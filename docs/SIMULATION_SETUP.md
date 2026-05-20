# Simulation Setup Guide — 仿真环境搭建指南

AerialClaw 的仿真环境基于 **PX4 SITL + Gazebo Harmonic**，本文档提供完整的搭建步骤。

## Prerequisites / 前置依赖

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | >= 3.10 | Core runtime |
| CMake | >= 3.22 | PX4 compilation |
| Gazebo Harmonic | gz sim 8.x | 3D simulation |
| PX4 Autopilot | v1.15+ | Flight controller SITL |
| Micro XRCE-DDS Agent | latest | PX4 ↔ ROS2 bridge |
| MAVSDK | latest | Drone control API |

## Step 1: Install Gazebo Harmonic

### macOS
```bash
brew tap osrf/simulation
brew install gz-harmonic
# Verify
gz sim --version  # should show 8.x
```

### Ubuntu 22.04
```bash
sudo apt install -y gz-harmonic
```

## Step 2: Clone and Build PX4

```bash
# Clone PX4 inside the AerialClaw project (or anywhere you prefer)
git clone https://github.com/PX4/PX4-Autopilot.git --recursive
cd PX4-Autopilot
git checkout v1.15.4  # or latest v1.15.x

# Install dependencies
bash Tools/setup/ubuntu.sh  # Ubuntu
# or for macOS: install build tools manually (see Troubleshooting below)

# Build for SITL with Gazebo
make px4_sitl gz_x500
```

### macOS ARM64 Known Issues

If building on Apple Silicon (M1/M2/M3/M4):

```bash
# Fix 1: CMake version compatibility
export CMAKE_POLICY_VERSION_MINIMUM=3.5

# Fix 2: If protobuf issues, use brew's version
brew install protobuf@33
export PKG_CONFIG_PATH="/opt/homebrew/Cellar/protobuf@33/33.5/lib/pkgconfig"

# Fix 3: VLA compilation errors
# Add to CMakeLists.txt or use:
export CFLAGS="-Wno-vla"
export CXXFLAGS="-Wno-vla -Wno-error=attributes"

# Then build
cd PX4-Autopilot
export CMAKE_POLICY_VERSION_MINIMUM=3.5
make px4_sitl gz_x500
```

## Step 3: Install Micro XRCE-DDS Agent

```bash
git clone https://github.com/eProsima/Micro-XRCE-DDS-Agent.git
cd Micro-XRCE-DDS-Agent
mkdir build && cd build
cmake .. -DUAGENT_SOCKETCAN_PROFILE=OFF
make -j$(nproc)
sudo make install
# or just use the binary directly: ./MicroXRCEAgent
```

## Step 4: Install MAVSDK

```bash
# Python SDK (for AerialClaw)
pip install mavsdk

# MAVSDK Server binary
# Download from: https://github.com/mavlink/MAVSDK/releases
# Or build from source
```

## Step 5: Download Gazebo Models

```bash
# PX4 Gazebo models (required for drone model)
# These are usually cloned with PX4-Autopilot

# Additional models for custom worlds
mkdir -p ~/.simulation-gazebo/models
# Download from https://github.com/PX4/PX4-gazebo-models if needed
```

## Running the Simulation

### Quick Start (recommended)

```bash
# Using PX4's built-in launch (manages Gazebo automatically)
cd PX4-Autopilot
export CMAKE_POLICY_VERSION_MINIMUM=3.5
export PX4_GZ_WORLD=default      # or: urban_rescue
make px4_sitl gz_x500
```

### Manual Start (advanced)

```bash
# Terminal 1: DDS Agent
MicroXRCEAgent udp4 -p 8888

# Terminal 2: Gazebo (headless)
export PX4_GZ_MODELS="<PX4_DIR>/Tools/simulation/gz/models"
export PX4_GZ_WORLDS="<PX4_DIR>/Tools/simulation/gz/worlds"
export GZ_SIM_RESOURCE_PATH="$HOME/.simulation-gazebo/models:$PX4_GZ_MODELS:$PX4_GZ_WORLDS"
gz sim --verbose=1 -r -s "${PX4_GZ_WORLDS}/default.sdf"    # server only
# gz sim -g                                                  # GUI (optional, separate terminal)

# Terminal 3: PX4 SITL (STANDALONE mode — connects to already-running Gazebo)
export PX4_SYS_AUTOSTART=4001
export PX4_SIMULATOR=gz
export PX4_GZ_WORLD=default
export PX4_SIM_MODEL=x500
export PX4_GZ_STANDALONE=1
PX4_BUILD="<PX4_DIR>/build/px4_sitl_default"
cd "$PX4_BUILD"
./bin/px4 "$PX4_BUILD" -s "${PX4_BUILD}/etc/init.d-posix/rcS"

# Terminal 4: AerialClaw
cd AerialClaw
source venv/bin/activate
python server.py
# Open http://localhost:5001
```

> **Important**: Use STANDALONE mode (`PX4_GZ_STANDALONE=1`) with `bin/px4` directly.
> The `make px4_sitl gz_x500` shortcut works for basic testing. Custom sensor models can be used when the corresponding Gazebo model files are available locally and `PX4_SIM_MODEL` is set accordingly.

### Using the start script (recommended)

```bash
# First time: set up PX4 environment
./scripts/setup_px4.sh

# Launch simulation (DDS Agent + Gazebo + PX4 SITL)
./scripts/start_sim.sh              # default world
./scripts/start_sim.sh urban_rescue  # urban rescue scenario

# In another terminal:
source venv/bin/activate
python server.py
# Open http://localhost:5001
```

## Sensor Configuration

### Default Sensor Setup

The default reviewer path uses PX4/Gazebo standard `x500`. Camera/LiDAR streaming requires a sensor-enabled Gazebo model. If you provide a local custom model, set `PX4_SIM_MODEL` to that model name and ensure Gazebo can resolve its SDF files.
The Web console does **not** read Gazebo topics directly. `sim/gz_sensor_bridge.py`
subscribes to Gazebo Transport camera/LiDAR topics and `server.py` forwards the
latest frames to the UI via Socket.IO events (`sensor_cameras`, `sensor_lidar`).

### Customizing Sensors

To modify the sensor configuration:
1. Add or edit your PX4/Gazebo model SDF files in a Gazebo model path.
2. Modify camera/LiDAR parameters in the model files if needed.
3. Update topic names in `sim/gz_sensor_bridge.py` if your sensor/link names change.

## Key PX4 Parameters

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `PX4_SYS_AUTOSTART` | 4001 | Gazebo X500 airframe |
| `COM_DISARM_PRFLT` | 10 | Auto-disarm after 10s if no takeoff |
| `MAV_SYS_ID` | 1 | MAVLink system ID |

**Important**: After arming, send the takeoff command within 10 seconds, or PX4 will auto-disarm.

## MAVLink Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 14540 | UDP | MAVSDK / Offboard control |
| 14550 | UDP | QGroundControl |

## Coordinate System

AerialClaw uses **NED** (North-East-Down):
- Gazebo uses ENU (X=East, Y=North, Z=Up)
- Conversion: `NED.North = Gazebo.Y, NED.East = Gazebo.X, NED.Down = -Gazebo.Z`
- All positions in `robot_profile/WORLD_MAP.md` and skill parameters use NED

## Troubleshooting

### Gazebo won't start
- Check `gz sim --version` works
- Ensure `GZ_SIM_RESOURCE_PATH` includes model directories
- Try `gz sim --verbose=4` for detailed logs

### PX4 can't connect to Gazebo
- Make sure Gazebo is running before PX4 (or use `make px4_sitl gz_x500`)
- Check `PX4_GZ_STANDALONE=1` is set when using manual start
- Verify DDS Agent is running: `MicroXRCEAgent udp4 -p 8888`

### Web console camera/LiDAR panels show `NO SIGNAL`

`gz topic -l` showing camera or LiDAR topics only proves Gazebo is publishing.
AerialClaw still needs the backend sensor bridge to subscribe to those topics and
push Socket.IO frames to the browser.

Check the full path:

```bash
# Gazebo should expose camera/LiDAR topics
gz topic -l | grep -Ei 'camera|image|lidar|scan'

# Start backend with PX4+Gazebo adapter
SIM_ADAPTER=px4 PX4_GZ_WORLD=urban_rescue PX4_SIM_MODEL=x500 python server.py

# After connecting the adapter, check bridge status
curl http://localhost:5001/api/sensor/status
```

Expected backend log after the adapter connects:

```text
传感器桥接启动 (world=urban_rescue, model=x500_0)
传感器数据推送线程已启动
```

If status says the bridge is unavailable:
- install / expose Gazebo Harmonic Python bindings (`gz.transport13`, `gz.msgs10`)
- verify `PX4_GZ_WORLD` matches your running world
- verify `PX4_SIM_MODEL` matches the spawned model base name; PX4/Gazebo commonly appends `_0` to the spawned model
- if you renamed links/sensors, update `sim/gz_sensor_bridge.py` topic templates

### MAVSDK connection fails
- Start `mavsdk_server` separately, don't rely on auto-start
- Don't kill `mavsdk_server` when restarting `server.py`
- Check port 14540 is not occupied: `lsof -i :14540`

### macOS: PX4 build fails
- See "macOS ARM64 Known Issues" above
- Python version: use 3.10-3.12 (3.14 may have dataclass compatibility issues)
- Proxy for GitHub: `export https_proxy=http://127.0.0.1:7897` if needed
