# ============================================================
# config.py  —— AerialClaw Global Configuration
#
# All sensitive values (API keys, URLs) are loaded from .env file.
# Copy .env.example to .env and fill in your values.
#
# 所有敏感配置（API Key、服务地址）从 .env 文件加载。
# 复制 .env.example 为 .env 后填入你的值即可。
# ============================================================

from __future__ import annotations
import os
from pathlib import Path

# ── Load .env ────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; user can export env vars manually

# ── Helper ───────────────────────────────────────────────────
def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)

# ── 1. Provider Configuration ───────────────────────────────
#
# Each provider entry defines an LLM service endpoint.
# api_key values are read from environment variables.
#
# 每个 provider 定义一个 LLM 服务端点。
# api_key 从环境变量读取，代码中不出现任何密钥。
#
PROVIDERS: dict[str, dict] = {

    # Local model via Ollama (no key needed)
    # 本地模型（通过 Ollama 运行，无需 key）
    "ollama_local": {
        "api_type":      "openai_compat",
        "base_url":      _env("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
        "api_key":       "ollama-local",
        "default_model": _env("OLLAMA_MODEL", "qwen2.5:7b"),
        "timeout":       300,
    },

    # OpenAI-compatible API (e.g., OpenAI, Azure, third-party proxy)
    # OpenAI 兼容接口（官方、Azure 或第三方代理均可）
    "openai": {
        "api_type":      "openai_compat",
        "base_url":      _env("LLM_BASE_URL", "https://api.openai.com/v1"),
        "api_key":       _env("LLM_API_KEY", ""),
        "default_model": _env("LLM_MODEL", "gpt-4o"),
        "timeout":       150,
    },

    # DeepSeek
    "deepseek": {
        "api_type":      "openai_compat",
        "base_url":      "https://api.deepseek.com/v1",
        "api_key":       _env("DEEPSEEK_API_KEY", ""),
        "default_model": "deepseek-chat",
        "timeout":       60,
    },

    # Moonshot (Kimi)
    "moonshot": {
        "api_type":      "openai_compat",
        "base_url":      "https://api.moonshot.cn/v1",
        "api_key":       _env("MOONSHOT_API_KEY", ""),
        "default_model": "moonshot-v1-8k",
        "timeout":       60,
    },

    # Zhipu (GLM)
    "zhipu": {
        "api_type":      "openai_compat",
        "base_url":      "https://open.bigmodel.cn/api/paas/v4",
        "api_key":       _env("ZHIPU_API_KEY", ""),
        "default_model": "glm-4",
        "timeout":       60,
    },

    # VLM - Vision Language Model (for image analysis)
    # VLM - 视觉语言模型（用于图像深度分析）
    "vlm": {
        "api_type":      "openai_compat",
        "base_url":      _env("VLM_BASE_URL", _env("LLM_BASE_URL", "https://api.openai.com/v1")),
        "api_key":       _env("VLM_API_KEY", _env("LLM_API_KEY", "")),
        "default_model": _env("VLM_MODEL", "gpt-4o"),
        "timeout":       60,
    },

    # Add more providers here / 在此添加更多 provider...
}

# ── 2. Active Provider ───────────────────────────────────────
#
# All modules use this provider by default unless overridden below.
# 所有模块默认使用此 provider，除非在下方单独指定。
#
ACTIVE_PROVIDER: str = _env("ACTIVE_PROVIDER", "openai")

# ── 3. Per-module Configuration (optional) ───────────────────
#
# Override provider/model for specific modules.
# Set to None to follow ACTIVE_PROVIDER and its default_model.
#
# 为特定模块指定不同的 provider/model。
# 设为 None 则跟随 ACTIVE_PROVIDER。
#
MODULE_CONFIG: dict[str, dict] = {

    # Planning module (brain/planner_agent.py)
    # 规划模块
    "planner": {
        "provider": None,
        "model":    None,
    },

    # Skill document generator (skills/skill_doc_generator.py)
    # 技能文档生成
    "doc_generator": {
        "provider": None,
        "model":    None,
    },

    # Tool-calling planner (requires Function Calling support)
    # 工具调用规划（需要模型支持 Function Calling）
    "tool_caller": {
        "provider": None,
        "model":    None,
    },

    # VLM vision module (perception/vlm_analyzer.py)
    # 视觉语言模型模块
    "vlm": {
        "provider": "vlm",
        "model":    None,
    },
}

# ── 4. Skill Paths ───────────────────────────────────────────
SKILLS_ROOT: Path = Path(__file__).parent / "skills"
