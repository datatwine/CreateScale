#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  collect_postmortem_v3.sh — Post-Load-Test Data Collection (k3s / Hetzner)
# ═══════════════════════════════════════════════════════════════════════════
#
#  PURPOSE: Collect ALL observability data after a load test on the Hetzner
#           k3s cluster into a single text file for AI analysis.
#           v3 fixes LT7 blindspots: full time series, per-node metrics,
#           resident vs fleet awareness, metrics-server health, HPA decision
#           log, pod lifecycle timing, pg_stat_statements.
#
#  USAGE:   bash scripts/collect_postmortem_v3.sh [duration_minutes]
#           → creates postmortem_v3_YYYYMMDD_HHMM.txt in the scripts/ directory
#
#  RUN ON:  The k3s master node (artkhoj-k3s), where kubectl is available.
#
#  CONFIGURE:  Set these env vars before running, or accept defaults:
#    DB_NODE_IP       — private IP of the DB node       (default: 10.0.0.2)
#    PROM_PORT        — Prometheus port on DB node       (default: 9090)
#    REDIS_PORT       — Redis port on DB node            (default: 6379)
#    K8S_NAMESPACE    — k8s namespace                    (default: artkhoj)
#    DEPLOY_NAME      — django fleet deployment name     (default: django)
#    PG_CONTAINER     — postgres docker container name   (default: postgres)
#    PG_USER          — postgres user                    (default: artkhoj)
#    PG_DB            — postgres database                (default: artkhoj_db)
#
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP="$(date +%Y%m%d_%H%M)"
OUTPUT="${SCRIPT_DIR}/postmortem_v3_${TIMESTAMP}.txt"

# Configurable
DB_NODE_IP="${DB_NODE_IP:-10.0.0.2}"
PROM="http://${DB_NODE_IP}:${PROM_PORT:-9090}"
REDIS_HOST="${DB_NODE_IP}"
REDIS_PORT="${REDIS_PORT:-6379}"
NS="${K8S_NAMESPACE:-artkhoj}"
DEPLOY="${DEPLOY_NAME:-django}"
PG_CONTAINER="${PG_CONTAINER:-postgres}"
PG_USER="${PG_USER:-artkhoj}"
PG_DB="${PG_DB:-artkhoj_db}"

# Time window
DURATION_MIN="${1:-${TEST_DURATION_MIN:-110}}"
END=$(date +%s)
START=$((END - DURATION_MIN * 60))
STEP=60

header() {
    echo "" >> "$OUTPUT"
    echo "╔══════════════════════════════════════════════════════════════╗" >> "$OUTPUT"
    printf "║  %-58s║\n" "$1" >> "$OUTPUT"
    echo "╚══════════════════════════════════════════════════════════════╝" >> "$OUTPUT"
}

sub_header() {
    echo "" >> "$OUTPUT"
    echo "── $1 ──" >> "$OUTPUT"
}

# ─── Prometheus helpers ───────────────────────────────────────────────────

# Sampled output (first 5, middle 5, last 5) — for less-critical metrics
prom_query() {
    local label="$1"
    local query="$2"
    sub_header "$label"
    curl -sf --max-time 10 \
        "${PROM}/api/v1/query_range?query=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$query'''))")&start=${START}&end=${END}&step=${STEP}" \
        2>/dev/null | python3 -c "
import sys, json
from datetime import datetime
try:
    d = json.load(sys.stdin)
    if d['status'] != 'success': print('  ERROR: ' + str(d)); sys.exit()
    for r in d['data']['result']:
        metric = r['metric']
        label = ', '.join(f'{k}={v}' for k,v in metric.items() if k != '__name__')
        if not label: label = 'value'
        vals = r['values']
        sample = vals[:5]
        if len(vals) > 15: sample += ['...']
        sample += vals[len(vals)//2-2:len(vals)//2+3]
        if len(vals) > 15: sample += ['...']
        sample += vals[-5:]
        for v in sample:
            if v == '...':
                print('  ...')
            else:
                ts = datetime.fromtimestamp(v[0]).strftime('%H:%M')
                print(f'  {label}: {ts} -> {float(v[1]):.4f}')
except Exception as e:
    print(f'  Parse error: {e}')
" >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ Query failed or timed out" >> "$OUTPUT"
}

# Full output (EVERY data point) — for critical metrics where gaps hide the story
prom_query_full() {
    local label="$1"
    local query="$2"
    sub_header "$label"
    curl -sf --max-time 15 \
        "${PROM}/api/v1/query_range?query=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$query'''))")&start=${START}&end=${END}&step=${STEP}" \
        2>/dev/null | python3 -c "
import sys, json
from datetime import datetime
try:
    d = json.load(sys.stdin)
    if d['status'] != 'success': print('  ERROR: ' + str(d)); sys.exit()
    for r in d['data']['result']:
        metric = r['metric']
        label = ', '.join(f'{k}={v}' for k,v in metric.items() if k != '__name__')
        if not label: label = 'value'
        for v in r['values']:
            ts = datetime.fromtimestamp(v[0]).strftime('%H:%M')
            val = float(v[1])
            if val != val:
                print(f'  {label}: {ts} -> NaN')
            else:
                print(f'  {label}: {ts} -> {val:.4f}')
except Exception as e:
    print(f'  Parse error: {e}')
" >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ Query failed or timed out" >> "$OUTPUT"
}

prom_instant() {
    local label="$1"
    local query="$2"
    sub_header "$label"
    curl -sf --max-time 10 \
        "${PROM}/api/v1/query?query=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$query'''))")" \
        2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if d['status'] != 'success': print('  ERROR: ' + str(d)); sys.exit()
    for r in d['data']['result']:
        metric = r['metric']
        label = ', '.join(f'{k}={v}' for k,v in metric.items() if k != '__name__')
        if not label: label = 'value'
        print(f'  {label}: {float(r[\"value\"][1]):.4f}')
except Exception as e:
    print(f'  Parse error: {e}')
" >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ Query failed or timed out" >> "$OUTPUT"
}


# ═══════════════════════════════════════════════════════════════════════════
#  BANNER
# ═══════════════════════════════════════════════════════════════════════════

cat >> "$OUTPUT" <<BANNER
═══════════════════════════════════════════════════════════════
  POSTMORTEM DATA COLLECTION v3 (k3s / Hetzner) — $(date)
  Time window: $(date -d @$START +%H:%M) → $(date -d @$END +%H:%M) (${DURATION_MIN}min)
  Prometheus:  ${PROM}
  Namespace:   ${NS}
═══════════════════════════════════════════════════════════════
BANNER


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 1: HETZNER INFRASTRUCTURE SNAPSHOT
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 1: INFRASTRUCTURE SNAPSHOT"

sub_header "1.1 Server Info (uname)"
uname -a >> "$OUTPUT" 2>/dev/null || echo "  N/A" >> "$OUTPUT"

sub_header "1.2 CPU Info"
lscpu | grep -E "^(Architecture|CPU\(s\)|Model name|CPU max MHz)" >> "$OUTPUT" 2>/dev/null || echo "  N/A" >> "$OUTPUT"

sub_header "1.3 Memory"
free -h >> "$OUTPUT" 2>/dev/null || echo "  N/A" >> "$OUTPUT"

sub_header "1.4 Disk Usage"
df -h / >> "$OUTPUT" 2>/dev/null || echo "  N/A" >> "$OUTPUT"

sub_header "1.5 k3s Version"
k3s --version >> "$OUTPUT" 2>/dev/null || echo "  N/A" >> "$OUTPUT"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 2: KUBERNETES STATE
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 2: KUBERNETES STATE"

sub_header "2.1 Nodes"
kubectl get nodes -o wide >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ kubectl failed" >> "$OUTPUT"

sub_header "2.2 Pods (${NS})"
kubectl get pods -n "$NS" -o wide >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ kubectl failed" >> "$OUTPUT"

sub_header "2.3 HPA Status"
kubectl get hpa -n "$NS" -o wide >> "$OUTPUT" 2>/dev/null || echo "  No HPA found" >> "$OUTPUT"
echo "" >> "$OUTPUT"
kubectl describe hpa -n "$NS" >> "$OUTPUT" 2>/dev/null

sub_header "2.4 Resource Usage — Pods"
kubectl top pods -n "$NS" >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ metrics-server not available" >> "$OUTPUT"

sub_header "2.5 Resource Usage — Nodes"
kubectl top nodes >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ metrics-server not available" >> "$OUTPUT"

sub_header "2.6 Pod Restarts & OOMKills"
kubectl get pods -n "$NS" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .status.containerStatuses[*]}restarts={.restartCount} lastState={.lastState}{"\n"}{end}{end}' >> "$OUTPUT" 2>/dev/null || echo "  N/A" >> "$OUTPUT"

sub_header "2.7 Recent k8s Events (last 100)"
kubectl get events -n "$NS" --sort-by='.lastTimestamp' 2>/dev/null | tail -100 >> "$OUTPUT" || echo "  N/A" >> "$OUTPUT"

sub_header "2.8 ALL HPA Events (scale decisions + failures + metrics errors)"
kubectl get events -n "$NS" --sort-by='.lastTimestamp' --field-selector involvedObject.kind=HorizontalPodAutoscaler 2>/dev/null | tail -100 >> "$OUTPUT" || echo "  No HPA events" >> "$OUTPUT"

sub_header "2.9 HPA Conditions (current state)"
kubectl get hpa -n "$NS" -o jsonpath='{range .items[*]}HPA: {.metadata.name}{"\n"}{range .status.conditions[*]}  {.type}={.status}  reason={.reason}  msg={.message}{"\n"}{end}{end}' >> "$OUTPUT" 2>/dev/null || echo "  N/A" >> "$OUTPUT"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 2A: RESIDENT vs FLEET PODS
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 2A: RESIDENT vs FLEET PODS"

sub_header "2A.1 Resident Pod (master-pinned)"
kubectl get pods -n "$NS" -l role=resident -o wide >> "$OUTPUT" 2>/dev/null || echo "  No resident pods found" >> "$OUTPUT"

sub_header "2A.2 Fleet Pods (worker nodes)"
kubectl get pods -n "$NS" -l role=fleet -o wide >> "$OUTPUT" 2>/dev/null || echo "  No fleet pods found" >> "$OUTPUT"

sub_header "2A.3 Resident Resource Usage"
kubectl top pods -n "$NS" -l role=resident >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ metrics unavailable" >> "$OUTPUT"

sub_header "2A.4 Fleet Resource Usage"
kubectl top pods -n "$NS" -l role=fleet >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ metrics unavailable" >> "$OUTPUT"

sub_header "2A.5 Pod-to-Node-to-Role Mapping"
kubectl get pods -n "$NS" -l app=django -o jsonpath='{range .items[*]}pod={.metadata.name}  node={.spec.nodeName}  role={.metadata.labels.role}{"\n"}{end}' >> "$OUTPUT" 2>/dev/null || echo "  N/A" >> "$OUTPUT"

sub_header "2A.6 Service Endpoints (should include both resident + fleet)"
kubectl get endpoints -n "$NS" >> "$OUTPUT" 2>/dev/null || echo "  N/A" >> "$OUTPUT"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 2B: METRICS-SERVER HEALTH
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 2B: METRICS-SERVER HEALTH"

sub_header "2B.1 Metrics-Server Pod Status"
kubectl get pods -n kube-system -l k8s-app=metrics-server -o wide >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ metrics-server pod not found" >> "$OUTPUT"

sub_header "2B.2 Metrics-Server Logs (last 100 lines)"
kubectl logs -n kube-system -l k8s-app=metrics-server --tail=100 --request-timeout=10s >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ Could not read metrics-server logs" >> "$OUTPUT"

sub_header "2B.3 kubectl top nodes (validates metrics API)"
kubectl top nodes >> "$OUTPUT" 2>&1 || echo "  ⚠️ metrics-server NOT returning data" >> "$OUTPUT"

sub_header "2B.4 kubectl top pods (validates pod metrics)"
kubectl top pods -n "$NS" >> "$OUTPUT" 2>&1 || echo "  ⚠️ metrics-server NOT returning pod data" >> "$OUTPUT"

sub_header "2B.5 Metrics API Service Health"
kubectl get apiservice v1beta1.metrics.k8s.io -o jsonpath='{.status.conditions[*].type}={.status.conditions[*].status}  message={.status.conditions[*].message}' >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ metrics API service not found" >> "$OUTPUT"
echo "" >> "$OUTPUT"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 2C: HPA REPLICA TIMELINE
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 2C: HPA REPLICA TIMELINE"

sub_header "2C.1 HPA Desired Replicas (kube-state-metrics)"
prom_query_full "HPA Desired Replicas" \
    "kube_horizontalpodautoscaler_status_desired_replicas{horizontalpodautoscaler='django-hpa',namespace='${NS}'}"

sub_header "2C.2 HPA Current Replicas (kube-state-metrics)"
prom_query_full "HPA Current Replicas" \
    "kube_horizontalpodautoscaler_status_current_replicas{horizontalpodautoscaler='django-hpa',namespace='${NS}'}"

sub_header "2C.3 HPA Scaling Events (fallback — parsed from events)"
kubectl get events -n "$NS" --field-selector reason=SuccessfulRescale \
    -o jsonpath='{range .items[*]}{.lastTimestamp} {.message}{"\n"}{end}' 2>/dev/null \
    | sort >> "$OUTPUT" || echo "  No SuccessfulRescale events" >> "$OUTPUT"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 2D: POD LIFECYCLE TIMING
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 2D: POD LIFECYCLE TIMING"

sub_header "2D.1 Pod Scheduling Events"
kubectl get events -n "$NS" --field-selector reason=Scheduled --sort-by='.lastTimestamp' 2>/dev/null | tail -50 >> "$OUTPUT" || echo "  None" >> "$OUTPUT"

sub_header "2D.2 Container Started Events"
kubectl get events -n "$NS" --field-selector reason=Started --sort-by='.lastTimestamp' 2>/dev/null | tail -50 >> "$OUTPUT" || echo "  None" >> "$OUTPUT"

sub_header "2D.3 Image Pull Events (measures pull latency)"
kubectl get events -n "$NS" --field-selector reason=Pulled --sort-by='.lastTimestamp' 2>/dev/null | tail -50 >> "$OUTPUT" || echo "  None" >> "$OUTPUT"

sub_header "2D.4 Pod Kill Events"
kubectl get events -n "$NS" --field-selector reason=Killing --sort-by='.lastTimestamp' 2>/dev/null | tail -50 >> "$OUTPUT" || echo "  None" >> "$OUTPUT"

sub_header "2D.5 Pod Startup Latency (created → ready)"
kubectl get pods -n "$NS" -l app=django -o jsonpath='{range .items[*]}pod={.metadata.name}  created={.metadata.creationTimestamp}  ready={.status.conditions[?(@.type=="Ready")].lastTransitionTime}  phase={.status.phase}{"\n"}{end}' >> "$OUTPUT" 2>/dev/null || echo "  N/A" >> "$OUTPUT"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 3: PROMETHEUS — RPS & LATENCY (full timeline for critical metrics)
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 3: PROMETHEUS — RPS & LATENCY"

prom_query_full "3.1 Total RPS (1-min windows) [FULL]" \
    "sum(rate(django_http_requests_total_by_view_transport_method_total[1m]))"

prom_query "3.2 p50 Latency (ms)" \
    "histogram_quantile(0.50, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[1m]))) * 1000"

prom_query_full "3.3 p95 Latency (ms) [FULL]" \
    "histogram_quantile(0.95, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[1m]))) * 1000"

prom_query "3.4 p99 Latency (ms)" \
    "histogram_quantile(0.99, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[1m]))) * 1000"

prom_query_full "3.5 Response Rate by Status Code [FULL]" \
    "sum by (status) (rate(django_http_responses_total_by_status_view_method_total[1m]))"

prom_instant "3.6 Top 10 Slowest Views (avg ms, last 5min)" \
    "topk(10, sum by (view) (rate(django_http_requests_latency_seconds_by_view_method_sum[5m])) / (sum by (view) (rate(django_http_requests_latency_seconds_by_view_method_count[5m])) + 0.001) * 1000)"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 4: PROMETHEUS — PER-POD FLEET METRICS
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 4: PER-POD FLEET METRICS"

prom_query "4.1 Per-Pod RPS (1-min rate)" \
    "sum by (pod) (rate(django_http_requests_total_by_view_transport_method_total[1m]))"

prom_query "4.2 Per-Pod p95 Latency (ms)" \
    "histogram_quantile(0.95, sum by (le, pod) (rate(django_http_requests_latency_seconds_by_view_method_bucket[1m]))) * 1000"

prom_query "4.3 Per-Pod CPU (process seconds/sec)" \
    "rate(process_cpu_seconds_total{job='web-fleet'}[1m])"

prom_query "4.4 Per-Pod Memory (RSS bytes)" \
    "process_resident_memory_bytes{job='web-fleet'}"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 5: HOST / NODE METRICS (per-node, full timeline)
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 5: HOST / NODE METRICS (per-node breakdown)"

prom_query_full "5.1 Per-Node CPU Usage % [FULL]" \
    "100 - (avg by (instance) (rate(node_cpu_seconds_total{mode='idle'}[1m])) * 100)"

prom_query_full "5.2 Per-Node Memory Usage % [FULL]" \
    "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100"

prom_query "5.3 Per-Node Disk Read IOPS" \
    "sum by (instance) (rate(node_disk_reads_completed_total[1m]))"

prom_query "5.4 Per-Node Disk Write IOPS" \
    "sum by (instance) (rate(node_disk_writes_completed_total[1m]))"

prom_query_full "5.5 Per-Node Disk I/O Wait % [FULL]" \
    "avg by (instance) (rate(node_cpu_seconds_total{mode='iowait'}[1m])) * 100"

prom_query "5.6 Per-Node Network Received (bytes/sec)" \
    "sum by (instance) (rate(node_network_receive_bytes_total{device!='lo'}[1m]))"

prom_query "5.7 Per-Node Network Transmitted (bytes/sec)" \
    "sum by (instance) (rate(node_network_transmit_bytes_total{device!='lo'}[1m]))"

prom_query "5.8 Per-Node Filesystem Usage %" \
    "100 - (node_filesystem_avail_bytes{mountpoint='/'} / node_filesystem_size_bytes{mountpoint='/'} * 100)"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 6: POSTGRES METRICS
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 6: POSTGRES METRICS"

prom_query "6.1 Active Connections" \
    "sum(pg_stat_activity_count)"

prom_query "6.2 Connections by State" \
    "sum by (state) (pg_stat_activity_count)"

prom_query "6.3 Cache Hit Ratio" \
    "pg_stat_database_blks_hit{datname!=\"\"} / (pg_stat_database_blks_hit{datname!=\"\"} + pg_stat_database_blks_read{datname!=\"\"} + 0.001)"

prom_query "6.4 Transactions per Second" \
    "sum(rate(pg_stat_database_xact_commit{datname!=\"\"}[1m]))"

prom_instant "6.5 Deadlocks (total)" \
    "sum(pg_stat_database_deadlocks)"

prom_instant "6.6 Temp Files Written (bytes, total)" \
    "sum(pg_stat_database_temp_bytes)"

prom_query "6.7 Rows Returned per Second" \
    "sum(rate(pg_stat_database_tup_returned[1m]))"

prom_query "6.8 Rows Inserted per Second" \
    "sum(rate(pg_stat_database_tup_inserted[1m]))"

sub_header "6.9 pg_stat_statements — Top 10 by total_exec_time"
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@${DB_NODE_IP}" \
    "docker exec ${PG_CONTAINER} psql -U ${PG_USER} -d ${PG_DB} -c \"
SELECT LEFT(query, 80) AS query,
       calls,
       round(total_exec_time::numeric, 1) AS total_ms,
       round(mean_exec_time::numeric, 1) AS mean_ms,
       round(max_exec_time::numeric, 1) AS max_ms,
       rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
\"" >> "$OUTPUT" 2>/dev/null || echo "  pg_stat_statements not available (extension may need enabling)" >> "$OUTPUT"

sub_header "6.10 pg_stat_statements — Top 10 by mean_exec_time (slowest queries)"
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@${DB_NODE_IP}" \
    "docker exec ${PG_CONTAINER} psql -U ${PG_USER} -d ${PG_DB} -c \"
SELECT LEFT(query, 80) AS query,
       calls,
       round(total_exec_time::numeric, 1) AS total_ms,
       round(mean_exec_time::numeric, 1) AS mean_ms,
       round(max_exec_time::numeric, 1) AS max_ms,
       rows
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
\"" >> "$OUTPUT" 2>/dev/null || echo "  pg_stat_statements not available" >> "$OUTPUT"

sub_header "6.11 Lock Waits (current)"
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@${DB_NODE_IP}" \
    "docker exec ${PG_CONTAINER} psql -U ${PG_USER} -d ${PG_DB} -c \"
SELECT count(*) AS lock_waits FROM pg_stat_activity WHERE wait_event_type = 'Lock';
\"" >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ SSH or query failed" >> "$OUTPUT"

sub_header "6.12 Long-Running Queries (> 5s)"
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@${DB_NODE_IP}" \
    "docker exec ${PG_CONTAINER} psql -U ${PG_USER} -d ${PG_DB} -c \"
SELECT pid,
       now() - pg_stat_activity.query_start AS duration,
       LEFT(query, 80) AS query
FROM pg_stat_activity
WHERE state != 'idle'
  AND (now() - pg_stat_activity.query_start) > interval '5 seconds'
ORDER BY duration DESC;
\"" >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ SSH or query failed" >> "$OUTPUT"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 7: REDIS CACHE STATS
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 7: REDIS CACHE STATS"

prom_query "7.1 Redis Ops/sec" \
    "rate(redis_commands_processed_total[1m])"

prom_query "7.2 Redis Memory Usage (bytes)" \
    "redis_memory_used_bytes"

prom_instant "7.3 Redis Hit Ratio (instant)" \
    "redis_keyspace_hits_total / (redis_keyspace_hits_total + redis_keyspace_misses_total + 0.001)"

sub_header "7.4 Redis INFO (direct)"
if command -v redis-cli &>/dev/null; then
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INFO stats 2>/dev/null \
        | grep -E "keyspace_hits|keyspace_misses|total_commands_processed|expired_keys|evicted_keys" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INFO memory 2>/dev/null \
        | grep -E "used_memory_human|used_memory_peak_human|maxmemory_human" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
    echo "  Key count:" >> "$OUTPUT"
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DBSIZE 2>/dev/null >> "$OUTPUT"
else
    echo "  redis-cli not installed — using Prometheus metrics above" >> "$OUTPUT"
fi

sub_header "7.5 Redis Slow Log (top 10)"
if command -v redis-cli &>/dev/null; then
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SLOWLOG GET 10 2>/dev/null >> "$OUTPUT"
else
    echo "  redis-cli not installed — skipping" >> "$OUTPUT"
fi


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 8: TRAEFIK INGRESS
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 8: TRAEFIK INGRESS"

sub_header "8.1 Traefik Pod Logs (last 100 lines, errors only)"
TRAEFIK_POD=$(kubectl get pods -n kube-system -l app.kubernetes.io/name=traefik -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$TRAEFIK_POD" ]; then
    kubectl logs -n kube-system "$TRAEFIK_POD" --tail=100 --request-timeout=10s 2>/dev/null \
        | grep -iE "error|502|503|504|timeout|refused" >> "$OUTPUT" \
        || echo "  No errors found in Traefik logs" >> "$OUTPUT"
else
    echo "  ⚠️ Traefik pod not found" >> "$OUTPUT"
fi

sub_header "8.2 Traefik IngressRoutes"
kubectl get ingressroutes -n "$NS" -o wide >> "$OUTPUT" 2>/dev/null \
    || kubectl get ingress -n "$NS" -o wide >> "$OUTPUT" 2>/dev/null \
    || echo "  No ingress resources found" >> "$OUTPUT"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 9: APPLICATION LOGS
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 9: APPLICATION LOGS"

sub_header "9.1 Django Pod Logs — errors & warnings (last 200 lines per pod)"
for POD in $(kubectl get pods -n "$NS" -l app=django -o jsonpath='{.items[*].metadata.name}'); do
    echo "" >> "$OUTPUT"
    echo "  ── Pod: $POD ──" >> "$OUTPUT"
    kubectl logs -n "$NS" "$POD" --tail=200 --request-timeout=10s 2>/dev/null \
        | grep -iE "error|exception|traceback|warning|critical|500|502|503|timeout" >> "$OUTPUT" \
        || echo "    No errors found" >> "$OUTPUT"
done

sub_header "9.2 Django Pod Logs — full last 50 lines per pod"
for POD in $(kubectl get pods -n "$NS" -l app=django -o jsonpath='{.items[*].metadata.name}'); do
    echo "" >> "$OUTPUT"
    echo "  ── Pod: $POD ──" >> "$OUTPUT"
    kubectl logs -n "$NS" "$POD" --tail=50 --request-timeout=10s >> "$OUTPUT" 2>/dev/null
done

sub_header "9.3 Celery Worker Logs (last 100 lines)"
kubectl logs -n "$NS" deploy/celery-worker --tail=100 --request-timeout=10s >> "$OUTPUT" 2>/dev/null \
    || echo "  ⚠️ Could not read celery-worker logs" >> "$OUTPUT"

sub_header "9.4 Celery Beat Logs (last 50 lines)"
kubectl logs -n "$NS" deploy/celery-beat --tail=50 --request-timeout=10s >> "$OUTPUT" 2>/dev/null \
    || echo "  ⚠️ Could not read celery-beat logs" >> "$OUTPUT"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 10: GUNICORN WORKERS (all pods)
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 10: GUNICORN WORKERS"

for POD in $(kubectl get pods -n "$NS" -l app=django -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
    sub_header "10.x Worker Processes — $POD"
    kubectl exec -n "$NS" "$POD" --request-timeout=10s -- ps aux 2>/dev/null | grep gunicorn >> "$OUTPUT" \
        || echo "  N/A" >> "$OUTPUT"

    echo "  Open file descriptors (connection proxy):" >> "$OUTPUT"
    kubectl exec -n "$NS" "$POD" --request-timeout=10s -- sh -c 'ls /proc/1/fd 2>/dev/null | wc -l' >> "$OUTPUT" 2>/dev/null \
        || echo "  N/A" >> "$OUTPUT"

    echo "  Context switches:" >> "$OUTPUT"
    for pid in $(kubectl exec -n "$NS" "$POD" --request-timeout=10s -- pgrep -f gunicorn 2>/dev/null); do
        pid=$(echo "$pid" | tr -d '\r')
        echo "    PID $pid:" >> "$OUTPUT"
        kubectl exec -n "$NS" "$POD" --request-timeout=10s -- cat /proc/$pid/status 2>/dev/null \
            | grep -E "voluntary_ctxt_switches|nonvoluntary_ctxt_switches" >> "$OUTPUT" \
            || true
    done
done


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 11: PROMETHEUS TARGETS
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 11: PROMETHEUS TARGETS"

curl -sf --max-time 10 "${PROM}/api/v1/targets" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for t in d['data']['activeTargets']:
        job = t['labels'].get('job', '?')
        health = t['health']
        url = t.get('scrapeUrl', '?')
        last_err = t.get('lastError', '')
        print(f'  {job:20s} -> {health:6s}  ({url})')
        if last_err: print(f'    └─ ERROR: {last_err}')
except Exception as e:
    print(f'  Parse error: {e}')
" >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ Could not reach Prometheus targets endpoint" >> "$OUTPUT"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 12: SCALING GAP ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 12: SCALING GAP ANALYSIS"

curl -sf --max-time 15 "${PROM}/api/v1/query_range?query=$(python3 -c "import urllib.parse; print(urllib.parse.quote('histogram_quantile(0.95, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[1m]))) * 1000'))")&start=${START}&end=${END}&step=30" \
| python3 -c "
import sys, json
from datetime import datetime

THRESHOLD_MS = 500
RECOVERY_READINGS = 3

try:
    d = json.load(sys.stdin)
    if d['status'] != 'success':
        print('  ERROR: ' + str(d))
        sys.exit()

    results = d['data']['result']
    if not results:
        print('  No p95 latency data found.')
        sys.exit()

    values = results[0]['values']
    if not values:
        print('  No p95 data points.')
        sys.exit()

    gap_start = None
    gap_start_idx = None
    max_p95 = 0
    for i, (ts, val) in enumerate(values):
        v = float(val)
        if v != v: continue
        if v > THRESHOLD_MS and gap_start is None:
            gap_start = float(ts)
            gap_start_idx = i
        if gap_start is not None and v > max_p95:
            max_p95 = v

    if gap_start is None:
        print('  No scaling gap detected — p95 never exceeded 500ms.')
        sys.exit()

    gap_end = None
    consecutive_below = 0
    for i in range(gap_start_idx, len(values)):
        ts, val = values[i]
        v = float(val)
        if v != v:
            consecutive_below = 0
            continue
        if v < THRESHOLD_MS:
            consecutive_below += 1
            if consecutive_below >= RECOVERY_READINGS:
                gap_end = float(values[i - RECOVERY_READINGS + 1][0])
                break
        else:
            consecutive_below = 0

    print('  SCALING GAP ANALYSIS')
    print('  ' + '-' * 40)
    print(f'  Gap start:    {datetime.fromtimestamp(gap_start).strftime(\"%H:%M:%S\")} (p95 crossed 500ms)')
    if gap_end:
        duration_s = gap_end - gap_start
        mins = int(duration_s // 60)
        secs = int(duration_s % 60)
        print(f'  Gap end:      {datetime.fromtimestamp(gap_end).strftime(\"%H:%M:%S\")} (p95 recovered below 500ms)')
        print(f'  Duration:     {mins}m {secs}s')
    else:
        duration_s = float(values[-1][0]) - gap_start
        mins = int(duration_s // 60)
        secs = int(duration_s % 60)
        print(f'  Gap end:      DID NOT RECOVER')
        print(f'  Duration:     {mins}m {secs}s (ongoing)')
    print(f'  Peak p95:     {max_p95:,.0f}ms')

except Exception as e:
    print(f'  Analysis error: {e}')
" >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ Gap analysis query failed" >> "$OUTPUT"

sub_header "12.1 5xx Errors During Test Window"
prom_instant "5xx Total" \
    "sum(increase(django_http_responses_total_by_status_view_method_total{status=~\"5..\"}[${DURATION_MIN}m]))"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 13: DB BOX HEALTH (via SSH)
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 13: DB BOX HEALTH"

sub_header "13.1 DB Box Docker Containers"
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@${DB_NODE_IP}" \
    "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.PIDs}}'" \
    >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ SSH to DB box failed" >> "$OUTPUT"

sub_header "13.2 DB Box Disk Usage"
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@${DB_NODE_IP}" \
    "df -h / && echo '' && df -h /var/lib/docker" \
    >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ SSH failed" >> "$OUTPUT"

sub_header "13.3 DB Box Memory"
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@${DB_NODE_IP}" \
    "free -h" \
    >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ SSH failed" >> "$OUTPUT"

sub_header "13.4 DB Box CPU"
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@${DB_NODE_IP}" \
    "uptime" \
    >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ SSH failed" >> "$OUTPUT"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 14: CLUSTER AUTOSCALER (expanded)
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 14: CLUSTER AUTOSCALER"

CA_POD=$(kubectl get pods -n kube-system -l app.kubernetes.io/name=cluster-autoscaler -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
[ -z "$CA_POD" ] && CA_POD=$(kubectl get pods -n kube-system 2>/dev/null | grep cluster-autoscaler | awk 'NR==1{print $1}')
if [ -n "$CA_POD" ]; then
    sub_header "14.1 Autoscaler Full Log (last 500 lines, scale-related)"
    kubectl logs -n kube-system "$CA_POD" --tail=500 --request-timeout=10s 2>/dev/null \
        | grep -iE "scale|node|add|remove|unneeded|ready|unschedulable|pending" >> "$OUTPUT" \
        || echo "  No scaling activity in logs" >> "$OUTPUT"

    sub_header "14.2 Node Provisioning Timeline (Scale-up decisions)"
    kubectl logs -n kube-system "$CA_POD" --tail=500 --request-timeout=10s 2>/dev/null \
        | grep -iE "Scale-up:|Creating.*node|Node.*registered|node.*ready|NodeReady" >> "$OUTPUT" \
        || echo "  No scale-up events" >> "$OUTPUT"

    sub_header "14.3 Scale-Down Decisions"
    kubectl logs -n kube-system "$CA_POD" --tail=500 --request-timeout=10s 2>/dev/null \
        | grep -iE "Scale-down:|unneeded|removing node|node.*removed" >> "$OUTPUT" \
        || echo "  No scale-down events" >> "$OUTPUT"

    sub_header "14.4 Autoscaler Errors & Warnings"
    kubectl logs -n kube-system "$CA_POD" --tail=500 --request-timeout=10s 2>/dev/null \
        | grep -iE "error|warn|fail|timeout|not ready" >> "$OUTPUT" \
        || echo "  No errors" >> "$OUTPUT"

    sub_header "14.5 Node Add/Remove k8s Events"
    kubectl get events -A --field-selector reason=ScaledUpGroup --sort-by='.lastTimestamp' >> "$OUTPUT" 2>/dev/null || true
    kubectl get events -A --field-selector reason=ScaleDown --sort-by='.lastTimestamp' >> "$OUTPUT" 2>/dev/null || true
    kubectl get events -A --field-selector reason=RegisteredNode --sort-by='.lastTimestamp' >> "$OUTPUT" 2>/dev/null || true

    sub_header "14.6 Autoscaler Status (configmap)"
    kubectl get configmap -n kube-system cluster-autoscaler-status -o yaml >> "$OUTPUT" 2>/dev/null \
        || echo "  No status configmap found" >> "$OUTPUT"
else
    echo "" >> "$OUTPUT"
    echo "  Cluster autoscaler is NOT installed." >> "$OUTPUT"
    echo "  Pod scaling only (HPA), no node autoscaling." >> "$OUTPUT"
fi


# ═══════════════════════════════════════════════════════════════════════════
#  DONE
# ═══════════════════════════════════════════════════════════════════════════

cat >> "$OUTPUT" <<FOOTER

═══════════════════════════════════════════════════════════════
  COLLECTION COMPLETE — $(date)
  Output: $OUTPUT
═══════════════════════════════════════════════════════════════
FOOTER

echo ""
echo "✅ Postmortem v3 data collected → $OUTPUT"
echo "   Lines: $(wc -l < "$OUTPUT")"
echo ""
echo "📋 Next steps:"
echo "   1. SCP this file to your local machine:"
echo "      scp root@$(hostname -I | awk '{print $1}'):${OUTPUT} ."
echo "   2. Paste the contents to the AI for analysis"
echo ""
