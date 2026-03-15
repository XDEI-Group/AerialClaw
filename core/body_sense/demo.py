#!/usr/bin/env python3
"""
core/body_sense/demo.py — BodySense 实时终端演示

直接运行：
    python3 -m core.body_sense.demo

在 AerialClaw 根目录下执行。
"""

from __future__ import annotations

import os
import sys
import time

# 确保能 import core 包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.body_sense.engine import BodySenseEngine
from core.body_sense.base import AlertLevel


def _bar(percent: float, width: int = 20) -> str:
    """生成进度条"""
    filled = int(width * percent / 100)
    bar = "█" * filled + "░" * (width - filled)
    return bar


def _color(text: str, code: int) -> str:
    """ANSI 颜色"""
    return f"\033[{code}m{text}\033[0m"


def _pct_color(pct: float) -> int:
    """根据百分比返回颜色码"""
    if pct >= 90:
        return 91  # 红
    if pct >= 70:
        return 93  # 黄
    return 92  # 绿


def main():
    print("\033[2J\033[H")  # 清屏
    print(_color("🔍 AerialClaw BodySense 启动中...", 96))
    print("   自动发现硬件监控器...\n")

    engine = BodySenseEngine()
    engine.auto_discover()
    engine.start()

    # 等一下让监控器采集第一轮数据
    time.sleep(1.5)

    tick = 0
    try:
        while True:
            snap = engine.snapshot()
            monitors = snap.get("monitors", {})
            
            # 清屏 + 移到顶部
            sys.stdout.write("\033[H\033[2J")

            # 标题
            print(_color("╔══════════════════════════════════════════════════════════════╗", 96))
            print(_color("║", 96) + _color("  🖥️  AerialClaw BodySense — 实时硬件感知", 97) + _color("                   ║", 96))
            print(_color("╠══════════════════════════════════════════════════════════════╣", 96))

            # CPU
            cpu = monitors.get("cpu", {}).get("data", {})
            if cpu:
                pct = cpu.get("total_percent", 0)
                cores = cpu.get("cores_total", 0)
                freq = cpu.get("frequency_ghz", 0)
                load1 = cpu.get("load_1m", 0)
                bar = _bar(pct)
                c = _pct_color(pct)
                per_cpu = cpu.get("per_cpu_percent", [])
                print(_color("║", 96) + f"  CPU    {_color(bar, c)} {_color(f'{pct:5.1f}%', c)}  {cores}C {freq}GHz  load:{load1:.1f}" + _color("  ║", 96).rjust(10))
                
                # 每核显示（紧凑）
                if per_cpu:
                    mini_bars = []
                    for i, p in enumerate(per_cpu):
                        filled = int(p / 10)
                        mini = "▓" * filled + "░" * (10 - filled)
                        mini_bars.append(f"C{i}:{p:4.0f}%")
                    # 分两行显示
                    half = len(mini_bars) // 2
                    line1 = "  ".join(mini_bars[:half])
                    line2 = "  ".join(mini_bars[half:])
                    print(_color("║", 96) + f"         {line1}")
                    print(_color("║", 96) + f"         {line2}")

            # Memory
            mem = monitors.get("memory", {}).get("data", {})
            if mem:
                pct = mem.get("percent", 0)
                used = mem.get("used_bytes", 0) / (1 << 30)
                total = mem.get("total_bytes", 0) / (1 << 30)
                avail = mem.get("available_bytes", 0) / (1 << 30)
                wired = mem.get("wired_bytes", 0) / (1 << 30)
                bar = _bar(pct)
                c = _pct_color(pct)
                print(_color("║", 96) + f"  MEM    {_color(bar, c)} {_color(f'{pct:5.1f}%', c)}  {used:.1f}/{total:.0f}GB  可用:{avail:.1f}GB  固定:{wired:.1f}GB")

            # Disk
            disk = monitors.get("disk", {}).get("data", {})
            if disk:
                pct = disk.get("percent", 0)
                free = disk.get("free_bytes", 0)
                free_gb = free / (1 << 30)
                rs = disk.get("read_bytes_sec", 0)
                ws = disk.get("write_bytes_sec", 0)
                bar = _bar(pct)
                c = _pct_color(pct)
                io_str = ""
                if rs > 0 or ws > 0:
                    io_str = f"  R:{rs/1e6:.1f}MB/s W:{ws/1e6:.1f}MB/s"
                print(_color("║", 96) + f"  DISK   {_color(bar, c)} {_color(f'{pct:5.1f}%', c)}  空闲:{free_gb:.0f}GB{io_str}")

            # Network
            net = monitors.get("network", {}).get("data", {})
            if net:
                up = net.get("up_bytes_sec", 0)
                down = net.get("down_bytes_sec", 0)
                rssi = net.get("wifi_rssi_dbm")
                ssid = net.get("wifi_ssid", "")
                ifaces = net.get("interfaces", {})

                def fmt_speed(bps):
                    if bps >= 1e6: return f"{bps/1e6:.1f}MB/s"
                    if bps >= 1e3: return f"{bps/1e3:.0f}KB/s"
                    return f"{bps:.0f}B/s"

                wifi_str = ""
                if rssi is not None:
                    wifi_str = f"  WiFi:{rssi}dBm"
                    if ssid:
                        wifi_str += f"({ssid[:12]})"

                iface_str = "  ".join(f"{k}:{v}" for k, v in list(ifaces.items())[:3])
                print(_color("║", 96) + f"  NET    ▲ {_color(fmt_speed(up), 92)}  ▼ {_color(fmt_speed(down), 94)}{wifi_str}")
                print(_color("║", 96) + f"         {iface_str}")

            # Thermal
            thermal = monitors.get("thermal", {}).get("data", {})
            if thermal:
                temps = thermal.get("temperatures", {})
                if temps:
                    parts = []
                    for k, v in temps.items():
                        if k == "thermal_level":
                            names = {0: "正常", 1: "轻微", 2: "中等", 3: "严重"}
                            parts.append(f"热压力:{names.get(int(v), f'L{int(v)}')}")
                        else:
                            c = 91 if v > 80 else (93 if v > 60 else 92)
                            parts.append(_color(f"{k}:{v:.0f}°C", c))
                    print(_color("║", 96) + f"  TEMP   {' '.join(parts)}")
                else:
                    print(_color("║", 96) + f"  TEMP   不可用（需安装 osx-cpu-temp）")

            # USB
            usb = monitors.get("usb", {}).get("data", {})
            if usb:
                count = usb.get("count", 0)
                devices = usb.get("devices", [])
                dev_names = [d.get("name", "?")[:20] for d in devices[:4]]
                dev_str = ", ".join(dev_names) if dev_names else "无"
                print(_color("║", 96) + f"  USB    {count}个设备: {dev_str}")

            # 分隔线
            print(_color("╠══════════════════════════════════════════════════════════════╣", 96))

            # 告警
            alerts = snap.get("alerts", [])
            critical = [a for a in alerts if a["level"] == "critical"]
            warnings = [a for a in alerts if a["level"] == "warning"]
            
            if critical:
                for a in critical[-3:]:
                    print(_color("║", 96) + f"  🚨 {_color(a['message'], 91)}")
            elif warnings:
                for a in warnings[-3:]:
                    print(_color("║", 96) + f"  ⚠️  {_color(a['message'], 93)}")
            else:
                print(_color("║", 96) + f"  {_color('✅ 所有系统正常', 92)}")

            # 状态栏
            uptime_s = time.time() - __import__("psutil").boot_time()
            days = int(uptime_s // 86400)
            hours = int((uptime_s % 86400) // 3600)
            mins = int((uptime_s % 3600) // 60)
            healthy = "🟢" if snap.get("healthy") else "🔴"
            tick_char = ["◐", "◓", "◑", "◒"][tick % 4]

            print(_color("╠══════════════════════════════════════════════════════════════╣", 96))
            print(_color("║", 96) + f"  {healthy} 状态:{_color('正常', 92) if snap.get('healthy') else _color('异常', 91)}  "
                  f"监控器:{snap.get('monitor_count', 0)}  "
                  f"运行:{days}d {hours}h {mins}m  "
                  f"{tick_char} 刷新中")
            print(_color("║", 96) + f"  LLM 摘要: {_color(engine.summary(), 97)}")
            print(_color("╚══════════════════════════════════════════════════════════════╝", 96))
            print(f"\n  按 Ctrl+C 退出")

            tick += 1
            time.sleep(0.5)

    except KeyboardInterrupt:
        engine.stop()
        print("\n\n" + _color("BodySense 已停止", 93))


if __name__ == "__main__":
    main()
