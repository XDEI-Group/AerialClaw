# AerialClaw Repository Package Guide

This guide is written for repository package users who need a quick, repeatable path before attempting the full PX4/Gazebo simulation.

## What is included

AerialClaw is an open-source framework for LLM-driven autonomous aerial agents. The repository includes:

- Python backend and autonomous agent loop
- hard/soft skill system
- memory and reflection modules
- simulator adapters, including a pure in-memory `mock` adapter
- PX4/Gazebo and AirSim integration code
- React Web console
- documentation and demo media


## One-command smoke gate

After installing Python and Web UI dependencies, users can run:

```bash
bash scripts/smoke_mock.sh
```

This runs repository consistency checks, Python compile, pytest, Web UI lint, and Web UI build.

## Quick path: Docker mock mode evaluation

This is the recommended first-pass user path. It does **not** require PX4, Gazebo, AirSim, a GPU, a real drone, or an LLM API key. The image intentionally uses `requirements-mock.txt` instead of the full simulation/ML dependency set.

```bash
git clone https://github.com/XDEI-Group/AerialClaw.git
cd AerialClaw

# Option A: Docker Compose
# Windows users: start Docker Desktop first and wait until the Linux engine is running.
docker compose up --build

# Option B: plain Docker
docker build -t aerialclaw:demo .
docker run --rm -p 5001:5001 aerialclaw:demo

# Open http://localhost:5001
# Or check in another terminal: curl http://localhost:5001/api/status
```

If Docker reports `TLS handshake timeout` while resolving `python:3.12-slim` or `node:22-slim`, the base image was not pulled and `aerialclaw:demo` was not created. Fix Docker Desktop's registry mirror/proxy settings, then run the build command again.

## Local mock mode evaluation

If Docker is unavailable, users can run the same mock path locally:

```bash
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m pytest

# Windows PowerShell activation uses: .\venv\Scripts\Activate.ps1
# Windows CMD activation uses: venv\Scripts\activate.bat

cd ui
npm install
npm run build
cd ..

# macOS / Linux
SIM_ADAPTER=mock python server.py

# Windows PowerShell
$env:SIM_ADAPTER="mock"; python server.py

# Windows CMD
set SIM_ADAPTER=mock
python server.py

# Open http://localhost:5001
```

Expected results:

- `python -m pytest` passes.
- `npm run build` completes and produces the Vite distribution directory under the UI workspace.
- The backend starts on `http://localhost:5001`.
- The Web console can be opened and initialized with the mock adapter.

## Guided PX4/Gazebo path

The second user path uses PX4 SITL + Gazebo Harmonic. It is heavier than mock mode, but the repository includes guided scripts so users do not have to infer paths manually.

```bash
# Diagnose what is already available and what is missing.
./scripts/doctor_gazebo.sh urban_rescue x500_lidar_2d_cam

# First-time setup: clone/build PX4, install models/worlds, install/check MAVSDK pieces.
./scripts/setup_px4.sh

# Launch DDS Agent + Gazebo + PX4 SITL.
./scripts/start_sim.sh urban_rescue x500_lidar_2d_cam

# In another terminal, start AerialClaw against PX4/Gazebo.
SIM_ADAPTER=px4 PX4_GZ_WORLD=urban_rescue PX4_SIM_MODEL=x500_lidar_2d_cam python server.py

# Verify backend and sensor bridge status.
curl http://localhost:5001/api/status
curl http://localhost:5001/api/sensor/status

# Optional live diagnosis once the simulation is running.
./scripts/doctor_gazebo.sh urban_rescue x500_lidar_2d_cam --live
```

Notes:

- `scripts/doctor_gazebo.sh` is read-only and explains the next command when something is missing.
- `scripts/setup_px4.sh` installs PX4/Gazebo assets and copies AerialClaw worlds and the bundled `x500_lidar_2d_cam` sensor model when present.
- `scripts/start_sim.sh` prints log locations and falls back to the standard PX4 `x500` model when the sensor model cannot be resolved locally.
- Gazebo/PX4 setup can take 10-30 minutes on the first run and depends on OS-level Gazebo/PX4 build requirements.

## Optional LLM configuration

For autonomous natural-language planning, copy `.env.example` to `.env` and configure an OpenAI-compatible provider:

```bash
cp .env.example .env
# edit ACTIVE_PROVIDER, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
```

Without an LLM key, users can still evaluate package structure, tests, Web UI build, and mock adapter behavior.

## Known limitations

- Real drone support requires additional safety validation and hardware-specific adapter work.
- PX4/Gazebo camera and LiDAR topics depend on local Gazebo bindings and model availability.
- Multi-platform device clients are described by the protocol documentation but are not shipped as production SDK packages in this repository yet.

## Run checklist

```bash
python -m compileall -q .
python -m pytest
cd ui && npm install && npm run build
```
