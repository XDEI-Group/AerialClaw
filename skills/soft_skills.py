"""
soft_skills.py
软技能（Soft Skills）：可进化的组合能力，由多个硬技能按逻辑组合而成。

特点：
    - skill_type = "soft"
    - 可由 LLM 生成、更新、重组步骤链
    - 代表任务级别的机器人能力

包含：SearchTarget / RescuePerson / PatrolArea
"""

import time
from skills.base_skill import Skill, SkillResult
from skills.hard_skills import FlyTo, Hover, GetPosition


class SearchTarget(Skill):
    """搜索目标：飞行到指定区域，悬停观察。"""

    name = "search_target"
    description = "UAV 飞行至目标区域，悬停观察搜索目标。返回到达位置和观察时间。"
    skill_type = "soft"
    robot_type = ["UAV"]
    preconditions = ["battery > 30%", "robot_type == UAV"]
    cost = 6.0
    input_schema = {
        "area_position": "[n, e, d]，搜索区域 NED 坐标",
        "observe_time": "float，观察时间（秒），默认 5.0",
    }
    output_schema = {
        "search_position": "[n, e, d]，实际搜索位置",
        "observe_duration": "float，实际观察时间",
    }

    def __init__(self):
        self._fly_to = FlyTo()
        self._hover = Hover()

    def check_precondition(self, robot_state: dict) -> bool:
        return robot_state.get("battery", 100) > 30 and robot_state.get("robot_type", "") == "UAV"

    def execute(self, input_data: dict) -> SkillResult:
        area_pos = input_data.get("area_position", [0, 0, -10])
        obs_time = input_data.get("observe_time", 5.0)
        logs = []
        start = time.time()

        # 飞到搜索区域
        r = self._fly_to.execute({"target_position": area_pos})
        logs.extend(r.logs)
        if not r.success:
            return SkillResult(success=False, error_msg="FlyTo failed", logs=logs, cost_time=round(time.time()-start, 2))

        # 悬停观察
        r2 = self._hover.execute({"duration": obs_time})
        logs.extend(r2.logs)

        return SkillResult(
            success=True,
            output={"search_position": r.output.get("arrived_position", area_pos), "observe_duration": r2.output.get("actual_duration", obs_time)},
            cost_time=round(time.time() - start, 2),
            logs=logs,
        )


class RescuePerson(Skill):
    """救援任务：飞到目标位置侦察，悬停标记，然后返回。"""

    name = "rescue_person"
    description = "UAV 飞行侦察并在目标位置悬停标记，完成救援定位。"
    skill_type = "soft"
    robot_type = ["UAV"]
    preconditions = ["battery > 40%", "robot_type == UAV"]
    cost = 10.0
    input_schema = {
        "target_position": "[n, e, d]，侦察目标 NED 坐标",
        "hover_time": "float，悬停标记时间（秒），默认 5.0",
    }
    output_schema = {
        "rescue_position": "[n, e, d]",
        "mission_time": "float",
    }

    def __init__(self):
        self._fly_to = FlyTo()
        self._hover = Hover()
        self._get_pos = GetPosition()

    def check_precondition(self, robot_state: dict) -> bool:
        return robot_state.get("battery", 100) > 40 and robot_state.get("robot_type", "") == "UAV"

    def execute(self, input_data: dict) -> SkillResult:
        target = input_data.get("target_position", [0, 0, -10])
        hover_t = input_data.get("hover_time", 5.0)
        logs = []
        start = time.time()

        # 飞到目标
        r = self._fly_to.execute({"target_position": target})
        logs.extend(r.logs)
        if not r.success:
            return SkillResult(success=False, error_msg="FlyTo failed", logs=logs, cost_time=round(time.time()-start, 2))

        # 悬停标记
        r2 = self._hover.execute({"duration": hover_t})
        logs.extend(r2.logs)

        # 获取当前位置
        r3 = self._get_pos.execute({})
        logs.extend(r3.logs)
        pos = r3.output.get("ned", target)

        return SkillResult(
            success=True,
            output={"rescue_position": pos, "mission_time": round(time.time()-start, 2)},
            cost_time=round(time.time() - start, 2),
            logs=logs,
        )


class PatrolArea(Skill):
    """区域巡逻：按航点序列飞行，在每个航点悬停观察。"""

    name = "patrol_area"
    description = "UAV 按给定航点序列飞行，在每个航点悬停观察，完成区域巡逻任务。"
    skill_type = "soft"
    robot_type = ["UAV"]
    preconditions = ["battery > 50%", "robot_type == UAV"]
    cost = 15.0
    input_schema = {
        "waypoints": "list[[n,e,d]]，巡逻航点序列",
        "hover_time": "float，每个航点悬停时间（秒），默认 3.0",
    }
    output_schema = {
        "waypoints_visited": "int",
        "patrol_complete": "bool",
    }

    def __init__(self):
        self._fly_to = FlyTo()
        self._hover = Hover()

    def check_precondition(self, robot_state: dict) -> bool:
        return robot_state.get("battery", 100) > 50 and robot_state.get("robot_type", "") == "UAV"

    def execute(self, input_data: dict) -> SkillResult:
        waypoints = input_data.get("waypoints", [[0, 0, -10], [10, 0, -10], [10, 10, -10]])
        hover_t = input_data.get("hover_time", 3.0)
        logs = []
        start = time.time()

        for i, wp in enumerate(waypoints):
            r = self._fly_to.execute({"target_position": wp})
            logs.extend(r.logs)
            if not r.success:
                return SkillResult(
                    success=False, error_msg=f"FlyTo waypoint {i} failed",
                    output={"waypoints_visited": i, "patrol_complete": False},
                    logs=logs, cost_time=round(time.time()-start, 2),
                )
            r2 = self._hover.execute({"duration": hover_t})
            logs.extend(r2.logs)

        return SkillResult(
            success=True,
            output={"waypoints_visited": len(waypoints), "patrol_complete": True},
            cost_time=round(time.time() - start, 2),
            logs=logs,
        )
