"""
doctor/tools/ — Doctor Agent 工具注册表

每个工具是一个函数，接收 dict 参数，返回 dict 结果。
工具在 agent.py 中通过 TOOL_REGISTRY 自动发现。
"""
