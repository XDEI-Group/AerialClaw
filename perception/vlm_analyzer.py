"""
perception/vlm_analyzer.py
VLM (视觉语言模型) 分析器 — 按需深度图像分析。

第二层感知: LLM 决定需要深度分析时调用。
使用 GPT-4o 等云端视觉大模型做 图像 -> 语言 转换。

功能:
  - 将摄像头图像发送给 VLM, 获取结构化环境描述
  - 支持多种分析模式: 环境分析 / 目标搜索 / 导航辅助
  - 与 PerceptionDaemon 联动: 分析结果自动注入环境摘要

设计:
  - 不在每次循环中调用 (VLM 调用有 API 成本)
  - 由 planner 或感知技能按需触发
  - 输出固定格式 JSON, 便于解析和融合
"""

import base64
import json
import logging
import time
from typing import Optional, Dict, Any

import cv2

logger = logging.getLogger(__name__)


class VLMAnalyzer:
    """
    VLM 分析器。通过 OpenAI 兼容接口调用视觉大模型分析图像。
    """

    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        model: str = None,
        timeout: int = 30,
    ):
        """
        Args:
            base_url: VLM API 地址 (default: from config/env)
            api_key:  API Key (default: from config/env)
            model:    模型名称 (default: from config/env)
            timeout:  请求超时 (秒)
        """
        import os
        self._base_url = (base_url or os.environ.get("VLM_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self._api_key = api_key or os.environ.get("VLM_API_KEY", "")
        self._model = model or os.environ.get("VLM_MODEL", "gpt-4o")
        self._timeout = timeout

        # 调用统计
        self._call_count = 0
        self._total_time = 0.0
        self._last_call_ts = 0.0

    # ── 主接口 ────────────────────────────────────────────────────────────────

    def analyze_image(
        self,
        image,  # np.ndarray (BGR) 或 bytes (JPEG)
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 500,
    ) -> Optional[Dict[str, Any]]:
        """
        发送图像给 VLM 分析。

        Args:
            image:         OpenCV BGR 图像 (np.ndarray) 或 JPEG bytes
            system_prompt: 系统提示词
            user_prompt:   用户提示词
            max_tokens:    最大输出 token 数

        Returns:
            dict: VLM 输出的结构化 JSON, 解析失败返回 None
        """
        import numpy as np

        # 将图像编码为 base64 JPEG
        if isinstance(image, np.ndarray):
            _, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 70])
            b64_image = base64.b64encode(buf.tobytes()).decode("ascii")
        elif isinstance(image, bytes):
            b64_image = base64.b64encode(image).decode("ascii")
        else:
            logger.error("VLM 输入类型不支持: %s", type(image))
            return None

        # 构建 messages
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_image}",
                            "detail": "low",  # 降低 token 消耗
                        },
                    },
                ],
            },
        ]

        # 调用 API
        start = time.time()
        try:
            raw = self._call_api(messages, max_tokens)
            elapsed = time.time() - start
            self._call_count += 1
            self._total_time += elapsed
            self._last_call_ts = time.time()

            logger.info(
                "VLM 分析完成 (%.1fs, 累计 %d 次, 平均 %.1fs)",
                elapsed, self._call_count, self._total_time / self._call_count,
            )

            # 解析 JSON
            return self._parse_json_response(raw)
        except Exception as e:
            logger.error("VLM 分析失败: %s", e)
            return None

    def analyze_environment(
        self,
        image,
        camera_direction: str = "前方",
        altitude: float = 5.0,
        task_context: str = "环境探索",
    ) -> Optional[Dict[str, Any]]:
        """
        环境分析: 分析相机图像, 返回结构化环境描述。

        Args:
            image:            OpenCV BGR 图像
            camera_direction: 相机方向 (前方/后方/左方/右方)
            altitude:         当前高度 (米)
            task_context:     当前任务描述

        Returns:
            dict: 环境分析结果
        """
        from perception.prompts import ENV_ANALYSIS_SYSTEM, ENV_ANALYSIS_USER
        user_prompt = ENV_ANALYSIS_USER.format(
            camera_direction=camera_direction,
            altitude=altitude,
            task_context=task_context,
        )
        return self.analyze_image(image, ENV_ANALYSIS_SYSTEM, user_prompt)

    def search_target(
        self,
        image,
        target_description: str,
        camera_direction: str = "前方",
        altitude: float = 5.0,
    ) -> Optional[Dict[str, Any]]:
        """
        目标搜索: 分析图像, 判断是否发现搜索目标。
        """
        from perception.prompts import TARGET_SEARCH_SYSTEM, TARGET_SEARCH_USER
        user_prompt = TARGET_SEARCH_USER.format(
            target_description=target_description,
            camera_direction=camera_direction,
            altitude=altitude,
        )
        return self.analyze_image(image, TARGET_SEARCH_SYSTEM, user_prompt)

    def evaluate_navigation(
        self,
        image,
        camera_direction: str = "前方",
        target_direction: str = "正前方",
        altitude: float = 5.0,
    ) -> Optional[Dict[str, Any]]:
        """
        导航辅助: 评估飞行路径安全性。
        """
        from perception.prompts import NAVIGATION_SYSTEM, NAVIGATION_USER
        user_prompt = NAVIGATION_USER.format(
            camera_direction=camera_direction,
            target_direction=target_direction,
            altitude=altitude,
        )
        return self.analyze_image(image, NAVIGATION_SYSTEM, user_prompt)

    # ── 统计信息 ──────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """获取调用统计。"""
        return {
            "call_count": self._call_count,
            "total_time": round(self._total_time, 2),
            "avg_time": round(self._total_time / max(self._call_count, 1), 2),
            "last_call": self._last_call_ts,
            "model": self._model,
        }

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _call_api(self, messages: list, max_tokens: int) -> str:
        """调用 OpenAI 兼容的 VLM API。"""
        import urllib.request
        import urllib.error

        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "stream": False,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                content = body["choices"][0]["message"]["content"]
                return content.strip()
            except urllib.error.HTTPError as e:
                status = e.code
                if status in (502, 503) and attempt < max_retries - 1:
                    logger.warning("VLM API %d, 重试 %d/%d", status, attempt + 1, max_retries)
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"VLM API HTTP {status}") from e
            except urllib.error.URLError as e:
                if attempt < max_retries - 1:
                    logger.warning("VLM API 连接失败, 重试 %d/%d: %s", attempt + 1, max_retries, e)
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"VLM API 连接失败: {e}") from e

    def _parse_json_response(self, raw: str) -> Optional[Dict[str, Any]]:
        """解析 VLM 输出的 JSON, 容忍 markdown 代码块包裹。"""
        # 去掉 markdown 代码块标记
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # 去掉第一行 ```json 和最后一行 ```
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取第一个 JSON 对象
            import re
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            logger.warning("VLM 输出 JSON 解析失败: %s", text[:200])
            return None


# ── 全局单例 ──────────────────────────────────────────────────────────────────

_analyzer: Optional[VLMAnalyzer] = None


def get_analyzer() -> Optional[VLMAnalyzer]:
    """获取全局 VLM 分析器实例。"""
    return _analyzer


def init_analyzer(**kwargs) -> VLMAnalyzer:
    """初始化全局 VLM 分析器。"""
    global _analyzer
    _analyzer = VLMAnalyzer(**kwargs)
    logger.info("VLM 分析器已初始化 (model=%s)", _analyzer._model)
    return _analyzer
