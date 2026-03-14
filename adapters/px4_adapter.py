"""
px4_adapter.py
PX4 SITL + MAVSDK-Python 仿真适配器。

连接方式: 外部 mavsdk_server 进程（通过 gRPC 端口 50051）。
不再让 System() 自行 spawn 子进程，避免 v3.15.0 bad_optional_access 崩溃。
如果外部 mavsdk_server 未运行，会自动启动它。

外部 mavsdk_server 命令:
  mavsdk_server -p 50051 --sysid 245 --compid 190 udp://:14540
"""

import os
import time
import asyncio
import subprocess
import threading
import logging
from typing import Optional

from mavsdk import System

from adapters.sim_adapter import (
    SimAdapter, Position, GPSPosition, VehicleState, ActionResult,
)

logger = logging.getLogger(__name__)

# mavsdk_server 二进制路径
_MAVSDK_SERVER_BIN = os.environ.get(
    "MAVSDK_SERVER_BIN",
    "/opt/homebrew/lib/python3.14/site-packages/mavsdk/bin/mavsdk_server"
)
_MAVSDK_GRPC_PORT = int(os.environ.get("MAVSDK_GRPC_PORT", "50051"))
_MAVSDK_SYSID = 245
_MAVSDK_COMPID = 190
_MAV_CONNECTION = "udp://:14540"


class PX4Adapter(SimAdapter):
    """PX4 SITL 仿真适配器，通过外部 mavsdk_server + gRPC 控制。"""

    name = "px4_mavsdk"
    description = "PX4 SITL via MAVSDK-Python (supports Gazebo, jMAVSim)"
    supported_vehicles = ["multirotor", "fixedwing", "vtol"]

    def __init__(self):
        self._drone: Optional[System] = None
        self._connected = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._mavsdk_proc: Optional[subprocess.Popen] = None

    def _ensure_loop(self):
        if self._loop and self._loop.is_running():
            return
        self._loop = asyncio.new_event_loop()
        def run():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()
        self._thread = threading.Thread(target=run, daemon=True, name="px4-adapter-loop")
        self._thread.start()

    def _run(self, coro, timeout=60.0):
        self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    # ── mavsdk_server 管理 ──────────────────────────────────────────────────

    def _is_mavsdk_server_running(self) -> bool:
        """检查外部 mavsdk_server 是否在运行"""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(("127.0.0.1", _MAVSDK_GRPC_PORT))
            s.close()
            return True
        except (ConnectionRefusedError, OSError):
            return False

    def _start_mavsdk_server(self) -> bool:
        """启动外部 mavsdk_server 进程"""
        if self._is_mavsdk_server_running():
            logger.info(f"PX4Adapter: mavsdk_server 已在端口 {_MAVSDK_GRPC_PORT} 运行")
            return True

        if not os.path.exists(_MAVSDK_SERVER_BIN):
            logger.error(f"PX4Adapter: mavsdk_server 二进制不存在: {_MAVSDK_SERVER_BIN}")
            return False

        cmd = [
            _MAVSDK_SERVER_BIN,
            "-p", str(_MAVSDK_GRPC_PORT),
            "--sysid", str(_MAVSDK_SYSID),
            "--compid", str(_MAVSDK_COMPID),
            _MAV_CONNECTION,
        ]
        logger.info(f"PX4Adapter: 启动 mavsdk_server: {' '.join(cmd)}")
        log_f = open("/tmp/mavsdk_server.log", "a")
        self._mavsdk_proc = subprocess.Popen(
            cmd, stdout=log_f, stderr=log_f
        )
        # 等待 gRPC 端口可用
        for _ in range(30):
            time.sleep(0.5)
            if self._is_mavsdk_server_running():
                logger.info(f"PX4Adapter: mavsdk_server 已启动 (pid={self._mavsdk_proc.pid})")
                return True
            # 检查进程是否已退出
            if self._mavsdk_proc.poll() is not None:
                logger.error(f"PX4Adapter: mavsdk_server 启动后立即退出 (rc={self._mavsdk_proc.returncode})")
                return False
        logger.error("PX4Adapter: mavsdk_server 启动超时")
        return False

    def _ensure_mavsdk_server(self) -> bool:
        """确保 mavsdk_server 在运行，不在则自动重启"""
        if self._is_mavsdk_server_running():
            return True
        logger.warning("PX4Adapter: mavsdk_server 未运行，正在重启...")
        return self._start_mavsdk_server()

    # ── 连接 ──────────────────────────────────────────────────────────────────

    def connect(self, connection_str: str = "udp://:14540", timeout: float = 15.0) -> bool:
        self._ensure_loop()
        # 先确保外部 mavsdk_server 在运行
        if not self._start_mavsdk_server():
            logger.error("PX4Adapter: 无法启动 mavsdk_server")
            return False
        return self._run(self._connect_async(timeout), timeout + 5)

    async def _connect_async(self, timeout):
        if self._connected and self._drone:
            return True
        try:
            # 连接到外部 mavsdk_server 的 gRPC 端口，不 spawn 子进程
            self._drone = System(mavsdk_server_address="127.0.0.1", port=_MAVSDK_GRPC_PORT)
            await self._drone.connect()
            logger.info(f"PX4Adapter: 连接 gRPC 127.0.0.1:{_MAVSDK_GRPC_PORT}...")
            deadline = asyncio.get_event_loop().time() + timeout
            async for st in self._drone.core.connection_state():
                if st.is_connected:
                    logger.info("PX4Adapter: ✅ 已连接 (通过外部 mavsdk_server)")
                    self._connected = True
                    return True
                if asyncio.get_event_loop().time() > deadline:
                    return False
        except Exception as e:
            logger.error(f"PX4Adapter 连接失败: {e}")
            return False
        return False

    def disconnect(self):
        self._connected = False
        self._drone = None

    def is_connected(self):
        return self._connected

    # ── 状态 ──────────────────────────────────────────────────────────────────

    def get_state(self) -> VehicleState:
        if not self._connected: return VehicleState()
        return self._run(self._get_state_async())

    async def _get_state_async(self):
        d = self._drone; s = VehicleState()
        try:
            async for a in d.telemetry.armed(): s.armed = a; break
            async for a in d.telemetry.in_air(): s.in_air = a; break
            async for fm in d.telemetry.flight_mode(): s.mode = str(fm); break
            async for pos in d.telemetry.position():
                s.position_gps = GPSPosition(pos.latitude_deg, pos.longitude_deg, pos.relative_altitude_m); break
            async for pv in d.telemetry.position_velocity_ned():
                p = pv.position; s.position_ned = Position(p.north_m, p.east_m, p.down_m)
                v = pv.velocity; s.velocity = [v.north_m_s, v.east_m_s, v.down_m_s]; break
            async for bat in d.telemetry.battery():
                s.battery_voltage = bat.voltage_v; s.battery_percent = bat.remaining_percent; break
            async for h in d.telemetry.heading(): s.heading_deg = h.heading_deg; break
        except Exception as e:
            err_str = str(e)
            if "UNAVAILABLE" in err_str or "failed to connect" in err_str:
                logger.warning("PX4Adapter: gRPC 连接丢失，mavsdk_server 可能已崩溃，标记断连")
                self._connected = False
                self._drone = None
            else:
                logger.warning(f"get_state 部分失败: {e}")
        return s

    def get_position(self) -> Position:
        if not self._connected: return Position()
        return self._run(self._pos_async())

    async def _pos_async(self):
        async for pv in self._drone.telemetry.position_velocity_ned():
            p = pv.position; return Position(p.north_m, p.east_m, p.down_m)
        return Position()

    def get_gps(self) -> GPSPosition:
        if not self._connected: return GPSPosition()
        return self._run(self._gps_async())

    async def _gps_async(self):
        async for pos in self._drone.telemetry.position():
            return GPSPosition(pos.latitude_deg, pos.longitude_deg, pos.relative_altitude_m)
        return GPSPosition()

    def get_battery(self) -> tuple:
        if not self._connected: return (0.0, 0.0)
        return self._run(self._bat_async())

    async def _bat_async(self):
        async for bat in self._drone.telemetry.battery():
            return (bat.voltage_v, bat.remaining_percent)
        return (0.0, 0.0)

    def is_armed(self) -> bool:
        if not self._connected: return False
        return self._run(self._armed_async())

    async def _armed_async(self):
        async for a in self._drone.telemetry.armed(): return a
        return False

    def is_in_air(self) -> bool:
        if not self._connected: return False
        return self._run(self._inair_async())

    async def _inair_async(self):
        async for a in self._drone.telemetry.in_air(): return a
        return False

    # ── 飞行操作 ──────────────────────────────────────────────────────────────

    def arm(self) -> ActionResult:
        if not self._connected: return ActionResult(False, "未连接")
        return self._run(self._arm_async())

    async def _arm_async(self):
        try:
            await self._drone.action.arm()
            return ActionResult(True, "ARM 成功")
        except Exception as e:
            return ActionResult(False, f"ARM 失败: {e}")

    def disarm(self) -> ActionResult:
        if not self._connected: return ActionResult(False, "未连接")
        return self._run(self._disarm_async())

    async def _disarm_async(self):
        try:
            await self._drone.action.disarm()
            return ActionResult(True, "DISARM 成功")
        except Exception as e:
            return ActionResult(False, f"DISARM 失败: {e}")

    def takeoff(self, altitude: float = 5.0) -> ActionResult:
        if not self._connected: return ActionResult(False, "未连接")
        return self._run(self._takeoff_async(altitude), timeout=90)

    async def _takeoff_async(self, altitude):
        start = time.time()
        try:
            await self._drone.action.set_takeoff_altitude(altitude)
            await self._drone.action.arm()
            await self._drone.action.takeoff()
            alt = 0.0
            for _ in range(120):
                async for pos in self._drone.telemetry.position():
                    alt = pos.relative_altitude_m; break
                if alt >= altitude * 0.85: break
                await asyncio.sleep(0.5)
            dur = round(time.time() - start, 2)
            return ActionResult(True, f"起飞到 {alt:.1f}m", {"altitude": round(alt, 2)}, dur)
        except Exception as e:
            return ActionResult(False, f"起飞失败: {e}", duration=round(time.time()-start, 2))

    def land(self) -> ActionResult:
        if not self._connected: return ActionResult(False, "未连接")
        return self._run(self._land_async(), timeout=30)

    async def _land_async(self):
        start = time.time()
        try:
            await self._drone.action.land()
            for _ in range(240):
                async for ia in self._drone.telemetry.in_air():
                    flying = ia; break
                if not flying: break
                await asyncio.sleep(0.5)
            return ActionResult(True, "降落完成", duration=round(time.time()-start, 2))
        except Exception as e:
            return ActionResult(False, f"降落失败: {e}", duration=round(time.time()-start, 2))

    def fly_to_ned(self, north, east, down, speed=2.0) -> ActionResult:
        if not self._connected: return ActionResult(False, "未连接")
        return self._run(self._fly_ned_async(north, east, down, speed), timeout=30)

    async def _fly_ned_async(self, north, east, down, speed):
        from mavsdk.offboard import PositionNedYaw
        start = time.time()
        try:
            cur = [0, 0, -5]
            async for pv in self._drone.telemetry.position_velocity_ned():
                p = pv.position; cur = [p.north_m, p.east_m, p.down_m]; break
            await self._drone.offboard.set_position_ned(PositionNedYaw(*cur, 0.0))
            await self._drone.offboard.start()
            await self._drone.offboard.set_position_ned(PositionNedYaw(north, east, down, 0.0))
            arrived = False
            for _ in range(240):
                async for pv in self._drone.telemetry.position_velocity_ned():
                    p = pv.position
                    d = ((p.north_m-north)**2 + (p.east_m-east)**2 + (p.down_m-down)**2) ** 0.5
                    if d < 1.0: arrived = True
                    break
                if arrived: break
                await asyncio.sleep(0.5)
            try: await self._drone.offboard.stop()
            except: pass
            final = cur
            async for pv in self._drone.telemetry.position_velocity_ned():
                p = pv.position; final = [round(p.north_m, 2), round(p.east_m, 2), round(p.down_m, 2)]; break
            dur = round(time.time()-start, 2)
            if arrived:
                return ActionResult(True, f"到达 NED={final}", {"position": final}, dur)
            return ActionResult(False, f"超时 NED={final}", {"position": final}, dur)
        except Exception as e:
            return ActionResult(False, f"飞行失败: {e}", duration=round(time.time()-start, 2))

    def hover(self, duration=5.0) -> ActionResult:
        if not self._connected: return ActionResult(False, "未连接")
        return self._run(self._hover_async(duration), timeout=duration+30)

    async def _hover_async(self, duration):
        from mavsdk.offboard import PositionNedYaw
        start = time.time()
        try:
            cur = [0, 0, -5]
            async for pv in self._drone.telemetry.position_velocity_ned():
                p = pv.position; cur = [p.north_m, p.east_m, p.down_m]; break
            await self._drone.offboard.set_position_ned(PositionNedYaw(*cur, 0.0))
            try: await self._drone.offboard.start()
            except: pass
            await asyncio.sleep(duration)
            try: await self._drone.offboard.stop()
            except: pass
            return ActionResult(True, f"悬停 {duration}s", {"position": [round(x, 2) for x in cur]}, round(time.time()-start, 2))
        except Exception as e:
            return ActionResult(False, f"悬停失败: {e}", duration=round(time.time()-start, 2))

    # ── 速度控制（Body 坐标系） ────────────────────────────

    def set_velocity_body(self, forward: float, right: float, down: float, yaw_rate: float = 0.0) -> ActionResult:
        """Body 坐标系速度控制。forward=前(+)/后(-), right=右(+)/左(-), down=下(+)/上(-), yaw_rate=顺时针(+)。"""
        if not self._connected:
            return ActionResult(False, "未连接")
        return self._run(self._velocity_body_async(forward, right, down, yaw_rate), timeout=5)

    async def _velocity_body_async(self, forward, right, down, yaw_rate):
        from mavsdk.offboard import VelocityBodyYawspeed
        try:
            vel = VelocityBodyYawspeed(forward, right, down, yaw_rate)
            # 需要先 set 一次再 start（如果还没 start 的话）
            await self._drone.offboard.set_velocity_body(vel)
            try:
                await self._drone.offboard.start()
            except Exception:
                pass  # 已经在 offboard 模式
            await self._drone.offboard.set_velocity_body(vel)
            return ActionResult(True, f"velocity body: fwd={forward} right={right} down={down} yaw={yaw_rate}")
        except Exception as e:
            return ActionResult(False, f"速度控制失败: {e}")

    def stop_velocity(self) -> ActionResult:
        """停止速度控制（悬停）。"""
        if not self._connected:
            return ActionResult(False, "未连接")
        return self._run(self._stop_velocity_async(), timeout=5)

    async def _stop_velocity_async(self):
        from mavsdk.offboard import VelocityBodyYawspeed
        try:
            await self._drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))
            await asyncio.sleep(0.3)
            try:
                await self._drone.offboard.stop()
            except Exception:
                pass
            return ActionResult(True, "已停止，切换到悬停")
        except Exception as e:
            return ActionResult(False, f"停止失败: {e}")

    def return_to_launch(self) -> ActionResult:
        if not self._connected: return ActionResult(False, "未连接")
        return self._run(self._rtl_async(), timeout=30)

    async def _rtl_async(self):
        start = time.time()
        try:
            await self._drone.action.return_to_launch()
            for _ in range(60):
                async for ia in self._drone.telemetry.in_air():
                    flying = ia; break
                if not flying: break
                await asyncio.sleep(0.5)
            return ActionResult(True, "RTL 完成", duration=round(time.time()-start, 2))
        except Exception as e:
            return ActionResult(False, f"RTL 失败: {e}", duration=round(time.time()-start, 2))
