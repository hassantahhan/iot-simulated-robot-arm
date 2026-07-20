# IoT Simulated Robot Arm (SO-ARM101)

A simulated **SO-ARM101** robot arm visualized with **Viser** (browser-based 3D) and connected to **AWS IoT Core**. Move the arm interactively in your browser — every joint change generates IoT telemetry flowing through Device Shadow, Rules Engine, and CloudWatch.

## Architecture Overview

```
+-------------------------+                    +-------------------+
|  Viser (Browser UI)     |  MQTT telemetry    |   AWS IoT Core    |
|    SO-ARM101 URDF       |------------------->|                   |
| interactive sliders     |<-------------------|   MQTT Broker     |
+-------------------------+ MQTT delta events  +----+----------+---+
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
- **Scalable pattern** — The architecture extends naturally to fleets of devices; add more arms without redesigning the backend.
- **Sim-to-real ready** — Swap Viser for a real SO-ARM101 and the IoT pipeline stays identical. Same MQTT topics, same shadow schema, same dashboards.

## Documentation

| Document | Description |
|----------|-------------|
| [Messaging and Data Flow](docs/messaging.md) | How the simulator communicates with AWS IoT Core — topics, message formats, the command cycle, and naming conventions |

## Project Structure

```
iot-simulated-robot-arm/
├── README.md
├── requirements.txt
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

## Quick Start

### PowerShell (Windows)

```powershell
# 1. Create and activate a Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download the SO-ARM101 URDF and mesh files
python setup/setup_urdf.py

# 4. Deploy infrastructure (creates IoT Thing, Rules, CloudWatch)
aws cloudformation deploy `
  --template-file setup/cfn-template.yaml `
  --stack-name iot-robot-arm `
  --capabilities CAPABILITY_NAMED_IAM `
  --region <your-region>

# 5. Create device certificates and configure endpoint
python setup/setup_certs.py --region <your-region>

# 6. Run the simulator (opens browser at localhost:8099)
python device/robot_arm_simulator.py

# 7. Send commands via shadow controller (open a NEW terminal, activate venv first)
.\.venv\Scripts\Activate.ps1
python operator/shadow_controller.py --joint gripper --angle 60

# 8. Query telemetry from CloudWatch (after simulator has been running)
python operator/query_telemetry.py --minutes 60
```

### Bash (macOS / Linux)

```bash
# 1. Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download the SO-ARM101 URDF and mesh files
python setup/setup_urdf.py

# 4. Deploy infrastructure (creates IoT Thing, Rules, CloudWatch)
aws cloudformation deploy \
  --template-file setup/cfn-template.yaml \
  --stack-name iot-robot-arm \
  --capabilities CAPABILITY_NAMED_IAM \
  --region <your-region>

# 5. Create device certificates and configure endpoint
python setup/setup_certs.py --region <your-region>

# 6. Run the simulator (opens browser at localhost:8099)
python device/robot_arm_simulator.py

# 7. Send commands via shadow controller (open a NEW terminal, activate venv first)
source .venv/bin/activate
python operator/shadow_controller.py --joint gripper --angle 60

# 8. Query telemetry from CloudWatch (after simulator has been running)
python operator/query_telemetry.py --minutes 60
```

## Prerequisites

- AWS Account with appropriate permissions
- AWS CLI v2 installed and configured
- Python 3.9+
- IoT certificates (generated during stack deployment or manually via AWS console)

This project was built with the help of [Kiro](https://kiro.dev).