"""
doctor/tools/read_adapter_method.py — 读取当前 adapter 指定方法的源码

工具名: read_adapter_method
参数: method (str), include_context (int, 默认 5)
"""
from __future__ import annotations
import inspect
import logging
import textwrap
from typing import Optional

logger = logging.getLogger(__name__)

TOOL_DEF = {
    "name": "read_adapter_method",
    "description": "读取当前 adapter 中指定方法的源码。用于理解 adapter 的具体实现逻辑。",
    "parameters": {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "description": "方法名，如 'land', 'takeoff', 'fly_to_ned', 'get_state'",
            },
            "include_context": {
                "type": "integer",
                "description": "方法前后额外包含的上下文行数（默认 5）",
            },
        },
        "required": ["method"],
    },
}


def execute(method: str = "", include_context: int = 5, **kwargs) -> dict:
    """读取当前 adapter 指定方法的源码。"""
    if not method:
        return {"success": False, "error": "method 参数不能为空"}

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

    # 查找方法
    method_obj = None
    # 先在当前类查找，再向上查找 MRO
    for cls in adapter_class.__mro__:
        if method in cls.__dict__:
            method_obj = cls.__dict__[method]
            # 如果是 property，获取其 fget
            if isinstance(method_obj, property):
                method_obj = method_obj.fget
            break

    if method_obj is None:
        # 列出可用方法
        available = [
            m for m in dir(adapter)
            if not m.startswith("_") and callable(getattr(adapter, m, None))
        ]
        # 也加上 property
        for cls in adapter_class.__mro__:
            for name, val in cls.__dict__.items():
                if isinstance(val, property) and not name.startswith("_"):
                    if name not in available:
                        available.append(name)
        return {
            "success": False,
            "error": f"adapter 中未找到方法 '{method}'",
            "available_methods": sorted(available),
        }

    # 获取源码
    try:
        source_code = inspect.getsource(method_obj)
        source_lines, start_line = inspect.getsourcelines(method_obj)
        end_line = start_line + len(source_lines) - 1
    except (OSError, TypeError) as e:
        return {"success": False, "error": f"无法获取方法源码: {e}"}

    # 如果需要上下文，读取整个文件
    context_before = ""
    context_after = ""
    if include_context > 0:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
            ctx_start = max(0, start_line - 1 - include_context)
            ctx_end = min(len(all_lines), end_line + include_context)
            if ctx_start < start_line - 1:
                context_before = "".join(all_lines[ctx_start:start_line - 1])
            if ctx_end > end_line:
                context_after = "".join(all_lines[end_line:ctx_end])
        except Exception:
            pass

    return {
        "success": True,
        "file_path": file_path,
        "adapter_class": adapter_class.__name__,
        "method": method,
        "source_code": source_code,
        "start_line": start_line,
        "end_line": end_line,
        "context_before": context_before if context_before else None,
        "context_after": context_after if context_after else None,
    }
