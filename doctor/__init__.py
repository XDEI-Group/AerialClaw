"""
doctor/ — Doctor Agent

AerialClaw 的设备接入工程师，负责：
- 诊断 adapter 合规性
- 自动修复 adapter 问题  
- 验证硬技能能正常执行
- 接入新硬件时生成 adapter 和技能
"""
from doctor.agent import DoctorAgent, get_doctor_agent

__all__ = ["DoctorAgent", "get_doctor_agent"]
