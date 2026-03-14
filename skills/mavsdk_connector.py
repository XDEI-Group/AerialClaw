"""
mavsdk_connector.py
MAVSDK 连接管理器 —— 管理 PX4 SITL 连接。

关键设计：
    - MAVSDK/gRPC 绑定 event loop，所有操作必须在同一个 loop 里
    - 提供 connect_drone_sync() 给同步代码用
    - 提供 run_in_drone_loop() 在 drone 的 loop 上跑异步操作
"""

import asyncio
import threading
import logging
from typing import Optional, Any, Coroutine

from mavsdk import System

logger = logging.getLogger(__name__)

# ── 全局状态 ──────────────────────────────────────────────────────────────────

_drone: Optional[System] = None
_connected: bool = False
_loop: Optional[asyncio.AbstractEventLoop] = None
_thread: Optional[threading.Thread] = None


def _ensure_loop():
    """确保有一个专门给 MAVSDK 用的 event loop 在后台线程跑。"""
    global _loop, _thread
    if _loop is not None and _loop.is_running():
        return

    _loop = asyncio.new_event_loop()

    def run():
        asyncio.set_event_loop(_loop)
        _loop.run_forever()

    _thread = threading.Thread(target=run, daemon=True, name="mavsdk-loop")
    _thread.start()
    logger.debug("MAVSDK event loop 已启动")


def run_in_drone_loop(coro: Coroutine, timeout: float = 60.0) -> Any:
    """在 MAVSDK 的 event loop 上跑一个协程，同步等待结果。"""
    _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=timeout)


def get_drone() -> Optional[System]:
    """获取 MAVSDK System 实例。"""
    return _drone if _connected else None


def is_connected() -> bool:
    return _connected


async def _connect_async(connection_str: str, timeout: float) -> bool:
    """异步连接到 PX4 SITL。"""
    global _drone, _connected

    if _connected and _drone is not None:
        logger.info("MAVSDK 已连接")
        return True

    try:
        _drone = System()
        await _drone.connect(system_address=connection_str)
        logger.info(f"正在连接 {connection_str}...")

        deadline = asyncio.get_event_loop().time() + timeout
        async for state in _drone.core.connection_state():
            if state.is_connected:
                logger.info("✅ MAVSDK 已连接到 PX4")
                _connected = True
                return True
            if asyncio.get_event_loop().time() > deadline:
                logger.error(f"❌ 连接超时 ({timeout}s)")
                return False

    except Exception as e:
        logger.error(f"❌ MAVSDK 连接失败: {e}")
        _connected = False
        return False

    return False


def connect_drone_sync(connection_str: str = "udp://:14540", timeout: float = 15.0) -> bool:
    """同步连接（给 Skill.execute() 用）。"""
    _ensure_loop()
    return run_in_drone_loop(_connect_async(connection_str, timeout), timeout=timeout + 5)


async def connect_drone(connection_str: str = "udp://:14540", timeout: float = 15.0) -> bool:
    """异步连接（给 async main 用）。"""
    _ensure_loop()
    # 如果当前在 MAVSDK loop 上就直接跑，否则跨线程调度
    if asyncio.get_event_loop() == _loop:
        return await _connect_async(connection_str, timeout)
    return run_in_drone_loop(_connect_async(connection_str, timeout), timeout=timeout + 5)


async def disconnect_drone():
    """断开 MAVSDK 连接。"""
    global _drone, _connected
    _connected = False
    _drone = None
    logger.info("MAVSDK 已断开")
