# Getting Started

## Prerequisites

- Python 3.9+
- AWS CLI v2 installed and configured
- AWS Account with appropriate permissions (see [IAM Permissions Required](#iam-permissions-required) below)

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
python operator/shadow_controller.py --joint base=180 shoulder=-45 elbow=-60 wrist_flex=-70 wrist_rotate=0 gripper=30

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
python operator/shadow_controller.py --joint base=180 shoulder=-45 elbow=-60 wrist_flex=-70 wrist_rotate=0 gripper=30

# 8. Query telemetry from CloudWatch (after simulator has been running)
python operator/query_telemetry.py --minutes 60
```

## IAM Permissions Required

The **device** authenticates with X.509 certificates — it does not need IAM credentials. The IoT Policy (`soarm101-policy`, created by CloudFormation) grants it MQTT access.

The setup and **operator** scripts use IAM credentials. The IAM principal running these scripts needs the following permissions:

### CloudFormation deployment

| Action | Resource |
|--------|----------|
| `cloudformation:*` | The stack |
| `iot:*` | Thing, Policy, TopicRule resources |
| `iam:CreateRole`, `iam:PutRolePolicy`, `iam:PassRole` | The Rules Engine role |
| `logs:CreateLogGroup`, `logs:PutMetricFilter` | Telemetry log group |
| `cloudwatch:PutDashboard`, `cloudwatch:PutMetricAlarm` | Dashboard and alarm |

### setup_certs.py (one-time setup)

| Action | Resource |
|--------|----------|
| `iot:DescribeEndpoint` | `*` |
| `iot:CreateKeysAndCertificate` | `*` |
| `iot:AttachThingPrincipal` | `arn:aws:iot:<region>:<account-id>:thing/*` |
| `iot:AttachPolicy` | `arn:aws:iot:<region>:<account-id>:cert/*` |

### shadow_controller.py

| Action | Resource |
|--------|----------|
| `iot:UpdateThingShadow` | `arn:aws:iot:<region>:<account-id>:thing/*` |
| `iot:GetThingShadow` | `arn:aws:iot:<region>:<account-id>:thing/*` |

### query_telemetry.py

| Action | Resource |
|--------|----------|
| `logs:StartQuery` | `*` |
| `logs:GetQueryResults` | `*` |

These permissions are not provisioned by the CloudFormation stack. They depend on your AWS account's existing IAM users or roles.
