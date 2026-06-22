# Node Bootstrap — How New VMs Auto-Join the k3s Cluster

## What is this?

When the Cluster Autoscaler decides pods won't fit on existing nodes, it boots a new
Hetzner VM. That VM needs to join the k3s cluster automatically — no SSH, no manual
setup. This doc explains how.

A node is a **blank vessel**. It doesn't need app code, env vars, or config files.
Its only job is to run the k3s agent and connect to the cluster. Once connected,
the scheduler places pods on it, and those pods carry their own context (image +
Secret + ConfigMap).

## The cloud-init script

When the Cluster Autoscaler creates a VM, it uses a cloud-init user-data script
(or a pre-baked snapshot) that does exactly two things:

```bash
#!/bin/bash
set -eu

# 1. Install k3s agent (not server — this node joins, it doesn't lead)
curl -sfL https://get.k3s.io | K3S_URL="https://CHANGE_ME_SERVER_IP:6443" \
  K3S_TOKEN="CHANGE_ME_CLUSTER_TOKEN" \
  INSTALL_K3S_EXEC="agent" sh -
```

That's it. Once the agent connects:
- The node appears in `kubectl get nodes`
- The scheduler can place pods on it
- DaemonSets (promtail, node-exporter) auto-deploy to it
- When traffic drops and the node empties out, the autoscaler drains and deletes it

## Getting the token

On the k3s server node (web-node-1):
```bash
cat /var/lib/rancher/k3s/server/node-token
```

## Snapshot approach (faster boot)

Instead of installing k3s on every boot, create a snapshot:

1. Boot a fresh CAX21 with the cloud-init above
2. Wait for k3s agent to install and connect
3. Stop the VM
4. Create a Hetzner snapshot from it
5. Configure `cluster-autoscaler-values.yaml` to use this snapshot image

New nodes from the snapshot boot in ~20s instead of ~60s (skip the install step).

## Firewall rules

The Hetzner firewall must allow:
- **6443/tcp** (inbound from nodes to server) — k3s API
- **10250/tcp** (inbound) — kubelet API
- **8472/udp** (inbound) — flannel VXLAN
- **51820/udp** (inbound) — WireGuard (if using k3s WireGuard backend)
- **80,443/tcp** (inbound from Cloudflare IPs) — web traffic to Traefik
