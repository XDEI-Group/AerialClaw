# 🦅 AerialClaw: Towards Personal AI Agents for General Autonomous Aerial Systems


<p>
  <img src="https://img.shields.io/badge/Status-Simulation%20Verified-blue" alt="status">
  <img src="https://img.shields.io/badge/License-MIT-brightgreen" alt="MIT License">
  <img src="https://img.shields.io/badge/Core-LLM%20Decision%20Making-orange" alt="LLM driven">
  <img src="https://img.shields.io/badge/Field-Embodied%20AI-black" alt="focus">
  <img src="https://img.shields.io/badge/Simulation-PX4+Gazebo-purple" alt="PX4 Gazebo">
</p>

**English** | [中文](README_CN.md)

**AerialClaw** is a personal AI agent framework for general autonomous aerial systems. The system provides a standardized library of atomic action skills (takeoff, navigation, perception, etc.), with an LLM performing real-time environmental perception, decision planning, and skill composition during task execution — eliminating the need to pre-script complete flight procedures for each mission, while endowing each drone with its own identity, task memory, and skill evolution capability.

The project uses Markdown documents to define and maintain each agent's cognitive state and capability boundaries, autonomously read and written by the model — making every drone truly "personal" with its own experience, preferences, and growth trajectory.

> *"No pre-scripted procedures, just defined capabilities — let every drone think, learn, and grow through its own missions."*

<p align="center">
  <img src="assets/demo.gif" alt="AerialClaw Demo" width="720" />
</p>

---
---

## 📑 Table of Contents

- [📢 Update](#-update)
- [Research Background and Motivation](#research-background-and-motivation)
- [System Architecture Design](#system-architecture-design)
- [Decision Mechanism](#decision-mechanism-autonomous-loop-implementation)
- [Skill System](#integrated-skill-system)
- [Perception System](#perception-system)
- [Safety Architecture](#safety-architecture)
- [Memory System](#memory-system)
- [Universal Device Protocol](#universal-device-protocol)
- [Self-Evolution](#self-evolution)
- [Simulation Environment](#simulation-verification-environment)
- [Web Monitoring Interface](#web-monitoring-interface)
- [Installation and Deployment](#installation-and-deployment)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Acknowledgements](#acknowledgements)

---

## 📢 Update

- **(2026/3/15)** AerialClaw v2.0 released — safety envelope, four-layer memory, universal device protocol, self-evolution engine, hybrid deployment.
- **(2026/3/14)** AerialClaw v1.0 released — full agent loop, 12 hard skills, reflection engine, Web UI, PX4+Gazebo simulation.

## Research Background and Motivation

Current drone systems mostly rely on pre-programmed scripts, lacking adaptability to unknown environments. AerialClaw explores endowing drones with **autonomous environmental understanding and real-time decision-making** through LLMs:

- 🧠 **Reasoning, not just execution** — LLM parses task objectives and generates step-by-step decisions
- 👁️ **Semantic-level understanding** — Multi-source sensor data converted to natural language for commonsense reasoning
- 📝 **Flight experience accumulation** — Task memory repository for history-based decision optimization
- 🪪 **Capability boundary awareness** — Performance profiles tracking capability boundaries

## System Architecture Design

<p align="center">
  <img src="assets/architecture.png" alt="AerialClaw System Architecture" width="900" />
</p>

### Core Design Principles

1. **First-person decision perspective** — Drone's own perspective for decision-making
2. **Semantic-level sensor fusion** — Raw sensor data converted to LLM-understandable descriptions
3. **Document-driven skill definition** — Actions and strategies as readable documents, dynamically loaded
4. **Hierarchical memory management** — Long-term experience and short-term context balanced efficiently

## Decision Mechanism: Autonomous Loop Implementation

The system employs an incremental decision mechanism based on real-time perception, executing a complete cognitive cycle at each step:

<p align="center">
  <img src="assets/decision_loop.png" alt="Autonomous Decision Loop" width="600" />
</p>

The system possesses basic exception handling capabilities: path replanning when obstructed, attention adjustment when discovering unexpected targets, and automatic return when battery is low.

### Identity and State Management System

| Document | Functional Description | Content Example |
|----------|-----------------------|-----------------|
| `SOUL.md` | Defines decision preferences and constraints | *Safety-first strategy, conservative risk assessment* |
| `BODY.md` | Records hardware configuration and performance parameters | *Sensor types, flight performance boundaries* |
| `MEMORY.md` | Stores task experience and lessons learned | *Effective strategy records for specific scenarios* |
| `SKILLS.md` | Tracks skill execution statistics | *Success rates and applicable conditions for actions* |
| `WORLD_MAP.md` | Builds environmental feature knowledge base | *Landmarks and risk points in known areas* |

All documents use Markdown format, supporting version management and manual review. The system automatically reads and writes relevant documents before and after tasks.

### Integrated Skill System

The system uses a **four-layer skill architecture** inspired by human cognitive structure:

```
┌─────────────────────────────────────────────────────┐
│  Strategy Layer (Soft Skills)                        │  ← Knowledge documents, LLM-composed
│  search_target, rescue_person, patrol_area           │
├─────────────────────────────────────────────────────┤
│  Cognitive Layer (Cognitive Skills)                   │  ← Information processing capabilities
│  http_request, run_python, read_file, write_file     │
├─────────────────────────────────────────────────────┤
│  Perception Layer (Perception Skills)                │  ← Environmental awareness
│  detect_object, observe, scan_area, fuse_perception  │
├─────────────────────────────────────────────────────┤
│  Motor Layer (Motor Skills)                          │  ← Physical actions
│  takeoff, land, fly_to, hover, return_to_launch      │
└─────────────────────────────────────────────────────┘
```

**Motor Skills (12 Atomic Actions)** — Physical control of the drone:

| Category | Skills | Description |
|:---|:---|:---|
| Flight Control | `takeoff` `land` `hover` `fly_to` `fly_relative` `change_altitude` `return_to_launch` | Takeoff/landing, hover, point-to-point flight, relative movement, altitude change, RTL |
| Perception | `look_around` `detect_object` `fuse_perception` | Multi-directional observation, object detection (VLM), multi-sensor semantic fusion |
| Status Query | `get_position` `get_battery` | Current position and battery status |
| Markers | `mark_location` `get_marks` | Mark points of interest, query marked locations |

**Cognitive Skills (4 Meta-Skills)** — Information processing and computation:

| Skill | Description | Safety |
|:---|:---|:---|
| `run_python` | Execute Python code in sandboxed environment | Auto-sandboxed (Docker → subprocess → restricted) |
| `http_request` | HTTP GET/POST requests for information retrieval | Internal network blocked, timeout enforced |
| `read_file` | Read file contents | Restricted to working directory |
| `write_file` | Write content to file | Restricted to working directory, audit logged |

Cognitive skills give the agent **information-gathering and processing capabilities** beyond physical actions — e.g., checking weather APIs before deciding flight paths, or computing optimal routes using Python.

**Soft Skills (Strategy Documents)**:

| Strategy | Description |
|:---|:---|
| `search_target` | Area search — LLM autonomously plans search paths, fuses vision and LiDAR to identify targets |
| `rescue_person` | Personnel rescue — Full workflow from approach, assessment, marking to reporting |
| `patrol_area` | Area patrol — Strategic area coverage with continuous anomaly monitoring |

Soft skills are stored as Markdown documents. During execution, the LLM reads these documents to understand strategic intent and autonomously composes motor, cognitive, and perception skills to complete tasks. The system also supports **dynamic soft skill generation**: when the LLM identifies recurring behavior patterns during reflection, it automatically extracts them into new strategy documents.

**Capability Gap Detection**: When the LLM plans a skill that doesn't exist, the system detects it *before execution* and classifies the gap as either `software` (auto-fillable via code generation) or `hardware` (requires physical capability the device lacks). This **self-aware capability boundary** prevents hallucinated plans from reaching the execution layer.

### Perception System

Skill execution depends on environmental awareness. The system adopts a **passive + active dual-layer perception architecture**, providing the LLM with environmental information at different granularities:

- **Passive perception** (`PerceptionDaemon`) — Runs continuously in the background, periodically fusing multi-sensor data into environmental summaries for real-time situational awareness
- **Active perception** (`VLMAnalyzer`) — Triggered on-demand by the LLM, invoking vision-language models for deep image analysis (object detection, scene understanding, etc.)

Perception models are **plug-and-play configurable**: connect to cloud APIs (GPT-4o, etc.), locally deployed open-source models, or custom fine-tuned models — adapting to different deployment scenarios' requirements for latency, accuracy, and privacy.

This design supports research across various application scenarios:
- 🏚️ **Disaster Response** — Personnel search and rescue in rubble environments
- 🌲 **Ecological Monitoring** — Anomaly detection in forested areas
- 🏗️ **Facility Inspection** — Safety inspection of building structures
- 🌾 **Agricultural Observation** — Assessment of crop growth status

## Safety Architecture

AerialClaw treats safety as a **hardware-level guarantee**, not an LLM-level policy. Four sequential gates protect every command:

```
Command → [Gate 1: Filter] → [Gate 2: Sandbox] → [Gate 3: Approval] → [Gate 4: Envelope] → Execution
```

| Gate | Mechanism | Description |
|------|-----------|-------------|
| **1. Command Filter** | Whitelist / Blacklist | Blocks prohibited commands before reaching the planner |
| **2. Sandbox Isolation** | Docker → subprocess → restricted (auto-downgrade) | Code execution never touches the host system |
| **3. Tiered Approval** | `auto` / `confirm` / `deny` | Operator-configurable per-action authorization level |
| **4. Safety Envelope** | Hard-coded physical limits | LLM cannot override — enforced at the adapter layer |

**Safety Envelope Parameters** (hard-coded, LLM-unreachable):

| Limit | Value |
|-------|-------|
| Max speed | 10 m/s |
| Max altitude | 120 m |
| Battery RTL threshold | 15% |
| Battery forced-land threshold | 5% |
| Heartbeat timeout | 10 s |

**"Spinal Cord" Architecture**: The LLM is the brain (capable of mistakes); the safety envelope is the spinal cord (hard-coded reflexes). Even a hallucinating LLM cannot command the drone beyond physical safety limits.

- **Audit Log**: All commands, decisions, and safety interventions are recorded and exportable.
- **Safety Levels**: Switch between `strict` / `standard` / `permissive` with a single config change.

## Memory System

The four-layer memory architecture balances immediate context, accumulated experience, and semantic retrieval:

```
┌─────────────────────────────────────────────────┐
│  Working Memory    — Current task context        │  Short-term, cleared per task
├─────────────────────────────────────────────────┤
│  Episodic Memory   — Task histories & outcomes  │  Persistent, retrieved by similarity
├─────────────────────────────────────────────────┤
│  Skill Memory      — Execution statistics        │  Success rates, failure patterns
├─────────────────────────────────────────────────┤
│  World Knowledge   — Environmental discoveries  │  Landmarks, hazards, map features
└─────────────────────────────────────────────────┘
```

- **Vector Semantic Retrieval** — `chromadb` primary with `TF-IDF` auto-fallback; no external service required
- **Reflection Engine** — After each task: task log → LLM reflection → memory update → informs next planning cycle
- **Planning-time Retrieval** — Relevant past experiences fetched and injected at planning time, replacing full-history injection to control token usage
- **Cross-task Transfer** — Experience from one platform or scenario generalizes to similar future tasks

## Universal Device Protocol

Any device implementing this protocol can be controlled by AerialClaw — no custom adapter required for basic operations.

**Dual-channel communication**: HTTP REST (commands & registration) + WebSocket (real-time telemetry)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/devices/register` | POST | Device registration with capability declaration |
| `/devices/{id}/status` | POST | Status reporting |
| `/devices/{id}/sensors` | POST | Sensor data upload |
| `/devices/{id}/command` | POST | Command dispatch |
| `/devices/{id}/heartbeat` | POST | Keep-alive (10 s timeout → auto-offline) |

- **Token authentication** on all endpoints
- **Heartbeat watchdog**: 10-second timeout triggers automatic device-offline status
- **Three client templates** included: Python · Arduino (ESP32) · ROS2 — see [`clients/README.md`](clients/README.md)

## Self-Evolution

AerialClaw can extend its own capabilities when encountering new devices or skill gaps:

**Device Analyzer** — When a new device is registered:
1. LLM analyzes the device's declared capabilities
2. Auto-generates a `BODY.md` tailored to the device
3. Matches against existing skills; flags gaps for generation

**Code Generator** — For `software`-class capability gaps:
1. LLM generates a Python adapter from scratch
2. Runs in sandbox — automatic self-repair on failure
3. Deploys to the adapter library on success

**Skill Evolver** — Continuous skill improvement:
1. Analyzes per-skill performance statistics from `SKILLS.md`
2. LLM proposes strategy improvements; under-performing skills are retired
3. New strategy documents are promoted automatically

**Capability Gap Detection** — Three-layer defense before execution:
- `software` gap → trigger code generation pipeline
- `hardware` gap → reject with clear explanation; no hallucinated execution
- "Onboarding a new platform" is itself a soft skill that can run end-to-end automatically

## Simulation Verification Environment

Currently implemented in a **PX4 SITL + Gazebo Harmonic** simulation environment:

<p align="center">
  <img src="assets/gazebo_demo.gif" alt="Gazebo Simulation" width="720" />
  <br>
  <em>Simulation testing of X500 drone in urban rescue scenario (4x speed playback)</em>
</p>

| Component | Technical Choice |
|-----------|------------------|
| Flight Control System | PX4 v1.15 Software-in-the-Loop |
| Simulation Environment | Gazebo Harmonic (gz sim 8.x) |
| Sensor Models | 5 cameras + 3D LiDAR (360°×16 layers) |
| Communication Protocol | Micro XRCE-DDS + MAVSDK gRPC |
| Coordinate System | NED (North-East-Down) local coordinate system |

**Simulation Scene Elements**: Collapsed buildings, trapped person models, fire and smoke effects, obstacle arrangements, ground markings, etc.

## Web Monitoring Interface

<p align="center">
  <img src="assets/ui_overview.png" alt="AerialClaw Web Control Interface" width="720" />
</p>

Provides necessary visualization and interaction tools for research:
- 📷 **Multi-view Video**  — Real-time feeds from front/back/left/right/down cameras
- 📡 **LiDAR Visualization** — Multi-layer rendering of 3D LiDAR point cloud data
- 🕹️ **Manual Control**     — First-person view with keyboard flight control
- 🤖 **AI Autonomous Mode** — Natural language tasking with LLM-driven execution
- 💬 **Command Interface**  — Natural language task commands and dialogue
- 📊 **Status Monitoring**  — Real-time flight parameters and system status
- ⚙️ **Model Configuration** — Switch and configure multiple LLM backends

The system supports **real-time Manual / AI mode switching**, allowing operators to take over control from AI autonomous mode at any time, with one-click execution interruption. This is the fundamental safety guarantee for real-world deployment — AI handles the decisions, but humans always retain the final override.

## Installation and Deployment

### Environment Requirements

- Python >= 3.10, Node.js >= 18
- CMake >= 3.22
- Git

### Step 1: Clone Repository

```bash
git clone https://github.com/XDEI-Group/AerialClaw.git
cd AerialClaw
```

### Step 2: Python Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Build Web Interface

```bash
cd ui
npm install
npm run build
cd ..
```

### Step 4: Configure LLM

```bash
cp .env.example .env
```

Edit `.env` with your LLM service credentials:

```bash
ACTIVE_PROVIDER=openai                    # or: ollama_local / deepseek / moonshot
LLM_BASE_URL=https://api.openai.com/v1   # API endpoint
LLM_API_KEY=sk-your-key-here              # API key
LLM_MODEL=gpt-4o                          # Model name
```

Supports OpenAI, DeepSeek, Moonshot, local Ollama, or any OpenAI-compatible API. See [docs/LLM_CONFIG.md](docs/LLM_CONFIG.md) for details.

### Step 5: Set Up PX4 Simulation

One-click script handles PX4 cloning, patching, custom model installation, and compilation:

```bash
./scripts/setup_px4.sh
```

This script automatically:
- Clones PX4-Autopilot from the official repository
- Applies AerialClaw parameter patches (magnetometer, no-RC mode, etc.)
- Installs custom drone model (x500_sensor: 5 cameras + 3D LiDAR)
- Installs custom Gazebo world (urban_rescue)
- Builds PX4 SITL

> First build takes approximately 10-30 minutes. For macOS ARM64 troubleshooting, see [docs/SIMULATION_SETUP.md](docs/SIMULATION_SETUP.md).

## Quick Start

Start four terminals in order:

**Terminal 1 — Simulation**
```bash
cd ../PX4-Autopilot
export CMAKE_POLICY_VERSION_MINIMUM=3.5
export PX4_GZ_WORLD=urban_rescue
make px4_sitl gz_x500
```

**Terminal 2 — MAVSDK Server**
```bash
mavsdk_server -p 50051 udp://:14540
```

**Terminal 3 — AerialClaw Service**
```bash
cd AerialClaw
source venv/bin/activate
python server.py
```

**Terminal 4 — Browser**
```
http://localhost:5001
```

In the Web UI:
1. Click "⚡ Initialize System"
2. Switch to "🤖 AI" mode (top right)
3. Test with natural language commands:
   - *"Take off to 15 meters and observe the surroundings"*
   - *"Search the northern area, photograph any targets found"*
   - *"Report current battery and position"*

## Project Structure

```
AerialClaw/
├── server.py                    # Service entry point
├── config.py                    # Global config (reads from .env)
├── llm_client.py                # Multi-provider LLM client
├── .env.example                 # Environment variable template
├── requirements.txt             # Python dependencies
│
├── brain/                       # Decision-making core
│   ├── agent_loop.py            #   Autonomous decision loop
│   ├── planner_agent.py         #   LLM task planner
│   └── chat_mode.py             #   Conversational mode
│
├── perception/                  # Perception system
│   ├── daemon.py                #   Passive perception daemon
│   ├── vlm_analyzer.py          #   Active visual analysis (VLM)
│   ├── prompts.py               #   Perception prompts
│   └── gz_camera.py             #   Gazebo camera bridge
│
├── skills/                      # Skill library
│   ├── motor_skills.py          #   Motor skills (physical layer, 12 actions)
│   ├── cognitive_skills.py      #   Cognitive skills (info layer, 4 meta-skills)
│   ├── perception_skills.py     #   Perception skills (sensing layer)
│   ├── hard_skills.py           #   Compatibility import layer
│   ├── soft_skills.py           #   Soft skill executor
│   ├── docs/                    #   Skill documents (13)
│   ├── soft_docs/               #   Soft skill strategy docs (4)
│   └── dynamic_skill_gen.py     #   Dynamic skill generation
│
├── memory/                      # Memory and learning
│   ├── vector_store.py          #   Vector storage (chromadb / TF-IDF fallback)
│   ├── memory_manager.py        #   Four-layer memory manager
│   ├── shared_memory.py         #   Cross-device shared memory
│   ├── reflection_engine.py     #   Reflection engine
│   ├── skill_evolution.py       #   Skill evolution
│   ├── world_model.py           #   World model
│   └── task_log.py              #   Task logger
│
├── robot_profile/               # Identity documents
│   ├── SOUL.md / BODY.md        #   Personality & hardware description
│   ├── MEMORY.md / SKILLS.md    #   Experience & skill self-description
│   └── WORLD_MAP.md             #   Environment map
│
├── adapters/                    # Hardware adaptation layer
│   ├── base_adapter.py          #   Abstract interface
│   ├── protocol_adapter.py      #   Universal protocol adapter
│   ├── px4_adapter.py           #   PX4 adapter
│   ├── sim_adapter.py           #   Simulation adapter
│   └── mock_adapter.py          #   Mock testing adapter
│
├── sim/                         # Simulation resources
│   ├── models/x500_sensor/      #   Custom drone model (5 cameras + LiDAR)
│   ├── worlds/urban_rescue.sdf  #   Custom Gazebo world
│   ├── airframes/               #   Custom airframe
│   └── px4_patches.diff         #   PX4 customization patches
│
├── ui/                          # Web monitoring interface (React)
│   └── src/components/          #   11 React components
│
├── core/                        # Core infrastructure
│   ├── safety/                  #   Four-gate safety system
│   ├── device_manager.py        #   Universal device manager
│   ├── capability_gap.py        #   Capability gap detection
│   ├── device_analyzer.py       #   LLM device analysis
│   ├── code_generator.py        #   LLM adapter generation
│   ├── skill_evolver.py         #   Skill evolution engine
│   ├── doctor.py                #   System health checks
│   ├── errors.py                #   Unified exception system
│   └── logger.py                #   Logging system
│
├── scripts/                     # Scripts
│   ├── setup_px4.sh             #   One-click PX4 install + patch
│   └── start_gz_sim.sh          #   One-click simulation launcher
│
├── docs/                        # Developer documentation
│   ├── ARCHITECTURE.md          #   System architecture
│   ├── SIMULATION_SETUP.md      #   Simulation environment setup
│   ├── ADAPTER_GUIDE.md         #   Adapter integration guide
│   ├── SKILL_GUIDE.md           #   Skill development guide
│   ├── PERCEPTION_GUIDE.md      #   Perception module guide
│   └── LLM_CONFIG.md            #   LLM configuration guide
│
└── assets/                      # Images and demo resources
```

## Research Progress and Plans

### Implemented
- [x] Autonomous decision loop · Identity & state management · 12 motor skills + 4 cognitive skills + 3 soft skills
- [x] Passive + active dual-layer perception · Experience reflection · Dynamic skill generation · Skill retirement
- [x] PX4 + Gazebo simulation · Web monitoring & interaction · Cockpit FPV
- [x] Four-layer memory system · Vector semantic retrieval · Cross-task experience transfer
- [x] Universal device protocol (HTTP + WebSocket) · Three-platform client templates
- [x] Four-gate safety system · Hard-coded safety envelope · Operation audit log
- [x] Adaptive sandbox · Cognitive skills · Capability gap detection
- [x] Self-evolution · LLM device analysis · Adapter auto-generation
- [x] Hybrid deployment · Offline emergency mode · Edge-cloud coordination

### Future Directions
- [ ] Real drone porting · ROS2 integration · Sim2Real transfer
- [ ] Multi-agent collaboration · Shared world model

## Contribution

Issues and PRs welcome. See [docs/](docs/) for developer documentation.

## License

This project is licensed under the [MIT License](LICENSE).

## Acknowledgements

Developed by ROBOTY Lab, School of Computer Science, Xidian University.

Inspired by [OpenClaw](https://github.com/openclaw/openclaw). Built with:
[PX4](https://px4.io/) · [Gazebo](https://gazebosim.org/) · [MAVSDK](https://mavsdk.mavlink.io/) · [React](https://react.dev/) · [Vite](https://vitejs.dev/)