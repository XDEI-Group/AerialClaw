"""
monitors/thermal.py — 温度监控（macOS Apple Silicon）

macOS 上 psutil 不支持 sensors_temperatures()。
通过 powermetrics（需 sudo）或 IOKit 获取 CPU/GPU 温度。
无权限时退化为系统负载推估。

告警：
- CPU > 80°C → WARNING
- CPU > 95°C → CRITICAL
"""

from __future__ import annotations

import ctypes
import ctypes.util
import struct
import subprocess
from typing import Dict, Optional

from core.body_sense.base import Alert, AlertLevel, Monitor, MonitorReading


def _read_smc_temp() -> Dict[str, float]:
    """
    通过多种方式获取 macOS 温度信息。
    优先级：osx-cpu-temp → pmset thermal → sysctl
    """
    temps = {}

    # 方法 1: osx-cpu-temp 命令行
    try:
        out = subprocess.run(
            ["osx-cpu-temp"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0 and "°C" in out.stdout:
            for line in out.stdout.strip().splitlines():
                parts = line.split(":")
                if len(parts) == 2:
                    label = parts[0].strip().lower()
                    try:
                        val = float(parts[1].replace("°C", "").strip())
                        temps[label] = val
                    except ValueError:
                        pass
            if temps:
                return temps
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # 方法 2: pmset thermal warning
    try:
        out = subprocess.run(
            ["pmset", "-g", "therm"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0:
            text = out.stdout
            if "No thermal warning" in text:
                temps["thermal_warning"] = 0.0  # 正常
            else:
                # 有热量警告
                temps["thermal_warning"] = 1.0
    except Exception:
        pass

    # 方法 3: CPU thermal level (Intel Mac)
    try:
        out = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "machdep.xcpm.cpu_thermal_level"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode == 0 and out.stdout.strip():
            level = int(out.stdout.strip())
            temps["thermal_level"] = float(level)
    except Exception:
        pass

    return temps


class ThermalMonitor(Monitor):
    name = "thermal"
    category = "thermal"
    hz = 0.5  # 温度变化慢

    def probe(self) -> MonitorReading:
        temps = _read_smc_temp()

        data = {
            "temperatures": temps,
            "source": "smc" if any(k != "thermal_level" for k in temps) else "sysctl",
        }

        alerts = []
        healthy = True

        if not temps:
            summary = "TEMP 不可用"
            return self._reading(data, summary, alerts, healthy)

        # 有实际温度值
        cpu_temp = temps.get("cpu", temps.get("cpu die", None))
        gpu_temp = temps.get("gpu", None)
        thermal_level = temps.get("thermal_level")
        thermal_warning = temps.get("thermal_warning")

        parts = []
        if cpu_temp is not None:
            parts.append(f"CPU {cpu_temp:.0f}°C")
            if cpu_temp > 95:
                alerts.append(self._alert(
                    AlertLevel.CRITICAL,
                    f"CPU 温度过高 {cpu_temp:.0f}°C",
                    "降低负载，检查散热",
                ))
                healthy = False
            elif cpu_temp > 80:
                alerts.append(self._alert(
                    AlertLevel.WARNING,
                    f"CPU 温度偏高 {cpu_temp:.0f}°C",
                ))
        if gpu_temp is not None:
            parts.append(f"GPU {gpu_temp:.0f}°C")

        if thermal_warning is not None:
            if thermal_warning == 0:
                parts.append("散热正常")
            else:
                parts.append("⚠️散热告警")
                alerts.append(self._alert(
                    AlertLevel.WARNING,
                    "系统散热告警",
                    "降低 CPU/GPU 负载",
                ))

        if thermal_level is not None and not parts:
            level_names = {0: "正常", 1: "轻微", 2: "中等", 3: "严重", 4: "危险"}
            name = level_names.get(int(thermal_level), f"等级{int(thermal_level)}")
            parts.append(f"热压力:{name}")
            if thermal_level >= 3:
                alerts.append(self._alert(
                    AlertLevel.WARNING,
                    f"系统热压力等级 {int(thermal_level)} ({name})",
                    "降低 CPU/GPU 负载",
                ))

        summary = "TEMP " + " ".join(parts) if parts else "TEMP 未知"

        return self._reading(data, summary, alerts, healthy)
