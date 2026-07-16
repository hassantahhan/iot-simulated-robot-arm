"""Query CloudWatch Logs for SO-ARM101 telemetry data.

Fetches recent telemetry from CloudWatch Logs Insights and displays it.

Usage:
    python dashboard/query_telemetry.py
    python dashboard/query_telemetry.py --minutes 30
"""

import argparse
import json
import time

import boto3


LOG_GROUP = "/iot/robot-arm/soarm101/telemetry"


def query_recent_telemetry(minutes: int = 10, limit: int = 50):
    """Query CloudWatch Logs Insights for recent telemetry."""
    client = boto3.client("logs")

    end_time = int(time.time())
    start_time = end_time - (minutes * 60)

    query = f"""
        fields @timestamp, @message
        | sort @timestamp desc
        | limit {limit}
    """

    print(f"[INFO] Querying last {minutes} minutes of telemetry...")

    # Start query
    response = client.start_query(
        logGroupName=LOG_GROUP,
        startTime=start_time,
        endTime=end_time,
        queryString=query,
        limit=limit,
    )
    query_id = response["queryId"]

    # Poll for results
    while True:
        result = client.get_query_results(queryId=query_id)
        if result["status"] in ("Complete", "Failed", "Cancelled"):
            break
        time.sleep(0.5)

    if result["status"] != "Complete":
        print(f"[ERROR] Query failed with status: {result['status']}")
        return

    # Display results
    print(f"\n{'='*80}")
    print(f"  SO-ARM101 Telemetry — Last {minutes} minutes ({len(result['results'])} records)")
    print(f"{'='*80}\n")

    for row in result["results"]:
        fields = {f["field"]: f["value"] for f in row}
        timestamp = fields.get("@timestamp", "?")
        message = fields.get("@message", "{}")

        try:
            data = json.loads(message)
            joints = data.get("joints", {})
            positions = {name: f"{j['position']:.1f}°" for name, j in joints.items()}
            print(f"  [{timestamp}] {positions}")
        except (json.JSONDecodeError, KeyError):
            print(f"  [{timestamp}] {message[:100]}")

    print(f"\n{'='*80}")
    print(f"  Dashboard: Check AWS Console → CloudWatch → Dashboards → so-arm101-dashboard")
    print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(description="Query SO-ARM101 telemetry from CloudWatch")
    parser.add_argument("--minutes", type=int, default=10, help="How many minutes back to query")
    parser.add_argument("--limit", type=int, default=50, help="Max records to return")
    args = parser.parse_args()

    query_recent_telemetry(minutes=args.minutes, limit=args.limit)


if __name__ == "__main__":
    main()
