"""
doctor/tools/write_file.py — 写入 adapter 或 skill 代码（备份+语法+安全验证）
"""
from __future__ import annotations
import ast
import difflib
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_ADAPTERS_DIR = _BASE_DIR / "adapters"
_SKILLS_DIR = _BASE_DIR / "skills"
_ALLOWED_DIRS = [_ADAPTERS_DIR, _SKILLS_DIR]
_FORBIDDEN_NAMES = {"sim_adapter.py", "adapter_manager.py", "base_skill.py", "__init__.py"}
_MAX_PATCH_LINES = 120

TOOL_DEF = {
    "name": "write_file",
    "description": "写入 adapter 或 skill 代码。自动备份原文件、检查语法、验证安全性。",
    "parameters": {
        "type": "object",
        "properties": {
            "filepath": {
                "type": "string",
                "description": "相对路径，如 adapters/airsim_adapter.py",
            },
            "code": {
                "type": "string",
                "description": "完整的 Python 源码",
            },
        },
        "required": ["filepath", "code"],
    },
}


def execute(filepath: str = "", code: str = "", **kwargs) -> dict:
    """写入代码文件。"""
    if not filepath or not code:
        return {"success": False, "error": "filepath 和 code 不能为空"}

    path = (_BASE_DIR / filepath).resolve()

    # 安全检查
    allowed = any(str(path).startswith(str(d.resolve())) for d in _ALLOWED_DIRS)
    if not allowed:
        return {"success": False, "error": f"权限不足：只能写 adapters/ 和 skills/"}

    if path.name in _FORBIDDEN_NAMES:
        return {"success": False, "error": f"禁止修改: {path.name}"}

    if ".." in filepath:
        return {"success": False, "error": "路径不安全"}

    # 语法检查
    try:
        ast.parse(code)
    except SyntaxError as e:
        return {"success": False, "error": f"语法错误: {e}"}

    # adapter 文件必须继承 SimAdapter
    if "adapter" in path.name.lower() and "SimAdapter" not in code:
        return {"success": False, "error": "adapter 文件必须继承 SimAdapter"}

    # 禁止 import safety
    for line in code.splitlines():
        s = line.strip()
        if s.startswith(("import ", "from ")) and "safety" in s:
            return {"success": False, "error": f"禁止导入 safety 模块: {s}"}

    # 备份
    original_code = None
    if path.exists():
        original_code = path.read_text(encoding="utf-8")
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
        logger.info(f"备份: {path.name} -> {backup.name}")

    # 变更量检查
    diff = ""
    if original_code:
        diff_lines = list(difflib.unified_diff(
            original_code.splitlines(), code.splitlines(),
            fromfile=f"a/{path.name}", tofile=f"b/{path.name}", lineterm=""
        ))
        diff = "\n".join(diff_lines)
        changed = sum(1 for l in diff_lines if l.startswith(('+', '-')) and not l.startswith(('+++', '---')))
        if changed > _MAX_PATCH_LINES:
            return {
                "success": False,
                "error": f"变更量过大: {changed} 行 > 上限 {_MAX_PATCH_LINES} 行",
                "diff": diff,
            }

    # 写入
    try:
        path.write_text(code, encoding="utf-8")
    except Exception as e:
        return {"success": False, "error": str(e)}

    # adapter 文件写入后验证能否正常实例化（防止丢方法/重复方法）
    if "adapter" in path.name.lower():
        import subprocess, sys
        check_code = (
            "import importlib.util; "
            f"spec=importlib.util.spec_from_file_location('m', r'{path}'); "
            "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
            "cls=[v for v in vars(m).values() if isinstance(v,type) "
            "and v.__name__.endswith('Adapter') and v.__name__!='SimAdapter']; "
            "assert cls, 'no Adapter class found'; cls[0](); print('ok')"
        )
        verify = subprocess.run(
            [sys.executable, "-c", check_code],
            capture_output=True, text=True, timeout=10
        )
        if verify.returncode != 0 or "ok" not in verify.stdout:
            if original_code:
                path.write_text(original_code, encoding="utf-8")
            return {
                "success": False,
                "error": f"实例化验证失败，已自动回滚: {verify.stderr.strip()[:300]}",
            }

    return {
        "success": True,
        "filepath": filepath,
        "lines": code.count("\n") + 1,
        "diff": diff if diff else "(新文件)",
        "backed_up": original_code is not None,
        "instantiate_ok": True,
    }
