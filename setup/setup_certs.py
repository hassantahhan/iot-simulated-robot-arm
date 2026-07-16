"""
============================================================
  IoT Certificate Setup for SO-ARM101 Simulator
============================================================

This script automates the creation of IoT device certificates
and wires them to the IoT Thing and Policy created by the
CloudFormation stack.

What it does (step by step):
------------------------------------------------------------
1. Gets your IoT Core endpoint (the MQTT URL your device connects to)
2. Creates a new certificate + private key pair (activated immediately)
3. Downloads Amazon's Root CA (public trust anchor)
4. Attaches the certificate to the IoT Thing ("soarm101")
5. Attaches the certificate to the IoT Policy ("soarm101-policy")
6. Updates device/device_config.py with your real endpoint
7. Saves everything to the certs/ folder

After running:
------------------------------------------------------------
  certs/
  ├── device.pem.crt      <- Public certificate (identifies your device)
  ├── private.pem.key     <- PRIVATE KEY (keep secret, never commit)
  └── AmazonRootCA1.pem   <- Amazon Root CA (public, verifies AWS)

Usage:
------------------------------------------------------------
  python device/setup_certs.py

  Optional: specify region and thing name
  python device/setup_certs.py --region us-east-1 --thing-name myarm

============================================================
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request


# ---------- Configuration ----------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CERTS_DIR = os.path.join(PROJECT_ROOT, "device", "certs")
CONFIG_FILE = os.path.join(PROJECT_ROOT, "device", "device_config.py")
ROOT_CA_URL = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"


# ---------- Helpers ----------

def run_aws(args: list[str], region: str) -> dict:
    """Run an AWS CLI command and return parsed JSON output."""
    cmd = ["aws"] + args + ["--region", region, "--output", "json"]
    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"\n  [ERROR] AWS CLI failed:\n  {result.stderr.strip()}")
        sys.exit(1)
    if result.stdout.strip():
        return json.loads(result.stdout)
    return {}


def save_file(path: str, content: str):
    """Write content to a file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Saved: {os.path.basename(path)}")


# ---------- Main Steps ----------

def main():
    parser = argparse.ArgumentParser(description="Setup IoT certificates for SO-ARM101")
    parser.add_argument("--region", default="ap-southeast-2", help="AWS region")
    parser.add_argument("--thing-name", default="soarm101", help="IoT Thing name")
    parser.add_argument("--policy-name", default="soarm101-policy", help="IoT Policy name")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  IoT Certificate Setup for SO-ARM101")
    print("=" * 60)

    # Create certs directory
    os.makedirs(CERTS_DIR, exist_ok=True)

    # --------------------------------------------------
    # STEP 1: Get IoT MQTT endpoint
    # --------------------------------------------------
    print("\n[1/6] Getting IoT MQTT Core endpoint...")
    endpoint_resp = run_aws(
        ["iot", "describe-endpoint", "--endpoint-type", "iot:Data-ATS"],
        args.region,
    )
    endpoint = endpoint_resp["endpointAddress"]
    print(f"  Endpoint: {endpoint}")

    # --------------------------------------------------
    # STEP 2: Create certificate and keys
    # --------------------------------------------------
    print("\n[2/6] Creating device certificate and private key...")
    cert_resp = run_aws(
        ["iot", "create-keys-and-certificate", "--set-as-active"],
        args.region,
    )
    certificate_arn = cert_resp["certificateArn"]
    certificate_pem = cert_resp["certificatePem"]
    private_key = cert_resp["keyPair"]["PrivateKey"]

    # Save certificate
    cert_path = os.path.join(CERTS_DIR, "device.pem.crt")
    save_file(cert_path, certificate_pem)

    # Save private key
    key_path = os.path.join(CERTS_DIR, "private.pem.key")
    save_file(key_path, private_key)
    print(f"  Certificate ARN: {certificate_arn}")

    # --------------------------------------------------
    # STEP 3: Download Amazon Root CA
    # --------------------------------------------------
    print("\n[3/6] Downloading Amazon Root CA...")
    root_ca_path = os.path.join(CERTS_DIR, "AmazonRootCA1.pem")
    urllib.request.urlretrieve(ROOT_CA_URL, root_ca_path)
    print(f"  Saved: AmazonRootCA1.pem")

    # --------------------------------------------------
    # STEP 4: Attach certificate to Thing
    # --------------------------------------------------
    print(f"\n[4/6] Attaching certificate to Thing '{args.thing_name}'...")
    run_aws(
        ["iot", "attach-thing-principal",
         "--thing-name", args.thing_name,
         "--principal", certificate_arn],
        args.region,
    )
    print("  Done.")

    # --------------------------------------------------
    # STEP 5: Attach certificate to Policy
    # --------------------------------------------------
    print(f"\n[5/6] Attaching certificate to Policy '{args.policy_name}'...")
    run_aws(
        ["iot", "attach-policy",
         "--policy-name", args.policy_name,
         "--target", certificate_arn],
        args.region,
    )
    print("  Done.")

    # --------------------------------------------------
    # STEP 6: Update device_config with endpoint
    # --------------------------------------------------
    print("\n[6/6] Updating device/device_config with endpoint...")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config_content = f.read()

    config_content = config_content.replace(
        'MQTT_ENDPOINT = os.environ.get("MQTT_ENDPOINT", "YOUR_ENDPOINT.iot.REGION.amazonaws.com")',
        f'MQTT_ENDPOINT = os.environ.get("MQTT_ENDPOINT", "{endpoint}")',
    )
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(config_content)
    print(f"  Updated MQTT_ENDPOINT to: {endpoint}")

    # --------------------------------------------------
    # Summary
    # --------------------------------------------------
    print()
    print("=" * 60)
    print("  SETUP COMPLETE")
    print("=" * 60)
    print(f"""
  Files created:
    certs/device.pem.crt     - Device certificate (public)
    certs/private.pem.key    - Private key (SECRET - never share!)
    certs/AmazonRootCA1.pem  - Amazon Root CA (public)

  Configuration updated:
    device/device_config     - IoT MQTT endpoint set to {endpoint}

  Next step:
    python device/robot_arm_simulator.py
""")


if __name__ == "__main__":
    main()
