# Perception Guide — 感知模块接入指南

## Dual-Layer Architecture

AerialClaw's perception system operates in two layers:

### Passive Perception (`PerceptionDaemon`)

**File:** `perception/daemon.py`

Runs continuously in the background, periodically generates environment summaries (~100 tokens) by fusing:
- LiDAR point cloud → obstacle detection, distance summary
- Camera images → basic scene description
- Flight state → position, heading, battery

The summary is injected into every LLM planning call as context.

```python
from perception.daemon import init_daemon, get_daemon

# Initialize (called by server.py at startup)
daemon = init_daemon(sensor_bridge=gz_bridge, adapter=px4_adapter)

# Get current environment summary
summary = daemon.get_summary()
# → "Position: N10 E5 D-15, Heading: 90°, Battery: 85%.
#    LiDAR: Clear ahead (>20m), obstacle left 8m.
#    Scene: Urban area with buildings."
```

### Active Perception (`VLMAnalyzer`)

**File:** `perception/vlm_analyzer.py`

Triggered on-demand by the LLM (via hard skills like `detect_object`, `look_around`). Sends camera images to a Vision Language Model for deep analysis.

```python
from perception.vlm_analyzer import init_analyzer, get_analyzer

# Initialize
analyzer = init_analyzer()  # reads from config/env

# Analyze an image
result = analyzer.analyze_image(
    image_base64="...",
    prompt="Describe what you see. Identify any people or vehicles.",
)
# → {"objects": [...], "description": "...", "confidence": 0.85}
```

## Configuring the VLM Provider

All VLM settings are in `.env`:

```bash
VLM_BASE_URL=https://api.openai.com/v1
VLM_API_KEY=your-key-here
VLM_MODEL=gpt-4o
```

### Using a Local Model

```bash
# Run a vision model locally via Ollama
ollama pull llava

# .env
VLM_BASE_URL=http://127.0.0.1:11434/v1
VLM_API_KEY=ollama-local
VLM_MODEL=llava
```

### Using a Fine-tuned Model

If you've fine-tuned a model and deployed it via vLLM, TGI, or similar:

```bash
VLM_BASE_URL=http://your-server:8000/v1
VLM_API_KEY=your-key
VLM_MODEL=your-finetuned-model
```

As long as the endpoint is OpenAI-compatible, it works.

## Adding a New Sensor Source

1. Create a sensor bridge (see `sim/gz_sensor_bridge.py` as reference)
2. Implement methods to provide:
   - `get_lidar_data()` → point cloud or range array
   - `get_camera_image(camera_name)` → base64 JPEG
3. Pass it to `PerceptionDaemon` on initialization:

```python
daemon = init_daemon(sensor_bridge=your_bridge, adapter=your_adapter)
```

4. Update `perception/daemon.py` `_build_lidar_summary()` and `_build_state_summary()` if your sensor data format differs.

## Prompt Engineering

Perception prompts are centralized in `perception/prompts.py`. Modify them to:
- Change the output format of environment summaries
- Adjust VLM analysis prompts for specific use cases
- Control output token budget
