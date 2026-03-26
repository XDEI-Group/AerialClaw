"""
adapter_manager.py
适配器管理器 —— 全局单例，管理当前活跃的仿真适配器。

用法:
    from adapters.adapter_manager import get_adapter, init_adapter

    init_adapter("px4", connection_str="udp://:14540")  # 启动时调用一次
    adapter = get_adapter()                              # 硬技能里获取适配器
    result = adapter.takeoff(5.0)                       # 调用统一接口
"""

import logging
from typing import Optional
from adapters.sim_adapter import SimAdapter

logger = logging.getLogger(__name__)

# ── 全局单例 ──────────────────────────────────────────────────────────────────

_adapter: Optional[SimAdapter] = None

# ── 适配器注册表 ──────────────────────────────────────────────────────────────

_ADAPTER_REGISTRY: dict = {}


def register_adapter(name: str, adapter_class):
    """注册一个适配器类型。"""
    _ADAPTER_REGISTRY[name] = adapter_class


def list_adapters() -> list:
    """列出所有已注册的适配器类型。"""
    return [
        {"name": name, "description": cls.description, "vehicles": cls.supported_vehicles}
        for name, cls in _ADAPTER_REGISTRY.items()
    ]


# ── 内置适配器注册 ────────────────────────────────────────────────────────────

def _register_builtins():
    from adapters.mock_adapter import MockAdapter
    register_adapter("mock", MockAdapter)
    try:
        from adapters.px4_adapter import PX4Adapter
        register_adapter("px4", PX4Adapter)
    except ImportError:
        pass  # mavsdk 未安装时跳过
    try:
        from adapters.airsim_adapter import AirSimAdapter
        register_adapter("airsim", AirSimAdapter)
    except ImportError:
        pass  # airsim 包未安装时跳过
    try:
        from adapters.airsim_physics import AirSimPhysicsAdapter
        register_adapter("airsim_physics", AirSimPhysicsAdapter)
    except ImportError:
        pass

_register_builtins()


# ── 公共接口 ──────────────────────────────────────────────────────────────────

def init_adapter(adapter_type: str = "px4", connection_str: str = "", timeout: float = 15.0) -> bool:
    """
    初始化并连接仿真适配器。

    Args:
        adapter_type: 适配器类型名（"px4" / "mock" / 自定义）
        connection_str: 连接字符串（每种适配器有默认值）
        timeout: 连接超时

    Returns:
        bool: 是否连接成功
    """
    global _adapter

    cls = _ADAPTER_REGISTRY.get(adapter_type)
    if cls is None:
        logger.error(f"未知适配器类型: {adapter_type}，可选: {list(_ADAPTER_REGISTRY.keys())}")
        return False

    _adapter = cls()
    logger.info(f"初始化适配器: {_adapter.name} ({_adapter.description})")

    ok = _adapter.connect(connection_str or "", timeout)
    if ok:
        logger.info(f"✅ 适配器 {_adapter.name} 连接成功")
    else:
        logger.warning(f"⚠️ 适配器 {_adapter.name} 连接失败，降级到 mock")
        from adapters.mock_adapter import MockAdapter
        _adapter = MockAdapter()
        _adapter.connect()

    return ok


def get_adapter() -> Optional[SimAdapter]:
    """获取当前活跃的适配器实例。"""
    return _adapter


def switch_adapter(adapter_type: str, connection_str: str = "", timeout: float = 15.0) -> bool:
    """
    运行时切换适配器（先断开旧的再连新的）。
    """
    global _adapter
    if _adapter and _adapter.is_connected():
        _adapter.disconnect()
    return init_adapter(adapter_type, connection_str, timeout)
