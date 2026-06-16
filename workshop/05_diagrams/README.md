# Module 5: Diagrams that do not lie

**Goal:** give the agent a deterministic way to draw real architecture, instead of
asking a small model to invent one.

**The problem you will see:** ask the 7B to "diagram my GPU cluster" and build the
structure itself, and it fabricates the node pools (invented GPU models and counts),
because it has to read, parse, and build the diagram all in one pass.

**What you will learn:** when a task is read then transform then render, do not make the
small model orchestrate it. Build a deterministic tool that reads the account and renders
in code with graphviz, so the model makes one reliable call. `diagram_lke_cluster` and
`diagram_network`.

## Sections (raw, then framework)
1. Setup
2. Configure the model
3. The generic-tool path fumbles: the 7B fabricates the GPU pools
4. Why: read then parse then build is too long a chain (it draws clean JSON correctly)
5. A deterministic tool by hand: read the cluster, build the graph, render the PNG
6. The same wired into the agent as `diagram_lke_cluster`, one call
7. A second tool: `diagram_network` (traffic flow, with an all_firewalls mode)
8. Keep the generic diagram tool for designed or conceptual diagrams

## Needs
- A `LINODE_TOKEN` with at least one LKE cluster, and some networking to draw
- The `graphviz` Python package and the `dot` binary

## Files
- `05_diagrams.ipynb` — the lab
- `../images/05_diagrams_architecture.png` — the architecture diagram
- `diagrams/` — rendered PNGs, created when you run the lab

_Status: complete._
