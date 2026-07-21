"""Shadow Controller for SO-ARM101.

Sends desired joint angles to the Device Shadow via the AWS IoT Data Plane API.
Uses IAM credentials (boto3) — does NOT require device certificates.

Usage:
    python operator/shadow_controller.py --joint base=45
    python operator/shadow_controller.py --joint base=30 shoulder=-15 elbow=45
    python operator/shadow_controller.py --get
    python operator/shadow_controller.py --region us-east-1 --joint base=45
"""

import argparse
import json
import os
import sys

import boto3


THING_NAME = "soarm101"
DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-2")

VALID_JOINTS = {"base", "shoulder", "elbow", "wrist_flex", "wrist_rotate", "gripper"}


def parse_joint_pair(pair: str) -> tuple[str, float]:
    """Parse a 'name=angle' string into (name, angle). Exits on invalid input."""
    if "=" not in pair:
        print(f"[ERROR] Invalid format: '{pair}'. Expected name=angle (e.g., base=45)")
        sys.exit(1)

    name, _, value = pair.partition("=")
    name = name.strip()
    value = value.strip()

    if name not in VALID_JOINTS:
        print(f"[ERROR] Unknown joint: '{name}'. Valid joints: {', '.join(sorted(VALID_JOINTS))}")
        sys.exit(1)

    try:
        angle = float(value)
    except ValueError:
        print(f"[ERROR] Invalid angle: '{value}'. Must be a number.")
        sys.exit(1)

    return name, angle


def update_shadow(desired_state: dict, region: str):
    """Update the device shadow's desired state via IoT Data Plane API."""
    client = boto3.client("iot-data", region_name=region)

    shadow_doc = {"state": {"desired": desired_state}}
    payload = json.dumps(shadow_doc)

    client.update_thing_shadow(
        thingName=THING_NAME,
        payload=payload,
    )
    print(f"[INFO] Shadow updated with desired state: {desired_state}")


def get_shadow(region: str):
    """Retrieve the current device shadow state."""
    client = boto3.client("iot-data", region_name=region)

    response = client.get_thing_shadow(thingName=THING_NAME)
    shadow = json.loads(response["payload"].read())
    return shadow


def main():
    joints_list = ", ".join(sorted(VALID_JOINTS))
    parser = argparse.ArgumentParser(
        description="SO-ARM101 Shadow Controller (IAM-based)",
        epilog=f"Valid joints:\n"
               f"  {joints_list}\n"
               f"\n"
               f"Examples:\n"
               f"  %(prog)s --joint base=45\n"
               f"  %(prog)s --joint base=30 shoulder=-15 elbow=45\n"
               f"  %(prog)s --get",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--region",
        default=DEFAULT_REGION,
        help=f"AWS region (default: {DEFAULT_REGION})",
    )
    parser.add_argument(
        "--joint",
        nargs="+",
        metavar="NAME=ANGLE",
        help="One or more joint targets (e.g., base=45 shoulder=-15)",
    )
    parser.add_argument("--get", action="store_true", help="Get current shadow state")
    args = parser.parse_args()

    if args.get:
        shadow = get_shadow(args.region)
        print(json.dumps(shadow, indent=2))
        return

    if not args.joint:
        parser.error("Provide --joint NAME=ANGLE or --get")

    # Build desired state from name=angle pairs
    desired = {}
    for pair in args.joint:
        name, angle = parse_joint_pair(pair)
        desired[name] = angle

    update_shadow(desired, args.region)
    print("[INFO] Done.")


if __name__ == "__main__":
    main()
