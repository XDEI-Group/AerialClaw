"""
world_model.py
世界模型模块：维护共享环境状态表示（Shared Environment Representation）。

职责：
    - 存储并更新机器人位置、目标位置、地图信息
    - 向 Brain 模块提供压缩的世界状态快照
    - 支持多机器人状态并行维护

Functions:
    update_world_state(update)  - 更新世界状态
    get_world_state()           - 获取当前完整世界状态

world_state 数据结构：
    {
        "robots": {
            "<robot_id>": {
                "robot_type": str,       # "UAV" | "UGV"
                "position": [x, y, z],
                "battery": float,        # 0-100
                "status": str,           # "idle" | "executing" | "error"
                "sensor_status": dict
            }
        },
        "targets": [
            {
                "target_id": str,
                "label": str,
                "position": [x, y, z],
                "confidence": float
            }
        ],
        "map": {
            "obstacles": list,
            "free_zones": list,
            "search_areas": list
        },
        "timestamp": float
    }
"""

import time
import copy
from typing import Any


class WorldModel:
    """
    共享世界模型。
    维护系统全局环境状态，供 Brain 模块做决策，供 Memory 模块做持久化。

    未来升级方向：
        - Neural World Model（神经网络隐状态世界模型）
        - 3D Scene Graph Memory
    """

    def __init__(self):
        self._state: dict = {
            "robots": {},
            "targets": [],
            "map": {
                "obstacles": [],
                "free_zones": [],
                "search_areas": [],
            },
            "timestamp": time.time(),
        }

    def update_world_state(self, update: dict) -> None:
        """
        增量更新世界状态。

        update 可包含以下任意字段：
            - robots: dict  ->  合并到 state["robots"]（按 robot_id 覆盖/新增）
            - targets: list ->  完全替换 state["targets"]
            - map: dict     ->  合并到 state["map"]（按子键覆盖）
            - 感知反馈中的 "objects": list -> 同步到 targets

        Args:
            update: 部分状态更新字典

        Example:
            update = {
                "robots": {
                    "UAV_1": {"position": [10, 20, 30], "battery": 85}
                }
            }
        """
        if "robots" in update:
            for robot_id, robot_data in update["robots"].items():
                if robot_id not in self._state["robots"]:
                    self._state["robots"][robot_id] = {}
                self._state["robots"][robot_id].update(robot_data)

        if "targets" in update:
            self._state["targets"] = update["targets"]

        if "map" in update:
            for key, value in update["map"].items():
                self._state["map"][key] = value

        # 支持感知数据直接更新目标列表
        if "objects" in update:
            for obj in update["objects"]:
                target_id = obj.get("target_id", obj.get("label", "unknown"))
                # 若目标已存在则更新，否则追加
                existing = next(
                    (t for t in self._state["targets"] if t.get("target_id") == target_id),
                    None,
                )
                if existing:
                    existing.update(obj)
                else:
                    if "target_id" not in obj:
                        obj["target_id"] = target_id
                    self._state["targets"].append(obj)

        self._state["timestamp"] = time.time()

    def get_world_state(self) -> dict:
        """
        获取当前完整世界状态快照（深拷贝，避免外部修改）。

        Returns:
            dict: 当前世界状态
        """
        return copy.deepcopy(self._state)

    def get_robot_state(self, robot_id: str) -> dict:
        """
        获取指定机器人的状态。

        Args:
            robot_id: 机器人 ID，例如 "UAV_1"

        Returns:
            dict: 机器人状态，若不存在返回空字典
        """
        return copy.deepcopy(self._state["robots"].get(robot_id, {}))

    def register_robot(
        self,
        robot_id: str,
        robot_type: str,
        initial_position: list | None = None,
        battery: float = 100.0,
    ) -> None:
        """
        注册一个新机器人到世界模型。

        Args:
            robot_id:          机器人唯一 ID
            robot_type:        机器人类型，"UAV" 或 "UGV"
            initial_position:  初始位置，默认 [0, 0, 0]
            battery:           初始电量，默认 100.0
        """
        if initial_position is None:
            initial_position = [0, 0, 0]

        self._state["robots"][robot_id] = {
            "robot_type": robot_type,
            "position": initial_position,
            "battery": battery,
            "status": "idle",
            "sensor_status": {
                "lidar": True,
                "camera": True,
                "microphone": True,
            },
        }
        self._state["timestamp"] = time.time()

    def get_idle_robots(self) -> list[str]:
        """
        返回所有处于空闲状态的机器人 ID 列表。

        Returns:
            list[str]: 空闲机器人 ID 列表
        """
        return [
            rid for rid, rdata in self._state["robots"].items()
            if rdata.get("status", "idle") == "idle"
        ]

    def get_robots_by_type(self, robot_type: str) -> list[str]:
        """
        按类型过滤机器人。

        Args:
            robot_type: "UAV" 或 "UGV"

        Returns:
            list[str]: 匹配类型的机器人 ID 列表
        """
        return [
            rid for rid, rdata in self._state["robots"].items()
            if rdata.get("robot_type", "") == robot_type
        ]

    def __repr__(self):
        n_robots = len(self._state["robots"])
        n_targets = len(self._state["targets"])
        return f"<WorldModel robots={n_robots} targets={n_targets}>"
