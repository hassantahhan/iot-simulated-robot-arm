"""SO-ARM101 6-DOF Robot Arm Simulator.

Launches a Viser-based 3D visualization of the SO-ARM101 arm in your browser.
Moving the joint sliders publishes telemetry to AWS IoT Core over MQTT.

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
    TOPIC_SHADOW_DELTA,
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
        self._mqtt_connection = None
        self._enricher: SimulatedSignals | None = None
        self._running = False
        self._applied_desired: dict[str, float] = {}  # tracks already-applied shadow commands

    def _connect_iot(self):
        """Establish MQTT connection to AWS IoT Core."""
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

            # Subscribe to shadow delta for receiving desired state
            self._mqtt_connection.subscribe(
                topic=TOPIC_SHADOW_DELTA,
                qos=mqtt.QoS.AT_LEAST_ONCE,
                callback=self._on_shadow_delta,
            )
            print(f"[INFO] Subscribed to: {TOPIC_SHADOW_DELTA}")
        except Exception as e:
            print(f"[WARN] IoT connection failed: {e}")
            print("[WARN] Running in visualization-only mode.")
            self._mqtt_connection = None

    def _on_shadow_delta(self, topic, payload, **kwargs):
        """Handle incoming shadow delta — move arm to desired state.
        
        Only applies each desired value ONCE. After applying, the reported
        state will match desired, clearing the delta on the next report cycle.
        """
        try:
            delta = json.loads(payload)
            desired_joints = delta.get("state", {})
            version = delta.get("version", 0)

            for friendly_name, angle in desired_joints.items():
                # Skip if we already applied this exact desired value
                last = self._applied_desired.get(friendly_name)
                if last == angle:
                    continue

                # Map friendly name to URDF joint name
                urdf_name = FRIENDLY_TO_URDF.get(friendly_name, friendly_name)
                if urdf_name in self._joint_names:
                    idx = self._joint_names.index(urdf_name)
                    angle_rad = float(angle) * (np.pi / 180.0)
                    self._slider_handles[idx].value = angle_rad
                    self._applied_desired[friendly_name] = angle
                    print(f"[SHADOW] Moving {friendly_name} ({urdf_name}) to {angle}° [v{version}]")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[ERROR] Bad shadow delta: {e}")

    def _publish_telemetry(self, telemetry: dict):
        """Publish telemetry to IoT Core."""
        if self._mqtt_connection is None:
            return

        payload = json.dumps(telemetry)
        self._mqtt_connection.publish(
            topic=TOPIC_TELEMETRY,
            payload=payload,
            qos=mqtt.QoS.AT_LEAST_ONCE,
        )

    def _publish_shadow_reported(self):
        """Report current joint positions to Device Shadow using friendly names (degrees)."""
        if self._mqtt_connection is None:
            return

        # Convert URDF joint positions (radians) to friendly names in degrees
        reported = {}
        for urdf_name, position_rad in self._joint_positions.items():
            friendly = URDF_TO_FRIENDLY.get(urdf_name, urdf_name)
            reported[friendly] = round(position_rad * (180.0 / np.pi), 3)

        shadow_doc = {
            "state": {
                "reported": reported
            }
        }
        self._mqtt_connection.publish(
            topic=TOPIC_SHADOW_UPDATE,
            payload=json.dumps(shadow_doc),
            qos=mqtt.QoS.AT_LEAST_ONCE,
        )

    def _telemetry_loop(self):
        """Background thread that publishes telemetry at fixed interval."""
        while self._running:
            if self._enricher and self._joint_positions:
                telemetry = self._enricher.generate(self._joint_positions)
                self._publish_telemetry(telemetry)
                self._publish_shadow_reported()
                print(f"[TELEMETRY] {json.dumps(telemetry, indent=None)[:120]}...")
            time.sleep(PUBLISH_INTERVAL_SEC)

    def run(self):
        """Start the Viser server and telemetry loop."""
        print("[INFO] Starting SO-ARM101 simulator...")
        print(f"[INFO] Open browser at http://localhost:{VISER_PORT}")

        # Start Viser server
        server = viser.ViserServer(host=VISER_HOST, port=VISER_PORT)

        # Load SO-ARM101 URDF from local files
        if os.path.exists(URDF_PATH):
            print(f"[INFO] Loading SO-ARM101 URDF from: {URDF_PATH}")
            urdf = yourdfpy.URDF.load(URDF_PATH)
            viser_urdf = ViserUrdf(server, urdf_or_path=urdf)
        else:
            print(f"[ERROR] URDF not found at: {URDF_PATH}")
            print("[ERROR] Run 'python setup/setup_urdf.py' first to download the model.")
            return

        # Create joint sliders
        self._joint_names = list(viser_urdf.get_actuated_joint_limits().keys())
        self._enricher = SimulatedSignals(self._joint_names)

        with server.gui.add_folder("Joint Controls"):
            for joint_name, (lower, upper) in viser_urdf.get_actuated_joint_limits().items():
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

                # Update callback — move URDF and track position
                def make_callback(jname, slider_list, vurdf):
                    def cb(_):
                        config = np.array([s.value for s in slider_list])
                        vurdf.update_cfg(config)
                        self._joint_positions[jname] = _.target.value
                    return cb

                slider.on_update(make_callback(joint_name, self._slider_handles, viser_urdf))

        # Set initial configuration
        initial_config = np.array([s.value for s in self._slider_handles])
        viser_urdf.update_cfg(initial_config)

        # Add reset button
        reset_btn = server.gui.add_button("Reset Joints")

        @reset_btn.on_click
        def _(_):
            for s in self._slider_handles:
                s.value = 0.0

        # Add grid for visual reference
        server.scene.add_grid("/grid", width=2, height=2, position=(0, 0, 0))

        # Connect to IoT Core
        self._connect_iot()

        # Start telemetry background thread
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
