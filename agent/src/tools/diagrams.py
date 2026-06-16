"""Deterministic architecture diagrams built from real account data.

The generic `diagram` tool asks the model to read a resource, parse nested JSON,
and hand-build nodes and edges. A small self-hosted model does that unreliably.
These tools do the read and the rendering in code, so the model makes ONE call
and the picture is always real and correct.
"""

from __future__ import annotations

import os

from strands import tool

from tools import _linode

# Where rendered diagrams are written. Relative to the process working directory.
DIAGRAM_DIR = os.environ.get("DIAGRAM_DIR", "diagrams")


def _is_gpu(plan: str) -> bool:
    return "gpu" in (plan or "").lower()


def _render(graph, name: str, summary: str) -> str:
    """Render a graphviz graph to the diagrams dir; return the path plus summary."""
    os.makedirs(DIAGRAM_DIR, exist_ok=True)
    try:
        path = graph.render(os.path.join(DIAGRAM_DIR, name), format="png", cleanup=True)
    except Exception as exc:  # noqa: BLE001 - e.g. missing 'dot' binary
        return f"Could not render the diagram (is graphviz 'dot' installed?): {type(exc).__name__}: {exc}"
    return f"Diagram saved to {path}\n{summary}"


@tool
def diagram_lke_cluster(cluster_id: int | None = None) -> str:
    """Draw an architecture diagram of an LKE (Kubernetes) cluster from real data.

    Use this whenever asked to draw or diagram an LKE / Kubernetes cluster. It
    reads the cluster and its node pools from the account and renders the control
    plane and each node pool with its real plan id and node count. You do not
    need to read anything first; this tool does it for you in one call.

    Args:
        cluster_id: The LKE cluster id. If omitted, a GPU cluster is chosen when
            one exists, otherwise the first cluster in the account.

    Returns:
        The path to the rendered PNG and a short text summary of the cluster.
    """
    try:
        import graphviz
    except Exception:
        return (
            "The diagram renderer is not installed. Install the diagram extra: "
            "pip install -e '.[diagram]' (and the graphviz 'dot' binary)."
        )

    try:
        clusters = _linode.get_all("/lke/clusters")
    except Exception as exc:  # noqa: BLE001 - surface a clean message to the model
        return f"Could not read LKE clusters: {type(exc).__name__}: {exc}"

    if not clusters:
        return "No LKE clusters found in this account."

    # Choose the cluster.
    cluster = None
    if cluster_id is not None:
        cluster = next((c for c in clusters if c.get("id") == cluster_id), None)
        if cluster is None:
            return f"No LKE cluster with id {cluster_id} in this account."
    else:
        # Prefer a cluster that has a GPU node pool; fall back to the first.
        for c in clusters:
            try:
                pools = _linode.get_all(f"/lke/clusters/{c['id']}/pools")
            except Exception:
                pools = []
            if any(_is_gpu(p.get("type", "")) for p in pools):
                cluster = c
                break
        if cluster is None:
            cluster = clusters[0]

    cid = cluster["id"]
    label = cluster.get("label", str(cid))
    region = cluster.get("region", "?")
    k8s = cluster.get("k8s_version", "?")

    try:
        pools = _linode.get_all(f"/lke/clusters/{cid}/pools")
    except Exception as exc:  # noqa: BLE001
        return f"Could not read node pools for cluster {cid}: {type(exc).__name__}: {exc}"

    # Build the graph.
    g = graphviz.Digraph(comment=label)
    g.attr(rankdir="TB")
    g.node(
        "cp",
        f"Control Plane\n{label}\nk8s {k8s} | {region}",
        shape="box",
        style="filled",
        fillcolor="#cfe8ff",
    )
    summary_pools = []
    for i, p in enumerate(pools):
        plan = p.get("type", "?")
        count = p.get("count", len(p.get("nodes", []) or []))
        fill = "#ffe0b3" if _is_gpu(plan) else "#d7f0d0"
        g.node(f"pool{i}", f"Node Pool\n{plan}\nx{count} node(s)", shape="box", style="filled", fillcolor=fill)
        g.edge("cp", f"pool{i}", label="manages")
        summary_pools.append(f"{plan} x{count}")

    pools_text = "; ".join(summary_pools) if summary_pools else "no node pools"
    return _render(
        g,
        f"lke-{cid}",
        f"Cluster '{label}' (id {cid}) in {region}, Kubernetes {k8s}.\n"
        f"Control plane manages {len(pools)} node pool(s): {pools_text}.",
    )


@tool
def diagram_network(all_firewalls: bool = False) -> str:
    """Draw the account's network topology from real data.

    Default view is the traffic flow: each NodeBalancer with the firewall in
    front of it and the Linodes behind it (firewall -> NodeBalancer -> backend
    Linodes). Use this for "diagram my network".

    Set all_firewalls=True to instead graph every firewall and what each one
    protects. Use this ONLY when the user explicitly asks to graph all firewalls.

    You do not need to read anything first; this tool does the reads for you.

    Returns:
        The path to the rendered PNG and a short text summary.
    """
    try:
        import graphviz
    except Exception:
        return (
            "The diagram renderer is not installed. Install the diagram extra: "
            "pip install -e '.[diagram]' (and the graphviz 'dot' binary)."
        )

    def _safe(path: str):
        try:
            return _linode.get_all(path)
        except Exception:
            return []

    firewalls = _safe("/networking/firewalls")

    # Map each firewall to what it is attached to (a NodeBalancer or a Linode).
    fw_devices: dict = {}
    nb_firewalls: dict = {}
    for fw in firewalls:
        devices = _safe(f"/networking/firewalls/{fw.get('id')}/devices")
        fw_devices[fw.get("id")] = devices
        for d in devices:
            ent = d.get("entity") or {}
            if ent.get("type") == "nodebalancer":
                nb_firewalls.setdefault(ent.get("id"), []).append(fw)

    # ---- all-firewalls view: every firewall and what it protects ----
    if all_firewalls:
        if not firewalls:
            return "No firewalls found in this account."
        g = graphviz.Digraph(comment="firewalls")
        g.attr(rankdir="TB")
        for fw in firewalls:
            fwid = f"fw-{fw.get('id')}"
            g.node(
                fwid,
                f"Firewall\n{fw.get('label', '?')}\n{fw.get('status', '')}",
                shape="box",
                style="filled",
                fillcolor="#ffcccc",
            )
            for d in fw_devices.get(fw.get("id"), []):
                ent = d.get("entity") or {}
                etype, eid = ent.get("type"), ent.get("id")
                prefix = "nb" if etype == "nodebalancer" else "linode" if etype == "linode" else str(etype)
                target = f"{prefix}-{eid}"
                g.node(
                    target,
                    f"{ent.get('label', eid)}\n({etype})",
                    shape="ellipse",
                    style="filled",
                    fillcolor="#ffe0b3" if etype == "nodebalancer" else "#d7f0d0",
                )
                g.edge(fwid, target, label="protects", style="dashed")
        return _render(g, "firewalls", f"{len(firewalls)} firewall(s) and what each protects.")

    # ---- default flow view: firewall -> NodeBalancer -> backend Linodes ----
    nodebalancers = _safe("/nodebalancers")
    instances = _safe("/linode/instances")
    ip_to_inst: dict = {}
    for inst in instances:
        for ip in inst.get("ipv4") or []:
            ip_to_inst[ip] = inst

    if not nodebalancers:
        return (
            "No NodeBalancers found in this account, so there is no traffic flow "
            "to draw. Ask me to graph all firewalls for the firewall view."
        )

    g = graphviz.Digraph(comment="network")
    g.attr(rankdir="LR")
    fw_drawn: set = set()
    fronted = 0
    total_backends = 0

    for nb in nodebalancers:
        nbid = nb.get("id")
        nbnode = f"nb-{nbid}"
        g.node(
            nbnode,
            f"NodeBalancer\n{nb.get('label', '?')}\n{nb.get('hostname', '')}",
            shape="box",
            style="filled",
            fillcolor="#ffe0b3",
        )

        # Firewall(s) in front of this NodeBalancer.
        for fw in nb_firewalls.get(nbid, []):
            fwnode = f"fw-{fw.get('id')}"
            if fwnode not in fw_drawn:
                g.node(
                    fwnode,
                    f"Firewall\n{fw.get('label', '?')}",
                    shape="box",
                    style="filled",
                    fillcolor="#ffcccc",
                )
                fw_drawn.add(fwnode)
            g.edge(fwnode, nbnode, label="allows")
        if nb_firewalls.get(nbid):
            fronted += 1

        # Linodes behind this NodeBalancer (from its config nodes' backend IPs).
        seen: set = set()
        for cfg in _safe(f"/nodebalancers/{nbid}/configs"):
            for node in _safe(f"/nodebalancers/{nbid}/configs/{cfg.get('id')}/nodes"):
                ip = (node.get("address") or "").split(":")[0]
                if not ip:
                    continue
                inst = ip_to_inst.get(ip)
                key = inst.get("id") if inst else ip
                if key in seen:
                    continue
                seen.add(key)
                total_backends += 1
                if inst:
                    bnode = f"linode-{inst.get('id')}"
                    g.node(
                        bnode,
                        f"{inst.get('label', 'Linode')}\n({inst.get('id')})",
                        shape="ellipse",
                        style="filled",
                        fillcolor="#d7f0d0",
                    )
                else:
                    bnode = f"ip-{ip}"
                    g.node(bnode, ip, shape="ellipse")
                g.edge(nbnode, bnode, label="backend")

    summary = (
        f"{len(nodebalancers)} NodeBalancer(s), {fronted} fronted by a firewall, "
        f"{total_backends} backend Linode(s)."
    )
    return _render(g, "network", summary)
