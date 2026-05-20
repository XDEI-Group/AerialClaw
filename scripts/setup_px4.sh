#!/usr/bin/env bash
# ============================================================
# AerialClaw — PX4 + Gazebo Simulation Environment Setup
# ============================================================
#
# This script sets up the complete PX4 SITL + Gazebo Harmonic
# simulation environment for AerialClaw.
#
# Usage:
#   chmod +x scripts/setup_px4.sh
#   ./scripts/setup_px4.sh
#
# What it does:
#   1. Checks prerequisites (CMake, Gazebo, Python)
#   2. Clones PX4-Autopilot (if not present)
#   3. Applies macOS ARM64 build patches
#   4. Downloads PX4 Gazebo base models
#   5. Installs optional custom drone model if present; otherwise falls back to PX4 x500
#   6. Installs AerialClaw custom Gazebo worlds (urban_rescue)
#   7. Builds PX4 SITL
#   8. Installs Micro XRCE-DDS Agent (if not present)
#
# After running this script, use scripts/start_sim.sh to launch.
# ============================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PX4_DIR="${PROJECT_DIR}/PX4-Autopilot"
MODEL_DIR="${HOME}/.simulation-gazebo/models"
WORLD_DIR="${HOME}/.simulation-gazebo/worlds"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; }

# ── Step 0: Prerequisites ──────────────────────────────────────

info "Checking prerequisites..."

check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        err "$1 not found. $2"
        return 1
    fi
    ok "$1 found: $(command -v "$1")"
}

MISSING=0
check_cmd cmake "Install: brew install cmake (macOS) or apt install cmake (Ubuntu)" || MISSING=1
check_cmd python3 "Install Python 3.10+" || MISSING=1

# Check Gazebo
if command -v gz &>/dev/null; then
    GZ_VER=$(gz sim --version 2>&1 | head -1)
    ok "Gazebo found: $GZ_VER"
else
    warn "Gazebo (gz) not found."
    echo "  macOS:  brew tap osrf/simulation && brew install gz-harmonic"
    echo "  Ubuntu: sudo apt install gz-harmonic"
    MISSING=1
fi

if [ "$MISSING" = "1" ]; then
    err "Please install missing prerequisites and re-run."
    exit 1
fi

# ── Step 1: Clone PX4 ──────────────────────────────────────────

if [ -d "$PX4_DIR" ]; then
    ok "PX4-Autopilot already exists at $PX4_DIR"
else
    info "Cloning PX4-Autopilot..."
    cd "$PROJECT_DIR"
    git clone https://github.com/PX4/PX4-Autopilot.git --recursive --depth=1 -b v1.15.4
    ok "PX4-Autopilot cloned"
fi

# ── Step 2: macOS ARM64 Patches ────────────────────────────────

ARCH=$(uname -m)
OS=$(uname -s)

if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
    info "Applying macOS ARM64 build patches..."
    export CMAKE_POLICY_VERSION_MINIMUM=3.5

    # protobuf fix (brew keg-only)
    if [ -d "/opt/homebrew/Cellar/protobuf@33" ]; then
        PROTO_VER=$(ls /opt/homebrew/Cellar/protobuf@33/ | head -1)
        export PKG_CONFIG_PATH="/opt/homebrew/Cellar/protobuf@33/${PROTO_VER}/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
        ok "protobuf@33 PKG_CONFIG_PATH set"
    fi

    # VLA and attribute warnings (common on ARM64 clang)
    export CFLAGS="${CFLAGS:-} -Wno-vla"
    export CXXFLAGS="${CXXFLAGS:-} -Wno-vla -Wno-error=attributes"

    ok "macOS ARM64 patches applied"
fi

# ── Step 3: Download PX4 Gazebo Base Models ────────────────────

info "Setting up Gazebo base models..."
mkdir -p "$MODEL_DIR"

# Download official PX4 models (x500 base, sensors, etc.)
if [ -d "${MODEL_DIR}/x500" ]; then
    ok "PX4 base models already present"
else
    info "Downloading PX4 Gazebo models..."
    MODELS_TMP=$(mktemp -d)
    git clone --depth=1 https://github.com/PX4/PX4-gazebo-models.git "$MODELS_TMP" 2>/dev/null || true
    if [ -d "${MODELS_TMP}/models" ]; then
        cp -r "${MODELS_TMP}/models/"* "$MODEL_DIR/" 2>/dev/null || true
        ok "PX4 Gazebo base models installed to $MODEL_DIR"
    else
        warn "Could not download PX4-gazebo-models. You may need to download manually."
        echo "  git clone https://github.com/PX4/PX4-gazebo-models.git"
        echo "  cp -r PX4-gazebo-models/models/* ~/.simulation-gazebo/models/"
    fi
    rm -rf "$MODELS_TMP"
fi

# ── Step 4: Install AerialClaw Custom Model ────────────────────

info "Checking optional AerialClaw custom drone model..."

# Optional customized sensor model. The repository remains runnable with PX4's
# standard x500 model when this directory is absent.
CUSTOM_MODEL_SRC="${PROJECT_DIR}/sim/models/x500_lidar_2d_cam"
if [ -d "$CUSTOM_MODEL_SRC" ]; then
    cp -r "$CUSTOM_MODEL_SRC" "$MODEL_DIR/"
    ok "AerialClaw x500_lidar_2d_cam installed"
else
    warn "Optional custom model not found at $CUSTOM_MODEL_SRC"
    echo "  Falling back to PX4 standard model: x500"
    echo "  Use ./scripts/start_sim.sh urban_rescue x500 for the default simulation path."
fi

# ── Step 5: Install Custom Gazebo Worlds ───────────────────────

info "Installing AerialClaw custom Gazebo worlds..."

PX4_WORLDS="${PX4_DIR}/Tools/simulation/gz/worlds"
CUSTOM_WORLDS_SRC="${PROJECT_DIR}/sim/worlds"

if [ -d "$CUSTOM_WORLDS_SRC" ] && [ -d "$PX4_WORLDS" ]; then
    cp "${CUSTOM_WORLDS_SRC}/"*.sdf "$PX4_WORLDS/" 2>/dev/null || true
    ok "Custom worlds installed to $PX4_WORLDS"
    ls "$CUSTOM_WORLDS_SRC/"*.sdf 2>/dev/null | while read f; do
        echo "  - $(basename "$f")"
    done
else
    warn "Custom worlds not found or PX4 worlds dir missing."
fi

# ── Step 6: Build PX4 SITL ─────────────────────────────────────

info "Building PX4 SITL (this may take 10-30 minutes on first build)..."
cd "$PX4_DIR"

if [ "$OS" = "Darwin" ]; then
    export CMAKE_POLICY_VERSION_MINIMUM=3.5
fi

# Build with Gazebo x500 (this also validates the build)
if [ -f "build/px4_sitl_default/bin/px4" ]; then
    ok "PX4 SITL binary already exists. Skipping build."
    echo "  To rebuild: cd $PX4_DIR && make px4_sitl gz_x500"
else
    make px4_sitl gz_x500 2>&1 | tail -20
    if [ -f "build/px4_sitl_default/bin/px4" ]; then
        ok "PX4 SITL build successful!"
    else
        err "PX4 build failed. Check the output above."
        echo "Common fixes for macOS ARM64:"
        echo "  export CMAKE_POLICY_VERSION_MINIMUM=3.5"
        echo "  brew install protobuf@33"
        echo "  See docs/SIMULATION_SETUP.md for detailed troubleshooting"
        exit 1
    fi
fi

# Kill any processes started by the test build
pkill -f "gz sim" 2>/dev/null || true
pkill -f "bin/px4" 2>/dev/null || true
sleep 2

# ── Step 7: Micro XRCE-DDS Agent ───────────────────────────────

if command -v MicroXRCEAgent &>/dev/null; then
    ok "MicroXRCEAgent already installed"
else
    info "MicroXRCEAgent not found. Installing..."
    XRCE_TMP=$(mktemp -d)
    cd "$XRCE_TMP"
    git clone --depth=1 https://github.com/eProsima/Micro-XRCE-DDS-Agent.git
    cd Micro-XRCE-DDS-Agent
    mkdir build && cd build
    cmake .. -DUAGENT_SOCKETCAN_PROFILE=OFF
    make -j$(sysctl -n hw.ncpu 2>/dev/null || nproc)
    sudo make install
    cd "$PROJECT_DIR"
    rm -rf "$XRCE_TMP"
    if command -v MicroXRCEAgent &>/dev/null; then
        ok "MicroXRCEAgent installed"
    else
        warn "MicroXRCEAgent install may have failed. You can try:"
        echo "  See docs/SIMULATION_SETUP.md Step 3"
    fi
fi

# ── Step 8: Python dependencies ────────────────────────────────

info "Checking Python mavsdk package..."
if python3 -c "import mavsdk" 2>/dev/null; then
    ok "mavsdk Python package installed"
else
    info "Installing mavsdk..."
    pip install mavsdk 2>/dev/null || pip3 install mavsdk
    ok "mavsdk installed"
fi

# ── Done ────────────────────────────────────────────────────────

echo ""
echo "============================================================"
echo -e "${GREEN} PX4 + Gazebo simulation environment is ready!${NC}"
echo "============================================================"
echo ""
echo "PX4 binary:  ${PX4_DIR}/build/px4_sitl_default/bin/px4"
echo "Models:      ${MODEL_DIR}/"
echo "Worlds:      ${PX4_WORLDS}/"
echo ""
echo "Next steps:"
echo "  1. Start simulation:  ./scripts/start_sim.sh"
echo "  2. Start AerialClaw:  python server.py"
echo "  3. Open browser:      http://localhost:5001"
echo ""
echo "See docs/SIMULATION_SETUP.md for detailed configuration."
