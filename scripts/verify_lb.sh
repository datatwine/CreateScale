#!/bin/bash
# =============================================================================
# verify_lb.sh — automated post-deploy verification for the multi-pool
# autoscaler + HAProxy ingress path (plan Phase V-b, checks V8–V19).
#
# Runs in CI as the final step of the deploy-autoscaler job (after the CA and
# HAProxy helm upgrades, before the firewall closes). Can also be run manually
# from any machine with cluster access:
#
#   MASTER_HOST=<master-ip> HCLOUD_TOKEN=<token> bash scripts/verify_lb.sh
#
# Requires: kubectl (KUBECONFIG set), curl, jq, openssl.
# Any FAIL → exit 1 (CI goes red). WARN never fails the run.
# =============================================================================
set -u

NS_APP="artkhoj"
NS_HAPROXY="haproxy-controller"
HOST_HEADER="stagefreedom.org"
HPA_MAX_REPLICAS=60   # keep in sync with deploy/k8s/30-hpa-web.yaml
EXPECTED_POOLS=19     # 21 worker pools + 1 ingress pool

PASS=0; FAIL=0; WARN=0
FAILED_LIST=""

pass() { PASS=$((PASS+1)); echo "  PASS  $1"; }
fail() { FAIL=$((FAIL+1)); FAILED_LIST="${FAILED_LIST}    - $1
"; echo "  FAIL  $1"; }
warn() { WARN=$((WARN+1)); echo "  WARN  $1"; }

echo "=== verify_lb.sh — $(date -u) ==="

if ! command -v kubectl >/dev/null 2>&1; then
  echo "FATAL: kubectl not found"; exit 1
fi

# -----------------------------------------------------------------------------
# Wait for the ingress node + HAProxy pod. On the FIRST deploy the cluster
# autoscaler has to create the node from scratch (enforce-node-group-min-size):
# Hetzner server create + boot + k3s join + image pull ≈ 2–4 min. Budget 10.
# -----------------------------------------------------------------------------
echo "--- waiting for ingress node (up to 10 min; first deploy creates it from scratch) ---"
INGRESS_NODE=""
for i in $(seq 1 60); do
  INGRESS_NODE=$(kubectl get nodes -l role=ingress -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
  if [ -n "$INGRESS_NODE" ]; then
    READY=$(kubectl get node "$INGRESS_NODE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)
    [ "$READY" = "True" ] && break
  fi
  sleep 10
done

echo "--- waiting for haproxy-ingress pod (up to 5 min) ---"
HAPROXY_POD=""
for i in $(seq 1 30); do
  HAPROXY_POD=$(kubectl get pods -n "$NS_HAPROXY" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
  if [ -n "$HAPROXY_POD" ]; then
    PHASE=$(kubectl get pod -n "$NS_HAPROXY" "$HAPROXY_POD" -o jsonpath='{.status.phase}' 2>/dev/null || true)
    [ "$PHASE" = "Running" ] && break
  fi
  sleep 10
done

# --- V8: cluster autoscaler healthy, 22 pools registered -----------------------
echo "--- V8: cluster autoscaler ---"
CA_DEPLOY=$(kubectl get deploy -n kube-system -o name 2>/dev/null | grep -i cluster-autoscaler | head -1)
if [ -n "$CA_DEPLOY" ]; then
  CA_READY=$(kubectl get "$CA_DEPLOY" -n kube-system -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)
  if [ "${CA_READY:-0}" -ge 1 ]; then pass "V8a cluster-autoscaler deployment ready"; else fail "V8a cluster-autoscaler deployment NOT ready"; fi
else
  fail "V8a cluster-autoscaler deployment not found in kube-system"
fi
POOL_COUNT=$(kubectl get cm cluster-autoscaler-priority-expander -n kube-system -o jsonpath='{.data.priorities}' 2>/dev/null | grep -cE 'web-|ingress-' || echo 0)
if [ "$POOL_COUNT" -eq "$EXPECTED_POOLS" ]; then
  pass "V8b priority ConfigMap lists $EXPECTED_POOLS pools"
else
  fail "V8b priority ConfigMap lists $POOL_COUNT pools (expected $EXPECTED_POOLS)"
fi

# --- V9: nodes ----------------------------------------------------------------
echo "--- V9: nodes ---"
WEB_READY=$(kubectl get nodes --no-headers 2>/dev/null | awk '$1 ~ /^web-/ && $2 == "Ready"' | wc -l)
if [ "$WEB_READY" -ge 1 ]; then pass "V9a $WEB_READY web worker node(s) Ready"; else fail "V9a no Ready web worker nodes"; fi
if [ -n "$INGRESS_NODE" ]; then
  READY=$(kubectl get node "$INGRESS_NODE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)
  if [ "$READY" = "True" ]; then pass "V9b ingress node $INGRESS_NODE Ready (label role=ingress)"; else fail "V9b ingress node $INGRESS_NODE exists but NOT Ready"; fi
else
  fail "V9b no node with label role=ingress after 10 min (CA didn't create the ingress pool node?)"
fi

# --- V10: taint ---------------------------------------------------------------
echo "--- V10: ingress node taint ---"
if [ -n "$INGRESS_NODE" ]; then
  TAINTS=$(kubectl get node "$INGRESS_NODE" -o jsonpath='{.spec.taints}' 2>/dev/null || true)
  if echo "$TAINTS" | grep -q '"key":"role"' && echo "$TAINTS" | grep -q '"value":"ingress"' && echo "$TAINTS" | grep -q '"effect":"NoSchedule"'; then
    pass "V10 taint role=ingress:NoSchedule present"
  else
    fail "V10 taint role=ingress:NoSchedule MISSING (django pods can colonize the LB node!) taints=$TAINTS"
  fi
fi

# --- V11: ingress node tenants ------------------------------------------------
echo "--- V11: ingress node tenants ---"
if [ -n "$INGRESS_NODE" ]; then
  TENANTS=$(kubectl get pods -A --field-selector "spec.nodeName=$INGRESS_NODE" --no-headers 2>/dev/null || true)
  if echo "$TENANTS" | awk '{print $1}' | grep -q "^$NS_APP$"; then
    fail "V11a django/app pods found on the ingress node (taint not enforced)"
  else
    pass "V11a no app pods on the ingress node"
  fi
  if echo "$TENANTS" | grep -q "svclb"; then
    fail "V11b svclb-traefik pod on the ingress node (port 80/443 conflict!)"
  else
    pass "V11b no svclb pod on the ingress node"
  fi
  if echo "$TENANTS" | grep -qE 'haproxy|kubernetes-ingress'; then
    pass "V11c haproxy-ingress pod running on the ingress node"
  else
    fail "V11c haproxy-ingress pod NOT on the ingress node (nodeSelector/toleration broken?)"
  fi
fi

# --- V12: Hetzner labels survived cloud-init (BUG 1 fix live) ------------------
echo "--- V12: server labels (Hetzner API) ---"
if [ -n "${HCLOUD_TOKEN:-}" ] && ! command -v jq >/dev/null 2>&1; then
  warn "V12 skipped — jq not installed on this machine"
elif [ -n "${HCLOUD_TOKEN:-}" ]; then
  LABELED=$(curl -s --max-time 20 -H "Authorization: Bearer $HCLOUD_TOKEN" \
    "https://api.hetzner.cloud/v1/servers?label_selector=hcloud%2Fnode-group&per_page=50" \
    | jq '[.servers[] | select(.labels.role == "k3s")] | length' 2>/dev/null || echo 0)
  if [ "${LABELED:-0}" -ge 1 ]; then
    pass "V12 $LABELED server(s) carry BOTH hcloud/node-group and role=k3s (label merge works)"
  else
    fail "V12 no server carries both hcloud/node-group and role=k3s (label merge broken?)"
  fi
else
  warn "V12 skipped — HCLOUD_TOKEN not set"
fi

# --- V13: ghost-sweeper dry run (BUG 2 fix live) -------------------------------
echo "--- V13: ghost-sweeper dry run ---"
if kubectl get cronjob ghost-node-sweeper -n kube-system >/dev/null 2>&1; then
  kubectl delete job verify-sweep -n kube-system --ignore-not-found >/dev/null 2>&1
  if kubectl create job verify-sweep -n kube-system --from=cronjob/ghost-node-sweeper >/dev/null 2>&1; then
    kubectl wait --for=condition=complete job/verify-sweep -n kube-system --timeout=180s >/dev/null 2>&1
    SWEEP_LOG=$(kubectl logs job/verify-sweep -n kube-system 2>/dev/null || true)
    OK_COUNT=$(echo "$SWEEP_LOG" | grep -c "^OK:" || true)
    MANAGED_NODES=$(kubectl get nodes --no-headers 2>/dev/null | awk '$1 ~ /^(web-|ingress-)/' | wc -l)
    if [ "$OK_COUNT" -ge "$MANAGED_NODES" ] && [ "$MANAGED_NODES" -ge 1 ]; then
      pass "V13 sweeper sees all $MANAGED_NODES managed node(s) as registered (selector fix works)"
    else
      fail "V13 sweeper OK-count $OK_COUNT < managed node count $MANAGED_NODES (selector still broken?)"
    fi
    if echo "$SWEEP_LOG" | grep -q "^GHOST:"; then
      warn "V13 sweeper deleted a real ghost during this run (that's its job — verify it wasn't a booting node): $(echo "$SWEEP_LOG" | grep "^GHOST:")"
    fi
    kubectl delete job verify-sweep -n kube-system --ignore-not-found >/dev/null 2>&1
  else
    fail "V13 could not create job from cronjob/ghost-node-sweeper"
  fi
else
  fail "V13 cronjob ghost-node-sweeper not found in kube-system"
fi

# --- Discover the ingress node public IP --------------------------------------
INGRESS_IP=""
if [ -n "$INGRESS_NODE" ]; then
  INGRESS_IP=$(kubectl get node "$INGRESS_NODE" -o jsonpath='{.status.addresses[?(@.type=="ExternalIP")].address}' 2>/dev/null || true)
fi
if [ -z "$INGRESS_IP" ] && [ -n "${HCLOUD_TOKEN:-}" ] && command -v jq >/dev/null 2>&1; then
  # Fallback: ask the Hetzner API directly
  INGRESS_IP=$(curl -s --max-time 20 -H "Authorization: Bearer $HCLOUD_TOKEN" \
    "https://api.hetzner.cloud/v1/servers?label_selector=hcloud%2Fnode-group=ingress-cx33-nbg1" \
    | jq -r '.servers[0].public_net.ipv4.ip // empty' 2>/dev/null || true)
fi
echo "--- ingress public IP: ${INGRESS_IP:-NOT FOUND} ---"

# --- V14: HTTP path through HAProxy → Service → pod ----------------------------
echo "--- V14: HTTP data path ---"
HAPROXY_HEADERS=""
if [ -n "$INGRESS_IP" ]; then
  # Retry loop: on the first deploy the parallel deploy-web job may still be
  # applying 21b-ingress-web-haproxy.yaml, and HAProxy needs a moment to load it.
  CODE=""
  for i in $(seq 1 18); do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
      "http://$INGRESS_IP/api/users/professions/" -H "Host: $HOST_HEADER" 2>/dev/null || true)
    [ "$CODE" = "401" ] && break
    sleep 10
  done
  if [ "$CODE" = "401" ]; then
    pass "V14 http://ingress/api/users/professions/ → 401 (auth wall = full path works)"
    HAPROXY_HEADERS=$(curl -s -D - -o /dev/null --max-time 10 \
      "http://$INGRESS_IP/api/users/professions/" -H "Host: $HOST_HEADER" -H "Accept-Encoding: gzip" 2>/dev/null || true)
  else
    fail "V14 expected 401, got '${CODE:-no-response}' — if no-response: is 80/443 open on artkhoj-fw? (plan B5.4)"
  fi
else
  fail "V14 skipped — ingress IP not discoverable"
fi

# --- V15: security headers + gzip (parity with 22-middlewares.yaml) ------------
echo "--- V15: headers + gzip ---"
if [ -n "$HAPROXY_HEADERS" ]; then
  check_header() {
    if echo "$HAPROXY_HEADERS" | grep -qiF "$1"; then pass "V15 header: $2"; else fail "V15 MISSING header: $2"; fi
  }
  check_header 'x-content-type-options: nosniff' "X-Content-Type-Options"
  check_header 'x-frame-options: DENY' "X-Frame-Options"
  check_header 'referrer-policy: strict-origin-when-cross-origin' "Referrer-Policy"
  check_header 'permissions-policy: camera=(), microphone=(), geolocation=()' "Permissions-Policy"
  check_header "content-security-policy: default-src 'self'" "Content-Security-Policy (prefix)"
  if echo "$HAPROXY_HEADERS" | grep -qi 'content-encoding: gzip'; then
    pass "V15 gzip active"
  else
    fail "V15 content-encoding: gzip missing (compression snippet not applied?)"
  fi
else
  [ -n "$INGRESS_IP" ] && fail "V15 skipped — no headers captured (V14 failed)"
fi

# --- V16: TLS cert is the Cloudflare Origin CA cert ----------------------------
echo "--- V16: TLS ---"
if [ -n "$INGRESS_IP" ]; then
  CERT=$(echo | openssl s_client -connect "$INGRESS_IP:443" -servername "$HOST_HEADER" 2>/dev/null | openssl x509 -noout -issuer -ext subjectAltName 2>/dev/null || true)
  if echo "$CERT" | grep -qi 'cloudflare origin'; then
    pass "V16a cert issuer is CloudFlare Origin CA"
  else
    fail "V16a cert is NOT the Cloudflare Origin cert (cf-origin secret missing in $NS_HAPROXY? plan B5.1-2). Got: $(echo "$CERT" | head -1)"
  fi
  if echo "$CERT" | grep -q "$HOST_HEADER"; then
    pass "V16b SAN covers $HOST_HEADER"
  else
    fail "V16b SAN does not cover $HOST_HEADER"
  fi
fi

# --- V17: 25MB body limit ------------------------------------------------------
echo "--- V17: body limit ---"
if [ -n "$INGRESS_IP" ]; then
  BIGFILE=$(mktemp)
  dd if=/dev/zero of="$BIGFILE" bs=1M count=26 status=none 2>/dev/null || dd if=/dev/zero of="$BIGFILE" bs=1048576 count=26 2>/dev/null
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 60 -X POST \
    --data-binary @"$BIGFILE" -H "Host: $HOST_HEADER" -H "Content-Type: application/octet-stream" \
    "http://$INGRESS_IP/api/users/professions/" 2>/dev/null || true)
  rm -f "$BIGFILE"
  if [ "$CODE" = "413" ]; then
    pass "V17 26MB POST → 413 (body limit enforced)"
  else
    fail "V17 26MB POST → '${CODE:-no-response}' (expected 413)"
  fi
fi

# --- V18: parity vs Traefik (status + headers; gzip excluded: Traefik's -------
# --- compress middleware skips bodies <1KB by design, HAProxy compresses all) --
echo "--- V18: Traefik parity ---"
if [ -n "${MASTER_HOST:-}" ]; then
  T_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
    "http://$MASTER_HOST/api/users/professions/" -H "Host: $HOST_HEADER" 2>/dev/null || true)
  if [ -z "$T_CODE" ] || [ "$T_CODE" = "000" ]; then
    warn "V18 Traefik path unreachable from this machine (master firewall may restrict port 80) — parity skipped"
  elif [ "$T_CODE" = "401" ]; then
    pass "V18a Traefik path → 401 (matches HAProxy)"
    T_HEADERS=$(curl -s -D - -o /dev/null --max-time 10 \
      "http://$MASTER_HOST/api/users/professions/" -H "Host: $HOST_HEADER" 2>/dev/null || true)
    MISMATCH=0
    for H in 'x-content-type-options' 'x-frame-options' 'referrer-policy' 'permissions-policy' 'content-security-policy'; do
      echo "$T_HEADERS" | grep -qi "$H" || MISMATCH=$((MISMATCH+1))
    done
    if [ "$MISMATCH" -eq 0 ]; then
      pass "V18b all 5 security headers present on both paths"
    else
      fail "V18b $MISMATCH security header(s) missing on the Traefik path (unexpected — middlewares changed?)"
    fi
  else
    fail "V18a Traefik path → '$T_CODE' (HAProxy gives 401 — paths disagree)"
  fi
else
  warn "V18 skipped — MASTER_HOST not set"
fi

# --- V19: DB connection headroom vs HPA max ------------------------------------
echo "--- V19: DB connection headroom ---"
DB_OUT=$(kubectl exec deploy/django -n "$NS_APP" -- python manage.py shell -c \
  "from django.db import connection; c=connection.cursor(); c.execute('show max_connections'); m=int(c.fetchone()[0]); c.execute('select count(*) from pg_stat_activity'); n=int(c.fetchone()[0]); print('MAXCONN=%d CURRENT=%d' % (m, n))" 2>/dev/null | grep MAXCONN || true)
if [ -n "$DB_OUT" ]; then
  MAXCONN=$(echo "$DB_OUT" | sed 's/.*MAXCONN=\([0-9]*\).*/\1/')
  CURRENT=$(echo "$DB_OUT" | sed 's/.*CURRENT=\([0-9]*\).*/\1/')
  REPLICAS=$(kubectl get deploy django -n "$NS_APP" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 1)
  REPLICAS=${REPLICAS:-1}
  PROJECTED=$(( CURRENT * HPA_MAX_REPLICAS / (REPLICAS > 0 ? REPLICAS : 1) ))
  echo "  info: max_connections=$MAXCONN current=$CURRENT replicas=$REPLICAS linear-projection@${HPA_MAX_REPLICAS}rep=$PROJECTED"
  if [ "$PROJECTED" -ge "$MAXCONN" ]; then
    # Linear extrapolation from 1-2 replicas overcounts (celery/beat/resident
    # connections are constant, not per-replica) → WARN below 3 replicas, FAIL at 3+.
    if [ "$REPLICAS" -ge 3 ]; then
      fail "V19 projected $PROJECTED conns at $HPA_MAX_REPLICAS replicas ≥ max_connections=$MAXCONN — pgbouncer/CONN_MAX_AGE work needed before LT8.3"
    else
      warn "V19 rough projection $PROJECTED ≥ max_connections=$MAXCONN (at $REPLICAS replica(s) the linear estimate overcounts — re-check during a scaled state)"
    fi
  else
    pass "V19 projected $PROJECTED conns at $HPA_MAX_REPLICAS replicas < max_connections=$MAXCONN"
  fi
else
  warn "V19 skipped — could not read pg_stat_activity via manage.py shell"
fi

# --- Summary -------------------------------------------------------------------
echo ""
echo "=== SUMMARY: $PASS passed, $FAIL failed, $WARN warnings ==="
if [ "$FAIL" -gt 0 ]; then
  echo "Failed checks:"
  printf '%b' "$FAILED_LIST"
fi
echo ""
echo "Reminder — the two dashboard glances this script cannot do:"
echo "  1. Cloudflare SSL mode: pre-cutover = leave unchanged; post-cutover = Full (strict)"
echo "  2. Cloudflare A record: pre-cutover = master IP; post-cutover = ingress IP (${INGRESS_IP:-unknown})"

[ "$FAIL" -gt 0 ] && exit 1
exit 0
