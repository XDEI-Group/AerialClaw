# AerialClaw Architecture Overview

## System Layers

```
┌─────────────────────────────────────────────────┐
│                  Web UI (React)                  │
│         Manual Control / AI Monitor / Chat       │
├─────────────────────────────────────────────────┤
│                 server.py (Flask-SocketIO)        │
│           WebSocket events + REST API            │
├──────────┬──────────┬──────────┬────────────────┤
│  Brain   │  Skills  │ Percep.  │    Memory      │
│ AgentLoop│ Hard/Soft│ Daemon   │ Reflection     │
│ Planner  │ Registry │ VLM      │ SkillEvolution │
│ ChatMode │ Loader   │ Prompts  │ WorldModel     │
├──────────┴──────────┴──────────┴────────────────┤
│              Runtime (AgentRuntime)              │
│           Task dispatch + execution              │
├─────────────────────────────────────────────────┤
│              Adapters (BaseAdapter)              │
│      PX4Adapter / SimAdapter / MockAdapter       │
├─────────────────────────────────────────────────┤
│           Simulation / Hardware Layer            │
│     PX4 SITL + Gazebo / MAVSDK / Real Drone     │
└─────────────────────────────────────────────────┘
```

## Data Flow

```
Task (natural language)
  │
  ▼
Brain (Planner) ──── reads ────► robot_profile/ (SOUL, MEMORY, SKILLS)
  │                               perception/daemon (env summary)
  │
  ▼
Plan (skill sequence)
  │
  ▼
Runtime ──── dispatches ────► Skills (hard_skills.py)
  │                            │
  │                            ▼
  │                          Adapter ────► PX4/Gazebo
  │
  ▼
Feedback ──── updates ────► Memory (reflection, skill_evolution)
  │
  ▼
Next iteration (or task complete)
```

## Module Responsibilities

| Module | Path | Role |
|--------|------|------|
| **Brain** | `brain/` | LLM-based planning and decision making |
| **Skills** | `skills/` | Atomic actions (hard) + strategy docs (soft) |
| **Perception** | `perception/` | Passive env monitoring + active VLM analysis |
| **Memory** | `memory/` | Task logs, reflection, skill evolution, world model |
| **Runtime** | `runtime/` | Skill execution orchestration |
| **Adapters** | `adapters/` | Hardware abstraction layer |
| **Sim** | `sim/` | Gazebo sensor bridge |
| **LLM** | `llm/`, `llm_client.py` | Multi-provider LLM client |
| **Tools** | `tools/` | LLM tool-calling support |
| **Config** | `config.py`, `.env` | Centralized configuration |
| **Profile** | `robot_profile/` | Identity documents (SOUL, BODY, MEMORY, SKILLS) |
| **UI** | `ui/` | React-based monitoring dashboard |
