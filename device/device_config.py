"""Configuration for the SO-ARM101 simulated device."""

import os

_DIR = os.path.dirname(os.path.abspath(__file__))


# ─── Device Identity ───────────────────────────────────────────────────────────

THING_NAME = "soarm101"


# ─── MQTT Broker (AWS IoT Core) ────────────────────────────────────────────────

MQTT_ENDPOINT = os.environ.get("MQTT_ENDPOINT", "YOUR_ENDPOINT.iot.REGION.amazonaws.com")
MQTT_CLIENT_ID = f"{THING_NAME}-simulator"
MQTT_CERT_FILE = os.path.join(_DIR, "certs", "device.pem.crt")
MQTT_KEY_FILE = os.path.join(_DIR, "certs", "private.pem.key")
MQTT_ROOT_CA_FILE = os.path.join(_DIR, "certs", "AmazonRootCA1.pem")


# ─── MQTT Topics ───────────────────────────────────────────────────────────────

TOPIC_TELEMETRY = f"robot-arm/{THING_NAME}/telemetry"
TOPIC_SHADOW_UPDATE = f"$aws/things/{THING_NAME}/shadow/update"
TOPIC_SHADOW_DELTA = f"$aws/things/{THING_NAME}/shadow/update/delta"


# ─── Telemetry ─────────────────────────────────────────────────────────────────

PUBLISH_INTERVAL_SEC = 1.0


# ─── Joint Mapping ─────────────────────────────────────────────────────────────
# Maps operator-facing names (used in shadow & telemetry) to URDF joint names.

FRIENDLY_TO_URDF = {
    "base": "shoulder_pan",
    "shoulder": "shoulder_lift",
    "elbow": "elbow_flex",
    "wrist_flex": "wrist_flex",
    "wrist_rotate": "wrist_roll",
    "gripper": "gripper",
}

URDF_TO_FRIENDLY = {v: k for k, v in FRIENDLY_TO_URDF.items()}


# ─── Joint Limits (degrees) ───────────────────────────────────────────────────

JOINT_LIMITS = {
    "base": {"min": -180.0, "max": 180.0, "initial": 0.0},
    "shoulder": {"min": -90.0, "max": 90.0, "initial": 0.0},
    "elbow": {"min": -90.0, "max": 90.0, "initial": 0.0},
    "wrist_flex": {"min": -90.0, "max": 90.0, "initial": 0.0},
    "wrist_rotate": {"min": -180.0, "max": 180.0, "initial": 0.0},
    "gripper": {"min": 0.0, "max": 60.0, "initial": 0.0},
}


# ─── Visualizer (Viser) ───────────────────────────────────────────────────────

VISER_HOST = "127.0.0.1"
VISER_PORT = 8099
