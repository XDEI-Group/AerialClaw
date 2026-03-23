"""
adapters/contracts.py — Adapter 行为契约定义
"""

ADAPTER_CONTRACTS = {
    "land": {
        "description": "降落指令",
        "postconditions": [
            {"check": "in_air == False", "tolerance": None},
        ],
        "timeout": 35.0,
    },
    "takeoff": {
        "description": "起飞指令",
        "postconditions": [
            {"check": "in_air == True", "tolerance": None},
            {"check": "z < -0.8", "tolerance": None},
        ],
        "timeout": 20.0,
    },
    "get_state": {
        "description": "获取状态",
        "postconditions": [
            {"check": "result is not None", "tolerance": None},
            {"check": "isinstance(in_air, bool)", "tolerance": None},
        ],
        "timeout": 5.0,
    },
    "fly_to_ned": {
        "description": "飞到指定 NED 坐标",
        "postconditions": [
            {"check": "result is not None", "tolerance": None},
        ],
        "timeout": 60.0,
    },
    "hover": {
        "description": "悬停",
        "postconditions": [
            {"check": "result is not None", "tolerance": None},
        ],
        "timeout": 10.0,
    },
    "is_in_air": {
        "description": "查询是否在空中",
        "postconditions": [
            {"check": "isinstance(result, bool)", "tolerance": None},
        ],
        "timeout": 5.0,
    },
    "connect": {
        "description": "连接设备",
        "postconditions": [
            {"check": "result == True", "tolerance": None},
        ],
        "timeout": 15.0,
    },
    "is_armed": {
        "description": "查询是否 armed",
        "postconditions": [
            {"check": "isinstance(result, bool)", "tolerance": None},
        ],
        "timeout": 5.0,
    },
}
