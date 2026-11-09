#!/usr/bin/env bash
# Deploy the Helm chart on a local kind cluster with Postgres + pgvector and run the smoke test
# through the Kubernetes Service. Used locally and in CI.
set -euo pipefail
CLUSTER=${CLUSTER:-triage-e2e}
IMAGE=triage-agent:e2e
API_KEY=e2e-api-key
APPROVER=e2e-approver-token

if ! kind get clusters | grep -qx "$CLUSTER"; then
  kind create cluster --name "$CLUSTER" --wait 120s
fi
docker build -t "$IMAGE" .
kind load docker-image "$IMAGE" --name "$CLUSTER"

kubectl apply -f deploy/e2e/postgres.yaml
kubectl rollout status deploy/pgvector --timeout=180s
kubectl create secret generic triage-agent-secrets \
  --from-literal=API_KEY="$API_KEY" \
  --from-literal=APPROVER_TOKENS="analyst:$APPROVER" \
  --from-literal=DATABASE_URL="postgresql://triage:triage@pgvector:5432/triage" \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install triage deploy/helm/triage-agent \
  --set image.repository=triage-agent --set image.tag=e2e --set image.pullPolicy=Never \
  --set autoscaling.enabled=false --set replicaCount=2 --wait --timeout 180s

kubectl port-forward svc/triage-triage-agent 18080:80 >/tmp/pf.log 2>&1 &
PF=$!
trap 'kill $PF 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do curl -sf localhost:18080/healthz >/dev/null && break; sleep 1; done

python3 scripts/smoke.py http://localhost:18080 "$API_KEY" "$APPROVER"
kubectl get pods -o wide
