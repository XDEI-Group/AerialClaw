#!/bin/bash
# ============================================================
# setup_px4.sh — Clone PX4 and apply AerialClaw customizations
#
# Usage:
#   ./scripts/setup_px4.sh
#
# What it does:
#   1. Clones PX4-Autopilot (if not already present)
#   2. Applies parameter patches (mag sensor, no-RC mode, etc.)
#   3. Copies custom drone model (x500_sensor: 5 cameras + 3D LiDAR)
#   4. Copies custom airframe (4010_gz_x500_sensor)
#   5. Copies custom Gazebo world (urban_rescue)
#   6. Builds PX4 SITL
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PX4_DIR="${PX4_DIR:-$PROJECT_DIR/../PX4-Autopilot}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[SETUP]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Step 1: Clone PX4 ──
if [ -d "$PX4_DIR" ]; then
    log "PX4-Autopilot already exists at: $PX4_DIR"
else
    log "Cloning PX4-Autopilot..."
    git clone https://github.com/PX4/PX4-Autopilot.git --recursive "$PX4_DIR"
fi
cd "$PX4_DIR"

# ── Step 2: Apply patches ──
log "Applying AerialClaw patches to PX4..."
if [ -f "$PROJECT_DIR/sim/px4_patches.diff" ]; then
    git apply --check "$PROJECT_DIR/sim/px4_patches.diff" 2>/dev/null && \
        git apply "$PROJECT_DIR/sim/px4_patches.diff" && \
        log "Patches applied successfully" || \
        warn "Patches already applied or conflict — skipping"
fi

# ── Step 3: Copy custom drone model ──
GZ_MODELS="$PX4_DIR/Tools/simulation/gz/models"
if [ -d "$PROJECT_DIR/sim/models/x500_sensor" ]; then
    log "Installing custom drone model: x500_sensor"
    cp -r "$PROJECT_DIR/sim/models/x500_sensor" "$GZ_MODELS/"
fi

# ── Step 4: Copy custom airframe ──
AIRFRAMES="$PX4_DIR/ROMFS/px4fmu_common/init.d-posix/airframes"
if [ -f "$PROJECT_DIR/sim/airframes/4010_gz_x500_sensor" ]; then
    log "Installing custom airframe: 4010_gz_x500_sensor"
    cp "$PROJECT_DIR/sim/airframes/4010_gz_x500_sensor" "$AIRFRAMES/"

    # Register in CMakeLists if not already there
    if ! grep -q "4010_gz_x500_sensor" "$AIRFRAMES/CMakeLists.txt" 2>/dev/null; then
        echo "	4010_gz_x500_sensor" >> "$AIRFRAMES/CMakeLists.txt"
        log "Registered airframe in CMakeLists.txt"
    fi
fi

# ── Step 5: Copy custom Gazebo world ──
GZ_WORLDS="$PX4_DIR/Tools/simulation/gz/worlds"
if [ -f "$PROJECT_DIR/sim/worlds/urban_rescue.sdf" ]; then
    log "Installing custom world: urban_rescue"
    cp "$PROJECT_DIR/sim/worlds/urban_rescue.sdf" "$GZ_WORLDS/"
fi

# ── Step 6: Build PX4 SITL ──
log "Building PX4 SITL (this may take 10-30 minutes on first run)..."
export CMAKE_POLICY_VERSION_MINIMUM=3.5
make px4_sitl gz_x500 || err "PX4 build failed. See docs/SIMULATION_SETUP.md for troubleshooting."

log "========================================="
log "  PX4 setup complete!"
log "  Custom model: x500_sensor (5 cameras + 3D LiDAR)"
log "  Custom world: urban_rescue"
log ""
log "  To start simulation:"
log "    cd $PX4_DIR"
log "    export CMAKE_POLICY_VERSION_MINIMUM=3.5"
log "    export PX4_GZ_WORLD=urban_rescue"
log "    make px4_sitl gz_x500"
log "========================================="
