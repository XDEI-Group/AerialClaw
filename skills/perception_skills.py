"""
perception_skills.py
感知技能（Perception Skills）：传感器原始数据 → 语义信息的转换层。

设计原则：
    不直接将原始传感器数据喂给 LLM，先提取语义信息再传给 Brain。
    skill_type = "perception"

包含：DetectObject / RecognizeSpeech / FusePerception / ScanArea / GetSensorData

AirSim 集成：
    - ScanArea: 通过 AirSim 获取相机图像进行区域扫描
    - GetSensorData: 从 AirSim 获取真实传感器数据

Author: AerialClaw Team
"""

import time
import math
import logging
from typing import Optional

import numpy as np

from skills.base_skill import Skill, SkillResult

logger = logging.getLogger(__name__)


_global_sim_manager = None
_global_sensor_bridge = None


def set_sim_manager(sim_manager) -> None:
    """
    设置全局仿真管理器实例
    
    Args:
        sim_manager: SimManager 实例
    """
    global _global_sim_manager
    _global_sim_manager = sim_manager
    logger.info("PerceptionSkills 已设置仿真管理器")


def get_sim_manager() -> Optional[object]:
    """获取全局仿真管理器实例"""
    return _global_sim_manager


def set_sensor_bridge(bridge) -> None:
    """设置 Gazebo 传感器桥接实例"""
    global _global_sensor_bridge
    _global_sensor_bridge = bridge
    logger.info("PerceptionSkills 已设置 GzSensorBridge")


def get_sensor_bridge():
    """获取 Gazebo 传感器桥接实例"""
    return _global_sensor_bridge


class DetectObject(Skill):
    """目标检测：将图像处理为语义对象列表。"""

    name = "detect_object"
    description = "对采集的图像运行目标检测，将像素级图像转换为语义对象列表（类别/置信度/位置）。"
    skill_type = "perception"
    robot_type = ["UAV", "UGV"]
    preconditions = []
    cost = 1.0
    input_schema = {
        "image_id": "str，待检测图像 ID（来自 capture_image 输出）",
        "confidence_threshold": "float，置信度过滤阈值，默认 0.5",
    }
    output_schema = {
        "detected_objects": "list，检测结果列表，每项含 label/confidence/bbox",
        "object_count": "int，过滤后的目标数量",
    }

    def check_precondition(self, robot_state: dict) -> bool:
        return (
            robot_state.get("battery", 100) > 10
            and robot_state.get("sensor_status", {}).get("camera", True)
        )

    def execute(self, input_data: dict) -> SkillResult:
        image_id = input_data.get("image_id", "unknown")
        threshold = input_data.get("confidence_threshold", 0.5)
        start = time.time()
        time.sleep(0.03)
        elapsed = round(time.time() - start, 4)

        # 检查是否有真实图像（暂未接入 YOLO，使用 mock 结果，但标注数据来源）
        bridge = get_sensor_bridge()
        source = "mock"
        if bridge is not None and bridge.is_running:
            cam_info = bridge.get_camera_info()
            if cam_info.get("has_data"):
                source = "gazebo"  # 有真实图像，后续可接入 YOLO

        raw_objects = [
            {"label": "person", "confidence": 0.92, "bbox": [120, 80, 60, 120]},
            {"label": "vehicle", "confidence": 0.78, "bbox": [300, 150, 100, 60]},
        ]
        filtered = [o for o in raw_objects if o["confidence"] >= threshold]

        return SkillResult(
            success=True,
            output={"detected_objects": filtered, "object_count": len(filtered), "source": source},
            cost_time=elapsed,
            logs=[f"DetectObject: image={image_id}, found {len(filtered)} objects (threshold={threshold}, source={source})"],
        )


class RecognizeSpeech(Skill):
    """语音识别：将音频输入转换为文本指令。"""

    name = "recognize_speech"
    description = "将机器人麦克风采集的音频转换为文本指令，供 Brain 模块解析执行。"
    skill_type = "perception"
    robot_type = ["UAV", "UGV"]
    preconditions = []
    cost = 0.8
    input_schema = {
        "audio_id": "str，音频数据 ID",
        "language": "str，语言代码，默认 'zh-CN'",
    }
    output_schema = {
        "text": "str，识别出的文本指令",
        "confidence": "float，识别置信度",
        "language": "str，实际识别语言",
    }

    def check_precondition(self, robot_state: dict) -> bool:
        return (
            robot_state.get("battery", 100) > 10
            and robot_state.get("sensor_status", {}).get("microphone", True)
        )

    def execute(self, input_data: dict) -> SkillResult:
        audio_id = input_data.get("audio_id", "unknown")
        language = input_data.get("language", "zh-CN")
        start = time.time()
        time.sleep(0.02)
        elapsed = round(time.time() - start, 4)
        text = "搜索 A 区域并报告目标情况"
        confidence = 0.95
        return SkillResult(
            success=True,
            output={"text": text, "confidence": confidence, "language": language},
            cost_time=elapsed,
            logs=[f"RecognizeSpeech: audio={audio_id} -> \"{text}\" (conf={confidence})"],
        )


class FusePerception(Skill):
    """多模态感知融合：图像检测 + 激光雷达 → 语义世界状态。"""

    name = "fuse_perception"
    description = "融合图像目标检测结果与激光雷达扫描数据，生成带三维坐标的语义世界状态片段。"
    skill_type = "perception"
    robot_type = ["UAV", "UGV"]
    preconditions = []
    cost = 1.2
    input_schema = {
        "detected_objects": "list，来自 detect_object 的检测结果",
        "lidar_scan": "dict，来自 scan_lidar 的扫描结果",
        "robot_pose": "[x, y, z, yaw]，机器人当前位姿",
    }
    output_schema = {
        "semantic_world_state": "dict，语义世界状态，含 objects（带三维坐标）/free_space_radius/robot_pose",
    }

    def check_precondition(self, robot_state: dict) -> bool:
        return robot_state.get("battery", 100) > 15

    def execute(self, input_data: dict) -> SkillResult:
        detected_objects = input_data.get("detected_objects", [])
        lidar_scan = input_data.get("lidar_scan", {})
        robot_pose = input_data.get("robot_pose", [0, 0, 0, 0])
        start = time.time()
        time.sleep(0.03)
        elapsed = round(time.time() - start, 4)

        source = "mock"

        # 优先使用 GzSensorBridge 获取真实激光雷达数据
        bridge = get_sensor_bridge()
        if bridge is not None and bridge.is_running:
            real_scan = bridge.get_lidar_scan()
            if real_scan is not None:
                lidar_scan = real_scan
                source = "gazebo"

        # 将激光雷达 ranges 转换为障碍物列表（极坐标）
        obstacles = lidar_scan.get("detected_obstacles", [])
        if not obstacles and "ranges" in lidar_scan:
            angle_min = lidar_scan.get("angle_min", 0.0)
            angle_inc = lidar_scan.get("angle_increment", 0.0)
            range_min = lidar_scan.get("range_min", 0.1)
            range_max = lidar_scan.get("range_max", 30.0)
            for i, r in enumerate(lidar_scan["ranges"]):
                if range_min < r < range_max:
                    angle_deg = math.degrees(angle_min + i * angle_inc)
                    obstacles.append({"distance": r, "angle": angle_deg})

        scan_range = lidar_scan.get("range_max", 20.0)
        semantic_objects = []
        for i, obj in enumerate(detected_objects):
            distance = obstacles[i]["distance"] if i < len(obstacles) else 5.0
            angle = obstacles[i]["angle"] if i < len(obstacles) else 0.0
            wx = robot_pose[0] + distance * math.cos(math.radians(angle))
            wy = robot_pose[1] + distance * math.sin(math.radians(angle))
            wz = robot_pose[2]
            semantic_objects.append({
                "label": obj.get("label", "unknown"),
                "world_position": [round(wx, 2), round(wy, 2), round(wz, 2)],
                "confidence": obj.get("confidence", 0.0),
            })

        return SkillResult(
            success=True,
            output={
                "semantic_world_state": {
                    "objects": semantic_objects,
                    "free_space_radius": scan_range,
                    "robot_pose": robot_pose,
                    "source": source,
                }
            },
            cost_time=elapsed,
            logs=[f"FusePerception: {len(detected_objects)} visual + {len(obstacles)} lidar -> {len(semantic_objects)} semantic objects (source={source})"],
        )


class ScanArea(Skill):
    """
    区域扫描：通过 AirSim 获取相机图像进行区域扫描
    
    该技能调用 AirSim 获取指定区域的图像数据，可用于目标搜索、环境探测等任务。
    """

    name = "scan_area"
    description = "通过 AirSim 获取相机图像进行区域扫描，返回图像数据用于目标检测。"
    skill_type = "perception"
    robot_type = ["UAV"]
    preconditions = []
    cost = 1.5
    input_schema = {
        "area_center": "[x, y, z]，扫描区域中心坐标",
        "scan_radius": "float，扫描半径（米），默认 20.0",
        "camera_id": "str，摄像头 ID，默认 '0'",
        "vehicle_id": "str，无人机 ID，默认 'UAV_1'",
    }
    output_schema = {
        "image_shape": "tuple，图像尺寸 (height, width, channels)",
        "image_id": "str，图像唯一 ID",
        "timestamp": "float，采集时间戳",
        "area_info": "dict，区域信息",
    }

    def check_precondition(self, robot_state: dict) -> bool:
        return (
            robot_state.get("battery", 100) > 15
            and robot_state.get("sensor_status", {}).get("camera", True)
        )

    def execute(self, input_data: dict) -> SkillResult:
        area_center = input_data.get("area_center", [0, 0, 10])
        scan_radius = input_data.get("scan_radius", 20.0)
        camera_id = input_data.get("camera_id", "0")
        vehicle_id = input_data.get("vehicle_id", "UAV_1")
        
        # 优先使用 GzSensorBridge（Gazebo 真实传感器）
        bridge = get_sensor_bridge()
        if bridge is not None and bridge.is_running:
            try:
                image = bridge.get_camera_image()
                if image is not None:
                    ts = time.time()
                    image_id = f"scan_{int(ts * 1000)}"
                    cam_info = bridge.get_camera_info()
                    
                    return SkillResult(
                        success=True,
                        output={
                            "image_shape": list(image.shape),
                            "image_id": image_id,
                            "timestamp": ts,
                            "source": "gazebo",
                            "camera_fps": round(cam_info["fps"], 1),
                            "area_info": {
                                "center": area_center,
                                "radius": scan_radius,
                            },
                        },
                        cost_time=0.0,
                        logs=[f"ScanArea: 从 Gazebo 获取真实图像 {image.shape} at {area_center}"],
                    )
            except Exception as e:
                logger.warning(f"ScanArea GzSensorBridge 失败: {e}")

        # 回退到 AirSim SimManager
        sim_mgr = get_sim_manager()
        if sim_mgr is not None:
            try:
                image = sim_mgr.get_camera_image(vehicle_id, camera_id)
                if image is not None:
                    ts = time.time()
                    image_id = f"scan_{int(ts * 1000)}"
                    
                    return SkillResult(
                        success=True,
                        output={
                            "image_shape": image.shape,
                            "image_id": image_id,
                            "timestamp": ts,
                            "area_info": {
                                "center": area_center,
                                "radius": scan_radius,
                            },
                        },
                        cost_time=0.0,
                        logs=[f"ScanArea: scanned area at {area_center}, radius={scan_radius}m via AirSim"],
                    )
                else:
                    return SkillResult(
                        success=False,
                        output={},
                        error_msg="Failed to get image from AirSim",
                        logs=[f"ScanArea: AirSim image capture failed"],
                    )
            except Exception as e:
                logger.error(f"ScanArea 执行失败: {e}")
        
        start = time.time()
        time.sleep(0.03)
        elapsed = round(time.time() - start, 4)
        ts = time.time()
        image_id = f"scan_{int(ts * 1000)}"
        
        return SkillResult(
            success=True,
            output={
                "image_shape": (720, 1280, 3),
                "image_id": image_id,
                "timestamp": ts,
                "area_info": {
                    "center": area_center,
                    "radius": scan_radius,
                },
            },
            cost_time=elapsed,
            logs=[f"ScanArea: scanned area at {area_center} (mock mode)"],
        )


class GetSensorData(Skill):
    """
    获取传感器数据：从 AirSim 获取真实传感器数据
    
    该技能从 AirSim 获取 IMU、GPS、气压计等传感器数据，用于状态估计和定位。
    """

    name = "get_sensor_data"
    description = "从 AirSim 获取真实传感器数据，包括 IMU、GPS、气压计等。"
    skill_type = "perception"
    robot_type = ["UAV", "UGV"]
    preconditions = []
    cost = 1.0
    input_schema = {
        "sensor_types": "list，要获取的传感器类型列表，默认 ['imu', 'gps', 'barometer']",
        "vehicle_id": "str，无人机 ID，默认 'UAV_1'",
    }
    output_schema = {
        "imu_data": "dict，IMU 数据（orientation/angular_velocity/linear_acceleration）",
        "gps_data": "dict，GPS 数据（latitude/longitude/altitude/speed/heading）",
        "barometer_data": "dict，气压计数据（altitude/pressure/qnh）",
        "timestamp": "float，数据时间戳",
    }

    def check_precondition(self, robot_state: dict) -> bool:
        return robot_state.get("battery", 100) > 10

    def execute(self, input_data: dict) -> SkillResult:
        sensor_types = input_data.get("sensor_types", ["imu", "gps", "barometer", "lidar", "camera"])
        vehicle_id = input_data.get("vehicle_id", "UAV_1")
        
        result_data = {}
        ts = time.time()
        source = "mock"

        # 优先使用 GzSensorBridge（Gazebo 真实传感器）
        bridge = get_sensor_bridge()
        if bridge is not None and bridge.is_running:
            try:
                if "lidar" in sensor_types:
                    scan = bridge.get_lidar_scan()
                    if scan is not None:
                        result_data["lidar_data"] = {
                            "ranges_count": scan["count"],
                            "angle_min": scan["angle_min"],
                            "angle_max": scan["angle_max"],
                            "range_min": scan["range_min"],
                            "range_max": scan["range_max"],
                            "min_distance": min(r for r in scan["ranges"] if r > scan["range_min"]) if scan["ranges"] else 0,
                            "obstacle_count": sum(1 for r in scan["ranges"] if scan["range_min"] < r < scan["range_max"] * 0.8),
                        }
                        source = "gazebo"

                if "camera" in sensor_types:
                    cam_info = bridge.get_camera_info()
                    if cam_info["has_data"]:
                        result_data["camera_data"] = {
                            "width": cam_info["width"],
                            "height": cam_info["height"],
                            "fps": round(cam_info["fps"], 1),
                            "status": "active",
                        }
                        source = "gazebo"

                if result_data:
                    result_data["timestamp"] = ts
                    result_data["source"] = source
                    return SkillResult(
                        success=True,
                        output=result_data,
                        cost_time=0.0,
                        logs=[f"GetSensorData: 从 Gazebo 获取 {list(result_data.keys())}"],
                    )
            except Exception as e:
                logger.warning(f"GetSensorData GzSensorBridge 失败: {e}")

        # 回退到 AirSim SimManager
        sim_mgr = get_sim_manager()
        
        if sim_mgr is not None and sim_mgr.airsim_bridge:
            try:
                bridge = sim_mgr.airsim_bridge
                
                if "imu" in sensor_types:
                    imu_data = bridge.get_imu_data(vehicle_id)
                    if imu_data:
                        result_data["imu_data"] = imu_data
                
                if "gps" in sensor_types:
                    gps_data = bridge.get_gps_data(vehicle_id)
                    if gps_data:
                        result_data["gps_data"] = gps_data
                
                if "barometer" in sensor_types:
                    baro_data = bridge.get_barometer_data(vehicle_id)
                    if baro_data:
                        result_data["barometer_data"] = baro_data
                
                if result_data:
                    result_data["timestamp"] = ts
                    return SkillResult(
                        success=True,
                        output=result_data,
                        cost_time=0.0,
                        logs=[f"GetSensorData: fetched {list(result_data.keys())} via AirSim"],
                    )
            except Exception as e:
                logger.error(f"GetSensorData 执行失败: {e}")
        
        start = time.time()
        time.sleep(0.02)
        elapsed = round(time.time() - start, 4)
        
        result_data = {
            "imu_data": {
                "orientation": [0.0, 0.0, 0.0, 1.0],
                "angular_velocity": [0.0, 0.0, 0.0],
                "linear_acceleration": [0.0, 0.0, -9.8],
            },
            "gps_data": {
                "latitude": 0.0,
                "longitude": 0.0,
                "altitude": 100.0,
                "speed": 0.0,
                "heading": 0.0,
            },
            "barometer_data": {
                "altitude": 10.0,
                "pressure": 1013.25,
                "qnh": 1013.25,
            },
            "timestamp": ts,
        }
        
        return SkillResult(
            success=True,
            output=result_data,
            cost_time=elapsed,
            logs=[f"GetSensorData: fetched sensor data (mock mode)"],
        )


# ══════════════════════════════════════════════════════════════════════════════
#  Observe — 拍照 + VLM 视觉分析 (真正的"看")
# ══════════════════════════════════════════════════════════════════════════════

def _get_adapter():
    """获取仿真适配器。"""
    from adapters.adapter_manager import get_adapter
    return get_adapter()


class Observe(Skill):
    name = "observe"
    description = (
        "用摄像头拍照, 并用视觉大模型(VLM)分析看到了什么。"
        "这是你真正'看'东西的方式。返回对环境的文字描述。"
        "可指定方向: front(前)/rear(后)/left(左)/right(右)/down(下)/around(环视所有方向)。"
        "注意: 后方请用 rear 而不是 back。向下观察地面用 down。"
        "也可以指定重点关注什么, 比如'寻找受困者'或'检查地形'。"
    )
    skill_type = "perception"
    robot_type = ["UAV"]
    preconditions = []
    cost = 4.0
    input_schema = {
        "direction": "str, 拍照方向: front/rear/left/right/down/around(环视), 默认front。后方用rear不用back, 向下用down",
        "focus": "str, 重点关注什么, 如'寻找地面上的人'、'检查建筑状况', 默认'观察环境'",
    }
    output_schema = {
        "description": "str, VLM 对图像的分析描述",
        "direction": "str, 拍照方向",
        "objects_found": "list, 检测到的物体",
    }

    def check_precondition(self, robot_state: dict) -> bool:
        adapter = _get_adapter()
        if adapter is None:
            return False
        try:
            return adapter.is_in_air()
        except Exception:
            return False

    # 方向别名映射: LLM 可能传各种写法，统一到 Gazebo 实际的 front/rear/left/right
    _DIR_ALIASES = {
        "front": "front", "前": "front", "前方": "front", "forward": "front",
        "rear": "rear", "后": "rear", "后方": "rear", "back": "rear", "backward": "rear",
        "left": "left", "左": "left", "左方": "left",
        "right": "right", "右": "right", "右方": "right",
        "down": "down", "下": "down", "下方": "down", "底": "down",
        "around": None,  # 特殊: 拍所有方向
        "all": None,
    }

    def execute(self, input_data: dict) -> SkillResult:
        raw_direction = input_data.get("direction", "front").strip().lower()
        focus = input_data.get("focus", "观察环境")
        start = time.time()

        # 方向映射
        mapped = self._DIR_ALIASES.get(raw_direction, raw_direction)

        # "around" / "all" → 拍所有方向并拼接
        if mapped is None:
            return self._observe_all(focus, start)

        direction = mapped

        # 1. 抓图：优先 adapter（AirSim base64→bytes），fallback Gazebo（numpy BGR）
        image = None
        adapter = _get_adapter()

        # 路径 A: AirSim adapter — 返回 base64 JPEG，decode 成 bytes 直接给 VLM
        _dir_to_cam = {"front": "cam_front", "left": "cam_left", "right": "cam_right", "rear": "cam_rear", "down": "cam_down"}
        try:
            if adapter and hasattr(adapter, 'get_image_base64'):
                import base64 as b64mod
                cam_name = _dir_to_cam.get(direction, f"cam_{direction}")
                b64_str = adapter.get_image_base64(camera_name=cam_name)
                if b64_str:
                    image = b64mod.b64decode(b64_str)
                    logger.debug("通过 adapter.get_image_base64(%s) 抓图成功 (%d bytes)", cam_name, len(image))
        except Exception as e:
            logger.warning("adapter 抓图失败: %s, 尝试 Gazebo 路径", e)

        # 路径 B: Gazebo gz_camera — 返回 numpy BGR
        if image is None:
            try:
                from perception.gz_camera import get_camera, init_camera
                camera = get_camera()
                if camera is None:
                    camera = init_camera()
                image = camera.capture(direction)
            except ImportError:
                logger.warning("gz 模块不可用, 跳过 Gazebo 相机路径")
            except Exception as e:
                logger.warning("Gazebo 相机抓图失败: %s", e)

        if image is None:
            return SkillResult(
                success=False,
                error_msg=f"相机抓图失败: adapter 和 Gazebo 均不可用",
                cost_time=round(time.time() - start, 2),
            )

        if image is None:
            return SkillResult(
                success=False,
                error_msg=f"{direction}方向相机无图像, 可能传感器未就绪",
                cost_time=round(time.time() - start, 2),
            )

        # 2. 获取当前高度
        adapter = _get_adapter()
        altitude = 10.0
        if adapter:
            try:
                pos = adapter.get_position()
                altitude = abs(pos.down)
            except Exception:
                pass

        dir_cn = {"front": "前方", "rear": "后方", "left": "左方", "right": "右方"}
        direction_cn = dir_cn.get(direction, direction)

        # 3. 调用 VLM 分析
        try:
            from perception.vlm_analyzer import get_analyzer, init_analyzer
            analyzer = get_analyzer()
            if analyzer is None:
                analyzer = init_analyzer()

            result = analyzer.analyze_image(
                image=image,
                system_prompt=(
                    "你是一架无人机的视觉系统。分析摄像头图像, 描述你看到的环境。"
                    "用简洁的中文回答。重点关注: 人员、建筑、障碍物、地形。"
                    "如果看到人, 描述人数、位置(画面中的大致方位)、状态(站/躺/动)。"
                    '输出 JSON: {"description": "环境描述", "objects": [{"type": "类型", "position": "方位", "detail": "细节"}], "hazards": ["危险因素"]}'
                ),
                user_prompt=(
                    f"拍摄方向: {direction_cn}, 飞行高度: {altitude:.0f}米。"
                    f"重点关注: {focus}。"
                    f"请分析这张图片。"
                ),
                max_tokens=400,
            )

            elapsed = round(time.time() - start, 2)

            if result is None:
                return SkillResult(
                    success=True,
                    output={
                        "description": f"拍摄了{direction_cn}图像但VLM分析返回异常",
                        "direction": direction_cn,
                        "objects_found": [],
                    },
                    cost_time=elapsed,
                    logs=[f"observe {direction_cn}: VLM 返回异常 ({elapsed:.1f}s)"],
                )

            desc = result.get("description", "无描述")
            objects = result.get("objects", [])
            hazards = result.get("hazards", [])

            # 注入到感知摘要
            try:
                from perception.daemon import get_daemon
                daemon = get_daemon()
                if daemon:
                    summary = f"[{direction_cn}] {desc}"
                    if objects:
                        summary += f" | 检测到: {', '.join(o.get('type','?') for o in objects)}"
                    daemon.set_vlm_summary(summary)
            except Exception:
                pass

            return SkillResult(
                success=True,
                output={
                    "description": desc,
                    "direction": direction_cn,
                    "objects_found": objects,
                    "hazards": hazards,
                },
                cost_time=elapsed,
                logs=[f"observe {direction_cn}: {desc[:60]}... ({elapsed:.1f}s)"],
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            logger.error(f"VLM 分析异常: {e}")
            return SkillResult(
                success=False,
                error_msg=f"VLM 分析失败: {e}",
                cost_time=elapsed,
            )

    def _observe_all(self, focus: str, start: float) -> SkillResult:
        """拍所有方向并拼接描述。优先 adapter（仅前向），fallback Gazebo（多方向）。"""
        from perception.vlm_analyzer import get_analyzer, init_analyzer

        # 尝试 Gazebo 多方向相机
        gz_camera = None
        try:
            from perception.gz_camera import get_camera, init_camera
            gz_camera = get_camera()
            if gz_camera is None:
                gz_camera = init_camera()
        except ImportError:
            pass

        # adapter fallback（仅支持前向）
        adapter = _get_adapter()
        has_adapter_cam = adapter and hasattr(adapter, 'get_image_base64')

        if gz_camera is None and not has_adapter_cam:
            return SkillResult(
                success=False,
                error_msg="相机不可用: gz 模块未安装且 adapter 无相机接口",
                cost_time=round(time.time() - start, 2),
            )

        analyzer = get_analyzer()
        if analyzer is None:
            analyzer = init_analyzer()

        # 获取高度
        adapter = _get_adapter()
        altitude = 10.0
        if adapter:
            try:
                pos = adapter.get_position()
                altitude = abs(pos.down)
            except Exception:
                pass

        dir_cn = {"front": "前方", "rear": "后方", "left": "左方", "right": "右方", "down": "下方"}
        all_descs = []
        all_objects = []
        success_count = 0

        for d in ["front", "left", "right", "rear", "down"]:
            try:
                image = None
                # AirSim adapter 支持所有方向摄像头
                _dir_to_cam = {"front": "cam_front", "left": "cam_left", "right": "cam_right", "rear": "cam_rear", "down": "cam_down"}
                if has_adapter_cam:
                    try:
                        import base64 as b64mod
                        cam_name = _dir_to_cam.get(d, f"cam_{d}")
                        b64_str = adapter.get_image_base64(camera_name=cam_name)
                        if b64_str:
                            image = b64mod.b64decode(b64_str)
                    except Exception:
                        pass
                # fallback Gazebo
                if image is None and gz_camera is not None:
                    image = gz_camera.capture(d)
                if image is None:
                    all_descs.append(f"[{dir_cn[d]}] 未获取到图像")
                    continue

                result = analyzer.analyze_image(
                    image=image,
                    system_prompt=(
                        "你是一架无人机的视觉系统。分析摄像头图像, 描述你看到的环境。"
                        "用简洁的中文回答。重点关注: 人员、建筑、障碍物、地形。"
                        '输出 JSON: {"description": "环境描述", "objects": [{"type": "类型", "position": "方位", "detail": "细节"}], "hazards": ["危险因素"]}'
                    ),
                    user_prompt=(
                        f"拍摄方向: {dir_cn[d]}, 飞行高度: {altitude:.0f}米。"
                        f"重点关注: {focus}。请分析这张图片。"
                    ),
                    max_tokens=300,
                )

                if result:
                    desc = result.get("description", "无描述")
                    all_descs.append(f"[{dir_cn[d]}] {desc}")
                    all_objects.extend(result.get("objects", []))
                    success_count += 1
                else:
                    all_descs.append(f"[{dir_cn[d]}] VLM 分析异常")
            except Exception as e:
                all_descs.append(f"[{dir_cn[d]}] 失败: {e}")

        elapsed = round(time.time() - start, 2)
        combined = "\n".join(all_descs)

        # 注入感知摘要
        try:
            from perception.daemon import get_daemon
            daemon = get_daemon()
            if daemon:
                daemon.set_vlm_summary(f"[环视] {combined[:200]}")
        except Exception:
            pass

        if success_count == 0:
            return SkillResult(
                success=False,
                error_msg="所有方向相机均未获取到图像",
                cost_time=elapsed,
            )

        return SkillResult(
            success=True,
            output={
                "description": combined,
                "direction": "环视(四方向)",
                "objects_found": all_objects,
            },
            cost_time=elapsed,
            logs=[f"observe 环视: {success_count}/4方向成功 ({elapsed:.1f}s)"],
        )


class Perceive(Skill):
    """
    主动感知技能 — LLM 自己决定看什么方向、关注什么内容。
    
    与 observe 的区别：
    - observe: 固定流程，拍所有方向，固定分析
    - perceive: LLM 自定义 prompt，看特定方向，获取特定信息
    
    用法示例：
    - perceive(direction="front", focus="前方建筑的窗户是否有破损？")
    - perceive(direction="down", focus="下方地面是否适合降落？")
    - perceive(direction="left", focus="左边有什么障碍物？距离多远？")
    """
    
    name = "perceive"
    description = "主动感知：查看指定方向的摄像头画面，用自定义问题获取特定信息。你可以自己决定看什么方向、问什么问题。"
    skill_type = "perception"
    
    input_schema = {
        "direction": "str，摄像头方向: front/left/right/rear/down",
        "focus": "str，你想了解的信息，用自然语言描述（如'前方有没有障碍物？距离多远？'）",
    }
    
    preconditions = []
    
    _DIR_ALIASES = {
        "前": "front", "前方": "front", "forward": "front",
        "左": "left", "左方": "left", "左侧": "left",
        "右": "right", "右方": "right", "右侧": "right",
        "后": "rear", "后方": "rear", "backward": "rear", "back": "rear",
        "下": "down", "下方": "down", "below": "down",
    }
    
    def execute(self, input_data=None, direction: str = "front", focus: str = "", **kwargs) -> SkillResult:
        start = time.time()
        
        # 兼容 dict 输入（executor 传整个 dict 作为第一个参数）
        if isinstance(input_data, dict):
            direction = input_data.get("direction", direction)
            focus = input_data.get("focus", focus)
        elif isinstance(input_data, str):
            direction = input_data
        
        # 方向别名映射
        direction = self._DIR_ALIASES.get(direction, direction)
        if direction not in ("front", "left", "right", "rear", "down"):
            direction = "front"
        
        # 获取被动感知引擎
        passive_engine = _get_passive_perception()
        if passive_engine:
            result = passive_engine.perceive_active(direction=direction, focus=focus)
            elapsed = round(time.time() - start, 2)
            
            summary = result.get("summary", "无法获取信息")
            return SkillResult(
                success="error" not in result,
                data={
                    "direction": direction,
                    "focus": focus,
                    "perception": result,
                    "summary": summary,
                },
                cost_time=elapsed,
                logs=[f"perceive({direction}): {summary}"],
            )
        
        # fallback: 没有被动感知引擎，直接走 adapter
        adapter = _get_adapter()
        if not adapter or not hasattr(adapter, 'get_image_base64'):
            return SkillResult(
                success=False,
                error_msg="adapter 不可用",
                cost_time=round(time.time() - start, 2),
            )
        
        dir_to_cam = {"front": "cam_front", "left": "cam_left", "right": "cam_right",
                      "rear": "cam_rear", "down": "cam_down"}
        cam_name = dir_to_cam.get(direction, "cam_front")
        
        try:
            import base64 as b64mod
            b64_str = adapter.get_image_base64(camera_name=cam_name)
            if not b64_str:
                return SkillResult(success=False, error_msg=f"{direction} 摄像头无图像",
                                   cost_time=round(time.time() - start, 2))
            
            image = b64mod.b64decode(b64_str)
            analyzer = get_analyzer()
            if analyzer is None:
                analyzer = init_analyzer()
            
            prompt = f"Analyze this drone camera image ({direction} view). Focus: {focus or 'describe environment'}. Answer in Chinese."
            result = analyzer.analyze_image(image, system_prompt="You are a drone perception system.", user_prompt=prompt)
            elapsed = round(time.time() - start, 2)
            
            return SkillResult(
                success=True,
                data={"direction": direction, "focus": focus, "summary": result},
                cost_time=elapsed,
                logs=[f"perceive({direction}): {result[:100]}..."],
            )
        except Exception as e:
            return SkillResult(success=False, error_msg=str(e),
                               cost_time=round(time.time() - start, 2))


# ── 被动感知引擎全局引用 ──
_global_passive_perception = None

def set_passive_perception(engine):
    global _global_passive_perception
    _global_passive_perception = engine

def _get_passive_perception():
    return _global_passive_perception
