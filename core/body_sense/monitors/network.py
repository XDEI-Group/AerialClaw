"""
monitors/network.py — 网络实时监控

采样：
- 接口列表 + IP 地址
- 实时上下行速率
- WiFi 信号强度（macOS）
- 到指定目标的延迟

告警：
- WiFi 信号 < -75dBm → WARNING
- 网络断开 → CRITICAL
"""

from __future__ import annotations

import re
import subprocess
import time
from typing import Optional

import psutil

from core.body_sense.base import Alert, AlertLevel, Monitor, MonitorReading


def _fmt_speed(bps: float) -> str:
    """字节/秒转人类可读速率"""
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.1f}MB/s"
    if bps >= 1_000:
        return f"{bps / 1_000:.0f}KB/s"
    return f"{bps:.0f}B/s"


def _get_wifi_rssi() -> Optional[int]:
    """获取 macOS WiFi 信号强度（dBm）"""
    try:
        out = subprocess.run(
            ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
            capture_output=True, text=True, timeout=2,
        )
        for line in out.stdout.splitlines():
            if "agrCtlRSSI" in line:
                return int(line.split(":")[1].strip())
    except Exception:
        pass
    return None


def _get_wifi_ssid() -> Optional[str]:
    """获取当前 WiFi SSID"""
    try:
        out = subprocess.run(
            ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
            capture_output=True, text=True, timeout=2,
        )
        for line in out.stdout.splitlines():
            line = line.strip()
            if line.startswith("SSID:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return None


class NetworkMonitor(Monitor):
    name = "network"
    category = "network"
    hz = 1.0

    def __init__(self) -> None:
        self._prev_io = None
        self._prev_time = 0.0

    def probe(self) -> MonitorReading:
        # 接口和 IP
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        
        interfaces = {}
        for iface, addr_list in addrs.items():
            if iface.startswith(("lo", "utun", "llw", "awdl", "bridge", "anpi")):
                continue
            iface_stat = stats.get(iface)
            if not iface_stat or not iface_stat.isup:
                continue
            ipv4 = None
            for a in addr_list:
                if a.family.name == "AF_INET":
                    ipv4 = a.address
            if ipv4:
                interfaces[iface] = ipv4

        # 上下行速率
        io = psutil.net_io_counters()
        now = time.time()
        up_speed = 0.0
        down_speed = 0.0
        if self._prev_io and self._prev_time:
            dt = now - self._prev_time
            if dt > 0:
                up_speed = (io.bytes_sent - self._prev_io.bytes_sent) / dt
                down_speed = (io.bytes_recv - self._prev_io.bytes_recv) / dt
        self._prev_io = io
        self._prev_time = now

        # WiFi 信号
        rssi = _get_wifi_rssi()
        ssid = _get_wifi_ssid()

        data = {
            "interfaces": interfaces,
            "up_bytes_sec": up_speed,
            "down_bytes_sec": down_speed,
            "bytes_sent_total": io.bytes_sent,
            "bytes_recv_total": io.bytes_recv,
            "wifi_rssi_dbm": rssi,
            "wifi_ssid": ssid,
            "errors_in": io.errin,
            "errors_out": io.errout,
            "drops_in": io.dropin,
            "drops_out": io.dropout,
        }

        up_str = _fmt_speed(up_speed)
        down_str = _fmt_speed(down_speed)
        summary = f"NET ▲{up_str} ▼{down_str}"
        if rssi is not None:
            summary += f" WiFi {rssi}dBm"
        if ssid:
            summary += f" ({ssid})"

        alerts = []
        healthy = True

        if rssi is not None and rssi < -80:
            alerts.append(self._alert(
                AlertLevel.CRITICAL,
                f"WiFi 信号极弱 {rssi}dBm，可能断连",
                "靠近路由器或切换有线网络",
            ))
            healthy = False
        elif rssi is not None and rssi < -70:
            alerts.append(self._alert(
                AlertLevel.WARNING,
                f"WiFi 信号偏弱 {rssi}dBm",
            ))

        if not interfaces:
            alerts.append(self._alert(
                AlertLevel.CRITICAL,
                "无可用网络接口",
                "检查网络连接",
            ))
            healthy = False

        return self._reading(data, summary, alerts, healthy)
