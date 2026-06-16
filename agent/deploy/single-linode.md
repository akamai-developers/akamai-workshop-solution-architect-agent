# Run the agent on one Linode (Anthropic model, no GPU, no LKE)

This is the lightweight alternative to the LKE deploy. The agent loop is CPU and
I/O bound. It reads from MCP, calls a hosted model, and gates writes. None of that
needs a GPU or a Kubernetes cluster. A small shared Linode plus a hosted model
(Anthropic) is enough. You only need LKE and a GPU node when you self-host the
model with vLLM.

Use `deploy/compose.yaml` next to this file.

## 1. Provision the Linode

Create a small shared instance. 2 GB is fine.

- Plan: `g6-standard-1` (2 GB RAM, 1 vCPU, shared)
- Image: Ubuntu 24.04 LTS
- Add your SSH key

```bash
linode-cli linodes create \
  --type g6-standard-1 \
  --region us-ord \
  --image linode/ubuntu24.04 \
  --label akamai-sa-agent \
  --root_pass "$(openssl rand -base64 24)" \
  --authorized_keys "$(cat ~/.ssh/id_ed25519.pub)"
```

SSH in once it boots:

```bash
ssh root@<linode-ip>
```

## 2. Install Docker and the compose plugin

```bash
curl -fsSL https://get.docker.com | sh
docker --version
docker compose version
```

`get.docker.com` installs the engine and the `docker compose` plugin together.

## 3. Build and push the image

Build and push the agent image from your dev machine first. See the agent README,
or run `deploy/scripts/build_and_push.sh`. The image name in `compose.yaml` is
`ghcr.io/REPLACE_you/akamai-sa-agent:latest`; set it to yours.

If the GHCR package is private, log in on the Linode before bringing it up:

```bash
echo "$GHCR_PAT" | docker login ghcr.io -u REPLACE_you --password-stdin
```

## 4. Create the .env

Copy `compose.yaml` to the Linode (for example `/opt/akamai-sa-agent`) and create
`.env` next to it. Fill in real values.

```bash
mkdir -p /opt/akamai-sa-agent && cd /opt/akamai-sa-agent
cat > .env <<'EOF'
MODEL_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL_ID=claude-sonnet-4-5-20250929
LINODE_TOKEN=
DOCS_INDEX_PATH=/app/data/llms.txt
EOF
chmod 600 .env
```

`compose.yaml` also sets `MODEL_PROVIDER=anthropic` as an environment override,
so it wins even if the `.env` drifts. Keep `LINODE_TOKEN` scoped to least
privilege. `DOCS_INDEX_PATH` points the docs
specialist at the `llms.txt` index baked into the image.

## 5. Bring it up

```bash
docker compose up -d
docker compose ps
docker compose logs -f agent
```

`restart: unless-stopped` brings the container back after a crash or a reboot.

## 6. Verify

```bash
curl -s http://localhost:8080/healthz
# {"status":"ok"}

curl -s http://localhost:8080/invoke \
  -H 'content-type: application/json' \
  -d '{"message":"List the Linode regions I can deploy to."}'
```

You get back JSON with `response`, `model`, `provider`, and `session_id`. Writes
are denied by default and come back as a `pending_approval` token. Re-send the
same message with `"approve":"<token>"` to run the write.

To reach it from your laptop, swap `localhost` for the Linode IP and open port
8080 in a Cloud Firewall.

## 7. Optional: Discord bridge

The same image ships a Discord bridge that calls `/invoke` internally. Set
`DISCORD_TOKEN` in `.env` and add a second service running `python -m
discord_bridge` against the same image, or run it as a separate container on the
host. Leave `DISCORD_TOKEN` empty to skip it. The HTTP service above is all you
need for the core demo.
