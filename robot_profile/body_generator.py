"""
body_generator.py
启动时自动扫描 adapter 能力 + 传感器列表，生成 BODY.md。

BODY.md 是机器人对自己"身体"的认知文档，LLM 读了就知道：
  - 我有什么传感器
  - 我能做什么动作
  - 我的运动能力边界
  - 我的硬件限制
"""

import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROFILE_DIR = Path(__file__).parent
BODY_MD_PATH = PROFILE_DIR / "BODY.md"


def generate_body_md(adapter=None, sensor_bridge=None, skill_registry=None):
    """
    扫描当前系统能力，生成 BODY.md。

    Args:
        adapter: SimAdapter 实例 (px4_adapter 等)
        sensor_bridge: GzSensorBridge 实例
        skill_registry: SkillRegistry 实例
    """
    sections = []
    sections.append("# BODY.md -- 身体认知文档")
    sections.append(f"# 自动生成于 {time.strftime('%Y-%m-%d %H:%M:%S')}")
    sections.append("# 本文件由系统启动时自动生成，请勿手动编辑。\n")

    # -- 基本信息 --
    sections.append("## 基本信息\n")
    if adapter:
        sections.append(f"- 适配器: {adapter.name}")
        sections.append(f"- 描述: {adapter.description}")
        vehicles = getattr(adapter, "supported_vehicles", [])
        if vehicles:
            sections.append(f"- 支持载具类型: {', '.join(vehicles)}")
        connected = adapter.is_connected() if hasattr(adapter, "is_connected") else False
        sections.append(f"- 连接状态: {'已连接' if connected else '未连接'}")
    else:
        sections.append("- 适配器: 未初始化")

    # -- 运动能力 --
    sections.append("\n## 运动能力\n")
    sections.append("- 类型: 多旋翼无人机 (Multirotor)")
    sections.append("- 坐标系: NED 本地坐标 (North-East-Down, 相对起飞点)")
    sections.append("- 飞行速度: 建议 2-3 m/s, 最大约 5 m/s")
    sections.append("- 旋转速度: 最大约 45 deg/s")
    sections.append("- 高度范围: 0-120m (受限于仿真环境)")
    sections.append("- 定位方式: IMU + 气压计惯性导航 (GPS 信号可能不可用)")
    sections.append("- 注意: 长距离飞行可能有位置漂移, 建议用视觉地标校正")

    # -- 传感器 --
    sections.append("\n## 传感器\n")
    if sensor_bridge and sensor_bridge.is_running:
        # 摄像头
        cam_dirs = getattr(sensor_bridge, "_camera_dirs", None)
        if cam_dirs:
            sections.append(f"### 摄像头 (x{len(cam_dirs)})")
            for d in cam_dirs:
                info = sensor_bridge.get_camera_info(d) if hasattr(sensor_bridge, "get_camera_info") else {}
                w = info.get("width", "?")
                h = info.get("height", "?")
                fps = info.get("fps", 0)
                sections.append(f"- {d}: {w}x{h} @ {round(fps, 1)} fps, FOV 80 度")
            sections.append("- 安装方位: 前(0度)/后(180度)/左(270度)/右(90度), 均向下倾斜约15度")
            sections.append("- 用途: 场景识别、目标检测、视觉导航")
        else:
            # 单摄像头兼容
            cam_info = sensor_bridge.get_camera_info() if hasattr(sensor_bridge, "get_camera_info") else {}
            if cam_info.get("has_data"):
                sections.append("### 摄像头 (x1)")
                sections.append(f"- 分辨率: {cam_info.get('width', '?')}x{cam_info.get('height', '?')}")
                sections.append(f"- 帧率: {round(cam_info.get('fps', 0), 1)} fps")

        # 激光雷达
        scan = sensor_bridge.get_lidar_scan() if hasattr(sensor_bridge, "get_lidar_scan") else None
        if scan:
            sections.append("\n### 2D 激光雷达 (x1)")
            sections.append(f"- 扫描点数: {scan.get('count', '?')}")
            sections.append(f"- 角度范围: {round(scan.get('angle_min', 0), 2)} ~ {round(scan.get('angle_max', 0), 2)} rad")
            sections.append(f"- 测距范围: {scan.get('range_min', '?')} ~ {scan.get('range_max', '?')} m")
            sections.append("- 安装位置: 机体顶部")
            sections.append("- 用途: 障碍物检测、环境建图、避障")
    else:
        sections.append("- 传感器桥接未启动, 传感器信息不可用")

    # -- 可用技能 --
    sections.append("\n## 可用硬技能\n")
    if skill_registry:
        catalog = skill_registry.get_skill_catalog()
        hard_skills = [s for s in catalog if s.get("skill_type") == "hard"]
        for s in hard_skills:
            inputs = ", ".join(s.get("input_schema", {}).keys()) or "无"
            sections.append(f"- {s['name']}: {s['description']} [参数: {inputs}]")
        if not hard_skills:
            sections.append("- 暂无已注册硬技能")
    else:
        sections.append("- 技能注册表未初始化")

    # -- 硬件限制 --
    sections.append("\n## 硬件限制\n")
    sections.append("- 电池: 有限续航, 低于 20% 应返航")
    sections.append("- 通信: MAVLink UDP, 可能受距离影响")
    sections.append("- 载荷: 无额外载荷能力 (仅传感器)")
    sections.append("- 天气: 仿真环境无风雨影响, 真实环境需考虑")

    # -- 写入文件 --
    content = "\n".join(sections) + "\n"
    BODY_MD_PATH.write_text(content, encoding="utf-8")
    logger.info("BODY.md 已生成: %s", BODY_MD_PATH)
    return content
