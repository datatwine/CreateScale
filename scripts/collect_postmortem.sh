#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  collect_postmortem.sh — Post-Load-Test Data Collection
# ═══════════════════════════════════════════════════════════════════════════
#
#  PURPOSE: Collect all observability data after a load test into a single
#           text file that you paste to the AI for comprehensive analysis.
#
#  USAGE:   bash scripts/collect_postmortem.sh
#           → creates postmortem_YYYYMMDD_HHMM.txt in the scripts/ directory
#
#  WHAT IT COLLECTS:
#    1. Prometheus range queries (RPS, latency percentiles, errors, CPU, memory, DB)
#    2. Nginx log analysis (status codes, slowest requests, timeouts, 5xx errors)
#    3. Gunicorn/Django logs (worker crashes, timeouts, tracebacks)
#    4. Docker stats snapshot (CPU/memory/network per container)
#
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP="$(date +%Y%m%d_%H%M)"
OUTPUT="${SCRIPT_DIR}/postmortem_${TIMESTAMP}.txt"
PROM="http://localhost:9090"

# Time window: last 70 minutes (covers the 55-min soak + buffer)
END=$(date +%s)
START=$((END - 4200))
STEP=60

echo "═══════════════════════════════════════════════════════════════" > "$OUTPUT"
echo "  POSTMORTEM DATA COLLECTION — $(date)" >> "$OUTPUT"
echo "  Time window: $(date -d @$START +%H:%M) → $(date -d @$END +%H:%M)" >> "$OUTPUT"
echo "═══════════════════════════════════════════════════════════════" >> "$OUTPUT"

# ---------------------------------------------------------------------------
# SECTION 1: Prometheus Metrics
# ---------------------------------------------------------------------------
echo "" >> "$OUTPUT"
echo "╔══════════════════════════════════════════════════════════════╗" >> "$OUTPUT"
echo "║  SECTION 1: PROMETHEUS METRICS                             ║" >> "$OUTPUT"
echo "╚══════════════════════════════════════════════════════════════╝" >> "$OUTPUT"

prom_query() {
    local label="$1"
    local query="$2"
    echo "" >> "$OUTPUT"
    echo "── $label ──" >> "$OUTPUT"
    curl -s "${PROM}/api/v1/query_range?query=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$query'))")&start=${START}&end=${END}&step=${STEP}" \
        | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if d['status'] != 'success': print('  ERROR: ' + str(d)); sys.exit()
    for r in d['data']['result']:
        metric = r['metric']
        label = ', '.join(f'{k}={v}' for k,v in metric.items() if k != '__name__')
        if not label: label = 'value'
        vals = r['values']
        # Show first 5, middle 5, last 5 values to keep output manageable
        sample = vals[:5] + (['...'] if len(vals) > 15 else []) + vals[len(vals)//2-2:len(vals)//2+3] + (['...'] if len(vals) > 15 else []) + vals[-5:]
        for v in sample:
            if v == '...':
                print('  ...')
            else:
                from datetime import datetime
                ts = datetime.fromtimestamp(v[0]).strftime('%H:%M')
                print(f'  {label}: {ts} → {float(v[1]):.4f}')
except Exception as e:
    print(f'  Parse error: {e}')
" 2>/dev/null >> "$OUTPUT"
}

prom_instant() {
    local label="$1"
    local query="$2"
    echo "" >> "$OUTPUT"
    echo "── $label ──" >> "$OUTPUT"
    curl -s "${PROM}/api/v1/query?query=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$query'))")" \
        | python3 -c "
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
" 2>/dev/null >> "$OUTPUT"
}

# 1.1 Overall RPS timeline
prom_query "1.1 Total RPS (1-min windows)" \
    "sum(rate(django_http_requests_total_by_view_transport_method_total[1m]))"

# 1.2 Latency percentiles
prom_query "1.2 p50 Latency (ms)" \
    "histogram_quantile(0.50, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[1m]))) * 1000"

prom_query "1.3 p95 Latency (ms)" \
    "histogram_quantile(0.95, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[1m]))) * 1000"

prom_query "1.4 p99 Latency (ms)" \
    "histogram_quantile(0.99, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[1m]))) * 1000"

# 1.5 Error rates by status
prom_query "1.5 Response Rate by Status Code" \
    "sum by (status) (rate(django_http_responses_total_by_status_view_method_total[1m]))"

# 1.6 Container CPU
prom_query "1.6 Container CPU Usage (cores)" \
    "sum by (container_label_com_docker_compose_service) (rate(container_cpu_usage_seconds_total{container_label_com_docker_compose_service=~\".+\"}[1m]))"

# 1.7 Total Host CPU %
prom_query "1.7 Host CPU % (total / 2 cores)" \
    "sum(rate(container_cpu_usage_seconds_total{container_label_com_docker_compose_service=~\".+\"}[1m])) / 2"

# 1.8 Container Memory
prom_query "1.8 Container Memory (bytes)" \
    "container_memory_usage_bytes{container_label_com_docker_compose_service=~\".+\"}"

# 1.9 Postgres connections
prom_query "1.9 Postgres Active Connections" \
    "sum(pg_stat_activity_count)"

# 1.10 Postgres cache hit ratio
prom_query "1.10 Postgres Cache Hit Ratio" \
    "pg_stat_database_blks_hit{datname!=\"\"} / (pg_stat_database_blks_hit{datname!=\"\"} + pg_stat_database_blks_read{datname!=\"\"} + 0.001)"

# 1.11 Top 10 slowest views (instant query, not range)
prom_instant "1.11 Top 10 Slowest Views (avg ms, last 5min)" \
    "topk(10, sum by (view) (rate(django_http_requests_latency_seconds_by_view_method_sum[5m])) / (sum by (view) (rate(django_http_requests_latency_seconds_by_view_method_count[5m])) + 0.001) * 1000)"


# ---------------------------------------------------------------------------
# SECTION 2: Nginx Log Analysis
# ---------------------------------------------------------------------------
echo "" >> "$OUTPUT"
echo "╔══════════════════════════════════════════════════════════════╗" >> "$OUTPUT"
echo "║  SECTION 2: NGINX LOG ANALYSIS                             ║" >> "$OUTPUT"
echo "╚══════════════════════════════════════════════════════════════╝" >> "$OUTPUT"

NGINX_LOG="/var/log/nginx/access.log"

# Check if log exists (it might be in a docker volume)
if [ ! -f "$NGINX_LOG" ]; then
    # Try the compose-mounted path
    NGINX_LOG="$(dirname "$SCRIPT_DIR")/logs/nginx/access.log"
fi

if [ -f "$NGINX_LOG" ]; then
    echo "" >> "$OUTPUT"
    echo "── 2.1 Status Code Distribution (last 5000 lines) ──" >> "$OUTPUT"
    tail -5000 "$NGINX_LOG" | awk '{print $9}' | sort | uniq -c | sort -rn | head -20 >> "$OUTPUT" 2>/dev/null

    echo "" >> "$OUTPUT"
    echo "── 2.2 Top 20 Slowest Requests (request time in seconds) ──" >> "$OUTPUT"
    tail -5000 "$NGINX_LOG" | grep -oP 'rt=\K[0-9.]+' | sort -rn | head -20 >> "$OUTPUT" 2>/dev/null

    echo "" >> "$OUTPUT"
    echo "── 2.3 Requests with Upstream Time > 5s ──" >> "$OUTPUT"
    COUNT=$(tail -5000 "$NGINX_LOG" | grep -oP 'urt=\K[0-9.]+' | awk '$1 > 5' | wc -l 2>/dev/null || echo "0")
    echo "  Count: $COUNT" >> "$OUTPUT"

    echo "" >> "$OUTPUT"
    echo "── 2.4 502/503/504 Errors (last 50) ──" >> "$OUTPUT"
    grep -E '" (502|503|504) ' "$NGINX_LOG" | tail -50 >> "$OUTPUT" 2>/dev/null || echo "  None found" >> "$OUTPUT"
else
    echo "  ⚠️ Nginx log not found at $NGINX_LOG" >> "$OUTPUT"
fi


# ---------------------------------------------------------------------------
# SECTION 3: Gunicorn / Django Logs
# ---------------------------------------------------------------------------
echo "" >> "$OUTPUT"
echo "╔══════════════════════════════════════════════════════════════╗" >> "$OUTPUT"
echo "║  SECTION 3: GUNICORN / DJANGO LOGS (last 200 lines)       ║" >> "$OUTPUT"
echo "╚══════════════════════════════════════════════════════════════╝" >> "$OUTPUT"
echo "" >> "$OUTPUT"

cd "$(dirname "$SCRIPT_DIR")"
docker compose logs --tail=200 web 2>/dev/null >> "$OUTPUT" || echo "  ⚠️ Could not read web container logs" >> "$OUTPUT"


# ---------------------------------------------------------------------------
# SECTION 4: Docker Stats Snapshot
# ---------------------------------------------------------------------------
echo "" >> "$OUTPUT"
echo "╔══════════════════════════════════════════════════════════════╗" >> "$OUTPUT"
echo "║  SECTION 4: DOCKER STATS (current snapshot)                ║" >> "$OUTPUT"
echo "╚══════════════════════════════════════════════════════════════╝" >> "$OUTPUT"
echo "" >> "$OUTPUT"

docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.PIDs}}" >> "$OUTPUT" 2>/dev/null || echo "  ⚠️ Could not read docker stats" >> "$OUTPUT"


# ---------------------------------------------------------------------------
# SECTION 5: Prometheus Targets Health
# ---------------------------------------------------------------------------
echo "" >> "$OUTPUT"
echo "╔══════════════════════════════════════════════════════════════╗" >> "$OUTPUT"
echo "║  SECTION 5: PROMETHEUS TARGETS                             ║" >> "$OUTPUT"
echo "╚══════════════════════════════════════════════════════════════╝" >> "$OUTPUT"
echo "" >> "$OUTPUT"

curl -s "${PROM}/api/v1/targets" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for t in d['data']['activeTargets']:
        job = t['labels'].get('job', '?')
        health = t['health']
        url = t.get('scrapeUrl', '?')
        last_err = t.get('lastError', '')
        print(f'  {job:20s} → {health:6s}  ({url})')
        if last_err: print(f'    └─ ERROR: {last_err}')
except Exception as e:
    print(f'  Parse error: {e}')
" 2>/dev/null >> "$OUTPUT"


# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo "" >> "$OUTPUT"
echo "═══════════════════════════════════════════════════════════════" >> "$OUTPUT"
echo "  COLLECTION COMPLETE — $(date)" >> "$OUTPUT"
echo "  Output: $OUTPUT" >> "$OUTPUT"
echo "═══════════════════════════════════════════════════════════════" >> "$OUTPUT"

echo ""
echo "✅ Postmortem data collected → $OUTPUT"
echo "   Lines: $(wc -l < "$OUTPUT")"
echo ""
echo "📋 Next steps:"
echo "   1. SCP this file to your local machine:"
echo "      scp -i <key.pem> ubuntu@<EC2_IP>:$(pwd)/scripts/postmortem_${TIMESTAMP}.txt ."
echo "   2. Paste the contents to the AI for analysis"
echo ""
