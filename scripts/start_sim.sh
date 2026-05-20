#!/usr/bin/env bash
# ============================================================
# AerialClaw — Start PX4 + Gazebo Simulation
# ============================================================
#
# Usage:
#   ./scripts/start_sim.sh                         # urban_rescue + sensor model
#   ./scripts/start_sim.sh default x500            # PX4 standard fallback
#   ./scripts/start_sim.sh urban_rescue x500       # custom world + standard model
#   PX4_DIR=/path/to/PX4-Autopilot ./scripts/start_sim.sh
#
# This starts: DDS Agent + Gazebo + PX4 SITL.
# Then run in another terminal:
#   SIM_ADAPTER=px4 PX4_GZ_WORLD=<world> PX4_SIM_MODEL=<model> python server.py
# ============================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

WORLD="${1:-urban_rescue}"
MODEL="${2:-x500_lidar_2d_cam}"

if [ -d "${PROJECT_DIR}/PX4-Autopilot" ]; then
    PX4_DIR="${PX4_DIR:-${PROJECT_DIR}/PX4-Autopilot}"
elif [ -n "${PX4_DIR:-}" ]; then
    true
else
    echo "ERROR: PX4-Autopilot not found."
    echo "Next: ./scripts/setup_px4.sh"
    exit 1
fi

PX4_BIN="${PX4_DIR}/build/px4_sitl_default/bin/px4"
PX4_BUILD="${PX4_DIR}/build/px4_sitl_default"
PX4_WORLDS="${PX4_DIR}/Tools/simulation/gz/worlds"
PX4_MODELS="${PX4_DIR}/Tools/simulation/gz/models"
LOCAL_MODELS="${HOME}/.simulation-gazebo/models"

if [ ! -f "$PX4_BIN" ]; then
    echo "ERROR: PX4 binary not found at $PX4_BIN"
    echo "Next: ./scripts/setup_px4.sh"
    exit 1
fi

if ! command -v MicroXRCEAgent >/dev/null 2>&1; then
    echo "ERROR: MicroXRCEAgent not found."
    echo "Next: ./scripts/setup_px4.sh"
    exit 1
fi

if ! command -v gz >/dev/null 2>&1; then
    echo "ERROR: Gazebo CLI 'gz' not found."
    echo "macOS: brew tap osrf/simulation && brew install gz-harmonic"
    echo "Ubuntu: install gz-harmonic"
    exit 1
fi

export PX4_GZ_MODELS="$PX4_MODELS"
export PX4_GZ_WORLDS="$PX4_WORLDS"
export GZ_SIM_RESOURCE_PATH="${LOCAL_MODELS}:${PX4_MODELS}:${PX4_WORLDS}:${GZ_SIM_RESOURCE_PATH:-}"
export PX4_SYS_AUTOSTART=4001
export PX4_SIMULATOR=gz
export PX4_GZ_WORLD="$WORLD"
export PX4_SIM_MODEL="$MODEL"
export PX4_GZ_STANDALONE=1

WORLD_SDF="${PX4_WORLDS}/${WORLD}.sdf"
if [ ! -f "$WORLD_SDF" ]; then
    echo "WARNING: World file not found: $WORLD_SDF"
    echo "Available worlds:"
    find "${PX4_WORLDS}" -maxdepth 1 -name '*.sdf' -print 2>/dev/null | xargs -I{} basename {} .sdf || true
    if [ -f "${PX4_WORLDS}/default.sdf" ]; then
        echo "Falling back to world: default"
        WORLD="default"
        WORLD_SDF="${PX4_WORLDS}/default.sdf"
        export PX4_GZ_WORLD="default"
    else
        echo "ERROR: default.sdf is also missing."
        echo "Next: ./scripts/setup_px4.sh"
        exit 1
    fi
fi

if [ ! -d "${LOCAL_MODELS}/${MODEL}" ] && [ ! -d "${PX4_MODELS}/${MODEL}" ]; then
    echo "WARNING: Model '${MODEL}' not found in common Gazebo model directories."
    if [ "$MODEL" != "x500" ] && { [ -d "${LOCAL_MODELS}/x500" ] || [ -d "${PX4_MODELS}/x500" ]; }; then
        echo "Falling back to model: x500"
        MODEL="x500"
        export PX4_SIM_MODEL="x500"
    else
        echo "Continuing anyway; Gazebo/PX4 may still resolve it from another path."
    fi
fi

cleanup() {
    echo ""
    echo "Shutting down simulation..."
    pkill -f "bin/px4" 2>/dev/null || true
    pkill -f "gz sim" 2>/dev/null || true
    pkill -f MicroXRCEAgent 2>/dev/null || true
    sleep 1
    echo "Done."
}
trap cleanup EXIT INT TERM

echo "============================================================"
echo " AerialClaw Simulation Launcher"
echo " World: $WORLD | Model: $MODEL"
echo " PX4_DIR: $PX4_DIR"
echo "============================================================"
echo ""

if [ -x "${SCRIPT_DIR}/doctor_gazebo.sh" ]; then
    echo "Preflight doctor (non-live):"
    if ! "${SCRIPT_DIR}/doctor_gazebo.sh" "$WORLD" "$MODEL"; then
        echo ""
        echo "Doctor found blocking issues. Fix them or run ./scripts/setup_px4.sh, then retry."
        exit 1
    fi
    echo ""
fi

echo "[1/3] Starting Micro XRCE-DDS Agent..."
MicroXRCEAgent udp4 -p 8888 > /tmp/aerialclaw_dds.log 2>&1 &
DDS_PID=$!
sleep 1
if kill -0 "$DDS_PID" 2>/dev/null; then
    echo "  DDS Agent running (PID: $DDS_PID)"
else
    echo "ERROR: DDS Agent failed to start. Log: /tmp/aerialclaw_dds.log"
    tail -80 /tmp/aerialclaw_dds.log 2>/dev/null || true
    exit 1
fi

echo "[2/3] Starting Gazebo ($WORLD)..."
gz sim --verbose=1 -r -s "$WORLD_SDF" > /tmp/aerialclaw_gz.log 2>&1 &
GZ_PID=$!
echo "  Waiting for Gazebo to load (10s)..."
sleep 10
if kill -0 "$GZ_PID" 2>/dev/null; then
    echo "  Gazebo running (PID: $GZ_PID)"
else
    echo "ERROR: Gazebo failed to start. Log: /tmp/aerialclaw_gz.log"
    tail -120 /tmp/aerialclaw_gz.log 2>/dev/null || true
    exit 1
fi

echo "[3/3] Starting PX4 SITL..."
cd "$PX4_BUILD"
"$PX4_BIN" "$PX4_BUILD" -s "${PX4_BUILD}/etc/init.d-posix/rcS" > /tmp/aerialclaw_px4.log 2>&1 < /dev/null &
PX4_PID=$!
sleep 8
if kill -0 "$PX4_PID" 2>/dev/null; then
    echo "  PX4 SITL running (PID: $PX4_PID)"
else
    echo "ERROR: PX4 SITL failed to start. Log: /tmp/aerialclaw_px4.log"
    tail -120 /tmp/aerialclaw_px4.log 2>/dev/null || true
    exit 1
fi

echo ""
echo "============================================================"
echo " Simulation is running!"
echo ""
echo " MAVLink:  udp://:14540 (MAVSDK/Offboard)"
echo "           udp://:14550 (QGroundControl)"
echo ""
echo " In another terminal, run:"
echo "   cd ${PROJECT_DIR}"
echo "   SIM_ADAPTER=px4 PX4_GZ_WORLD=${WORLD} PX4_SIM_MODEL=${MODEL} python server.py"
echo "   curl http://localhost:5001/api/status"
echo "   curl http://localhost:5001/api/sensor/status"
echo ""
echo " Optional live doctor:"
echo "   ./scripts/doctor_gazebo.sh ${WORLD} ${MODEL} --live"
echo ""
echo " Gazebo GUI (optional):"
echo "   gz sim -g"
echo ""
echo " Logs:"
echo "   DDS:     /tmp/aerialclaw_dds.log"
echo "   Gazebo:  /tmp/aerialclaw_gz.log"
echo "   PX4:     /tmp/aerialclaw_px4.log"
echo ""
echo " Press Ctrl+C to stop all."
echo "============================================================"

wait
