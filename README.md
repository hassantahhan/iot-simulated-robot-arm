# IoT Simulated Robot Arm (SO-ARM101)

A simulated **SO-ARM101** robot arm visualized with **Viser** (browser-based 3D) and connected to **AWS IoT Core**. Move the arm interactively in your browser — every joint change generates IoT telemetry flowing through Device Shadow, Rules Engine, and CloudWatch.

## Architecture Overview

```
+-------------------------+    report state    +-------------------+
|  Viser (Browser UI)     |  report telemetry  |   AWS IoT Core    |
|    SO-ARM101 URDF       |------------------->|                   |
| interactive sliders     |<-------------------|   MQTT Broker     |
+-------------------------+    shadow delta    +----+----------+---+
                                                    |          |
                                                    |          |
+-------------------------+            +------------v---+   +--v---------------+
|  Operator CLI (boto3)   |  update    | Device Shadow  |   |   Rules Engine   |
|                         |  desired   |                |   |                  |
| shadow_controller.py    |----------->| desired/       |   | Route telemetry  |
|                         |            | reported state |   | to CloudWatch    |
+-------------------------+            +----------------+   +---------+--------+
                                                                      |
                                                           +----------v----------+
                                                           | CloudWatch          |
                                                           | Dashboard, Logs,    |
                                                           | Metrics & Alarms    |
                                                           +---------------------+
``` 

## Tech Stack

| Technology | Role |
|------------|------|
| **Python 3.9+** | Device simulator and control scripts |
| **Viser** | Browser-based 3D visualization with interactive joint sliders |
| **SO-ARM101 URDF** | 6-DOF robot arm model (downloaded from TheRobotStudio GitHub) |
| **AWS IoT Core** | MQTT broker for device communication |
| **Device Shadow** | Synchronize desired vs. reported arm state |
| **IoT Rules Engine** | Route telemetry to CloudWatch Logs |
| **Amazon CloudWatch** | Dashboard, log-based telemetry queries, metric filters, and alarms |
| **AWS CloudFormation** | Infrastructure as code |
| **AWS IAM** | Roles and policies for service permissions |

## Values Demonstrated

- **Operational visibility** — A centralized dashboard gives operators real-time insight into arm position, velocity, and health without physical access.
- **Remote control** — Device Shadow enables operators to send target poses from anywhere; the arm receives and executes them even if it was temporarily offline, with automatic state reconciliation on reconnect.
- **Predictive maintenance** — CloudWatch alarms detect abnormal joint temperatures or positions early, reducing unplanned downtime.
- **Secure IoT identity** — The device authenticates with unique X.509 certificates and TLS mutual authentication, ensuring only authorized arms connect to the cloud backend.
- **Sim-to-real ready** — Swap Viser for a real SO-ARM101 and the IoT pipeline stays identical. Same MQTT topics, same shadow schema, same dashboards.

## Project Structure

```
iot-simulated-robot-arm/
├── README.md
├── requirements.txt
├── docs/                                # Project documentation
│   ├── setup.md                         #   Prerequisites, setup steps
│   └── messaging.md                     #   MQTT topics, message formats, data flow
├── setup/                               # One-time provisioning (run once)
│   ├── cfn-template.yaml                #   CloudFormation (IoT, Rules, CloudWatch)
│   ├── setup_certs.py                   #   Creates IoT certificates & configures endpoint
│   └── setup_urdf.py                    #   Downloads SO-ARM101 URDF & meshes from GitHub
├── device/                              # Simulated device runtime (the "robot arm")
│   ├── robot_arm_simulator.py           #   Viser 3D UI + MQTT publish loop
│   ├── readings_enricher.py             #   Simulated signals (velocity, torque, temp)
│   ├── device_config.py                 #   MQTT endpoint, cert paths, topics, joint mapping
│   ├── certs/                           #   Device certificates & private key (git-ignored)
│   └── urdf/so101/                      #   Downloaded URDF + STL meshes (git-ignored)
└── operator/                            # Remote operator tools (cloud-side, uses IAM/certs)
    ├── shadow_controller.py             #   Send desired joint angles via Device Shadow (MQTT)
    └── query_telemetry.py               #   Query stored telemetry from CloudWatch (boto3)
```

## How It Works

### Step by step

1. **Viser** serves a browser UI at `http://127.0.0.1:8099` (localhost only) with the SO-ARM101 3D model and 6 joint sliders.
2. You **drag any slider** — the arm moves visually and the new joint angles publish to IoT Core over MQTT.
3. **Device Shadow** maintains desired vs. reported state — the shadow controller can set target poses remotely.
4. When the shadow is updated remotely, the **simulator receives the delta via MQTT**, updates the sliders programmatically, and the **browser updates automatically** (no refresh needed).
5. **Rules Engine** forwards all telemetry to CloudWatch Logs (configured via IoT Core, not called directly).
6. **CloudWatch Dashboard** visualizes joint positions, velocity, and temperature with alarms on anomalies.

### Two ways to control the arm

| Method | Protocol | Auth | Use case |
|--------|----------|------|----------|
| **Browser sliders** (Viser) | WebSocket (local) | None — local only | Interactive testing at the machine |
| **Shadow controller** (CLI) | HTTPS (IoT Data Plane API) | IAM credentials | Remote control from anywhere |

### Operator tools (`operator/`)

| Script | Connects to | Auth method | Purpose |
|--------|------------|-------------|---------|
| `shadow_controller.py` | **IoT Data Plane API** | IAM credentials (boto3) | Sends desired joint angles to the arm |
| `query_telemetry.py` | **CloudWatch** | IAM credentials (boto3) | Reads stored telemetry after Rules Engine routes it |

### Device runtime (`device/`)

| Script | Connects to | Auth method | Purpose |
|--------|------------|-------------|---------|
| `robot_arm_simulator.py` | **IoT Core** (MQTT) | Device certificate + private key | Publishes telemetry, receives shadow deltas |

## Documentation

| Document | Description |
|----------|-------------|
| [Setup and Prerequisites](docs/setup.md) | Prerequisites, IAM permissions, and step-by-step setup for Windows and macOS/Linux |
| [Messaging and Data Flow](docs/messaging.md) | How the simulator communicates with AWS IoT Core — topics, message formats, the command cycle, and naming conventions |

This project was built with the help of [Kiro](https://kiro.dev).