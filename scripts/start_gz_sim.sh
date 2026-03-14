#!/bin/bash
# ============================================================
# start_gz_sim.sh — PX4 SITL + Gazebo Harmonic 一键启动
#
# 用法:
#   ./start_gz_sim.sh              # default world + GUI
#   ./start_gz_sim.sh urban_rescue # urban_rescue world + GUI
#   HEADLESS=1 ./start_gz_sim.sh   # 无 GUI
#
# 停止: Ctrl+C
# ============================================================

# PX4 directory — set this to your PX4-Autopilot clone location
# PX4 目录 — 设置为你的 PX4-Autopilot 克隆路径
PX4_DIR="${PX4_DIR:-$(cd "$(dirname "$0")/.." && pwd)/PX4-Autopilot}"
BUILD_DIR="${PX4_DIR}/build/px4_sitl_default"
ROOTFS="${BUILD_DIR}/rootfs"
LOG_DIR="/tmp/aerialclaw_sim"
WORLD="${1:-default}"

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[SIM]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; }
die()  { err "$1"; exit 1; }

DDS_PID="" ; GZ_PID="" ; GUI_PID="" ; PX4_PID=""

cleanup() {
    log "清理进程..."
    [ -n "$PX4_PID" ] && kill "$PX4_PID" 2>/dev/null
    [ -n "$GUI_PID" ] && kill "$GUI_PID" 2>/dev/null
    [ -n "$GZ_PID"  ] && kill "$GZ_PID"  2>/dev/null
    [ -n "$DDS_PID" ] && kill "$DDS_PID" 2>/dev/null
    sleep 1
    pkill -f "gz sim" 2>/dev/null || true
    pkill -f "px4-gz_bridge" 2>/dev/null || true
    pkill -f "ruby.*gz" 2>/dev/null || true
    pkill -f "bin/px4" 2>/dev/null || true
    pkill -f "MicroXRCEAgent" 2>/dev/null || true
    log "已停止"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── 预检 ─────────────────────────────────────────────────────
WORLD_SDF="${PX4_DIR}/Tools/simulation/gz/worlds/${WORLD}.sdf"
[ -f "$WORLD_SDF" ]            || die "World 文件不存在: $WORLD_SDF"
[ -x "${BUILD_DIR}/bin/px4" ]  || die "PX4 二进制不存在"
command -v gz >/dev/null        || die "gz (Gazebo) 未安装"
command -v MicroXRCEAgent >/dev/null || die "MicroXRCEAgent 未安装"

# ── 杀掉残留 ─────────────────────────────────────────────────
log "清理残留进程..."
pkill -9 -f "gz sim" 2>/dev/null || true
pkill -9 -f "px4-gz_bridge" 2>/dev/null || true
pkill -9 -f "ruby.*gz" 2>/dev/null || true
pkill -9 -f "bin/px4" 2>/dev/null || true
pkill -9 -f "MicroXRCEAgent" 2>/dev/null || true
sleep 2

mkdir -p "$LOG_DIR"

# ── 环境变量 ─────────────────────────────────────────────────
export PX4_GZ_MODELS="${PX4_DIR}/Tools/simulation/gz/models"
export PX4_GZ_WORLDS="${PX4_DIR}/Tools/simulation/gz/worlds"
export GZ_SIM_RESOURCE_PATH="${HOME}/.simulation-gazebo/models:${PX4_GZ_MODELS}:${PX4_GZ_WORLDS}"
export PKG_CONFIG_PATH="/opt/homebrew/Cellar/protobuf@33/33.5/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export PX4_SYS_AUTOSTART=4001
export PX4_SIMULATOR=gz
export PX4_GZ_WORLD="$WORLD"
export PX4_SIM_MODEL=x500_lidar_2d_cam
export PX4_GZ_STANDALONE=1

# ── 1. DDS Agent ─────────────────────────────────────────────
log "启动 DDS Agent (UDP:8888)..."
MicroXRCEAgent udp4 -p 8888 > "${LOG_DIR}/dds.log" 2>&1 &
DDS_PID=$!
sleep 1
kill -0 "$DDS_PID" 2>/dev/null || die "DDS Agent 启动失败"
log "DDS Agent OK (PID $DDS_PID)"

# ── 2. Gazebo Server ────────────────────────────────────────
log "启动 Gazebo server (world: ${WORLD})..."
gz sim --verbose=0 -r -s "$WORLD_SDF" > "${LOG_DIR}/gz_server.log" 2>&1 &
GZ_PID=$!

log "等待 Gazebo world 加载 (最多 30s)..."
LOADED=0
for i in $(seq 1 30); do
    if gz topic -l 2>/dev/null | grep -q "/world/"; then
        LOADED=1
        break
    fi
    if ! kill -0 "$GZ_PID" 2>/dev/null; then
        err "Gazebo server 崩溃:"
        tail -20 "${LOG_DIR}/gz_server.log"
        cleanup
    fi
    sleep 1
done

if [ "$LOADED" = "1" ]; then
    log "Gazebo server OK (PID $GZ_PID)"
else
    err "Gazebo world 加载超时:"
    tail -20 "${LOG_DIR}/gz_server.log"
    cleanup
fi

# ── 3. Gazebo GUI ───────────────────────────────────────────
if [ "${HEADLESS:-0}" != "1" ]; then
    log "启动 Gazebo GUI..."
    gz sim -g > "${LOG_DIR}/gz_gui.log" 2>&1 &
    GUI_PID=$!
    sleep 2
    if kill -0 "$GUI_PID" 2>/dev/null; then
        log "Gazebo GUI OK (PID $GUI_PID)"
    else
        log "Gazebo GUI 未启动 (可忽略)"
    fi
fi

# ── 4. PX4 SITL ─────────────────────────────────────────────
log "启动 PX4 SITL (gz_x500, STANDALONE)..."
cd "${ROOTFS}"
"${BUILD_DIR}/bin/px4" "${ROOTFS}" -s "etc/init.d-posix/rcS" < /dev/null > "${LOG_DIR}/px4.log" 2>&1 &
PX4_PID=$!

log "等待 PX4 初始化 (最多 20s)..."
for i in $(seq 1 20); do
    if grep -q "MAVLink" "${LOG_DIR}/px4.log" 2>/dev/null; then
        break
    fi
    if ! kill -0 "$PX4_PID" 2>/dev/null; then
        err "PX4 崩溃:"
        tail -30 "${LOG_DIR}/px4.log"
        cleanup
    fi
    sleep 1
done

if kill -0 "$PX4_PID" 2>/dev/null; then
    log "PX4 SITL OK (PID $PX4_PID)"
else
    err "PX4 启动失败:"
    tail -30 "${LOG_DIR}/px4.log"
    cleanup
fi

# ── 状态 ─────────────────────────────────────────────────────
echo ""
echo "=========================================="
log "🚀 仿真环境已就绪！"
echo "=========================================="
echo ""
echo "  World:      ${WORLD}"
echo "  MAVLink:    udp://127.0.0.1:14540 (MAVSDK)"
echo "              udp://127.0.0.1:14550 (QGC)"
echo "  DDS:        udp://127.0.0.1:8888"
echo ""
echo "  日志目录:   ${LOG_DIR}/"
echo "  停止:       Ctrl+C"
echo ""

# 前台等待
wait
