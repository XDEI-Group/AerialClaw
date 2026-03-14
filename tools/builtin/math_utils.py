"""
tools/builtin/math_utils.py  —— 数学计算工具

提供机器人场景下常用的空间计算工具。

工具列表：
    CalculateDistanceTool  : 计算两点之间的欧氏距离（支持 2D / 3D）
    FindNearestRobotTool   : 从机器人列表中找到距目标位置最近的机器人
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.base_tool import BaseTool
from memory.world_model import WorldModel


class CalculateDistanceTool(BaseTool):
    """
    计算两个坐标点之间的欧氏距离。

    LLM 调用时机：评估机器人到达目标的代价、比较多条路径时。
    """

    @property
    def name(self) -> str:
        return "calculate_distance"

    @property
    def description(self) -> str:
        return (
            "计算两个坐标点之间的欧氏距离。支持 2D（[x, y]）和 3D（[x, y, z]）坐标。"
            "用于评估机器人到目标的距离，辅助任务分配决策。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "point_a": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "起点坐标 [x, y] 或 [x, y, z]",
                },
                "point_b": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "终点坐标 [x, y] 或 [x, y, z]",
                },
            },
            "required": ["point_a", "point_b"],
        }

    def _run(
        self,
        point_a: list[float],
        point_b: list[float],
        **kwargs: Any,
    ) -> dict:
        if len(point_a) != len(point_b):
            raise ValueError(
                f"坐标维度不匹配：point_a={len(point_a)}D, point_b={len(point_b)}D"
            )
        if len(point_a) not in (2, 3):
            raise ValueError(f"只支持 2D 或 3D 坐标，收到 {len(point_a)}D")

        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(point_a, point_b)))
        return {
            "point_a": point_a,
            "point_b": point_b,
            "distance": round(dist, 4),
            "unit": "meters",
        }


class FindNearestRobotTool(BaseTool):
    """
    从世界模型中找到距目标位置最近的（可用）机器人。

    LLM 调用时机：需要将任务分配给距目标最近的机器人以提升效率时。
    """

    def __init__(self, world_model: WorldModel):
        self._wm = world_model

    @property
    def name(self) -> str:
        return "find_nearest_robot"

    @property
    def description(self) -> str:
        return (
            "在世界模型中查找距给定目标位置最近的空闲机器人。"
            "可按机器人类型（UAV/UGV）过滤。"
            "返回最近机器人的 ID、距离和当前位置。"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target_position": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "目标位置坐标 [x, y] 或 [x, y, z]",
                },
                "robot_type": {
                    "type": "string",
                    "description": "可选：只在指定类型中搜索，'UAV' 或 'UGV'，不填则搜索所有类型",
                    "enum": ["UAV", "UGV"],
                },
                "status_filter": {
                    "type": "string",
                    "description": "可选：只在指定状态中搜索，默认只搜索 'idle' 状态",
                    "enum": ["idle", "executing", "any"],
                    "default": "idle",
                },
            },
            "required": ["target_position"],
        }

    def _run(
        self,
        target_position: list[float],
        robot_type: str | None = None,
        status_filter: str = "idle",
        **kwargs: Any,
    ) -> dict:
        ws = self._wm.get_world_state()
        robots = ws.get("robots", {})

        candidates = []
        for rid, rdata in robots.items():
            # 类型过滤
            if robot_type and rdata.get("robot_type") != robot_type:
                continue
            # 状态过滤
            if status_filter != "any" and rdata.get("status") != status_filter:
                continue

            pos = rdata.get("position", [0, 0, 0])
            # 对齐维度
            n = min(len(target_position), len(pos))
            dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(target_position[:n], pos[:n])))
            candidates.append({
                "robot_id":    rid,
                "robot_type":  rdata.get("robot_type"),
                "status":      rdata.get("status"),
                "battery":     rdata.get("battery"),
                "position":    pos,
                "distance":    round(dist, 4),
            })

        if not candidates:
            return {
                "found": False,
                "message": (
                    f"未找到可用机器人"
                    f"（类型={robot_type or '任意'}, 状态={status_filter}）"
                ),
                "nearest": None,
                "all_candidates": [],
            }

        candidates.sort(key=lambda x: x["distance"])
        nearest = candidates[0]

        return {
            "found":          True,
            "target_position": target_position,
            "nearest":        nearest,
            "all_candidates": candidates,
        }
