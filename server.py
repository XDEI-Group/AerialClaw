"""
server.py — AerialClaw 控制台后端服务

提供：
  - REST API  : 系统初始化、世界状态查询、技能列表
  - WebSocket : 实时技能执行、执行日志推送、状态更新
  - 模式切换  : 手动模式（用户按按钮选技能）↔ AI 模式（LLM 自主规划执行）

启动：
  pip install flask flask-socketio flask-cors
  python server.py

前端连接：
  ws://localhost:5001  (Socket.IO)
  http://localhost:5001/api/...
"""

import sys
import os
import json
import time
import base64
import threading
import logging
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS

# ── 日志 ──────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── 静态文件目录（React build 产物）────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_UI_DIST  = os.path.join(_BASE_DIR, "ui", "dist")

# ── Flask 应用 ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=_UI_DIST, static_url_path="")
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "aerialclaw-dev")
CORS(app, resources={r"/api/*": {"origins": "*"}, r"/socket.io/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ══════════════════════════════════════════════════════════════════════════════
#  全局状态
# ══════════════════════════════════════════════════════════════════════════════

class AppState:
    """应用全局状态，单例。"""

    def __init__(self):
        self.mode: str = "manual"          # "manual" | "ai"
        self.is_executing: bool = False    # 当前是否正在执行技能
        self.current_robot: str = "UAV_1"  # 当前选中的机器人

        # 核心模块（延迟初始化）
        # robot_registries: {robot_id → SkillRegistry}  每台机器人独立注册表，技能执行历史互不干扰
        self.robot_registries: dict = {}
        self.world_model = None
        self.episodic_memory = None
        self.skill_memory = None
        self.runtime = None
        self.initialized: bool = False

        # 传感器桥接
        self.sensor_bridge = None

        # AI 模式线程
        self._ai_thread: Optional[threading.Thread] = None
        self._ai_stop_event = threading.Event()
        self._current_agent_loop = None  # 当前运行的 AgentLoop 实例

        # 执行日志缓冲（最多保留 200 条）
        self.log_buffer: list[dict] = []
        self._log_lock = threading.Lock()

    def push_log(self, level: str, msg: str, extra: dict = None):
        """追加日志并通过 WebSocket 广播。"""
        entry = {
            "ts": round(time.time() * 1000),
            "level": level,
            "msg": msg,
            **(extra or {}),
        }
        with self._log_lock:
            self.log_buffer.append(entry)
            if len(self.log_buffer) > 200:
                self.log_buffer.pop(0)
        socketio.emit("log", entry)

    def get_world_snapshot(self) -> dict:
        """返回当前世界状态（轻量版，供前端轮询/推送）。"""
        if not self.world_model:
            return {"robots": {}, "targets": []}
        state = self.world_model.get_world_state()
        return {
            "robots": state.get("robots", {}),
            "targets": state.get("targets", []),
            "timestamp": state.get("timestamp", 0),
        }


state = AppState()


# ══════════════════════════════════════════════════════════════════════════════
#  系统初始化
# ══════════════════════════════════════════════════════════════════════════════

def _build_robot_registry(robot_id: str, robot_type: str):
    """
    为单台机器人构建独立的 SkillRegistry，只注册该机器人类型支持的技能。
    每次调用都返回全新的实例（含独立的 Skill 对象），执行历史互不干扰。

    robot_type 匹配规则：
        skill.robot_type 为空列表 → 对所有类型可见（感知技能）
        否则 → robot_type 必须在列表中
    """
    from skills.registry import SkillRegistry
    from skills.motor_skills import (
        Takeoff, Land, FlyTo, Hover, GetPosition, GetBattery, ReturnToLaunch, ChangeAltitude,
        FlyRelative, LookAround, MarkLocation, GetMarks,
    )
    from skills.perception_skills import (
        DetectObject, RecognizeSpeech, FusePerception, ScanArea, GetSensorData, Observe,
    )
    from skills.cognitive_skills import (
        RunPython, HttpRequest, ReadFile, WriteFile,
    )

    # 全量技能工厂（每次都 new 出新实例，避免共享状态）
    ALL_SKILL_FACTORIES = [
        Takeoff, Land, FlyTo, FlyRelative, Hover, ChangeAltitude,
        GetPosition, GetBattery, ReturnToLaunch,
        LookAround, MarkLocation, GetMarks,
        # 软技能不再注册 Python 类，改为文档驱动 (skills/soft_docs/*.md)
        DetectObject, RecognizeSpeech, FusePerception, ScanArea, GetSensorData, Observe,
        # 认知技能（信息层）
        RunPython, HttpRequest, ReadFile, WriteFile,
    ]

    reg = SkillRegistry(auto_generate_doc=False)
    count = 0
    for SkillClass in ALL_SKILL_FACTORIES:
        instance = SkillClass()
        rt = instance.robot_type  # list, e.g. ["UAV"] or ["UAV","UGV"] or []
        if not rt or robot_type in rt:
            reg.register_skill(instance)
            count += 1

    return reg, count


def _do_init():
    """在后台线程中初始化所有模块，避免阻塞 HTTP 响应。"""
    global state
    try:
        state.push_log("info", "系统初始化中...")

        from memory.world_model import WorldModel
        from memory.episodic_memory import EpisodicMemory
        from memory.skill_memory import SkillMemory
        from runtime.agent_runtime import AgentRuntime
        from memory.reflection_engine import ReflectionEngine
        from memory.skill_evolution import SkillEvolution

        # ── 世界模型 ─────────────────────────────────────────────────────────
        state.world_model = WorldModel()
        robots_init = [
            ("UAV_1", "UAV", [0, 0, 0], 92.0),
        ]
        for rid, rtype, pos, bat in robots_init:
            state.world_model.register_robot(rid, rtype, initial_position=pos, battery=bat)
        state.push_log("success", "世界模型初始化 (UAV_1)")

        # ── 每台机器人独立注册表 ─────────────────────────────────────────────
        # 同类型的两台 UAV 各自拥有独立的 Skill 实例，执行历史互不干扰
        state.robot_registries = {}
        for rid, rtype, _, _ in robots_init:
            reg, count = _build_robot_registry(rid, rtype)
            state.robot_registries[rid] = reg
            state.push_log("info", f"  {rid} ({rtype}): 注册 {count} 个技能")

        total = sum(len(r) for r in state.robot_registries.values())
        state.push_log("success", f"技能注册完成：{len(state.robot_registries)} 台机器人，共 {total} 个技能实例")

        # ── 记忆模块 ─────────────────────────────────────────────────────────
        state.episodic_memory = EpisodicMemory()
        state.skill_memory = SkillMemory()

        # ── 反思引擎 + 技能进化 ──────────────────────────────────────────────
        try:
            from llm_client import get_client
            reflection_client = get_client(module="planner")
            reflection_engine = ReflectionEngine(
                llm_client=reflection_client,
                skill_memory=state.skill_memory,
            )
            skill_evolution = SkillEvolution(persist=True)
            state.push_log("success", "反思引擎 + 技能进化模块已加载")
        except Exception as e:
            reflection_engine = None
            skill_evolution = None
            state.push_log("warning", f"反思引擎加载失败(非致命): {e}")

        # ── 运行时（传入 per-robot 注册表字典）───────────────────────────────
        state.runtime = AgentRuntime(
            state.robot_registries,
            state.world_model,
            state.episodic_memory,
            state.skill_memory,
            reflection_engine=reflection_engine,
            skill_evolution=skill_evolution,
        )

        state.initialized = True
        state.push_log("success", "✅ 系统初始化完成，等待设备接入")
        state.push_log("info", "💡 仿真设备: cd simulator && python sim_client.py")

        # 推送初始世界状态
        socketio.emit("world_state", state.get_world_snapshot())
        socketio.emit("skill_catalog", _get_skill_catalog())
        socketio.emit("system_status", _get_system_status())

        # 启动设备管理器
        _get_device_manager()

    except Exception as e:
        logger.exception("初始化失败")
        state.push_log("error", f"初始化失败: {e}")


def _try_connect_adapter():
    """通过 adapter_manager 连接仿真环境，连上后启动遥测同步线程。"""
    def _connect():
        try:
            from adapters.adapter_manager import init_adapter, get_adapter
            state.push_log("info", "正在连接仿真适配器 (PX4 MAVSDK)...")
            ok = init_adapter("px4", connection_str="udp://:14540", timeout=10)
            adapter = get_adapter()
            if ok:
                state.push_log("success", f"✅ 仿真适配器连接成功: {adapter.name}")
            else:
                state.push_log("warn", f"仿真适配器降级为: {adapter.name}")
            _start_telemetry_sync()
        except Exception as e:
            state.push_log("warn", f"仿真适配器不可用: {e}，以 mock 模式运行")

    t = threading.Thread(target=_connect, daemon=True)
    t.start()


def _start_telemetry_sync():
    """后台持续读取仿真遥测数据，同步到 WorldModel 并推送前端。"""
    def _sync_loop():
        from adapters.adapter_manager import get_adapter
        _reconnect_attempts = 0
        _MAX_RECONNECT_INTERVAL = 30  # 最大重连间隔(秒)

        while state.initialized:
            try:
                adapter = get_adapter()
                if adapter and not adapter.is_connected():
                    # mavsdk_server 可能崩了，尝试自动重连
                    _reconnect_attempts += 1
                    wait = min(5 * _reconnect_attempts, _MAX_RECONNECT_INTERVAL)
                    if _reconnect_attempts <= 3 or _reconnect_attempts % 10 == 0:
                        logger.warning(f"PX4 连接丢失，{wait}秒后尝试第{_reconnect_attempts}次重连...")
                        state.push_log("warning", f"⚠️ MAVSDK 连接丢失，正在重连 (第{_reconnect_attempts}次)...")
                    time.sleep(wait)
                    ok = adapter.connect(timeout=15)
                    if ok:
                        logger.info("PX4 自动重连成功")
                        state.push_log("success", "✅ MAVSDK 自动重连成功")
                        _reconnect_attempts = 0
                    continue
                if adapter and adapter.is_connected():
                    _reconnect_attempts = 0
                    st = adapter.get_state()
                    update = {"robots": {"UAV_1": {}}}

                    if st.battery_percent > 0:
                        raw = st.battery_percent
                        # MAVSDK remaining_percent: 通常 0-100
                        # 但 PX4 SITL 有时返回异常值, 做多层兜底
                        if raw > 100:
                            pct = raw / 100.0   # 可能是 0-10000 的万分比
                            if pct > 100:
                                pct = 100.0     # 仍然超 100, 封顶
                        elif raw <= 1.0:
                            pct = raw * 100.0   # 0-1 范围, 转百分比
                        else:
                            pct = raw           # 正常 0-100
                        pct = max(0.0, min(100.0, round(pct, 1)))
                        update["robots"]["UAV_1"]["battery"] = pct
                    if st.position_ned:
                        p = st.position_ned
                        update["robots"]["UAV_1"]["position"] = [round(p.north, 2), round(p.east, 2), round(p.altitude, 2)]
                    if not state.is_executing:
                        update["robots"]["UAV_1"]["status"] = "airborne" if st.in_air else "idle"
                        update["robots"]["UAV_1"]["in_air"] = st.in_air

                    state.world_model.update_world_state(update)
                    socketio.emit("world_state", state.get_world_snapshot())
            except Exception:
                pass
            time.sleep(1)

    t = threading.Thread(target=_sync_loop, daemon=True, name="telemetry-sync")
    t.start()
    state.push_log("info", "遥测同步线程已启动（1Hz 刷新位置/电量/状态）")


def _start_sensor_bridge():
    """启动 Gazebo 传感器桥接，开始推送相机和雷达数据到前端。"""
    def _init_bridge():
        try:
            from sim.gz_sensor_bridge import GzSensorBridge
            from skills.perception_skills import set_sensor_bridge

            # 从 start.py 传入的环境变量读取 world 名
            world = os.environ.get("PX4_GZ_WORLD", "urban_rescue")
            model = os.environ.get("PX4_SIM_MODEL", "x500_lidar_2d_cam") + "_0"
            bridge = GzSensorBridge(model_name=model, world_name=world)

            if bridge.start():
                state.sensor_bridge = bridge
                set_sensor_bridge(bridge)
                state.push_log("success", f"📷 传感器桥接启动 (world={world}, model={model})")
                logger.info("开始启动传感器数据推送线程...")
                # 启动数据推送线程
                try:
                    _start_sensor_stream()
                    logger.info("传感器数据推送线程启动成功")
                except Exception as e:
                    logger.error(f"传感器数据推送线程启动失败: {e}", exc_info=True)

                # 生成 BODY.md (身体认知文档)
                _generate_body_md()

                # 启动感知守护线程
                _start_perception_daemon()
            else:
                state.push_log("warn", "传感器桥接启动失败（Gazebo 可能未运行）")

        except ImportError as e:
            state.push_log("warn", f"传感器桥接不可用: {e}")
            logger.error(f"传感器桥接导入失败: {e}", exc_info=True)
        except Exception as e:
            state.push_log("warn", f"传感器桥接异常: {e}")
            logger.error(f"传感器桥接异常: {e}", exc_info=True)

    def _generate_body_md():
        """生成 BODY.md 身体认知文档。"""
        try:
            from robot_profile.body_generator import generate_body_md
            from adapters.adapter_manager import get_adapter
            adapter = get_adapter()
            skill_reg = None
            for rid, reg in state.robot_registries.items():
                skill_reg = reg
                break
            generate_body_md(
                adapter=adapter,
                sensor_bridge=state.sensor_bridge,
                skill_registry=skill_reg,
            )
            state.push_log("info", "BODY.md 身体认知文档已生成")
        except Exception as e:
            logger.warning("BODY.md 生成失败: %s", e)

    def _start_perception_daemon():
        """启动感知守护线程。"""
        try:
            from perception.daemon import init_daemon
            from adapters.adapter_manager import get_adapter
            adapter = get_adapter()
            daemon = init_daemon(
                sensor_bridge=state.sensor_bridge,
                adapter=adapter,
                update_interval=3.0,
            )
            state.push_log("info", "感知守护线程已启动 (3s 间隔)")
        except Exception as e:
            logger.warning("感知守护线程启动失败: %s", e)
            state.push_log("warn", f"感知守护线程启动失败: {e}")

    def _spawn_camera_dynamic(world: str):
        """动态 spawn OakD-Lite 相机到 Gazebo 世界"""
        try:
            import subprocess

            logger.info(f"开始动态 spawn 相机到 world={world}")

            # 用 SDF 文件 spawn（避免引号转义问题）
            sdf_file = os.path.join(_BASE_DIR, "config", "camera_spawn.sdf")
            with open(sdf_file, "r") as f:
                sdf_content = f.read()

            cmd = [
                "gz", "service",
                "-s", f"/world/{world}/create",
                "--reqtype", "gz.msgs.EntityFactory",
                "--reptype", "gz.msgs.Boolean",
                "--timeout", "5000",
                "--req", f'sdf: "{sdf_content}"'
            ]
            logger.info(f"执行 gz service spawn 相机")
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            logger.info(f"spawn 结果: rc={result.returncode}, stdout={result.stdout.decode()}, stderr={result.stderr.decode()}")
            if result.returncode == 0 and b"true" in result.stdout:
                state.push_log("success", "📷 OakD-Lite 相机已动态 spawn 到世界")
            else:
                state.push_log("warn", f"相机 spawn 失败: rc={result.returncode} {result.stderr.decode()}")

        except Exception as e:
            logger.error(f"相机 spawn 异常: {e}", exc_info=True)
            state.push_log("warn", f"相机 spawn 异常: {e}")

    # 延迟 15 秒等 Gazebo + PX4 完全启动
    def _delayed_init():
        time.sleep(15)
        _init_bridge()

    t = threading.Thread(target=_delayed_init, daemon=True, name="sensor-bridge-init")
    t.start()


def _start_sensor_stream():
    """后台线程：周期性推送 4 相机 + 激光雷达数据到前端 WebSocket。"""
    import base64
    import cv2
    import math

    DIRECTIONS = ["front", "rear", "left", "right", "down"]

    def _stream_loop():
        while state.initialized and state.sensor_bridge and state.sensor_bridge.is_running:
            try:
                bridge = state.sensor_bridge

                # ── 4 相机帧 ──
                cameras_payload = {}
                for d in DIRECTIONS:
                    img = bridge.get_camera_image(d)
                    if img is not None:
                        _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 50])
                        b64 = base64.b64encode(buf.tobytes()).decode("ascii")
                        info = bridge.get_camera_info(d)
                        cameras_payload[d] = {
                            "image": b64,
                            "width": info["width"],
                            "height": info["height"],
                            "fps": round(info["fps"], 1),
                        }
                if cameras_payload:
                    socketio.emit("sensor_cameras", cameras_payload)

                # 兼容旧前端：也发 sensor_camera (front)
                if "front" in cameras_payload:
                    socketio.emit("sensor_camera", cameras_payload["front"])

                # ── 激光雷达 ──
                scan = bridge.get_lidar_scan()
                if scan is not None:
                    ranges = scan["ranges"]
                    rmax = scan["range_max"]
                    rmin = scan["range_min"]
                    v_count = scan.get("vertical_count", 1)
                    h_count = scan.get("count", len(ranges))
                    is_3d = scan.get("is_3d", False)

                    if is_3d and v_count > 1:
                        # 3D 点云: ranges 按 [h0v0, h0v1, ..., h0vN, h1v0, ...] 排列
                        # 每个水平角度有 v_count 个垂直采样
                        # 降采样水平方向到最多 180 线
                        h_step = max(1, h_count // 180)
                        v_angle_min = scan.get("vertical_angle_min", 0)
                        v_angle_max = scan.get("vertical_angle_max", 0)

                        # 提取每层的水平扫描
                        layers = []
                        for vi in range(v_count):
                            layer_ranges = []
                            for hi in range(0, h_count, h_step):
                                idx = hi * v_count + vi
                                if idx < len(ranges):
                                    r = ranges[idx]
                                    layer_ranges.append(
                                        round(r, 2) if (math.isfinite(r) and r >= rmin) else rmax
                                    )
                            layers.append(layer_ranges)

                        socketio.emit("sensor_lidar", {
                            "is_3d": True,
                            "layers": layers,
                            "h_count": len(layers[0]) if layers else 0,
                            "v_count": v_count,
                            "angle_min": scan["angle_min"],
                            "angle_max": scan["angle_max"],
                            "angle_increment": scan["angle_increment"] * h_step,
                            "v_angle_min": v_angle_min,
                            "v_angle_max": v_angle_max,
                            "range_min": rmin,
                            "range_max": rmax,
                            "count": len(layers[0]) if layers else 0,
                            "total_points": scan.get("total_points", len(ranges)),
                            "fps": round(bridge.get_lidar_info()["fps"], 1),
                        })
                    else:
                        # 2D 兼容模式
                        step = max(1, len(ranges) // 270)
                        actual_increment = scan["angle_increment"] * step
                        clean_ranges = [
                            round(r, 2) if (math.isfinite(r) and r >= rmin) else rmax
                            for r in ranges[::step]
                        ]
                        socketio.emit("sensor_lidar", {
                            "is_3d": False,
                            "ranges": clean_ranges,
                            "angle_min": scan["angle_min"],
                            "angle_max": scan["angle_max"],
                            "angle_increment": actual_increment,
                            "range_min": rmin,
                            "range_max": rmax,
                            "count": len(clean_ranges),
                            "fps": round(bridge.get_lidar_info()["fps"], 1),
                        })

            except Exception as e:
                logger.debug(f"传感器推送异常: {e}")

            time.sleep(0.1)  # 10 FPS

    t = threading.Thread(target=_stream_loop, daemon=True, name="sensor-stream")
    t.start()
    state.push_log("info", "传感器数据推送线程已启动（10Hz 4相机/雷达）")


def _get_skill_catalog(robot_id: str = None) -> dict:
    """
    返回技能表。
    - robot_id 指定时：返回该机器人的技能列表（list）
    - robot_id 为 None 时：返回所有机器人的技能表字典 {robot_id: [skills]}
    """
    if not state.robot_registries:
        return {} if robot_id is None else []
    if robot_id:
        reg = state.robot_registries.get(robot_id)
        return reg.get_skill_catalog() if reg else []
    return {
        rid: reg.get_skill_catalog()
        for rid, reg in state.robot_registries.items()
    }


def _get_system_status() -> dict:
    return {
        "initialized": state.initialized,
        "mode": state.mode,
        "is_executing": state.is_executing,
        "current_robot": state.current_robot,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  REST API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/init", methods=["POST"])
def api_init():
    """初始化系统（异步，通过 WebSocket 推送进度）。"""
    if state.initialized:
        return jsonify({"ok": True, "msg": "系统已初始化"})
    t = threading.Thread(target=_do_init, daemon=True)
    t.start()
    return jsonify({"ok": True, "msg": "初始化中，请监听 WebSocket log 事件"})


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(_get_system_status())


@app.route("/api/world", methods=["GET"])
def api_world():
    return jsonify(state.get_world_snapshot())


@app.route("/api/skills", methods=["GET"])
def api_skills():
    """返回全部机器人技能表 {robot_id: [skills]}，或指定机器人 ?robot=UAV_1。"""
    robot_id = request.args.get("robot")
    return jsonify(_get_skill_catalog(robot_id))


# ── 软技能管理 API ────────────────────────────────────────────────────────────

@app.route("/api/skills/soft", methods=["GET"])
def api_soft_skills():
    """返回所有软技能列表和摘要。"""
    from skills.soft_skill_manager import get_soft_skill_manager
    mgr = get_soft_skill_manager()
    skills = []
    for name in mgr.list_skills():
        info = mgr._cache.get(name, {})
        skills.append({
            "name": name,
            "title": info.get("title", name),
            "summary": info.get("summary", ""),
            "path": info.get("path", ""),
        })
    return jsonify({"ok": True, "skills": skills, "count": len(skills)})


@app.route("/api/skills/soft/<name>", methods=["GET"])
def api_soft_skill_detail(name):
    """获取单个软技能的完整文档。"""
    from skills.soft_skill_manager import get_soft_skill_manager
    mgr = get_soft_skill_manager()
    doc = mgr.get_skill_doc(name)
    if not doc:
        return jsonify({"ok": False, "msg": f"软技能 '{name}' 不存在"}), 404
    return jsonify({"ok": True, "name": name, "content": doc})


@app.route("/api/skills/soft", methods=["POST"])
def api_create_soft_skill():
    """手动创建软技能文档。body: {"name": str, "content": str}"""
    from skills.soft_skill_manager import get_soft_skill_manager
    mgr = get_soft_skill_manager()
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    content = data.get("content", "").strip()
    if not name or not content:
        return jsonify({"ok": False, "msg": "name 和 content 不能为空"}), 400
    if mgr.skill_exists(name):
        return jsonify({"ok": False, "msg": f"软技能 '{name}' 已存在"}), 409
    path = mgr.create_skill(name, content)
    return jsonify({"ok": True, "name": name, "path": path})


@app.route("/api/skills/soft/<name>", methods=["DELETE"])
def api_delete_soft_skill(name):
    """删除(淘汰)软技能。"""
    from skills.soft_skill_manager import get_soft_skill_manager
    mgr = get_soft_skill_manager()
    if not mgr.skill_exists(name):
        return jsonify({"ok": False, "msg": f"软技能 '{name}' 不存在"}), 404
    mgr.remove_skill(name)
    return jsonify({"ok": True, "name": name, "msg": "已淘汰"})


@app.route("/api/skills/soft/patterns", methods=["GET"])
def api_soft_skill_patterns():
    """检测重复模式, 返回可能生成新软技能的候选模式。"""
    from skills.dynamic_skill_gen import detect_patterns
    from memory.task_log import TaskLogger
    tl = TaskLogger()
    logs = tl.get_all_logs()
    min_count = int(request.args.get("min_count", 3))
    patterns = detect_patterns(logs, min_count=min_count)
    return jsonify({"ok": True, "patterns": patterns, "total_logs": len(logs)})


@app.route("/api/skills/soft/generate", methods=["POST"])
def api_generate_soft_skill():
    """
    根据指定的模式自动生成软技能文档。
    body: {"pattern": {"pattern": [...], "count": N, ...}}
    """
    from skills.soft_skill_manager import get_soft_skill_manager
    from skills.dynamic_skill_gen import generate_soft_skill_doc
    from llm_client import get_client

    mgr = get_soft_skill_manager()
    data = request.get_json() or {}
    pattern = data.get("pattern")
    if not pattern:
        return jsonify({"ok": False, "msg": "缺少 pattern 字段"}), 400

    try:
        client = get_client(module="doc_generator")
        result = generate_soft_skill_doc(
            pattern=pattern,
            llm_client=client,
            existing_skills=mgr.list_skills(),
        )
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500

    if result is None:
        return jsonify({"ok": False, "msg": "LLM 建议跳过或生成失败"})

    path = mgr.create_skill(result["name"], result["content"])
    return jsonify({"ok": True, "name": result["name"], "path": path})


@app.route("/api/skills/soft/retire", methods=["POST"])
def api_retire_soft_skills():
    """
    检查并淘汰不合格的软技能。
    body: {"dry_run": true/false}  默认 dry_run=true
    """
    from skills.soft_skill_manager import get_soft_skill_manager
    from skills.dynamic_skill_gen import get_retirement_candidates, retire_skills

    mgr = get_soft_skill_manager()
    data = request.get_json() or {}
    dry_run = data.get("dry_run", True)

    # 尝试获取 skill_evolution (可能不存在)
    skill_evolution = None
    if state.runtime and hasattr(state.runtime, '_skill_evolution'):
        skill_evolution = state.runtime._skill_evolution

    candidates = get_retirement_candidates(mgr, skill_evolution)
    if dry_run:
        return jsonify({"ok": True, "dry_run": True, "candidates": candidates})
    else:
        retired = retire_skills(mgr, candidates, dry_run=False)
        return jsonify({"ok": True, "dry_run": False, "retired": retired, "count": len(retired)})


# ── 模型配置 API ──────────────────────────────────────────────────────────────

@app.route("/api/llm/config", methods=["GET"])
def api_llm_config():
    """
    返回当前 LLM 配置: 所有 provider、激活的 provider、各模块配置。
    API key 只返回掩码版本。
    """
    import config as cfg

    def _mask_key(key):
        if not key or len(key) < 8:
            return "***"
        return key[:4] + "..." + key[-4:]

    providers = {}
    for name, p in cfg.PROVIDERS.items():
        providers[name] = {
            "api_type": p.get("api_type", "openai_compat"),
            "base_url": p.get("base_url", ""),
            "api_key_masked": _mask_key(p.get("api_key", "")),
            "default_model": p.get("default_model", ""),
            "timeout": p.get("timeout", 60),
        }

    modules = {}
    for mod, mc in cfg.MODULE_CONFIG.items():
        resolved_provider = mc.get("provider") or cfg.ACTIVE_PROVIDER
        resolved_model = mc.get("model") or cfg.PROVIDERS.get(resolved_provider, {}).get("default_model", "")
        modules[mod] = {
            "provider": mc.get("provider"),
            "model": mc.get("model"),
            "resolved_provider": resolved_provider,
            "resolved_model": resolved_model,
        }

    return jsonify({
        "ok": True,
        "active_provider": cfg.ACTIVE_PROVIDER,
        "providers": providers,
        "modules": modules,
    })


@app.route("/api/llm/active", methods=["PUT"])
def api_set_active_provider():
    """切换全局激活 provider。body: {"provider": "ollama_local"}"""
    import config as cfg
    data = request.get_json() or {}
    provider = data.get("provider", "").strip()
    if not provider:
        return jsonify({"ok": False, "msg": "provider 不能为空"}), 400
    if provider not in cfg.PROVIDERS:
        return jsonify({"ok": False, "msg": f"未知 provider: {provider}"}), 404
    cfg.ACTIVE_PROVIDER = provider
    state.push_log("info", f"全局 LLM 已切换到: {provider} ({cfg.PROVIDERS[provider]['default_model']})")
    return jsonify({"ok": True, "active_provider": provider})


@app.route("/api/llm/module/<module_name>", methods=["PUT"])
def api_set_module_config(module_name):
    """
    设置模块级 LLM 配置。
    body: {"provider": "openai", "model": "gpt-4o"}
    provider/model 设为 null 表示跟随全局。
    """
    import config as cfg
    if module_name not in cfg.MODULE_CONFIG:
        return jsonify({"ok": False, "msg": f"未知模块: {module_name}"}), 404
    data = request.get_json() or {}
    if "provider" in data:
        p = data["provider"]
        if p is not None and p not in cfg.PROVIDERS:
            return jsonify({"ok": False, "msg": f"未知 provider: {p}"}), 400
        cfg.MODULE_CONFIG[module_name]["provider"] = p
    if "model" in data:
        cfg.MODULE_CONFIG[module_name]["model"] = data["model"]
    resolved_p = cfg.MODULE_CONFIG[module_name].get("provider") or cfg.ACTIVE_PROVIDER
    resolved_m = cfg.MODULE_CONFIG[module_name].get("model") or cfg.PROVIDERS.get(resolved_p, {}).get("default_model", "")
    state.push_log("info", f"模块 {module_name} LLM 配置更新: {resolved_p}/{resolved_m}")
    return jsonify({"ok": True, "module": module_name, "resolved_provider": resolved_p, "resolved_model": resolved_m})


@app.route("/api/llm/provider", methods=["POST"])
def api_add_provider():
    """
    新增或更新一个 provider。
    body: {
      "name": "my_provider",
      "base_url": "https://...",
      "api_key": "sk-...",
      "default_model": "gpt-4o",
      "timeout": 60
    }
    """
    import config as cfg
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    base_url = data.get("base_url", "").strip()
    api_key = data.get("api_key", "").strip()
    default_model = data.get("default_model", "").strip()
    timeout = data.get("timeout", 60)

    if not name:
        return jsonify({"ok": False, "msg": "name 不能为空"}), 400
    if not base_url:
        return jsonify({"ok": False, "msg": "base_url 不能为空"}), 400
    if not default_model:
        return jsonify({"ok": False, "msg": "default_model 不能为空"}), 400

    is_new = name not in cfg.PROVIDERS
    cfg.PROVIDERS[name] = {
        "api_type": "openai_compat",
        "base_url": base_url.rstrip("/"),
        "api_key": api_key or "none",
        "default_model": default_model,
        "timeout": int(timeout),
    }
    action = "新增" if is_new else "更新"
    state.push_log("success", f"{action} LLM 渠道: {name} ({default_model} @ {base_url})")
    return jsonify({"ok": True, "action": action, "name": name})


@app.route("/api/llm/provider/<name>", methods=["DELETE"])
def api_delete_provider(name):
    """删除一个 provider (不能删除当前激活的)。"""
    import config as cfg
    if name not in cfg.PROVIDERS:
        return jsonify({"ok": False, "msg": f"provider '{name}' 不存在"}), 404
    if name == cfg.ACTIVE_PROVIDER:
        return jsonify({"ok": False, "msg": "不能删除当前激活的 provider"}), 400
    del cfg.PROVIDERS[name]
    state.push_log("info", f"已删除 LLM 渠道: {name}")
    return jsonify({"ok": True, "name": name})


@app.route("/api/mode", methods=["POST"])
def api_set_mode():
    """切换 manual / ai 模式。"""
    data = request.get_json() or {}
    new_mode = data.get("mode", "manual")
    if new_mode not in ("manual", "ai"):
        return jsonify({"ok": False, "msg": "mode 必须是 manual 或 ai"}), 400

    if new_mode == state.mode:
        return jsonify({"ok": True, "msg": f"已是 {new_mode} 模式"})

    # 如果从 AI → Manual，停止 AI 线程
    if state.mode == "ai" and new_mode == "manual":
        state._ai_stop_event.set()
        state.push_log("info", "已切换到手动模式，AI 规划已停止")

    state.mode = new_mode
    socketio.emit("system_status", _get_system_status())

    if new_mode == "ai":
        state.push_log("info", "已切换到 AI 模式，等待任务指令")

    return jsonify({"ok": True, "mode": state.mode})


@app.route("/api/logs", methods=["GET"])
def api_logs():
    """返回最近的日志缓冲。"""
    with state._log_lock:
        return jsonify(state.log_buffer[-100:])


@app.route("/api/sensor/status", methods=["GET"])
def api_sensor_status():
    """返回传感器桥接状态。"""
    if state.sensor_bridge:
        return jsonify(state.sensor_bridge.get_status())
    return jsonify({"running": False, "error": "传感器桥接未启动"})


@app.route("/api/sensor/camera", methods=["GET"])
def api_sensor_camera():
    """返回最新一帧相机 JPEG 图像。"""
    if not state.sensor_bridge:
        return jsonify({"error": "传感器桥接未启动"}), 503
    img = state.sensor_bridge.get_camera_image()
    if img is None:
        return jsonify({"error": "暂无相机数据"}), 503
    import cv2
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    from flask import Response
    return Response(buf.tobytes(), mimetype="image/jpeg")


@app.route("/api/sensor/lidar", methods=["GET"])
def api_sensor_lidar():
    """返回最新激光雷达数据 JSON。"""
    if not state.sensor_bridge:
        return jsonify({"error": "传感器桥接未启动"}), 503
    scan = state.sensor_bridge.get_lidar_scan()
    if scan is None:
        return jsonify({"error": "暂无雷达数据"}), 503
    # inf/nan 不是合法 JSON，替换为 range_max
    import math
    rmax = scan["range_max"]
    scan["ranges"] = [
        r if (math.isfinite(r) and r >= scan["range_min"]) else rmax
        for r in scan["ranges"]
    ]
    return jsonify(scan)


# ── 前端静态文件服务 ──────────────────────────────────────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    """Serve React build dist. Non-API routes fall through to index.html (SPA)."""
    if path.startswith("api/") or path.startswith("socket.io"):
        return jsonify({"error": "not found"}), 404
    if path and os.path.exists(os.path.join(_UI_DIST, path)):
        return send_from_directory(_UI_DIST, path)
    index = os.path.join(_UI_DIST, "index.html")
    if os.path.exists(index):
        return send_file(index)
    return "<h2>前端未构建，请先运行 cd ui && npm run build</h2>", 200


# ══════════════════════════════════════════════════════════════════════════════
#  WebSocket 事件
# ══════════════════════════════════════════════════════════════════════════════

@socketio.on("connect")
def on_connect():
    logger.info("客户端连接: %s", request.sid)
    # 推送当前状态给新连接的客户端
    emit("system_status", _get_system_status())
    emit("world_state", state.get_world_snapshot())
    if state.robot_registries:
        emit("skill_catalog", _get_skill_catalog())
    # 推送历史日志
    with state._log_lock:
        for entry in state.log_buffer[-50:]:
            emit("log", entry)


@socketio.on("disconnect")
def on_disconnect():
    logger.info("客户端断开: %s", request.sid)


@socketio.on("execute_skill")
def on_execute_skill(data):
    """
    手动模式：执行单个技能。
    data: {
        "robot_id": "UAV_1",
        "skill_name": "takeoff",
        "parameters": {"altitude": 5.0}
    }
    """
    if not state.initialized:
        emit("skill_result", {"ok": False, "error": "系统未初始化"})
        return

    if state.mode != "manual":
        emit("skill_result", {"ok": False, "error": "当前不是手动模式"})
        return

    if state.is_executing:
        emit("skill_result", {"ok": False, "error": "正在执行中，请稍候"})
        return

    robot_id = data.get("robot_id", state.current_robot)
    skill_name = data.get("skill_name", "")
    parameters = data.get("parameters", {})

    if not skill_name:
        emit("skill_result", {"ok": False, "error": "skill_name 不能为空"})
        return

    # 在后台线程执行，避免阻塞 SocketIO 事件循环
    def _run():
        state.is_executing = True
        socketio.emit("system_status", _get_system_status())
        state.push_log("info", f"▶ 执行: [{robot_id}] {skill_name}", {"skill": skill_name, "robot": robot_id})

        try:
            result = state.runtime.dispatch_skill({
                "step": 1,
                "skill": skill_name,
                "robot": robot_id,
                "parameters": parameters,
            })

            ok = result.success
            level = "success" if ok else "error"
            state.push_log(level, f"{'✅' if ok else '❌'} {skill_name} → {'成功' if ok else '失败: ' + result.error_msg}",
                           {"skill": skill_name, "robot": robot_id, "output": result.output})

            # 回写该机器人的技能执行状态（per-robot 隔离）
            robot_reg = state.robot_registries.get(robot_id)
            if robot_reg:
                robot_reg.update_execution_status(skill_name, ok)

            result_payload = {
                "ok": ok,
                "skill": skill_name,
                "robot": robot_id,
                "output": result.output,
                "error": result.error_msg,
                "cost_time": result.cost_time,
                "logs": result.logs,
            }
            socketio.emit("skill_result", result_payload)

            # 推送更新后的世界状态
            socketio.emit("world_state", state.get_world_snapshot())
            socketio.emit("skill_catalog", _get_skill_catalog())

        except Exception as e:
            logger.exception("技能执行异常")
            state.push_log("error", f"技能执行异常: {e}")
            socketio.emit("skill_result", {"ok": False, "error": str(e), "skill": skill_name, "robot": robot_id})
        finally:
            state.is_executing = False
            socketio.emit("system_status", _get_system_status())

    t = threading.Thread(target=_run, daemon=True)
    t.start()


@socketio.on("select_robot")
def on_select_robot(data):
    """切换当前选中机器人。"""
    robot_id = data.get("robot_id", "UAV_1")
    state.current_robot = robot_id
    state.push_log("info", f"选中机器人: {robot_id}")
    emit("system_status", _get_system_status())


@socketio.on("ai_task")
def on_ai_task(data):
    """
    AI 模式：提交自然语言任务，让 LLM 规划并执行。
    data: {"task": "搜索北部区域，发现目标后拍照记录", "use_tools": false}
    """
    if not state.initialized:
        emit("ai_plan_result", {"ok": False, "error": "系统未初始化"})
        return

    if state.mode != "ai":
        emit("ai_plan_result", {"ok": False, "error": "请先切换到 AI 模式"})
        return

    # ── Check LLM configuration before executing ──
    try:
        import config as cfg
        provider_name = cfg.ACTIVE_PROVIDER
        provider_cfg = cfg.PROVIDERS.get(provider_name, {})
        api_key = provider_cfg.get("api_key", "")
        if not api_key or api_key in ("", "your-llm-api-key-here", "your-key-here"):
            emit("ai_plan_result", {
                "ok": False,
                "error": f"LLM 未配置: 当前 provider [{provider_name}] 的 API Key 为空。请先在 .env 文件中配置 API Key，或通过界面右上角 ⚙️ 添加模型。"
            })
            return
    except Exception:
        pass

    if state.is_executing:
        # 执行中: 注入用户消息
        task = data.get("task", "")
        if task and state._current_agent_loop:
            state._current_agent_loop.inject_user_message(task)
            emit("ai_plan_result", {"ok": True, "injected": True, "message": f"已注入指令: {task[:50]}"})
        else:
            emit("ai_plan_result", {"ok": False, "error": "正在执行中，请稍候"})
        return

    task = data.get("task", "")
    use_tools = data.get("use_tools", False)

    if not task:
        emit("ai_plan_result", {"ok": False, "error": "任务描述不能为空"})
        return

    state._ai_stop_event.clear()

    def _run_ai():
        state.is_executing = True
        socketio.emit("system_status", _get_system_status())
        state.push_log("info", f"🤖 AI 任务: {task}")

        try:
            # ai_task 是明确的任务执行入口，直接启动自主 Agent 循环
            # 对话/查询类请求走 ai_chat 入口；ai_task 始终执行 AgentLoop
            from llm_client import get_client
            client = get_client(module="planner")

            import brain.planner_agent as planner

            # 使用 AgentLoop 自主执行任务
            socketio.emit("ai_thinking", {"phase": "planning", "detail": "正在启动自主 Agent..."})
            state.push_log("info", "🧠 启动 Agent 自主循环...")

            from brain.agent_loop import AgentLoop
            reg = state.robot_registries.get(state.current_robot)

            def on_thinking(iteration, output):
                thinking = output.get("thinking", "")
                decision = output.get("decision", "")
                action = output.get("action", {})
                progress = output.get("goal_progress", "")
                socketio.emit("ai_thinking", {
                    "phase": "thinking",
                    "detail": f"[第{iteration}轮] {thinking[:80]}",
                    "iteration": iteration,
                    "decision": decision,
                    "action": action,
                    "progress": progress,
                })
                state.push_log("info", f"🧠 第{iteration}轮: {thinking[:60]}...")

                # 同时把 thinking 作为清洁文本推到 stream (而不是原始 JSON token)
                socketio.emit("ai_stream", {"token": "", "done": True})  # 清空上一轮
                clean_text = f"[第{iteration}轮] {thinking}"
                if progress:
                    clean_text += f"\n进度: {progress}"
                socketio.emit("ai_stream", {"token": clean_text, "done": False})

            def on_action(iteration, skill, params, result):
                status = "✅" if result.success else "❌"
                state.push_log(
                    "success" if result.success else "error",
                    f"  {status} {skill} ({result.cost_time:.1f}s)" + (f" - {result.error_msg}" if not result.success else ""),
                )
                socketio.emit("world_state", state.get_world_snapshot())

            final_result = {"success": False, "summary": ""}
            def on_complete(success, summary):
                final_result["success"] = success
                final_result["summary"] = summary
                socketio.emit("ai_thinking", {"phase": "idle", "detail": ""})
                # 把完成报告发到聊天框
                status_icon = "✅" if success else "❌"
                socketio.emit("ai_chat_reply", {
                    "ok": True,
                    "reply": f"{status_icon} 任务{'完成' if success else '未完成'}\n\n{summary}",
                    "intent": "task_report",
                })

            # LLM streaming 回调 — 禁用原始 token 推送, thinking 内容由 on_thinking 以清洁文本推送
            def _on_stream(token):
                pass  # 不再推送碎片 JSON token

            loop = AgentLoop(
                goal=task,
                llm_client=client,
                runtime=state.runtime,
                world_model=state.world_model,
                skill_registry=reg,
                max_iterations=15,
                on_thinking=on_thinking,
                on_action=on_action,
                on_complete=on_complete,
                on_stream=_on_stream,
                stop_event=state._ai_stop_event,
            )
            state._current_agent_loop = loop
            loop.run()
            state._current_agent_loop = None
            # 通知 streaming 结束
            socketio.emit("ai_stream", {"token": "", "done": True})

            # 推送执行报告
            summary = loop.get_summary()
            ok = final_result["success"]
            status_str = "✅ 目标达成" if ok else "❌ 任务未完成"
            state.push_log("success" if ok else "error",
                f"{status_str} | {summary['successful']}/{summary['total_actions']} 步成功 | {summary['iterations']} 轮思考")

            socketio.emit("ai_execution_report", {
                "ok": ok,
                "task": task,
                "completed_steps": summary["successful"],
                "total_steps": summary["total_actions"],
                "replans": 0,
                "cost_time": sum(h.get("cost_time", 0) for h in summary["history"]),
                "step_results": [
                    {"skill": h["skill"], "robot": "UAV_1", "success": h["success"],
                     "cost_time": h.get("cost_time", 0), "error": h.get("error")}
                    for h in summary["history"]
                ],
                "agent_iterations": summary["iterations"],
            })

        except Exception as e:
            logger.exception("AI 任务执行异常")
            state.push_log("error", f"AI 任务异常: {e}")
            socketio.emit("ai_plan_result", {"ok": False, "error": str(e)})
        finally:
            state.is_executing = False
            socketio.emit("system_status", _get_system_status())

    t = threading.Thread(target=_run_ai, daemon=True)
    t.start()


# ── AI 对话聊天 ──────────────────────────────────────────────────────────────

# 对话历史 (server 端维护, 每个 session 独立)
_chat_histories: dict = {}  # {sid: [{"role": str, "content": str}]}


@socketio.on("ai_chat")
def on_ai_chat(data):
    """
    统一对话入口: LLM 自己决定是聊天还是执行任务。
    不做硬编码意图识别, 让模型自主判断。
    data: {"message": "..."}
    """
    if not state.initialized:
        emit("ai_chat_reply", {"ok": False, "error": "系统未初始化"})
        return

    message = data.get("message", "").strip()
    if not message:
        emit("ai_chat_reply", {"ok": False, "error": "消息不能为空"})
        return

    sid = request.sid

    def _reply():
        from brain.chat_mode import unified_chat
        from llm_client import get_client

        if sid not in _chat_histories:
            _chat_histories[sid] = []
        history = _chat_histories[sid]

        client = get_client(module="planner")

        # 收集上下文: 感知摘要 + 世界状态 + 技能表
        perception_summary = ""
        try:
            from perception.daemon import get_daemon
            daemon = get_daemon()
            if daemon and daemon.is_running:
                perception_summary = daemon.get_summary()
        except ImportError:
            pass

        world_state = state.world_model.get_world_state()
        world_lines = []
        for rid, rd in world_state.get("robots", {}).items():
            pos = rd.get("position", [0, 0, 0])
            world_lines.append(
                f"{rid}: 位置 NED={pos}, 电量={rd.get('battery', '?')}%, "
                f"状态={rd.get('status', '?')}, 在空中={rd.get('in_air', '?')}"
            )
        world_state_str = "\n".join(world_lines) if world_lines else "(无)"

        # 技能表
        skill_table = ""
        reg = state.robot_registries.get(state.current_robot)
        if reg:
            try:
                from skills.skill_loader import build_skill_summary
                skill_table = build_skill_summary(reg.get_skill_catalog())
            except Exception:
                pass

        # 尝试获取最近的相机视觉描述 (VLM)
        camera_description = ""
        try:
            from perception.daemon import get_daemon
            daemon = get_daemon()
            if daemon and daemon.is_running:
                detailed = daemon.get_detailed_summary()
                camera_description = detailed.get("vlm", "")
        except Exception:
            pass

        # 统一调用 LLM
        result = unified_chat(
            user_input=message,
            chat_history=history,
            llm_client=client,
            skill_table=skill_table,
            perception_summary=perception_summary,
            world_state_str=world_state_str,
            camera_description=camera_description,
        )

        # 更新历史
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": result["text"]})
        if len(history) > 40:
            _chat_histories[sid] = history[-40:]

        if result["type"] == "plan" and result["plan"] and state.mode == "ai":
            # LLM 决定执行任务 — 启动自主 Agent 循环
            socketio.emit("ai_chat_reply", {
                "ok": True,
                "intent": "TASK",
                "reply": result["text"],
                "message": message,
            }, to=sid)

            state.push_log("info", f"🤖 启动自主任务: {message}")

            # 启动 AgentLoop
            _run_agent_loop(message, sid)
        else:
            # 纯对话
            socketio.emit("ai_chat_reply", {
                "ok": True,
                "intent": "CHAT",
                "reply": result["text"],
                "message": message,
            }, to=sid)

    t = threading.Thread(target=_reply, daemon=True)
    t.start()


def _run_agent_loop(goal, sid):
    """
    启动自主 Agent 循环。观察→思考→行动→反思, 直到目标达成。
    """
    if state.is_executing:
        # 任务执行中, 注入用户消息到 AgentLoop
        if state._current_agent_loop:
            state._current_agent_loop.inject_user_message(goal)
            socketio.emit("ai_chat_reply", {
                "ok": True, "intent": "INJECT",
                "reply": f"收到, 已将你的指令注入到当前任务: \"{goal[:50]}\"",
                "message": goal,
            }, to=sid)
        else:
            socketio.emit("ai_chat_reply", {
                "ok": True, "intent": "CHAT",
                "reply": "我正在执行另一个任务, 请等我完成。",
                "message": goal,
            }, to=sid)
        return

    state.is_executing = True
    state._ai_stop_event.clear()
    socketio.emit("system_status", _get_system_status())

    try:
        from brain.agent_loop import AgentLoop
        from llm_client import get_client

        client = get_client(module="planner")
        reg = state.robot_registries.get(state.current_robot)

        def on_thinking(iteration, output):
            thinking = output.get("thinking", "")
            decision = output.get("decision", "")
            progress = output.get("goal_progress", "")
            socketio.emit("ai_thinking", {
                "phase": "thinking",
                "detail": f"[第{iteration}轮] {thinking[:80]}",
                "decision": decision,
            })
            # 把思考过程推送到聊天
            socketio.emit("ai_chat_reply", {
                "ok": True, "intent": "THINKING",
                "reply": f"💭 {thinking}" + (f"\n📊 {progress}" if progress else ""),
                "message": goal,
            }, to=sid)
            state.push_log("info", f"🧠 第{iteration}轮: {thinking[:60]}...")

        def on_action(iteration, skill, params, result):
            status = "✅" if result.success else "❌"
            msg = f"{status} {skill}"
            if not result.success:
                msg += f" - {result.error_msg}"
            state.push_log("success" if result.success else "error", f"  {msg} ({result.cost_time:.1f}s)")
            socketio.emit("world_state", state.get_world_snapshot())

        def on_complete(success, summary):
            socketio.emit("ai_thinking", {"phase": "idle", "detail": ""})
            status = "✅ 目标达成" if success else "⚠️ 任务结束"
            state.push_log("success" if success else "warn", f"{status}: {summary[:80]}")
            socketio.emit("ai_chat_reply", {
                "ok": True, "intent": "RESULT",
                "reply": f"{status}\n{summary}",
                "message": goal,
            }, to=sid)

        loop = AgentLoop(
            goal=goal,
            llm_client=client,
            runtime=state.runtime,
            world_model=state.world_model,
            skill_registry=reg,
            max_iterations=15,
            on_thinking=on_thinking,
            on_action=on_action,
            on_complete=on_complete,
            on_stream=lambda token: socketio.emit("ai_stream", {"token": token, "done": False}),
            stop_event=state._ai_stop_event,
        )
        loop.run()
        socketio.emit("ai_stream", {"token": "", "done": True})

        # 推送执行报告
        summary = loop.get_summary()
        socketio.emit("ai_execution_report", {
            "ok": summary["failed"] == 0 and summary["total_actions"] > 0,
            "task": goal,
            "completed_steps": summary["successful"],
            "total_steps": summary["total_actions"],
            "replans": 0,
            "cost_time": sum(h.get("cost_time", 0) for h in summary["history"]),
            "step_results": [
                {"skill": h["skill"], "robot": "UAV_1", "success": h["success"],
                 "cost_time": h.get("cost_time", 0), "error": h.get("error")}
                for h in summary["history"]
            ],
            "agent_iterations": summary["iterations"],
        })
        socketio.emit("world_state", state.get_world_snapshot())
        socketio.emit("skill_catalog", _get_skill_catalog())

    except Exception as e:
        logger.exception("AgentLoop 异常")
        state.push_log("error", f"Agent 异常: {e}")
    finally:
        state.is_executing = False
        socketio.emit("system_status", _get_system_status())


def _execute_plan_from_chat(task, steps, sid):
    """
    从对话中触发的任务执行。
    复用 ai_task 的逐步执行 + 重规划逻辑。
    """
    if state.is_executing:
        socketio.emit("ai_chat_reply", {
            "ok": True, "intent": "CHAT",
            "reply": "我正在执行另一个任务, 请等我完成。",
            "message": task,
        }, to=sid)
        return

    state.is_executing = True
    state._ai_stop_event.clear()
    socketio.emit("system_status", _get_system_status())

    try:
        import time as _time
        MAX_REPLANS = 3
        replan_count = 0
        all_step_results = []
        final_success = False

        while replan_count <= MAX_REPLANS:
            state.push_log("info", f"🚀 执行 {len(steps)} 步" + (f" (重规划第{replan_count}次)" if replan_count > 0 else ""))
            total = len(steps)
            completed = 0
            failed_step = None
            failed_error = None

            for i, step_data in enumerate(steps):
                if state._ai_stop_event.is_set():
                    break

                skill_name = step_data.get("skill", "?")
                step_num = step_data.get("step", i + 1)
                socketio.emit("ai_thinking", {
                    "phase": "executing",
                    "detail": f"执行步骤 {step_num}/{total}: {skill_name}",
                    "current_step": step_num,
                    "total_steps": total,
                    "skill": skill_name,
                })

                result = state.runtime.dispatch_skill(step_data)
                all_step_results.append((step_data, result))

                robot_id = step_data.get("robot", state.current_robot)
                robot_reg = state.robot_registries.get(robot_id)
                if robot_reg:
                    robot_reg.update_execution_status(skill_name, result.success)

                if result.success:
                    completed += 1
                    state.push_log("success", f"✅ 步骤 {step_num}: {skill_name} ({result.cost_time:.1f}s)")
                else:
                    failed_step = step_data
                    failed_error = result.error_msg
                    state.push_log("error", f"❌ 步骤 {step_num}: {skill_name} - {result.error_msg}")
                    break

            if completed == total:
                final_success = True
                break
            if state._ai_stop_event.is_set():
                break

            # 重规划
            if failed_step and replan_count < MAX_REPLANS:
                replan_count += 1
                state.push_log("info", f"🔄 重规划 (第{replan_count}次)...")
                socketio.emit("ai_thinking", {"phase": "replanning", "detail": f"{failed_step.get('skill','?')} 失败, 重新规划..."})

                from brain.chat_mode import unified_chat
                from llm_client import get_client
                client = get_client(module="planner")

                world_state = state.world_model.get_world_state()
                w_lines = [f"{rid}: pos={rd.get('position')}, battery={rd.get('battery')}%, status={rd.get('status')}" for rid, rd in world_state.get("robots", {}).items()]

                history_str = "\n".join(f"  - {sd.get('skill','?')}: {'成功' if r.success else f'失败({r.error_msg})'}" for sd, r in all_step_results)
                replan_msg = f"刚才执行任务\"{task}\"时, 出了问题:\n{history_str}\n\n请根据当前状态重新规划。已成功的步骤不需要重复。"

                skill_table = ""
                reg = state.robot_registries.get(state.current_robot)
                if reg:
                    try:
                        from skills.skill_loader import build_skill_summary
                        skill_table = build_skill_summary(reg.get_skill_catalog())
                    except Exception:
                        pass

                replan_result = unified_chat(
                    user_input=replan_msg,
                    chat_history=[],
                    llm_client=client,
                    skill_table=skill_table,
                    world_state_str="\n".join(w_lines),
                )

                if replan_result["type"] == "plan" and replan_result["plan"]:
                    steps = replan_result["plan"]
                    state.push_log("info", f"📋 重规划: {len(steps)} 步 | {replan_result['text'][:60]}")
                    socketio.emit("ai_plan_result", {"ok": True, "task": task, "reasoning": f"[重规划] {replan_result['text']}", "steps": steps})
                else:
                    state.push_log("warn", f"重规划未产生计划: {replan_result['text'][:60]}")
                    break
            else:
                if replan_count >= MAX_REPLANS:
                    state.push_log("error", f"已达最大重规划次数 ({MAX_REPLANS})")
                break

        socketio.emit("ai_thinking", {"phase": "idle", "detail": ""})

        total_completed = sum(1 for _, r in all_step_results if r.success)
        status = "✅ 成功" if final_success else "❌ 失败"
        replan_note = f" (重规划{replan_count}次)" if replan_count > 0 else ""
        state.push_log("success" if final_success else "error", f"{status} | 完成 {total_completed}/{len(all_step_results)} 步{replan_note}")

        socketio.emit("ai_execution_report", {
            "ok": final_success, "task": task,
            "completed_steps": total_completed, "total_steps": len(all_step_results),
            "replans": replan_count,
            "cost_time": sum(r.cost_time for _, r in all_step_results),
            "step_results": [{"skill": sd.get("skill", "?"), "robot": sd.get("robot", state.current_robot), "success": r.success, "cost_time": r.cost_time, "error": r.error_msg if hasattr(r, "error_msg") else None} for sd, r in all_step_results],
        })

        # 把执行结果也推送到对话
        result_msg = f"{'任务完成' if final_success else '任务未完成'}: {total_completed}/{len(all_step_results)} 步成功{replan_note}"
        socketio.emit("ai_chat_reply", {"ok": True, "intent": "RESULT", "reply": result_msg, "message": task}, to=sid)
        socketio.emit("world_state", state.get_world_snapshot())
        socketio.emit("skill_catalog", _get_skill_catalog())

    except Exception as e:
        logger.exception("对话任务执行异常")
        state.push_log("error", f"执行异常: {e}")
    finally:
        state.is_executing = False
        socketio.emit("system_status", _get_system_status())


@socketio.on("stop_execution")
def on_stop_execution():
    """中止当前执行：重置 is_executing，让无人机悬停等待下一指令。"""
    state._ai_stop_event.set()

    # 强制重置执行状态
    was_executing = state.is_executing
    state.is_executing = False
    socketio.emit("system_status", _get_system_status())

    if was_executing:
        state.push_log("warn", "⏹ 执行已打断，尝试悬停...")
        # 后台让无人机悬停
        def _hold():
            try:
                from adapters.adapter_manager import get_adapter
                adapter = get_adapter()
                if adapter and adapter.is_connected() and adapter.is_in_air():
                    result = adapter.hover(2.0)
                    state.push_log("info", f"🔄 悬停中: {result.message}")
                else:
                    state.push_log("info", "无人机不在空中，无需悬停")
            except Exception as e:
                state.push_log("warn", f"悬停失败: {e}")
        threading.Thread(target=_hold, daemon=True).start()
    else:
        state.push_log("info", "⏹ 当前无执行中的任务")

    emit("system_status", _get_system_status())


@socketio.on("velocity_control")
def on_velocity_control(data):
    """
    驾驶舱实时速度控制 (Body 坐标系)。
    data: {"forward": 0, "right": 0, "down": 0, "yaw_rate": 0}
    所有值为 m/s 或 deg/s，0 = 停止。
    """
    if not state.initialized:
        emit("velocity_result", {"ok": False, "error": "系统未初始化"})
        return

    from adapters.adapter_manager import get_adapter
    adapter = get_adapter()
    if not adapter or not adapter.is_connected():
        emit("velocity_result", {"ok": False, "error": "适配器未连接"})
        return

    fwd   = float(data.get("forward", 0))
    right = float(data.get("right", 0))
    down  = float(data.get("down", 0))
    yaw   = float(data.get("yaw_rate", 0))

    # 全 0 = 停止
    if fwd == 0 and right == 0 and down == 0 and yaw == 0:
        result = adapter.stop_velocity()
    else:
        result = adapter.set_velocity_body(fwd, right, down, yaw)
    emit("velocity_result", {"ok": result.success, "msg": result.message})


@socketio.on("get_telemetry")
def on_get_telemetry():
    """返回实时遥测数据（位置/速度/电池/姿态）。"""
    if not state.initialized:
        emit("telemetry", {})
        return
    from adapters.adapter_manager import get_adapter
    adapter = get_adapter()
    if not adapter or not adapter.is_connected():
        emit("telemetry", {})
        return
    try:
        pos = adapter.get_position()
        bat = adapter.get_battery()
        in_air = adapter.is_in_air()
        armed = adapter.is_armed()
        emit("telemetry", {
            "position": {"north": round(pos.north, 2), "east": round(pos.east, 2), "down": round(pos.down, 2)},
            "altitude": round(-pos.down, 2),
            "battery": round(min(bat[1], 100) if bat[1] > 1 else bat[1] * 100, 1) if bat else None,
            "in_air": in_air,
            "armed": armed,
        })
    except Exception as e:
        logger.warning("遥测获取失败: %s", e)
        emit("telemetry", {})


@socketio.on("get_world_state")
def on_get_world_state():
    emit("world_state", state.get_world_snapshot())


@socketio.on("get_skill_catalog")
def on_get_skill_catalog():
    emit("skill_catalog", _get_skill_catalog())


@socketio.on("update_robot_position")
def on_update_robot_position(data):
    """
    更新机器人位置（供仿真器推送位置更新）。
    data: {"robot_id": "UAV_1", "position": [x, y, z], "battery": 90.0}
    """
    if not state.world_model:
        return
    robot_id = data.get("robot_id")
    if not robot_id:
        return
    update = {"robots": {robot_id: {}}}
    if "position" in data:
        update["robots"][robot_id]["position"] = data["position"]
    if "battery" in data:
        update["robots"][robot_id]["battery"] = data["battery"]
    if "status" in data:
        update["robots"][robot_id]["status"] = data["status"]
    state.world_model.update_world_state(update)
    socketio.emit("world_state", state.get_world_snapshot())


@socketio.on("register_robot")
def on_register_robot(data):
    """
    动态注册新机器人（无需重启服务）。
    data: {
        "robot_id": "UAV_2",
        "robot_type": "UAV",          # "UAV" | "UGV" | ...
        "initial_position": [0, 0, 0],
        "battery": 100.0
    }
    新机器人注册后广播 robot_joined 事件，前端自动渲染新卡片。
    """
    if not state.initialized or not state.world_model:
        emit("register_robot_result", {"ok": False, "error": "系统未初始化"})
        return

    robot_id   = data.get("robot_id", "").strip()
    robot_type = data.get("robot_type", "UAV").upper()
    position   = data.get("initial_position", [0, 0, 0])
    battery    = float(data.get("battery", 100.0))

    if not robot_id:
        emit("register_robot_result", {"ok": False, "error": "robot_id 不能为空"})
        return

    # 已存在则只更新状态，不重复广播 robot_joined
    world = state.world_model.get_world_state()
    already_exists = robot_id in world.get("robots", {})

    state.world_model.register_robot(robot_id, robot_type,
                                     initial_position=position,
                                     battery=battery)

    # 为新机器人构建独立技能注册表（已存在则重建，保持最新）
    reg, count = _build_robot_registry(robot_id, robot_type)
    state.robot_registries[robot_id] = reg
    # 注入到 runtime 的 executor
    if state.runtime:
        state.runtime._robot_registries[robot_id] = reg
        state.runtime._executor._robot_registries[robot_id] = reg

    state.push_log("info", f"{'更新' if already_exists else '新增'}机器人: {robot_id} ({robot_type})")
    emit("register_robot_result", {"ok": True, "robot_id": robot_id, "already_existed": already_exists})

    # 只有真正新加入的机器人才广播 robot_joined
    if not already_exists:
        robot_info = {
            "robot_id":   robot_id,
            "robot_type": robot_type,
            "position":   position,
            "battery":    battery,
        }
        socketio.emit("robot_joined", robot_info)
        state.push_log("success", f"✅ 机器人 {robot_id} ({robot_type}) 已加入编队")

    # 广播最新世界状态
    socketio.emit("world_state", state.get_world_snapshot())


# ══════════════════════════════════════════════════════════════════════════════
#  世界状态定时推送（每 2 秒广播一次）
# ══════════════════════════════════════════════════════════════════════════════

def _world_state_broadcaster():
    while True:
        time.sleep(2)
        if state.initialized:
            socketio.emit("world_state", state.get_world_snapshot())


# ── Doctor API ────────────────────────────────────────────────────────────────

@app.route("/api/doctor/run", methods=["GET"])
def api_doctor_run():
    """执行系统健康检查，返回报告"""
    try:
        from core.doctor import create_doctor
        doctor = create_doctor()
        report = doctor.run()
        return jsonify(report.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@socketio.on("run_doctor")
def on_run_doctor():
    """WebSocket 触发健康检查"""
    try:
        from core.doctor import create_doctor
        doctor = create_doctor()
        report = doctor.run()
        emit("doctor_report", report.to_dict())
    except Exception as e:
        emit("doctor_report", {"error": str(e)})


# ── Safety API ────────────────────────────────────────────────────────────────

@app.route("/api/safety/status", methods=["GET"])
def api_safety_status():
    """安全体系状态"""
    try:
        from core.safety.config import get_safety_config
        from core.safety.flight_envelope import FlightEnvelope
        cfg = get_safety_config()
        fe = FlightEnvelope()
        return jsonify({
            "ok": True,
            "level": cfg.level,
            "gates": {
                "command_filter": {"name": "Command Filter", "passed": 0, "blocked": 0},
                "sandbox": {"name": "Sandbox", "passed": 0, "blocked": 0},
                "approval": {"name": "Approval", "passed": 0, "blocked": 0},
                "flight_envelope": {"name": "Flight Envelope", "passed": 0, "blocked": 0},
            },
            "envelope": {
                "max_speed": fe.MAX_SPEED,
                "max_altitude": fe.MAX_ALTITUDE,
                "min_battery": fe.MIN_BATTERY,
                "critical_battery": fe.CRITICAL_BATTERY,
                "heartbeat_timeout": fe.HEARTBEAT_TIMEOUT,
                "max_distance": fe.MAX_DISTANCE,
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/safety/audit", methods=["GET"])
def api_safety_audit():
    """审计日志"""
    limit = int(request.args.get("limit", 10))
    try:
        from core.safety.audit_log import AuditLog
        al = AuditLog()
        logs = al.get_log(limit=limit)
        return jsonify({"ok": True, "logs": [e.to_dict() for e in logs], "count": len(logs)})
    except Exception as e:
        return jsonify({"ok": True, "logs": [], "count": 0})


# ── Memory API ────────────────────────────────────────────────────────────────

_memory_manager_singleton = None

def _get_memory_manager():
    """记忆管理器单例，避免重复初始化"""
    global _memory_manager_singleton
    if _memory_manager_singleton is None:
        from memory.memory_manager import MemoryManager
        _memory_manager_singleton = MemoryManager()
    return _memory_manager_singleton


@app.route("/api/memory/stats", methods=["GET"])
def api_memory_stats():
    """记忆系统统计"""
    try:
        mm = _get_memory_manager()
        return jsonify({
            "ok": True,
            "layers": {
                "working": {"count": len(mm.working.get_recent(100)), "label": "Working"},
                "episodic": {"count": mm.episodic.count(), "label": "Episodic"},
                "skill": {"count": mm.skill.count(), "label": "Skill"},
                "world": {"count": mm.world.count(), "label": "World"},
            },
        })
    except Exception as e:
        return jsonify({"ok": True, "layers": {
            "working": {"count": 0, "label": "Working"},
            "episodic": {"count": 0, "label": "Episodic"},
            "skill": {"count": 0, "label": "Skill"},
            "world": {"count": 0, "label": "World"},
        }})


@app.route("/api/memory/recent", methods=["GET"])
def api_memory_recent():
    """最近记忆"""
    try:
        mm = _get_memory_manager()
        items = mm.working.get_recent(20)
        return jsonify({"ok": True, "items": [
            {"text": str(item), "score": 0, "layer": "working", "metadata": {}}
            for item in items
        ]})
    except Exception as e:
        return jsonify({"ok": True, "items": []})


@app.route("/api/memory/search", methods=["POST"])
def api_memory_search():
    """记忆语义搜索"""
    data = request.get_json() or {}
    query = data.get("query", "")
    top_k = data.get("top_k", 10)
    if not query:
        return jsonify({"ok": False, "error": "query 不能为空"}), 400
    try:
        mm = _get_memory_manager()
        items = mm.recall(query, top_k=top_k)
        return jsonify({"ok": True, "query": query, "items": [
            {"text": i.text, "score": i.score, "layer": i.metadata.get("layer", "unknown"),
             "metadata": i.metadata} for i in items
        ]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── 通用设备协议 API (Phase 4) ────────────────────────────────────────────────

# 全局设备管理器（延迟初始化）
_device_manager = None


def _get_device_manager():
    """获取或创建设备管理器单例"""
    global _device_manager
    if _device_manager is None:
        from core.device_manager import DeviceManager
        _device_manager = DeviceManager()

        # 设备离线回调
        def on_offline(device_id):
            state.push_log("warning", f"⚠️ 设备离线: {device_id}")
            socketio.emit("device_offline", {"device_id": device_id})

        def on_online(device_id):
            state.push_log("info", f"✅ 设备上线: {device_id}")
            socketio.emit("device_online", {"device_id": device_id})

        _device_manager.on_device_offline(on_offline)
        _device_manager.on_device_online(on_online)
        _device_manager.start()
    return _device_manager


@app.route("/api/device/register", methods=["POST"])
def api_device_register():
    """设备注册"""
    from core.device_manager import DeviceInfo
    dm = _get_device_manager()
    data = request.get_json() or {}

    required = ["device_id", "device_type", "capabilities", "sensors", "protocol"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"ok": False, "error": f"缺少必填字段: {missing}", "code": "MISSING_FIELDS"}), 400

    try:
        info = DeviceInfo(
            device_id=data["device_id"],
            device_type=data["device_type"],
            capabilities=data["capabilities"],
            sensors=data["sensors"],
            protocol=data["protocol"],
            metadata=data.get("metadata", {}),
        )
        token = dm.register(info)
        state.push_log("success", f"✅ 设备注册: {info.device_id} ({info.device_type})")
        socketio.emit("device_registered", {"device_id": info.device_id, "device_type": info.device_type})
        return jsonify({"ok": True, "device_id": info.device_id, "token": token, "message": "设备注册成功"}), 201
    except ValueError as e:
        # 设备已注册 — 返回已有 token（方便重连）
        existing = dm.get_device(data.get("device_id", ""))
        if existing:
            return jsonify({"ok": True, "device_id": existing.info.device_id,
                            "token": existing.token, "message": "设备已注册，返回已有 token"}), 200
        return jsonify({"ok": False, "error": str(e), "code": "DEVICE_ALREADY_EXISTS"}), 409


@app.route("/api/device/<device_id>", methods=["DELETE"])
def api_device_unregister(device_id):
    """设备注销"""
    dm = _get_device_manager()
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not dm.validate_token(device_id, token):
        return jsonify({"ok": False, "error": "Token 无效", "code": "INVALID_TOKEN"}), 401
    try:
        dm.unregister(device_id)
        state.push_log("info", f"设备注销: {device_id}")
        socketio.emit("device_unregistered", {"device_id": device_id})
        return jsonify({"ok": True, "device_id": device_id, "message": "设备已注销"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "code": "DEVICE_NOT_FOUND"}), 404


@app.route("/api/device/<device_id>/state", methods=["POST"])
def api_device_state(device_id):
    """设备状态上报"""
    dm = _get_device_manager()
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not dm.validate_token(device_id, token):
        return jsonify({"ok": False, "error": "Token 无效", "code": "INVALID_TOKEN"}), 401
    try:
        data = request.get_json() or {}
        dm.update_state(device_id, data)
        return jsonify({"ok": True, "device_id": device_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 404


@app.route("/api/device/<device_id>/sensor", methods=["POST"])
def api_device_sensor(device_id):
    """传感器数据上报"""
    dm = _get_device_manager()
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not dm.validate_token(device_id, token):
        return jsonify({"ok": False, "error": "Token 无效", "code": "INVALID_TOKEN"}), 401
    try:
        data = request.get_json() or {}
        dm.update_sensor(device_id, data)
        return jsonify({"ok": True, "device_id": device_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 404


@app.route("/api/devices", methods=["GET"])
def api_device_list():
    """设备列表"""
    dm = _get_device_manager()
    devices = dm.list_devices()
    return jsonify({
        "ok": True,
        "devices": [dm.to_dict(d) for d in devices],
        "count": len(devices),
    })


@app.route("/api/device/<device_id>/action", methods=["POST"])
def api_device_send_action(device_id):
    """向设备下发指令"""
    dm = _get_device_manager()
    device = dm.get_device(device_id)
    if not device:
        return jsonify({"ok": False, "error": f"设备 {device_id} 不存在"}), 404
    if device.status != "online":
        return jsonify({"ok": False, "error": f"设备 {device_id} 离线"}), 503
    data = request.get_json() or {}
    action_name = data.get("action", "")
    params = data.get("params", {})
    if not action_name:
        return jsonify({"ok": False, "error": "action 不能为空"}), 400
    try:
        from core.device_manager import Action
        result = dm.send_action(device_id, Action(action=action_name, params=params, timeout=15))
        return jsonify({"ok": result.success, "message": result.message, "output": result.output,
                        "cost_time": result.cost_time})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 504


@app.route("/api/device/<device_id>/state", methods=["GET"])
def api_device_get_state(device_id):
    """获取设备状态（GET 版本）"""
    dm = _get_device_manager()
    try:
        state = dm.get_device_state(device_id)
        return jsonify({"ok": True, **state})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 404


# ── 通用设备 WebSocket 事件 ──────────────────────────────────────────────────

@socketio.on("device_connect")
def on_device_connect(data):
    """设备 WebSocket 认证"""
    dm = _get_device_manager()
    device_id = data.get("device_id", "")
    token = data.get("token", "")
    if not dm.validate_token(device_id, token):
        emit("device_connected", {"ok": False, "error": "Token 无效"})
        return
    device_sid = request.sid  # 捕获当前 sid，闭包保存
    dm.set_ws_sid(device_id, device_sid)
    # 注册指令下发回调 — 用闭包捕获的 sid
    def send_action_to_device(payload):
        socketio.emit("device_action", payload, to=device_sid)
    dm.set_action_callback(device_id, send_action_to_device)
    emit("device_connected", {"ok": True, "device_id": device_id, "message": "WebSocket 已认证"})
    state.push_log("info", f"设备 WebSocket 认证: {device_id}")


@socketio.on("device_state")
def on_device_state_ws(data):
    """WebSocket 设备状态上报 — 同时转发给控制台"""
    dm = _get_device_manager()
    device_id = data.get("device_id", "")
    try:
        dm.update_state(device_id, data)
        # 转发给控制台前端（不发回给设备自己）
        socketio.emit("device_state_update", {"device_id": device_id, "state": data},
                      skip_sid=request.sid)
    except Exception as e:
        logger.warning("设备状态更新失败 [%s]: %s", device_id, e)


@socketio.on("device_sensor")
def on_device_sensor_ws(data):
    """WebSocket 传感器数据上报 — 同时转发给控制台"""
    dm = _get_device_manager()
    device_id = data.get("device_id", "")
    try:
        dm.update_sensor(device_id, data)
        socketio.emit("device_sensor_update", {"device_id": device_id, "data": data},
                      skip_sid=request.sid)
    except Exception as e:
        logger.warning("传感器数据更新失败 [%s]: %s", device_id, e)


@socketio.on("heartbeat")
def on_device_heartbeat(data):
    """设备心跳"""
    dm = _get_device_manager()
    device_id = data.get("device_id", "")
    try:
        dm.heartbeat(device_id)
        emit("heartbeat_ack", {"device_id": device_id, "timestamp": time.time()})
    except Exception as e:
        logger.warning("心跳处理失败 [%s]: %s", device_id, e)


@socketio.on("action_result")
def on_action_result(data):
    """设备指令执行结果回报"""
    from core.device_manager import ActionResult
    dm = _get_device_manager()
    action_id = data.get("action_id", "")
    result = ActionResult(
        action_id=action_id,
        success=data.get("success", False),
        message=data.get("message", ""),
        output=data.get("output", {}),
        cost_time=data.get("cost_time", 0),
    )
    dm.report_action_result(action_id, result)


# ── Bootstrap API (Phase 4) ─────────────────────────────────────────────────

@app.route("/api/bootstrap/status", methods=["GET"])
def api_bootstrap_status():
    """获取引导状态"""
    from core.bootstrap import get_bootstrap_manager
    bm = get_bootstrap_manager()
    return jsonify({
        "ok": True,
        "needs_bootstrap": bm.needs_bootstrap(),
        "state": bm.get_state(),
    })


@app.route("/api/bootstrap/llm", methods=["POST"])
def api_bootstrap_llm():
    """保存 LLM 配置"""
    from core.bootstrap import get_bootstrap_manager
    bm = get_bootstrap_manager()
    data = request.get_json() or {}
    provider = data.get("provider", "custom")
    base_url = data.get("base_url", "")
    api_key = data.get("api_key", "")
    model = data.get("model", "")
    if not base_url or not api_key or not model:
        return jsonify({"ok": False, "error": "base_url, api_key, model 不能为空"}), 400
    # 先测试连接
    test = bm.test_llm_connection(base_url, api_key, model)
    if not test["ok"]:
        return jsonify({"ok": False, "error": test["message"]}), 502
    # 保存配置
    ok = bm.save_llm_config(provider, base_url, api_key, model)
    return jsonify({"ok": ok, "test_result": test})


@app.route("/api/bootstrap/safety", methods=["POST"])
def api_bootstrap_safety():
    """设置安全等级"""
    from core.bootstrap import get_bootstrap_manager
    bm = get_bootstrap_manager()
    data = request.get_json() or {}
    level = data.get("level", "standard")
    if level not in ("strict", "standard", "permissive"):
        return jsonify({"ok": False, "error": "level 必须是 strict/standard/permissive"}), 400
    ok = bm.save_safety_level(level)
    return jsonify({"ok": ok, "level": level})


@app.route("/api/bootstrap/complete", methods=["POST"])
def api_bootstrap_complete():
    """完成引导"""
    from core.bootstrap import get_bootstrap_manager
    bm = get_bootstrap_manager()
    bm.complete()
    return jsonify({"ok": True, "message": "引导完成"})


# ── 启动 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # v2.0: 统一日志 + 启动自检
    from core.logger import setup_logging
    from core.preflight import run_preflight

    setup_logging(log_dir="logs", level="INFO")
    preflight_report = run_preflight()

    # 启动世界状态定时推送
    t = threading.Thread(target=_world_state_broadcaster, daemon=True)
    t.start()

    # 自动初始化
    init_thread = threading.Thread(target=_do_init, daemon=True)
    init_thread.start()

    logger.info("AerialClaw 控制台服务启动于 http://localhost:5001")
    socketio.run(app, host="0.0.0.0", port=5001, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
