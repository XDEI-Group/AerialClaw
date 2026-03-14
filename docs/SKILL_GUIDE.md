# Skill Development Guide — 技能开发指南

## Overview

AerialClaw uses a two-tier skill system:
- **Hard Skills** — Atomic actions that directly control the drone
- **Soft Skills** — Strategy documents that the LLM reads and executes by composing hard skills

## Hard Skills

### Structure

Each hard skill is a function in `skills/hard_skills.py` with a corresponding documentation file in `skills/docs/`.

```python
# skills/hard_skills.py

async def takeoff(adapter, altitude: float = 5.0, **kwargs) -> dict:
    """
    Take off to specified altitude.

    Args:
        adapter: Hardware adapter instance
        altitude: Target altitude in meters

    Returns:
        {"ok": True/False, "message": "...", ...}
    """
    success = await adapter.takeoff(altitude)
    return {
        "ok": success,
        "message": f"Took off to {altitude}m" if success else "Takeoff failed",
        "altitude": altitude,
    }
```

### Skill Document (`skills/docs/takeoff.md`)

```markdown
# takeoff

Take off to a specified altitude.

## Parameters
| Name     | Type  | Required | Default | Description          |
|----------|-------|----------|---------|----------------------|
| altitude | float | No       | 5.0     | Target altitude (m)  |

## Returns
- ok: bool
- altitude: float (actual altitude reached)

## Notes
- Drone must be on the ground
- Will arm automatically if not armed
```

### Adding a New Hard Skill

1. Add the function to `skills/hard_skills.py`
2. Create `skills/docs/your_skill.md` (the LLM reads this to understand usage)
3. Register in `skills/registry.py`

The skill loader (`skills/skill_loader.py`) automatically discovers skills from the docs directory and builds a summary table for the LLM.

## Soft Skills

### What Are Soft Skills?

Soft skills are **strategy documents** — not code. The LLM reads these Markdown files to understand complex multi-step strategies, then autonomously composes hard skills to execute them.

### Structure (`skills/soft_docs/search_target.md`)

```markdown
# search_target — Area Search Strategy

## Objective
Systematically search an area to locate a specific target.

## Strategy
1. Fly to the center of the search area
2. Execute a spiral or grid search pattern
3. At each waypoint: look_around to scan the environment
4. If potential target detected: fly closer and detect_object
5. Confirm detection with fuse_perception
6. Mark confirmed target location

## Required Hard Skills
takeoff, fly_to, look_around, detect_object, fuse_perception, mark_location

## Parameters
- area_position: [N, E, D] center of search area
- scan_range: radius in meters

## Tips
- Maintain altitude for better camera coverage
- Use LiDAR data to avoid obstacles
- Check battery periodically
```

### Adding a New Soft Skill

1. Create `skills/soft_docs/your_strategy.md`
2. Follow the template above
3. The system discovers it automatically — no code changes needed

### Dynamic Skill Generation

The system can automatically generate new soft skills during operation:
- When the reflection engine detects recurring behavior patterns
- The LLM extracts them into new `.md` strategy documents
- See `skills/dynamic_skill_gen.py` and `memory/skill_evolution.py`
