#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  collect_postmortem_v2.sh — Post-Load-Test Data Collection (k3s / Hetzner)
# ═══════════════════════════════════════════════════════════════════════════
#
#  PURPOSE: Collect all observability data after a load test on the Hetzner
#           k3s cluster into a single text file for AI analysis.
#
#  USAGE:   bash scripts/collect_postmortem_v2.sh [duration_minutes]
#           → creates postmortem_YYYYMMDD_HHMM.txt in the scripts/ directory
#
#  RUN ON:  The k3s node (artkhoj-k3s), where kubectl is available.
#
#  CONFIGURE:  Set these env vars before running, or accept defaults:
#    DB_NODE_IP       — private IP of the DB node   (default: 10.0.0.2)
#    PROM_PORT        — Prometheus port on DB node   (default: 9090)
#    REDIS_PORT       — Redis port on DB node        (default: 6379)
#    K8S_NAMESPACE    — k8s namespace                (default: artkhoj)
#    DEPLOY_NAME      — django deployment name       (default: django)
#
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP="$(date +%Y%m%d_%H%M)"
OUTPUT="${SCRIPT_DIR}/postmortem_${TIMESTAMP}.txt"

# Configurable
DB_NODE_IP="${DB_NODE_IP:-10.0.0.2}"
PROM="http://${DB_NODE_IP}:${PROM_PORT:-9090}"
REDIS_HOST="${DB_NODE_IP}"
REDIS_PORT="${REDIS_PORT:-6379}"
NS="${K8S_NAMESPACE:-artkhoj}"
DEPLOY="${DEPLOY_NAME:-django}"

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
  POSTMORTEM DATA COLLECTION v2 (k3s / Hetzner) — $(date)
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

sub_header "2.7 Recent k8s Events (last 50)"
kubectl get events -n "$NS" --sort-by='.lastTimestamp' 2>/dev/null | tail -50 >> "$OUTPUT" || echo "  N/A" >> "$OUTPUT"

sub_header "2.8 HPA Scaling Events"
kubectl get events -n "$NS" --field-selector reason=SuccessfulRescale --sort-by='.lastTimestamp' >> "$OUTPUT" 2>/dev/null || echo "  No scaling events" >> "$OUTPUT"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 3: PROMETHEUS — RPS & LATENCY
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 3: PROMETHEUS — RPS & LATENCY"

prom_query "3.1 Total RPS (1-min windows)" \
    "sum(rate(django_http_requests_total_by_view_transport_method_total[1m]))"

prom_query "3.2 p50 Latency (ms)" \
    "histogram_quantile(0.50, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[1m]))) * 1000"

prom_query "3.3 p95 Latency (ms)" \
    "histogram_quantile(0.95, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[1m]))) * 1000"

prom_query "3.4 p99 Latency (ms)" \
    "histogram_quantile(0.99, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[1m]))) * 1000"

prom_query "3.5 Response Rate by Status Code" \
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
#  SECTION 5: PROMETHEUS — HOST / NODE METRICS
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 5: HOST / NODE METRICS"

prom_query "5.1 Node CPU Usage % (all cores)" \
    "100 - (avg(rate(node_cpu_seconds_total{mode='idle',job='node-web'}[1m])) * 100)"

prom_query "5.2 Node Memory Usage %" \
    "(1 - node_memory_MemAvailable_bytes{job='node-web'} / node_memory_MemTotal_bytes{job='node-web'}) * 100"

prom_query "5.3 Disk Read IOPS" \
    "sum(rate(node_disk_reads_completed_total{job='node-web'}[1m]))"

prom_query "5.4 Disk Write IOPS" \
    "sum(rate(node_disk_writes_completed_total{job='node-web'}[1m]))"

prom_query "5.5 Disk I/O Wait %" \
    "avg(rate(node_cpu_seconds_total{mode='iowait',job='node-web'}[1m])) * 100"

prom_query "5.6 Network Received (bytes/sec)" \
    "sum(rate(node_network_receive_bytes_total{device!='lo',job='node-web'}[1m]))"

prom_query "5.7 Network Transmitted (bytes/sec)" \
    "sum(rate(node_network_transmit_bytes_total{device!='lo',job='node-web'}[1m]))"

prom_query "5.8 Filesystem Usage %" \
    "100 - (node_filesystem_avail_bytes{mountpoint='/',job='node-web'} / node_filesystem_size_bytes{mountpoint='/',job='node-web'} * 100)"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 6: PROMETHEUS — POSTGRES
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


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 7: REDIS CACHE STATS
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 7: REDIS CACHE STATS"

# Via Prometheus (redis_exporter)
prom_query "7.1 Redis Ops/sec" \
    "rate(redis_commands_processed_total[1m])"

prom_query "7.2 Redis Memory Usage (bytes)" \
    "redis_memory_used_bytes"

prom_instant "7.3 Redis Hit Ratio (instant)" \
    "redis_keyspace_hits_total / (redis_keyspace_hits_total + redis_keyspace_misses_total + 0.001)"

# Direct Redis CLI via network (no SSH needed — Redis is on private net, unprotected)
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
#  SECTION 8: TRAEFIK INGRESS (replaces Nginx)
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 8: TRAEFIK INGRESS"

sub_header "8.1 Traefik Pod Logs (last 100 lines, errors only)"
TRAEFIK_POD=$(kubectl get pods -n kube-system -l app.kubernetes.io/name=traefik -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$TRAEFIK_POD" ]; then
    kubectl logs -n kube-system "$TRAEFIK_POD" --tail=100 2>/dev/null \
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
    kubectl logs -n "$NS" "$POD" --tail=200 2>/dev/null \
        | grep -iE "error|exception|traceback|warning|critical|500|502|503|timeout" >> "$OUTPUT" \
        || echo "    No errors found" >> "$OUTPUT"
done

sub_header "9.2 Django Pod Logs — full last 50 lines per pod"
for POD in $(kubectl get pods -n "$NS" -l app=django -o jsonpath='{.items[*].metadata.name}'); do
    echo "" >> "$OUTPUT"
    echo "  ── Pod: $POD ──" >> "$OUTPUT"
    kubectl logs -n "$NS" "$POD" --tail=50 >> "$OUTPUT" 2>/dev/null
done

sub_header "9.3 Celery Worker Logs (last 100 lines)"
kubectl logs -n "$NS" deploy/celery-worker --tail=100 >> "$OUTPUT" 2>/dev/null \
    || echo "  ⚠️ Could not read celery-worker logs" >> "$OUTPUT"

sub_header "9.4 Celery Beat Logs (last 50 lines)"
kubectl logs -n "$NS" deploy/celery-beat --tail=50 >> "$OUTPUT" 2>/dev/null \
    || echo "  ⚠️ Could not read celery-beat logs" >> "$OUTPUT"


# ═══════════════════════════════════════════════════════════════════════════
#  SECTION 10: GUNICORN WORKERS
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 10: GUNICORN WORKERS"

FIRST_POD=$(kubectl get pods -n "$NS" -l app=django -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$FIRST_POD" ]; then
    sub_header "10.1 Worker Process List"
    kubectl exec -n "$NS" "$FIRST_POD" -- ps aux 2>/dev/null | grep gunicorn >> "$OUTPUT" \
        || echo "  N/A" >> "$OUTPUT"

    sub_header "10.2 Per-Worker Context Switches"
    for pid in $(kubectl exec -n "$NS" "$FIRST_POD" -- pgrep -f gunicorn 2>/dev/null); do
        pid=$(echo "$pid" | tr -d '\r')
        echo "  PID $pid:" >> "$OUTPUT"
        kubectl exec -n "$NS" "$FIRST_POD" -- cat /proc/$pid/status 2>/dev/null \
            | grep -E "voluntary_ctxt_switches|nonvoluntary_ctxt_switches" >> "$OUTPUT"
    done
else
    echo "  ⚠️ No django pod found" >> "$OUTPUT"
fi


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
    >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ SSH to DB box failed (add k3s node's key to DB authorized_keys)" >> "$OUTPUT"

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
#  SECTION 14: CLUSTER AUTOSCALER (if installed)
# ═══════════════════════════════════════════════════════════════════════════
header "SECTION 14: CLUSTER AUTOSCALER"

CA_POD=$(kubectl get pods -n kube-system -l app.kubernetes.io/name=cluster-autoscaler -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$CA_POD" ]; then
    sub_header "14.1 Autoscaler Status"
    kubectl logs -n kube-system "$CA_POD" --tail=50 2>/dev/null \
        | grep -iE "scale|node|add|remove|unneeded|ready" >> "$OUTPUT" \
        || echo "  No scaling activity in logs" >> "$OUTPUT"

    sub_header "14.2 Node Add/Remove Events"
    kubectl get events -A --field-selector reason=ScaledUpGroup --sort-by='.lastTimestamp' >> "$OUTPUT" 2>/dev/null
    kubectl get events -A --field-selector reason=ScaleDown --sort-by='.lastTimestamp' >> "$OUTPUT" 2>/dev/null
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
echo "✅ Postmortem data collected → $OUTPUT"
echo "   Lines: $(wc -l < "$OUTPUT")"
echo ""
echo "📋 Next steps:"
echo "   1. SCP this file to your local machine:"
echo "      scp root@$(hostname -I | awk '{print $1}'):${OUTPUT} ."
echo "   2. Paste the contents to the AI for analysis"
echo ""
