"""
monitors/usb.py — USB 设备监控

多平台支持：
  macOS: hidutil list（Apple Silicon 兼容）+ system_profiler 降级
  Linux: lsusb / /sys/bus/usb/devices
  通用: psutil 无 USB 支持，需要平台特定方案

告警：
- 新设备接入 → INFO
- 设备断开 → WARNING
"""

from __future__ import annotations

import platform
import re
import subprocess
from typing import Dict, List, Set

from core.body_sense.base import Alert, AlertLevel, Monitor, MonitorReading


def _scan_usb_hidutil() -> List[Dict[str, str]]:
    """macOS: 通过 hidutil list 扫描 USB HID 设备（Apple Silicon 兼容）"""
    try:
        out = subprocess.run(
            ["hidutil", "list"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return []

        devices = {}  # name → device info, 去重
        for line in out.stdout.splitlines():
            parts = line.split()
            if len(parts) < 9:
                continue
            transport = parts[6] if len(parts) > 6 else ""
            if transport != "USB":
                continue
            # 提取产品名（可能包含空格，在第8个字段之后）
            # 格式: VID PID LocID UsagePage Usage RegID Transport Class Product...
            try:
                product_start = 8
                # 找到 Product 列
                product_parts = []
                for i in range(product_start, len(parts)):
                    # 遇到 AppleUser... 就停
                    if parts[i].startswith("Apple") and i > product_start:
                        break
                    product_parts.append(parts[i])
                product = " ".join(product_parts)
                if product and product not in devices:
                    vid = parts[0]
                    pid = parts[1]
                    devices[product] = {
                        "name": product,
                        "vendor_id": vid,
                        "product_id": pid,
                        "transport": "USB",
                    }
            except (IndexError, ValueError):
                continue

        return list(devices.values())
    except FileNotFoundError:
        return []
    except Exception:
        return []


def _scan_usb_system_profiler() -> List[Dict[str, str]]:
    """macOS: system_profiler 降级方案（Intel Mac 或旧系统）"""
    try:
        import json as _json
        out = subprocess.run(
            ["/usr/sbin/system_profiler", "SPUSBDataType", "-json"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return []
        data = _json.loads(out.stdout)
        devices = []

        def _walk(items):
            if not isinstance(items, list):
                return
            for item in items:
                if isinstance(item, dict):
                    name = item.get("_name", "")
                    vendor = item.get("manufacturer", "")
                    if name and name not in ("USB Bus", "Root Hub"):
                        devices.append({
                            "name": name,
                            "vendor": vendor,
                            "transport": "USB",
                        })
                    for key in ("_items", "Media"):
                        if key in item:
                            _walk(item[key])

        _walk(data.get("SPUSBDataType", []))
        return devices
    except Exception:
        return []


def _scan_usb_linux() -> List[Dict[str, str]]:
    """Linux: 通过 lsusb 扫描"""
    try:
        out = subprocess.run(
            ["lsusb"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return []
        devices = []
        for line in out.stdout.strip().splitlines():
            # Bus 001 Device 003: ID 1234:5678 Product Name
            m = re.match(r"Bus \d+ Device \d+: ID (\w+):(\w+)\s+(.*)", line)
            if m:
                vid, pid, name = m.groups()
                # 过滤掉 root hub
                if "root hub" in name.lower():
                    continue
                devices.append({
                    "name": name.strip(),
                    "vendor_id": f"0x{vid}",
                    "product_id": f"0x{pid}",
                    "transport": "USB",
                })
        return devices
    except FileNotFoundError:
        return []
    except Exception:
        return []


def scan_usb() -> List[Dict[str, str]]:
    """跨平台 USB 设备扫描"""
    system = platform.system()
    if system == "Darwin":
        # macOS: 先试 hidutil（Apple Silicon），再降级 system_profiler
        devices = _scan_usb_hidutil()
        if not devices:
            devices = _scan_usb_system_profiler()
        return devices
    elif system == "Linux":
        return _scan_usb_linux()
    # Windows / 其他: 暂不支持
    return []


class USBMonitor(Monitor):
    name = "usb"
    category = "system"
    hz = 0.2  # 5 秒一次

    def __init__(self) -> None:
        self._prev_device_names: Set[str] = set()

    def probe(self) -> MonitorReading:
        devices = scan_usb()
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
            names = [d["name"][:20] for d in devices[:3]]
            summary += f" ({', '.join(names)})"

        return self._reading(data, summary, alerts, healthy)
