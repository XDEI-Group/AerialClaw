"""
monitors/cpu.py — CPU 实时监控

采样内容：
- 总使用率 + 每核使用率
- 频率
- 核心数（性能核 + 效率核）
- 负载均值

告警：
- CPU > 90% 持续 → WARNING
- CPU > 95% 持续 → CRITICAL
"""

from __future__ import annotations

import subprocess

import psutil

from core.body_sense.base import Alert, AlertLevel, Monitor, MonitorReading


def _get_apple_silicon_info() -> dict:
    """获取 Apple Silicon 的 CPU 信息（sysctl）"""
    info = {}
    try:
        # 性能核数
        out = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "hw.perflevel0.logicalcpu"],
            capture_output=True, text=True, timeout=1,
        )
        if out.returncode == 0:
            info["p_cores"] = int(out.stdout.strip())
        # 效率核数
        out = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "hw.perflevel1.logicalcpu"],
            capture_output=True, text=True, timeout=1,
        )
        if out.returncode == 0:
            info["e_cores"] = int(out.stdout.strip())
    except Exception:
        pass
    return info


class CPUMonitor(Monitor):
    name = "cpu"
    category = "system"
    hz = 2.0  # 2Hz 采样

    def __init__(self) -> None:
        self._high_count = 0
        self._apple_info = _get_apple_silicon_info()

    def probe(self) -> MonitorReading:
        total = psutil.cpu_percent(interval=0)
        per_cpu = psutil.cpu_percent(interval=0, percpu=True)
        freq = psutil.cpu_freq()
        count = psutil.cpu_count()
        count_phys = psutil.cpu_count(logical=False) or count
        load_1, load_5, load_15 = psutil.getloadavg()

        # Apple Silicon: psutil 频率不可靠，用 sysctl
        freq_ghz = round(freq.current / 1000, 2) if freq and freq.current > 100 else 0
        if freq_ghz == 0:
            # Apple Silicon M 系列通常不暴露实时频率
            freq_ghz = 0  # 不显示，避免误导

        p_cores = self._apple_info.get("p_cores", 0)
        e_cores = self._apple_info.get("e_cores", 0)

        data = {
            "total_percent": total,
            "per_cpu_percent": per_cpu,
            "frequency_ghz": freq_ghz,
            "cores_total": count,
            "cores_physical": count_phys,
            "p_cores": p_cores,
            "e_cores": e_cores,
            "load_1m": round(load_1, 2),
            "load_5m": round(load_5, 2),
            "load_15m": round(load_15, 2),
        }

        core_str = f"{p_cores}P+{e_cores}E" if p_cores else f"{count}C"
        summary = f"CPU {total:.0f}% {core_str} load:{load_1:.1f}"

        alerts = []
        healthy = True

        if total > 95:
            self._high_count += 1
            if self._high_count >= 5:
                alerts.append(self._alert(
                    AlertLevel.CRITICAL,
                    f"CPU 持续过载 {total:.0f}%",
                    "降低感知频率或暂停非关键任务",
                ))
                healthy = False
        elif total > 90:
            self._high_count += 1
            if self._high_count >= 10:
                alerts.append(self._alert(
                    AlertLevel.WARNING,
                    f"CPU 高负载 {total:.0f}%",
                ))
        else:
            self._high_count = max(0, self._high_count - 1)

        return self._reading(data, summary, alerts, healthy)
