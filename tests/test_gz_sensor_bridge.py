import math

import numpy as np

from sim.gz_sensor_bridge import GzSensorBridge


class FakeImage:
    width = 2
    height = 1
    pixel_format_type = 3  # RGB_INT8
    data = bytes([255, 0, 0, 0, 255, 0])


class FakeScan:
    ranges = [1.0, 2.5, float("inf")]
    angle_min = -math.pi
    angle_max = math.pi
    angle_step = math.pi
    range_min = 0.1
    range_max = 30.0


def test_bridge_imports_and_exposes_server_api():
    bridge = GzSensorBridge(model_name="x500_lidar_2d_cam_0", world_name="urban_rescue")

    for attr in [
        "is_running",
        "start",
        "stop",
        "get_camera_image",
        "get_camera_info",
        "get_lidar_scan",
        "get_lidar_info",
        "get_status",
    ]:
        assert hasattr(bridge, attr)

    status = bridge.get_status()
    assert status["running"] is False
    assert set(status["cameras"].keys()) == {"front", "rear", "left", "right", "down"}


def test_camera_decode_updates_latest_frame_and_info():
    bridge = GzSensorBridge()
    bridge._on_image("front", FakeImage())

    image = bridge.get_camera_image("front")
    info = bridge.get_camera_info("front")

    assert isinstance(image, np.ndarray)
    assert image.shape == (1, 2, 3)
    assert info["width"] == 2
    assert info["height"] == 1
    assert info["frame_count"] == 1


def test_lidar_decode_updates_latest_scan_and_info():
    bridge = GzSensorBridge()
    bridge._on_lidar(FakeScan())

    scan = bridge.get_lidar_scan()
    info = bridge.get_lidar_info()

    assert scan["ranges"][:2] == [1.0, 2.5]
    assert scan["count"] == 3
    assert scan["range_max"] == 30.0
    assert info["frame_count"] == 1
