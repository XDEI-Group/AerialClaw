"""
core/device_onboarding.py — 对话式设备建档

操作员通过自然语言描述设备，LLM 引导建档：
  1. 分析描述，提取设备信息
  2. 追问缺失细节
  3. 可选：搜索网上资料补充
  4. 生成 device_profiles/<device_id>.md 档案
  5. 匹配技能子集
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.logger import get_logger

logger = get_logger(__name__)

_PROFILES_DIR = Path(__file__).parent.parent / "device_profiles"
_PROFILES_DIR.mkdir(exist_ok=True)

ONBOARDING_SYSTEM_PROMPT = """你是 AerialClaw 的设备接入专家。操作员正在接入一台新设备，你需要通过对话了解这台设备的全部信息。

你的任务：
1. 根据操作员的描述，提取设备的关键信息
2. 如果信息不完整，追问具体细节（型号、传感器、通信方式、物理限制等）
3. 当信息足够时，生成结构化的设备档案

对话风格：
- 简洁专业，不废话
- 一次最多问 2-3 个问题
- 主动猜测常见配置，让操作员确认即可

当你认为信息足够时，输出以下 JSON（用 ```json 包裹）：

```json
{
  "ready": true,
  "profile": {
    "name": "设备名称",
    "model": "具体型号",
    "type": "UAV/UGV/ARM/SENSOR/PHONE/CUSTOM",
    "capabilities": ["fly", "camera", "lidar", ...],
    "sensors": ["gps", "imu", "camera_front", ...],
    "physical_limits": {
      "max_speed": 10.0,
      "max_altitude": 120.0,
      "battery_capacity": "5000mAh",
      "weight": "1.5kg",
      "max_payload": "0.5kg"
    },
    "communication": "mavlink/ros2/http/serial/wifi",
    "notes": "其他重要信息"
  }
}
```

如果信息还不够，正常回复文字继续对话，不要输出 JSON。
"""


class DeviceOnboarding:
    """
    对话式设备建档管理器。

    每个设备的建档过程是一个独立的对话会话。
    """

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client
        self._sessions: Dict[str, List[Dict[str, str]]] = {}

    def start_session(self, device_id: str) -> str:
        """
        开始建档会话。

        Returns:
            AI 的欢迎消息
        """
        self._sessions[device_id] = []
        welcome = (
            f"开始为设备 [{device_id}] 建档。\n"
            "请描述这台设备：是什么类型？什么型号？有哪些传感器和能力？"
        )
        self._sessions[device_id].append({"role": "assistant", "content": welcome})
        return welcome

    def chat(self, device_id: str, user_input: str) -> Dict[str, Any]:
        """
        建档对话。

        Args:
            device_id: 设备 ID
            user_input: 操作员输入

        Returns:
            {"reply": str, "profile_ready": bool, "profile": dict|None}
        """
        if device_id not in self._sessions:
            self.start_session(device_id)

        history = self._sessions[device_id]
        history.append({"role": "user", "content": user_input})

        if self._llm is None:
            return {"reply": "LLM 未配置，无法进行对话建档", "profile_ready": False, "profile": None}

        messages = [{"role": "system", "content": ONBOARDING_SYSTEM_PROMPT}] + history

        try:
            raw = self._llm.chat(messages, temperature=0.3, max_tokens=800)
        except Exception as e:
            logger.error("建档对话 LLM 调用失败: %s", e)
            return {"reply": f"AI 响应失败: {e}", "profile_ready": False, "profile": None}

        history.append({"role": "assistant", "content": raw})

        # 检查是否输出了完整的设备档案
        profile = self._extract_profile(raw)
        if profile and profile.get("ready"):
            device_profile = profile.get("profile", {})
            self._save_profile(device_id, device_profile)
            # 清理回复文本（去掉 JSON 块）
            clean_reply = re.sub(r'```json[\s\S]*?```', '', raw).strip()
            if not clean_reply:
                clean_reply = f"设备 [{device_id}] 建档完成！档案已保存。"
            return {"reply": clean_reply, "profile_ready": True, "profile": device_profile}

        return {"reply": raw, "profile_ready": False, "profile": None}

    def _extract_profile(self, text: str) -> Optional[Dict]:
        """从 LLM 输出中提取 JSON 档案"""
        match = re.search(r'```json\s*([\s\S]*?)```', text)
        if match:
            try:
                data = json.loads(match.group(1))
                if data.get("ready"):
                    return data
            except json.JSONDecodeError:
                pass
        return None

    def _save_profile(self, device_id: str, profile: Dict) -> str:
        """保存设备档案为 Markdown 文件"""
        path = _PROFILES_DIR / f"{device_id}.md"
        ts = time.strftime("%Y-%m-%d %H:%M")

        limits = profile.get("physical_limits", {})
        limits_lines = "\n".join(f"- {k}: {v}" for k, v in limits.items()) if limits else "- 未知"

        content = f"""# {profile.get('name', device_id)} — 设备档案

> 创建时间: {ts}
> 设备 ID: {device_id}

## 基本信息
- 型号: {profile.get('model', '未知')}
- 类型: {profile.get('type', 'CUSTOM')}
- 通信方式: {profile.get('communication', '未知')}

## 能力
{chr(10).join('- ' + c for c in profile.get('capabilities', []))}

## 传感器
{chr(10).join('- ' + s for s in profile.get('sensors', []))}

## 物理限制
{limits_lines}

## 备注
{profile.get('notes', '无')}

## 技能绑定
> 由系统自动管理，设备接入时匹配，退出时挂起

## 经验记录
> 随任务执行自动积累
"""
        path.write_text(content, encoding="utf-8")
        logger.info("设备档案已保存: %s", path)
        return str(path)

    def get_profile(self, device_id: str) -> Optional[str]:
        """读取设备档案"""
        path = _PROFILES_DIR / f"{device_id}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def list_profiles(self) -> List[str]:
        """列出所有设备档案"""
        return [p.stem for p in _PROFILES_DIR.glob("*.md")]

    def end_session(self, device_id: str) -> None:
        """结束建档会话"""
        self._sessions.pop(device_id, None)
