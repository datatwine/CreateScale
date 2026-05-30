#!/usr/bin/env python3
"""
Polls AWS EC2 API every 30 seconds.
Discovers all running instances tagged Role=web.
Probes each Spot on port 8000 to confirm Gunicorn is actually listening
(EC2 "running" != application ready — UserData takes ~150s after boot).
Rewrites /etc/nginx/upstream.conf with only ready IPs + keepalive pool.
Always includes 127.0.0.1 (the local Gunicorn on this OD box).
Reloads Nginx only if the list changed.
"""
import hashlib
import socket
import subprocess
import time

import boto3

REGION = "ap-south-1"
TAG_KEY = "Role"
TAG_VALUE = "web"
UPSTREAM_FILE = "/etc/nginx/upstream.conf"
POLL_INTERVAL = 30

ec2 = boto3.client("ec2", region_name=REGION)


def get_web_ips():
    resp = ec2.describe_instances(Filters=[
        {"Name": f"tag:{TAG_KEY}", "Values": [TAG_VALUE]},
        {"Name": "instance-state-name", "Values": ["running"]},
    ])
    ips = []
    for res in resp["Reservations"]:
        for inst in res["Instances"]:
            ip = inst.get("PrivateIpAddress")
            if ip:
                ips.append(ip)
    return sorted(ips)


def is_spot_ready(ip, port=8000, timeout=2):
    """True if Gunicorn is actually listening and serving HTTP on ip:port.

    Uses a one-shot HTTP/1.0 GET to /metrics (lightweight, unauthenticated
    Prometheus endpoint — no DB hit, no auth redirect). We only read the
    first 64 bytes to check for a valid HTTP response line.

    Timeout of 2s avoids blocking the poll loop when a Spot is mid-boot
    or mid-restart. Worst case: 7 unresponsive Spots × 2s = 14s added
    to one poll cycle — well within the 30s interval.
    """
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            s.sendall(b"GET /metrics HTTP/1.0\r\nHost: healthcheck\r\n\r\n")
            response = s.recv(64)
            return response.startswith(b"HTTP/1.")
    except (socket.error, OSError):
        return False


def write_upstream(ips):
    lines = ["upstream django_upstream {"]
    lines.append("    least_conn;")
    # Always include localhost (the OD box's own Gunicorn)
    lines.append("    server 127.0.0.1:8000 max_fails=2 fail_timeout=10s;")
    for ip in ips:
        lines.append(f"    server {ip}:8000 max_fails=2 fail_timeout=10s;")
    # Keep 32 idle connections open to each backend for HTTP/1.1 reuse.
    # Without this, every request opens + closes a TCP connection, burning
    # ephemeral ports (28K budget, 60s TIME_WAIT → ~470 conn/sec ceiling).
    lines.append("    keepalive 32;")
    lines.append("}")
    return "\n".join(lines) + "\n"


prev_hash = ""
while True:
    try:
        ips = get_web_ips()
        # Exclude the OD box's own private IP (already included as 127.0.0.1)
        # The OD box is tagged Role=web too, so filter it out by its own IP
        my_ip = socket.gethostbyname(socket.gethostname())
        ips = [ip for ip in ips if ip != my_ip]

        # Only include Spots whose Gunicorn is actually serving HTTP.
        # Filters out Spots still running UserData (Docker pull, collectstatic)
        # and Spots mid-restart after an OOM or crash.
        ready_ips = [ip for ip in ips if is_spot_ready(ip)]
        if ips and not ready_ips:
            print(f"All {len(ips)} Spots failed readiness — keeping previous upstream")
            time.sleep(POLL_INTERVAL)
            continue

        conf = write_upstream(ready_ips)
        new_hash = hashlib.md5(conf.encode(), usedforsecurity=False).hexdigest()
        if new_hash != prev_hash:
            with open(UPSTREAM_FILE, "w") as f:
                f.write(conf)
            result = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
            if result.returncode == 0:
                subprocess.run(["systemctl", "reload", "nginx"], check=True)
                print(f"Updated upstream: 127.0.0.1 + {ips}")
                prev_hash = new_hash
            else:
                print(f"Nginx config test failed: {result.stderr}")
    except Exception as e:
        print(f"Discovery error: {e}")
    time.sleep(POLL_INTERVAL)
