"""
doctor/tools/register_adapter.py — 初始化并注册 adapter
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

TOOL_DEF = {
    "name": "register_adapter",
    "description": "初始化 adapter 并连接仿真环境。类型: airsim / px4 / mock / 自定义名称",
    "parameters": {
        "type": "object",
        "properties": {
            "adapter_type": {
                "type": "string",
                "description": "adapter 类型名，如 airsim / px4 / mock",
            },
            "connection_str": {
                "type": "string",
                "description": "连接字符串，如 127.0.0.1:41451，留空用默认值",
            },
        },
        "required": ["adapter_type"],
    },
}


def execute(adapter_type: str = "", connection_str: str = "", **kwargs) -> dict:
    """初始化并连接 adapter。"""
    if not adapter_type:
        return {"success": False, "error": "adapter_type 不能为空"}

    try:
        from adapters.adapter_manager import init_adapter, get_adapter, list_adapters

        available = [a["name"] for a in list_adapters()]
        if adapter_type not in available:
            return {
                "success": False,
                "error": f"未知 adapter 类型: {adapter_type}",
                "available": available,
            }

        ok = init_adapter(adapter_type, connection_str)
        adapter = get_adapter()

        if ok:
            return {
                "success": True,
                "adapter_name": adapter.name,
                "connected": adapter.is_connected,
                "summary": f"{adapter.name} 连接成功",
            }
        else:
            return {
                "success": False,
                "adapter_name": getattr(adapter, 'name', '?'),
                "error": f"连接失败，已降级到 {getattr(adapter, 'name', 'mock')}",
            }
    except Exception as e:
        return {"success": False, "error": str(e)}
