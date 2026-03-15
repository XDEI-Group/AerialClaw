# AerialClaw Simulator — 仿真设备端

仿真无人机作为一个"设备"，通过通用设备协议连接 AerialClaw 控制端。

## 一键启动

```bash
# 前提: AerialClaw 控制台已启动 (python server.py)

# 默认启动 (urban_rescue 场景 + GUI + 连接 localhost:5001)
cd AerialClaw_2.0/simulator
./start_sim.sh

# 不要 GUI
./start_sim.sh --no-gui

# 指定控制台地址
./start_sim.sh --server http://10.195.196.228:5001

# 指定场景
./start_sim.sh --world default
```

## 手动启动 (分步)

如果一键脚本有问题，按以下顺序手动启动：

```bash
# ⚠️ 重要: 必须用 STANDALONE 模式，不要用 make px4_sitl gz_xxx
# make 命令会硬编码模型名，无法使用自定义模型

# 0. 设置环境变量
PX4_DIR=~/PyCharmMiscProject/openrobot/PX4-Autopilot
export PX4_GZ_MODELS="$PX4_DIR/Tools/simulation/gz/models"
export PX4_GZ_WORLDS="$PX4_DIR/Tools/simulation/gz/worlds"
export GZ_SIM_RESOURCE_PATH="$HOME/.simulation-gazebo/models:$PX4_GZ_MODELS:$PX4_GZ_WORLDS"
export PX4_SYS_AUTOSTART=4001
export PX4_SIMULATOR=gz
export PX4_GZ_WORLD=urban_rescue
export PX4_SIM_MODEL=x500_lidar_2d_cam    # ← 带摄像头+LiDAR的模型
export PX4_GZ_STANDALONE=1
export CMAKE_POLICY_VERSION_MINIMUM=3.5

# 1. DDS Agent (终端 1)
MicroXRCEAgent udp4 -p 8888

# 2. Gazebo Server (终端 2, macOS 必须 -s 分开)
gz sim --verbose=0 -r -s "$PX4_GZ_WORLDS/urban_rescue.sdf"

# 3. PX4 SITL (终端 3)
cd $PX4_DIR/build/px4_sitl_default/rootfs
../bin/px4 . -s etc/init.d-posix/rcS

# 4. Gazebo GUI (终端 4, 可选)
gz sim -g

# 5. 仿真客户端 (终端 5)
cd AerialClaw_2.0/simulator
python3 sim_client.py --server http://127.0.0.1:5001
```

## 已知问题和解决方案

### ❌ `make px4_sitl gz_x500_lidar_2d_cam` 报 No rule to make target
**原因**: PX4 的 CMake 没有这个 target，只有 `gz_x500`
**解决**: 不用 make，用 STANDALONE 模式手动启动 (见上方)

### ❌ Gazebo 报 `CameraJoint` / `LidarJoint` 帧不存在
**原因**: 使用了 `x500_sensor` 自定义模型，joint 引用有问题
**解决**: 使用 `x500_lidar_2d_cam` 模型 (在 `~/.simulation-gazebo/models/`)，这个是验证通过的

### ❌ macOS 上 `gz sim` 报错 "cannot run both server and gui"
**原因**: macOS 不支持同一进程跑 server + gui
**解决**: 分开启动 `gz sim -s` (server) 和 `gz sim -g` (gui)

### ❌ PX4 报 "already running for instance 0"
**原因**: 上次 PX4 没正常退出，锁文件残留
**解决**: `pkill -9 -f "bin/px4"` 然后重启

### ❌ 模型 spawn 了但没有摄像头/LiDAR
**原因**: 使用了默认 x500 模型而不是 x500_lidar_2d_cam
**解决**: 确保 `PX4_SIM_MODEL=x500_lidar_2d_cam`

### ❌ sim_client 注册报 409 Conflict
**原因**: 设备已注册（server 重启后 sim_client 没重启）
**解决**: 重启 sim_client，或重启 server.py

## 模型说明

| 模型 | 说明 | 传感器 |
|------|------|--------|
| `x500` | 默认四旋翼 | IMU + GPS + 气压计 |
| `x500_lidar_2d_cam` ✅ | **推荐** 带传感器 | 5 摄像头 + 2D LiDAR + IMU + GPS |
| `x500_sensor` ❌ | 自定义(有问题) | joint 引用错误，不要用 |

## 文件说明

```
simulator/
├── start_sim.sh      # 一键启动脚本
├── sim_client.py      # 仿真设备客户端 (完全独立，不依赖控制端代码)
├── requirements.txt   # 依赖: mavsdk + socketio + requests
└── README.md          # 本文件
```
