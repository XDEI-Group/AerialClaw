"""
core/doctor_checks/adapter.py — Adapter 合规检查

自动检测 adapter 接口实现是否符合 SimAdapter 契约。
发现问题后生成 fix_hint 和 fixable 标记，供 AdapterHealer 自动修复。
"""

from __future__ import annotations

import inspect
import logging
from typing import Optional

from core.doctor import HealthCheck, CheckResult

logger = logging.getLogger(__name__)


def _get_adapter():
    """安全获取当前 adapter，失败返回 None。"""
    try:
        from adapters.adapter_manager import get_adapter
        return get_adapter()
    except Exception:
        return None


def _get_adapter_source_file() -> Optional[str]:
    """获取当前 adapter 的源文件路径。"""
    adapter = _get_adapter()
    if adapter is None:
        return None
    try:
        return inspect.getfile(type(adapter))
    except (TypeError, OSError):
        return None


# ══════════════════════════════════════════════════════════════
#  检查项 1: 连接状态 + is_connected 类型安全
# ══════════════════════════════════════════════════════════════

class AdapterConnectionCheck(HealthCheck):
    """检查 adapter 连接状态和 is_connected 接口类型。"""
    name = "Adapter 连接"
    category = "adapter"

    def check(self) -> CheckResult:
        adapter = _get_adapter()
        if adapter is None:
            return self._warn("无活跃 adapter", "启动仿真环境后重试")

        # 检查 is_connected 是 property 还是 attribute/method
        cls = type(adapter)
        is_prop = isinstance(getattr(cls, 'is_connected', None), property)
        
        # 尝试获取 is_connected 值
        try:
            val = adapter.is_connected
        except Exception as e:
            return self._fail(
                f"is_connected 访问异常: {e}",
                fix="检查 adapter 的 is_connected 实现"
            )

        if not isinstance(val, bool):
            return self._fail(
                f"is_connected 返回 {type(val).__name__}，应为 bool",
                fix="将 is_connected 改为返回 bool 的 @property"
            )

        if not val:
            return self._warn(
                f"adapter {adapter.name} 未连接",
                "检查仿真环境是否在运行"
            )

        return self._ok(f"{adapter.name} 已连接 (is_connected=property: {is_prop})")


# ══════════════════════════════════════════════════════════════
#  检查项 2: VehicleState 完整性
# ══════════════════════════════════════════════════════════════

class AdapterStateCheck(HealthCheck):
    """检查 get_state() 返回值的完整性。"""
    name = "Adapter 状态"
    category = "adapter"

    def check(self) -> CheckResult:
        adapter = _get_adapter()
        if adapter is None:
            return self._warn("无活跃 adapter")

        try:
            state = adapter.get_state()
        except Exception as e:
            return self._fail(
                f"get_state() 异常: {e}",
                fix="检查 adapter.get_state() 实现"
            )

        if state is None:
            return self._fail(
                "get_state() 返回 None",
                fix="确保 adapter 连接成功后 get_state() 返回有效 VehicleState"
            )

        issues = []

        # 检查 position_ned
        if state.position_ned is None:
            issues.append("position_ned=None")

        # 检查 battery
        if state.battery_percent <= 0:
            issues.append(f"battery_percent={state.battery_percent}（应 > 0，未模拟电量时默认 100）")

        # 检查 velocity
        if state.velocity is None:
            issues.append("velocity=None")

        if issues:
            return self._warn(
                f"VehicleState 字段不完整: {'; '.join(issues)}",
                fix="在 adapter.get_state() 中为缺失字段设置合理默认值"
            )

        return self._ok(
            f"VehicleState OK: pos={state.position_ned}, "
            f"bat={state.battery_percent}%, armed={state.armed}, in_air={state.in_air}"
        )


# ══════════════════════════════════════════════════════════════
#  检查项 3: 飞行状态逻辑
# ══════════════════════════════════════════════════════════════

class AdapterFlightStateCheck(HealthCheck):
    """检查 is_in_air / is_armed 的返回值逻辑。"""
    name = "Adapter 飞行状态"
    category = "adapter"

    def check(self) -> CheckResult:
        adapter = _get_adapter()
        if adapter is None:
            return self._warn("无活跃 adapter")

        issues = []

        # 检查 is_in_air 返回类型
        try:
            in_air = adapter.is_in_air()
            if not isinstance(in_air, bool):
                issues.append(f"is_in_air() 返回 {type(in_air).__name__}，应为 bool")
        except Exception as e:
            issues.append(f"is_in_air() 异常: {e}")
            in_air = None

        # 检查 is_armed 返回类型
        try:
            armed = adapter.is_armed()
            if not isinstance(armed, bool):
                issues.append(f"is_armed() 返回 {type(armed).__name__}，应为 bool")
        except Exception as e:
            issues.append(f"is_armed() 异常: {e}")
            armed = None

        # 交叉验证: get_state() 和 is_in_air() 一致性
        try:
            state = adapter.get_state()
            if state and in_air is not None:
                if state.in_air != in_air:
                    issues.append(
                        f"get_state().in_air={state.in_air} 与 is_in_air()={in_air} 不一致，"
                        "可能 landed_state 映射有误"
                    )
        except Exception:
            pass

        # 启动时如果报告在空中，大概率是 landed_state 映射反了
        if in_air is True:
            try:
                state = adapter.get_state()
                if state and state.position_ned:
                    alt = -state.position_ned.down  # altitude
                    if alt < 0.5:
                        issues.append(
                            f"is_in_air()=True 但高度仅 {alt:.2f}m，"
                            "疑似 landed_state 映射反了 (0=Landed, 1=Flying)"
                        )
            except Exception:
                pass

        if issues:
            return self._fail(
                f"飞行状态异常: {'; '.join(issues)}",
                fix="检查 adapter 的 landed_state/is_in_air 映射逻辑"
            )

        return self._ok(f"in_air={in_air}, armed={armed}")


# ══════════════════════════════════════════════════════════════
#  检查项 4: 指令接口类型
# ══════════════════════════════════════════════════════════════

class AdapterCommandCheck(HealthCheck):
    """检查 takeoff/land/hover 等指令接口的签名和返回类型。"""
    name = "Adapter 指令接口"
    category = "adapter"

    def check(self) -> CheckResult:
        adapter = _get_adapter()
        if adapter is None:
            return self._warn("无活跃 adapter")

        missing = []
        type_issues = []

        for method_name in ["takeoff", "land", "hover", "fly_to_ned", "return_to_launch"]:
            method = getattr(adapter, method_name, None)
            if method is None:
                missing.append(method_name)
                continue
            if not callable(method):
                type_issues.append(f"{method_name} 不可调用")

        if missing:
            return self._fail(
                f"缺少指令方法: {', '.join(missing)}",
                fix="在 adapter 中实现缺失的 SimAdapter 抽象方法"
            )

        if type_issues:
            return self._warn(
                f"指令接口问题: {'; '.join(type_issues)}",
                fix="确保所有指令方法是可调用的函数"
            )

        return self._ok(f"5 个指令接口就绪: takeoff/land/hover/fly_to_ned/return_to_launch")
