"""Proactive heartbeat: scheduled, observe-and-report posts to Discord.

A background asyncio task that runs alongside the discord client. There is no
cron and no external scheduler: if the bot is up, the heartbeat is up. Every
minute it checks a few time windows in the configured timezone and posts:

  - a daily cost snapshot and a security-drift report to the proactive channel,
  - vLLM/Postgres up->down / down->up alerts and instance inventory changes to
    the ops-alerts channel.

It is strictly read-only: it never changes the account. The numbers come from
the Linode API directly (not the model), so a cost figure is always real. State
lives in Postgres so it never double-posts and catches up after a restart; if
the database is unreachable, the heartbeat keeps running (without dedup) rather
than crash the bot.

Imported lazily by discord_bridge.main(), so importing the bridge for unit tests
never pulls discord in through this module.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
import httpx

from config.settings import settings
from tools import _linode

log = logging.getLogger("akamai_sa.heartbeat")

TICK_SECONDS = 60         # how often the loop wakes
HEALTH_SECONDS = 300      # vLLM/Postgres probe cadence
RESOURCE_SECONDS = 900    # instance inventory scan cadence
SECURITY_SECONDS = 1800   # security-drift scan cadence

# Daily window as [start_hour, end_hour) in settings.heartbeat_tz: the cost recap
# fires once when the local hour is in the window and it has not posted today; the
# window (not a single instant) is what gives free restart catch-up.
COST_RECAP_WINDOW = (8, 11)

# LKE auto-creates a firewall per cluster (label "lke-<id>") and names its nodes
# "lke<id>-...". Those are platform-managed, so the drift check ignores them and
# reports only the resources you own.
_LKE_FW = re.compile(r"^lke-\d+$")
_LKE_NODE = re.compile(r"^lke\d+-")

_COLORS = {"info": 0x3498DB, "success": 0x2ECC71, "warning": 0xE67E22, "error": 0xE74C3C}


# ----------------------------------------------------------------- Postgres state
# Dedup + small key/value state. Every call fails soft: a database hiccup must
# not take the bot down, it just means we lose dedup for that tick.

def _db_on() -> bool:
    return bool(settings.database_url)


def _connect():
    import psycopg  # lazy: only needed when a database is configured

    return psycopg.connect(settings.database_url)


def ensure_schema() -> None:
    if not _db_on():
        return
    try:
        with _connect() as c, c.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS heartbeat_log ("
                "  job_key TEXT PRIMARY KEY, posted_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS heartbeat_kv ("
                "  k TEXT PRIMARY KEY, v TEXT, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            c.commit()
    except Exception as exc:  # noqa: BLE001 - run without dedup if the DB is down
        log.warning("heartbeat schema setup failed: %s", exc)


def _already_posted(job_key: str) -> bool:
    if not _db_on():
        return False
    try:
        with _connect() as c, c.cursor() as cur:
            cur.execute("SELECT 1 FROM heartbeat_log WHERE job_key=%s", (job_key,))
            return cur.fetchone() is not None
    except Exception as exc:  # noqa: BLE001
        log.warning("heartbeat dedup read failed: %s", exc)
        return False


def _mark_posted(job_key: str) -> None:
    if not _db_on():
        return
    try:
        with _connect() as c, c.cursor() as cur:
            cur.execute("INSERT INTO heartbeat_log (job_key) VALUES (%s) ON CONFLICT DO NOTHING", (job_key,))
            c.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("heartbeat dedup write failed: %s", exc)


def _kv_get(k: str) -> str | None:
    if not _db_on():
        return None
    try:
        with _connect() as c, c.cursor() as cur:
            cur.execute("SELECT v FROM heartbeat_kv WHERE k=%s", (k,))
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as exc:  # noqa: BLE001
        log.warning("heartbeat kv read failed: %s", exc)
        return None


def _kv_set(k: str, v: str) -> None:
    if not _db_on():
        return
    try:
        with _connect() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO heartbeat_kv (k, v, updated_at) VALUES (%s, %s, now()) "
                "ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
                (k, v),
            )
            c.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("heartbeat kv write failed: %s", exc)


# ---------------------------------------------------------- action data (read-only)
# These run in a worker thread (httpx is blocking). The Linode API is the source
# of truth for every number, so a cost or a finding is never model-invented.

def _cost_recap_text() -> str:
    types = {t["id"]: t for t in _linode.get_all("/linode/types")}
    instances = _linode.get_all("/linode/instances")
    nbs = _linode.get_all("/nodebalancers")
    monthly = 0.0
    by_type: dict[str, int] = {}
    for i in instances:
        price = types.get(i.get("type"), {}).get("price") or {}
        monthly += price.get("monthly") or 0.0
        by_type[i.get("type", "?")] = by_type.get(i.get("type", "?"), 0) + 1
    monthly += len(nbs) * 10.0  # Linode NodeBalancers are ~$10/mo each
    lines = [
        "**Daily cost snapshot**",
        f"{len(instances)} instance(s), {len(nbs)} NodeBalancer(s)",
        f"Estimated **${monthly:,.0f}/mo** (~${monthly / 730:.2f}/hr), compute + NodeBalancers",
        "",
        "By plan:",
    ]
    for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
        each = (types.get(t, {}).get("price") or {}).get("monthly") or 0.0
        lines.append(f"  {count}x `{t}` (${each:,.0f}/mo each)")
    lines.append("\n_Estimate from plan list prices; excludes storage, transfer, and Object Storage._")
    return "\n".join(lines)


def _security_findings(allow: set[str]) -> tuple[str, str]:
    """Return (report_text, fingerprint) for non-LKE-managed resources.

    The fingerprint is a stable signature of the findings so the loop can post
    only when something actually changes, instead of dumping the same list daily.
    """
    fws = _linode.get_all("/networking/firewalls")
    public: list[str] = []
    protected_ids: set = set()
    for fw in fws:
        label = fw.get("label", str(fw.get("id")))
        managed = bool(_LKE_FW.match(label)) or label in allow
        if not managed:
            for r in (fw.get("rules") or {}).get("inbound") or []:
                ipv4 = (r.get("addresses") or {}).get("ipv4") or []
                if r.get("action") == "ACCEPT" and "0.0.0.0/0" in ipv4:
                    public.append(f"{label} (ports {r.get('ports', 'all')})")
                    break
        for d in _linode.get_all(f"/networking/firewalls/{fw.get('id')}/devices"):
            ent = d.get("entity") or {}
            if ent.get("type") == "linode":
                protected_ids.add(ent.get("id"))
    instances = [i for i in _linode.get_all("/linode/instances") if not _LKE_NODE.match(i.get("label", ""))]
    no_fw = [i for i in instances if i.get("id") not in protected_ids]
    untagged = [i for i in instances if not i.get("tags")]

    fp = ";".join(sorted(public) + [f"nofw:{i['id']}" for i in no_fw] + [f"untag:{i['id']}" for i in untagged])
    if not fp:
        return ("**Security drift** ✅ no findings on your resources (LKE-managed ignored).", "")
    lines = ["**Security drift** ⚠️ (your resources; LKE-managed ignored)"]
    if public:
        lines.append(f"\n\U0001f6a8 Firewalls open to 0.0.0.0/0: {len(public)}")
        lines += [f"  - {p}" for p in public[:10]]
    if no_fw:
        lines.append(f"\n⚠️ Instances with no Cloud Firewall: {len(no_fw)}")
        lines += [f"  - {i.get('label')} ({i.get('id')}) in {i.get('region')}" for i in no_fw[:10]]
    if untagged:
        lines.append(f"\n\U0001f3f7️ Untagged instances: {len(untagged)}")
        lines += [f"  - {i.get('label')} ({i.get('id')})" for i in untagged[:10]]
    lines.append("\n_Observe-and-report only; no changes made._")
    return ("\n".join(lines), fp)


def _instance_index() -> dict[str, str]:
    return {str(i["id"]): i.get("label", "?") for i in _linode.get_all("/linode/instances")}


def _vllm_ok() -> bool:
    try:
        url = settings.vllm_base_url.rstrip("/") + "/models"
        r = httpx.get(url, headers={"Authorization": f"Bearer {settings.vllm_api_key}"}, timeout=8.0)
        return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _postgres_ok() -> bool:
    if not _db_on():
        return False
    try:
        with _connect() as c, c.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------- Discord delivery

async def _channel(client, channel_id):
    if not channel_id:
        return None
    try:
        cid = int(channel_id)
    except (TypeError, ValueError):
        return None
    return client.get_channel(cid) or await client.fetch_channel(cid)


async def _post(client, channel_id, text: str) -> bool:
    """Send to a channel; return True only if it actually posted."""
    ch = await _channel(client, channel_id)
    if ch is None:
        log.warning("heartbeat: channel %r not set/accessible; skipping post", channel_id)
        return False
    while text:
        await ch.send(text[:1900])
        text = text[1900:]
    return True


async def _alert(client, title: str, message: str, level: str = "info") -> None:
    ch = await _channel(client, settings.ops_alerts_channel_id)
    if ch is None:
        return
    embed = discord.Embed(title=title, description=message[:4000], color=_COLORS.get(level, _COLORS["info"]))
    embed.set_footer(text="Akamai SA agent")
    try:
        await ch.send(embed=embed)
    except Exception as exc:  # noqa: BLE001 - alerts are best-effort
        log.warning("heartbeat alert failed: %s", exc)


# ------------------------------------------------------------------- the loop

def _allowlist() -> set[str]:
    return {s.strip() for s in (settings.heartbeat_public_fw_allow or "").split(",") if s.strip()}


async def _run_health(client) -> None:
    """Probe vLLM and Postgres; alert only on a state transition (no spam)."""
    for name, ok in (
        ("vLLM", await asyncio.to_thread(_vllm_ok)),
        ("Postgres", await asyncio.to_thread(_postgres_ok)),
    ):
        state = "up" if ok else "down"
        prev = _kv_get(f"health:{name}")
        if prev is None:
            _kv_set(f"health:{name}", state)
            continue
        if prev == "up" and not ok:
            await _alert(client, f"{name} Unreachable", f"{name} stopped responding.", "error")
        elif prev == "down" and ok:
            await _alert(client, f"{name} Recovered", f"{name} is reachable again.", "success")
        _kv_set(f"health:{name}", state)


async def _run_resource_diff(client) -> None:
    """Report instances created or removed since the last scan."""
    idx = await asyncio.to_thread(_instance_index)
    cur = set(idx)
    raw = _kv_get("known_instances")
    if raw is None:
        _kv_set("known_instances", json.dumps(sorted(cur)))
        return  # first run: establish a baseline silently
    prev = set(json.loads(raw))
    new, gone = cur - prev, prev - cur
    if new or gone:
        lines = ["**Instance inventory changed**"]
        lines += [f"  \U0001f195 created: {idx[i]} ({i})" for i in sorted(new)]
        lines += [f"  \U0001f5d1️ removed: ({i})" for i in sorted(gone)]
        if not await _post(client, settings.proactive_channel_id, "\n".join(lines)):
            return  # couldn't post; keep the old baseline so the change retries
        log.info("heartbeat resource diff (+%d/-%d)", len(new), len(gone))
    _kv_set("known_instances", json.dumps(sorted(cur)))


async def _run_security_drift(client) -> None:
    """Post the security report only when the set of findings changes."""
    text, fingerprint = await asyncio.to_thread(_security_findings, _allowlist())
    if fingerprint == (_kv_get("security_fp") or ""):
        return  # unchanged since last post (including a stable "no findings")
    if await _post(client, settings.proactive_channel_id, text):
        _kv_set("security_fp", fingerprint)  # only mark posted if it actually went out
        log.info("heartbeat posted security_drift (changed)")


async def heartbeat_loop(client) -> None:
    """Run proactive posts and health alerts until the bot stops."""
    tz = ZoneInfo(settings.heartbeat_tz)
    ensure_schema()
    log.info(
        "Heartbeat started (tz=%s, proactive_channel=%s, ops_channel=%s).",
        settings.heartbeat_tz, settings.proactive_channel_id, settings.ops_alerts_channel_id,
    )
    await _alert(client, "Agent Online", f"Model: {settings.model_label()}\nHeartbeat: active", "success")

    last_health = last_resource = last_security = 0.0
    while not client.is_closed():
        try:
            now = datetime.now(tz)
            today = now.strftime("%Y-%m-%d")

            if COST_RECAP_WINDOW[0] <= now.hour < COST_RECAP_WINDOW[1] and not _already_posted(f"cost_recap:{today}"):
                if await _post(client, settings.proactive_channel_id, await asyncio.to_thread(_cost_recap_text)):
                    _mark_posted(f"cost_recap:{today}")
                    log.info("heartbeat posted cost_recap")

            if time.monotonic() - last_security >= SECURITY_SECONDS:
                await _run_security_drift(client)
                last_security = time.monotonic()

            if time.monotonic() - last_health >= HEALTH_SECONDS:
                await _run_health(client)
                last_health = time.monotonic()

            if time.monotonic() - last_resource >= RESOURCE_SECONDS:
                await _run_resource_diff(client)
                last_resource = time.monotonic()

        except Exception as exc:  # noqa: BLE001 - one bad tick must not kill the loop
            log.exception("heartbeat tick failed")
            await _alert(client, "Heartbeat Error", str(exc)[:500], "error")

        await asyncio.sleep(TICK_SECONDS)
