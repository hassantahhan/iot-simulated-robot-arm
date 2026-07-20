# Messaging and Data Flow

This document explains how the SO-ARM101 simulator communicates with AWS IoT Core over MQTT. It covers the topics used, the shape of each message, and how the different parts of the system interact.

## How the simulator talks to the cloud

The simulator connects to AWS IoT Core using MQTT with mutual TLS authentication (device certificates). Once connected, it does two things on a loop every second:

1. Publishes **telemetry** — a rich set of sensor readings for each joint (position, velocity, torque, temperature).
2. Publishes the **shadow reported state** — a simple summary of where each joint currently is, used for the command-and-control flow.

It also subscribes to **shadow delta** messages, which tell it when an operator has requested the arm to move somewhere new.

On startup, before subscribing to deltas, the simulator retrieves the full shadow document via a **shadow GET** request. This lets it restore the arm to its last known position and apply any commands that were sent while it was offline.

## The topics

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
- **torque** — a simulated approximation of how hard the motor is working. In a real servo motor, this would correlate with current draw.
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

### Shadow get: `$aws/things/soarm101/shadow/get`

Another reserved AWS topic used to retrieve the full shadow document on demand.

IoT Core responds on one of two topics:

- **`$aws/things/soarm101/shadow/get/accepted`** — returns the full shadow document containing both reported and desired state.
- **`$aws/things/soarm101/shadow/get/rejected`** — returned if the shadow doesn't exist yet (e.g., first boot before any state has been set).

The accepted response looks like:

```json
{
  "state": {
    "desired": {
      "base": 45.0
    },
    "reported": {
      "base": 30.0,
      "shoulder": -15.0,
      "elbow": 0.0,
      "wrist_flex": 45.0,
      "wrist_rotate": 0.0,
      "gripper": 20.0
    }
  },
  "version": 42
}
```

The simulator uses this to initialize joint positions from the reported state (where the arm was before shutdown) and to apply any desired values that differ from reported (commands sent while offline).

## The startup sequence

When the simulator starts (or reconnects after being offline), it goes through this sequence before accepting live commands:

1. Connect to IoT Core via MQTT with device certificates.
2. Subscribe to `shadow/get/accepted` and `shadow/get/rejected`.
3. Publish `{}` to `shadow/get` — asking IoT Core for the full shadow document.
4. Receive the response. Initialize joints from the **reported** state (last actual position). Then check for any **desired** values that differ from reported — these are commands sent while the arm was offline — and apply them.
5. Clear all desired keys by publishing them as `null`. This marks them as consumed and prevents stale deltas from firing.
6. Publish the current reported state (so the shadow reflects the arm's actual position).
7. Subscribe to `shadow/update/delta` for live commands.

After this sequence, the arm is at its last known position (or at the position requested by an offline command), and ready to receive new commands via delta.

## The full command cycle

Here's what happens end-to-end when an operator tells the arm to move:

1. The operator runs `shadow_controller.py --joint base --angle 45`. This calls the IoT Data Plane API (over HTTPS, not MQTT) to write the desired state into the shadow document.

2. IoT Core sees that the shadow's desired state (`base: 45`) doesn't match the reported state (`base: 0`). It publishes a delta message to the delta topic.

3. The simulator receives the delta over its MQTT subscription. It converts 45 degrees to radians and moves the joint slider in the 3D visualization.

4. The simulator clears the desired key by publishing it as `null`. This marks the command as consumed — regardless of whether the arm reached the exact target (e.g., joint limits may clamp the position).

5. On the next telemetry cycle (within one second), the simulator publishes the updated reported state (`base: 45.0`) to the shadow.

6. Meanwhile, the full telemetry payload (with all sensor readings) is also published to the telemetry topic and routed to CloudWatch for monitoring.

This pattern means the arm can be offline when the operator sends a command. The desired state persists in the shadow. When the arm reconnects, its startup sequence (described above) retrieves the shadow, sees the pending desired state differs from reported, applies it, and then clears it.

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

## Topic reference

This section lists every MQTT topic relevant to this project — the custom telemetry topic and all native Device Shadow topics that AWS IoT Core provides for a classic (unnamed) shadow. Some are used in this project, others exist in the protocol but aren't needed here.

### Custom topic

| Topic | Direction | When to use |
|-------|-----------|-------------|
| `robot-arm/soarm101/telemetry` | Device → Cloud | Continuous sensor data stream. Publish rich readings (position, velocity, torque, temperature) for dashboards, analytics, and alerting. IoT Core routes it via Rules Engine — it has no built-in meaning. |

### Shadow topics — update family

| Topic | Direction | When to use | Used? |
|-------|-----------|-------------|-------|
| `$aws/things/{thing}/shadow/update` | Device/Operator → IoT Core | Publish reported state (device) or desired state (operator) to modify the shadow document. | Yes |
| `$aws/things/{thing}/shadow/update/accepted` | IoT Core → Device | Subscribe to confirm your update was accepted. Useful for retry logic or audit trails. | No |
| `$aws/things/{thing}/shadow/update/rejected` | IoT Core → Device | Subscribe to detect failed updates (e.g., version conflicts, malformed payloads). Without this you silently drop errors. | No |
| `$aws/things/{thing}/shadow/update/delta` | IoT Core → Device | Subscribe to receive commands. IoT Core auto-publishes here when desired differs from reported. This is how the device learns it needs to move. | Yes |
| `$aws/things/{thing}/shadow/update/documents` | IoT Core → Device | Subscribe to get the full shadow document (previous + current) after every successful update. Useful for debugging or building a local cache of the complete state. | No |

### Shadow topics — get family

| Topic | Direction | When to use | Used? |
|-------|-----------|-------------|-------|
| `$aws/things/{thing}/shadow/get` | Device → IoT Core | Publish `{}` to request the full shadow document on demand. Typically used at startup to restore last known state. | Yes |
| `$aws/things/{thing}/shadow/get/accepted` | IoT Core → Device | Subscribe to receive the full shadow document in response to a get request. Contains both reported and desired state. | Yes |
| `$aws/things/{thing}/shadow/get/rejected` | IoT Core → Device | Subscribe to handle the case where the shadow doesn't exist yet (first boot). Without this, the device would hang waiting for an accepted response that never comes. | Yes |

### Shadow topics — delete family

| Topic | Direction | When to use | Used? |
|-------|-----------|-------------|-------|
| `$aws/things/{thing}/shadow/delete` | Device/Operator → IoT Core | Publish `{}` to completely erase the shadow document. Use for factory reset, decommissioning, or clearing a corrupted shadow. | No |
| `$aws/things/{thing}/shadow/delete/accepted` | IoT Core → Device | Subscribe to confirm the shadow was successfully deleted. | No |
| `$aws/things/{thing}/shadow/delete/rejected` | IoT Core → Device | Subscribe to handle deletion failures (e.g., shadow doesn't exist). | No |

### Why we don't use all of them

This project keeps things simple. The simulator does fire-and-forget on its shadow updates — it publishes reported state every second, so even if one update is rejected, the next one will correct it. Subscribing to `update/accepted` and `update/rejected` would add robustness (retry logic, error alerting) but isn't necessary for a demo. The delete family is an operational tool — you'd use it from the AWS Console or a management script, not from the device's normal runtime loop.