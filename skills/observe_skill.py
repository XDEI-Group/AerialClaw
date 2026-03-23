"""
observe_skill.py — 相机观察技能（修复版）

问题根因：
    motor_skills.py 中的 Observe 类尝试 `import gz`（Gazebo Python 绑定），
    在 AirSim 环境下导致 ModuleNotFoundError: No module named 'gz'

修复方案：
    1. 本文件提供正确的 Observe 实现，通过 adapter.get_image_base64() 获取图像
    2. 导入时自动替换 motor_skills.Observe，确保 Brain 层调用时走正确路径
    3. 不依赖任何仿真器特定模块（不 import gz / airsim）

Author: AerialClaw Doctor Agent
"""

import time
import logging

from skills.base_skill import Skill, SkillResult

logger = logging.getLogger(__name__)


def _get_adapter():
    """获取当前活跃的仿真适配器。"""
    from adapters.adapter_manager import get_adapter
    return get_adapter()


class Observe(Skill):
    """
    观察技能：通过当前 adapter 的相机接口抓取图像，返回 base64 编码的 JPEG。

    修复说明：
        原实现依赖 `gz`（Gazebo Python 模块），在 AirSim 环境下不可用。
        本实现通过 adapter.get_image_base64() 获取图像，与仿真器解耦。
    """

    name = "observe"
    description = "抓取无人机前向相机图像，返回 base64 JPEG 字符串，供视觉感知使用。"
    skill_type = "hard"
    robot_type = ["UAV"]
    preconditions = ["battery > 10%", "camera_sensor == operational"]
    cost = 0.5
    input_schema = {
        "camera": "str，摄像头名称（可选，默认由 adapter 决定，当前为 front_custom）",
    }
    output_schema = {
        "image_base64": "str，base64 编码的 JPEG 图像",
        "width": "int，图像宽度（像素），未知时为 0",
        "height": "int，图像高度（像素），未知时为 0",
        "source": "str，图像来源标识（如 airsim_openfly）",
    }

    def check_precondition(self, robot_state: dict) -> bool:
        return robot_state.get("battery", 100) > 10

    def execute(self, input_data: dict) -> SkillResult:
        start = time.time()

        # 获取 adapter（不依赖 gz / airsim 等仿真器特定模块）
        adapter = _get_adapter()
        if adapter is None:
            return SkillResult(
                success=False,
                error_msg="无仿真适配器，无法抓图",
                logs=["❌ observe: 无 adapter 连接"],
            )

        # 调用 adapter.get_image_base64()
        get_img = getattr(adapter, "get_image_base64", None)
        if get_img is None:
            return SkillResult(
                success=False,
                error_msg=(
                    f"adapter ({adapter.name}) 不支持 get_image_base64，"
                    "请在 adapter 中实现该方法"
                ),
                logs=[f"❌ observe: adapter={adapter.name} 缺少 get_image_base64 方法"],
            )

        try:
            b64 = get_img()
        except Exception as e:
            logger.warning(f"observe: get_image_base64 异常: {e}")
            return SkillResult(
                success=False,
                error_msg=f"相机抓图失败: {e}",
                logs=[f"❌ observe: get_image_base64 异常: {e}"],
            )

        if not b64:
            return SkillResult(
                success=False,
                error_msg=(
                    "相机返回空图像，请检查 AirSim settings.json 中 "
                    "front_custom 摄像头配置（Width/Height 不能为 0）"
                ),
                logs=["❌ observe: get_image_base64 返回空，检查摄像头配置"],
            )

        elapsed = round(time.time() - start, 3)
        logger.info(f"observe: 抓图成功 {len(b64)} bytes [{adapter.name}]")
        return SkillResult(
            success=True,
            output={
                "image_base64": b64,
                "width": 0,   # 可从 adapter 扩展获取精确尺寸
                "height": 0,
                "source": adapter.name,
            },
            cost_time=elapsed,
            logs=[f"✅ observe: 抓图成功 ({len(b64)} bytes b64) [{adapter.name}] {elapsed}s"],
        )


# ── 自动修补 motor_skills.Observe ────────────────────────────────────────────
# 当本文件被导入时，替换 motor_skills 模块中的 Observe 类，
# 确保 Brain 层通过 motor_skills.Observe 调用时走正确路径（不依赖 gz）。

def _patch_motor_skills():
    """将修复版 Observe 注入 motor_skills 模块。"""
    try:
        import skills.motor_skills as _ms
        _ms.Observe = Observe
        logger.info("observe_skill: 已修补 motor_skills.Observe（去除 gz 依赖）")
    except Exception as e:
        logger.warning(f"observe_skill: 修补 motor_skills.Observe 失败: {e}")


_patch_motor_skills()
