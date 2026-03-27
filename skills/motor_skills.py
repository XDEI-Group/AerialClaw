"""
motor_skills.py — 运动技能（物理层）

通过 SimAdapter 接口控制飞行器。

设计:
    运动技能不直接调用 MAVSDK/AirSim 等 API，而是通过 adapters.adapter_manager
    获取当前活跃的 SimAdapter 实例，调用统一接口。

    切换仿真环境只需切换 adapter，运动技能代码无需修改。

包含:
    Takeoff / Land / FlyTo / Hover / GetPosition / GetBattery / ReturnToLaunch
"""

import time
import math
import logging

from skills.base_skill import Skill, SkillResult

logger = logging.getLogger(__name__)


def _get_adapter():
    """获取当前活跃的仿真适配器。"""
    from adapters.adapter_manager import get_adapter
    adapter = get_adapter()
    if adapter is None:
        logger.error("[motor] adapter is None — get_adapter() returned None")
    else:
        try:
            logger.debug(f"[motor] adapter={adapter.name} connected={adapter.is_connected() if callable(adapter.is_connected) else adapter.is_connected}")
        except Exception:
            pass
    return adapter


def _check_in_air() -> bool:
    """检查无人机是否在空中。"""
    adapter = _get_adapter()
    if adapter is None:
        return False
    try:
        r = adapter.is_in_air()
        logger.debug(f"[motor] is_in_air={r}")
        return r
    except Exception as e:
        logger.warning(f"[motor] is_in_air error: {e}")
        return False


def _check_armed() -> bool:
    """检查无人机是否已解锁。"""
    adapter = _get_adapter()
    if adapter is None:
        return False
    try:
        r = adapter.is_armed()
        logger.debug(f"[motor] is_armed={r}")
        return r
    except Exception as e:
        logger.warning(f"[motor] is_armed error: {e}")
        return False


def _log_state(adapter, label: str = ""):
    """打印飞行器完整状态快照（世界坐标）。"""
    try:
        pos = adapter.get_position()
        st = adapter.get_state()
        vel = st.velocity if st else None
        alt = None
        if hasattr(adapter, '_get_altitude'):
            try:
                alt = adapter._get_altitude()
            except Exception:
                pass
        if alt is None and pos:
            alt = abs(pos.down)
        logger.info(
            f"[STATE {label}] 位置({pos.north:.1f},{pos.east:.1f},{pos.down:.1f}) "
            f"alt={alt:.1f}m armed={st.armed} in_air={st.in_air} "
            f"mode={st.mode} vel={vel} [{adapter.name}]"
        )
    except Exception as e:
        logger.warning(f"[STATE {label}] read fail: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  Takeoff
# ══════════════════════════════════════════════════════════════════════════════

class Takeoff(Skill):
    name = "takeoff"
    description = "从当前高度往上飞指定米数（相对上升）。altitude=30表示从当前位置再往上飞30米。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 2.0
    input_schema = {"altitude": "float，起飞目标高度（米），默认 5.0"}
    output_schema = {"actual_altitude": "float", "takeoff_time": "float"}

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        logger.info(f"[Takeoff] input={input_data}")
        if _check_in_air():
            logger.warning("[Takeoff] already in air")
            return SkillResult(success=False, error_msg="无人机已在空中，无法起飞", logs=["❌ 前提检查失败: 已在空中"])

        altitude = input_data.get("altitude", 5.0)
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器", logs=["❌ 无适配器连接"])

        _log_state(adapter, "PRE-TAKEOFF")
        logger.info(f"[Takeoff] adapter.takeoff({altitude}) [{adapter.name}]")
        t0 = time.time()
        result = adapter.takeoff(altitude)
        dt = round(time.time() - t0, 2)
        logger.info(f"[Takeoff] ok={result.success} msg='{result.message}' {dt}s")
        _log_state(adapter, "POST-TAKEOFF")

        return SkillResult(
            success=result.success,
            output={"actual_altitude": result.data.get("altitude", altitude), "takeoff_time": dt},
            error_msg=result.message if not result.success else "",
            cost_time=dt,
            logs=[f"takeoff({altitude}m): {result.message} [{adapter.name}] {dt}s"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Land
# ══════════════════════════════════════════════════════════════════════════════

class Land(Skill):
    name = "land"
    description = "安全降落：逐步下降并用下方深度探测地面，接近地面自动停止，不会穿模。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 1.5
    input_schema = {}
    output_schema = {"landed_position": "[lat, lon, alt]", "land_time": "float"}

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        logger.info("[Land] called")
        if not _check_in_air():
            logger.info("[Land] not in air, skip")
            return SkillResult(success=True, output={"landed_position": [], "land_time": 0.0},
                               cost_time=0.0, logs=["✅ 无人机已在地面，无需降落"])

        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")

        _log_state(adapter, "PRE-LAND")
        logger.info(f"[Land] adapter.land() [{adapter.name}]")
        t0 = time.time()
        result = adapter.land()
        dt = round(time.time() - t0, 2)
        logger.info(f"[Land] ok={result.success} msg='{result.message}' {dt}s")
        _log_state(adapter, "POST-LAND")

        gps = adapter.get_gps()
        ned = adapter.get_position()
        pos = [round(gps.lat,7), round(gps.lon,7), round(gps.alt,2)] if gps else None
        ned_l = [round(ned.north,2), round(ned.east,2), round(ned.down,2)] if ned else None

        return SkillResult(
            success=result.success,
            output={"landed_position": pos, "ned": ned_l, "land_time": dt},
            error_msg=result.message if not result.success else "",
            cost_time=dt,
            logs=[f"land: {result.message} [{adapter.name}] {dt}s"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  FlyTo
# ══════════════════════════════════════════════════════════════════════════════

class FlyTo(Skill):
    name = "fly_to"
    description = "底层移动技能：飞到指定AirSim世界坐标。z越负越高，地面z≈-13。⚠️使用前必须先get_position！"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 3.0
    input_schema = {
        "target_position": "[x, y, z] AirSim世界坐标。z越负越高，地面z≈-13。z=-43表示离地30m。先get_position再决定坐标！",
        "speed": "float，飞行速度 m/s，默认 15.0，⚠️ 必须传 speed=15，不要用低速度",
    }
    output_schema = {"arrived_position": "[n, e, d]", "distance_traveled": "float", "altitude": "float", "start_position": "[n, e, d]"}

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        target = input_data.get("target_position", [0, 0, -43])
        speed = max(float(input_data.get("speed", 15.0)), 15.0)  # 最低 15 m/s
        logger.info(f"[FlyTo] target={target} speed={speed}")

        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")
        
        pos = adapter.get_position()

        # 直接使用世界坐标 [x, y, z]
        n, e = float(target[0]), float(target[1])
        d = float(target[2]) if len(target) > 2 else -43.0

        # 获取离地高度用于日志
        if hasattr(adapter, '_get_altitude'):
            current_alt = adapter._get_altitude()
        else:
            current_alt = abs(pos.down)

        horiz = math.sqrt((n - pos.north)**2 + (e - pos.east)**2)
        logger.info(
            f"[FlyTo] from 世界({pos.north:.1f},{pos.east:.1f},{pos.down:.1f}) "
            f"→ 世界({n:.1f},{e:.1f},{d:.1f}) horiz={horiz:.1f}m"
        )
        _log_state(adapter, "PRE-FLYTO")

        t0 = time.time()
        result = adapter.fly_to_ned(n, e, d, speed)
        dt = round(time.time() - t0, 2)

        final_pos = adapter.get_position()
        if hasattr(adapter, '_get_altitude'):
            final_alt = adapter._get_altitude()
        else:
            final_alt = abs(final_pos.down)
        dist = math.sqrt((final_pos.north - pos.north)**2 + (final_pos.east - pos.east)**2)
        err = math.sqrt((final_pos.north - n)**2 + (final_pos.east - e)**2 + (final_pos.down - d)**2)
        logger.info(
            f"[FlyTo] ok={result.success} msg='{result.message}' "
            f"final=世界({final_pos.north:.1f},{final_pos.east:.1f},{final_pos.down:.1f}) "
            f"err={err:.1f}m dist={dist:.1f}m {dt}s"
        )
        _log_state(adapter, "POST-FLYTO")

        # 障碍物阻挡：在 output 中包含详细信息供 LLM 重规划
        if not result.success and ('障碍' in result.message or 'Obstacle' in result.message):
            obstacle_info = getattr(adapter, '_last_obstacle_info', {})
            return SkillResult(
                success=False,
                output={
                    'obstacle_detected': True,
                    'obstacle_direction': obstacle_info.get('direction', '前方'),
                    'obstacle_distance': obstacle_info.get('front_dist', 0),
                    'current_position': [round(final_pos.north, 1), round(final_pos.east, 1), round(final_pos.down, 1)],
                    'original_target': [n, e, d],
                    'suggestion': '建议: 1) change_altitude 升高绕过 2) fly_relative 横向避开',
                },
                error_msg=result.message,
                cost_time=dt,
                logs=[f"fly_to: 障碍 {result.message}"],
            )

        return SkillResult(
            success=result.success,
            output={
                "start_position": [round(pos.north, 1), round(pos.east, 1), round(pos.down, 1)],
                "arrived_position": [round(final_pos.north, 1), round(final_pos.east, 1), round(final_pos.down, 1)],
                "distance_traveled": round(dist, 1),
                "altitude": round(final_alt, 1),
                "error_to_target": round(err, 1),
            },
            error_msg=result.message if not result.success else "",
            cost_time=dt,
            logs=[f"fly_to ({n:.0f},{e:.0f},{d:.0f}) alt={final_alt:.0f}m err={err:.1f}m: {result.message} [{adapter.name}] {dt}s"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Hover
# ══════════════════════════════════════════════════════════════════════════════

class Hover(Skill):
    name = "hover"
    description = "无人机在当前位置悬停指定时间。前提：无人机必须在空中。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 1.0
    input_schema = {"duration": "float，悬停时间（秒），默认 5.0"}
    output_schema = {"hover_position": "[n, e, d]", "actual_duration": "float"}

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        logger.info(f"[Hover] input={input_data}")
        if not _check_in_air():
            logger.warning("[Hover] not in air")
            return SkillResult(success=False, error_msg="无人机不在空中，无法悬停", logs=["❌ 前提检查失败: 不在空中"])

        duration = float(input_data.get("duration", 5.0))
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")

        _log_state(adapter, "PRE-HOVER")
        logger.info(f"[Hover] adapter.hover({duration}) [{adapter.name}]")
        t0 = time.time()
        result = adapter.hover(duration)
        dt = round(time.time() - t0, 2)
        logger.info(f"[Hover] ok={result.success} msg='{result.message}' {dt}s")
        _log_state(adapter, "POST-HOVER")

        pos = adapter.get_position()
        pos_l = [round(pos.north, 2), round(pos.east, 2), round(pos.down, 2)] if pos else [0, 0, 0]

        return SkillResult(
            success=result.success,
            output={"hover_position": pos_l, "actual_duration": dt},
            error_msg=result.message if not result.success else "",
            cost_time=dt,
            logs=[f"hover({duration}s): {result.message} [{adapter.name}] {dt}s"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  ChangeAltitude（快捷：在当前位置上升/下降到指定高度）
# ══════════════════════════════════════════════════════════════════════════════

class ChangeAltitude(Skill):
    name = "change_altitude"
    description = "在当前水平位置上调整飞行高度。前提：无人机必须在空中。打断后想往上飞用这个。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 2.0
    input_schema = {"altitude": "float，目标高度（米，正数），默认 10.0"}
    output_schema = {"arrived_position": "[n, e, d]", "target_altitude": "float"}

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        altitude = float(input_data.get("altitude", 10.0))
        logger.info(f"[ChangeAltitude] target_alt={altitude}")
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")

        # 优先用 _get_altitude() 获取离地高度
        if hasattr(adapter, '_get_altitude'):
            current_alt = adapter._get_altitude()
        else:
            pos = adapter.get_position()
            current_alt = abs(pos.down)

        logger.info(f"[ChangeAltitude] {current_alt:.1f}m → {altitude:.1f}m")
        _log_state(adapter, "PRE-CHALT")

        t0 = time.time()
        # 优先用 change_altitude_relative（delta正=升高，负=下降）
        delta = altitude - current_alt
        if hasattr(adapter, 'change_altitude_relative'):
            logger.info(f"[ChangeAltitude] using adapter.change_altitude_relative(delta={delta:.1f})")
            result = adapter.change_altitude_relative(delta, speed=8.0)
        else:
            logger.info(f"[ChangeAltitude] fallback: fly_to_ned for vertical")
            pos = adapter.get_position()
            # 计算目标 z（世界坐标）
            ground_z = getattr(adapter, '_ground_z', -13.0)
            target_z = ground_z - altitude
            result = adapter.fly_to_ned(pos.north, pos.east, target_z, speed=15.0)
        dt = round(time.time() - t0, 2)

        if hasattr(adapter, '_get_altitude'):
            final_alt = adapter._get_altitude()
        else:
            final_pos = adapter.get_position()
            final_alt = abs(final_pos.down)
        final_pos = adapter.get_position()
        logger.info(f"[ChangeAltitude] ok={result.success} {current_alt:.1f}→{final_alt:.1f}m {dt}s")
        _log_state(adapter, "POST-CHALT")

        return SkillResult(
            success=result.success,
            error_msg=result.message if not result.success else "",
            output={
                "previous_altitude": round(current_alt, 1),
                "target_altitude": altitude,
                "current_altitude": round(final_alt, 1),
                "current_position": [round(final_pos.north, 1), round(final_pos.east, 1), round(final_pos.down, 1)],
            },
            cost_time=dt,
            logs=[f"change_altitude: {current_alt:.0f}m → {final_alt:.0f}m [{adapter.name}] {dt}s"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  GetPosition
# ══════════════════════════════════════════════════════════════════════════════

class GetPosition(Skill):
    name = "get_position"
    description = "获取无人机当前的 AirSim 世界坐标和 GPS 坐标。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 0.5
    input_schema = {}
    output_schema = {"gps": {"lat": "float", "lon": "float", "alt": "float"}, "ned": "[n, e, d]"}

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        logger.debug("[GetPosition] called")
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")
        
        t0 = time.time()
        gps = adapter.get_gps()
        pos = adapter.get_position()
        state = adapter.get_state()
        dt = round(time.time() - t0, 3)
        
        gps_d = {"lat": round(gps.lat, 7), "lon": round(gps.lon, 7), "alt": round(gps.alt, 2)} if gps and gps.lat != 0 else None
        # 世界坐标 [x, y, z]
        world_pos = [round(pos.north, 2), round(pos.east, 2), round(pos.down, 2)]
        vel = state.velocity if state else None
        hdg = round(state.heading_deg, 1) if state else None

        # 离地高度：使用 adapter._get_altitude()
        if hasattr(adapter, '_get_altitude'):
            altitude = adapter._get_altitude()
        else:
            altitude = abs(pos.down)

        ground_z = getattr(adapter, '_ground_z', None)

        logger.info(f"[GetPosition] 世界坐标={world_pos} 离地高度={altitude:.1f}m GPS={gps_d} vel={vel} [{adapter.name}]")
        
        return SkillResult(
            success=True,
            output={
                "gps": gps_d,
                "position": world_pos,   # AirSim世界坐标 [x, y, z]
                "ned": world_pos,        # 兼容旧字段名
                "altitude": round(altitude, 1),   # 离地高度（正数）
                "ground_z": round(ground_z, 2) if ground_z is not None else None,
                "heading": hdg,
                "velocity": vel,
            },
            cost_time=dt,
            logs=[f"位置: 世界坐标={world_pos} 离地高度={altitude:.1f}m [{adapter.name}]"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  GetBattery
# ══════════════════════════════════════════════════════════════════════════════

class GetBattery(Skill):
    name = "get_battery"
    description = "获取无人机电池电压和剩余电量。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 0.5
    input_schema = {}
    output_schema = {"voltage_v": "float", "remaining_percent": "float"}

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        logger.debug("[GetBattery] called")
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")
        
        t0 = time.time()
        v, pct = adapter.get_battery()
        dt = round(time.time() - t0, 3)

        logger.info(f"[GetBattery] {v:.1f}V {pct:.0%} [{adapter.name}]")
        
        return SkillResult(
            success=True,
            output={"voltage_v": round(v, 2), "remaining_percent": round(pct, 2)},
            cost_time=dt,
            logs=[f"电池: {v:.1f}V, {pct:.0%} [{adapter.name}]"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  ReturnToLaunch
# ══════════════════════════════════════════════════════════════════════════════

class ReturnToLaunch(Skill):
    name = "return_to_launch"
    description = "无人机返回起飞位置并自动降落。调用后无人机会在地面, 不需要再额外调用 land。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 2.0
    input_schema = {}
    output_schema = {"rtl_time": "float"}

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        logger.info("[ReturnToLaunch] called")
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")

        _log_state(adapter, "PRE-RTL")
        t0 = time.time()
        result = adapter.return_to_launch()
        dt = round(time.time() - t0, 2)
        logger.info(f"[ReturnToLaunch] ok={result.success} msg='{result.message}' {dt}s")
        _log_state(adapter, "POST-RTL")

        return SkillResult(
            success=result.success,
            output={"rtl_time": dt},
            error_msg=result.message if not result.success else "",
            cost_time=dt,
            logs=[f"RTL: {result.message} [{adapter.name}] {dt}s"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  FlyRelative — 相对移动 (前后左右上下, 单位: 米)
# ══════════════════════════════════════════════════════════════════════════════

class FlyRelative(Skill):
    name = "fly_relative"
    description = (
        "相对当前位置和朝向移动。使用前/后/左/右/上/下, 单位: 米。"
        "例如: forward=10 表示往前飞10米, right=5 表示往右飞5米。"
        "多个方向可以同时指定。"
    )
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 3.0
    input_schema = {
        "forward": "float, 向前(+)或向后(-), 单位米, 默认0",
        "right": "float, 向右(+)或向左(-), 单位米, 默认0",
        "up": "float, 向上(+)或向下(-), 单位米, 默认0",
        "speed": "float, 飞行速度 m/s, 默认 15.0，⚠️ 必须传 speed=15",
    }
    output_schema = {
        "start_position": "[n, e, d]",
        "end_position": "[n, e, d]",
        "distance": "float",
    }

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        logger.info(f"[FlyRelative] input={input_data}")
        if not _check_in_air():
            return SkillResult(
                success=False,
                error_msg="无人机不在空中, 请先起飞",
                logs=["前提检查失败: 不在空中"],
            )

        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")

        fwd = float(input_data.get("forward", 0))
        rgt = float(input_data.get("right", 0))
        up = float(input_data.get("up", 0))
        speed = max(float(input_data.get("speed", 15.0)), 15.0)  # 最低 15 m/s

        # ── LiDAR 前置障碍检测 ──
        MIN_SAFE_DIST = 3.0  # 米
        try:
            from skills.perception_skills import get_sensor_bridge
            bridge = get_sensor_bridge()
            if bridge:
                scan = bridge.get_lidar_scan()
                if scan and scan.get("ranges"):
                    ranges = scan["ranges"]
                    h_count = scan.get("count", 360)
                    v_count = scan.get("vertical_count", 1)
                    range_max = scan.get("range_max", 100)
                    mid_layer = v_count // 2
                    h_ranges = ranges[mid_layer * h_count : (mid_layer + 1) * h_count]
                    blocked_dirs = []
                    sector_size = max(1, h_count // 12)
                    sectors = {
                        "forward": 0,
                        "right": h_count // 4,
                        "backward": h_count // 2,
                        "left": 3 * h_count // 4,
                    }
                    for dir_name, center_idx in sectors.items():
                        min_r = float('inf')
                        for offset in range(-sector_size, sector_size + 1):
                            idx = (center_idx + offset) % h_count
                            if idx < len(h_ranges):
                                r = h_ranges[idx]
                                if 0.1 < r <= range_max and r < min_r:
                                    min_r = r
                        if min_r < MIN_SAFE_DIST:
                            blocked_dirs.append((dir_name, min_r))

                    move_dirs = []
                    if fwd > 0: move_dirs.append("forward")
                    if fwd < 0: move_dirs.append("backward")
                    if rgt > 0: move_dirs.append("right")
                    if rgt < 0: move_dirs.append("left")

                    for d_name in move_dirs:
                        for bd, br in blocked_dirs:
                            if d_name == bd:
                                logger.warning(f"[FlyRelative] {d_name} blocked at {br:.1f}m < {MIN_SAFE_DIST}m")
                                return SkillResult(
                                    success=False,
                                    error_msg=f"{d_name} 方向检测到障碍物 ({br:.1f}m), 距离不足 {MIN_SAFE_DIST}m",
                                    logs=[f"fly_relative 障碍: {d_name} {br:.1f}m"],
                                )
        except Exception as e:
            logger.debug(f"[FlyRelative] obstacle check skip: {e}")

        # 获取当前位置和航向
        pos = adapter.get_position()
        state = adapter.get_state()
        heading_deg = state.heading_deg if hasattr(state, 'heading_deg') else 0

        start_ned = [round(pos.north, 2), round(pos.east, 2), round(pos.down, 2)]  # 世界坐标
        heading_rad = math.radians(heading_deg)

        # Body frame → NED
        dn = fwd * math.cos(heading_rad) - rgt * math.sin(heading_rad)
        de = fwd * math.sin(heading_rad) + rgt * math.cos(heading_rad)
        dd = -up

        target_n = pos.north + dn
        target_e = pos.east + de
        target_d = pos.down + dd
        distance = math.sqrt(dn**2 + de**2 + dd**2)

        dirs = []
        if fwd > 0: dirs.append(f"前{fwd:.0f}m")
        elif fwd < 0: dirs.append(f"后{-fwd:.0f}m")
        if rgt > 0: dirs.append(f"右{rgt:.0f}m")
        elif rgt < 0: dirs.append(f"左{-rgt:.0f}m")
        if up > 0: dirs.append(f"上{up:.0f}m")
        elif up < 0: dirs.append(f"下{-up:.0f}m")
        dir_str = "+".join(dirs) if dirs else "原地"

        logger.info(f"[FlyRelative] {dir_str} hdg={heading_deg:.0f}° → 世界({target_n:.1f},{target_e:.1f},{target_d:.1f})")
        _log_state(adapter, "PRE-FLYREL")

        t0 = time.time()
        result = adapter.fly_to_ned(target_n, target_e, target_d, speed)
        dt = round(time.time() - t0, 2)

        fp = adapter.get_position()
        end_ned = [round(fp.north, 2), round(fp.east, 2), round(fp.down, 2)]
        logger.info(f"[FlyRelative] ok={result.success} msg='{result.message}' end={end_ned} {dt}s")
        _log_state(adapter, "POST-FLYREL")

        return SkillResult(
            success=result.success,
            output={
                "start_position": start_ned,
                "end_position": end_ned,
                "distance": round(distance, 2),
                "direction": dir_str,
                "heading": round(heading_deg, 1),
            },
            error_msg=result.message if not result.success else "",
            cost_time=dt,
            logs=[f"fly_relative {dir_str}: {result.message} [{adapter.name}] {dt}s"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  LookAround — 原地旋转观察
# ══════════════════════════════════════════════════════════════════════════════

class LookAround(Skill):
    name = "look_around"
    description = (
        "在当前位置原地旋转一圈, 观察四周环境。"
        "用于搜索目标、侦察地形。旋转期间 LiDAR 持续扫描。"
    )
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 2.0
    input_schema = {
        "duration": "float, 旋转持续时间(秒), 默认8 (约转一圈)",
    }
    output_schema = {
        "heading_start": "float",
        "heading_end": "float",
    }

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        logger.info(f"[LookAround] input={input_data}")
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")

        duration = float(input_data.get("duration", 8))
        state = adapter.get_state()
        heading_start = state.heading_deg if hasattr(state, 'heading_deg') else 0

        yaw_rate = 360.0 / duration
        logger.info(f"[LookAround] yaw_rate={yaw_rate:.1f}°/s duration={duration}s hdg_start={heading_start:.0f}°")
        _log_state(adapter, "PRE-LOOKAROUND")
        start_t = time.time()

        try:
            while time.time() - start_t < duration:
                # 用关键字参数，兼容 airsim_physics 和 mavsdk 不同签名
                # mavsdk adapter 的 set_velocity_body 有 duration 参数会 sleep
                if hasattr(adapter, 'name') and 'mavsdk' in adapter.name.lower():
                    adapter.set_velocity_body(0, 0, 0, duration=0.2, yaw_rate=yaw_rate)
                else:
                    adapter.set_velocity_body(0, 0, 0, yaw_rate=yaw_rate)
                    time.sleep(0.2)
            # 停止旋转
            if hasattr(adapter, 'name') and 'mavsdk' in adapter.name.lower():
                adapter.set_velocity_body(0, 0, 0, duration=0.5, yaw_rate=0)
            else:
                adapter.set_velocity_body(0, 0, 0, yaw_rate=0)
                time.sleep(0.5)
        except Exception as e:
            logger.error(f"[LookAround] error: {e}")
            return SkillResult(
                success=False, error_msg=f"旋转失败: {e}",
                cost_time=round(time.time() - start_t, 2),
            )

        dt = round(time.time() - start_t, 2)
        state2 = adapter.get_state()
        heading_end = state2.heading_deg if hasattr(state2, 'heading_deg') else 0
        logger.info(f"[LookAround] hdg {heading_start:.0f}°→{heading_end:.0f}° {dt}s")
        _log_state(adapter, "POST-LOOKAROUND")

        return SkillResult(
            success=True,
            output={"heading_start": round(heading_start, 1), "heading_end": round(heading_end, 1)},
            cost_time=dt,
            logs=[f"look_around: {heading_start:.0f}°→{heading_end:.0f}° {duration:.0f}s [{adapter.name}]"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  MarkLocation — 标记当前位置 (保存到世界模型)
# ══════════════════════════════════════════════════════════════════════════════

class MarkLocation(Skill):
    name = "mark_location"
    description = (
        "在当前位置设置标记点, 记录发现的目标或兴趣点。"
        "标记会保存到世界模型, 后续可以查看所有标记。"
    )
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 0.5
    input_schema = {
        "label": "str, 标记名称, 如'受困者A'、'废墟入口'",
        "priority": "str, 优先级: high/medium/low, 默认medium",
    }
    output_schema = {
        "position": "[n, e, d]",
        "label": "str",
        "mark_id": "int",
    }

    # 类变量: 所有标记
    _marks = []

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        logger.info(f"[MarkLocation] input={input_data}")
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")

        label = input_data.get("label", "标记点")
        priority = input_data.get("priority", "medium")

        pos = adapter.get_position()
        ned = [round(pos.north, 2), round(pos.east, 2), round(pos.down, 2)]

        mark = {
            "id": len(MarkLocation._marks) + 1,
            "label": label,
            "position": ned,
            "priority": priority,
            "time": time.strftime("%H:%M:%S"),
        }
        MarkLocation._marks.append(mark)

        logger.info(f"[MarkLocation] #{mark['id']} '{label}' NED={ned} [{priority}] [{adapter.name}]")

        return SkillResult(
            success=True,
            output={"position": ned, "label": label, "mark_id": mark["id"],
                     "total_marks": len(MarkLocation._marks)},
            cost_time=0.1,
            logs=[f"标记 #{mark['id']}: {label} @ ({ned[0]:.0f},{ned[1]:.0f},{ned[2]:.0f}) [{priority}]"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  GetMarks — 查看所有标记
# ══════════════════════════════════════════════════════════════════════════════

class GetMarks(Skill):
    name = "get_marks"
    description = "查看已设置的所有标记点列表。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 0.5
    input_schema = {}
    output_schema = {"marks": "list", "count": "int"}

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        marks = MarkLocation._marks.copy()
        return SkillResult(
            success=True,
            output={"marks": marks, "count": len(marks)},
            cost_time=0.1,
            logs=[f"共 {len(marks)} 个标记点"],
        )


class Observe(Skill):
    """相机观察技能：通过 AirSim adapter 抓取前向摄像头图像（base64 JPEG）。
    
    不依赖 Gazebo gz 模块，直接调用 SimAdapter.get_image_base64()。
    适用于 AirSim / OpenFly 仿真环境。
    """

    name = "observe"
    description = "抓取无人机前向摄像头图像，返回 base64 编码的 JPEG 图像。用于视觉感知和目标识别。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 1.5
    input_schema = {
        "camera_name": "str，摄像头名称，默认 'front_custom'（可选）",
    }
    output_schema = {
        "image_base64": "str，base64 编码的 JPEG 图像，失败时为 None",
        "has_image": "bool，是否成功获取图像",
        "source": "str，图像来源（airsim / mock）",
    }

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        logger.info(f"[Observe] input={input_data}")
        start = time.time()

        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(
                success=False,
                error_msg="无仿真适配器",
                logs=["❌ observe: 无适配器连接"],
            )

        image_b64 = None
        source = "mock"

        if hasattr(adapter, "get_image_base64"):
            try:
                image_b64 = adapter.get_image_base64()
                if image_b64:
                    source = adapter.name
                    logger.info(f"[Observe] image captured from {source}, len={len(image_b64)}")
            except Exception as e:
                logger.warning(f"[Observe] get_image_base64 error: {e}")

        elapsed = round(time.time() - start, 3)
        has_image = image_b64 is not None

        if has_image:
            return SkillResult(
                success=True,
                output={
                    "image_base64": image_b64,
                    "has_image": True,
                    "source": source,
                },
                cost_time=elapsed,
                logs=[f"✅ observe: 图像获取成功 ({source}), 耗时 {elapsed}s"],
            )
        else:
            # 无图像但不报错——返回 has_image=False，让 Brain 决策
            return SkillResult(
                success=True,
                output={
                    "image_base64": None,
                    "has_image": False,
                    "source": "none",
                },
                cost_time=elapsed,
                logs=[f"⚠️ observe: 未获取到图像（adapter={adapter.name}），耗时 {elapsed}s"],
            )


# ══════════════════════════════════════════════════════════════════════════════
#  OrbitInspect — 航点绕楼巡检（逐层爬升 + VLM 窗户检测）
# ══════════════════════════════════════════════════════════════════════════════

class OrbitInspect(Skill):
    """围绕建筑物飞行巡检的硬技能。

    使用预设航点（非连续螺旋），避免穿模。
    根据建筑尺寸在四周生成航点，逐层爬升，
    每个航点暂停并调用 observe+VLM 分析窗户/外墙状况。
    """

    name = "orbit_inspect"
    description = (
        "围绕指定建筑物进行逐层爬升巡检。"
        "给定建筑中心坐标和尺寸，在四周生成安全航点，逐层升高飞行。"
        "每个航点自动拍照并用VLM分析建筑外观（窗户破损/裂纹/异常）。"
        "完成后返回所有层的巡检报告。"
    )
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 15.0
    input_schema = {
        "center": "[x, y], 建筑中心 AirSim世界坐标（米）",
        "radius": "float, 绕飞半径（米）, 即建筑外墙到航点的距离, 默认 25",
        "start_height": "float, 起始巡检高度（米）, 默认 20",
        "end_height": "float, 终止巡检高度（米）, 默认 80",
        "height_step": "float, 每层高度间隔（米）, 默认 15",
        "points_per_layer": "int, 每层航点数, 默认 8 (八边形)",
        "speed": "float, 飞行速度 m/s, 默认 15.0，⚠️ 必须传 speed=15",
        "focus": "str, VLM 重点关注内容, 默认 '检查窗户是否破损、裂纹、缺失，外墙是否有开裂或异常'",
    }
    output_schema = {
        "layers_inspected": "int, 巡检层数",
        "total_waypoints": "int, 总航点数",
        "observations": "list, 每个航点的VLM观察结果",
        "summary": "str, 巡检总结",
    }

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        logger.info(f"[OrbitInspect] input={input_data}")

        center = input_data.get("center", [0, 0])
        radius = float(input_data.get("radius", 25))
        start_h = float(input_data.get("start_height", 20))
        end_h = float(input_data.get("end_height", 80))
        h_step = float(input_data.get("height_step", 15))
        pts_per_layer = int(input_data.get("points_per_layer", 8))
        speed = float(input_data.get("speed", 15.0))  # 强制最低
        speed = max(speed, 15.0)
        focus = input_data.get("focus",
            "检查窗户是否破损、裂纹、缺失，外墙是否有开裂或异常")

        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")
        if not _check_in_air():
            return SkillResult(success=False,
                error_msg="无人机不在空中，请先执行 takeoff 起飞")

        cn, ce = float(center[0]), float(center[1])
        start_time = time.time()
        all_observations = []
        logs = []

        # 计算层数
        layers = []
        h = start_h
        while h <= end_h:
            layers.append(h)
            h += h_step
        if not layers:
            layers = [start_h]

        logs.append(f"🔄 orbit_inspect: 中心({cn},{ce}), 半径{radius}m, "
                     f"{len(layers)}层 ({start_h}-{end_h}m), 每层{pts_per_layer}点")

        for layer_idx, height in enumerate(layers):
            # 世界坐标：target_z = ground_z - height
            ground_z = getattr(adapter, '_ground_z', -13.0)
            target_down = ground_z - height  # AirSim世界坐标，z越负越高
            logs.append(f"📐 第{layer_idx+1}层: 高度{height}m")

            for pt_idx in range(pts_per_layer):
                # 计算航点: 均匀分布在圆周上
                angle = 2 * math.pi * pt_idx / pts_per_layer
                wp_n = cn + radius * math.cos(angle)
                wp_e = ce + radius * math.sin(angle)

                # 飞到航点
                result = adapter.fly_to_ned(wp_n, wp_e, target_down, speed)
                if not result.success:
                    logs.append(f"⚠️ 航点({wp_n:.0f},{wp_e:.0f})飞行失败: {result.message}")
                    continue

                # 到达航点后悬停1秒稳定画面
                time.sleep(1.0)

                # 调用 VLM 观察
                obs_result = self._observe_at_waypoint(
                    adapter, height, layer_idx, pt_idx, angle, focus)
                all_observations.append(obs_result)

                direction_name = self._angle_to_direction(angle)
                status = "✅" if obs_result.get("has_image") else "⚠️"
                logs.append(
                    f"  {status} 点{pt_idx+1}/{pts_per_layer} "
                    f"({direction_name}面): {obs_result.get('summary', '无描述')[:60]}")

        elapsed = round(time.time() - start_time, 1)

        # 生成汇总
        issues_found = [o for o in all_observations
                        if any(kw in o.get("summary", "")
                               for kw in ["破损", "裂纹", "损坏", "缺失", "异常",
                                          "crack", "broken", "damage", "missing"])]
        if issues_found:
            summary = (f"巡检完成: {len(layers)}层, {len(all_observations)}个观测点, "
                       f"发现{len(issues_found)}处疑似异常。耗时{elapsed}s")
        else:
            summary = (f"巡检完成: {len(layers)}层, {len(all_observations)}个观测点, "
                       f"未发现明显异常。耗时{elapsed}s")

        logs.append(f"🏁 {summary}")

        return SkillResult(
            success=True,
            output={
                "layers_inspected": len(layers),
                "total_waypoints": len(all_observations),
                "observations": all_observations,
                "summary": summary,
            },
            cost_time=elapsed,
            logs=logs,
        )

    def _observe_at_waypoint(self, adapter, height, layer_idx, pt_idx, angle, focus):
        """在航点拍照+VLM分析"""
        import base64 as b64mod

        obs = {
            "layer": layer_idx + 1,
            "point": pt_idx + 1,
            "height": height,
            "angle_deg": round(angle * 180 / 3.14159, 1),
            "direction": self._angle_to_direction(angle),
            "has_image": False,
            "summary": "",
            "objects": [],
        }

        # 抓图
        image_bytes = None
        try:
            if hasattr(adapter, 'get_image_base64'):
                b64_str = adapter.get_image_base64()
                if b64_str:
                    image_bytes = b64mod.b64decode(b64_str)
        except Exception as e:
            logger.warning(f"orbit_inspect 抓图失败: {e}")

        if not image_bytes:
            obs["summary"] = "抓图失败"
            return obs

        obs["has_image"] = True

        # VLM 分析
        try:
            from perception.vlm_analyzer import get_analyzer, init_analyzer
            analyzer = get_analyzer()
            if analyzer is None:
                analyzer = init_analyzer()

            result = analyzer.analyze_image(
                image=image_bytes,
                system_prompt=(
                    "你是一架无人机的建筑巡检视觉系统。分析摄像头图像，重点检查建筑外墙和窗户。"
                    "用简洁的中文回答。重点关注: 窗户破损/裂纹/缺失, 外墙开裂/渗水/脱落, 其他异常。"
                    '输出 JSON: {"description": "观察描述", "objects": [{"type": "类型", "status": "正常/异常", "detail": "细节"}], "issues": ["发现的问题"]}'
                ),
                user_prompt=(
                    f"巡检高度: {height:.0f}米, 方向: {self._angle_to_direction(angle)}面。"
                    f"重点关注: {focus}。"
                    f"请分析这张建筑外观图像。"
                ),
                max_tokens=400,
            )

            if result:
                desc = result.get("description", "无描述")
                objects = result.get("objects", [])
                issues = result.get("issues", [])
                obs["summary"] = desc
                obs["objects"] = objects
                if issues:
                    obs["issues"] = issues
                    obs["summary"] += f" [问题: {', '.join(issues)}]"
            else:
                obs["summary"] = "VLM 返回为空"

        except Exception as e:
            logger.error(f"orbit_inspect VLM 异常: {e}")
            obs["summary"] = f"VLM 分析失败: {e}"

        return obs

    @staticmethod
    def _angle_to_direction(angle):
        """角度(弧度) → 方位名称"""
        import math
        deg = (angle * 180 / math.pi) % 360
        if deg < 22.5 or deg >= 337.5:
            return "北"
        elif deg < 67.5:
            return "东北"
        elif deg < 112.5:
            return "东"
        elif deg < 157.5:
            return "东南"
        elif deg < 202.5:
            return "南"
        elif deg < 247.5:
            return "西南"
        elif deg < 292.5:
            return "西"
        else:
            return "西北"
