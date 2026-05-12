"""Persistent runtime LLM configuration.

The UI can edit providers/module overrides at runtime.  config.py contains the
bootstrap defaults, while this file stores user edits in a local JSON override
file so a server restart does not lose them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).parent / ".aerialclaw_llm_config.json"
_PROVIDER_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def _public_provider(provider: dict[str, Any]) -> dict[str, Any]:
    return {
        "api_type": provider.get("api_type", "openai_compat"),
        "base_url": str(provider.get("base_url", "")).rstrip("/"),
        "api_key": provider.get("api_key", ""),
        "default_model": str(provider.get("default_model", "")),
        "timeout": int(provider.get("timeout", 60) or 60),
    }


def validate_provider_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("provider 名称不能为空")
    if not _PROVIDER_RE.match(name):
        raise ValueError("provider 名称只能包含字母、数字、下划线、点和短横线，最长 64 位")
    return name


def load_runtime_config(cfg: Any) -> None:
    """Apply persisted runtime overrides to the imported config module."""
    if not CONFIG_PATH.exists():
        return
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[LLMConfigStore] 加载持久化配置失败，已忽略: {e}")
        return

    providers = data.get("providers") or {}
    if isinstance(providers, dict):
        for name, provider in providers.items():
            try:
                clean_name = validate_provider_name(name)
                if isinstance(provider, dict):
                    cfg.PROVIDERS[clean_name] = _public_provider(provider)
            except Exception as e:
                print(f"[LLMConfigStore] 跳过无效 provider {name!r}: {e}")

    active = data.get("active_provider")
    if isinstance(active, str) and active in cfg.PROVIDERS:
        cfg.ACTIVE_PROVIDER = active

    modules = data.get("modules") or {}
    if isinstance(modules, dict):
        for module_name, module_cfg in modules.items():
            if module_name not in cfg.MODULE_CONFIG or not isinstance(module_cfg, dict):
                continue
            provider = module_cfg.get("provider")
            model = module_cfg.get("model")
            if provider is not None and provider not in cfg.PROVIDERS:
                provider = None
            cfg.MODULE_CONFIG[module_name]["provider"] = provider
            cfg.MODULE_CONFIG[module_name]["model"] = model or None


def save_runtime_config(cfg: Any) -> None:
    """Persist the current runtime LLM config atomically."""
    data = {
        "active_provider": cfg.ACTIVE_PROVIDER,
        "providers": {
            name: _public_provider(provider)
            for name, provider in cfg.PROVIDERS.items()
        },
        "modules": {
            name: {
                "provider": module_cfg.get("provider"),
                "model": module_cfg.get("model"),
            }
            for name, module_cfg in cfg.MODULE_CONFIG.items()
        },
    }
    tmp = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)
