#!/usr/bin/env python3
"""
Polls AWS EC2 API every 30 seconds.
Discovers all running instances tagged Role=web.
Rewrites /etc/nginx/conf.d/upstream.conf with their private IPs.
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


def write_upstream(ips):
    lines = ["upstream django_upstream {"]
    # Always include localhost (the OD box's own Gunicorn)
    lines.append("    server 127.0.0.1:8000 max_fails=2 fail_timeout=10s;")
    for ip in ips:
        lines.append(f"    server {ip}:8000 max_fails=2 fail_timeout=10s;")
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

        conf = write_upstream(ips)
        new_hash = hashlib.md5(conf.encode()).hexdigest()
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
