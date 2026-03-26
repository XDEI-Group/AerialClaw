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
import logging

from skills.base_skill import Skill, SkillResult

logger = logging.getLogger(__name__)


def _get_adapter():
    """获取当前活跃的仿真适配器。"""
    from adapters.adapter_manager import get_adapter
    return get_adapter()


def _check_in_air() -> bool:
    """检查无人机是否在空中。"""
    adapter = _get_adapter()
    if adapter is None:
        return False
    try:
        return adapter.is_in_air()
    except Exception:
        return False


def _check_armed() -> bool:
    """检查无人机是否已解锁。"""
    adapter = _get_adapter()
    if adapter is None:
        return False
    try:
        return adapter.is_armed()
    except Exception:
        return False


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
        if _check_in_air():
            return SkillResult(success=False, error_msg="无人机已在空中，无法起飞", logs=["❌ 前提检查失败: 已在空中"])

        altitude = input_data.get("altitude", 5.0)
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器", logs=["❌ 无适配器连接"])
        
        result = adapter.takeoff(altitude)
        return SkillResult(
            success=result.success,
            output={"actual_altitude": result.data.get("altitude", 0), "takeoff_time": result.duration},
            error_msg=result.message if not result.success else "",
            cost_time=result.duration,
            logs=[f"takeoff({altitude}m): {result.message} [{adapter.name}]"],
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
        if not _check_in_air():
            return SkillResult(success=True, output={"landed_position": [], "land_time": 0.0},
                               cost_time=0.0, logs=["✅ 无人机已在地面，无需降落"])

        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")
        
        result = adapter.land()
        gps = adapter.get_gps()
        ned = adapter.get_position()
        pos = [round(gps.lat,7), round(gps.lon,7), round(gps.alt,2)] if gps else None
        ned_l = [round(ned.north,2), round(ned.east,2), round(ned.down,2)] if ned else None

        return SkillResult(
            success=result.success,
            output={"landed_position": pos, "ned": ned_l, "land_time": result.duration},
            error_msg=result.message if not result.success else "",
            cost_time=result.duration,
            logs=[f"land: {result.message} [{adapter.name}]"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  FlyTo
# ══════════════════════════════════════════════════════════════════════════════

class FlyTo(Skill):
    name = "fly_to"
    description = "底层移动技能：飞到指定NED坐标。down负值=高度，如down=-80表示80m高。⚠️使用前必须先get_position！高度低于50m会被自动修正到80m。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 3.0
    input_schema = {
        "target_position": "[north, east, down]，NED坐标。down=-80=80m高。⚠️高度<50m会被自动修正！先get_position再决定高度！",
        "speed": "float，飞行速度 m/s，默认 8.0",
    }
    output_schema = {"arrived_position": "[n, e, d]", "distance_traveled": "float", "altitude": "float", "start_position": "[n, e, d]"}

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        target = input_data.get("target_position", [0, 0, -80])
        speed = input_data.get("speed", 8.0)
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")
        
        pos = adapter.get_position()
        current_alt = abs(pos.down)
        
        n, e = float(target[0]), float(target[1])
        d = float(target[2]) if len(target) > 2 else -80.0
        
        # down 正值=地下，修正
        if d > 0:
            d = -d
        
        # 高度安全：< 50m 自动调到 80m
        target_alt = abs(d)
        height_corrected = False
        if target_alt < 50:
            logger.warning(f"fly_to: 目标高度{target_alt:.0f}m不安全，自动调整到80m")
            d = -80.0
            target_alt = 80.0
            height_corrected = True
        
        logger.info(f"fly_to: ({pos.north:.1f},{pos.east:.1f},alt={current_alt:.0f}m) → ({n},{e},alt={target_alt:.0f}m)")
        
        result = adapter.fly_to_ned(n, e, d, speed)

        final_pos = adapter.get_position()
        final_alt = abs(final_pos.down)
        dist = ((final_pos.north - pos.north)**2 + (final_pos.east - pos.east)**2) ** 0.5

        msg = result.message
        if height_corrected and result.success:
            msg = f"已到达，高度从{target_alt:.0f}m（你给的值不安全，已自动修正到80m）"

        # 障碍物阻挡：在 output 中包含详细信息供 LLM 重规划
        if not result.success and '障碍物' in result.message:
            obstacle_info = getattr(adapter, '_last_obstacle_info', {})
            return SkillResult(
                success=False,
                output={
                    'obstacle_detected': True,
                    'obstacle_direction': obstacle_info.get('direction', '前方'),
                    'obstacle_distance': obstacle_info.get('front_dist', 0),
                    'current_position': [round(final_pos.north, 1), round(final_pos.east, 1), round(final_pos.down, 1)],
                    'original_target': [n, e, d],
                    'suggestion': '建议: 1) change_altitude 升高绕过 2) fly_relative 横向避开 3) 重新规划路线',
                },
                error_msg=result.message,
                cost_time=result.duration,
                logs=[f"fly_to: 障碍物阻挡 {result.message}"],
            )

        return SkillResult(
            success=result.success,
            output={
                "start_position": [round(pos.north, 1), round(pos.east, 1), round(pos.down, 1)],
                "arrived_position": [round(final_pos.north, 1), round(final_pos.east, 1), round(final_pos.down, 1)],
                "distance_traveled": round(dist, 1),
                "altitude": round(final_alt, 1),
                "height_corrected": height_corrected,
            },
            error_msg=msg if not result.success else "",
            cost_time=result.duration,
            logs=[f"fly_to ({n},{e}) alt={final_alt:.0f}m: {msg}"],
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
        if not _check_in_air():
            return SkillResult(success=False, error_msg="无人机不在空中，无法悬停", logs=["❌ 前提检查失败: 不在空中"])

        duration = input_data.get("duration", 5.0)
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")
        
        result = adapter.hover(duration)
        pos = result.data.get("position", [0, 0, 0])
        
        return SkillResult(
            success=result.success,
            output={"hover_position": pos, "actual_duration": result.duration},
            error_msg=result.message if not result.success else "",
            cost_time=result.duration,
            logs=[f"hover({duration}s): {result.message} [{adapter.name}]"],
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
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")

        # 获取当前位置
        pos = adapter.get_position()
        current_alt = abs(pos.down)
        target_down = -abs(altitude)
        result = adapter.fly_to_ned(pos.north, pos.east, target_down, speed=5.0)

        final_pos = adapter.get_position()
        return SkillResult(
            success=result.success,
            error_msg=result.message if not result.success else "",
            data={
                "previous_altitude": round(current_alt, 1),
                "target_altitude": altitude,
                "current_altitude": round(abs(final_pos.down), 1),
                "current_position": [round(final_pos.north, 1), round(final_pos.east, 1), round(final_pos.down, 1)],
            },
            cost_time=0,
            logs=[f"change_altitude: {current_alt:.0f}m → {abs(final_pos.down):.0f}m"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  GetPosition
# ══════════════════════════════════════════════════════════════════════════════

class GetPosition(Skill):
    name = "get_position"
    description = "获取无人机当前的 GPS 坐标和 NED 局部坐标。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = []
    cost = 0.5
    input_schema = {}
    output_schema = {"gps": {"lat": "float", "lon": "float", "alt": "float"}, "ned": "[n, e, d]"}

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")
        
        start = time.time()
        gps = adapter.get_gps()
        ned = adapter.get_position()
        elapsed = round(time.time() - start, 2)
        
        gps_d = {"lat": round(gps.lat, 7), "lon": round(gps.lon, 7), "alt": round(gps.alt, 2)} if gps else None
        ned_l = [round(ned.north, 2), round(ned.east, 2), round(ned.down, 2)]
        
        return SkillResult(
            success=True,
            output={"gps": gps_d, "ned": ned_l},
            cost_time=elapsed,
            logs=[f"位置: GPS={gps_d}, NED={ned_l} [{adapter.name}]"],
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
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")
        
        start = time.time()
        v, pct = adapter.get_battery()
        elapsed = round(time.time() - start, 2)
        
        return SkillResult(
            success=True,
            output={"voltage_v": round(v, 2), "remaining_percent": round(pct, 2)},
            cost_time=elapsed,
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
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")
        
        result = adapter.return_to_launch()
        return SkillResult(
            success=result.success,
            output={"rtl_time": result.duration},
            error_msg=result.message if not result.success else "",
            cost_time=result.duration,
            logs=[f"RTL: {result.message} [{adapter.name}]"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  FlyRelative — 相对移动 (前后左右上下, 单位: 米)
# ══════════════════════════════════════════════════════════════════════════════

import math

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
        "speed": "float, 飞行速度 m/s, 默认2.0",
    }
    output_schema = {
        "start_position": "[n, e, d]",
        "end_position": "[n, e, d]",
        "distance": "float",
    }

    def check_precondition(self, robot_state: dict) -> bool:
        return True

    def execute(self, input_data: dict) -> SkillResult:
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
        speed = float(input_data.get("speed", 2.0))

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
                    # 取中间层 (水平面) 的数据
                    mid_layer = v_count // 2
                    h_ranges = ranges[mid_layer * h_count : (mid_layer + 1) * h_count]
                    # 判断目标方向的扇区 (前后左右各取 ±30° 扇区)
                    blocked_dirs = []
                    sector_size = max(1, h_count // 12)  # 30° = 360°/12
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

                    # 检查要飞的方向是否有障碍
                    move_dirs = []
                    if fwd > 0: move_dirs.append("forward")
                    if fwd < 0: move_dirs.append("backward")
                    if rgt > 0: move_dirs.append("right")
                    if rgt < 0: move_dirs.append("left")

                    for d in move_dirs:
                        for bd, br in blocked_dirs:
                            if d == bd:
                                logger.warning(f"fly_relative: {d} 方向障碍物 {br:.1f}m < {MIN_SAFE_DIST}m, 拒绝执行")
                                return SkillResult(
                                    success=False,
                                    error_msg=f"{d} 方向检测到障碍物 ({br:.1f}m), 距离不足 {MIN_SAFE_DIST}m, 请更换方向或先升高",
                                    logs=[f"fly_relative 障碍检测: {d} 方向 {br:.1f}m, 安全距离 {MIN_SAFE_DIST}m"],
                                )
        except Exception as e:
            logger.debug(f"fly_relative 障碍检测跳过: {e}")

        # 获取当前位置和航向
        pos = adapter.get_position()
        state = adapter.get_state()
        heading_deg = state.heading_deg if hasattr(state, 'heading_deg') else 0

        start_ned = [round(pos.north, 2), round(pos.east, 2), round(pos.down, 2)]
        heading_rad = math.radians(heading_deg)

        # Body frame → NED: 根据航向旋转
        #   前(fwd) 和 右(rgt) 转换为 北(dn) 和 东(de)
        dn = fwd * math.cos(heading_rad) - rgt * math.sin(heading_rad)
        de = fwd * math.sin(heading_rad) + rgt * math.cos(heading_rad)
        dd = -up  # NED 的 down 是正, 上是负

        target_n = pos.north + dn
        target_e = pos.east + de
        target_d = pos.down + dd

        distance = math.sqrt(dn**2 + de**2 + dd**2)

        # 构造方向描述
        dirs = []
        if fwd > 0: dirs.append(f"前{fwd:.0f}m")
        elif fwd < 0: dirs.append(f"后{-fwd:.0f}m")
        if rgt > 0: dirs.append(f"右{rgt:.0f}m")
        elif rgt < 0: dirs.append(f"左{-rgt:.0f}m")
        if up > 0: dirs.append(f"上{up:.0f}m")
        elif up < 0: dirs.append(f"下{-up:.0f}m")
        dir_str = "+".join(dirs) if dirs else "原地"

        logger.info(f"fly_relative: {dir_str} (heading={heading_deg:.0f}°) → NED({target_n:.1f},{target_e:.1f},{target_d:.1f})")

        result = adapter.fly_to_ned(target_n, target_e, target_d, speed)
        final = result.data.get("position", [target_n, target_e, target_d])

        return SkillResult(
            success=result.success,
            output={
                "start_position": start_ned,
                "end_position": [round(x, 2) for x in final],
                "distance": round(distance, 2),
                "direction": dir_str,
                "heading": round(heading_deg, 1),
            },
            error_msg=result.message if not result.success else "",
            cost_time=result.duration,
            logs=[f"fly_relative {dir_str}: {result.message} [{adapter.name}]"],
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
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")

        duration = float(input_data.get("duration", 8))
        state = adapter.get_state()
        heading_start = state.heading_deg if hasattr(state, 'heading_deg') else 0

        # 使用 body frame 速度控制: yaw_rate=45°/s, 8秒转一圈
        yaw_rate = 360.0 / duration
        start_t = time.time()

        try:
            while time.time() - start_t < duration:
                adapter.set_velocity_body(0, 0, 0, yaw_rate)
                time.sleep(0.2)
            # 停止旋转
            adapter.set_velocity_body(0, 0, 0, 0)
            time.sleep(0.5)
        except Exception as e:
            return SkillResult(
                success=False, error_msg=f"旋转失败: {e}",
                cost_time=round(time.time() - start_t, 2),
            )

        state2 = adapter.get_state()
        heading_end = state2.heading_deg if hasattr(state2, 'heading_deg') else 0

        return SkillResult(
            success=True,
            output={"heading_start": round(heading_start, 1), "heading_end": round(heading_end, 1)},
            cost_time=round(time.time() - start_t, 2),
            logs=[f"look_around: {heading_start:.0f}°→{heading_end:.0f}°, 持续{duration:.0f}s"],
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

        logger.info(f"mark_location: #{mark['id']} '{label}' at NED={ned} [{priority}]")

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
        import time
        start = time.time()

        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(
                success=False,
                error_msg="无仿真适配器",
                logs=["❌ observe: 无适配器连接"],
            )

        # 尝试调用 adapter 的 get_image_base64 方法
        image_b64 = None
        source = "mock"

        if hasattr(adapter, "get_image_base64"):
            try:
                image_b64 = adapter.get_image_base64()
                if image_b64:
                    source = "airsim"
            except Exception as e:
                logger.warning(f"observe: get_image_base64 失败: {e}")

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
        "center": "[north, east], 建筑中心 NED 坐标（米）",
        "radius": "float, 绕飞半径（米）, 即建筑外墙到航点的距离, 默认 25",
        "start_height": "float, 起始巡检高度（米）, 默认 20",
        "end_height": "float, 终止巡检高度（米）, 默认 80",
        "height_step": "float, 每层高度间隔（米）, 默认 15",
        "points_per_layer": "int, 每层航点数, 默认 8 (八边形)",
        "speed": "float, 飞行速度 m/s, 默认 2.0",
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
        import math

        center = input_data.get("center", [0, 0])
        radius = float(input_data.get("radius", 25))
        start_h = float(input_data.get("start_height", 20))
        end_h = float(input_data.get("end_height", 80))
        h_step = float(input_data.get("height_step", 15))
        pts_per_layer = int(input_data.get("points_per_layer", 8))
        speed = float(input_data.get("speed", 2.0))
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
            target_down = -height  # NED: 负值 = 向上
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
