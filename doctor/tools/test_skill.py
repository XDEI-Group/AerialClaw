"""
doctor/tools/test_skill.py — 执行硬技能验证
"""
from __future__ import annotations
import logging
import traceback

logger = logging.getLogger(__name__)

TOOL_DEF = {
    "name": "test_skill",
    "description": "执行一个硬技能并返回结果。用于验证 adapter 接入是否正确。",
    "parameters": {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "技能名: get_position / get_battery / takeoff / land / hover / fly_to / return_to_launch",
            },
            "params": {
                "type": "object",
                "description": "技能参数，如 {\"altitude\": 5.0}",
            },
        },
        "required": ["skill_name"],
    },
}


def execute(skill_name: str = "", params: dict = None, **kwargs) -> dict:
    """执行硬技能。"""
    if not skill_name:
        return {"success": False, "error": "skill_name 不能为空"}

    if params is None:
        params = {}

    # 检查 adapter
    try:
        from adapters.adapter_manager import get_adapter
        adapter = get_adapter()
        if not adapter:
            return {"success": False, "error": "adapter 未初始化，先调用 register_adapter"}
        if not adapter.is_connected:
            return {"success": False, "error": f"adapter {adapter.name} 未连接"}
    except Exception as e:
        return {"success": False, "error": f"adapter 检查失败: {e}"}

    # 查找技能
    try:
        from skills.skill_loader import get_skill_by_name
        skill = get_skill_by_name(skill_name)
    except (ImportError, AttributeError):
        skill = _find_skill_manual(skill_name)

    if skill is None:
        return {
            "success": False,
            "error": f"技能不存在: {skill_name}",
            "available": _list_available_skills(),
        }

    # 执行
    try:
        result = skill.execute(params)
        return {
            "success": result.success,
            "output": result.output,
            "error": result.error_msg if not result.success else None,
            "logs": result.logs,
            "cost_time": result.cost_time,
        }
    except Exception as e:
        tb = traceback.format_exc()
        return {
            "success": False,
            "error": str(e),
            "traceback": tb,
        }


def _find_skill_manual(skill_name: str):
    """手动查找技能类。"""
    try:
        from skills import motor_skills
        skill_map = {
            "takeoff": motor_skills.Takeoff,
            "land": motor_skills.Land,
            "fly_to": motor_skills.FlyTo,
            "hover": motor_skills.Hover,
            "get_position": motor_skills.GetPosition,
            "get_battery": motor_skills.GetBattery,
            "return_to_launch": motor_skills.ReturnToLaunch,
            "change_altitude": motor_skills.ChangeAltitude,
            "fly_relative": motor_skills.FlyRelative,
            "look_around": motor_skills.LookAround,
            "mark_location": motor_skills.MarkLocation,
            "get_marks": motor_skills.GetMarks,
        }
        cls = skill_map.get(skill_name)
        return cls() if cls else None
    except Exception:
        return None


def _list_available_skills() -> list:
    """列出可用技能。"""
    try:
        from skills import motor_skills
        import inspect
        from skills.base_skill import Skill
        skills = []
        for name, obj in inspect.getmembers(motor_skills, inspect.isclass):
            if issubclass(obj, Skill) and obj is not Skill:
                skills.append(getattr(obj, 'name', name))
        return skills
    except Exception:
        return []
