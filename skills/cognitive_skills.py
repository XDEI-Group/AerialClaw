"""
cognitive_skills.py — 认知技能（信息层）

元技能：信息获取、计算与文件操作。
skill_type = "cognitive"，robot_type = []（通用，所有设备可用）。

包含:
    RunPython / HttpRequest / ReadFile / WriteFile
"""

import logging
import os
import re
import time
from pathlib import Path

from skills.base_skill import Skill, SkillResult

logger = logging.getLogger(__name__)


def _parse_pos(robot_state):
    """从 robot_state 解析位置，兼容数组和字典格式。返回 (north, east, down)"""
    pos = robot_state.get("position", [0, 0, 0])
    if isinstance(pos, (list, tuple)):
        return float(pos[0]) if len(pos) > 0 else 0.0, float(pos[1]) if len(pos) > 1 else 0.0, float(pos[2]) if len(pos) > 2 else 0.0
    return float(pos.get("north", 0)), float(pos.get("east", 0)), float(pos.get("down", 0))


# 工作目录基准（限制文件读写范围）
_WORK_DIR = Path(os.environ.get("AERIALCLAW_WORKDIR", ".")).resolve()

# 禁止访问的敏感路径前缀
_BLOCKED_PATHS = ["/etc", "/usr", "/bin", "/sbin", "/lib", "/boot",
                  str(Path.home() / ".ssh"), str(Path.home() / ".gnupg")]

# 禁止的内网 IP 模式
_PRIVATE_IP_PATTERNS = [
    re.compile(r"^https?://127\."),
    re.compile(r"^https?://localhost"),
    re.compile(r"^https?://192\.168\."),
    re.compile(r"^https?://10\."),
    re.compile(r"^https?://172\.(1[6-9]|2\d|3[01])\."),
]

_MAX_RESPONSE_LEN = 10_000
_MAX_FILE_SIZE = 1024 * 1024  # 1 MB


def _is_safe_url(url: str) -> bool:
    for pat in _PRIVATE_IP_PATTERNS:
        if pat.match(url):
            return False
    return True


def _resolve_safe_path(path_str: str) -> tuple[Path | None, str]:
    """
    解析路径并验证是否在工作目录内、不在敏感目录中。
    返回 (resolved_path, error_msg)，成功时 error_msg 为空字符串。
    """
    try:
        target = (_WORK_DIR / path_str).resolve()
    except Exception as e:
        return None, f"路径解析失败: {e}"

    # 必须在工作目录内
    try:
        target.relative_to(_WORK_DIR)
    except ValueError:
        return None, f"路径超出工作目录范围: {target}"

    # 禁止访问敏感系统路径
    target_str = str(target)
    for blocked in _BLOCKED_PATHS:
        if target_str.startswith(blocked):
            return None, f"禁止访问敏感路径: {blocked}"

    return target, ""


# ══════════════════════════════════════════════════════════════════════════════
#  RunPython
# ══════════════════════════════════════════════════════════════════════════════

class RunPython(Skill):
    """在沙箱中执行 Python 代码"""

    name = "run_python"
    skill_type = "cognitive"
    description = "在安全沙箱中执行 Python 代码，返回 stdout/stderr"
    robot_type = []
    preconditions = []
    cost = 2.0
    input_schema = {"code": "要执行的 Python 代码（字符串）"}
    output_schema = {"stdout": "标准输出", "stderr": "标准错误", "exit_code": "int"}

    def execute(self, input_data: dict) -> SkillResult:
        code = input_data.get("code", "")
        if not code.strip():
            return SkillResult(success=False, error_msg="code 参数不能为空")

        try:
            from core.safety.sandbox import get_sandbox
            sandbox = get_sandbox()
        except Exception as e:
            return SkillResult(success=False, error_msg=f"沙箱初始化失败: {e}")

        start = time.time()
        try:
            result = sandbox.execute(code, timeout=10)
        except Exception as e:
            return SkillResult(
                success=False,
                error_msg=f"沙箱执行异常: {e}",
                cost_time=round(time.time() - start, 2),
            )

        elapsed = round(time.time() - start, 2)
        logger.info(f"run_python: exit_code={result.exit_code}, time={elapsed}s")

        return SkillResult(
            success=result.success,
            output={
                "stdout": result.stdout[:_MAX_RESPONSE_LEN],
                "stderr": result.stderr[:_MAX_RESPONSE_LEN],
                "exit_code": result.exit_code,
            },
            error_msg=result.stderr[:500] if not result.success else "",
            cost_time=elapsed,
            logs=[f"run_python: exit={result.exit_code}, {elapsed}s [{result.sandbox_type}]"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  HttpRequest
# ══════════════════════════════════════════════════════════════════════════════

class HttpRequest(Skill):
    """发起 HTTP 请求"""

    name = "http_request"
    skill_type = "cognitive"
    description = "发起 HTTP GET/POST 请求获取信息"
    robot_type = []
    preconditions = []
    cost = 1.5
    input_schema = {
        "url": "请求地址（仅允许公网 URL）",
        "method": "GET 或 POST，默认 GET",
        "data": "POST 请求体（可选，dict 或 str）",
    }
    output_schema = {
        "status_code": "int，HTTP 状态码",
        "body": "str，响应体（最多 10000 字符）",
    }

    def execute(self, input_data: dict) -> SkillResult:
        url = input_data.get("url", "").strip()
        method = input_data.get("method", "GET").upper()
        data = input_data.get("data", None)

        if not url:
            return SkillResult(success=False, error_msg="url 参数不能为空")

        if not _is_safe_url(url):
            return SkillResult(success=False, error_msg=f"禁止访问内网地址: {url}")

        if method not in ("GET", "POST"):
            return SkillResult(success=False, error_msg=f"不支持的 HTTP 方法: {method}")

        try:
            import requests as _requests
        except ImportError:
            return SkillResult(success=False, error_msg="requests 库未安装，请 pip install requests")

        start = time.time()
        try:
            if method == "GET":
                resp = _requests.get(url, timeout=10)
            else:
                resp = _requests.post(url, json=data if isinstance(data, dict) else None,
                                      data=data if isinstance(data, str) else None, timeout=10)
        except Exception as e:
            return SkillResult(
                success=False,
                error_msg=f"HTTP 请求失败: {e}",
                cost_time=round(time.time() - start, 2),
            )

        elapsed = round(time.time() - start, 2)
        body = resp.text[:_MAX_RESPONSE_LEN]
        ok = resp.ok
        logger.info(f"http_request: {method} {url} → {resp.status_code}, {elapsed}s")

        return SkillResult(
            success=ok,
            output={"status_code": resp.status_code, "body": body},
            error_msg="" if ok else f"HTTP {resp.status_code}",
            cost_time=elapsed,
            logs=[f"http_request: {method} {url} → {resp.status_code} ({elapsed}s)"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  ReadFile
# ══════════════════════════════════════════════════════════════════════════════

class ReadFile(Skill):
    """读取文件"""

    name = "read_file"
    skill_type = "cognitive"
    description = "读取指定路径的文件内容（限工作目录内，最大 1MB）"
    robot_type = []
    preconditions = []
    cost = 0.5
    input_schema = {"path": "文件路径（相对于工作目录）"}
    output_schema = {"content": "str，文件内容", "size_bytes": "int，文件字节数"}

    def execute(self, input_data: dict) -> SkillResult:
        path_str = input_data.get("path", "").strip()
        if not path_str:
            return SkillResult(success=False, error_msg="path 参数不能为空")

        target, err = _resolve_safe_path(path_str)
        if err:
            return SkillResult(success=False, error_msg=err)

        if not target.exists():
            return SkillResult(success=False, error_msg=f"文件不存在: {path_str}")

        if not target.is_file():
            return SkillResult(success=False, error_msg=f"不是文件: {path_str}")

        size = target.stat().st_size
        if size > _MAX_FILE_SIZE:
            return SkillResult(
                success=False,
                error_msg=f"文件过大: {size / 1024:.0f}KB > 1MB 限制",
            )

        start = time.time()
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return SkillResult(
                success=False,
                error_msg=f"读取失败: {e}",
                cost_time=round(time.time() - start, 2),
            )

        elapsed = round(time.time() - start, 2)
        logger.info(f"read_file: {target} ({size}B), {elapsed}s")

        return SkillResult(
            success=True,
            output={"content": content, "size_bytes": size},
            cost_time=elapsed,
            logs=[f"read_file: {path_str} ({size}B)"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  WriteFile
# ══════════════════════════════════════════════════════════════════════════════

class WriteFile(Skill):
    """写入文件"""

    name = "write_file"
    skill_type = "cognitive"
    description = "将内容写入文件（限工作目录内，操作会记录审计日志）"
    robot_type = []
    preconditions = []
    cost = 1.0
    input_schema = {
        "path": "文件路径（相对于工作目录）",
        "content": "要写入的文件内容",
    }
    output_schema = {"size_bytes": "int，写入字节数", "path": "str，实际写入路径"}

    def execute(self, input_data: dict) -> SkillResult:
        path_str = input_data.get("path", "").strip()
        content = input_data.get("content", "")

        if not path_str:
            return SkillResult(success=False, error_msg="path 参数不能为空")

        target, err = _resolve_safe_path(path_str)
        if err:
            return SkillResult(success=False, error_msg=err)

        start = time.time()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except Exception as e:
            return SkillResult(
                success=False,
                error_msg=f"写入失败: {e}",
                cost_time=round(time.time() - start, 2),
            )

        size = len(content.encode("utf-8"))
        elapsed = round(time.time() - start, 2)

        # 审计日志
        logger.info(f"[AUDIT] write_file: {target} ({size}B), {time.strftime('%Y-%m-%d %H:%M:%S')}")

        return SkillResult(
            success=True,
            output={"size_bytes": size, "path": str(target)},
            cost_time=elapsed,
            logs=[f"write_file: {path_str} ({size}B) 写入成功"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Report — 实时巡检报告
# ══════════════════════════════════════════════════════════════════════════════

class Report(Skill):
    """边飞边写报告，实时推送到前端。也可以追加条目到累积报告中。"""

    name = "report"
    description = "记录一条巡检发现并实时推送给操作员。支持边飞边写报告，所有条目会累积成完整报告。"
    skill_type = "cognitive"
    robot_type = []

    input_schema = {
        "content": {"type": "str", "description": "报告内容，描述当前位置看到的情况"},
        "severity": {"type": "str", "description": "严重程度: info/warning/danger，默认 info"},
    }
    output_schema = {
        "report_id": {"type": "int", "description": "报告条目编号"},
        "total_entries": {"type": "int", "description": "累计报告条目数"},
    }
    preconditions = []

    # 类级别的报告累积器
    _reports = []

    def execute(self, robot_state: dict, **params) -> SkillResult:
        start = time.time()
        content = params.get("content", "")
        severity = params.get("severity", "info")

        if not content:
            return SkillResult(success=False, error_msg="报告内容不能为空", cost_time=0)

        # 获取当前位置
        _n, _e, _d = _parse_pos(robot_state)
        pos_str = f"({_n:.0f}, {_e:.0f}, h={abs(_d):.0f}m)"

        entry = {
            "id": len(Report._reports) + 1,
            "time": time.strftime("%H:%M:%S"),
            "position": pos_str,
            "severity": severity,
            "content": content,
        }
        Report._reports.append(entry)

        # 通过 socketio 实时推送
        icon = {"info": "📋", "warning": "⚠️", "danger": "🚨"}.get(severity, "📋")
        msg = f"{icon} 巡检报告 #{entry['id']} [{entry['time']}] {pos_str}\n{content}"

        try:
            from server import socketio
            socketio.emit("ai_chat_reply", {
                "ok": True,
                "reply": msg,
                "intent": "patrol_report",
            })
            # 同时推送位置标注到地图
            socketio.emit("map_report", {
                "id": entry["id"],
                "n": _n,
                "e": _e,
                "severity": severity,
                "content": content[:60],
            })
        except Exception as e:
            logger.warning(f"推送报告失败: {e}")

        elapsed = time.time() - start
        return SkillResult(
            success=True,
            output={"report_id": entry["id"], "total_entries": len(Report._reports)},
            cost_time=elapsed,
            logs=[f"report #{entry['id']}: {severity} - {content[:50]}"],
        )

    @classmethod
    def get_full_report(cls) -> str:
        """获取完整累积报告（供任务完成时汇总）。"""
        if not cls._reports:
            return "（无巡检记录）"
        lines = ["# 巡检报告\n"]
        for r in cls._reports:
            icon = {"info": "📋", "warning": "⚠️", "danger": "🚨"}.get(r["severity"], "📋")
            lines.append(f"{icon} **#{r['id']}** [{r['time']}] {r['position']}")
            lines.append(f"   {r['content']}\n")
        return "\n".join(lines)

    @classmethod
    def reset(cls):
        """重置报告累积器（新任务开始时调用）。"""
        cls._reports = []


# ══════════════════════════════════════════════════════════════════════════════
#  Alert — 异常上报
# ══════════════════════════════════════════════════════════════════════════════

class Alert(Skill):
    """发现异常情况时，立刻通知操作员。"""

    name = "alert"
    description = "发现异常情况时紧急通知操作员。会以醒目方式推送警报，操作员可以决定是否中止任务。"
    skill_type = "cognitive"
    robot_type = []

    input_schema = {
        "message": {"type": "str", "description": "警报内容，描述发现的异常"},
        "level": {"type": "str", "description": "警报等级: warning/danger/critical，默认 warning"},
    }
    output_schema = {
        "alert_id": {"type": "int", "description": "警报编号"},
        "acknowledged": {"type": "bool", "description": "是否已送达"},
    }
    preconditions = []

    _alert_count = 0

    def execute(self, robot_state: dict, **params) -> SkillResult:
        start = time.time()
        message = params.get("message", "")
        level = params.get("level", "warning")

        if not message:
            return SkillResult(success=False, error_msg="警报内容不能为空", cost_time=0)

        Alert._alert_count += 1
        alert_id = Alert._alert_count

        _n, _e, _d = _parse_pos(robot_state)
        pos_str = f"({_n:.0f}, {_e:.0f}, h={abs(_d):.0f}m)"

        icon = {"warning": "⚠️", "danger": "🚨", "critical": "🆘"}.get(level, "⚠️")
        msg = f"{icon} **警报 #{alert_id}** [{level.upper()}]\n📍 位置: {pos_str}\n{message}"

        try:
            from server import socketio
            socketio.emit("ai_chat_reply", {
                "ok": True,
                "reply": msg,
                "intent": "alert",
                "level": level,
            })
            socketio.emit("alert", {"id": alert_id, "level": level, "message": message, "position": pos_str})
        except Exception as e:
            logger.warning(f"推送警报失败: {e}")

        elapsed = time.time() - start
        return SkillResult(
            success=True,
            output={"alert_id": alert_id, "acknowledged": True},
            cost_time=elapsed,
            logs=[f"alert #{alert_id}: {level} - {message[:50]}"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  AskUser — 主动提问
# ══════════════════════════════════════════════════════════════════════════════

class AskUser(Skill):
    """遇到不确定的情况时，主动向操作员提问并等待回答。"""

    name = "ask_user"
    description = "向操作员提问并等待回答。用于遇到不确定情况需要人类判断时。操作员有60秒回答时间。"
    skill_type = "cognitive"
    robot_type = []

    input_schema = {
        "question": {"type": "str", "description": "要问操作员的问题"},
    }
    output_schema = {
        "answer": {"type": "str", "description": "操作员的回答，超时则为'(操作员未回答)'"},
    }
    preconditions = []

    # 用于接收用户回答的队列
    _pending_answer = None
    _answer_event = None

    def execute(self, robot_state: dict, **params) -> SkillResult:
        import threading
        start = time.time()
        question = params.get("question", "")

        if not question:
            return SkillResult(success=False, error_msg="问题不能为空", cost_time=0)

        _n, _e, _d = _parse_pos(robot_state)
        pos_str = f"({_n:.0f}, {_e:.0f})"

        # 设置等待事件
        AskUser._pending_answer = None
        AskUser._answer_event = threading.Event()

        msg = f"🙋 **无人机提问** 📍{pos_str}\n{question}\n\n💬 请在聊天框回复，60秒内有效"

        try:
            from server import socketio
            socketio.emit("ai_chat_reply", {
                "ok": True,
                "reply": msg,
                "intent": "ask_user",
                "awaiting_answer": True,
            })
        except Exception as e:
            logger.warning(f"推送提问失败: {e}")

        # 等待回答（最多60秒）
        answered = AskUser._answer_event.wait(timeout=60)

        if answered and AskUser._pending_answer:
            answer = AskUser._pending_answer
        else:
            answer = "(操作员未回答，自行判断)"

        AskUser._pending_answer = None
        AskUser._answer_event = None

        elapsed = time.time() - start
        return SkillResult(
            success=True,
            output={"answer": answer},
            cost_time=elapsed,
            logs=[f"ask_user: Q='{question[:40]}' A='{answer[:40]}'"],
        )

    @classmethod
    def receive_answer(cls, answer: str):
        """接收操作员的回答（由 server 调用）。"""
        cls._pending_answer = answer
        if cls._answer_event:
            cls._answer_event.set()


# ══════════════════════════════════════════════════════════════════════════════
#  UpdateMap — 自动更新地图
# ══════════════════════════════════════════════════════════════════════════════

class UpdateMap(Skill):
    """将新发现的地标/建筑信息追加到 WORLD_MAP.md，持续积累场景知识。"""

    name = "update_map"
    description = "将新发现的地标或建筑信息追加到场景地图(WORLD_MAP.md)。用于探索新区域后记录发现。"
    skill_type = "cognitive"
    robot_type = []

    input_schema = {
        "landmark_name": {"type": "str", "description": "地标名称 (如 '高层办公楼群')"},
        "description": {"type": "str", "description": "外观描述"},
    }
    output_schema = {
        "updated": {"type": "bool", "description": "是否更新成功"},
        "total_landmarks": {"type": "int", "description": "地图中总地标数"},
    }
    preconditions = []

    def execute(self, robot_state: dict, **params) -> SkillResult:
        start = time.time()
        name = params.get("landmark_name", "")
        desc = params.get("description", "")

        if not name:
            return SkillResult(success=False, error_msg="地标名称不能为空", cost_time=0)

        n, e, _d = _parse_pos(robot_state)

        map_path = Path(__file__).parent.parent / "robot_profile" / "WORLD_MAP.md"

        try:
            content = map_path.read_text(encoding="utf-8") if map_path.exists() else "# WORLD_MAP.md\n"

            # 追加到 "## 探索发现" 段落
            marker = "## 探索发现"
            entry = f"| {name} | ({n:.0f}, {e:.0f}) | {desc} |"

            if marker not in content:
                content += f"\n\n{marker}\n\n| 地标 | NED坐标 | 描述 |\n|------|---------|------|\n{entry}\n"
            else:
                content = content.rstrip() + f"\n{entry}\n"

            map_path.write_text(content, encoding="utf-8")

            # 数地标数
            total = content.count("| (")

            # 实时推送新地标到前端
            try:
                from server import socketio
                socketio.emit("map_landmark", {
                    "name": name,
                    "n": round(n, 1),
                    "e": round(e, 1),
                    "desc": desc,
                })
            except Exception as _e:
                logger.warning(f"推送地标失败: {_e}")

            elapsed = time.time() - start
            return SkillResult(
                success=True,
                output={"updated": True, "total_landmarks": total},
                cost_time=elapsed,
                logs=[f"update_map: added '{name}' at ({n:.0f},{e:.0f})"],
            )
        except Exception as e:
            return SkillResult(success=False, error_msg=f"更新地图失败: {e}", cost_time=time.time()-start)
