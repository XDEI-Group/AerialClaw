# LLM Configuration Guide — LLM 配置说明

## Quick Start

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Fill in your LLM API credentials:
   ```bash
   LLM_BASE_URL=https://api.openai.com/v1
   LLM_API_KEY=sk-your-key-here
   LLM_MODEL=gpt-4o
   ```

3. Done. All modules will use this provider by default.

## Provider System

AerialClaw supports multiple LLM providers simultaneously. Each is defined in `config.py` under `PROVIDERS`.

### Supported Providers

| Provider | Type | Notes |
|----------|------|-------|
| `openai` | Cloud | OpenAI or any compatible API |
| `ollama_local` | Local | Via Ollama, no key needed |
| `deepseek` | Cloud | DeepSeek API |
| `moonshot` | Cloud | Moonshot (Kimi) API |
| `zhipu` | Cloud | Zhipu GLM API |
| `vlm` | Cloud/Local | Vision model, separate config |

### Switching Provider

```bash
# .env
ACTIVE_PROVIDER=ollama_local   # Use local Ollama
# or
ACTIVE_PROVIDER=deepseek       # Use DeepSeek cloud
```

## Per-Module Override

Different modules can use different providers/models. Edit `MODULE_CONFIG` in `config.py`:

```python
MODULE_CONFIG = {
    "planner": {
        "provider": "openai",      # Planning uses GPT-4o
        "model": "gpt-4o",
    },
    "tool_caller": {
        "provider": "deepseek",    # Tool calling uses DeepSeek
        "model": "deepseek-chat",
    },
    "vlm": {
        "provider": "vlm",         # VLM uses separate endpoint
        "model": None,             # follows provider default
    },
}
```

## Adding a New Provider

1. Add entry to `PROVIDERS` in `config.py`:
   ```python
   "my_provider": {
       "api_type": "openai_compat",
       "base_url": _env("MY_PROVIDER_URL", "https://api.example.com/v1"),
       "api_key": _env("MY_PROVIDER_KEY", ""),
       "default_model": "my-model",
       "timeout": 60,
   },
   ```

2. Add env vars to `.env`:
   ```bash
   MY_PROVIDER_URL=https://api.example.com/v1
   MY_PROVIDER_KEY=your-key
   ```

3. Set as active: `ACTIVE_PROVIDER=my_provider`

Any service compatible with OpenAI's `/v1/chat/completions` endpoint will work.

## Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `ACTIVE_PROVIDER` | Default LLM provider | `openai` |
| `LLM_BASE_URL` | OpenAI-compatible API URL | `https://api.openai.com/v1` |
| `LLM_API_KEY` | API key for LLM | (required) |
| `LLM_MODEL` | Default LLM model | `gpt-4o` |
| `VLM_BASE_URL` | VLM API URL | follows `LLM_BASE_URL` |
| `VLM_API_KEY` | API key for VLM | follows `LLM_API_KEY` |
| `VLM_MODEL` | VLM model name | `gpt-4o` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://127.0.0.1:11434/v1` |
| `OLLAMA_MODEL` | Ollama model name | `qwen2.5:7b` |
| `DEEPSEEK_API_KEY` | DeepSeek API key | (optional) |
| `MOONSHOT_API_KEY` | Moonshot API key | (optional) |
| `ZHIPU_API_KEY` | Zhipu API key | (optional) |
