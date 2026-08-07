#!/bin/bash
# MIRROR WARNING: deploy/cloud-init/worker-init.sh and deploy/cloud-init/ingress-init.sh
# must stay identical EXCEPT the k3s config.yaml heredoc (ingress adds node-label/node-taint).
# Any other change made here MUST be copied to the sibling file in the same commit.
set -e

# Defense-in-depth: snapshot v2 ships k3s-agent DISABLED, so nothing should be
# running here. This stop only matters if a future snapshot rebuild forgets the
# disable — the agent must never register before config.yaml is written, because
# k3s applies node-taint/labels only at FIRST registration, never on restart.
systemctl stop k3s-agent 2>/dev/null || true

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
ip addr add ${PRIVATE_IP}/32 dev enp7s0 2>/dev/null || true
ip link set enp7s0 up
ip route add 10.0.0.0/16 via ${GATEWAY} dev enp7s0 2>/dev/null || true

# --- Write k3s agent config ---
mkdir -p /etc/rancher/k3s
cat > /etc/rancher/k3s/config.yaml <<CONF
flannel-iface: enp7s0
node-ip: ${PRIVATE_IP}
node-label:
  - "role=ingress"
node-taint:
  - "role=ingress:NoSchedule"
kubelet-arg:
  - "cloud-provider=external"
  - "system-reserved=cpu=300m,memory=300Mi"
CONF

# --- Registry mirror: pull images from DB node LAN cache first ---
cat > /etc/rancher/k3s/registries.yaml <<MIRROR
mirrors:
  ghcr.io:
    endpoint:
      - "http://10.0.0.2:5000"
MIRROR

# --- Label server in Hetzner API (MERGE — preserve autoscaler's hcloud/node-group label) ---
# A PUT replaces ALL labels, so read the current set first and add role=k3s to it.
# The hcloud/node-group=<pool> label set by the cluster autoscaler at creation
# must survive: it is how the CA and the ghost-sweeper track pool membership.
SERVER_ID=$(curl -s http://169.254.169.254/hetzner/v1/metadata/instance-id)
CURRENT_LABELS=$(curl -s -H "Authorization: Bearer __HCLOUD_TOKEN__" \
  "https://api.hetzner.cloud/v1/servers/$SERVER_ID" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); l=d['server']['labels']; l['role']='k3s'; print(json.dumps({'labels': l}))")
curl -s -X PUT "https://api.hetzner.cloud/v1/servers/$SERVER_ID" \
  -H "Authorization: Bearer __HCLOUD_TOKEN__" \
  -H "Content-Type: application/json" \
  -d "$CURRENT_LABELS"

# --- Enable + start k3s agent (pre-installed but DISABLED in the snapshot) ---
# This script is the ONLY starter, and it runs after config.yaml exists, so the
# first registration always carries the right taints/labels. enable makes the
# node rejoin normally after reboots.
systemctl enable --now k3s-agent
