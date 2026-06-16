# Module 1: Your first agent, from scratch and with a framework

**Goal:** understand exactly what an agent is by building the loop by hand, then build
the same thing with a framework in a fraction of the code.

**The problem you will see:** a model on its own guesses. Ask it the date or for some
math and it answers from training data, `finish_reason` stays `stop`, and no tool ever
runs.

**What you will learn:** an LLM call is an HTTP POST; `finish_reason` drives a
tool-calling loop; build that ReAct loop by hand with native tool calling, then do the
same with Strands; add built-in tools and your own with the `@tool` decorator; and the
vLLM flags that turn tool calling on.

## Sections (raw, then framework)
1. Setup
2. Configure url, model, and api key
3. Send your first model request (read `finish_reason`)
4. An LLM is not an agent (it guesses)
5. Build the agent loop by hand (native tool calling, branch on `finish_reason`)
6. The same agent with Strands (no plumbing)
7. Build your own tools (the `@tool` decorator)
8. Two vLLM configurations to know (the tool-call flags, the empty-tools array)

## Needs
- Python 3.11+
- A vLLM endpoint, or any OpenAI-compatible endpoint

## Files
- `01_first_agent.ipynb` — the lab
- `../images/01_agent_architecture.png` — the architecture diagram

_Status: complete._
