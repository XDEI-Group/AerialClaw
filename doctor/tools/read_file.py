"""
doctor/tools/read_file.py — 读取 adapter 或 skill 源码
"""
from __future__ import annotations
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_ALLOWED_DIRS = [
    _BASE_DIR / "adapters",
    _BASE_DIR / "skills",
]

TOOL_DEF = {
    "name": "read_file",
    "description": "读取 adapter 或 skill 的源码文件，返回文件内容",
    "parameters": {
        "type": "object",
        "properties": {
            "filepath": {
                "type": "string",
                "description": "相对路径，如 adapters/airsim_adapter.py 或 skills/motor_skills.py",
            },
        },
        "required": ["filepath"],
    },
}


def execute(filepath: str = "", **kwargs) -> dict:
    """读取源码文件。"""
    if not filepath:
        return {"success": False, "error": "filepath 不能为空"}

    path = (_BASE_DIR / filepath).resolve()

    # 安全检查：只允许读 adapters/ 和 skills/
    allowed = any(str(path).startswith(str(d.resolve())) for d in _ALLOWED_DIRS)
    if not allowed:
        return {"success": False, "error": f"权限不足：只能读取 adapters/ 和 skills/ 下的文件"}

    if not path.exists():
        # 列出目录下可用文件
        parent = path.parent
        if parent.exists():
            available = [f.name for f in parent.glob("*.py") if not f.name.startswith("__")]
            return {"success": False, "error": f"文件不存在: {filepath}", "available": available}
        return {"success": False, "error": f"文件不存在: {filepath}"}

    try:
        code = path.read_text(encoding="utf-8")
        return {
            "success": True,
            "filepath": filepath,
            "code": code,
            "lines": code.count("\n") + 1,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
