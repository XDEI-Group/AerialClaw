#!/usr/bin/env bash
# ============================================================
# AerialClaw — PX4/Gazebo guided setup doctor
# ============================================================
# This is a reviewer-facing diagnostic script. It does not install
# or modify anything; it checks whether the optional PX4/Gazebo path
# is configured well enough to start and explains the next command
# when something is missing.
#
# Usage:
#   ./scripts/doctor_gazebo.sh
#   ./scripts/doctor_gazebo.sh --live       # also inspect running gz/PX4/MAVSDK ports
#   PX4_DIR=/path/to/PX4-Autopilot ./scripts/doctor_gazebo.sh
# ============================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PX4_DIR="${PX4_DIR:-${PROJECT_DIR}/PX4-Autopilot}"
LIVE=0
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --live) LIVE=1 ;;
    *) ARGS+=("$arg") ;;
  esac
done

WORLD="${PX4_GZ_WORLD:-${ARGS[0]:-default}}"
MODEL="${PX4_SIM_MODEL:-${ARGS[1]:-x500}}"

PX4_BUILD="${PX4_DIR}/build/px4_sitl_default"
PX4_BIN="${PX4_BUILD}/bin/px4"
PX4_WORLD_DIR="${PX4_DIR}/Tools/simulation/gz/worlds"
PX4_MODEL_DIR="${PX4_DIR}/Tools/simulation/gz/models"
LOCAL_MODEL_DIR="${HOME}/.simulation-gazebo/models"
LOCAL_WORLD_DIR="${HOME}/.simulation-gazebo/worlds"
CUSTOM_MODEL_DIR="${PROJECT_DIR}/sim/models/${MODEL}"
CUSTOM_WORLD_FILE="${PROJECT_DIR}/sim/worlds/${WORLD}.sdf"
WORLD_FILE="${PX4_WORLD_DIR}/${WORLD}.sdf"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  RED=$'\033[0;31m'
  GREEN=$'\033[0;32m'
  YELLOW=$'\033[1;33m'
  BLUE=$'\033[0;34m'
  NC=$'\033[0m'
else
  RED=''
  GREEN=''
  YELLOW=''
  BLUE=''
  NC=''
fi

PASS=0
WARN=0
FAIL=0

pass() { printf "%b[PASS]%b %s\n" "$GREEN" "$NC" "$1"; PASS=$((PASS + 1)); }
warn() { printf "%b[WARN]%b %s\n" "$YELLOW" "$NC" "$1"; WARN=$((WARN + 1)); }
fail() { printf "%b[FAIL]%b %s\n" "$RED" "$NC" "$1"; FAIL=$((FAIL + 1)); }
info() { printf "%b[INFO]%b %s\n" "$BLUE" "$NC" "$1"; }

has_cmd() { command -v "$1" >/dev/null 2>&1; }

check_cmd() {
  local cmd="$1"
  local hint="$2"
  if has_cmd "$cmd"; then
    pass "$cmd found: $(command -v "$cmd")"
  else
    fail "$cmd not found. $hint"
  fi
}

check_python_import() {
  local module="$1"
  local hint="$2"
  if python3 -c "import ${module}" >/dev/null 2>&1; then
    pass "python module '${module}' importable"
  else
    fail "python module '${module}' missing. $hint"
  fi
}

printf "============================================================\n"
printf " AerialClaw PX4/Gazebo Doctor\n"
printf " Project: %s\n" "$PROJECT_DIR"
printf " PX4_DIR: %s\n" "$PX4_DIR"
printf " World:   %s\n" "$WORLD"
printf " Model:   %s\n" "$MODEL"
printf " Live:    %s\n" "$LIVE"
printf "============================================================\n\n"

info "1/7 Checking host tools"
check_cmd git "Install git first."
check_cmd cmake "macOS: brew install cmake | Ubuntu: sudo apt install cmake"
check_cmd python3 "Install Python >=3.10."
if has_cmd gz; then
  GZ_VERSION="$(gz sim --version 2>&1 | head -1 || true)"
  pass "Gazebo CLI found: ${GZ_VERSION:-gz}"
else
  fail "Gazebo CLI 'gz' not found. macOS: brew tap osrf/simulation && brew install gz-harmonic | Ubuntu: install gz-harmonic."
fi

printf "\n"
info "2/7 Checking PX4 checkout and build"
if [ -d "$PX4_DIR/.git" ]; then
  pass "PX4 checkout exists"
else
  fail "PX4 checkout missing at $PX4_DIR. Run: ./scripts/setup_px4.sh"
fi

if [ -x "$PX4_BIN" ]; then
  pass "PX4 SITL binary exists: $PX4_BIN"
else
  fail "PX4 SITL binary missing. Run: ./scripts/setup_px4.sh  (or: cd '$PX4_DIR' && make px4_sitl gz_x500)"
fi

if [ -d "$PX4_WORLD_DIR" ]; then
  pass "PX4 Gazebo worlds directory exists"
else
  fail "PX4 Gazebo worlds directory missing: $PX4_WORLD_DIR"
fi

if [ -d "$PX4_MODEL_DIR" ]; then
  pass "PX4 Gazebo models directory exists"
else
  warn "PX4 Gazebo models directory missing: $PX4_MODEL_DIR (local ~/.simulation-gazebo/models may still work)"
fi

printf "\n"
info "3/7 Checking AerialClaw world/model assets"
if [ -f "$CUSTOM_WORLD_FILE" ]; then
  pass "Repository world source exists: sim/worlds/${WORLD}.sdf"
elif [ "$WORLD" = "default" ]; then
  warn "No repository source for PX4 default world; this is expected when using PX4's built-in default world."
else
  fail "Repository world source missing: sim/worlds/${WORLD}.sdf"
fi

if [ -f "$WORLD_FILE" ]; then
  pass "World installed into PX4: $WORLD_FILE"
elif [ "$WORLD" = "default" ]; then
  warn "PX4 default world not found at $WORLD_FILE yet. Run ./scripts/setup_px4.sh or check PX4 install."
else
  fail "World not installed into PX4. Run: ./scripts/setup_px4.sh"
fi

if [ -d "$CUSTOM_MODEL_DIR" ]; then
  pass "Repository model source exists: sim/models/${MODEL}"
elif [ "$MODEL" = "x500" ]; then
  warn "Using PX4 standard x500 model; repository custom sensor model is not required."
else
  fail "Repository model source missing: sim/models/${MODEL}"
fi

if [ -d "$LOCAL_MODEL_DIR/$MODEL" ] || [ -d "$PX4_MODEL_DIR/$MODEL" ]; then
  pass "Gazebo can likely resolve model '${MODEL}'"
else
  if [ "$MODEL" = "x500" ]; then
    warn "x500 model not found in common model dirs yet. Run ./scripts/setup_px4.sh to download PX4-gazebo-models."
  else
    fail "Model '${MODEL}' not found in ~/.simulation-gazebo/models or PX4 model dir. Run ./scripts/setup_px4.sh"
  fi
fi

printf "\n"
info "4/7 Checking runtime dependencies"
if has_cmd MicroXRCEAgent; then
  pass "MicroXRCEAgent found: $(command -v MicroXRCEAgent)"
else
  fail "MicroXRCEAgent missing. Run ./scripts/setup_px4.sh or build eProsima/Micro-XRCE-DDS-Agent."
fi
check_python_import mavsdk "Install with: python3 -m pip install mavsdk"

printf "\n"
info "5/7 Checking AerialClaw server path"
if [ -f "$PROJECT_DIR/server.py" ]; then
  pass "server.py exists"
else
  fail "server.py missing; run this script from the AerialClaw repository."
fi
if [ -f "$PROJECT_DIR/sim/gz_sensor_bridge.py" ]; then
  pass "Gazebo sensor bridge exists"
else
  fail "sim/gz_sensor_bridge.py missing"
fi

printf "\n"
info "6/7 Suggested commands"
printf "  Setup once:      ./scripts/setup_px4.sh\n"
printf "  Start sim:       ./scripts/start_sim.sh %s %s\n" "$WORLD" "$MODEL"
printf "  Start backend:   SIM_ADAPTER=px4 PX4_GZ_WORLD=%s PX4_SIM_MODEL=%s python server.py\n" "$WORLD" "$MODEL"
printf "  Status checks:   curl http://localhost:5001/api/status && curl http://localhost:5001/api/sensor/status\n"
printf "  Logs:            /tmp/aerialclaw_dds.log /tmp/aerialclaw_gz.log /tmp/aerialclaw_px4.log\n"

if [ "$LIVE" = "1" ]; then
  printf "\n"
  info "7/7 Live simulation checks"
  if pgrep -f "MicroXRCEAgent.*8888" >/dev/null 2>&1; then
    pass "MicroXRCEAgent appears to be running"
  else
    warn "MicroXRCEAgent process not detected"
  fi
  if pgrep -f "gz sim" >/dev/null 2>&1; then
    pass "Gazebo process appears to be running"
  else
    warn "Gazebo process not detected"
  fi
  if pgrep -f "bin/px4" >/dev/null 2>&1; then
    pass "PX4 SITL process appears to be running"
  else
    warn "PX4 SITL process not detected"
  fi
  if has_cmd lsof; then
    if lsof -i UDP:14540 >/dev/null 2>&1 || lsof -i :14540 >/dev/null 2>&1; then
      pass "MAVSDK/Offboard UDP port 14540 appears active"
    else
      warn "Port 14540 not observed yet; PX4 may still be starting or MAVLink not bound"
    fi
  fi
  if has_cmd gz; then
    TOPICS="$(gz topic -l 2>/dev/null || true)"
    if printf "%s" "$TOPICS" | grep -Eq "camera|image|lidar|scan|gpu_lidar"; then
      pass "Gazebo sensor topics detected"
      printf "%s\n" "$TOPICS" | grep -Ei "camera|image|lidar|scan|gpu_lidar" | sed 's/^/    /' | head -20
    else
      warn "No Gazebo camera/LiDAR topics detected. Use sensor model x500_lidar_2d_cam or inspect with: gz topic -l"
    fi
  fi
else
  printf "\n"
  info "7/7 Live simulation checks skipped (use --live after starting simulation)"
fi

printf "\n============================================================\n"
printf "Summary: %s pass, %s warn, %s fail\n" "$PASS" "$WARN" "$FAIL"
printf "============================================================\n"

if [ "$FAIL" -gt 0 ]; then
  printf "\nNext recommended command:\n  ./scripts/setup_px4.sh\n"
  exit 1
fi

if [ "$WARN" -gt 0 ]; then
  printf "\nDoctor completed with warnings. You can usually continue, but read the warnings above.\n"
else
  printf "\nDoctor passed. Gazebo/PX4 path is ready to try.\n"
fi
