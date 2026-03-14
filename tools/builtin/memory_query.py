"""
tools/builtin/memory_query.py  —— 记忆查询工具

提供对 EpisodicMemory 和 SkillMemory 的只读查询接口。

工具列表：
    RetrieveEpisodeTool      : 按任务描述检索相似历史经历
    GetSkillReliabilityTool  : 查询技能执行历史可靠性（成功率 + 平均耗时）
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.base_tool import BaseTool
from memory.episodic_memory import EpisodicMemory
from memory.skill_memory import SkillMemory


class RetrieveEpisodeTool(BaseTool):
    """
    按任务描述检索相似历史执行经历。

    LLM 调用时机：规划类似任务前，查询历史经验以优化方案。
    """

    def __init__(self, episodic_memory: EpisodicMemory):
        self._em = episodic_memory

    @property
    def name(self) -> str:
        return "retrieve_episode"

    @property
    def description(self) -> str:
        return (
            "按任务描述从情节记忆中检索相似的历史执行经历，"
            "返回历史任务的执行技能、成功率、奖励等信息。"
            "在制定计划前调用此工具可以参考历史经验，避免重复错误。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "任务描述关键词，例如 '救援 北部 人员'",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回最相似的前 k 条，默认 3",
                    "default": 3,
                },
                "success_only": {
                    "type": "boolean",
                    "description": "是否只返回成功的经历，默认 false",
                    "default": False,
                },
            },
            "required": ["query"],
        }

    def _run(
        self,
        query: str,
        top_k: int = 3,
        success_only: bool = False,
        **kwargs: Any,
    ) -> dict:
        episodes = self._em.retrieve_episode(
            query=query,
            top_k=top_k,
            success_only=success_only,
        )

        # 精简返回（去掉 episode_id 等内部字段）
        simplified = []
        for ep in episodes:
            simplified.append({
                "task":         ep.get("task", ""),
                "environment":  ep.get("environment", ""),
                "skills_used":  ep.get("skills_used", []),
                "robot":        ep.get("robot", ""),
                "success":      ep.get("success", False),
                "reward":       ep.get("reward", 0.0),
                "cost_time":    ep.get("cost_time", 0.0),
            })

        return {
            "query": query,
            "found": len(simplified),
            "episodes": simplified,
        }


class GetSkillReliabilityTool(BaseTool):
    """
    查询某技能的历史执行可靠性统计。

    LLM 调用时机：在多个技能可选时，参考成功率做出更优选择。
    """

    def __init__(self, skill_memory: SkillMemory):
        self._sm = skill_memory

    @property
    def name(self) -> str:
        return "get_skill_reliability"

    @property
    def description(self) -> str:
        return (
            "查询指定技能的历史执行可靠性，包括成功率、平均耗时、总执行次数。"
            "-1.0 的成功率表示该技能从未被执行过（无历史数据）。"
            "在多个技能方案中做选择时调用此工具。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "技能名称，例如 'fly_to'、'search_target'",
                },
                "robot_id": {
                    "type": "string",
                    "description": "可选：指定机器人 ID，返回该机器人维度的统计；不填则返回全局统计",
                },
            },
            "required": ["skill_name"],
        }

    def _run(
        self,
        skill_name: str,
        robot_id: str | None = None,
        **kwargs: Any,
    ) -> dict:
        reliability = self._sm.get_skill_reliability(
            skill_name=skill_name,
            robot_id=robot_id,
        )
        return reliability
