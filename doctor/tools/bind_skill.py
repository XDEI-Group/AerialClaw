"""
doctor/tools/bind_skill.py — 绑定技能到设备
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

TOOL_DEF = {
    "name": "bind_skill",
    "description": "将技能绑定到当前设备。通过 SkillBinder 匹配设备能力和技能。",
    "parameters": {
        "type": "object",
        "properties": {
            "device_id": {
                "type": "string",
                "description": "设备 ID，如 drone_1",
            },
            "capabilities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "设备能力列表，如 [\"fly\", \"camera\", \"lidar\"]",
            },
            "device_type": {
                "type": "string",
                "description": "设备类型: UAV / GROUND_VEHICLE / ARM / CUSTOM",
            },
        },
        "required": ["device_id", "capabilities"],
    },
}


def execute(
    device_id: str = "",
    capabilities: list = None,
    device_type: str = "UAV",
    **kwargs,
) -> dict:
    """绑定技能到设备。"""
    if not device_id:
        return {"success": False, "error": "device_id 不能为空"}
    if not capabilities:
        return {"success": False, "error": "capabilities 不能为空"}

    try:
        from core.skill_binder import SkillBinder
        binder = SkillBinder()
        binding = binder.bind(device_id, capabilities, device_type)
        info = binding.to_dict()
        return {
            "success": True,
            "device_id": device_id,
            "motor_skills": info["motor"],
            "perception_skills": info["perception"],
            "cognitive_skills": info["cognitive"],
            "soft_skills": info["soft"],
            "total": info["total"],
            "summary": f"设备 {device_id} 已绑定 {info['total']} 个技能",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
