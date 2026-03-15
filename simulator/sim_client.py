"""
sim_client.py — AerialClaw 仿真设备端（完全独立）

不依赖控制端任何代码。只用标准库 + mavsdk + socketio + requests。
通过通用设备协议（HTTP + WebSocket）接入控制端。

用法:
    python sim_client.py --server http://localhost:5001
    python sim_client.py --server http://localhost:5001 --no-sim  # 不启动PX4,mock模式
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

import requests
import socketio

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sim_client")

# ══════════════════════════════════════════════════════════════
#  轻量 PX4 控制器（不依赖 adapters/px4_adapter.py）
# ══════════════════════════════════════════════════════════════

class PX4Controller:
    """直接通过 MAVSDK-Python 控制 PX4，不依赖控制端代码。"""

    def __init__(self, connection: str = "udp://:14540"):
        self._conn = connection
        self._system = None
        self._connected = False

    async def connect(self, timeout: float = 20) -> bool:
        try:
            from mavsdk import System
            self._system = System()
            await self._system.connect(system_address=self._conn)
            logger.info("等待 PX4 连接...")
            deadline = time.time() + timeout
            async for state in self._system.core.connection_state():
                if state.is_connected:
                    self._connected = True
                    logger.info("✅ PX4 已连接")
                    return True
                if time.time() > deadline:
                    break
            logger.warning("PX4 连接超时")
            return False
        except ImportError:
            logger.warning("mavsdk 未安装，使用 mock 模式")
            return False
        except Exception as e:
            logger.warning("PX4 连接失败: %s", e)
            return False

    async def execute(self, action: str, params: dict) -> dict:
        """执行飞行指令，返回 {success, message}"""
        if not self._connected or not self._system:
            return {"success": False, "message": "PX4 未连接"}
        try:
            if action == "takeoff":
                alt = params.get("altitude", 5.0)
                await self._system.action.arm()
                await self._system.action.set_takeoff_altitude(alt)
                await self._system.action.takeoff()
                return {"success": True, "message": f"起飞至 {alt}m"}
            elif action == "land":
                await self._system.action.land()
                return {"success": True, "message": "降落中"}
            elif action == "hover":
                await self._system.action.hold()
                return {"success": True, "message": "悬停"}
            elif action == "return_to_launch":
                await self._system.action.return_to_launch()
                return {"success": True, "message": "返航"}
            elif action == "fly_to":
                n = params.get("north", 0)
                e = params.get("east", 0)
                d = params.get("down", -5)
                await self._system.action.goto_location(n, e, abs(d), 0)
                return {"success": True, "message": f"飞行至 N={n} E={e} D={d}"}
            else:
                return {"success": False, "message": f"未知指令: {action}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def get_telemetry(self) -> dict:
        """获取遥测数据"""
        if not self._connected or not self._system:
            return self._mock_telemetry()
        try:
            pos = await self._system.telemetry.position().__anext__()
            bat = await self._system.telemetry.battery().__anext__()
            in_air = await self._system.telemetry.in_air().__anext__()
            armed = await self._system.telemetry.armed().__anext__()
            return {
                "battery": round(bat.remaining_percent * 100, 1),
                "latitude": pos.latitude_deg,
                "longitude": pos.longitude_deg,
                "altitude": pos.relative_altitude_m,
                "in_air": in_air,
                "armed": armed,
                "status": "airborne" if in_air else "idle",
            }
        except Exception:
            return self._mock_telemetry()

    def _mock_telemetry(self) -> dict:
        """Mock 遥测数据"""
        return {
            "battery": 85.0,
            "latitude": 34.2517,
            "longitude": 108.9460,
            "altitude": 0.0,
            "in_air": False,
            "armed": False,
            "status": "idle (mock)",
        }


# ══════════════════════════════════════════════════════════════
#  仿真客户端
# ══════════════════════════════════════════════════════════════

class SimulatorClient:
    """仿真设备客户端 — 完全独立，通过通用协议接入控制端。"""

    def __init__(self, server_url: str, device_id: str = "SIM_UAV_1",
                 world: str = "default", no_sim: bool = False):
        self.server_url = server_url.rstrip("/")
        self.device_id = device_id
        self.world = world
        self.no_sim = no_sim
        self.token = ""
        self.sio = socketio.Client(reconnection=True, reconnection_delay=3)
        self.px4 = PX4Controller()
        self._running = False
        self._loop = None

    def start(self):
        """启动仿真客户端"""
        logger.info("=== AerialClaw 仿真设备端 ===")
        logger.info("device_id: %s | server: %s | world: %s", self.device_id, self.server_url, self.world)

        # 1. 连接 PX4
        if not self.no_sim:
            self._loop = asyncio.new_event_loop()
            connected = self._loop.run_until_complete(self.px4.connect())
            if not connected:
                logger.warning("PX4 未连接，以 mock 模式运行（遥测为模拟数据）")

        # 2. 注册到控制端
        self._register()

        # 3. WebSocket 连接
        self._setup_ws()
        try:
            self.sio.connect(self.server_url, transports=["polling", "websocket"])
        except Exception as e:
            logger.error("WebSocket 连接失败: %s", e)
            return

        # 4. 认证
        self.sio.emit("device_connect", {"device_id": self.device_id, "token": self.token})

        # 5. 启动上报线程
        self._running = True
        threading.Thread(target=self._telemetry_loop, daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

        logger.info("✅ 仿真客户端就绪，按 Ctrl+C 退出")

        # 主循环
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("正在退出...")
            self._running = False
            self.sio.disconnect()

    def _register(self):
        """注册设备"""
        payload = {
            "device_id": self.device_id,
            "device_type": "UAV",
            "capabilities": ["fly", "camera", "lidar", "takeoff", "land",
                             "fly_to", "hover", "return_to_launch"],
            "sensors": ["gps", "imu", "barometer", "camera_front",
                        "camera_rear", "camera_left", "camera_right",
                        "camera_down", "lidar_3d"],
            "protocol": "websocket",
            "metadata": {"simulator": True, "world": self.world},
        }
        url = f"{self.server_url}/api/device/register"
        for i in range(10):
            try:
                r = requests.post(url, json=payload, timeout=5)
                if r.status_code in (200, 201):
                    self.token = r.json().get("token", "")
                    logger.info("✅ 注册成功 token=%s...", self.token[:12])
                    return
                elif r.status_code == 409:
                    logger.info("设备已注册，尝试重新注册...")
                    requests.delete(f"{self.server_url}/api/device/{self.device_id}", timeout=5)
                    continue
                else:
                    logger.warning("注册失败 %d: %s", r.status_code, r.text[:100])
            except Exception as e:
                logger.warning("连接控制端失败: %s (重试 %d/10)", e, i+1)
            time.sleep(3)
        logger.error("注册失败，无法继续")

    def _setup_ws(self):
        """设置 WebSocket 事件处理"""
        @self.sio.on("device_connected")
        def on_connected(data):
            if data.get("ok"):
                logger.info("✅ WebSocket 认证成功")

        @self.sio.on("device_action")
        def on_action(data):
            action = data.get("action", "")
            params = data.get("params", {})
            action_id = data.get("action_id", "")
            logger.info("📩 收到指令: %s params=%s", action, params)

            # 执行
            if self._loop and not self.no_sim:
                result = self._loop.run_until_complete(self.px4.execute(action, params))
            else:
                # Mock 执行
                result = {"success": True, "message": f"[mock] {action} 已执行"}

            logger.info("指令结果: %s", result)
            self.sio.emit("action_result", {
                "action_id": action_id,
                "device_id": self.device_id,
                "success": result["success"],
                "message": result["message"],
                "output": result.get("output", {}),
            })

    def _telemetry_loop(self):
        """遥测上报循环 (1Hz)"""
        while self._running:
            try:
                if self._loop and not self.no_sim:
                    telem = self._loop.run_until_complete(self.px4.get_telemetry())
                else:
                    telem = self.px4._mock_telemetry()
                self.sio.emit("device_state", {
                    "device_id": self.device_id,
                    **telem,
                })
            except Exception as e:
                logger.debug("遥测上报异常: %s", e)
            time.sleep(1)

    def _heartbeat_loop(self):
        """心跳循环 (5s)"""
        while self._running:
            try:
                self.sio.emit("heartbeat", {"device_id": self.device_id})
            except Exception:
                pass
            time.sleep(5)


# ══════════════════════════════════════════════════════════════
#  启动
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="AerialClaw 仿真设备端")
    parser.add_argument("--server", default="http://localhost:5001", help="控制端地址")
    parser.add_argument("--device-id", default="SIM_UAV_1", help="设备 ID")
    parser.add_argument("--world", default="urban_rescue", help="Gazebo 场景")
    parser.add_argument("--no-sim", action="store_true", help="不连接 PX4，纯 mock 模式")
    args = parser.parse_args()

    client = SimulatorClient(
        server_url=args.server,
        device_id=args.device_id,
        world=args.world,
        no_sim=args.no_sim,
    )
    client.start()


if __name__ == "__main__":
    main()
