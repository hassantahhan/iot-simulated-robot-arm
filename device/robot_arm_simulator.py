"""SO-ARM101 6-DOF Robot Arm Simulator.

Launches a Viser-based 3D visualization of the SO-ARM101 arm in your browser.
Moving the joint sliders publishes telemetry to AWS IoT Core over MQTT.

Startup behavior:
    1. GET the Device Shadow to retrieve the last known state.
    2. Initialize joints from shadow's desired state (honours offline commands).
       Falls back to reported state if no desired exists.
    3. Clear desired state (marks commands as consumed).
    4. Subscribe to shadow/update/delta for live commands.

Setup:
    1. Run `python device/setup_urdf.py` to download the SO-ARM101 URDF and meshes.
    2. Run `python device/robot_arm_simulator.py` to start the simulator.
"""

import json
import os
import time
import threading
import numpy as np

import viser
from viser.extras import ViserUrdf
import yourdfpy

from device_config import (
    MQTT_ENDPOINT,
    MQTT_CLIENT_ID,
    MQTT_CERT_FILE,
    MQTT_KEY_FILE,
    MQTT_ROOT_CA_FILE,
    TOPIC_TELEMETRY,
    TOPIC_SHADOW_UPDATE,
    TOPIC_SHADOW_UPDATE_DELTA,
    TOPIC_SHADOW_GET,
    TOPIC_SHADOW_GET_ACCEPTED,
    TOPIC_SHADOW_GET_REJECTED,
    PUBLISH_INTERVAL_SEC,
    VISER_HOST,
    VISER_PORT,
    FRIENDLY_TO_URDF,
    URDF_TO_FRIENDLY,
)
from readings_enricher import SimulatedSignals

# Path to locally downloaded SO-ARM101 URDF
URDF_PATH = os.path.join(os.path.dirname(__file__), "urdf", "so101", "so101.urdf")

# Conditional IoT import — allows running visualization without AWS certs
try:
    from awscrt import mqtt
    from awsiot import mqtt_connection_builder

    IOT_AVAILABLE = True
except ImportError:
    IOT_AVAILABLE = False
    print("[WARN] awsiotsdk not installed. Running in visualization-only mode.")


class RobotArmSimulator:
    """Viser-based SO-ARM101 simulator with IoT Core integration."""

    def __init__(self):
        self._joint_positions: dict[str, float] = {}
        self._slider_handles: list = []
        self._joint_names: list[str] = []
        self._viser_urdf = None
        self._mqtt_connection = None
        self._enricher: SimulatedSignals | None = None
        self._running = False
        self._shadow_ready = threading.Event()

    # ─── IoT Connection ────────────────────────────────────────────────────────

    def _connect_iot(self):
        """Connect to IoT Core, restore state from shadow, then subscribe to delta."""
        if not IOT_AVAILABLE:
            return

        try:
            self._mqtt_connection = mqtt_connection_builder.mtls_from_path(
                endpoint=MQTT_ENDPOINT,
                cert_filepath=MQTT_CERT_FILE,
                pri_key_filepath=MQTT_KEY_FILE,
                ca_filepath=MQTT_ROOT_CA_FILE,
                client_id=MQTT_CLIENT_ID,
                clean_session=False,
                keep_alive_secs=30,
            )
            connect_future = self._mqtt_connection.connect()
            connect_future.result(timeout=10)
            print(f"[INFO] Connected to IoT Core: {MQTT_ENDPOINT}")

            # 1. Subscribe to GET response topics
            self._mqtt_connection.subscribe(
                topic=TOPIC_SHADOW_GET_ACCEPTED,
                qos=mqtt.QoS.AT_LEAST_ONCE,
                callback=self._on_shadow_get_accepted,
            )
            self._mqtt_connection.subscribe(
                topic=TOPIC_SHADOW_GET_REJECTED,
                qos=mqtt.QoS.AT_LEAST_ONCE,
                callback=self._on_shadow_get_rejected,
            )

            # 2. Request shadow document
            print("[INFO] Requesting shadow state...")
            self._mqtt_connection.publish(
                topic=TOPIC_SHADOW_GET,
                payload="{}",
                qos=mqtt.QoS.AT_LEAST_ONCE,
            )

            # 3. Wait for response
            if self._shadow_ready.wait(timeout=5.0):
                print("[INFO] Shadow state restored.")
            else:
                print("[WARN] Shadow GET timed out — starting with default positions.")

            # 4. Report current positions (so shadow reported matches reality)
            self._publish_shadow_reported()

            # 5. NOW subscribe to delta for live commands
            self._mqtt_connection.subscribe(
                topic=TOPIC_SHADOW_UPDATE_DELTA,
                qos=mqtt.QoS.AT_LEAST_ONCE,
                callback=self._on_shadow_delta,
            )
            print(f"[INFO] Subscribed to: {TOPIC_SHADOW_UPDATE_DELTA}")

        except Exception as e:
            print(f"[WARN] IoT connection failed: {e}")
            print("[WARN] Running in visualization-only mode.")
            self._mqtt_connection = None

    # ─── Shadow Handlers ───────────────────────────────────────────────────────

    def _on_shadow_get_accepted(self, topic, payload, **kwargs):
        """Restore joints from shadow document.

        Uses reported state as the starting position (where the arm was last).
        Then applies any desired values that differ from reported — those are
        commands sent while the arm was offline.
        Finally clears all desired keys so no stale delta fires.
        """
        try:
            doc = json.loads(payload)
            state = doc.get("state", {})
            reported = state.get("reported", {})
            desired = state.get("desired", {})

            # Restore from reported (last actual position)
            for friendly_name, angle_deg in reported.items():
                self._set_joint_from_friendly(friendly_name, float(angle_deg))

            # Apply offline commands: desired keys that differ from reported
            for friendly_name, angle_deg in desired.items():
                rep = reported.get(friendly_name)
                if rep is None or abs(float(angle_deg) - float(rep)) > 0.5:
                    self._set_joint_from_friendly(friendly_name, float(angle_deg))
                    print(f"[SHADOW] Offline command applied: {friendly_name} → {angle_deg}°")

            # Update 3D visualization
            self._update_urdf_visual()

            # Clear all desired — consumed. Prevents stale delta after subscribe.
            if desired and self._mqtt_connection:
                self._mqtt_connection.publish(
                    topic=TOPIC_SHADOW_UPDATE,
                    payload=json.dumps({"state": {"desired": {k: None for k in desired}}}),
                    qos=mqtt.QoS.AT_LEAST_ONCE,
                )
                print("[SHADOW] Cleared consumed desired state")

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[ERROR] Failed to parse shadow GET response: {e}")
        finally:
            self._shadow_ready.set()

    def _on_shadow_get_rejected(self, topic, payload, **kwargs):
        """Shadow doesn't exist yet — proceed with defaults."""
        print("[WARN] Shadow GET rejected (shadow may not exist yet)")
        self._shadow_ready.set()

    def _on_shadow_delta(self, topic, payload, **kwargs):
        """Handle live shadow delta — move arm to new desired state, then clear desired."""
        try:
            delta = json.loads(payload)
            desired_joints = delta.get("state", {})
            version = delta.get("version", 0)

            for friendly_name, angle_deg in desired_joints.items():
                if self._set_joint_from_friendly(friendly_name, float(angle_deg)):
                    print(f"[SHADOW] Moving {friendly_name} to {angle_deg}° [v{version}]")

            self._update_urdf_visual()

            # Clear desired — command has been consumed. This ensures the shadow
            # doesn't retain stale desired state if the arm can't fully reach
            # the target (e.g., joint limits clamp the actual position).
            if desired_joints and self._mqtt_connection:
                clear_desired = {k: None for k in desired_joints}
                self._mqtt_connection.publish(
                    topic=TOPIC_SHADOW_UPDATE,
                    payload=json.dumps({"state": {"desired": clear_desired}}),
                    qos=mqtt.QoS.AT_LEAST_ONCE,
                )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[ERROR] Bad shadow delta: {e}")

    # ─── Joint Helpers ─────────────────────────────────────────────────────────

    def _set_joint_from_friendly(self, friendly_name: str, angle_deg: float) -> bool:
        """Set a joint position by friendly name (degrees). Clamps to joint limits.
        Returns True if successful."""
        urdf_name = FRIENDLY_TO_URDF.get(friendly_name)
        if urdf_name is None or urdf_name not in self._joint_names:
            return False

        idx = self._joint_names.index(urdf_name)
        slider = self._slider_handles[idx]
        angle_rad = angle_deg * (np.pi / 180.0)

        # Clamp to joint limits
        clamped_rad = float(np.clip(angle_rad, slider.min, slider.max))
        slider.value = clamped_rad
        self._joint_positions[urdf_name] = clamped_rad
        return True

    def _update_urdf_visual(self):
        """Push current slider values to the 3D URDF visualization."""
        if self._viser_urdf:
            config = np.array([s.value for s in self._slider_handles])
            self._viser_urdf.update_cfg(config)

    # ─── Telemetry ─────────────────────────────────────────────────────────────

    def _publish_telemetry(self, telemetry: dict):
        """Publish telemetry to IoT Core."""
        if self._mqtt_connection is None:
            return

        self._mqtt_connection.publish(
            topic=TOPIC_TELEMETRY,
            payload=json.dumps(telemetry),
            qos=mqtt.QoS.AT_LEAST_ONCE,
        )

    def _publish_shadow_reported(self):
        """Report current joint positions to Device Shadow (friendly names, degrees)."""
        if self._mqtt_connection is None:
            return

        reported = {}
        for urdf_name, position_rad in self._joint_positions.items():
            friendly = URDF_TO_FRIENDLY.get(urdf_name, urdf_name)
            reported[friendly] = round(position_rad * (180.0 / np.pi), 3)

        self._mqtt_connection.publish(
            topic=TOPIC_SHADOW_UPDATE,
            payload=json.dumps({"state": {"reported": reported}}),
            qos=mqtt.QoS.AT_LEAST_ONCE,
        )

    def _telemetry_loop(self):
        """Background thread: publish telemetry + shadow reported at fixed interval."""
        while self._running:
            if self._enricher and self._joint_positions:
                telemetry = self._enricher.generate(self._joint_positions)
                self._publish_telemetry(telemetry)
                self._publish_shadow_reported()
                print(f"[TELEMETRY] {json.dumps(telemetry, indent=None)[:120]}...")
            time.sleep(PUBLISH_INTERVAL_SEC)

    # ─── Main Loop ─────────────────────────────────────────────────────────────

    def run(self):
        """Start the Viser server and telemetry loop."""
        print("[INFO] Starting SO-ARM101 simulator...")
        print(f"[INFO] Open browser at http://localhost:{VISER_PORT}")

        server = viser.ViserServer(host=VISER_HOST, port=VISER_PORT)

        # Load URDF
        if not os.path.exists(URDF_PATH):
            print(f"[ERROR] URDF not found at: {URDF_PATH}")
            print("[ERROR] Run 'python setup/setup_urdf.py' first to download the model.")
            return

        print(f"[INFO] Loading SO-ARM101 URDF from: {URDF_PATH}")
        urdf = yourdfpy.URDF.load(URDF_PATH)
        self._viser_urdf = ViserUrdf(server, urdf_or_path=urdf)

        # Create joint sliders
        self._joint_names = list(self._viser_urdf.get_actuated_joint_limits().keys())
        self._enricher = SimulatedSignals(self._joint_names)

        with server.gui.add_folder("Joint Controls"):
            for joint_name, (lower, upper) in self._viser_urdf.get_actuated_joint_limits().items():
                lower = lower if lower is not None else -np.pi
                upper = upper if upper is not None else np.pi
                initial = 0.0 if lower < -0.1 and upper > 0.1 else (lower + upper) / 2.0

                slider = server.gui.add_slider(
                    label=joint_name,
                    min=lower,
                    max=upper,
                    step=0.01,
                    initial_value=initial,
                )
                self._slider_handles.append(slider)
                self._joint_positions[joint_name] = initial

                def make_callback(jname):
                    def cb(_):
                        self._joint_positions[jname] = _.target.value
                        self._update_urdf_visual()
                    return cb

                slider.on_update(make_callback(joint_name))

        # Set initial visualization
        self._update_urdf_visual()

        # Reset button
        reset_btn = server.gui.add_button("Reset Joints")

        @reset_btn.on_click
        def _(_):
            for s in self._slider_handles:
                s.value = 0.0
            self._update_urdf_visual()

        # Grid
        server.scene.add_grid("/grid", width=2, height=2, position=(0, 0, 0))

        # Connect to IoT Core (restores state from shadow)
        self._connect_iot()

        # Start telemetry
        self._running = True
        telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
        telemetry_thread.start()

        print("[INFO] Simulator running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            self._running = False
            print("\n[INFO] Shutting down...")
            if self._mqtt_connection:
                self._mqtt_connection.disconnect()


if __name__ == "__main__":
    sim = RobotArmSimulator()
    sim.run()
