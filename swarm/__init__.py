"""
swarm/__init__.py — AerialClaw 多机协作模块

三级架构：
    主节点 (Commander)  → 全局任务分解、区域分配、报告汇总
    子节点 (Coordinator) → 区域协调、下属无人机管理、区域报告
    无人机 (Executor)    → 单机 AerialClaw 执行，感知+决策+飞行
"""
