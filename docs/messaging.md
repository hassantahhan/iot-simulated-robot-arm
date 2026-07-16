# Messaging and Data Flow

This document explains how the SO-ARM101 simulator communicates with AWS IoT Core over MQTT. It covers the topics used, the shape of each message, and how the different parts of the system interact.

## How the simulator talks to the cloud

The simulator connects to AWS IoT Core using MQTT with mutual TLS authentication (device certificates). Once connected, it does two things on a loop every second:

1. Publishes **telemetry** — a rich set of sensor readings for each joint (position, velocity, torque, temperature).
2. Publishes the **shadow reported state** — a simple summary of where each joint currently is, used for the command-and-control flow.

It also subscribes to **shadow delta** messages, which tell it when an operator has requested the arm to move somewhere new.

## The three topics

### Telemetry: `robot-arm/soarm101/telemetry`

This is a custom topic that the project defines. AWS IoT Core doesn't treat it specially — it's just a data stream that gets routed by the IoT Rules Engine to wherever you configure (CloudWatch Logs in our case).

The simulator publishes here once per second. The payload contains the full sensor state of all six joints, using the URDF joint names and values in radians. This is the raw engineering data intended for dashboards, analytics, anomaly detection, and historical storage.

MQTT message example:

```json
{
  "timestamp": 1752789600.123,
  "device_id": "soarm101-simulator",
  "joints": {
    "shoulder_pan": {
      "position": 0.524,
      "velocity": 0.031,
      "torque": 0.1027,
      "temperature": 25.12
    },
    "shoulder_lift": {
      "position": -0.262,
      "velocity": -0.015,
      "torque": 0.0983,
      "temperature": 25.08
    },
    "elbow_flex": {
      "position": 0.0,
      "velocity": 0.0,
      "torque": 0.0912,
      "temperature": 25.03
    },
    "wrist_flex": {
      "position": 0.785,
      "velocity": 0.042,
      "torque": 0.1134,
      "temperature": 25.19
    },
    "wrist_roll": {
      "position": 0.0,
      "velocity": 0.0,
      "torque": 0.0876,
      "temperature": 25.01
    },
    "gripper": {
      "position": 0.35,
      "velocity": 0.008,
      "torque": 0.0945,
      "temperature": 25.05
    }
  }
}
```

Each joint includes:

- **position** — the current angle in radians.
- **velocity** — how fast the joint is moving, in radians per second. Derived from the change in position over time.
- **torque** — a simulated approximation of how hard the motor is working. In a real servo this would correlate with current draw.
- **temperature** — the simulated motor temperature in degrees Celsius. It rises under sustained load and slowly cools back toward 25°C ambient.

### Shadow update: `$aws/things/soarm101/shadow/update`

This is a reserved AWS topic (the `$aws/` prefix means IoT Core intercepts and processes these messages internally). Two different actors publish to this topic with different payloads.

**The simulator** publishes the reported state every second, telling IoT Core where the arm actually is right now. It uses friendly joint names (like "base" and "shoulder") and values in degrees, because this is the interface operators interact with.

```json
{
  "state": {
    "reported": {
      "base": 30.0,
      "shoulder": -15.0,
      "elbow": 0.0,
      "wrist_flex": 45.0,
      "wrist_rotate": 0.0,
      "gripper": 20.0
    }
  }
}
```

**The operator** (using `shadow_controller.py`) publishes the desired state when they want the arm to move. You only need to include the joints you want to change:

```json
{
  "state": {
    "desired": {
      "base": 45,
      "elbow": -30
    }
  }
}
```

IoT Core merges both into a single shadow document and keeps track of whether the device has caught up to what the operator asked for.

### Shadow delta: `$aws/things/soarm101/shadow/update/delta`

This is also a reserved AWS topic, but nobody in this project publishes to it. IoT Core generates delta messages automatically whenever the desired state doesn't match the reported state.

The simulator subscribes to this topic. When a delta arrives, it means "the operator asked you to move and you haven't done it yet." The payload contains only the joints that need to change:

```json
{
  "version": 12,
  "state": {
    "base": 45,
    "elbow": -30
  }
}
```

Once the simulator moves to the requested position and reports it back, the desired and reported states match, and IoT Core stops sending deltas. The system is at rest.

## The full command cycle

Here's what happens end-to-end when an operator tells the arm to move:

1. The operator runs `shadow_controller.py --joint base --angle 45`. This calls the IoT Data Plane API (over HTTPS, not MQTT) to write the desired state into the shadow document.

2. IoT Core sees that the shadow's desired state (`base: 45`) doesn't match the reported state (`base: 0`). It publishes a delta message to the delta topic.

3. The simulator receives the delta over its MQTT subscription. It converts 45 degrees to radians and moves the joint slider in the 3D visualization.

4. On the next telemetry cycle (within one second), the simulator publishes the updated reported state (`base: 45.0`) to the shadow. IoT Core sees that desired now matches reported, and the delta clears.

5. Meanwhile, the full telemetry payload (with all sensor readings) is also published to the telemetry topic and routed to CloudWatch for monitoring.

This pattern means the arm can be offline when the operator sends a command. The desired state persists in the shadow. When the arm reconnects, it receives the delta and catches up automatically.

## Why two different naming schemes

The project uses two sets of joint names and two units for angles. This is intentional.

**Telemetry** uses URDF joint names (`shoulder_pan`, `shoulder_lift`, `elbow_flex`, etc.) and radians. These are the canonical names from the robot's physical model definition. Data pipelines, kinematics libraries, and ML models all work with these names and units natively. Translating would add friction for every downstream consumer.

**Shadow** uses friendly names (`base`, `shoulder`, `elbow`, etc.) and degrees. An operator doesn't need to know the URDF naming conventions — they think "rotate the base 45 degrees." Degrees are intuitive for humans.

The mapping between the two lives in `device_config.py`:

- `base` maps to `shoulder_pan`
- `shoulder` maps to `shoulder_lift`
- `elbow` maps to `elbow_flex`
- `wrist_flex` maps to `wrist_flex`
- `wrist_rotate` maps to `wrist_roll`
- `gripper` maps to `gripper`

The conversion (both names and units) happens inside `robot_arm_simulator.py`, at the boundary between the internal simulation state and the shadow interface.

## Why telemetry and shadow are separate

They serve different purposes with different consumers:

**Telemetry** is a continuous data stream — a firehose of sensor readings published every second regardless of whether anything is happening. It's append-only historical data. Dashboards, alerting, and analytics consume it. You'd never delete or overwrite a telemetry record.

**Shadow** is a single-value state document — it always reflects "right now." It gets overwritten every cycle. Its job is to enable command-and-control: letting an operator say "go here" and letting the device confirm "I'm there." It doesn't store history and it doesn't carry sensor richness like torque or temperature.

You could collapse them into one message, but then either your shadow gets bloated with data IoT Core doesn't need for state comparison, or your analytics pipeline loses the detailed sensor readings it cares about.
