"""
monitors/disk.py — 磁盘实时监控

采样：容量、I/O 速率

告警：
- 剩余 < 10% → WARNING
- 剩余 < 5% → CRITICAL
"""

from __future__ import annotations

import time

import psutil

from core.body_sense.base import Alert, AlertLevel, Monitor, MonitorReading


def _fmt_bytes(n: int) -> str:
    if n >= 1 << 30:
        return f"{n / (1 << 30):.0f}GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.0f}MB"
    return f"{n / (1 << 10):.0f}KB"


class DiskMonitor(Monitor):
    name = "disk"
    category = "system"
    hz = 0.5  # 0.5Hz，磁盘变化慢

    def __init__(self) -> None:
        self._prev_io = None
        self._prev_time = 0.0

    def probe(self) -> MonitorReading:
        usage = psutil.disk_usage("/")

        # I/O 速率
        io = psutil.disk_io_counters()
        now = time.time()
        read_speed = 0.0
        write_speed = 0.0
        if self._prev_io and self._prev_time:
            dt = now - self._prev_time
            if dt > 0:
                read_speed = (io.read_bytes - self._prev_io.read_bytes) / dt
                write_speed = (io.write_bytes - self._prev_io.write_bytes) / dt
        self._prev_io = io
        self._prev_time = now

        data = {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "percent": usage.percent,
            "read_bytes_sec": read_speed,
            "write_bytes_sec": write_speed,
        }

        free_str = _fmt_bytes(usage.free)
        summary = f"DISK {usage.percent:.0f}% {free_str}空闲"

        if read_speed > 0 or write_speed > 0:
            r = _fmt_bytes(int(read_speed))
            w = _fmt_bytes(int(write_speed))
            summary += f" R{r}/s W{w}/s"

        alerts = []
        healthy = True

        free_pct = 100 - usage.percent
        if free_pct < 5:
            alerts.append(self._alert(
                AlertLevel.CRITICAL,
                f"磁盘空间严重不足，仅剩 {free_str}",
                "清理日志或临时文件",
            ))
            healthy = False
        elif free_pct < 10:
            alerts.append(self._alert(
                AlertLevel.WARNING,
                f"磁盘空间偏低，剩余 {free_str}",
            ))

        return self._reading(data, summary, alerts, healthy)
