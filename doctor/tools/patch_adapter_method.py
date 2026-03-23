"""
doctor/tools/patch_adapter_method.py — 安全地 patch adapter 方法

工具名: patch_adapter_method
参数: method (str), new_code (str), reason (str)
安全约束：路径白名单、自动备份、行数限制、语法检查+自动回滚
"""
from __future__ import annotations
import inspect
import logging
import os
import py_compile
import shutil
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_BACKUP_DIR = Path(__file__).resolve().parent.parent / "memory" / "backups"

TOOL_DEF = {
    "name": "patch_adapter_method",
    "description": (
        "安全地 patch 当前 adapter 中的指定方法。"
        "自动备份、语法检查，失败自动回滚。仅允许修改 adapters/ 目录下的 .py 文件。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "description": "要 patch 的方法名，如 'land', 'get_state'",
            },
            "new_code": {
                "type": "string",
                "description": "新的方法代码（完整的 def ... 定义）",
            },
            "reason": {
                "type": "string",
                "description": "修改原因说明",
            },
        },
        "required": ["method", "new_code", "reason"],
    },
}

_MAX_PATCH_LINES = 80


def execute(method: str = "", new_code: str = "", reason: str = "", **kwargs) -> dict:
    """安全 patch adapter 方法。"""
    if not method or not new_code or not reason:
        return {"success": False, "error": "method, new_code, reason 均不能为空"}

    # 行数检查
    new_lines = new_code.strip().split("\n")
    if len(new_lines) > _MAX_PATCH_LINES:
        return {
            "success": False,
            "error": f"new_code 超过 {_MAX_PATCH_LINES} 行限制（当前 {len(new_lines)} 行），请拆分修改",
        }

    from adapters.adapter_manager import get_adapter

    adapter = get_adapter()
    if adapter is None:
        return {"success": False, "error": "当前没有活跃的 adapter"}

    adapter_class = type(adapter)

    # 获取 adapter 源码文件路径
    try:
        file_path = inspect.getfile(adapter_class)
    except (TypeError, OSError) as e:
        return {"success": False, "error": f"无法获取 adapter 源码文件: {e}"}

    file_path = Path(file_path).resolve()

    # 路径白名单检查：只允许 adapters/ 目录下的 .py 文件
    adapters_dir = (_BASE_DIR / "adapters").resolve()
    if not str(file_path).startswith(str(adapters_dir)):
        return {
            "success": False,
            "error": f"安全拒绝: 只允许修改 adapters/ 目录下的文件，当前文件: {file_path}",
        }
    if not file_path.suffix == ".py":
        return {"success": False, "error": f"只允许修改 .py 文件: {file_path}"}

    # 查找方法在源码中的位置
    method_obj = None
    for cls in adapter_class.__mro__:
        if method in cls.__dict__:
            method_obj = cls.__dict__[method]
            if isinstance(method_obj, property):
                method_obj = method_obj.fget
            # 确认方法确实定义在目标文件中
            try:
                method_file = Path(inspect.getfile(method_obj)).resolve()
                if method_file == file_path:
                    break
            except (TypeError, OSError):
                pass
            method_obj = None

    if method_obj is None:
        return {"success": False, "error": f"在 adapter 文件中未找到方法 '{method}'"}

    try:
        source_lines, start_line = inspect.getsourcelines(method_obj)
        end_line = start_line + len(source_lines) - 1
    except (OSError, TypeError) as e:
        return {"success": False, "error": f"无法获取方法源码位置: {e}"}

    # 读取整个文件
    original_content = file_path.read_text(encoding="utf-8")
    all_lines = original_content.split("\n")

    # 备份到 doctor/memory/backups/
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{file_path.stem}_{timestamp}.py"
    backup_path = _BACKUP_DIR / backup_name
    shutil.copy2(file_path, backup_path)
    logger.info(f"备份: {file_path.name} -> {backup_path}")

    # 计算缩进：保持与原方法相同的缩进
    original_indent = ""
    for ch in source_lines[0]:
        if ch in (" ", "\t"):
            original_indent += ch
        else:
            break

    # 确保 new_code 使用正确的缩进
    new_code_lines = new_code.strip().split("\n")
    # 检测 new_code 的缩进
    new_indent = ""
    for ch in new_code_lines[0]:
        if ch in (" ", "\t"):
            new_indent += ch
        else:
            break

    # 如果 new_code 没有缩进但原始方法有缩进，则添加缩进
    if original_indent and not new_indent:
        new_code_lines = [original_indent + line if line.strip() else line for line in new_code_lines]
    elif original_indent != new_indent:
        # 替换缩进
        adjusted = []
        for line in new_code_lines:
            if line.strip():
                # 移除旧缩进，添加新缩进
                stripped = line.lstrip()
                extra_indent = len(line) - len(stripped) - len(new_indent)
                if extra_indent < 0:
                    extra_indent = 0
                adjusted.append(original_indent + " " * extra_indent + stripped)
            else:
                adjusted.append("")
        new_code_lines = adjusted

    # 替换源码中的方法
    # all_lines 是 0-indexed, start_line/end_line 是 1-indexed
    new_all_lines = (
        all_lines[:start_line - 1]
        + new_code_lines
        + all_lines[end_line:]
    )
    new_content = "\n".join(new_all_lines)

    # 写入
    file_path.write_text(new_content, encoding="utf-8")

    # py_compile 语法检查
    syntax_ok = True
    try:
        py_compile.compile(str(file_path), doraise=True)
    except py_compile.PyCompileError as e:
        syntax_ok = False
        logger.error(f"语法检查失败，自动回滚: {e}")
        # 从备份恢复
        shutil.copy2(backup_path, file_path)
        return {
            "success": False,
            "error": f"语法检查失败，已自动从备份恢复: {e}",
            "backup_path": str(backup_path),
            "syntax_ok": False,
        }

    lines_changed = abs(len(new_code_lines) - len(source_lines))

    # 实例化验证：确保改完后 adapter 还能正常实例化（防止丢方法等问题）
    import subprocess, sys
    verify_cmd = [
        sys.executable, "-c",
        f"import importlib.util, sys; spec = importlib.util.spec_from_file_location('m', r''{file_path}''); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); cls = [v for v in vars(m).values() if isinstance(v, type) and v.__name__.endswith('Adapter') and v.__name__ != 'SimAdapter'][0]; cls(); print('ok')"
    ]
    result = subprocess.run(verify_cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0 or 'ok' not in result.stdout:
        logger.error(f"实例化验证失败，自动回滚: {result.stderr.strip()}")
        shutil.copy2(backup_path, file_path)
        return {
            "success": False,
            "error": f"实例化验证失败，已自动从备份恢复: {result.stderr.strip()[:300]}",
            "backup_path": str(backup_path),
        }

    return {
        "success": True,
        "file_path": str(file_path),
        "method": method,
        "backup_path": str(backup_path),
        "original_lines": f"{start_line}-{end_line} ({len(source_lines)} lines)",
        "new_lines": len(new_code_lines),
        "lines_changed": lines_changed,
        "syntax_ok": True,
        "instantiate_ok": True,
        "reason": reason,
    }
