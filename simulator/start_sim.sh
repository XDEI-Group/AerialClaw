#!/bin/bash
# ============================================================
# start_sim.sh — AerialClaw 仿真设备一键启动
#
# 用法:
#   ./start_sim.sh                    # 启动仿真 + 连接控制台
#   ./start_sim.sh --no-gui           # 不启动 Gazebo GUI
#   ./start_sim.sh --server URL       # 指定控制台地址
#   ./start_sim.sh --world default    # 指定 Gazebo 场景
#
# 前提:
#   1. PX4-Autopilot 已编译 (在 openrobot 或 AerialClaw 目录下)
#   2. AerialClaw server.py 已启动
#
# 关键经验 (踩过的坑):
#   - macOS 上 gz sim 必须分开跑 server(-s) 和 gui(-g)
#   - make px4_sitl gz_x500 会硬编码模型名，无法覆盖
#   - 必须用 STANDALONE 模式 + PX4_SIM_MODEL 才能指定自定义模型
#   - 模型 x500_lidar_2d_cam 在 ~/.simulation-gazebo/models/ 里
#     (不是 x500_sensor，那个 joint 有问题)
#   - PX4 实例锁文件在 /tmp，残留会导致 "already running"
# ============================================================

set -e

# ── 配置 ──
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AC_DIR="$(dirname "$SCRIPT_DIR")"

# 查找 PX4 目录 (优先 AerialClaw 下，其次 openrobot)
if [ -d "$AC_DIR/PX4-Autopilot/build/px4_sitl_default" ]; then
    PX4_DIR="$AC_DIR/PX4-Autopilot"
elif [ -d "$(dirname "$AC_DIR")/openrobot/PX4-Autopilot/build/px4_sitl_default" ]; then
    PX4_DIR="$(dirname "$AC_DIR")/openrobot/PX4-Autopilot"
else
    echo "❌ 找不到 PX4-Autopilot (需要先编译)"
    echo "   参考: docs/SIMULATION_SETUP.md"
    exit 1
fi

BUILD_DIR="$PX4_DIR/build/px4_sitl_default"
WORLD="${WORLD:-urban_rescue}"
SERVER="${SERVER:-http://127.0.0.1:5001}"
MODEL="x500_lidar_2d_cam"  # 带5摄像头+LiDAR的模型
GUI=true

# 解析参数
for arg in "$@"; do
    case $arg in
        --no-gui) GUI=false ;;
        --server=*) SERVER="${arg#*=}" ;;
        --server) shift; SERVER="$1" ;;
        --world=*) WORLD="${arg#*=}" ;;
        --world) shift; WORLD="$1" ;;
    esac
    shift 2>/dev/null || true
done

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[SIM]${NC} $1"; }
warn() { echo -e "${YELLOW}[SIM]${NC} $1"; }
err()  { echo -e "${RED}[SIM]${NC} $1"; }

# ── 清理 ──
cleanup() {
    log "清理进程..."
    kill $PX4_PID $GZ_PID $GUI_PID $DDS_PID $SIM_CLIENT_PID 2>/dev/null
    wait 2>/dev/null
    log "已退出"
}
trap cleanup EXIT INT TERM

# ── 环境变量 ──
export PX4_GZ_MODELS="$PX4_DIR/Tools/simulation/gz/models"
export PX4_GZ_WORLDS="$PX4_DIR/Tools/simulation/gz/worlds"
export GZ_SIM_RESOURCE_PATH="${HOME}/.simulation-gazebo/models:${PX4_GZ_MODELS}:${PX4_GZ_WORLDS}"
export PX4_SYS_AUTOSTART=4001
export PX4_SIMULATOR=gz
export PX4_GZ_WORLD="$WORLD"
export PX4_SIM_MODEL="$MODEL"
export PX4_GZ_STANDALONE=1
export CMAKE_POLICY_VERSION_MINIMUM=3.5

log "=== AerialClaw 仿真设备启动 ==="
log "PX4 目录: $PX4_DIR"
log "模型: $MODEL (5摄像头 + LiDAR)"
log "场景: $WORLD"
log "控制台: $SERVER"
echo ""

# ── 1. DDS Agent ──
log "启动 DDS Agent..."
MicroXRCEAgent udp4 -p 8888 > /tmp/dds.log 2>&1 &
DDS_PID=$!
sleep 2

# ── 2. Gazebo Server ──
WORLD_FILE="$PX4_GZ_WORLDS/${WORLD}.sdf"
if [ ! -f "$WORLD_FILE" ]; then
    # 尝试 AerialClaw 的 worlds 目录
    WORLD_FILE="$AC_DIR/sim/worlds/${WORLD}.sdf"
fi
if [ ! -f "$WORLD_FILE" ]; then
    err "场景文件不存在: $WORLD_FILE"
    exit 1
fi

log "启动 Gazebo Server (场景: $WORLD)..."
gz sim --verbose=0 -r -s "$WORLD_FILE" > /tmp/gz.log 2>&1 &
GZ_PID=$!
sleep 8

# ── 3. PX4 SITL ──
log "启动 PX4 SITL (模型: $MODEL)..."
cd "$BUILD_DIR/rootfs"
"$BUILD_DIR/bin/px4" "$BUILD_DIR/rootfs" -s etc/init.d-posix/rcS < /dev/null > /tmp/px4.log 2>&1 &
PX4_PID=$!
sleep 8

# ── 4. 验证 ──
if gz topic -l 2>/dev/null | grep -q "cam_front"; then
    log "✅ 摄像头话题已发布"
else
    warn "⚠️ 未检测到摄像头话题"
fi

if gz topic -l 2>/dev/null | grep -q "lidar"; then
    log "✅ LiDAR 话题已发布"
else
    warn "⚠️ 未检测到 LiDAR 话题"
fi

# ── 5. Gazebo GUI ──
if $GUI; then
    log "启动 Gazebo GUI..."
    gz sim -g > /tmp/gz_gui.log 2>&1 &
    GUI_PID=$!
    sleep 2
fi

# ── 6. 连接控制台 ──
log "启动仿真客户端，连接控制台 $SERVER ..."
cd "$AC_DIR/simulator"
python3 sim_client.py --server "$SERVER" > /tmp/sim_client.log 2>&1 &
SIM_CLIENT_PID=$!
sleep 5

if tail -3 /tmp/sim_client.log | grep -q "注册成功"; then
    log "✅ 仿真设备已注册到控制台"
else
    warn "⚠️ 仿真设备注册可能失败，检查 /tmp/sim_client.log"
fi

log ""
log "=== 仿真运行中 ==="
log "  Gazebo GUI: $(if $GUI; then echo '已启动'; else echo '未启动 (--no-gui)'; fi)"
log "  PX4 日志: /tmp/px4.log"
log "  Gazebo 日志: /tmp/gz.log"
log "  sim_client 日志: /tmp/sim_client.log"
log "  按 Ctrl+C 退出"
log ""

# 等待
wait
