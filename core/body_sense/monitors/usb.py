"""
monitors/usb.py — USB 设备监控

采样（低频 0.2Hz，USB 变化不频繁）：
- 连接的 USB 设备列表
- 新设备接入 / 设备断开检测

告警：
- 新设备接入 → INFO
- 设备断开 → WARNING
"""

from __future__ import annotations

import json
import subprocess
from typing import Dict, List, Optional, Set

from core.body_sense.base import Alert, AlertLevel, Monitor, MonitorReading


def _scan_usb_macos() -> List[Dict[str, str]]:
    """macOS 扫描 USB 设备"""
    try:
        out = subprocess.run(
            ["/usr/sbin/system_profiler", "SPUSBDataType", "-json"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return []

        data = json.loads(out.stdout)
        devices = []
        
        def _walk(items):
            if not isinstance(items, list):
                return
            for item in items:
                if isinstance(item, dict):
                    name = item.get("_name", "")
                    vendor = item.get("manufacturer", "")
                    serial = item.get("serial_num", "")
                    if name and name not in ("USB Bus", "Root Hub"):
                        devices.append({
                            "name": name,
                            "vendor": vendor,
                            "serial": serial,
                        })
                    # 递归子项
                    for key in ("_items", "Media"):
                        if key in item:
                            _walk(item[key])
        
        _walk(data.get("SPUSBDataType", []))
        return devices
    except Exception:
        return []


class USBMonitor(Monitor):
    name = "usb"
    category = "system"
    hz = 0.2  # 5 秒一次

    def __init__(self) -> None:
        self._prev_device_names: Set[str] = set()

    def probe(self) -> MonitorReading:
        devices = _scan_usb_macos()
        current_names = {d["name"] for d in devices}

        alerts = []
        healthy = True

        # 检测变化
        added = current_names - self._prev_device_names
        removed = self._prev_device_names - current_names

        if self._prev_device_names:  # 跳过首次
            for name in added:
                alerts.append(self._alert(
                    AlertLevel.INFO,
                    f"USB 设备接入: {name}",
                ))
            for name in removed:
                alerts.append(self._alert(
                    AlertLevel.WARNING,
                    f"USB 设备断开: {name}",
                ))

        self._prev_device_names = current_names

        data = {
            "count": len(devices),
            "devices": devices,
        }
        summary = f"USB {len(devices)}设备"
        if devices:
            names = [d["name"][:15] for d in devices[:3]]
            summary += f" ({', '.join(names)})"

        return self._reading(data, summary, alerts, healthy)
