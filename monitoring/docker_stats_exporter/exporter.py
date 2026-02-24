#!/usr/bin/env python3
"""
docker_stats_exporter.py
Exposes per-container CPU / memory / network stats as Prometheus metrics.

Metric names match what load_test_dashboard.json already queries:
  container_cpu_usage_seconds_total
  container_memory_usage_bytes
  container_network_receive_bytes_total
  container_network_transmit_bytes_total

Label: container_label_com_docker_compose_service
"""

import http.client
import http.server
import json
import os
import socket
import threading

DOCKER_SOCK = "/var/run/docker.sock"
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "9417"))
# Per-call socket timeout (seconds). Docker stats?stream=false returns in <1s.
TIMEOUT = float(os.getenv("DOCKER_TIMEOUT", "5"))


# ---------------------------------------------------------------------------
# Docker socket helpers
# ---------------------------------------------------------------------------

def _unix_get(path):
    """Fire a GET request over the Unix socket and return parsed JSON."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    s.connect(DOCKER_SOCK)
    request = f"GET {path} HTTP/1.0\r\nHost: localhost\r\n\r\n"
    s.sendall(request.encode())

    buf = b""
    while True:
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    s.close()

    # Strip HTTP headers
    header_end = buf.find(b"\r\n\r\n")
    body = buf[header_end + 4:] if header_end != -1 else buf
    return json.loads(body)


def list_containers():
    return _unix_get("/containers/json")


def get_stats(container_id):
    return _unix_get(f"/containers/{container_id}/stats?stream=false&one-shot=true")


# ---------------------------------------------------------------------------
# Metric collection (concurrent per container)
# ---------------------------------------------------------------------------

def collect_one(c, results):
    labels = c.get("Labels", {})
    service = labels.get("com.docker.compose.service", "")
    if not service:
        return

    try:
        stats = get_stats(c["Id"])
    except Exception as e:
        results.append(f"# ERROR {service}: {e}")
        return

    label = f'container_label_com_docker_compose_service="{service}"'

    # CPU — cumulative nanoseconds → seconds (Prometheus counter)
    cpu_ns = stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
    cpu_sec = cpu_ns / 1e9

    # Memory — exclude page cache so it matches `docker stats`
    mem = stats.get("memory_stats", {})
    mem_usage = mem.get("usage", 0)
    mem_cache = mem.get("stats", {}).get("cache", 0)
    mem_real = max(mem_usage - mem_cache, 0)

    # Network — sum all interfaces
    networks = stats.get("networks", {})
    rx = sum(i.get("rx_bytes", 0) for i in networks.values())
    tx = sum(i.get("tx_bytes", 0) for i in networks.values())

    results.append(f"container_cpu_usage_seconds_total{{{label}}} {cpu_sec}")
    results.append(f"container_memory_usage_bytes{{{label}}} {mem_real}")
    results.append(f"container_network_receive_bytes_total{{{label}}} {rx}")
    results.append(f"container_network_transmit_bytes_total{{{label}}} {tx}")


def collect_metrics():
    header = [
        "# HELP container_cpu_usage_seconds_total Total CPU time consumed (seconds)",
        "# TYPE container_cpu_usage_seconds_total counter",
        "# HELP container_memory_usage_bytes Current memory usage in bytes",
        "# TYPE container_memory_usage_bytes gauge",
        "# HELP container_network_receive_bytes_total Bytes received over network",
        "# TYPE container_network_receive_bytes_total counter",
        "# HELP container_network_transmit_bytes_total Bytes transmitted over network",
        "# TYPE container_network_transmit_bytes_total counter",
    ]

    try:
        containers = list_containers()
    except Exception as e:
        return "\n".join(header + [f"# ERROR listing containers: {e}"]) + "\n"

    results = []
    threads = []
    for c in containers:
        t = threading.Thread(target=collect_one, args=(c, results), daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join(timeout=TIMEOUT + 1)

    return "\n".join(header + results) + "\n"


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class MetricsHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/metrics", "/metrics/"):
            body = collect_metrics().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # Suppress per-request noise


if __name__ == "__main__":
    print(f"[docker-stats-exporter] Listening on :{LISTEN_PORT}/metrics", flush=True)
    server = http.server.HTTPServer(("", LISTEN_PORT), MetricsHandler)
    server.serve_forever()
