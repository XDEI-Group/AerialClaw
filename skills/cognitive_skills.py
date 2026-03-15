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
