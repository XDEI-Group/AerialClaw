# AerialClaw Artifact Guide

This guide is written for artifact reviewers who need a quick, reproducible path before attempting the full PX4/Gazebo simulation.

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

After installing Python and Web UI dependencies, reviewers can run:

```bash
bash scripts/smoke_mock.sh
```

This runs artifact consistency checks, Python compile, pytest, Web UI lint, and Web UI build.

## Quick path: Docker mock-mode evaluation

This is the recommended first-pass reviewer path. It does **not** require PX4, Gazebo, AirSim, a GPU, a real drone, or an LLM API key. The image intentionally uses `requirements-mock.txt` instead of the full simulation/ML dependency set.

```bash
git clone https://github.com/XDEI-Group/AerialClaw.git
cd AerialClaw

docker build -t aerialclaw:review .
docker run --rm -p 5001:5001 aerialclaw:review
# Open http://localhost:5001
# Or check: curl http://localhost:5001/api/status
```

## Local mock-mode evaluation

If Docker is unavailable, reviewers can run the same mock path locally:

```bash
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m pytest

cd ui
npm install
npm run build
cd ..

SIM_ADAPTER=mock python server.py
# Open http://localhost:5001
```

Expected results:

- `python -m pytest` passes.
- `npm run build` completes and produces the Vite distribution directory under the UI workspace.
- The backend starts on `http://localhost:5001`.
- The Web console can be opened and initialized with the mock adapter.

## Full simulation path

The full demo uses PX4 SITL + Gazebo Harmonic and is heavier. Use this only after the mock path works.

```bash
./scripts/setup_px4.sh
./scripts/start_sim.sh urban_rescue

# In another terminal:
source venv/bin/activate
SIM_ADAPTER=px4 python server.py
```

Notes:

- `scripts/setup_px4.sh` installs PX4/Gazebo assets and copies AerialClaw worlds.
- If the custom sensor model is not available in the repository, the script falls back to the standard PX4 `x500` model and prints a warning.
- Gazebo/PX4 setup can take 10-30 minutes on the first run.

## Optional LLM configuration

For autonomous natural-language planning, copy `.env.example` to `.env` and configure an OpenAI-compatible provider:

```bash
cp .env.example .env
# edit ACTIVE_PROVIDER, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL
```

Without an LLM key, reviewers can still evaluate package structure, tests, Web UI build, and mock adapter behavior.

## Known limitations

- Real drone support requires additional safety validation and hardware-specific adapter work.
- PX4/Gazebo camera and LiDAR topics depend on local Gazebo bindings and model availability.
- Multi-platform device clients are described by the protocol documentation but are not shipped as production SDK packages in this repository yet.

## Review checklist

```bash
python -m compileall -q .
python -m pytest
cd ui && npm install && npm run build
```
