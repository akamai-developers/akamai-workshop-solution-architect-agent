# Module 4: Memory and durable sessions

**Goal:** make the agent remember the conversation, first in memory, then durably so it
survives a restart and works across replicas.

**The problem you will see:** ask a follow-up like "what did I just ask?" and a fresh
agent has no idea. Each turn starts blank.

**What you will learn:** the three layers of "remembering" (in-process, a file on a
volume, and Akamai Object Storage), and why a stateless service behind a NodeBalancer
needs the durable layer.

## Planned sections (raw, then framework)
1. Setup
2. In-process memory: one reused agent remembers within the process
3. Why that is not enough: a new process, or a second replica, forgets
4. Durable sessions by hand: persist and rehydrate the message list by `session_id`
5. The same with Strands `SessionManager` (file, then S3)
6. Akamai Object Storage as the session store (S3-compatible, `endpoint_url`)
7. Rehydrating across replicas behind a NodeBalancer
8. Things to know (session id design, what is persisted, cost of the durable layer)

## Needs
- For the durable demo: an Akamai Object Storage bucket and access keys
- `scripts/create_bucket.py` (created in this lab) to provision the bucket, called from the notebook

## Files
- `04_memory_and_sessions.ipynb`
- `scripts/create_bucket.py` — provisions the Object Storage bucket for the lab
- `architecture.html` — rendered to `../images/04_sessions_architecture.png`

_Status: scaffolded._
