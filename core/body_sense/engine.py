"""
core/body_sense/engine.py — BodySense 引擎

管理所有 Monitor，后台线程采样，实时汇总身体状态。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional

from core.body_sense.base import Alert, AlertLevel, Monitor, MonitorReading


class BodySenseEngine:
    """
    实时身体感知引擎。

    启动后，每个 Monitor 按自己的频率在后台采样。
    外部可随时调用 snapshot() 获取最新状态、summary() 获取文本摘要。
    """

    def __init__(self, alert_callback: Optional[Callable[[Alert], None]] = None) -> None:
        self._monitors: List[Monitor] = []
        self._latest: Dict[str, MonitorReading] = {}
        self._alerts: deque[Alert] = deque(maxlen=100)
        self._lock = threading.RLock()
        self._running = False
        self._threads: List[threading.Thread] = []
        self._alert_callback = alert_callback

    # ── 注册 ─────────────────────────────────────────────

    def register(self, monitor: Monitor) -> "BodySenseEngine":
        """注册一个监控器"""
        if monitor.available():
            self._monitors.append(monitor)
        return self

    def auto_discover(self) -> "BodySenseEngine":
        """自动发现并注册所有可用的监控器"""
        from core.body_sense.monitors.cpu import CPUMonitor
        from core.body_sense.monitors.memory import MemoryMonitor
        from core.body_sense.monitors.disk import DiskMonitor
        from core.body_sense.monitors.network import NetworkMonitor
        from core.body_sense.monitors.usb import USBMonitor
        from core.body_sense.monitors.thermal import ThermalMonitor

        all_monitors = [
            CPUMonitor(),
            MemoryMonitor(),
            DiskMonitor(),
            NetworkMonitor(),
            USBMonitor(),
            ThermalMonitor(),
        ]
        for m in all_monitors:
            self.register(m)
        return self

    # ── 生命周期 ─────────────────────────────────────────

    def start(self) -> None:
        """启动所有监控器的后台采样线程"""
        if self._running:
            return
        self._running = True

        for monitor in self._monitors:
            t = threading.Thread(
                target=self._monitor_loop,
                args=(monitor,),
                daemon=True,
                name=f"body-sense-{monitor.name}",
            )
            self._threads.append(t)
            t.start()

    def stop(self) -> None:
        """停止所有监控"""
        self._running = False
        # daemon threads will die with the process

    # ── 查询 ─────────────────────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        """
        获取最新的完整身体状态快照。

        Returns:
            {
                "timestamp": float,
                "monitors": { "cpu": {...}, "memory": {...}, ... },
                "alerts": [...],
                "healthy": bool
            }
        """
        with self._lock:
            monitors = {}
            all_healthy = True
            for name, reading in self._latest.items():
                monitors[name] = reading.to_dict()
                if not reading.healthy:
                    all_healthy = False

            return {
                "timestamp": time.time(),
                "monitors": monitors,
                "alerts": [
                    {"level": a.level.value, "source": a.source,
                     "message": a.message, "action": a.action}
                    for a in self._alerts
                ],
                "healthy": all_healthy,
                "monitor_count": len(self._monitors),
            }

    def summary(self) -> str:
        """
        生成一句话身体摘要（给 LLM 用）。

        Returns:
            "CPU 45% 10C | MEM 73% 11.8/16GB | DISK 26% 184GB free | NET ▲1.2MB/s ▼3.4MB/s | 52°C | 正常"
        """
        with self._lock:
            parts = []
            for monitor in self._monitors:
                reading = self._latest.get(monitor.name)
                if reading:
                    parts.append(reading.summary)
            
            alerts = [a for a in self._alerts if a.level == AlertLevel.CRITICAL]
            if alerts:
                parts.append(f"🚨 {len(alerts)}个严重告警")
            elif not all(r.healthy for r in self._latest.values()):
                parts.append("⚠️ 部分异常")
            else:
                parts.append("✅ 正常")

            return " | ".join(parts) if parts else "无数据"

    def get_alerts(self, level: Optional[AlertLevel] = None) -> List[Alert]:
        """获取告警列表"""
        with self._lock:
            if level:
                return [a for a in self._alerts if a.level == level]
            return list(self._alerts)

    def get_reading(self, monitor_name: str) -> Optional[MonitorReading]:
        """获取指定监控器的最新读数"""
        with self._lock:
            return self._latest.get(monitor_name)

    # ── 内部 ─────────────────────────────────────────────

    def _monitor_loop(self, monitor: Monitor) -> None:
        """单个监控器的采样循环"""
        interval = 1.0 / monitor.hz if monitor.hz > 0 else 1.0
        while self._running:
            try:
                reading = monitor.probe()
                with self._lock:
                    self._latest[monitor.name] = reading
                    for alert in reading.alerts:
                        self._alerts.append(alert)
                        if self._alert_callback:
                            try:
                                self._alert_callback(alert)
                            except Exception:
                                pass
            except Exception as e:
                # 单个监控器挂了不影响其他
                with self._lock:
                    self._latest[monitor.name] = MonitorReading(
                        monitor_name=monitor.name,
                        category=monitor.category,
                        timestamp=time.time(),
                        data={"error": str(e)},
                        summary=f"{monitor.name}: 探测异常",
                        healthy=False,
                    )
            time.sleep(interval)
