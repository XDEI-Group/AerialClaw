"""
tools/builtin/world_query.py  —— 世界状态查询工具

提供对 WorldModel 的只读查询接口，供 LLM 在规划阶段主动调用。

工具列表：
    GetRobotStatusTool  : 查询指定机器人的实时状态（位置/电量/状态）
    GetAllRobotsTool    : 获取所有机器人的完整状态列表
    GetTargetsTool      : 获取当前所有已知目标列表
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.base_tool import BaseTool
from memory.world_model import WorldModel


class GetRobotStatusTool(BaseTool):
    """
    查询指定机器人的当前状态。

    LLM 调用时机：需要确认某台机器人是否空闲、电量是否充足、当前位置时。
    """

    def __init__(self, world_model: WorldModel):
        self._wm = world_model

    @property
    def name(self) -> str:
        return "get_robot_status"

    @property
    def description(self) -> str:
        return (
            "查询指定机器人的当前实时状态，包括：位置坐标、电量、运行状态（idle/executing/error）、"
            "传感器状态。在分配任务前调用此工具确认机器人可用性。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "robot_id": {
                    "type": "string",
                    "description": "机器人唯一 ID，例如 'UAV_1'、'UGV_1'",
                }
            },
            "required": ["robot_id"],
        }

    def _run(self, robot_id: str, **kwargs: Any) -> dict:
        state = self._wm.get_robot_state(robot_id)
        if not state:
            return {
                "found": False,
                "robot_id": robot_id,
                "message": f"机器人 '{robot_id}' 不存在于世界模型中",
            }
        return {
            "found": True,
            "robot_id": robot_id,
            **state,
        }


class GetAllRobotsTool(BaseTool):
    """
    获取所有机器人的完整状态列表。

    LLM 调用时机：需要了解当前有哪些机器人可用，或对比多台机器人状态时。
    """

    def __init__(self, world_model: WorldModel):
        self._wm = world_model

    @property
    def name(self) -> str:
        return "get_all_robots"

    @property
    def description(self) -> str:
        return (
            "获取系统中所有机器人的当前状态列表，包括每台机器人的类型、位置、电量和运行状态。"
            "用于总览可用资源，或筛选特定类型/状态的机器人。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "filter_status": {
                    "type": "string",
                    "description": "可选：按状态过滤，例如 'idle'、'executing'，不填则返回全部",
                    "enum": ["idle", "executing", "error"],
                },
                "filter_type": {
                    "type": "string",
                    "description": "可选：按机器人类型过滤，例如 'UAV'、'UGV'，不填则返回全部",
                    "enum": ["UAV", "UGV"],
                },
            },
            "required": [],
        }

    def _run(
        self,
        filter_status: str | None = None,
        filter_type: str | None = None,
        **kwargs: Any,
    ) -> dict:
        ws = self._wm.get_world_state()
        robots = ws.get("robots", {})

        result = []
        for rid, rdata in robots.items():
            if filter_status and rdata.get("status") != filter_status:
                continue
            if filter_type and rdata.get("robot_type") != filter_type:
                continue
            result.append({"robot_id": rid, **rdata})

        return {
            "total": len(result),
            "filter_status": filter_status,
            "filter_type": filter_type,
            "robots": result,
        }


class GetTargetsTool(BaseTool):
    """
    获取当前所有已知目标列表。

    LLM 调用时机：需要确认目标位置、数量或置信度时。
    """

    def __init__(self, world_model: WorldModel):
        self._wm = world_model

    @property
    def name(self) -> str:
        return "get_targets"

    @property
    def description(self) -> str:
        return (
            "获取当前世界模型中所有已知目标（人员、车辆、建筑等）的信息，"
            "包括目标 ID、标签类别、位置坐标和置信度。"
            "在制定救援或打击计划前调用此工具确认目标信息。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "label_filter": {
                    "type": "string",
                    "description": "可选：按标签过滤目标，例如 'person'、'vehicle'，不填则返回全部",
                },
                "min_confidence": {
                    "type": "number",
                    "description": "可选：最低置信度阈值 [0.0, 1.0]，不填则返回全部",
                },
            },
            "required": [],
        }

    def _run(
        self,
        label_filter: str | None = None,
        min_confidence: float | None = None,
        **kwargs: Any,
    ) -> dict:
        ws = self._wm.get_world_state()
        targets = ws.get("targets", [])

        result = []
        for t in targets:
            if label_filter and t.get("label", "").lower() != label_filter.lower():
                continue
            if min_confidence is not None and t.get("confidence", 0.0) < min_confidence:
                continue
            result.append(t)

        return {
            "total": len(result),
            "label_filter": label_filter,
            "min_confidence": min_confidence,
            "targets": result,
        }
