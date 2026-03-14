"""
tools/builtin/system_tools.py  —— 系统命令工具

提供在宿主机上执行 shell 命令的能力。

工具列表：
    ExecCommandTool  : 执行任意 shell 命令，返回 stdout/stderr/returncode

安全说明：
    - ExecCommandTool 默认允许执行任意命令，存在安全风险
    - 生产环境应设置 allowed_commands 白名单或在沙箱中运行
    - 默认超时 30 秒，防止阻塞规划流程
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.base_tool import BaseTool


class ExecCommandTool(BaseTool):
    """
    在宿主机上执行 shell 命令。

    LLM 调用时机：需要获取系统信息（如磁盘空间、进程状态），或触发外部脚本时。

    Args:
        allowed_commands : 白名单列表，None 表示不限制（谨慎使用）
        timeout          : 命令超时秒数，默认 30s
        working_dir      : 命令执行目录，None 表示当前工作目录
    """

    def __init__(
        self,
        allowed_commands: list[str] | None = None,
        timeout: int = 30,
        working_dir: str | None = None,
    ):
        self._allowed = allowed_commands
        self._timeout = timeout
        self._working_dir = working_dir

    @property
    def name(self) -> str:
        return "exec_command"

    @property
    def description(self) -> str:
        allowed_hint = (
            f"允许的命令前缀：{self._allowed}" if self._allowed
            else "无限制（生产环境请配置白名单）"
        )
        return (
            f"在宿主机上执行 shell 命令，返回标准输出、标准错误和返回码。"
            f"用于获取系统实时信息或触发外部脚本。"
            f"超时时间：{self._timeout}s。{allowed_hint}"
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令，例如 'ls -la /tmp' 或 'python check_sensor.py'",
                },
                "working_dir": {
                    "type": "string",
                    "description": "可选：命令执行目录，不填则使用默认工作目录",
                },
            },
            "required": ["command"],
        }

    def _run(
        self,
        command: str,
        working_dir: str | None = None,
        **kwargs: Any,
    ) -> dict:
        # 白名单检查
        if self._allowed is not None:
            allowed = any(command.strip().startswith(prefix) for prefix in self._allowed)
            if not allowed:
                raise PermissionError(
                    f"命令 '{command}' 不在白名单中。"
                    f"允许的命令前缀：{self._allowed}"
                )

        cwd = working_dir or self._working_dir

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=cwd,
            )
            return {
                "command":     command,
                "returncode":  proc.returncode,
                "stdout":      proc.stdout[:4096],   # 限制输出大小
                "stderr":      proc.stderr[:1024],
                "success":     proc.returncode == 0,
                "working_dir": cwd,
            }
        except subprocess.TimeoutExpired:
            raise TimeoutError(
                f"命令 '{command}' 超时（{self._timeout}s）"
            )
