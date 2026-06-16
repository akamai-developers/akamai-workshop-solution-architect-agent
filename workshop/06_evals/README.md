# Module 6: Evals, turn "it felt fine" into a number

**Goal:** measure the agent's behavior instead of eyeballing it, so you can find and fix
real gaps with confidence.

**The problem you will see:** the same cost question gives different answers across runs
(for example $233.28 on one run, $236.52 on the next). One good-looking answer is not
evidence for a stochastic model.

**What you will learn:** build a small eval harness with structural checks (which tool
ran, did the approval gate block the write), run each case with `--repeat` for an honest
pass rate, find the cost gap (the model skips the calculator), fix it in the prompt, and
watch the pass rate rise.

## Sections (by hand, then the repo suite)
1. Setup (inline agent, write-tool stubs, a slim approval gate)
2. Why one good answer is not enough (run the cost prompt 3 times, watch it wander)
3. A behavioral eval by hand (read the tools off `agent.messages`, read the gate)
4. From one check to a dataset (`EvalCase` + `run_case`)
5. Run with `--repeat` for an honest pass rate (PASS / FLAKY / FAIL)
6. The eval finds a real gap (cost is flaky)
7. Fix it, watch the number rise (eval-driven development)
8. The full suite in the repo (`evals/`, `python -m evals.run`)

## Needs
- The same vLLM endpoint from the earlier modules (no account or MCP needed for the inline demo)

## Files
- `06_evals.ipynb` — the lab
- `../images/06_evals_architecture.png` — the architecture diagram

_Status: complete._
