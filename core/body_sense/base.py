"""
core/body_sense/base.py — Monitor 基类 + 告警系统

每个 Monitor 独立运行，按自己的频率采样，异常立即告警。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """硬件告警"""
    level: AlertLevel
    source: str          # 哪个 monitor 产生的
    message: str
    action: str = ""     # 建议的自动动作
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    @property
    def icon(self) -> str:
        return {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.CRITICAL: "🚨",
        }[self.level]


@dataclass
class MonitorReading:
    """单次采样结果"""
    monitor_name: str
    category: str
    timestamp: float
    data: Dict[str, Any]          # 原始数据
    summary: str                   # 人类可读摘要
    alerts: List[Alert] = field(default_factory=list)
    healthy: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "monitor": self.monitor_name,
            "category": self.category,
            "timestamp": self.timestamp,
            "data": self.data,
            "summary": self.summary,
            "healthy": self.healthy,
            "alerts": [
                {"level": a.level.value, "message": a.message, "action": a.action}
                for a in self.alerts
            ],
        }


class Monitor(ABC):
    """
    硬件监控器基类。

    每个 Monitor:
    - 有自己的采样频率 (hz)
    - 独立在后台线程运行
    - 产生 MonitorReading
    - 发现异常时生成 Alert
    """

    name: str = "unnamed"
    category: str = "general"  # system / sensor / network / power / thermal
    hz: float = 1.0            # 默认 1Hz 采样

    @abstractmethod
    def probe(self) -> MonitorReading:
        """
        执行一次采样。

        Returns:
            MonitorReading: 采样结果，包含数据、摘要、告警
        """
        ...

    def available(self) -> bool:
        """当前平台是否支持此监控器，默认 True"""
        return True

    def _reading(
        self,
        data: Dict[str, Any],
        summary: str,
        alerts: Optional[List[Alert]] = None,
        healthy: bool = True,
    ) -> MonitorReading:
        """快捷创建 MonitorReading"""
        return MonitorReading(
            monitor_name=self.name,
            category=self.category,
            timestamp=time.time(),
            data=data,
            summary=summary,
            alerts=alerts or [],
            healthy=healthy,
        )

    def _alert(
        self,
        level: AlertLevel,
        message: str,
        action: str = "",
    ) -> Alert:
        """快捷创建 Alert"""
        return Alert(
            level=level,
            source=self.name,
            message=message,
            action=action,
        )
