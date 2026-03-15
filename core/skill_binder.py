"""
core/skill_binder.py — 技能动态绑定

设备接入时自动匹配技能子集，退出时挂起。

流程：
  设备接入 → 读取档案 → 从四层技能中选匹配的 → 绑定到设备
  设备退出 → 绑定的技能标记挂起 → 经验保留
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from core.logger import get_logger

logger = get_logger(__name__)


# 能力到技能的映射表
_CAPABILITY_SKILL_MAP = {
    # 运动层
    "fly": ["takeoff", "land", "fly_to", "fly_relative", "hover",
            "change_altitude", "return_to_launch"],
    "drive": ["move_to", "stop", "turn"],
    "grab": ["grab", "release"],

    # 感知层
    "camera": ["detect_object", "observe", "look_around"],
    "lidar": ["scan_area", "fuse_perception"],
    "gps": ["get_position"],
    "accelerometer": ["get_sensor_data"],

    # 通用
    "screen": ["screenshot"],
}

# 所有设备都有的认知技能
_UNIVERSAL_COGNITIVE = ["run_python", "http_request", "read_file", "write_file"]
_UNIVERSAL_STATUS = ["get_status", "get_battery", "get_position"]


class SkillBinding:
    """单个设备的技能绑定记录"""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self.motor: List[str] = []
        self.perception: List[str] = []
        self.cognitive: List[str] = list(_UNIVERSAL_COGNITIVE)
        self.soft: List[str] = []
        self.status: str = "active"  # active / suspended

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "status": self.status,
            "motor": self.motor,
            "perception": self.perception,
            "cognitive": self.cognitive,
            "soft": self.soft,
            "total": len(self.motor) + len(self.perception) + len(self.cognitive) + len(self.soft),
        }


class SkillBinder:
    """
    技能动态绑定管理器。

    根据设备能力自动匹配技能，设备退出时挂起。
    """

    def __init__(self) -> None:
        self._bindings: Dict[str, SkillBinding] = {}

    def bind(self, device_id: str, capabilities: List[str],
             device_type: str = "CUSTOM") -> SkillBinding:
        """
        为设备匹配并绑定技能。

        Args:
            device_id: 设备 ID
            capabilities: 设备能力列表
            device_type: 设备类型

        Returns:
            SkillBinding: 绑定记录
        """
        binding = SkillBinding(device_id)

        # 根据能力匹配技能
        matched = set()
        for cap in capabilities:
            cap_lower = cap.lower()
            skills = _CAPABILITY_SKILL_MAP.get(cap_lower, [])
            matched.update(skills)

        # 加上通用状态技能
        matched.update(_UNIVERSAL_STATUS)

        # 分类到四层
        motor_skills = {"takeoff", "land", "fly_to", "fly_relative", "hover",
                        "change_altitude", "return_to_launch", "move_to", "stop",
                        "turn", "grab", "release"}
        perception_skills = {"detect_object", "observe", "look_around", "scan_area",
                             "fuse_perception", "get_sensor_data", "screenshot"}
        status_skills = {"get_status", "get_battery", "get_position"}

        binding.motor = sorted(matched & motor_skills)
        binding.perception = sorted(matched & (perception_skills | status_skills))

        # 软技能根据设备类型推荐
        if device_type == "UAV":
            binding.soft = ["search_target", "patrol_area", "rescue_person"]
        elif device_type == "PHONE":
            binding.soft = []
        else:
            binding.soft = []

        self._bindings[device_id] = binding
        logger.info(
            "技能绑定 [%s]: motor=%d perception=%d cognitive=%d soft=%d",
            device_id, len(binding.motor), len(binding.perception),
            len(binding.cognitive), len(binding.soft),
        )
        return binding

    def suspend(self, device_id: str) -> Optional[SkillBinding]:
        """
        设备退出时挂起绑定（不删除，保留经验）。

        Returns:
            挂起的绑定记录，不存在返回 None
        """
        binding = self._bindings.get(device_id)
        if binding:
            binding.status = "suspended"
            logger.info("技能挂起 [%s]: %d 个技能已暂停", device_id, binding.to_dict()["total"])
        return binding

    def resume(self, device_id: str) -> Optional[SkillBinding]:
        """设备重新接入时恢复绑定"""
        binding = self._bindings.get(device_id)
        if binding:
            binding.status = "active"
            logger.info("技能恢复 [%s]", device_id)
        return binding

    def get_binding(self, device_id: str) -> Optional[SkillBinding]:
        """获取设备的技能绑定"""
        return self._bindings.get(device_id)

    def get_all_bindings(self) -> Dict[str, Dict]:
        """获取所有绑定"""
        return {did: b.to_dict() for did, b in self._bindings.items()}

    def remove(self, device_id: str) -> None:
        """彻底移除绑定"""
        self._bindings.pop(device_id, None)
