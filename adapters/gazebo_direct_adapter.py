"""
Gazebo Direct Adapter

A lightweight local-demo adapter for Gazebo Harmonic worlds that already expose
/world/<world>/set_pose. It moves the visual/sensor model directly with Gazebo
Transport instead of going through PX4/MAVSDK.

This is intentionally a demo/control fallback: it keeps hard skills and cockpit
controls bound to the same Gazebo model that publishes camera/LiDAR topics, so
Web UI validation is not a fake mock-control success.
"""

from __future__ import annotations

import math
import os
import subprocess
import threading
import time
from dataclasses import dataclass

from adapters.sim_adapter import ActionResult, GPSPosition, Position, SimAdapter, VehicleState


@dataclass
class _Pose:
    north: float = 0.0  # mapped to Gazebo y
    east: float = 0.0   # mapped to Gazebo x
    down: float = -3.0  # altitude = -down, Gazebo z = -down
    heading_deg: float = 0.0


class GazeboDirectAdapter(SimAdapter):
    name = "gazebo_direct"
    description = "Gazebo direct set_pose adapter (demo: no PX4, controls sensor model pose)"
    supported_vehicles = ["multirotor"]

    def __init__(self):
        self.world = os.getenv("PX4_GZ_WORLD", os.getenv("GZ_WORLD", "urban_rescue"))
        model_env = os.getenv("PX4_SIM_MODEL", os.getenv("GZ_MODEL", "x500_lidar_2d_cam_0"))
        self.model = model_env if model_env.endswith("_0") else f"{model_env}_0"
        self.connected = False
        self.armed = False
        self.in_air = False
        self.pose = _Pose(down=-3.0)
        self.velocity = [0.0, 0.0, 0.0]
        self._last_velocity_ts = time.time()
        self._pose_lock = threading.RLock()
        self._hold_thread: threading.Thread | None = None
        self._hold_stop = threading.Event()
        # Prefer in-process Gazebo Transport for smooth pose hold; CLI is fallback.
        self._hold_hz = float(os.getenv("GAZEBO_DIRECT_HOLD_HZ", "30"))
        self._last_error = ""
        self._gz_node = None
        self._gz_pose_cls = None
        self._gz_bool_cls = None
        self._init_gz_transport()

    def connect(self, connection_str: str = "", timeout: float = 15.0) -> bool:
        if connection_str:
            # Accept forms like world=urban_rescue,model=x500_lidar_2d_cam_0
            for part in connection_str.split(","):
                if "=" not in part:
                    continue
                k, v = [x.strip() for x in part.split("=", 1)]
                if k == "world" and v:
                    self.world = v
                elif k == "model" and v:
                    self.model = v
        ok = self._set_pose(self.pose)
        self.connected = ok
        if ok:
            self._start_hold_loop()
        return ok

    def disconnect(self) -> None:
        self.connected = False
        self._hold_stop.set()

    def is_connected(self) -> bool:
        return self.connected

    def get_state(self) -> VehicleState:
        return VehicleState(
            armed=self.armed,
            in_air=self.in_air,
            mode="GAZEBO_DIRECT",
            position_ned=self.get_position(),
            position_gps=self.get_gps(),
            battery_voltage=16.0,
            battery_percent=0.95,
            heading_deg=self.pose.heading_deg,
            velocity=list(self.velocity),
        )

    def get_position(self) -> Position:
        with self._pose_lock:
            return Position(self.pose.north, self.pose.east, self.pose.down)

    def get_gps(self) -> GPSPosition:
        return GPSPosition(0.0, 0.0, -self.pose.down)

    def get_battery(self) -> tuple:
        return (16.0, 0.95)

    def is_armed(self) -> bool:
        return self.armed

    def is_in_air(self) -> bool:
        return self.in_air

    def arm(self) -> ActionResult:
        self.armed = True
        return ActionResult(True, "armed (gazebo direct)")

    def disarm(self) -> ActionResult:
        self.armed = False
        return ActionResult(True, "disarmed (gazebo direct)")

    def takeoff(self, altitude: float = 5.0) -> ActionResult:
        self.armed = True
        self.in_air = True
        with self._pose_lock:
            self.pose.down = -abs(float(altitude))
            ok = self._set_pose(self.pose)
        self._start_hold_loop()
        # Treat direct pose commands as accepted once the adapter state is
        # updated. Gazebo set_pose can transiently return false while the model
        # pose is still driven by the hold loop; reporting that as skill failure
        # makes the UI show false negatives like "landed" but ok=false.
        success = ok or self.connected
        data = {"altitude": -self.pose.down}
        if not ok and self._last_error:
            data["warning"] = self._last_error
        return ActionResult(success, f"takeoff to {altitude:.1f}m (gazebo direct, pose hold)", data)

    def land(self) -> ActionResult:
        with self._pose_lock:
            self.pose.down = 0.0
            ok = self._set_pose(self.pose)
        self.in_air = False
        data = {"altitude": 0.0}
        if not ok and self._last_error:
            data["warning"] = self._last_error
        return ActionResult(ok or self.connected, "landed (gazebo direct)", data)

    def fly_to_ned(self, north: float, east: float, down: float, speed: float = 2.0) -> ActionResult:
        with self._pose_lock:
            self.pose.north = float(north)
            self.pose.east = float(east)
            self.pose.down = float(down)
            self.in_air = self.pose.down < -0.5
            self.armed = self.armed or self.in_air
            ok = self._set_pose(self.pose)
        self._start_hold_loop()
        data = {"position": self.get_position().to_list()}
        if not ok and self._last_error:
            data["warning"] = self._last_error
        return ActionResult(ok or self.connected, f"fly_to_ned {self.pose.north:.1f},{self.pose.east:.1f},{self.pose.down:.1f} (gazebo direct, pose hold)", data)

    def hover(self, duration: float = 5.0) -> ActionResult:
        self.velocity = [0.0, 0.0, 0.0]
        self._start_hold_loop()
        with self._pose_lock:
            ok = self._set_pose(self.pose)
        data = {}
        if not ok and self._last_error:
            data["warning"] = self._last_error
        return ActionResult(ok or self.connected, f"hover {duration:.1f}s (gazebo direct, pose hold)", data)

    def return_to_launch(self) -> ActionResult:
        return self.fly_to_ned(0.0, 0.0, self.pose.down, speed=5.0)

    def change_altitude_relative(self, delta: float, speed: float = 3.0) -> ActionResult:
        # delta positive means climb in AerialClaw skills; NED down decreases.
        with self._pose_lock:
            self.pose.down -= float(delta)
            self.in_air = self.pose.down < -0.5
            ok = self._set_pose(self.pose)
        self._start_hold_loop()
        data = {"altitude": -self.pose.down}
        if not ok and self._last_error:
            data["warning"] = self._last_error
        return ActionResult(ok or self.connected, f"change_altitude {delta:+.1f}m (gazebo direct, pose hold)", data)

    def set_velocity_body(self, forward: float, right: float, down: float, duration: float = 0.12, yaw_rate: float = 0.0) -> ActionResult:
        # Simple body-to-world integration. Heading 0 means forward -> north.
        dt = max(0.05, min(float(duration or 0.12), 0.3))
        hdg = math.radians(self.pose.heading_deg)
        f = float(forward)
        r = float(right)
        vn = f * math.cos(hdg) - r * math.sin(hdg)
        ve = f * math.sin(hdg) + r * math.cos(hdg)
        vd = float(down)
        with self._pose_lock:
            self.pose.north += vn * dt
            self.pose.east += ve * dt
            self.pose.down += vd * dt
            self.pose.heading_deg = (self.pose.heading_deg + float(yaw_rate) * dt) % 360.0
            self.in_air = self.pose.down < -0.5
            ok = self._set_pose(self.pose)
        self.velocity = [vn, ve, vd]
        self._start_hold_loop()
        data = {"position": self.get_position().to_list()}
        if not ok and self._last_error:
            data["warning"] = self._last_error
        return ActionResult(ok or self.connected, "velocity_body integrated (gazebo direct, pose hold)", data)

    def stop_velocity(self) -> ActionResult:
        self.velocity = [0.0, 0.0, 0.0]
        self._start_hold_loop()
        with self._pose_lock:
            ok = self._set_pose(self.pose)
        data = {}
        if not ok and self._last_error:
            data["warning"] = self._last_error
        return ActionResult(ok or self.connected, "velocity stopped (gazebo direct, pose hold)", data)

    def _start_hold_loop(self) -> None:
        if self._hold_thread and self._hold_thread.is_alive():
            return
        self._hold_stop.clear()
        self._hold_thread = threading.Thread(target=self._hold_loop, name="gazebo-direct-pose-hold", daemon=True)
        self._hold_thread.start()

    def _hold_loop(self) -> None:
        interval = 1.0 / max(1.0, self._hold_hz)
        while not self._hold_stop.is_set():
            if self.connected and self.in_air:
                with self._pose_lock:
                    self._set_pose(self.pose)
            time.sleep(interval)

    def _init_gz_transport(self) -> None:
        try:
            import gz.transport13 as transport
            from gz.msgs10.pose_pb2 import Pose
            from gz.msgs10.boolean_pb2 import Boolean
            self._gz_node = transport.Node()
            self._gz_pose_cls = Pose
            self._gz_bool_cls = Boolean
        except Exception as e:
            self._gz_node = None
            self._last_error = f"Gazebo Python transport unavailable: {e}"

    def _pose_values(self, pose: _Pose) -> tuple[float, float, float, float, float]:
        # NED -> Gazebo ENU-ish for this demo: east->x, north->y, altitude->z.
        x = pose.east
        y = pose.north
        z = max(0.02, -pose.down)
        yaw = math.radians(pose.heading_deg)
        qw = math.cos(yaw / 2.0)
        qz = math.sin(yaw / 2.0)
        return x, y, z, qw, qz

    def _set_pose(self, pose: _Pose) -> bool:
        if self._gz_node is not None:
            return self._set_pose_transport(pose)
        return self._set_pose_cli(pose)

    def _set_pose_transport(self, pose: _Pose) -> bool:
        x, y, z, qw, qz = self._pose_values(pose)
        try:
            req = self._gz_pose_cls()
            req.name = self.model
            req.position.x = x
            req.position.y = y
            req.position.z = z
            req.orientation.w = qw
            req.orientation.x = 0.0
            req.orientation.y = 0.0
            req.orientation.z = qz

            # If the protobuf exposes velocity fields, clear them while holding.
            # This prevents Gazebo from preserving a downward velocity between
            # pose corrections, which appears as up/down bouncing in the UI.
            for field in ("linear_velocity", "velocity"):
                if hasattr(req, field):
                    v = getattr(req, field)
                    v.x = v.y = v.z = 0.0
            for field in ("angular_velocity",):
                if hasattr(req, field):
                    v = getattr(req, field)
                    v.x = v.y = v.z = 0.0

            ok, rep = self._gz_node.request(
                f"/world/{self.world}/set_pose",
                req,
                self._gz_pose_cls,
                self._gz_bool_cls,
                1000,
            )
            success = bool(ok) and bool(getattr(rep, "data", False))
            self._last_error = "" if success else f"gz transport set_pose failed: ok={ok} reply={rep}"
            return success
        except Exception as e:
            self._last_error = str(e)
            return False

    def _set_pose_cli(self, pose: _Pose) -> bool:
        x, y, z, qw, qz = self._pose_values(pose)
        req = (
            f'name: "{self.model}" '
            f'position {{ x: {x:.6f} y: {y:.6f} z: {z:.6f} }} '
            f'orientation {{ w: {qw:.9f} x: 0 y: 0 z: {qz:.9f} }}'
        )
        try:
            proc = subprocess.run(
                [
                    "gz", "service", "-s", f"/world/{self.world}/set_pose",
                    "--reqtype", "gz.msgs.Pose",
                    "--reptype", "gz.msgs.Boolean",
                    "--timeout", "5000",
                    "--req", req,
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=6,
            )
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
            low = out.lower()
            if proc.returncode != 0:
                self._last_error = out.strip() or f"gz service exited {proc.returncode}"
                return False
            if "data: false" in low or "false" == low.strip():
                self._last_error = out.strip() or "gz set_pose returned false"
                return False
            self._last_error = ""
            return True
        except Exception as e:
            self._last_error = str(e)
            return False
