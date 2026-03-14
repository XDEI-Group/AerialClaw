"""
mock_adapter.py
Mock 仿真适配器 —— 纯内存模拟，不依赖任何外部仿真环境。
用于单元测试、离线开发、CI/CD。
"""

import time
import logging
from adapters.sim_adapter import SimAdapter, Position, GPSPosition, VehicleState, ActionResult

logger = logging.getLogger(__name__)


class MockAdapter(SimAdapter):
    """Mock 仿真适配器，所有操作纯内存模拟。"""

    name = "mock"
    description = "Mock adapter (in-memory simulation, no external dependencies)"
    supported_vehicles = ["multirotor", "fixedwing", "rover"]

    def __init__(self):
        self._connected = False
        self._armed = False
        self._in_air = False
        self._position = Position(0, 0, 0)
        self._battery = (12.6, 1.0)

    def connect(self, connection_str="mock://", timeout=1.0) -> bool:
        self._connected = True
        logger.info("MockAdapter: ✅ 已连接 (mock)")
        return True

    def disconnect(self):
        self._connected = False

    def is_connected(self):
        return self._connected

    def get_state(self) -> VehicleState:
        return VehicleState(
            armed=self._armed, in_air=self._in_air, mode="MOCK",
            position_ned=self._position,
            position_gps=GPSPosition(47.397971, 8.546163, self._position.altitude),
            battery_voltage=self._battery[0], battery_percent=self._battery[1],
        )

    def get_position(self) -> Position:
        return self._position

    def get_gps(self) -> GPSPosition:
        return GPSPosition(47.397971, 8.546163, self._position.altitude)

    def get_battery(self) -> tuple:
        return self._battery

    def is_armed(self) -> bool:
        return self._armed

    def is_in_air(self) -> bool:
        return self._in_air

    def arm(self) -> ActionResult:
        self._armed = True
        return ActionResult(True, "ARM (mock)")

    def disarm(self) -> ActionResult:
        self._armed = False
        return ActionResult(True, "DISARM (mock)")

    def takeoff(self, altitude=5.0) -> ActionResult:
        self._armed = True
        self._in_air = True
        self._position = Position(0, 0, -altitude)
        time.sleep(0.1)
        return ActionResult(True, f"起飞到 {altitude}m (mock)", {"altitude": altitude}, 0.1)

    def land(self) -> ActionResult:
        self._in_air = False
        self._position = Position(self._position.north, self._position.east, 0)
        self._armed = False
        time.sleep(0.1)
        return ActionResult(True, "降落 (mock)", duration=0.1)

    def fly_to_ned(self, north, east, down, speed=2.0) -> ActionResult:
        self._position = Position(north, east, down)
        dist = (north**2 + east**2 + down**2) ** 0.5
        dur = dist / speed if speed > 0 else 0.1
        time.sleep(min(dur, 0.5))
        return ActionResult(True, f"到达 NED=({north},{east},{down}) (mock)",
                          {"position": [north, east, down]}, round(dur, 2))

    def hover(self, duration=5.0) -> ActionResult:
        time.sleep(min(duration, 0.5))
        return ActionResult(True, f"悬停 {duration}s (mock)",
                          {"position": self._position.to_list()}, duration)

    def return_to_launch(self) -> ActionResult:
        self._position = Position(0, 0, 0)
        self._in_air = False
        self._armed = False
        return ActionResult(True, "RTL (mock)", duration=0.1)
