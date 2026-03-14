"""
core/doctor_checks/connection.py — 连接状态检查
"""

from __future__ import annotations

import os
from core.doctor import HealthCheck, CheckResult


class LLMConnectionCheck(HealthCheck):
    name = "LLM API"
    category = "connection"

    def check(self) -> CheckResult:
        provider = os.environ.get("ACTIVE_PROVIDER", "")
        key = os.environ.get("LLM_API_KEY", "")
        url = os.environ.get("LLM_BASE_URL", "")

        if provider == "ollama_local":
            try:
                import requests
                base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
                r = requests.get(f"{base.rstrip('/v1')}/api/tags", timeout=3)
                if r.status_code == 200:
                    models = [m["name"] for m in r.json().get("models", [])[:3]]
                    return self._ok(f"Ollama 在线, 模型: {', '.join(models)}")
            except Exception:
                pass
            return self._warn("Ollama 未响应", "启动: ollama serve")

        if not key or key in ("your-llm-api-key-here", ""):
            return self._fail(f"API Key 未配置 (provider={provider})", "编辑 .env 填入 LLM_API_KEY")

        try:
            import requests
            r = requests.get(f"{url}/models",
                             headers={"Authorization": f"Bearer {key}"}, timeout=5)
            if r.status_code == 200:
                return self._ok(f"在线 ({provider})")
            return self._warn(f"HTTP {r.status_code}", "检查 API Key 和 URL")
        except Exception as e:
            return self._warn(f"连接失败: {str(e)[:50]}", "检查网络和 LLM_BASE_URL")


class VLMConnectionCheck(HealthCheck):
    name = "VLM API"
    category = "connection"

    def check(self) -> CheckResult:
        key = os.environ.get("VLM_API_KEY", os.environ.get("LLM_API_KEY", ""))
        url = os.environ.get("VLM_BASE_URL", os.environ.get("LLM_BASE_URL", ""))

        if not key or key in ("your-vlm-api-key-here", "your-llm-api-key-here", ""):
            return self._warn("VLM 未配置（感知功能受限）", "编辑 .env 填入 VLM_API_KEY")

        try:
            import requests
            r = requests.get(f"{url}/models",
                             headers={"Authorization": f"Bearer {key}"}, timeout=5)
            if r.status_code == 200:
                return self._ok(f"在线 ({os.environ.get('VLM_MODEL', 'unknown')})")
            return self._warn(f"HTTP {r.status_code}")
        except Exception:
            return self._warn("VLM 连接失败", "检查 VLM_BASE_URL")


class MAVSDKCheck(HealthCheck):
    name = "MAVSDK"
    category = "connection"

    def check(self) -> CheckResult:
        try:
            import mavsdk
            return self._ok("已安装")
        except ImportError:
            return self._warn("未安装", "pip install mavsdk")


class PX4Check(HealthCheck):
    name = "PX4 连接"
    category = "connection"

    def check(self) -> CheckResult:
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            s.connect(("127.0.0.1", 14540))
            s.close()
            return self._ok("UDP 14540 可达")
        except Exception:
            return self._warn("PX4 未检测到（使用 Mock 模式）", "启动仿真: make px4_sitl gz_x500")
