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

Instead of installing k3s on every boot, nodes boot from a pre-baked snapshot.
Current golden image: **417284290** (`k3s-node-golden-v2-agent-disabled`,
built 2026-08-07 on a cpx22 → 80GB disk; referenced in
`deploy/cloud-init/cluster-config.json`).

### THE CARDINAL RULE — k3s-agent must be DISABLED in the snapshot

If k3s-agent is *enabled*, it auto-starts at power-on and registers with the
master BEFORE cloud-init writes `/etc/rancher/k3s/config.yaml`. k3s applies
`node-taint`/`node-label` config **only at first registration, never on
restart** — so the node joins untainted/unlabeled forever. This exact bug let
django pods + svclb-traefik colonize the dedicated ingress node (2026-08-07).
With the agent disabled, the init script (`worker-init.sh` / `ingress-init.sh`)
is the ONLY thing that ever starts it — always after config.yaml exists — and
it runs `systemctl enable --now` so reboots rejoin normally afterwards.

### Rebuild procedure (v2 — follow exactly)

1. Boot a throwaway from the current golden image, **without private network,
   without user-data** (agent can't reach the master = can't phantom-join):
   `hcloud server create --name snapshot-builder --type cpx22 --location nbg1 --image <CURRENT_ID> --ssh-key artkhoj-key`
   **Builder disk must be exactly 80GB** (cx33/cpx21/cpx22) — the image
   inherits the builder's disk size, and a bigger image won't fit the 80GB
   pools (learned the hard way with cx23's 40GB).
2. Make whatever changes prompted the rebuild (k3s upgrade, OS patches, …).
3. Clean + disable (all as root):
   ```bash
   systemctl disable --now k3s-agent          # THE fix — never skip
   rm -rf /var/lib/rancher/k3s/agent          # no inherited cluster identity
   rm -f  /etc/rancher/node/password
   rm -rf /etc/rancher/k3s                    # init scripts rewrite these
   truncate -s 0 /etc/machine-id              # each clone mints its own
   rm -f /var/lib/dbus/machine-id && ln -s /etc/machine-id /var/lib/dbus/machine-id
   cloud-init clean --logs                    # next boot = first boot
   rm -f /etc/ssh/ssh_host_*                  # per-node host keys
   systemctl is-enabled k3s-agent             # MUST print "disabled"
   ```
   **Never delete** `/etc/systemd/system/k3s-agent.service.env` — it holds the
   baked-in `K3S_URL` (master private IP) + `K3S_TOKEN` join credentials that
   the init scripts rely on.
4. Freeze offline: `hcloud server poweroff snapshot-builder` then
   `hcloud server create-image --type snapshot --description "k3s-node-golden-vN-agent-disabled" snapshot-builder`
5. **Pre-flight before pointing the fleet at it:** boot a second throwaway from
   the new image (again no private net / no user-data) and verify:
   is-enabled=disabled, is-active=inactive, no `/var/lib/rancher/k3s/agent`,
   `K3S_URL` still present. Delete both throwaways.
6. Update `imagesForArch` in `deploy/cloud-init/cluster-config.json`, commit,
   push. Keep the previous image until the new one has survived a load test —
   rollback is just reverting that one line.

## Firewall rules

The Hetzner firewall must allow:
- **6443/tcp** (inbound from nodes to server) — k3s API
- **10250/tcp** (inbound) — kubelet API
- **8472/udp** (inbound) — flannel VXLAN
- **51820/udp** (inbound) — WireGuard (if using k3s WireGuard backend)
- **80,443/tcp** (inbound from Cloudflare IPs) — web traffic to Traefik
