"""
doctor/tools/run_contract.py — 运行 Adapter 行为契约测试

工具名: run_contract_test
参数: method (str) — 方法名，传 'all' 则执行所有契约测试
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

TOOL_DEF = {
    "name": "run_contract_test",
    "description": "运行 adapter 行为契约测试。指定方法名测试单个契约，传 'all' 测试所有契约。返回结构化的通过/违规结果。",
    "parameters": {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "description": "要测试的方法名（如 'land', 'takeoff', 'get_state'），传 'all' 执行全部契约",
            },
        },
        "required": ["method"],
    },
}


def execute(method: str = "all", **kwargs) -> dict:
    """执行契约测试。"""
    from adapters.adapter_manager import get_adapter
    from adapters.contract_runner import ContractRunner

    adapter = get_adapter()
    if adapter is None:
        return {
            "success": False,
            "error": "当前没有活跃的 adapter，请先初始化 adapter",
        }

    runner = ContractRunner()

    try:
        if method == "all":
            result = runner.run_all_contracts(adapter)
            return {
                "success": True,
                "mode": "all",
                "adapter_name": getattr(adapter, "name", "unknown"),
                **result,
            }
        else:
            result = runner.run_contract(adapter, method)
            return {
                "success": result["success"],
                "mode": "single",
                "adapter_name": getattr(adapter, "name", "unknown"),
                **result,
            }
    except Exception as e:
        logger.exception("契约测试异常")
        return {
            "success": False,
            "error": f"契约测试异常: {e}",
        }
