"""
swarm/launcher.py — 多机集群一键启动

在单台机器上启动完整的三级集群用于演示/测试。
生产环境各节点分布在不同机器上，各自启动即可。

用法：
    python -m swarm.launcher --mode demo
    python -m swarm.launcher --mode commander --port 6000
    python -m swarm.launcher --mode coordinator --port 6100 --parent http://10.0.0.1:6000
    python -m swarm.launcher --mode executor --port 6200 --parent http://10.0.0.1:6100
"""

import argparse
import logging
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swarm.commander import Commander
from swarm.coordinator import Coordinator
from swarm.executor import Executor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def launch_demo(num_coordinators: int = 2, drones_per_coordinator: int = 2):
    """
    在单机上启动完整演示集群。
    
    架构：
        Commander (port 6000)
        ├── Coordinator-A (port 6100)
        │     ├── UAV-A1 (port 6200)
        │     └── UAV-A2 (port 6201)
        └── Coordinator-B (port 6101)
              ├── UAV-B1 (port 6210)
              └── UAV-B2 (port 6211)
    """
    logger.info("=" * 60)
    logger.info("AerialClaw Swarm Demo — 三级多机协作")
    logger.info("=" * 60)

    # 1. 启动主节点
    commander = Commander(port=6000, node_id="commander")
    commander.start()
    time.sleep(1)

    # 2. 启动子节点
    coordinators = []
    for i in range(num_coordinators):
        coord = Coordinator(
            port=6100 + i,
            commander_url="http://127.0.0.1:6000",
            node_id=f"coord-{chr(65 + i)}",      # coord-A, coord-B, ...
            name=f"区域协调站-{chr(65 + i)}",
        )
        coord.start()
        coordinators.append(coord)
        time.sleep(0.5)

    # 3. 启动无人机
    executors = []
    for i, coord in enumerate(coordinators):
        for j in range(drones_per_coordinator):
            port = 6200 + i * 10 + j
            executor = Executor(
                port=port,
                coordinator_url=f"http://127.0.0.1:{6100 + i}",
                node_id=f"uav-{chr(65 + i)}{j + 1}",   # uav-A1, uav-A2, uav-B1, ...
                name=f"无人机-{chr(65 + i)}{j + 1}",
                capabilities=["flight", "camera_5x", "lidar_2d", "search", "patrol"],
            )
            executor.start()
            executors.append(executor)
            time.sleep(0.5)

    # 等待所有注册完成
    time.sleep(2)

    logger.info("")
    logger.info("=" * 60)
    logger.info("集群启动完成!")
    logger.info(f"  主节点:     commander (port 6000)")
    for i, coord in enumerate(coordinators):
        logger.info(f"  子节点:     {coord.node_info.node_id} (port {coord.node_info.port})")
        alive = coord.swarm.get_alive_children()
        for drone_id in alive:
            logger.info(f"    └── 无人机: {drone_id}")
    logger.info("=" * 60)
    logger.info("")

    return commander, coordinators, executors


def main():
    parser = argparse.ArgumentParser(description="AerialClaw Swarm Launcher")
    parser.add_argument("--mode", choices=["demo", "commander", "coordinator", "executor"],
                        default="demo", help="启动模式")
    parser.add_argument("--port", type=int, default=6000, help="监听端口")
    parser.add_argument("--parent", type=str, default=None, help="上级节点 URL")
    parser.add_argument("--node-id", type=str, default=None, help="节点 ID")
    parser.add_argument("--name", type=str, default=None, help="节点名称")
    parser.add_argument("--coordinators", type=int, default=2, help="[demo] 子节点数量")
    parser.add_argument("--drones", type=int, default=2, help="[demo] 每个子节点的无人机数")

    args = parser.parse_args()

    if args.mode == "demo":
        commander, coordinators, executors = launch_demo(args.coordinators, args.drones)

        # 交互式输入任务
        print("\n输入任务指令（Ctrl+C 退出）：")
        try:
            while True:
                instruction = input("\n>>> ").strip()
                if not instruction:
                    continue
                print("\n执行中...\n")
                report = commander.execute_mission(instruction)
                print("\n" + "=" * 60)
                print("全局任务报告")
                print("=" * 60)
                print(report)
                print("=" * 60)
        except KeyboardInterrupt:
            print("\n\n正在关闭集群...")
            for e in executors:
                e.stop()
            for c in coordinators:
                c.stop()
            commander.stop()
            print("已关闭。")

    elif args.mode == "commander":
        commander = Commander(port=args.port, node_id=args.node_id or "commander")
        commander.start()
        print(f"Commander running on port {args.port}. Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            commander.stop()

    elif args.mode == "coordinator":
        if not args.parent:
            print("Error: --parent is required for coordinator mode")
            sys.exit(1)
        coord = Coordinator(
            port=args.port, commander_url=args.parent,
            node_id=args.node_id, name=args.name or "Coordinator",
        )
        coord.start()
        print(f"Coordinator running on port {args.port}. Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            coord.stop()

    elif args.mode == "executor":
        if not args.parent:
            print("Error: --parent is required for executor mode")
            sys.exit(1)
        executor = Executor(
            port=args.port, coordinator_url=args.parent,
            node_id=args.node_id, name=args.name or "UAV",
        )
        executor.start()
        print(f"Executor running on port {args.port}. Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            executor.stop()


if __name__ == "__main__":
    main()
