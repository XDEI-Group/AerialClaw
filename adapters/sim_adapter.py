"""
sim_adapter.py
仿真环境适配器抽象层 —— 让硬技能与具体仿真环境解耦。

设计思想：
    硬技能 ──调用──→ SimAdapter (抽象接口) ──实现──→ 具体仿真环境
    
    例如：
        Takeoff.execute() → adapter.takeoff(5.0)
            └→ PX4Adapter.takeoff() → MAVSDK arm + takeoff
            └→ AirSimAdapter.takeoff() → AirSim API
            └→ MockAdapter.takeoff() → 模拟返回

扩展方式：
    1. 新建 adapters/xxx_adapter.py，继承 SimAdapter
    2. 实现所有抽象方法
    3. 在 config/sim_config.yaml 里配置使用哪个 adapter
    4. 硬技能代码无需改动

支持的仿真环境（已有/计划）：
    - PX4 SITL + Gazebo (通过 MAVSDK-Python) ← 当前实现
    - AirSim (通过 airsim Python API) ← 预留
    - ROS2 (通过 rclpy) ← 预留
    - Mock (纯内存模拟) ← 测试用
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


# ── 统一数据结构 ──────────────────────────────────────────────────────────────

@dataclass
class Position:
    """统一位置表示（NED 坐标系）"""
    north: float = 0.0   # 正北（米）
    east: float = 0.0    # 正东（米）
    down: float = 0.0    # 向下（米），负值 = 向上
    
    @property
    def altitude(self) -> float:
        """高度 = -down"""
        return -self.down
    
    def to_list(self) -> list:
        return [self.north, self.east, self.down]

    def __repr__(self):
        return f"NED({self.north:.1f}, {self.east:.1f}, {self.down:.1f})"


@dataclass
class GPSPosition:
    """GPS 坐标"""
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0   # 相对高度（米）


@dataclass
class VehicleState:
    """飞行器统一状态"""
    armed: bool = False
    in_air: bool = False
    mode: str = "UNKNOWN"
    position_ned: Optional[Position] = None
    position_gps: Optional[GPSPosition] = None
    battery_voltage: float = 0.0
    battery_percent: float = 0.0
    heading_deg: float = 0.0
    velocity: Optional[list] = None   # [vn, ve, vd] m/s
    
    def to_dict(self) -> dict:
        return {
            "armed": self.armed,
            "in_air": self.in_air,
            "mode": self.mode,
            "position_ned": self.position_ned.to_list() if self.position_ned else None,
            "position_gps": {"lat": self.position_gps.lat, "lon": self.position_gps.lon, "alt": self.position_gps.alt} if self.position_gps else None,
            "battery_voltage": self.battery_voltage,
            "battery_percent": self.battery_percent,
            "heading_deg": self.heading_deg,
        }


@dataclass
class ActionResult:
    """操作结果"""
    success: bool
    message: str = ""
    data: dict = field(default_factory=dict)
    duration: float = 0.0


# ── 仿真适配器抽象基类 ────────────────────────────────────────────────────────

class SimAdapter(ABC):
    """
    仿真环境适配器抽象基类。
    
    所有具体仿真环境（PX4/AirSim/ROS2/Mock）必须实现此接口。
    硬技能只调用此接口的方法，不直接操作仿真 API。
    
    生命周期:
        connect() → [takeoff/fly_to/land/...] → disconnect()
    """
    
    # ── 适配器元信息（子类覆盖）──────────────────────────────────────────────
    name: str = "base"
    description: str = "Base adapter"
    supported_vehicles: list = []   # e.g. ["multirotor", "fixedwing", "rover"]
    
    # ── 连接管理 ──────────────────────────────────────────────────────────────
    
    @abstractmethod
    def connect(self, connection_str: str = "", timeout: float = 15.0) -> bool:
        """连接仿真环境。返回是否成功。"""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """断开连接。"""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """当前是否连接。"""
        pass
    
    # ── 状态查询 ──────────────────────────────────────────────────────────────
    
    @abstractmethod
    def get_state(self) -> VehicleState:
        """获取飞行器当前完整状态。"""
        pass
    
    @abstractmethod
    def get_position(self) -> Position:
        """获取当前 NED 位置。"""
        pass
    
    @abstractmethod
    def get_gps(self) -> GPSPosition:
        """获取当前 GPS 位置。"""
        pass
    
    @abstractmethod
    def get_battery(self) -> tuple:
        """获取电池状态。返回 (voltage_v, percent_0to1)。"""
        pass
    
    @abstractmethod
    def is_armed(self) -> bool:
        pass
    
    @abstractmethod
    def is_in_air(self) -> bool:
        pass
    
    # ── 基本飞行操作 ──────────────────────────────────────────────────────────
    
    @abstractmethod
    def arm(self) -> ActionResult:
        """解锁电机。"""
        pass
    
    @abstractmethod
    def disarm(self) -> ActionResult:
        """上锁电机。"""
        pass
    
    @abstractmethod
    def takeoff(self, altitude: float = 5.0) -> ActionResult:
        """
        起飞到指定高度。
        包括 ARM（如果未 ARM）+ 起飞 + 等待到达目标高度。
        """
        pass
    
    @abstractmethod
    def land(self) -> ActionResult:
        """降落到地面，等待落地。"""
        pass
    
    @abstractmethod
    def fly_to_ned(self, north: float, east: float, down: float, speed: float = 2.0) -> ActionResult:
        """
        飞到指定 NED 坐标。
        使用 Offboard/guided 模式。
        """
        pass
    
    @abstractmethod
    def hover(self, duration: float = 5.0) -> ActionResult:
        """在当前位置悬停指定秒数。"""
        pass
    
    @abstractmethod
    def return_to_launch(self) -> ActionResult:
        """返航到起飞点并降落。"""
        pass
    
    # ── 可选扩展接口 ──────────────────────────────────────────────────────────
    
    def fly_to_gps(self, lat: float, lon: float, alt: float, speed: float = 2.0) -> ActionResult:
        """飞到指定 GPS 坐标（可选实现）。"""
        return ActionResult(success=False, message="fly_to_gps not implemented")
    
    def set_heading(self, heading_deg: float) -> ActionResult:
        """设置航向角（可选实现）。"""
        return ActionResult(success=False, message="set_heading not implemented")
    
    def orbit(self, radius: float, velocity: float, center: Position = None) -> ActionResult:
        """绕点飞行（可选实现）。"""
        return ActionResult(success=False, message="orbit not implemented")
    
    def goto_waypoints(self, waypoints: list, speed: float = 2.0) -> ActionResult:
        """按航点列表依次飞行（可选实现）。"""
        for i, wp in enumerate(waypoints):
            result = self.fly_to_ned(wp[0], wp[1], wp[2], speed)
            if not result.success:
                return ActionResult(success=False, message=f"Failed at waypoint {i}: {result.message}")
        return ActionResult(success=True, message=f"Completed {len(waypoints)} waypoints")
