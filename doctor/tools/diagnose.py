"""
doctor/tools/diagnose.py — 运行 adapter 合规检查
"""
from __future__ import annotations
import inspect
import logging
from typing import Optional

logger = logging.getLogger(__name__)

TOOL_DEF = {
    "name": "diagnose",
    "description": "运行 adapter 合规检查（连接/状态/飞行状态/指令接口），返回分数和问题列表",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}


def execute(**kwargs) -> dict:
    """运行 4 项 adapter 合规检查。"""
    from core.doctor_checks.adapter import (
        AdapterConnectionCheck, AdapterStateCheck,
        AdapterFlightStateCheck, AdapterCommandCheck,
    )
    from adapters.adapter_manager import get_adapter

    adapter = get_adapter()
    adapter_name = getattr(adapter, 'name', 'none') if adapter else 'none'
    adapter_file = None
    if adapter:
        try:
            adapter_file = inspect.getfile(type(adapter))
        except (TypeError, OSError):
            pass

    checks = [
        AdapterConnectionCheck(),
        AdapterStateCheck(),
        AdapterFlightStateCheck(),
        AdapterCommandCheck(),
    ]
    issues, passed = [], []
    for check in checks:
        try:
            result = check.check()
            entry = {
                "name": result.name,
                "status": result.status,
                "message": result.message,
                "fix_hint": result.fix_hint,
            }
            if result.status in ("fail", "warn"):
                issues.append(entry)
            else:
                passed.append(entry)
        except Exception as e:
            issues.append({
                "name": check.name, "status": "fail",
                "message": f"检查异常: {e}", "fix_hint": "",
            })

    total = len(issues) + len(passed)
    score = round(len(passed) / total * 100) if total > 0 else 0

    return {
        "success": True,
        "adapter_name": adapter_name,
        "adapter_file": adapter_file,
        "score": score,
        "issues": issues,
        "passed": passed,
        "summary": f"{adapter_name}: {score}/100, {len(passed)}通过 {len(issues)}问题",
    }
