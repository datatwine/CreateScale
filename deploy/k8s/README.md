# k3s Deployment — ArtKhoj (CreateScale)

## What is this folder?

This folder contains k8s/k3s manifest files — YAML configs that tell k3s
how to run, route, monitor, and scale the ArtKhoj web app.

Docker solved: "works on my machine" — package app + deps into an image.
k3s solves: "how do I run 8 copies across 4 machines, route to healthy ones,
replace crashed ones, and scale automatically?" Docker doesn't do that.
k3s orchestrates Docker containers — your Dockerfile and image stay the same.


## The 4 groups of files

### Group 1 — Run the App (what runs)

| File | What it does |
|---|---|
| `00-namespace.yaml` | Creates an isolated "room" called `artkhoj` for all our stuff |
| `examples/01-secret.example.yaml` | Template for env vars (DB, Redis, OAuth, etc). Real secret never committed |
| `10-job-migrate.yaml` | Runs `manage.py migrate` once per deploy, then exits |
| `11-deployment-web.yaml` | Runs Django/Gunicorn (2-8 copies depending on traffic) |
| `12-deployment-worker.yaml` | Runs Celery worker (processes background tasks from Redis) |
| `13-deployment-beat.yaml` | Runs Celery beat scheduler (exactly 1 copy, always) |

How tasks flow through the system:
- User uploads video -> web pod calls .delay() -> Redis -> worker pod compresses it
- 2am every day -> beat pod pushes "release payouts" into Redis -> worker pod does it
- Beat decides WHEN tasks run. Workers do the actual work. Redis sits in between.

### Group 2 — Route Traffic (how users reach the app)

| File | What it does |
|---|---|
| `20-service-web.yaml` | Internal load balancer. Finds all healthy web pods by label |
| `21-ingress-web.yaml` | Front door. Internet -> Traefik -> Service -> pod |
| `22-middlewares.yaml` | Gzip compression, 25MB body limit, security headers (CSP) |
| `hetzner/traefik-helmchartconfig.yaml` | Trusts Cloudflare IPs so we see real user IPs |

The chain: Internet -> Cloudflare (SSL) -> Ingress (Traefik) -> Service -> Pod

### Group 3 — Watch Everything (how you monitor it)

| File | What it does |
|---|---|
| `40-daemonset-promtail.yaml` | Ships container logs from every node to Loki (DB box) |
| `promtail-config.yaml` | ConfigMap telling promtail which pods to watch |
| `41-daemonset-node-exporter.yaml` | Exposes host CPU/memory for Prometheus to scrape |
| `50-rbac-prometheus.yaml` | Read-only credentials so DB-box Prometheus can see into k3s |
| `../db/prometheus.k8s.yml` | Prometheus config: discovers pods instead of EC2 instances |
| `dev/90-dev-postgres.yaml` | Throwaway DB for local testing. NEVER used in production |

Two monitoring pipelines:
- Logs (text):    App prints -> Promtail ships -> Loki stores -> Grafana shows
- Metrics (numbers): Prometheus scrapes pods/nodes -> stores time-series -> Grafana shows

### Group 4 — Scale & Deploy (how it grows and ships)

| File | What it does |
|---|---|
| `30-hpa-web.yaml` | Auto-scale pods: CPU > 60% -> add pods (2-8 range, seconds) |
| `hetzner/cluster-autoscaler-values.yaml` | Auto-scale VMs: pods don't fit -> boot a new Hetzner VM (~60s) |
| `deploy-k3s.yml` (in .github/workflows/) | CI/CD: build -> test -> push image -> kubectl apply |
| `hetzner/NODE_BOOTSTRAP.md` | How new VMs auto-join the cluster |

Two-layer scaling:
- Layer 1: HPA scales pods (containers) in 2-5 seconds. Fires first.
- Layer 2: Cluster Autoscaler scales VMs only when pods won't fit. Fires second.
- Most traffic spikes are handled by Layer 1 alone.


## Key concepts (jargon decoder)

| Term | Plain English |
|---|---|
| Pod | A running container. Like one `docker run` |
| Deployment | "Run N copies and keep them alive." If one crashes, restart it |
| Service | Internal load balancer. Finds pods by label, routes traffic to them |
| Ingress | The front door. Routes internet traffic to Services |
| DaemonSet | "Run one copy on every node." Auto-added to new nodes |
| Job | "Run once and exit." Used for migrations |
| Namespace | An isolated room. `kubectl delete namespace artkhoj` wipes everything in it |
| HPA | Horizontal Pod Autoscaler — watches CPU, adds/removes pods |
| ConfigMap | A config file stored in k3s (not on any machine's disk). Any pod can mount it |
| Secret | Same as ConfigMap but for sensitive data (passwords, API keys). Encrypted at rest |
| RBAC | Role-Based Access Control — "this identity can read but not write" |
| Manifest | A YAML file that tells k3s what you want. k3s makes it happen |
| `kubectl` | The CLI for talking to k3s. Like `docker` talks to Docker |
| `---` | In YAML: separates multiple objects in one file |
| `selector` | How objects find each other. Service says "find pods labelled app: django" |
| `labels` | Tags on objects. Pods get labels, Services/HPAs select on them |


## First-time setup

### Step 1: Create the namespace
```
kubectl apply -f 00-namespace.yaml
```

### Step 2: Create the real Secret (NEVER commit this)
```
# Copy .env.example to .env.hetzner, fill in real values, then:
kubectl -n artkhoj create secret generic artkhoj-env --from-env-file=.env.hetzner
```

### Step 3: Apply the production manifests
```bash
# Apply each production file explicitly (CI does this automatically).
# Do NOT use "kubectl apply -f deploy/k8s/" — that would apply dev/examples files too.
for f in 00-namespace.yaml 11-deployment-web.yaml 12-deployment-worker.yaml \
  13-deployment-beat.yaml 20-service-web.yaml 21-ingress-web.yaml \
  22-middlewares.yaml 30-hpa-web.yaml 40-daemonset-promtail.yaml \
  41-daemonset-node-exporter.yaml 50-rbac-prometheus.yaml promtail-config.yaml; do
  kubectl apply -f deploy/k8s/$f
done
```

### Step 4: Verify
```
kubectl get pods -n artkhoj
# You should see: django (x2), celery-worker, celery-beat, promtail, node-exporter — all Running
```


## Day-to-day commands

```bash
# Is everything running?
kubectl get pods -n artkhoj

# What's the autoscaler doing? How many replicas right now?
kubectl get hpa -n artkhoj

# Read Django logs (last 100 lines)
kubectl logs deployment/django -n artkhoj --tail=100

# Read worker logs
kubectl logs deployment/celery-worker -n artkhoj --tail=100

# Why is a pod crashing?
kubectl describe pod <pod-name> -n artkhoj

# Restart all web pods (e.g. after a config change)
kubectl rollout restart deployment/django -n artkhoj

# Watch pods in real time (scaling up/down)
kubectl get pods -n artkhoj --watch

# Run a one-off Django management command
kubectl exec -it deployment/django -n artkhoj -- python manage.py shell

# Check what image is running
kubectl get deployment django -n artkhoj -o jsonpath='{.spec.template.spec.containers[0].image}'
```


## Updating a Secret (env var change)

```bash
# Secrets can't be edited in place from an env file. Delete and recreate:
kubectl -n artkhoj delete secret artkhoj-env
kubectl -n artkhoj create secret generic artkhoj-env --from-env-file=.env.hetzner
# Then restart pods so they pick up the new values:
kubectl rollout restart deployment/django -n artkhoj
kubectl rollout restart deployment/celery-worker -n artkhoj
kubectl rollout restart deployment/celery-beat -n artkhoj
```


## Rollback to AWS

No code changes needed. Just point Cloudflare DNS back to the AWS Elastic IP.
The ASG, nginx, discovery script, and deploy.yml are all still there — untouched.
