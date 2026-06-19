"""Cost and utilization advisor: real numbers, not the model's guesses.

Reads the account, the plan catalog, and per-instance CPU/network stats from the
Linode API and returns a deterministic report: monthly run-rate at list price,
charges accrued this period, and per-instance runtime + 24h CPU utilization with
a right-size verdict. The model only relays this text, so the figures are always
real (the same reason the diagram tools render in code).

GPU utilization is NOT exposed by the Linode API (/stats is CPU/network/disk
only), so GPU instances get an explicit caveat instead of a CPU-based verdict
that would mislead for GPU workloads - and GPUs are usually the bulk of the bill.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from strands import tool

from tools import _linode

NB_MONTHLY = 10.0  # Linode NodeBalancer list price


def _monthly(t: dict) -> float:
    return (t.get("price") or {}).get("monthly") or 0.0


def _avg_max_cpu(stats: dict) -> tuple[float | None, float | None]:
    cpu = [v for _ts, v in (stats.get("cpu") or []) if v is not None]
    if not cpu:
        return None, None
    return sum(cpu) / len(cpu), max(cpu)


def _age_days(created: str, now: datetime) -> int:
    try:
        c = datetime.fromisoformat(created.replace("Z", "+00:00"))
        return max((now - c).days, 0)
    except Exception:  # noqa: BLE001
        return 0


@tool
def cost_advisor() -> str:
    """Report real cost and utilization for the account and recommend right-sizing.

    Use this for "am I overpaying", "right-size my fleet", "what's idle", cost
    breakdowns, and any utilization question about instances, LKE nodes, or GPUs.
    Reports each resource's runtime, list-price monthly cost, 24h average CPU, and
    a verdict (idle / under-utilized / hot / right-sized) with a concrete smaller
    plan and the monthly saving where it applies. GPU compute utilization is not
    available from the API, so GPU nodes are flagged rather than guessed.

    Returns:
        A deterministic cost-and-utilization report with source-true numbers.
    """
    try:
        types = {t["id"]: t for t in _linode.get_all("/linode/types")}
        instances = _linode.get_all("/linode/instances")
        nbs = _linode.get_all("/nodebalancers")
        account = _linode.get("/account")
    except Exception as exc:  # noqa: BLE001
        return f"Could not read the account from the Akamai Cloud API: {type(exc).__name__}: {exc}"

    if not instances:
        return "No Linode instances found in this account."

    # Per-instance 24h stats, fetched in parallel (one /stats call each).
    def _fetch_stats(inst: dict):
        try:
            return inst["id"], _linode.get(f"/linode/instances/{inst['id']}/stats").get("data", {})
        except Exception:  # noqa: BLE001 - an instance may be too new for stats
            return inst["id"], {}

    with ThreadPoolExecutor(max_workers=8) as ex:
        stats = dict(ex.map(_fetch_stats, instances))

    # The next smaller plan in the SAME family (e.g. g6-dedicated-8 -> g6-dedicated-4):
    # fewer vCPUs and a lower price. Comparing by price alone crosses generations and
    # can return a same-or-bigger plan that merely costs less, which is bad advice.
    def _family(type_id: str) -> str:
        return re.sub(r"(-\d+)+$", "", type_id)

    def _next_down(type_id: str) -> dict | None:
        t = types.get(type_id, {})
        fam, vcpus, price = _family(type_id), t.get("vcpus") or 0, _monthly(t)
        cands = [
            x for x in types.values()
            if _family(x["id"]) == fam and 0 < (x.get("vcpus") or 0) < vcpus and _monthly(x) < price
        ]
        return max(cands, key=lambda x: x.get("vcpus") or 0) if cands else None

    now = datetime.now(timezone.utc)
    run_rate = sum(_monthly(types.get(i["type"], {})) for i in instances) + len(nbs) * NB_MONTHLY
    gpu_rate = sum(_monthly(types.get(i["type"], {})) for i in instances if "gpu" in i["type"])

    rows = []
    for i in instances:
        t = types.get(i["type"], {})
        price = _monthly(t)
        vcpus = max(t.get("vcpus", 1) or 1, 1)
        avg, mx = _avg_max_cpu(stats.get(i["id"], {}))
        rows.append((i, price, vcpus, avg, mx, _age_days(i.get("created", ""), now), "gpu" in i["type"]))
    rows.sort(key=lambda r: -r[1])  # most expensive first

    savings = 0.0
    lines = []
    for i, price, vcpus, avg, mx, age, gpu in rows:
        # Linode's CPU stat is summed per core (100% = one core), so divide by
        # vCPUs to get utilization as a percent of the whole box.
        util = (avg / vcpus) if avg is not None else None
        peak = (mx / vcpus) if mx is not None else None
        ustr = f"{util:.0f}%" if util is not None else " n/a"

        if gpu:
            verdict = f"GPU - GPU util not in the API (CPU {ustr} is only a weak hint; needs DCGM)"
        elif util is None:
            verdict = "no stats yet (too new)"
        elif util < 5:
            nd = _next_down(i["type"])
            if nd:
                save = price - _monthly(nd)
                savings += save
                verdict = f"IDLE -> downsize to {nd['id']} (save ${save:.0f}/mo) or remove"
            else:
                verdict = "IDLE -> already smallest in class; remove if unused"
        elif util < 20:
            nd = _next_down(i["type"])
            if nd:
                save = price - _monthly(nd)
                savings += save * 0.5
                verdict = f"under-utilized -> consider {nd['id']} (save ${save:.0f}/mo)"
            else:
                verdict = "under-utilized -> already smallest in class"
        elif peak is not None and peak > 75:
            verdict = "HOT -> consider a larger plan"
        else:
            verdict = "right-sized"

        lke = " [LKE]" if i.get("label", "").startswith("lke") and i["label"][3:4].isdigit() else ""
        lines.append(f"  {i['label'][:32]:32}{lke:6} {i['type']:20} ${price:>4.0f}/mo  up{age:>3}d  CPU {ustr:>5}  {verdict}")

    mtd = account.get("balance_uninvoiced")
    mtd_str = f"${mtd:.2f}" + (" (on credits)" if not mtd else "") if mtd is not None else "n/a"
    header = [
        "**Cost & utilization advisor**",
        f"Run-rate (list price): ${run_rate:,.0f}/mo (~${run_rate / 730:.2f}/hr)   accrued this period: {mtd_str}",
        f"{len(instances)} instances + {len(nbs)} NodeBalancer(s) (${len(nbs) * NB_MONTHLY:.0f}/mo). "
        f"GPUs are ${gpu_rate:,.0f}/mo ({gpu_rate / run_rate * 100:.0f}% of run-rate).",
        "",
        "Per resource (24h avg CPU as % of the box):",
    ]
    footer = [""]
    if savings >= 1:
        footer.append(f"Right-size opportunity (non-GPU, CPU-based): up to ~${savings:,.0f}/mo.")
    footer.append(
        "GPU utilization is not in the Linode API, so the GPU nodes - the bulk of the run-rate - "
        "can't be right-sized from here. Install a DCGM exporter on them to surface real GPU usage."
    )
    return "\n".join(header + lines + footer)
