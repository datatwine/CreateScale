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

# Time window: configurable via $1 (minutes) or TEST_DURATION_MIN env var
DURATION_MIN="${1:-${TEST_DURATION_MIN:-110}}"
END=$(date +%s)
START=$((END - DURATION_MIN * 60))
STEP=60
ASG_NAME="${ASG_NAME:-AK-WebFleet-ASG}"

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
# SECTION 6: Context Switches + Gunicorn Workers
# ---------------------------------------------------------------------------
echo "" >> "$OUTPUT"
echo "╔══════════════════════════════════════════════════════════════╗" >> "$OUTPUT"
echo "║  SECTION 6: CONTEXT SWITCHES + GUNICORN WORKERS            ║" >> "$OUTPUT"
echo "╚══════════════════════════════════════════════════════════════╝" >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "── 6.1 Kernel Context Switches ──" >> "$OUTPUT"
grep ctxt /proc/stat >> "$OUTPUT" 2>/dev/null || echo "  N/A" >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "── 6.2 Gunicorn Worker Processes ──" >> "$OUTPUT"
docker compose exec -T web ps aux 2>/dev/null | grep gunicorn >> "$OUTPUT" || echo "  N/A" >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "── 6.3 Per-Process Context Switches ──" >> "$OUTPUT"
for pid in $(docker compose exec -T web pgrep -f gunicorn 2>/dev/null); do
    pid=$(echo "$pid" | tr -d '\r')
    echo "  PID $pid:" >> "$OUTPUT"
    docker compose exec -T web cat /proc/$pid/status 2>/dev/null | grep -E "voluntary_ctxt_switches|nonvoluntary_ctxt_switches" >> "$OUTPUT"
done


# ---------------------------------------------------------------------------
# SECTION 7: Redis Cache Stats
# ---------------------------------------------------------------------------
echo "" >> "$OUTPUT"
echo "╔══════════════════════════════════════════════════════════════╗" >> "$OUTPUT"
echo "║  SECTION 7: REDIS CACHE STATS                              ║" >> "$OUTPUT"
echo "╚══════════════════════════════════════════════════════════════╝" >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "── 7.1 Cache Hit/Miss Ratio ──" >> "$OUTPUT"
cd "$(dirname "$SCRIPT_DIR")"
docker compose exec -T redis redis-cli INFO stats 2>/dev/null | grep -E "keyspace_hits|keyspace_misses|total_commands_processed" >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "── 7.2 Redis Memory ──" >> "$OUTPUT"
docker compose exec -T redis redis-cli INFO memory 2>/dev/null | grep -E "used_memory_human|used_memory_peak_human|maxmemory_human" >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "── 7.3 Redis Key Count ──" >> "$OUTPUT"
docker compose exec -T redis redis-cli DBSIZE 2>/dev/null >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "── 7.4 Redis Slow Log (top 10) ──" >> "$OUTPUT"
docker compose exec -T redis redis-cli SLOWLOG GET 10 2>/dev/null >> "$OUTPUT"


# ---------------------------------------------------------------------------
# SECTION 8: ASG Scaling Activity
# ---------------------------------------------------------------------------
echo "" >> "$OUTPUT"
echo "╔══════════════════════════════════════════════════════════════╗" >> "$OUTPUT"
echo "║  SECTION 8: ASG SCALING ACTIVITY                           ║" >> "$OUTPUT"
echo "╚══════════════════════════════════════════════════════════════╝" >> "$OUTPUT"
echo "" >> "$OUTPUT"

if command -v aws &>/dev/null; then
    aws autoscaling describe-scaling-activities \
        --auto-scaling-group-name "$ASG_NAME" \
        --max-items 50 2>/dev/null \
    | python3 -c "
import sys, json
from datetime import datetime
try:
    d = json.load(sys.stdin)
    activities = d.get('Activities', [])
    start_ts = $START
    end_ts = $END
    print(f'  ASG: $ASG_NAME')
    print(f'  Window: {datetime.fromtimestamp(start_ts).strftime(\"%H:%M\")} -> {datetime.fromtimestamp(end_ts).strftime(\"%H:%M\")}')
    print(f'  {\"StartTime\":<22s} {\"Status\":<12s} Description')
    print(f'  {\"─\"*22} {\"─\"*12} {\"─\"*50}')
    found = 0
    for a in activities:
        # Parse ISO timestamp
        ts_str = a.get('StartTime', '')
        if isinstance(ts_str, str):
            try:
                ts = datetime.fromisoformat(ts_str.replace('Z','+00:00')).timestamp()
            except:
                continue
        else:
            ts = ts_str
        if start_ts <= ts <= end_ts:
            found += 1
            t = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
            status = a.get('StatusCode', '?')
            desc = a.get('Description', '')[:60]
            print(f'  {t:<22s} {status:<12s} {desc}')
    if found == 0:
        print('  No scaling activity during test window.')
except Exception as e:
    print(f'  Parse error: {e}')
" >> "$OUTPUT"
else
    echo "  ⚠️  aws CLI not available — skipping ASG activity" >> "$OUTPUT"
fi


# ---------------------------------------------------------------------------
# SECTION 9: Per-Instance Fleet Metrics
# ---------------------------------------------------------------------------
echo "" >> "$OUTPUT"
echo "╔══════════════════════════════════════════════════════════════╗" >> "$OUTPUT"
echo "║  SECTION 9: PER-INSTANCE FLEET METRICS                     ║" >> "$OUTPUT"
echo "╚══════════════════════════════════════════════════════════════╝" >> "$OUTPUT"

prom_query "9.1 Per-Instance RPS (1-min rate)" \
    "sum by (instance) (rate(django_http_requests_total_by_view_transport_method_total[1m]))"

prom_query "9.2 Per-Instance p95 Latency (ms)" \
    "histogram_quantile(0.95, sum by (le, instance) (rate(django_http_requests_latency_seconds_by_view_method_bucket[1m]))) * 1000"

prom_query "9.3 Per-Instance CPU (process seconds/sec)" \
    "rate(process_cpu_seconds_total{job=\"web-fleet\"}[1m])"


# ---------------------------------------------------------------------------
# SECTION 10: Scaling Gap Analysis
# ---------------------------------------------------------------------------
echo "" >> "$OUTPUT"
echo "╔══════════════════════════════════════════════════════════════╗" >> "$OUTPUT"
echo "║  SECTION 10: SCALING GAP ANALYSIS                          ║" >> "$OUTPUT"
echo "╚══════════════════════════════════════════════════════════════╝" >> "$OUTPUT"
echo "" >> "$OUTPUT"

# Query p95 latency at 30s resolution, then find the gap where p95 > 500ms
curl -s "${PROM}/api/v1/query_range?query=$(python3 -c "import urllib.parse; print(urllib.parse.quote('histogram_quantile(0.95, sum by (le) (rate(django_http_requests_latency_seconds_by_view_method_bucket[1m]))) * 1000'))")&start=${START}&end=${END}&step=30" \
| python3 -c "
import sys, json
from datetime import datetime

THRESHOLD_MS = 500
RECOVERY_READINGS = 3   # 3 consecutive readings below threshold = recovered (90s)

try:
    d = json.load(sys.stdin)
    if d['status'] != 'success':
        print('  ERROR: ' + str(d))
        sys.exit()

    results = d['data']['result']
    if not results:
        print('  No p95 latency data found.')
        sys.exit()

    values = results[0]['values']  # [[timestamp, value], ...]
    if not values:
        print('  No p95 data points.')
        sys.exit()

    # Find gap_start: first timestamp where p95 > threshold
    gap_start = None
    gap_start_idx = None
    max_p95 = 0
    for i, (ts, val) in enumerate(values):
        v = float(val)
        if v != v:  # NaN check
            continue
        if v > THRESHOLD_MS and gap_start is None:
            gap_start = float(ts)
            gap_start_idx = i
        if gap_start is not None and v > max_p95:
            max_p95 = v

    if gap_start is None:
        print('  No scaling gap detected — p95 never exceeded 500ms. ')
        sys.exit()

    # Find gap_end: first timestamp after gap_start with 3+ consecutive readings below threshold
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
                # Recovery point is when the streak started
                gap_end = float(values[i - RECOVERY_READINGS + 1][0])
                break
        else:
            consecutive_below = 0

    # Query 5xx errors during gap window
    gap_end_ts = gap_end if gap_end else float(values[-1][0])

    print('  SCALING GAP ANALYSIS')
    print('  ' + '─' * 40)
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
" >> "$OUTPUT"

# 5xx error count during gap (separate query — uses the gap timestamps from above or full window)
echo "" >> "$OUTPUT"
echo "── 10.1 5xx Errors During Test Window ──" >> "$OUTPUT"
prom_instant "5xx Total" \
    "sum(increase(django_http_responses_total_by_status_view_method_total{status=~\"5..\"}[${DURATION_MIN}m]))"


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
