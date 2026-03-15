# AerialClaw Simulator — 仿真设备端

仿真无人机作为一个"设备"，通过通用设备协议连接 AerialClaw 控制端。

## 前提

- PX4 SITL + Gazebo Harmonic 已安装（参考 `docs/SIMULATION_SETUP.md`）
- AerialClaw 控制端已启动

## 使用

```bash
# 终端 1: 启动控制端
cd AerialClaw_2.0
python server.py

# 终端 2: 启动仿真设备
cd AerialClaw_2.0/simulator
python sim_client.py --server http://localhost:5001 --world urban_rescue
```

## 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--server` | `http://localhost:5001` | 控制端地址 |
| `--device-id` | `SIM_UAV_1` | 设备 ID |
| `--world` | `default` | Gazebo 场景 |
| `--no-sim` | - | 不自动启动仿真，手动管理 PX4+Gazebo |

## 工作流程

```
sim_client.py 启动
  ├── 连接 MAVSDK (PX4)
  ├── 连接 Gazebo 传感器
  ├── POST /api/device/register → 获取 token
  ├── WebSocket 连接控制端
  └── 主循环:
       ├── 每 5s → 心跳
       ├── 每 1s → 上报遥测 (位置/电量/状态)
       ├── 每 0.5s → 上报传感器 (相机/LiDAR)
       └── 收到 device_action → MAVSDK 执行 → 回报结果
```
