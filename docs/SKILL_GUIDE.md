# Skill Development Guide — 技能开发指南

## Overview

AerialClaw uses a two-tier skill system:
- **Hard Skills** — Atomic actions that directly control the drone
- **Soft Skills** — Strategy documents that the LLM reads and executes by composing hard skills

## Hard Skills

### Structure

Each hard skill is a `Skill` subclass implemented in files such as `skills/motor_skills.py`, `skills/perception_skills.py`, and `skills/cognitive_skills.py`, with corresponding documentation in `skills/docs/`.

```python
# skills/motor_skills.py

class Takeoff(Skill):
    name = "takeoff"
    description = "Take off or climb to a target altitude."
    skill_type = "hard"
    robot_type = ["UAV"]
    input_schema = {"altitude": "float, target altitude in meters"}

    def execute(self, input_data: dict) -> SkillResult:
        adapter = _get_adapter()
        altitude = input_data.get("altitude", 5.0)
        ok = adapter.takeoff(altitude)
        return SkillResult(success=ok)
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

1. Add a `Skill` subclass to the appropriate implementation module, for example `skills/motor_skills.py` for motion skills or `skills/perception_skills.py` for perception skills.
2. Create a matching Markdown document under `skills/docs/` (for example, create `skills/docs/your_skill.md`) so the LLM can understand usage.
3. Register the skill instance through `skills/registry.py` in the same place where related skills are registered.

The skill loader (`skills/skill_loader.py`) discovers documents from `skills/docs/` and builds a summary table for the LLM.

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
