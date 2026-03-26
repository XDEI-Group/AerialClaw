"""
airsim_rpc.py
纯 socket 实现的 msgpack-rpc 客户端，完全不依赖 tornado/asyncio。
用于替代 airsim 官方包的底层通信，彻底解决 event loop 冲突。
"""
import socket
import struct
import threading
import msgpack


class MsgpackRpcClient:
    """同步阻塞的 msgpack-rpc 客户端，纯 socket 实现。"""

    def __init__(self, host: str, port: int, timeout: float = 10.0):
        self._host = host
        self._port = port
        self._timeout = timeout
        self._sock = None
        self._msg_id = 0
        self._lock = threading.Lock()
        self._unpacker = msgpack.Unpacker(raw=False)

    def connect(self) -> bool:
        try:
            self._sock = socket.create_connection((self._host, self._port), timeout=self._timeout)
            self._sock.settimeout(self._timeout)
            return True
        except Exception:
            return False

    def close(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def call(self, method: str, *args):
        with self._lock:
            self._msg_id = (self._msg_id + 1) & 0xFFFFFFFF
            msg_id = self._msg_id
            # msgpack-rpc request: [type=0, msgid, method, params]
            payload = msgpack.packb([0, msg_id, method, list(args)], use_bin_type=True)
            self._sock.sendall(payload)
            # read response
            return self._recv_response(msg_id)

    def _recv_response(self, expected_id: int):
        self._unpacker = msgpack.Unpacker(raw=False)
        while True:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("Connection closed")
            self._unpacker.feed(chunk)
            for msg in self._unpacker:
                # msgpack-rpc response: [type=1, msgid, error, result]
                if isinstance(msg, list) and len(msg) == 4 and msg[0] == 1:
                    if msg[1] == expected_id:
                        if msg[2]:
                            raise RuntimeError(f"RPC error: {msg[2]}")
                        return msg[3]


class AirSimDirectClient:
    """
    直接用 socket 与 AirSim RPC server 通信的客户端。
    替代 airsim.MultirotorClient，不依赖 tornado/asyncio。
    """

    def __init__(self, ip: str = "127.0.0.1", port: int = 41451, timeout: float = 10.0):
        self._rpc = MsgpackRpcClient(ip, port, timeout)
        self._vehicle = ""

    def connect(self) -> bool:
        return self._rpc.connect()

    def close(self):
        self._rpc.close()

    def ping(self) -> bool:
        try:
            return bool(self._rpc.call("ping"))
        except Exception:
            return False

    def confirm_connection(self):
        """Mimic airsim.confirmConnection()"""
        self._rpc.call("ping")

    def enable_api_control(self, is_enabled: bool, vehicle_name: str = ""):
        self._rpc.call("enableApiControl", is_enabled, vehicle_name)

    def arm_disarm(self, arm: bool, vehicle_name: str = "") -> bool:
        return bool(self._rpc.call("armDisarm", arm, vehicle_name))

    def list_vehicles(self) -> list:
        try:
            return self._rpc.call("listVehicles") or []
        except Exception:
            return []

    def get_multirotor_state(self, vehicle_name: str = "") -> dict:
        """返回原始 dict，调用者自行解析。"""
        return self._rpc.call("getMultirotorState", vehicle_name)

    def takeoff_async_join(self, timeout_sec: float = 20.0, vehicle_name: str = ""):
        self._rpc.call("takeoff", timeout_sec, vehicle_name)

    def land_async_join(self, timeout_sec: float = 60.0, vehicle_name: str = ""):
        self._rpc.call("land", timeout_sec, vehicle_name)

    def hover_async_join(self, vehicle_name: str = ""):
        self._rpc.call("hover", vehicle_name)

    def move_to_position_async_join(self, x, y, z, velocity,
                                     timeout_sec=120.0, vehicle_name=""):
        self._rpc.call("moveToPosition", x, y, z, velocity,
                       timeout_sec, 0, 0, 0, vehicle_name)

    def sim_get_images(self, requests: list, vehicle_name: str = "", external: bool = False) -> list:
        """
        requests: list of dicts with keys: camera_name, image_type, pixels_as_float, compress
        AirSim RPC expects list of dicts (not lists), plus vehicle_name and external args.
        """
        rpc_reqs = [{"camera_name": r["camera_name"], "image_type": r["image_type"],
                     "pixels_as_float": r["pixels_as_float"], "compress": r["compress"]}
                    for r in requests]
        return self._rpc.call("simGetImages", rpc_reqs, vehicle_name, external) or []

    def get_lidar_data(self, lidar_name: str = "LidarSensor1", vehicle_name: str = "") -> dict:
        """Get LiDAR point cloud data from AirSim.
        Returns dict with keys: point_cloud (flat list of x,y,z), timestamp, pose, etc.
        """
        return self._rpc.call("getLidarData", lidar_name, vehicle_name) or {}

    def sim_get_collision_info(self, vehicle_name: str = "") -> dict:
        """Get collision info. Returns dict with has_collided, normal, impact_point, etc."""
        try:
            return self._rpc.call("simGetCollisionInfo", vehicle_name) or {}
        except Exception:
            return {}

    def move_by_velocity_async_join(self, vx: float, vy: float, vz: float,
                                     duration: float, vehicle_name: str = ""):
        """Speed control: fly at (vx, vy, vz) m/s for duration seconds (NED frame)."""
        self._rpc.call("moveByVelocity", vx, vy, vz, duration, 0, 0, 0, 0, vehicle_name)
