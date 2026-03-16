#!/usr/bin/env python3
"""
test_airsim_remote.py — AirSim 远程连接测试

用法:
    pip install airsim
    python test_airsim_remote.py --ip 10.204.233.85

测试内容:
    1. 连接 AirSim 服务器
    2. 获取无人机状态
    3. 起飞到 5m
    4. 前飞 10m
    5. 悬停 3s
    6. 获取相机图像
    7. 获取 LiDAR 数据
    8. 返航降落
"""

import argparse
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.airsim_adapter import AirSimAdapter


def main():
    parser = argparse.ArgumentParser(description="AirSim 远程连接测试")
    parser.add_argument("--ip", default="10.204.233.85", help="AirSim 服务器 IP")
    parser.add_argument("--port", type=int, default=41451, help="AirSim 端口")
    parser.add_argument("--vehicle", default="", help="无人机名称 (空=默认)")
    parser.add_argument("--no-fly", action="store_true", help="只测连接，不飞")
    args = parser.parse_args()

    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    print(f"\n{'='*60}")
    print(f"  AerialClaw AirSim 远程连接测试")
    print(f"  目标: {args.ip}:{args.port}")
    print(f"  无人机: {args.vehicle or '默认'}")
    print(f"{'='*60}\n")

    # 1. 创建适配器并连接
    adapter = AirSimAdapter(vehicle_name=args.vehicle)
    conn_str = f"{args.ip}:{args.port}"

    print("[1/8] 连接 AirSim...")
    if not adapter.connect(conn_str):
        print("❌ 连接失败，退出")
        return 1

    # 2. 获取状态
    print("[2/8] 获取无人机状态...")
    state = adapter.get_state()
    pos = adapter.get_position()
    print(f"  位置: NED({pos.north:.1f}, {pos.east:.1f}, {pos.down:.1f})")
    print(f"  高度: {pos.altitude:.1f}m")
    print(f"  在空中: {state.in_air}")
    print(f"  航向: {state.heading_deg:.0f}°")
    print(f"  模式: {state.mode}")

    if args.no_fly:
        print("\n✅ 连接测试通过 (--no-fly 模式，跳过飞行)")
        adapter.disconnect()
        return 0

    # 3. 起飞
    print("\n[3/8] 起飞到 5m...")
    result = adapter.takeoff(5.0)
    print(f"  {'✅' if result.success else '❌'} {result.message} ({result.duration}s)")
    if not result.success:
        adapter.disconnect()
        return 1

    # 4. 前飞 10m
    print("[4/8] 前飞 10m (NED north+10)...")
    pos = adapter.get_position()
    result = adapter.fly_to_ned(pos.north + 10, pos.east, pos.down, speed=2.0)
    print(f"  {'✅' if result.success else '❌'} {result.message} ({result.duration}s)")

    # 5. 悬停
    print("[5/8] 悬停 3s...")
    result = adapter.hover(3.0)
    print(f"  {'✅' if result.success else '❌'} {result.message}")

    # 6. 相机图像
    print("[6/8] 获取相机图像...")
    for cam_name in ["0", "front_custom"]:
        img = adapter.get_camera_image(camera_name=cam_name)
        if img is not None:
            print(f"  ✅ 相机 '{cam_name}': {img.shape}")
        else:
            print(f"  ⚠️ 相机 '{cam_name}': 无数据")

    # 7. LiDAR
    print("[7/8] 获取 LiDAR 数据...")
    for lidar_name in ["LidarSensor1", "LidarSensor2"]:
        points = adapter.get_lidar_data(lidar_name=lidar_name)
        if points is not None:
            print(f"  ✅ {lidar_name}: {points.shape[0]} 点")
        else:
            print(f"  ⚠️ {lidar_name}: 无数据")

    # 8. 返航
    print("[8/8] 返航降落...")
    result = adapter.return_to_launch()
    print(f"  {'✅' if result.success else '❌'} {result.message} ({result.duration}s)")

    adapter.disconnect()
    print(f"\n{'='*60}")
    print("  测试完成 ✅")
    print(f"{'='*60}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
