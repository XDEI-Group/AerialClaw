"""
monitors/memory.py — 内存实时监控

采样：总量、已用、可用、百分比、Swap

告警：
- MEM > 85% → WARNING
- MEM > 95% → CRITICAL（系统可能 OOM）
"""

from __future__ import annotations

import psutil

from core.body_sense.base import Alert, AlertLevel, Monitor, MonitorReading


def _fmt_bytes(n: int) -> str:
    """字节转人类可读"""
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f}GB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.0f}MB"
    return f"{n / (1 << 10):.0f}KB"


class MemoryMonitor(Monitor):
    name = "memory"
    category = "system"
    hz = 2.0

    def probe(self) -> MonitorReading:
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()

        data = {
            "total_bytes": vm.total,
            "used_bytes": vm.used,
            "available_bytes": vm.available,
            "percent": vm.percent,
            "active_bytes": getattr(vm, "active", 0),
            "wired_bytes": getattr(vm, "wired", 0),
            "swap_total": swap.total,
            "swap_used": swap.used,
            "swap_percent": swap.percent,
        }

        used_gb = vm.used / (1 << 30)
        total_gb = vm.total / (1 << 30)
        summary = f"MEM {vm.percent:.0f}% {used_gb:.1f}/{total_gb:.0f}GB"

        alerts = []
        healthy = True

        if vm.percent > 95:
            alerts.append(self._alert(
                AlertLevel.CRITICAL,
                f"内存即将耗尽 {vm.percent:.0f}%，可用 {_fmt_bytes(vm.available)}",
                "释放缓存或减少并发任务",
            ))
            healthy = False
        elif vm.percent > 85:
            alerts.append(self._alert(
                AlertLevel.WARNING,
                f"内存较高 {vm.percent:.0f}%，可用 {_fmt_bytes(vm.available)}",
            ))

        return self._reading(data, summary, alerts, healthy)
