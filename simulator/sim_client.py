#!/usr/bin/env python3
"""
sim_client.py — AerialClaw 仿真设备端客户端

独立运行在仿真环境中，通过通用设备协议连接控制端（server.py）。

功能：
  - 连接 PX4 SITL via MAVSDK
  - 连接 Gazebo 传感器桥接（相机 + 激光雷达）
  - 注册到控制端（HTTP POST /api/device/register）
  - 通过 WebSocket 与控制端保持长连接
  - 持续上报遥测状态（位置/电量/armed/in_air）→ device_state
  - 持续上报传感器数据（相机帧 base64 / LiDAR）→ device_sensor
  - 接收并执行控制指令（device_action）→ 回报 action_result

用法：
  # 先启动控制端
  python server.py

  # 另一个终端启动仿真端
  cd simulator
  python sim_client.py --server http://localhost:5001 --world urban_rescue
"""

import sys
import os
import time
import base64
import threading
import logging
import argparse

# 将上级目录（项目根）加入 sys.path，以便 import adapters/ 和 sim/
_SIM_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SIM_DIR)
sys.path.insert(0, _ROOT_DIR)

import requests
import socketio as sio_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("sim_client")


class SimulatorClient:
    """仿真设备端客户端。

    通过通用设备协议将 PX4 SITL + Gazebo 仿真环境
    注册到控制端，使控制端无需感知对端是仿真还是真机。
    """

    def __init__(
        self,
        server_url: str = "http://localhost:5001",
        device_id: str = "SIM_UAV_1",
        world: str = "urban_rescue",
        model: str = "x500_lidar_2d_cam_0",
        telemetry_hz: float = 2.0,
        sensor_hz: float = 5.0,
        heartbeat_interval: float = 5.0,
    ):
        self.server_url = server_url.rstrip("/")
        self.device_id = device_id
        self.world = world
        self.model = model
        self.telemetry_interval = 1.0 / telemetry_hz
        self.sensor_interval = 1.0 / sensor_hz
        self.heartbeat_interval = heartbeat_interval
        self.token: str = ""
        self._running = False

        # Socket.IO 客户端（自动重连）
        self.sio = sio_module.Client(
            reconnection=True,
            reconnection_attempts=0,  # 无限重连
            reconnection_delay=3,
        )

        # PX4 适配器 + 传感器桥接（延迟初始化）
        self._adapter = None
        self._bridge = None

        self._register_sio_handlers()

    # ──────────────────────────────────────────────────────────────────────────
    #  启动流程
    # ──────────────────────────────────────────────────────────────────────────

    def start(self):
        """完整启动：PX4 → 传感器 → 注册 → WebSocket → 遥测/传感器流。"""
        logger.info("=== AerialClaw 仿真设备端启动 ===")
        logger.info("  device_id : %s", self.device_id)
        logger.info("  server    : %s", self.server_url)
        logger.info("  world     : %s", self.world)
        self._running = True

        self._connect_px4()
        self._start_sensors()
        self._register()
        self._connect_ws()

        # 后台线程：遥测 + 传感器上报
        threading.Thread(target=self._telemetry_loop, daemon=True, name="telemetry").start()
        threading.Thread(target=self._sensor_loop, daemon=True, name="sensor").start()

        logger.info("仿真客户端就绪，按 Ctrl+C 退出")
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到 Ctrl+C，退出...")
        finally:
            self._running = False
            if self.sio.connected:
                self.sio.disconnect()

    # ──────────────────────────────────────────────────────────────────────────
    #  PX4 连接
    # ──────────────────────────────────────────────────────────────────────────

    def _connect_px4(self):
        """初始化 PX4Adapter 并连接 MAVSDK。"""
        try:
            from adapters.px4_adapter import PX4Adapter
            logger.info("正在连接 PX4 SITL (MAVSDK)...")
            self._adapter = PX4Adapter()
            ok = self._adapter.connect(timeout=20)
            if ok:
                logger.info("✅ PX4 适配器连接成功")
            else:
                logger.warning("⚠️  PX4 适配器连接超时，以 mock 模式运行")
                self._adapter = None
        except Exception as e:
            logger.warning("PX4 适配器不可用: %s，以 mock 模式运行", e)
            self._adapter = None

    # ──────────────────────────────────────────────────────────────────────────
    #  Gazebo 传感器桥接
    # ──────────────────────────────────────────────────────────────────────────

    def _start_sensors(self):
        """初始化 GzSensorBridge 并订阅传感器 topic。"""
        try:
            from sim.gz_sensor_bridge import GzSensorBridge
            logger.info("正在连接 Gazebo 传感器 (world=%s, model=%s)...", self.world, self.model)
            bridge = GzSensorBridge(model_name=self.model, world_name=self.world)
            if bridge.start():
                self._bridge = bridge
                logger.info("✅ 传感器桥接启动成功")
            else:
                logger.warning("⚠️  传感器桥接启动失败（Gazebo 可能未运行）")
        except Exception as e:
            logger.warning("传感器桥接不可用: %s", e)
            self._bridge = None

    # ──────────────────────────────────────────────────────────────────────────
    #  设备注册
    # ──────────────────────────────────────────────────────────────────────────

    def _register(self):
        """HTTP POST /api/device/register 向控制端注册本设备。"""
        payload = {
            "device_id": self.device_id,
            "device_type": "UAV",
            "capabilities": [
                "fly", "camera", "lidar",
                "takeoff", "land", "fly_to", "hover",
                "arm", "disarm", "velocity_control",
            ],
            "metadata": {
                "simulator": True,
                "world": self.world,
                "model": self.model,
                "px4_connected": self._adapter is not None,
                "sensor_bridge": self._bridge is not None,
            },
        }
        url = f"{self.server_url}/api/device/register"
        for attempt in range(10):
            try:
                resp = requests.post(url, json=payload, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    self.token = data.get("token", "")
                    logger.info("✅ 设备注册成功，token=%s...", self.token[:8])
                    return
                else:
                    logger.warning("注册失败 HTTP %d: %s", resp.status_code, resp.text[:200])
            except requests.ConnectionError:
                logger.warning(
                    "无法连接控制端 %s，3秒后重试 (%d/10)...", url, attempt + 1
                )
            time.sleep(3)
        logger.error("设备注册失败，已达最大重试次数，以无 token 模式继续运行")

    # ──────────────────────────────────────────────────────────────────────────
    #  WebSocket 连接
    # ──────────────────────────────────────────────────────────────────────────

    def _connect_ws(self):
        """建立 Socket.IO 连接。"""
        try:
            self.sio.connect(self.server_url, wait_timeout=10)
            logger.info("✅ WebSocket 连接成功")
        except Exception as e:
            logger.error("WebSocket 连接失败: %s", e)

    def _register_sio_handlers(self):
        """注册 Socket.IO 事件处理器。"""

        @self.sio.event
        def connect():
            logger.info("WebSocket 已连接，发送 device_connect 认证...")
            self.sio.emit("device_connect", {
                "device_id": self.device_id,
                "token": self.token,
            })
            # 重连后重新启动心跳（之前的守护线程会因 _running 检查自动退出）
            threading.Thread(
                target=self._heartbeat_loop, daemon=True, name="heartbeat"
            ).start()

        @self.sio.event
        def disconnect():
            logger.warning("WebSocket 断开连接")

        @self.sio.on("device_action")
        def on_device_action(data):
            logger.info("收到指令: %s", data)
            threading.Thread(
                target=self._handle_action,
                args=(data,),
                daemon=True,
                name="action",
            ).start()

    # ──────────────────────────────────────────────────────────────────────────
    #  心跳
    # ──────────────────────────────────────────────────────────────────────────

    def _heartbeat_loop(self):
        while self._running and self.sio.connected:
            self.sio.emit("device_heartbeat", {"device_id": self.device_id})
            time.sleep(self.heartbeat_interval)

    # ──────────────────────────────────────────────────────────────────────────
    #  遥测上报
    # ──────────────────────────────────────────────────────────────────────────

    def _telemetry_loop(self):
        """持续上报飞行状态 → device_state 事件。"""
        while self._running:
            try:
                state_data = self._get_telemetry()
                if self.sio.connected:
                    self.sio.emit("device_state", {
                        "device_id": self.device_id,
                        **state_data,
                    })
            except Exception as e:
                logger.debug("遥测上报异常: %s", e)
            time.sleep(self.telemetry_interval)

    def _get_telemetry(self) -> dict:
        """从 PX4 适配器读取遥测，无适配器时返回 mock 数据。"""
        if self._adapter and self._adapter.is_connected():
            try:
                st = self._adapter.get_state()
                pos = st.position_ned
                battery = st.battery_percent
                # 电量归一化到 0-100
                if battery > 100:
                    battery = battery / 100.0
                elif battery <= 1.0:
                    battery = battery * 100.0
                battery = round(max(0.0, min(100.0, battery)), 1)
                return {
                    "position": {
                        "north": round(pos.north, 2) if pos else 0.0,
                        "east":  round(pos.east,  2) if pos else 0.0,
                        "down":  round(pos.down,  2) if pos else 0.0,
                    },
                    "altitude": round(-pos.down, 2) if pos else 0.0,
                    "battery": battery,
                    "armed":  st.is_armed,
                    "in_air": st.in_air,
                    "status": "airborne" if st.in_air else "idle",
                }
            except Exception as e:
                logger.debug("读取遥测失败: %s", e)
        # mock 数据
        return {
            "position": {"north": 0.0, "east": 0.0, "down": 0.0},
            "altitude": 0.0,
            "battery": 92.0,
            "armed": False,
            "in_air": False,
            "status": "idle",
        }

    # ──────────────────────────────────────────────────────────────────────────
    #  传感器上报
    # ──────────────────────────────────────────────────────────────────────────

    def _sensor_loop(self):
        """持续上报相机帧 base64 + LiDAR 数据 → device_sensor 事件。"""
        while self._running:
            try:
                if self._bridge and self._bridge.is_running and self.sio.connected:
                    payload = self._collect_sensor_data()
                    if payload:
                        self.sio.emit("device_sensor", {
                            "device_id": self.device_id,
                            **payload,
                        })
            except Exception as e:
                logger.debug("传感器上报异常: %s", e)
            time.sleep(self.sensor_interval)

    def _collect_sensor_data(self) -> dict:
        """收集相机帧（base64 JPEG）和激光雷达数据。"""
        import math
        payload = {}

        # ── 相机 ──
        try:
            import cv2
            cameras = {}
            for direction in ["front", "rear", "left", "right", "down"]:
                img = self._bridge.get_camera_image(direction)
                if img is not None:
                    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 50])
                    info = self._bridge.get_camera_info(direction)
                    cameras[direction] = {
                        "image": base64.b64encode(buf.tobytes()).decode("ascii"),
                        "width":  info["width"],
                        "height": info["height"],
                        "fps":    round(info["fps"], 1),
                    }
            if cameras:
                payload["cameras"] = cameras
        except Exception as e:
            logger.debug("相机采集失败: %s", e)

        # ── 激光雷达 ──
        try:
            scan = self._bridge.get_lidar_scan()
            if scan is not None:
                rmax = scan["range_max"]
                rmin = scan["range_min"]
                ranges = scan["ranges"]
                step = max(1, len(ranges) // 360)
                clean = [
                    round(r, 2) if (math.isfinite(r) and r >= rmin) else rmax
                    for r in ranges[::step]
                ]
                payload["lidar"] = {
                    "ranges":           clean,
                    "angle_min":        scan["angle_min"],
                    "angle_max":        scan["angle_max"],
                    "angle_increment":  scan["angle_increment"] * step,
                    "range_min":        rmin,
                    "range_max":        rmax,
                    "count":            len(clean),
                }
        except Exception as e:
            logger.debug("激光雷达采集失败: %s", e)

        return payload

    # ──────────────────────────────────────────────────────────────────────────
    #  指令处理
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_action(self, data: dict):
        """收到 device_action → 调用 PX4 适配器执行 → 回报 action_result。"""
        action    = data.get("action", "")
        params    = data.get("params", {})
        action_id = data.get("action_id", "")

        logger.info("执行指令: %s params=%s", action, params)
        result = {"ok": False, "message": "适配器未连接", "action_id": action_id}

        if not self._adapter or not self._adapter.is_connected():
            result["message"] = "PX4 适配器未连接"
        else:
            try:
                ar = self._dispatch_action(action, params)
                result = {
                    "ok":        ar.success,
                    "message":   ar.message,
                    "action_id": action_id,
                    "action":    action,
                }
            except Exception as e:
                result = {
                    "ok":        False,
                    "message":   str(e),
                    "action_id": action_id,
                    "action":    action,
                }

        logger.info("指令结果: %s", result)
        if self.sio.connected:
            self.sio.emit("action_result", {
                "device_id": self.device_id,
                **result,
            })

    def _dispatch_action(self, action: str, params: dict):
        """将 action 字符串分派到 PX4 适配器对应方法。"""
        a = self._adapter
        dispatch = {
            "takeoff":          lambda: a.takeoff(params.get("altitude", 5.0)),
            "land":             lambda: a.land(),
            "hover":            lambda: a.hover(),
            "arm":              lambda: a.arm(),
            "disarm":           lambda: a.disarm(),
            "fly_to":           lambda: a.fly_to(
                params["north"], params["east"],
                params.get("altitude", 5.0),
                params.get("yaw", 0.0),
            ),
            "go_north":         lambda: a.fly_to(
                params.get("distance", 5.0), 0, params.get("altitude", 5.0)
            ),
            "go_south":         lambda: a.fly_to(
                -params.get("distance", 5.0), 0, params.get("altitude", 5.0)
            ),
            "go_east":          lambda: a.fly_to(
                0, params.get("distance", 5.0), params.get("altitude", 5.0)
            ),
            "go_west":          lambda: a.fly_to(
                0, -params.get("distance", 5.0), params.get("altitude", 5.0)
            ),
            "velocity_control": lambda: a.set_velocity_body(
                params.get("forward", 0), params.get("right", 0),
                params.get("down", 0), params.get("yaw_rate", 0),
            ),
        }
        fn = dispatch.get(action)
        if fn is None:
            from adapters.sim_adapter import ActionResult
            return ActionResult(success=False, message=f"未知指令: {action}")
        return fn()


# ══════════════════════════════════════════════════════════════════════════════
#  入口
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="AerialClaw 仿真设备端客户端",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--server", default="http://localhost:5001",
        help="控制端地址"
    )
    parser.add_argument(
        "--device-id", default="SIM_UAV_1",
        help="设备唯一 ID"
    )
    parser.add_argument(
        "--world", default="urban_rescue",
        help="Gazebo world 名称"
    )
    parser.add_argument(
        "--model", default="x500_lidar_2d_cam_0",
        help="Gazebo 模型名称（不含编号后缀则自动加 _0）"
    )
    parser.add_argument(
        "--telemetry-hz", type=float, default=2.0,
        help="遥测上报频率 (Hz)"
    )
    parser.add_argument(
        "--sensor-hz", type=float, default=5.0,
        help="传感器上报频率 (Hz)"
    )
    args = parser.parse_args()

    client = SimulatorClient(
        server_url=args.server,
        device_id=args.device_id,
        world=args.world,
        model=args.model,
        telemetry_hz=args.telemetry_hz,
        sensor_hz=args.sensor_hz,
    )
    client.start()


if __name__ == "__main__":
    main()
