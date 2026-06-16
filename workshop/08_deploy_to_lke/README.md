# Module 8: Deploy to Akamai LKE

**Goal:** ship the agent you built to Akamai Cloud on LKE: one image, a Deployment behind a
NodeBalancer, with durable sessions on Object Storage.

**The problem you will see:** everything so far runs in a notebook on your laptop. The
agent cannot serve requests, scale, or survive a restart, and off-cluster it cannot even
read its own region.

**What you will learn:** the orchestrator does its multi-agent work in one process, so you
deploy it like any HTTP service. Package it into one container image, push it to GHCR, run
it as a Deployment, put a NodeBalancer in front with a LoadBalancer Service, keep config in
a Secret, and keep sessions in Object Storage so any pod serves any conversation.

## Sections
1. Setup (Docker, kubectl, an LKE kubeconfig, a namespace)
2. The agent as an HTTP service (`src/api.py` with `AGENT_MODE=orchestrator`: run it, curl it)
3. Package it: the container image (Dockerfile, build, push to GHCR)
4. Secrets (the app Secret from `.env`, the GHCR pull secret)
5. Deploy (`kubectl apply` the Deployment and Service, wait for the NodeBalancer IP)
6. Prove it survives (delete a pod, the session continues via Object Storage)
7. Things to know (gated writes, cost and teardown, scaling)

## Needs
- Docker, `kubectl`, and an LKE cluster with its kubeconfig
- A GHCR account, with a token that has `write:packages` and `read:packages`
- The Object Storage bucket and keys from Module 4
- BILLED: the LKE cluster and a NodeBalancer (tear down when done)

## Files
- `08_deploy_to_lke.ipynb` — the lab
- `Dockerfile` — the image (serves the orchestrator over HTTP on :8080, MCP and docs index baked in)
- `manifests/deployment.yaml` — the Deployment (two replicas)
- `manifests/service.yaml` — the LoadBalancer Service (the NodeBalancer)
- `manifests/secret.example.yaml` — the Secret template
- `scripts/` — `build_and_push.sh`, `make_secret.sh`, `ghcr_pull_secret.sh`
- `../images/08_deploy_architecture.png` — the architecture diagram
- The HTTP service is `src/api.py` with `AGENT_MODE=orchestrator`; the orchestrator is `src/orchestrator.py`

_Status: complete (the deploy steps need your own LKE cluster and are billed)._
