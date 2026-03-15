"""
core/body_sense — 实时硬件感知引擎

大脑必须时刻知道自己的身体状态。
"""

from core.body_sense.engine import BodySenseEngine
from core.body_sense.base import Monitor, MonitorReading, Alert, AlertLevel

__all__ = ["BodySenseEngine", "Monitor", "MonitorReading", "Alert", "AlertLevel"]
