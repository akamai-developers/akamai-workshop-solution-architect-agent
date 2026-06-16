#!/usr/bin/env bash
# Create the imagePullSecret kagent uses to pull your private GHCR image.
# The token needs read:packages.
#
#   GITHUB_USER=you GITHUB_TOKEN=ghp_xxx \
#     ./workshop/08_deploy_to_lke/scripts/ghcr_pull_secret.sh
set -euo pipefail

: "${GITHUB_USER:?set GITHUB_USER}"
: "${GITHUB_TOKEN:?set GITHUB_TOKEN (a PAT with read:packages)}"

kubectl create secret docker-registry ghcr-pull \
  --namespace akamai-sa-agent \
  --docker-server=ghcr.io \
  --docker-username="$GITHUB_USER" \
  --docker-password="$GITHUB_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Created/updated imagePullSecret ghcr-pull in namespace kagent."
