# Adapter Guide — 硬件适配层接入指南

AerialClaw 通过 Adapter 模式实现硬件抽象，所有飞行控制操作通过统一接口调用。

## Adapter Interface

适配器通过 `adapters/adapter_manager.py` 注册和切换。当前仓库没有单独的 base adapter 源文件；内置适配器以 `adapters/sim_adapter.py` 中的 `SimAdapter` 数据结构和方法约定为基线，并由 `skills/motor_skills.py` 通过 `get_adapter()` 调用。

新适配器至少应提供运动技能实际使用的同步方法：

```python
class MyAdapter:
    name = "my_device"
    description = "My hardware or simulator adapter"
    supported_vehicles = ["UAV"]

    def connect(self, connection_str: str = "", timeout: float = 15.0) -> bool: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...
    def is_armed(self) -> bool: ...
    def is_in_air(self) -> bool: ...
    def takeoff(self, altitude: float) -> bool: ...
    def land(self) -> bool: ...
    def fly_to(self, north: float, east: float, down: float, speed: float = 5.0) -> bool: ...
    def hover(self, duration: float = 1.0) -> bool: ...
    def return_to_launch(self) -> bool: ...
    def get_position(self): ...
    def get_battery(self) -> float: ...
    def get_state(self): ...
```

## Existing Adapters

| Adapter | File | Use Case |
|---------|------|----------|
| `PX4Adapter` | `adapters/px4_adapter.py` | PX4 SITL / real PX4 via MAVSDK |
| `SimAdapter` | `adapters/sim_adapter.py` | Gazebo simulation bridge |
| `MockAdapter` | `adapters/mock_adapter.py` | Testing without hardware |

## Adding a New Adapter

1. Create a new adapter module under `adapters/`.
2. Implement the interface methods above. Use `adapters/mock_adapter.py` and `adapters/px4_adapter.py` as concrete references.
3. Register it in `adapters/adapter_manager.py`:

```python
from adapters.my_adapter import MyAdapter
register_adapter("my_device", MyAdapter)
```

4. Start the server or switch at runtime with that adapter name, for example `SIM_ADAPTER=my_device python server.py` if your startup path reads `SIM_ADAPTER`.

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
