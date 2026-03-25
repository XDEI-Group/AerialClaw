"""
passive_perception.py — 被动感知引擎

持续在后台运行，定期对摄像头画面做 VLM 结构化分析，
将障碍物、建筑物、地面特征等写入 WorldModel + 推送前端态势图。

架构角色：
  - 被动感知：每 N 帧自动分析，维护环境感知（障碍物、空旷区域）
  - 主动感知：LLM 调用 perceive() 技能，自己写 prompt 获取特定信息

输出格式（结构化 JSON）：
  {
    "obstacles": [{"direction": "front", "type": "building", "distance_m": 30, "height_m": 50, "description": "..."}],
    "open_areas": [{"direction": "left", "description": "空旷道路"}],
    "summary": "前方30m有高层建筑，左侧空旷，下方是十字路口",
    "timestamp": 1234567890.0
  }
"""

import logging
import time
import threading
import json
from typing import Optional, Callable

logger = logging.getLogger("perception.passive")

# VLM 被动感知提示词（输出结构化 JSON，~100 tokens）
PASSIVE_PROMPT = """Analyze this drone camera image. Output ONLY a JSON object:
{
  "obstacles": [{"direction": "front/left/right/rear/below", "type": "building/tree/tower/vehicle/other", "distance_m": <estimated meters>, "height_m": <if applicable>, "width_m": <if applicable>}],
  "features": [{"type": "road/water/park/parking/rooftop", "direction": "below/front/left/right", "description": "<brief>"}],
  "hazards": [{"type": "collision_risk/no_landing_zone/restricted", "direction": "<dir>", "description": "<brief>"}],
  "summary": "<one sentence scene description in Chinese>"
}
Be concise. Estimate distances from drone perspective. If unsure, use rough estimates."""

# 主动感知提示词模板
ACTIVE_PROMPT_TEMPLATE = """Analyze this drone camera image ({direction} view).
Focus: {focus}
Output ONLY a JSON object with your findings:
{{
  "findings": ["{focus} related observations"],
  "objects_detected": [{{"type": "<type>", "description": "<detail>", "confidence": 0.0-1.0}}],
  "summary": "<answer to the focus question in Chinese>"
}}"""


class PassivePerception:
    """后台被动感知引擎。定期对摄像头帧做 VLM 分析，更新 WorldModel。"""

    def __init__(self, adapter_getter, world_model, vlm_analyzer,
                 socketio=None, interval_seconds: float = 5.0):
        """
        Args:
            adapter_getter: callable，返回当前 adapter 实例
            world_model: WorldModel 实例
            vlm_analyzer: VLM 分析器（有 analyze_image 方法）
            socketio: SocketIO 实例，用于推送感知结果到前端
            interval_seconds: 被动感知间隔（秒）
        """
        self._get_adapter = adapter_getter
        self._world_model = world_model
        self._vlm = vlm_analyzer
        self._sio = socketio
        self._interval = interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._latest_perception: dict = {}
        self._lock = threading.Lock()

    def start(self):
        """启动被动感知后台线程。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="passive-perception")
        self._thread.start()
        logger.info("被动感知引擎已启动 (间隔 %.1fs)", self._interval)

    def stop(self):
        self._running = False

    def get_latest(self) -> dict:
        """获取最新的被动感知结果（供 LLM planner 读取）。"""
        with self._lock:
            return self._latest_perception.copy()

    def perceive_active(self, direction: str = "front", focus: str = "") -> dict:
        """
        主动感知：LLM 按需调用，用自定义 prompt 分析指定方向的图像。
        
        Args:
            direction: 摄像头方向 (front/left/right/rear/down)
            focus: LLM 自己写的关注点（如"窗户玻璃是否有裂纹"）
        
        Returns:
            VLM 结构化分析结果
        """
        adapter = self._get_adapter()
        if not adapter or not hasattr(adapter, 'get_image_base64'):
            return {"error": "adapter 不可用", "summary": "无法获取图像"}

        dir_to_cam = {"front": "cam_front", "left": "cam_left", "right": "cam_right",
                      "rear": "cam_rear", "down": "cam_down"}
        cam_name = dir_to_cam.get(direction, f"cam_{direction}")

        try:
            import base64
            b64_str = adapter.get_image_base64(camera_name=cam_name)
            if not b64_str:
                return {"error": f"{direction} 摄像头无图像", "summary": "图像获取失败"}

            image_bytes = base64.b64decode(b64_str)
            prompt = ACTIVE_PROMPT_TEMPLATE.format(direction=direction, focus=focus or "全面观察环境")
            
            result = self._vlm.analyze_image(image_bytes, system_prompt="You are a drone perception system.", user_prompt=prompt)
            if result and isinstance(result, dict):
                result["direction"] = direction
                result["timestamp"] = time.time()
                return result
            elif result and isinstance(result, str):
                # fallback: 纯文本
                parsed = self._try_parse_json(result)
                if parsed:
                    parsed["direction"] = direction
                    parsed["timestamp"] = time.time()
                    return parsed
                return {"summary": result, "direction": direction, "timestamp": time.time()}
            return {"error": "VLM 返回空", "summary": "分析失败"}
        except Exception as e:
            logger.warning("主动感知失败 (%s): %s", direction, e)
            return {"error": str(e), "summary": f"感知异常: {e}"}

    def _loop(self):
        """后台循环：定期拍前方 + 下方，VLM 分析，更新 WorldModel。"""
        while self._running:
            try:
                adapter = self._get_adapter()
                if not adapter or not hasattr(adapter, 'get_image_base64'):
                    time.sleep(self._interval)
                    continue

                # 飞行中才做被动感知（悬停时 observe 会主动看）
                if not getattr(adapter, 'is_flying', False) and not getattr(adapter, 'in_air', True):
                    time.sleep(self._interval)
                    continue

                perception_result = self._analyze_surroundings(adapter)
                if perception_result:
                    with self._lock:
                        self._latest_perception = perception_result

                    # 更新 WorldModel 障碍物
                    self._update_world_model(perception_result)

                    # 推送到前端态势图
                    if self._sio:
                        self._sio.emit("perception_update", perception_result)

                    logger.debug("被动感知更新: %s", perception_result.get("summary", ""))

            except Exception as e:
                logger.warning("被动感知异常: %s", e)

            time.sleep(self._interval)

    def _analyze_surroundings(self, adapter) -> Optional[dict]:
        """分析前方画面，返回结构化感知结果。"""
        import base64

        try:
            b64_str = adapter.get_image_base64(camera_name="cam_front")
            if not b64_str:
                return None

            image_bytes = base64.b64decode(b64_str)
            result = self._vlm.analyze_image(
                image_bytes,
                system_prompt="You are a drone passive perception system. Output structured JSON only.",
                user_prompt=PASSIVE_PROMPT,
            )
            
            if result and isinstance(result, dict):
                result["timestamp"] = time.time()
                try:
                    pos = adapter.get_position()
                    result["drone_position"] = {"north": pos.north, "east": pos.east, "down": pos.down}
                except:
                    pass
                return result
            elif result and isinstance(result, str):
                parsed = self._try_parse_json(result)
                if parsed:
                    parsed["timestamp"] = time.time()
                    # 获取当前位置用于定位障碍物
                    try:
                        pos = adapter.get_position()
                        parsed["drone_position"] = {"north": pos.north, "east": pos.east, "down": pos.down}
                    except:
                        pass
                    return parsed
            return None
        except Exception as e:
            logger.warning("被动感知分析失败: %s", e)
            return None

    def _update_world_model(self, perception: dict):
        """将感知结果写入 WorldModel。"""
        obstacles = perception.get("obstacles", [])
        if obstacles and self._world_model:
            # 追加新障碍物（去重：同方向同类型不重复添加）
            existing = self._world_model._state.get("map", {}).get("obstacles", [])
            for obs in obstacles:
                dup = any(
                    e.get("direction") == obs.get("direction") and e.get("type") == obs.get("type")
                    and abs(e.get("distance_m", 0) - obs.get("distance_m", 0)) < 10
                    for e in existing
                )
                if not dup:
                    existing.append({
                        **obs,
                        "timestamp": time.time(),
                        "source": "passive_perception"
                    })
            
            self._world_model.update_world_state({
                "map": {"obstacles": existing[-50:]}  # 保留最近50个
            })

    @staticmethod
    def _try_parse_json(text: str) -> Optional[dict]:
        """尝试从 VLM 输出中提取 JSON。"""
        text = text.strip()
        # 尝试直接解析
        try:
            return json.loads(text)
        except:
            pass
        # 尝试提取 ```json ... ``` 块
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start) if "```" in text[start:] else len(text)
            try:
                return json.loads(text[start:end].strip())
            except:
                pass
        # 尝试找第一个 { ... }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except:
                pass
        return None
