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
TOPIC_SHADOW_UPDATE_DELTA = f"$aws/things/{THING_NAME}/shadow/update/delta"
TOPIC_SHADOW_GET = f"$aws/things/{THING_NAME}/shadow/get"
TOPIC_SHADOW_GET_ACCEPTED = f"$aws/things/{THING_NAME}/shadow/get/accepted"
TOPIC_SHADOW_GET_REJECTED = f"$aws/things/{THING_NAME}/shadow/get/rejected"


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


# ─── Visualizer (Viser) ───────────────────────────────────────────────────────

VISER_HOST = "127.0.0.1"
VISER_PORT = 8099
