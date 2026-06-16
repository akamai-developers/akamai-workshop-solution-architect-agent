#!/usr/bin/env bash
# Build the agent image and push it to GHCR. Run from the repo root.
#
#   GITHUB_USER=you GITHUB_TOKEN=ghp_xxx IMAGE=ghcr.io/you/akamai-sa-agent:latest \
#     ./workshop/08_deploy_to_lke/scripts/build_and_push.sh
#
# The token needs write:packages to push.
set -euo pipefail

IMAGE="${IMAGE:-ghcr.io/REPLACE_your_org/akamai-sa-agent:latest}"

if [[ -n "${GITHUB_TOKEN:-}" && -n "${GITHUB_USER:-}" ]]; then
  echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USER" --password-stdin
fi

docker build -f workshop/08_deploy_to_lke/Dockerfile -t "$IMAGE" .
docker push "$IMAGE"
echo "Pushed $IMAGE"
