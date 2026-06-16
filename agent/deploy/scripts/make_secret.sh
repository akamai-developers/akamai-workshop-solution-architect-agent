#!/usr/bin/env bash
# Build the agent Secret in the cluster from your .env, so keys never land in a
# tracked YAML file. Run from the repo root after kagent is installed.
#
#   ./workshop/08_deploy_to_lke/scripts/make_secret.sh
set -euo pipefail

# Load .env into the environment.
set -a
# shellcheck disable=SC1091
source .env
set +a

kubectl create secret generic akamai-sa-agent-secrets \
  --namespace akamai-sa-agent \
  --from-literal=LINODE_TOKEN="${LINODE_TOKEN:?set LINODE_TOKEN in .env}" \
  --from-literal=VLLM_BASE_URL="${VLLM_BASE_URL:?set VLLM_BASE_URL in .env}" \
  --from-literal=VLLM_API_KEY="${VLLM_API_KEY:-placeholder}" \
  --from-literal=SESSION_BUCKET="${SESSION_BUCKET:-}" \
  --from-literal=SESSION_ACCESS_KEY="${SESSION_ACCESS_KEY:-}" \
  --from-literal=SESSION_SECRET_KEY="${SESSION_SECRET_KEY:-}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Created/updated secret akamai-sa-agent-secrets in namespace kagent."
