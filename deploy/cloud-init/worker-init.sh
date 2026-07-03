#!/bin/bash
set -e

# --- Fix IPv6: force IPv4 preference for all DNS resolution ---
# Hetzner IPv6 → GHCR CDN drops mid-transfer; IPv4 is reliable.
echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf

# --- Wait for Hetzner metadata service (retries) ---
for i in $(seq 1 30); do
  PRIVATE_IP=$(curl -s --connect-timeout 3 http://169.254.169.254/hetzner/v1/metadata/private-networks | grep "ip:" | head -1 | awk '{print $NF}')
  GATEWAY=$(curl -s --connect-timeout 3 http://169.254.169.254/hetzner/v1/metadata/private-networks | grep "gateway:" | head -1 | awk '{print $2}')
  [ -n "$PRIVATE_IP" ] && [ -n "$GATEWAY" ] && break
  sleep 2
done

if [ -z "$PRIVATE_IP" ] || [ -z "$GATEWAY" ]; then
  echo "FATAL: Could not get private network info after 60s"
  exit 1
fi

# --- Configure private network interface ---
ip addr add ${PRIVATE_IP}/32 dev enp7s0
ip link set enp7s0 up
ip route add 10.0.0.0/16 via ${GATEWAY} dev enp7s0

# --- Write k3s agent config ---
mkdir -p /etc/rancher/k3s
cat > /etc/rancher/k3s/config.yaml <<CONF
flannel-iface: enp7s0
node-ip: ${PRIVATE_IP}
kubelet-arg:
  - "cloud-provider=external"
CONF

# --- Registry mirror: pull images from DB node LAN cache first ---
cat > /etc/rancher/k3s/registries.yaml <<MIRROR
mirrors:
  ghcr.io:
    endpoint:
      - "http://10.0.0.2:5000"
MIRROR

# --- Label server in Hetzner API ---
SERVER_ID=$(curl -s http://169.254.169.254/hetzner/v1/metadata/instance-id)
curl -s -X PUT "https://api.hetzner.cloud/v1/servers/$SERVER_ID" \
  -H "Authorization: Bearer __HCLOUD_TOKEN__" \
  -H "Content-Type: application/json" \
  -d '{"labels":{"role":"k3s","hcloud/node-group":"web-pool"}}'

# --- Start k3s agent (pre-installed in image snapshot) ---
systemctl restart k3s-agent
