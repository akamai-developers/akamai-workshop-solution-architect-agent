# Akamai SA Agent — Heartbeat Schedule

The proactive loop (`heartbeat.py`) runs inside the Discord bridge process. It is
**observe-and-report only** — it never changes the account. Every numeric fact
comes straight from the Linode API, not the model.

Times are in `HEARTBEAT_TZ` (default `America/New_York`). State (what has already
posted, last health state, known instances) lives in Postgres so nothing
double-posts and the schedule catches up after a restart.

## Actions

| Action | Cadence (ET) | Channel | What it posts |
|---|---|---|---|
| `cost_recap` | daily, 8–11 AM window | proactive | Instance + NodeBalancer count and estimated $/mo, broken down by plan |
| `security_drift` | every 30 min, **on change only** | proactive | Firewalls open to `0.0.0.0/0`, instances with no firewall, untagged instances — **LKE-managed resources ignored**. Posts only when the finding set changes (true drift, not a daily dump) |
| `health_check` | every 5 min | ops-alerts | vLLM / Postgres up→down and down→up transitions only (no spam) |
| `resource_diff` | every 15 min | proactive | Instances created or removed since the last scan |
| `Agent Online` | on startup | ops-alerts | Model + heartbeat status |
| `Heartbeat Error` | on a failed tick | ops-alerts | The exception (truncated) |

## Tuning (env vars)

| Variable | Default | Purpose |
|---|---|---|
| `HEARTBEAT_ENABLED` | `false` | Master switch |
| `HEARTBEAT_TZ` | `America/New_York` | Timezone for the daily windows |
| `PROACTIVE_CHANNEL_ID` | — | Channel for cost/security/inventory posts |
| `OPS_ALERTS_CHANNEL_ID` | — | Channel for health + error alerts |
| `HEARTBEAT_PUBLIC_FW_ALLOW` | — | Comma-separated firewall labels to ignore in the `0.0.0.0/0` check (e.g. an intentionally public vLLM endpoint) |

To change a window, edit the `*_WINDOW` constants at the top of `heartbeat.py`.
Adding an action: write a read-only data function, then call it from
`heartbeat_loop` behind a window or interval check and a `heartbeat_log` key.
