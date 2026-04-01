"""
swarm/__init__.py — AerialClaw 多机/多设备协作模块

三级架构（设备无关）：
    主节点 (Commander)   → 全局任务分解、区域/分组分配、报告汇总
    子节点 (Coordinator) → 区域协调、下属设备管理、区域报告生成
    执行节点 (Executor)  → 单设备 AerialClaw 实例，感知+决策+执行

设计原则：
    - 代码不绑定任何具体设备类型（无人机、无人车、机械臂均可）
    - 设备能力通过 BODY.md / SKILLS.md / capabilities 列表描述
    - LLM 根据能力描述自主判断如何分配任务
    - 通信协议与设备类型无关
"""
