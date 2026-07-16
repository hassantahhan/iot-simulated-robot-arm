"""Shadow Controller for SO-ARM101.

Sends desired joint angles to the Device Shadow via the AWS IoT Data Plane API.
Uses IAM credentials (boto3) — does NOT require device certificates.

Usage:
    python operator/shadow_controller.py --joint base --angle 45
    python operator/shadow_controller.py --pose '{"base": 30, "shoulder": -15, "elbow": 45}'
"""

import argparse
import json

import boto3


THING_NAME = "soarm101"
REGION = "ap-southeast-2"


def update_shadow(desired_state: dict):
    """Update the device shadow's desired state via IoT Data Plane API."""
    client = boto3.client("iot-data", region_name=REGION)

    shadow_doc = {"state": {"desired": desired_state}}
    payload = json.dumps(shadow_doc)

    client.update_thing_shadow(
        thingName=THING_NAME,
        payload=payload,
    )
    print(f"[INFO] Shadow updated with desired state: {desired_state}")


def get_shadow():
    """Retrieve the current device shadow state."""
    client = boto3.client("iot-data", region_name=REGION)

    response = client.get_thing_shadow(thingName=THING_NAME)
    shadow = json.loads(response["payload"].read())
    return shadow


def main():
    parser = argparse.ArgumentParser(description="SO-ARM101 Shadow Controller (IAM-based)")
    parser.add_argument("--joint", type=str, help="Joint name to move (e.g., base, shoulder)")
    parser.add_argument("--angle", type=float, help="Target angle in degrees")
    parser.add_argument("--pose", type=str, help='Full pose as JSON (e.g., \'{"base": 30, "elbow": 45}\')')
    parser.add_argument("--get", action="store_true", help="Get current shadow state instead of updating")
    args = parser.parse_args()

    if args.get:
        shadow = get_shadow()
        print(json.dumps(shadow, indent=2))
        return

    if not args.joint and not args.pose:
        parser.error("Provide either --joint/--angle, --pose, or --get")

    # Build desired state
    if args.pose:
        desired = json.loads(args.pose)
    else:
        if args.angle is None:
            parser.error("--angle is required when using --joint")
        desired = {args.joint: args.angle}

    update_shadow(desired)
    print("[INFO] Done.")


if __name__ == "__main__":
    main()
