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
    description = "无人机解锁电机并起飞到指定高度。前提：无人机在地面。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = ["battery > 20%", "robot_type == UAV", "in_air == False"]
    cost = 2.0
    input_schema = {"altitude": "float，起飞目标高度（米），默认 5.0"}
    output_schema = {"actual_altitude": "float", "takeoff_time": "float"}

    def check_precondition(self, robot_state: dict) -> bool:
        if robot_state.get("battery", 100) <= 20:
            return False
        if _check_in_air():
            return False  # 已在空中，不能再起飞
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
    description = "无人机降落到地面。前提：无人机在空中。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = ["battery > 10%", "robot_type == UAV", "in_air == True"]
    cost = 1.5
    input_schema = {}
    output_schema = {"landed_position": "[lat, lon, alt]", "land_time": "float"}

    def check_precondition(self, robot_state: dict) -> bool:
        if robot_state.get("battery", 100) <= 10:
            return False
        if not _check_in_air():
            return False  # 不在空中，无法降落
        return True

    def execute(self, input_data: dict) -> SkillResult:
        if not _check_in_air():
            return SkillResult(success=False, error_msg="无人机不在空中，无法降落", logs=["❌ 前提检查失败: 不在空中"])

        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")
        
        result = adapter.land()
        gps = adapter.get_gps()
        pos = [gps.lat, gps.lon, gps.alt]
        
        return SkillResult(
            success=result.success,
            output={"landed_position": pos, "land_time": result.duration},
            error_msg=result.message if not result.success else "",
            cost_time=result.duration,
            logs=[f"land: {result.message} [{adapter.name}]"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  FlyTo
# ══════════════════════════════════════════════════════════════════════════════

class FlyTo(Skill):
    name = "fly_to"
    description = "无人机飞行到指定 NED 坐标。前提：无人机必须在空中。north=正北, east=正东, down=向下（负值=向上）。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = ["battery > 20%", "robot_type == UAV", "in_air == True"]
    cost = 3.0
    input_schema = {
        "target_position": "[north, east, down]，NED 坐标（米）",
        "speed": "float，飞行速度 m/s，默认 2.0",
    }
    output_schema = {"arrived_position": "[n, e, d]", "distance_traveled": "float"}

    def check_precondition(self, robot_state: dict) -> bool:
        if robot_state.get("battery", 100) <= 20:
            return False
        if not _check_in_air():
            return False  # 必须在空中才能飞行
        return True

    def execute(self, input_data: dict) -> SkillResult:
        if not _check_in_air():
            return SkillResult(
                success=False,
                error_msg="无人机不在空中，请先执行 takeoff 起飞",
                logs=["❌ 前提检查失败: 不在空中，请先起飞"]
            )

        target = input_data.get("target_position", [0, 0, -5])
        speed = input_data.get("speed", 2.0)
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")
        
        n, e, d = float(target[0]), float(target[1]), float(target[2])
        result = adapter.fly_to_ned(n, e, d, speed)
        
        final = result.data.get("position", target)
        dist = (final[0]**2 + final[1]**2 + final[2]**2) ** 0.5
        
        return SkillResult(
            success=result.success,
            output={"arrived_position": final, "distance_traveled": round(dist, 2)},
            error_msg=result.message if not result.success else "",
            cost_time=result.duration,
            logs=[f"fly_to NED=({n},{e},{d}): {result.message} [{adapter.name}]"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Hover
# ══════════════════════════════════════════════════════════════════════════════

class Hover(Skill):
    name = "hover"
    description = "无人机在当前位置悬停指定时间。前提：无人机必须在空中。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = ["battery > 15%", "robot_type == UAV", "in_air == True"]
    cost = 1.0
    input_schema = {"duration": "float，悬停时间（秒），默认 5.0"}
    output_schema = {"hover_position": "[n, e, d]", "actual_duration": "float"}

    def check_precondition(self, robot_state: dict) -> bool:
        if robot_state.get("battery", 100) <= 15:
            return False
        if not _check_in_air():
            return False
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
    preconditions = ["battery > 20%", "robot_type == UAV", "in_air == True"]
    cost = 2.0
    input_schema = {"altitude": "float，目标高度（米，正数），默认 10.0"}
    output_schema = {"arrived_position": "[n, e, d]", "target_altitude": "float"}

    def check_precondition(self, robot_state: dict) -> bool:
        if robot_state.get("battery", 100) <= 20:
            return False
        if not _check_in_air():
            return False
        return True

    def execute(self, input_data: dict) -> SkillResult:
        if not _check_in_air():
            return SkillResult(success=False, error_msg="无人机不在空中，请先起飞", logs=["❌ 前提检查失败: 不在空中"])

        altitude = float(input_data.get("altitude", 10.0))
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")

        # 获取当前水平位置，只改高度
        pos = adapter.get_position()
        target_down = -abs(altitude)  # 正数高度转 NED down（负值=上）
        result = adapter.fly_to_ned(pos.north, pos.east, target_down, speed=2.0)

        final = result.data.get("position", [pos.north, pos.east, target_down])
        return SkillResult(
            success=result.success,
            output={"arrived_position": final, "target_altitude": altitude},
            error_msg=result.message if not result.success else "",
            cost_time=result.duration,
            logs=[f"change_altitude → {altitude}m: {result.message} [{adapter.name}]"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  GetPosition
# ══════════════════════════════════════════════════════════════════════════════

class GetPosition(Skill):
    name = "get_position"
    description = "获取无人机当前的 GPS 坐标和 NED 局部坐标。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = ["robot_type == UAV"]
    cost = 0.5
    input_schema = {}
    output_schema = {"gps": {"lat": "float", "lon": "float", "alt": "float"}, "ned": "[n, e, d]"}

    def check_precondition(self, robot_state: dict) -> bool:
        return robot_state.get("robot_type", "") == "UAV"

    def execute(self, input_data: dict) -> SkillResult:
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(success=False, error_msg="无仿真适配器")
        
        start = time.time()
        gps = adapter.get_gps()
        ned = adapter.get_position()
        elapsed = round(time.time() - start, 2)
        
        gps_d = {"lat": round(gps.lat, 7), "lon": round(gps.lon, 7), "alt": round(gps.alt, 2)}
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
    preconditions = ["robot_type == UAV"]
    cost = 0.5
    input_schema = {}
    output_schema = {"voltage_v": "float", "remaining_percent": "float"}

    def check_precondition(self, robot_state: dict) -> bool:
        return robot_state.get("robot_type", "") == "UAV"

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
    description = "无人机返回起飞位置并降落。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = ["battery > 10%", "robot_type == UAV"]
    cost = 2.0
    input_schema = {}
    output_schema = {"rtl_time": "float"}

    def check_precondition(self, robot_state: dict) -> bool:
        return robot_state.get("battery", 100) > 10

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
    preconditions = ["battery > 20%", "in_air == True"]
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
        if robot_state.get("battery", 100) <= 20:
            return False
        return _check_in_air()

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
    preconditions = ["in_air == True"]
    cost = 2.0
    input_schema = {
        "duration": "float, 旋转持续时间(秒), 默认8 (约转一圈)",
    }
    output_schema = {
        "heading_start": "float",
        "heading_end": "float",
    }

    def check_precondition(self, robot_state: dict) -> bool:
        return _check_in_air()

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

