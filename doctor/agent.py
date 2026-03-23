"""
doctor/agent.py — Doctor Agent 核心引擎

像 OpenClaw 一样的自主 Agent：
- 读 soul.md 了解自己的身份和职责
- 工具调用循环（LLM 决策 -> 执行工具 -> 反馈 -> 下一步）
- 记忆系统（操作历史 + 经验教训）
- 两种模式：对话模式 / 自主模式
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

_DOCTOR_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _DOCTOR_DIR / "tools"
_MEMORY_DIR = _DOCTOR_DIR / "memory"
_SOUL_PATH = _DOCTOR_DIR / "soul.md"
_HISTORY_PATH = _MEMORY_DIR / "history.json"
_LESSONS_PATH = _MEMORY_DIR / "lessons.md"


# ══════════════════════════════════════════════════════════════
#  工具自动发现
# ══════════════════════════════════════════════════════════════

def _discover_tools() -> Dict[str, dict]:
    """
    扫描 doctor/tools/ 目录，自动发现所有工具。
    每个工具模块需要提供: TOOL_DEF (dict) + execute(**kwargs) -> dict
    """
    tools = {}
    for py_file in sorted(_TOOLS_DIR.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"doctor.tools.{py_file.stem}"
        try:
            mod = importlib.import_module(module_name)
            if hasattr(mod, "TOOL_DEF") and hasattr(mod, "execute"):
                tool_def = mod.TOOL_DEF
                tools[tool_def["name"]] = {
                    "definition": tool_def,
                    "execute": mod.execute,
                }
        except Exception as e:
            logger.warning(f"工具加载失败 {py_file.name}: {e}")
    return tools


# ══════════════════════════════════════════════════════════════
#  记忆系统
# ══════════════════════════════════════════════════════════════

class DoctorMemory:
    """Doctor 的记忆：操作历史 + 经验教训。"""

    MAX_HISTORY = 200

    def __init__(self):
        _MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    def load_history(self) -> List[dict]:
        if not _HISTORY_PATH.exists():
            return []
        try:
            data = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def save_step(self, step: dict) -> None:
        history = self.load_history()
        history.append(step)
        if len(history) > self.MAX_HISTORY:
            history = history[-self.MAX_HISTORY:]
        try:
            _HISTORY_PATH.write_text(
                json.dumps(history, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning(f"历史写入失败: {e}")

    def load_lessons(self) -> str:
        if _LESSONS_PATH.exists():
            return _LESSONS_PATH.read_text(encoding="utf-8")
        return ""

    def save_lesson(self, lesson: str) -> None:
        try:
            existing = self.load_lessons()
            new_content = existing.rstrip() + "\n\n" + lesson.strip() + "\n"
            _LESSONS_PATH.write_text(new_content, encoding="utf-8")
        except OSError as e:
            logger.warning(f"经验写入失败: {e}")

    def get_recent_steps(self, n: int = 10) -> List[dict]:
        history = self.load_history()
        return history[-n:] if len(history) > n else history


# ══════════════════════════════════════════════════════════════
#  Doctor Agent
# ══════════════════════════════════════════════════════════════

class DoctorAgent:
    """
    Doctor Agent 核心引擎。

    两种使用方式：
    1. 自主模式: agent.run(goal) -> Generator，自主循环直到完成
    2. 对话模式: agent.chat(message, history) -> dict，和用户对话
    """

    def __init__(self, llm_client=None):
        # LLM 客户端
        if llm_client is None:
            try:
                from llm_client import get_client
                self._llm = get_client(module="doctor")
            except Exception as e:
                logger.error(f"Doctor LLM 初始化失败: {e}")
                self._llm = None
        else:
            self._llm = llm_client

        # 工具
        self._tools = _discover_tools()
        logger.info(f"Doctor Agent 加载了 {len(self._tools)} 个工具: {list(self._tools.keys())}")

        # 记忆
        self._memory = DoctorMemory()

        # 运行状态
        self._running = False
        self._max_iterations = int(os.environ.get("DOCTOR_MAX_ITERATIONS", "15"))
        self._auto_apply = os.environ.get("DOCTOR_AUTO_APPLY", "false").lower() == "true"

        # 当前会话上下文
        self._session_steps: List[dict] = []

    # ── 身份 ──────────────────────────────────────────────

    def _load_soul(self) -> str:
        """读取 soul.md。"""
        if _SOUL_PATH.exists():
            return _SOUL_PATH.read_text(encoding="utf-8")
        return "你是 AerialClaw 的设备接入工程师。"

    # ── 自主模式 ──────────────────────────────────────────

    def run(self, goal: str = "诊断并修复 adapter 问题，确保硬技能能正常执行") -> Generator[Dict, None, None]:
        """
        自主执行循环。

        Yields:
            {
                "iteration": int,
                "thinking": str,
                "tool": str,
                "args": dict,
                "result": dict,
                "done": bool,
                "error": str | None,
            }
        """
        if not self._llm:
            yield {"error": "LLM 不可用，检查 DOCTOR_LLM_PROVIDER 配置", "done": True}
            return

        self._running = True
        self._session_steps = []
        logger.info(f"Doctor Agent 启动: {goal}")

        for i in range(1, self._max_iterations + 1):
            if not self._running:
                yield {"iteration": i, "done": True, "stopped": True}
                break

            # 1. 构建消息
            messages = self._build_messages(goal)

            # 2. LLM 工具调用
            try:
                tool_defs = self._build_tool_defs()
                response = self._llm.chat_with_tools(
                    messages=messages,
                    tools=tool_defs,
                    tool_choice="auto",
                    temperature=0.3,
                )
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                yield {"iteration": i, "error": f"LLM 调用失败: {e}", "done": True}
                break

            msg = response.get("message", {})
            finish_reason = response.get("finish_reason", "stop")
            thinking = msg.get("content") or ""
            tool_calls = msg.get("tool_calls") or []

            # 3. 没有工具调用 = LLM 认为完成了
            if not tool_calls:
                step = {
                    "iteration": i,
                    "thinking": thinking,
                    "tool": None,
                    "args": {},
                    "result": {"message": thinking},
                    "done": True,
                    "timestamp": time.time(),
                }
                self._session_steps.append(step)
                self._memory.save_step(step)
                yield step
                break

            # 4. 执行每个工具调用
            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                try:
                    tool_args = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}

                logger.info(f"Step {i}: {tool_name}({tool_args})")

                # 执行
                result = self._execute_tool(tool_name, tool_args)

                step = {
                    "iteration": i,
                    "thinking": thinking,
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result,
                    "done": False,
                    "timestamp": time.time(),
                }
                self._session_steps.append(step)
                self._memory.save_step(step)

                yield step

        self._running = False
        logger.info(f"Doctor Agent 结束 ({len(self._session_steps)} 步)")

    def stop(self):
        """中止运行。"""
        self._running = False

    # ── 对话模式 ──────────────────────────────────────────

    def chat(self, message: str, history: List[dict] = None) -> Generator[dict, None, None]:
        """
        对话模式：用户和 Doctor 交互。
        改成生成器模式，支持多轮工具调用循环。

        Yields:
            {
                "reply": str | None,
                "tool": str | None,
                "args": dict | None,
                "result": dict | None,
                "done": bool,
                "error": str | None,
            }
        """
        if not self._llm:
            yield {"reply": "LLM 不可用，检查配置。", "done": True, "error": "no_llm"}
            return

        if history is None:
            history = []

        # 1. 构建初始消息
        soul = self._load_soul()
        lessons = self._memory.load_lessons()
        system_content = soul
        if lessons:
            system_content += f"\n\n## 历史经验\n{lessons[-2000:]}"

        messages = [{"role": "system", "content": system_content}]
        messages.extend(history[-20:])
        messages.append({"role": "user", "content": message})

        # 2. 循环执行工具调用直到完成
        for r in range(50):  # 最多 50 轮，足够解决任何问题
            try:
                tool_defs = self._build_tool_defs()
                response = self._llm.chat_with_tools(
                    messages=messages,
                    tools=tool_defs,
                    tool_choice="auto",
                    temperature=0.3,
                )
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                yield {"error": f"LLM 调用失败: {e}", "done": True}
                break

            msg = response.get("message", {})
            thinking = msg.get("content") or ""
            tool_calls = msg.get("tool_calls") or []

            # 如果没有工具调用，说明对话结束
            if not tool_calls:
                yield {
                    "reply": thinking,
                    "done": True,
                    "timestamp": time.time(),
                }
                break

            # 记录 assistant 的消息 (包含 tool_calls) 到消息列表
            # 过滤空 content，避免 Claude API 报 text content blocks must be non-empty
            safe_msg = {k: v for k, v in msg.items() if k != "content" or v}
            messages.append(safe_msg)

            # 执行工具调用
            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                try:
                    tool_args = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}

                logger.info(f"Chat Round {r+1}: {tool_name}({tool_args})")
                
                # 向前端发送思考过程和工具调用信息
                yield {
                    "thinking": thinking,
                    "tool": tool_name,
                    "args": tool_args,
                    "done": False,
                    "timestamp": time.time(),
                }

                # 执行工具
                result = self._execute_tool(tool_name, tool_args)
                
                # 将工具执行结果反馈到消息列表
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False)[:3000],
                })

                # 向前端发送工具执行结果
                yield {
                    "tool": tool_name,
                    "result": result,
                    "done": False,
                    "timestamp": time.time(),
                }

        else:
            yield {"reply": "达到最大工具调用轮次（50轮）。", "done": True}
            try:
                followup = self._llm.chat(messages, temperature=0.3, max_tokens=2000)
                reply = followup
            except Exception as e:
                reply = f"工具执行完成但生成回复失败: {e}\n\n工具结果: {json.dumps(tool_results, ensure_ascii=False)[:1000]}"



    # ── 内部方法 ──────────────────────────────────────────

    def _build_messages(self, goal: str) -> list:
        """构建自主模式的消息列表。"""
        soul = self._load_soul()
        lessons = self._memory.load_lessons()

        system_content = soul
        if lessons:
            system_content += f"\n\n## 历史经验\n{lessons[-2000:]}"

        messages = [{"role": "system", "content": system_content}]

        # 目标
        messages.append({"role": "user", "content": f"目标: {goal}\n\n请开始工作。每一步调用一个工具，根据结果决定下一步。全部完成后直接回复总结，不再调用工具。"})

        # 注入历史步骤作为上下文
        for step in self._session_steps[-8:]:
            # assistant 调用工具
            tool_name = step.get("tool")
            if tool_name:
                thinking_text = step.get("thinking", "")
                asst_msg = {"role": "assistant", "tool_calls": [{
                        "id": f"call_{step['iteration']}",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(step.get("args", {}), ensure_ascii=False),
                        },
                    }]}
                if thinking_text:
                    asst_msg["content"] = thinking_text
                messages.append(asst_msg)
                # tool 结果
                result_str = json.dumps(step.get("result", {}), ensure_ascii=False)
                if len(result_str) > 3000:
                    result_str = result_str[:3000] + "...(truncated)"
                messages.append({
                    "role": "tool",
                    "tool_call_id": f"call_{step['iteration']}",
                    "content": result_str,
                })
            else:
                # 纯文本思考
                if step.get("thinking"):
                    messages.append({"role": "assistant", "content": step["thinking"]})

        return messages

    def _build_tool_defs(self) -> list:
        """构建 OpenAI Function Calling 格式的工具定义列表。"""
        defs = []
        for name, tool in self._tools.items():
            defs.append({
                "type": "function",
                "function": tool["definition"],
            })
        return defs

    def _execute_tool(self, tool_name: str, args: dict) -> dict:
        """执行工具。"""
        if tool_name not in self._tools:
            return {"success": False, "error": f"未知工具: {tool_name}，可用: {list(self._tools.keys())}"}

        tool = self._tools[tool_name]
        try:
            return tool["execute"](**args)
        except TypeError as e:
            return {"success": False, "error": f"参数错误: {e}"}
        except Exception as e:
            return {"success": False, "error": f"工具执行异常: {e}"}

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def tools(self) -> List[str]:
        return list(self._tools.keys())

    @property
    def session_steps(self) -> List[dict]:
        return list(self._session_steps)


# ══════════════════════════════════════════════════════════════
#  全局单例
# ══════════════════════════════════════════════════════════════

_doctor_agent: Optional[DoctorAgent] = None


def get_doctor_agent() -> DoctorAgent:
    """获取全局 Doctor Agent 实例。"""
    global _doctor_agent
    if _doctor_agent is None:
        _doctor_agent = DoctorAgent()
    return _doctor_agent
