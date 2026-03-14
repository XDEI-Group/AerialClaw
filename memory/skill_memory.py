"""
skill_memory.py
技能记忆模块：记录技能执行历史，提供技能可靠性查询接口。

职责：
    - 记录每次技能执行的成功率、执行耗时等统计数据
    - 向 Brain 模块提供技能可靠性信息，辅助技能选择
    - 支持多机器人维度的技能统计

Functions:
    update_skill_statistics(feedback)   - 根据执行反馈更新技能统计
    get_skill_reliability(skill_name)   - 获取技能可靠性（成功率 + 平均耗时）

feedback 数据格式（来自 Runtime 模块）：
    {
        "task_id": str,
        "skill": str,          # 技能名称
        "robot": str,          # 执行机器人 ID
        "success": bool,
        "cost_time": float     # 执行耗时（秒）
    }
"""

import time
from dataclasses import dataclass, field


@dataclass
class SkillStats:
    """单个技能的统计数据"""
    skill_name: str
    total_executions: int = 0
    success_count: int = 0
    total_cost_time: float = 0.0
    last_updated: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        """成功率 [0.0, 1.0]"""
        if self.total_executions == 0:
            return -1.0
        return round(self.success_count / self.total_executions, 4)

    @property
    def average_cost_time(self) -> float:
        """平均执行耗时（秒）"""
        if self.total_executions == 0:
            return 0.0
        return round(self.total_cost_time / self.total_executions, 4)


class SkillMemory:
    """
    技能记忆。
    按技能名称维护统计数据，支持全局和按机器人维度的查询。

    未来升级方向：
        - 接入 Neural memory embedding
        - RAG 检索式技能经验复用
    """

    def __init__(self):
        # 全局技能统计：{skill_name: SkillStats}
        self._global_stats: dict[str, SkillStats] = {}
        # 按机器人维度的技能统计：{robot_id: {skill_name: SkillStats}}
        self._robot_stats: dict[str, dict[str, SkillStats]] = {}
        # 原始执行记录（用于审计）
        self._execution_logs: list[dict] = []

    def update_skill_statistics(self, feedback: dict) -> None:
        """
        根据执行反馈更新技能统计数据。

        Args:
            feedback: 执行反馈字典，包含：
                - task_id (str):   任务 ID
                - skill (str):     技能名称
                - robot (str):     执行机器人 ID
                - success (bool):  是否成功
                - cost_time (float): 执行耗时
        """
        skill_name = feedback.get("skill", "")
        robot_id = feedback.get("robot", "")
        success = feedback.get("success", False)
        cost_time = feedback.get("cost_time", 0.0)

        if not skill_name:
            return

        # 记录原始日志
        self._execution_logs.append({
            **feedback,
            "logged_at": time.time(),
        })

        # 更新全局统计
        if skill_name not in self._global_stats:
            self._global_stats[skill_name] = SkillStats(skill_name=skill_name)
        gs = self._global_stats[skill_name]
        gs.total_executions += 1
        gs.success_count += 1 if success else 0
        gs.total_cost_time += cost_time
        gs.last_updated = time.time()

        # 更新机器人维度统计
        if robot_id:
            if robot_id not in self._robot_stats:
                self._robot_stats[robot_id] = {}
            if skill_name not in self._robot_stats[robot_id]:
                self._robot_stats[robot_id][skill_name] = SkillStats(skill_name=skill_name)
            rs = self._robot_stats[robot_id][skill_name]
            rs.total_executions += 1
            rs.success_count += 1 if success else 0
            rs.total_cost_time += cost_time
            rs.last_updated = time.time()

    def get_skill_reliability(
        self,
        skill_name: str,
        robot_id: str | None = None,
    ) -> dict:
        """
        获取技能可靠性统计信息。

        Args:
            skill_name: 技能名称
            robot_id:   若指定，返回该机器人维度的统计；否则返回全局统计

        Returns:
            dict: {
                "skill_name": str,
                "success_rate": float,       # -1.0 表示无记录
                "average_cost_time": float,
                "total_executions": int,
                "last_updated": float
            }
        """
        if robot_id and robot_id in self._robot_stats:
            stats = self._robot_stats[robot_id].get(skill_name)
        else:
            stats = self._global_stats.get(skill_name)

        if stats is None:
            return {
                "skill_name": skill_name,
                "success_rate": -1.0,
                "average_cost_time": 0.0,
                "total_executions": 0,
                "last_updated": None,
            }

        return {
            "skill_name": stats.skill_name,
            "success_rate": stats.success_rate,
            "average_cost_time": stats.average_cost_time,
            "total_executions": stats.total_executions,
            "last_updated": stats.last_updated,
        }

    def get_all_skill_reliabilities(self) -> list[dict]:
        """
        返回所有技能的全局可靠性统计，按成功率降序排列。

        Returns:
            list[dict]: 所有技能的可靠性信息
        """
        result = [
            self.get_skill_reliability(name)
            for name in self._global_stats
        ]
        result.sort(key=lambda x: x["success_rate"], reverse=True)
        return result

    def get_best_robot_for_skill(self, skill_name: str) -> str | None:
        """
        返回历史上执行指定技能成功率最高的机器人 ID。

        Args:
            skill_name: 技能名称

        Returns:
            str | None: 最佳机器人 ID，若无记录返回 None
        """
        best_robot = None
        best_rate = -1.0
        for robot_id, skill_dict in self._robot_stats.items():
            if skill_name in skill_dict:
                rate = skill_dict[skill_name].success_rate
                if rate > best_rate:
                    best_rate = rate
                    best_robot = robot_id
        return best_robot

    def clear(self) -> None:
        """清空所有统计数据。"""
        self._global_stats.clear()
        self._robot_stats.clear()
        self._execution_logs.clear()

    def __repr__(self):
        return (
            f"<SkillMemory "
            f"skills={list(self._global_stats.keys())} "
            f"robots={list(self._robot_stats.keys())}>"
        )
