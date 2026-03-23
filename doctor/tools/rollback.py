"""
doctor/tools/rollback.py — 回滚代码到备份版本
"""
from __future__ import annotations
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent

TOOL_DEF = {
    "name": "rollback",
    "description": "回滚文件到 .bak 备份版本",
    "parameters": {
        "type": "object",
        "properties": {
            "filepath": {
                "type": "string",
                "description": "要回滚的文件路径，如 adapters/airsim_adapter.py",
            },
        },
        "required": ["filepath"],
    },
}


def execute(filepath: str = "", **kwargs) -> dict:
    """回滚到备份。"""
    if not filepath:
        return {"success": False, "error": "filepath 不能为空"}

    target = (_BASE_DIR / filepath).resolve()
    backup = target.with_suffix(target.suffix + ".bak")

    if not backup.exists():
        return {"success": False, "error": f"备份文件不存在: {backup.name}"}

    try:
        shutil.copy2(backup, target)
        return {"success": True, "filepath": filepath, "summary": f"已回滚 {target.name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
