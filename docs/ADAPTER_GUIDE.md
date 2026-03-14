# Adapter Guide — 硬件适配层接入指南

AerialClaw 通过 Adapter 模式实现硬件抽象，所有飞行控制操作通过统一接口调用。

## BaseAdapter Interface

所有适配器必须继承 `adapters/base_adapter.py` 中的 `BaseAdapter`，实现以下方法：

```python
class BaseAdapter:
    """Hardware abstraction interface."""

    async def connect(self) -> bool:
        """Connect to the drone. Return True on success."""

    async def arm(self) -> bool:
        """Arm the drone motors."""

    async def takeoff(self, altitude: float) -> bool:
        """Take off to specified altitude (meters, positive up)."""

    async def land(self) -> bool:
        """Land at current position."""

    async def fly_to(self, north: float, east: float, down: float, speed: float) -> bool:
        """Fly to NED position at given speed."""

    async def get_position(self) -> tuple[float, float, float]:
        """Return current position as (north, east, down) in meters."""

    async def get_battery(self) -> float:
        """Return battery percentage (0-100)."""

    async def get_heading(self) -> float:
        """Return current heading in degrees (0-360)."""

    async def set_heading(self, heading: float) -> bool:
        """Rotate to specified heading."""

    async def hover(self, duration: float) -> bool:
        """Hold current position for duration seconds."""

    async def return_to_launch(self) -> bool:
        """Return to takeoff position and land."""
```

## Existing Adapters

| Adapter | File | Use Case |
|---------|------|----------|
| `PX4Adapter` | `adapters/px4_adapter.py` | PX4 SITL / real PX4 via MAVSDK |
| `SimAdapter` | `adapters/sim_adapter.py` | Gazebo simulation bridge |
| `MockAdapter` | `adapters/mock_adapter.py` | Testing without hardware |

## Adding a New Adapter

1. Create `adapters/my_adapter.py`
2. Inherit from `BaseAdapter`
3. Implement all abstract methods
4. Register in `adapters/adapter_factory.py`:

```python
# adapter_factory.py
from adapters.my_adapter import MyAdapter

ADAPTERS = {
    "px4": PX4Adapter,
    "sim": SimAdapter,
    "mock": MockAdapter,
    "my_device": MyAdapter,  # ← add here
}
```

5. Use it in your config or startup code

## Coordinate System

AerialClaw uses **NED (North-East-Down)** coordinates internally:
- X = North (positive forward)
- Y = East (positive right)
- Z = Down (positive downward, so altitude is negative Z)

If your hardware uses a different frame (e.g., ENU), convert in your adapter.

## MockAdapter for Development

The `MockAdapter` simulates drone responses without any hardware:

```python
from adapters.mock_adapter import MockAdapter

adapter = MockAdapter()
await adapter.connect()
await adapter.takeoff(10)       # simulated takeoff
pos = await adapter.get_position()  # returns simulated position
```

This allows full agent loop development and testing on any machine.
