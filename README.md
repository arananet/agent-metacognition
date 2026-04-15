# Agent Meta Cognition — POC

> **Author:** Eduardo Arana  
> **Status:** Proof of Concept  
> **Model:** Claude (Anthropic SDK — `claude-opus-4-6`)

A proof-of-concept that applies the **Meta Cognition** paradigm to AI agents.
A metacognitive layer wraps a standard Claude agent, observes each task run,
evaluates performance, and generates updated instructions that are injected into
the agent's next invocation — enabling the agent to **self-evolve** without human
intervention.

---

## What is Meta Cognition?

Metacognition is _"thinking about thinking"_ — the capacity to monitor, evaluate,
and regulate one's own cognitive processes.  First formalised by developmental
psychologist John Flavell in 1979, it is now recognised as a key factor in
effective learning and problem-solving.

> _"Metacognition refers to one's knowledge concerning one's own cognitive processes
> and products or anything related to them."_  
> — Flavell, J. H. (1979)

In this POC the concept is mapped onto an agentic loop:

| Human metacognition | Agent equivalent |
|---|---|
| Observe your own thought process | Record the full agent response |
| Evaluate quality of reasoning | Isolated evaluator Claude call → `SelfEvaluationReport` |
| Identify failure modes | `failure_modes[]` + `reasoning_quality_score` |
| Adjust strategy for next attempt | `instruction_delta` prepended to system prompt |

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                       Metacognitive Loop                       │
│                                                                │
│  Task ──► BaselineAgent ──► response                          │
│                │                │                              │
│           [OBSERVE]        [EVALUATE] ◄── MetacognitiveEvaluator
│                │                │         (isolated Claude call)
│           [REFLECT]  ◄──── SelfEvaluationReport               │
│                │              (task_outcome, score,            │
│           [UPDATE]             failure_modes,                  │
│                │               instruction_delta)              │
│           delta store                                          │
│           {category → delta}                                   │
│                │                                               │
│  Next Task ──► BaselineAgent(system = delta + base_prompt)    │
└────────────────────────────────────────────────────────────────┘
```

**Key design decisions:**

- The evaluator is a **separate, isolated Claude call** — it never sees the
  agent's own system prompt or reasoning chain, avoiding self-serving bias.
- Instruction deltas are stored **per task category** in memory and evolve
  with each completed run.
- Both agents use the same model and base system prompt; the only difference
  is the prepended delta.

---

## Project Structure

```
agent-metacognition/
├── main.py                  # CLI — `--mode compare --tasks <file>`
├── requirements.txt
├── src/
│   ├── models.py            # Task, AgentRun, SelfEvaluationReport,
│   │                        #   MetacognitiveLog, ComparisonReport
│   ├── agent.py             # BaselineAgent  (streaming + prompt caching)
│   ├── evaluator.py         # MetacognitiveEvaluator (isolated judge)
│   ├── meta_agent.py        # MetaAgent  (observe → evaluate → reflect → update)
│   └── logger.py            # CycleLogger  (JSON Lines output)
├── tasks/
│   └── general.yaml         # 9 benchmark tasks (3 categories × 3 tasks)
├── results/                 # Runtime output (JSON reports + cycle logs)
└── .openspec/               # OpenSpec configuration and feature spec
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/)

### Install

```bash
pip install -r requirements.txt
```

### Run

```bash
export ANTHROPIC_API_KEY=sk-ant-...

python main.py --mode compare --tasks tasks/general.yaml
```

The CLI will:

1. Run a **BaselineAgent** (no self-reflection) on every task.
2. Run a **MetaAgent** (metacognitive loop) on the same tasks in the same order.
3. Print a side-by-side comparison table in the terminal.
4. Write two files to `results/`:
   - `comparison_<timestamp>.json` — full report with per-task outcomes and all cycle logs.
   - `cycles_<timestamp>.jsonl` — one JSON Line per metacognitive cycle for offline analysis.

### Optional flags

| Flag | Default | Description |
|---|---|---|
| `--tasks FILE` | — | YAML benchmark task file (required) |
| `--output DIR` | `results/` | Directory for JSON output |

---

## Benchmark Tasks

`tasks/general.yaml` contains 9 tasks across three categories:

| Category | Tasks | Pattern the meta agent learns |
|---|---|---|
| `logical_reasoning` | Seating constraints, Truth-teller puzzle, Compound inference | Systematic enumeration before elimination |
| `mathematical` | Mixture problem, Rate-work problem, Quadratic word problem | Define variables explicitly; set up equations first |
| `code_analysis` | Off-by-one bug, List mutation bug, Complexity analysis | Trace execution line by line; state error type and location |

Tasks within a category share a reasoning pattern so that a failure on task _N_
generates a useful `instruction_delta` that can improve performance on tasks
_N+1_ and _N+2_ — directly demonstrating within-category self-evolution.

---

## Output Schema

### `SelfEvaluationReport`

```jsonc
{
  "task_outcome": "The agent correctly identified the seating arrangement.",
  "success": true,
  "reasoning_quality_score": 7.5,    // 0–10
  "failure_modes": [],
  "instruction_delta": "When solving constraint-satisfaction problems, enumerate all candidate positions for the fixed variable first, then apply remaining constraints in order of most restrictive."
}
```

### `MetacognitiveLog` (one JSON Line per cycle)

```jsonc
{
  "cycle_id": "e3f7a1b2-...",
  "task_id": "lr-002",
  "task_category": "logical_reasoning",
  "timestamp": "2026-04-15T14:23:01.123456",
  "phase_observe":  { "agent_success": false, "injected_delta": null, "..." },
  "phase_evaluate": { "success": false, "reasoning_quality_score": 4.0, "..." },
  "phase_reflect":  { "previous_delta": null, "delta_changed": true },
  "phase_update":   { "new_delta": "When answering logic puzzles..." }
}
```

---

## References

### Metacognition — foundational theory

- **Flavell, J. H. (1979).** "Metacognition and cognitive monitoring: A new area of cognitive–developmental inquiry."  
  *American Psychologist, 34*(10), 906–911.  
  <https://doi.org/10.1037/0003-066X.34.10.906>

- **MIT Teaching + Learning Lab — Metacognition.**  
  Practical overview of metacognitive strategies and their role in deep learning.  
  <https://tll.mit.edu/teaching-resources/how-people-learn/metacognition/>

- **Schraw, G., & Dennison, R. S. (1994).** "Assessing Metacognitive Awareness."  
  *Contemporary Educational Psychology, 19*(4), 460–475.  
  Introduces the *Metacognitive Awareness Inventory* (knowledge of cognition +
  regulation of cognition) — the two-factor model this POC maps onto evaluate
  and update phases.

### Self-reflection and self-improvement in LLMs

- **Shinn, N., Cassano, F., Labash, A., Gopinath, A., Narasimhan, K., & Yao, S. (2023).**  
  "Reflexion: Language Agents with Verbal Reinforcement Learning."  
  *NeurIPS 2023.*  
  <https://arxiv.org/abs/2303.11366>  
  Closest prior work: agents reflect on failed task trajectories and store verbal
  reinforcement signals — directly inspired this POC's `instruction_delta` design.

- **Madaan, A., Tandon, N., Gupta, P., et al. (2023).**  
  "Self-Refine: Iterative Refinement with Self-Feedback."  
  *NeurIPS 2023.*  
  <https://arxiv.org/abs/2303.17651>  
  Shows that LLMs can iteratively improve their own outputs via self-generated
  feedback, without additional training.

- **Yao, S., Zhao, J., Yu, D., et al. (2023).**  
  "ReAct: Synergizing Reasoning and Acting in Language Models."  
  *ICLR 2023.*  
  <https://arxiv.org/abs/2210.03629>  
  Foundational agent paper combining chain-of-thought reasoning with tool use
  — underpins the single-turn agent loop used here.

### Prompt caching and efficient inference

- **Anthropic — Prompt Caching.**  
  Official documentation for the `cache_control` API used in this POC to cache
  stable system prompts across tasks.  
  <https://platform.claude.com/docs/en/build-with-claude/prompt-caching>

- **Anthropic — Claude API (Python SDK).**  
  SDK used for all agent and evaluator calls.  
  <https://github.com/anthropics/anthropic-sdk-python>

### Related frameworks

- **LangChain — Self-Evaluation Chains.**  
  Higher-level abstraction for LLM self-evaluation; this POC intentionally avoids
  LangChain to keep the metacognitive loop transparent and inspectable.  
  <https://python.langchain.com/docs/guides/evaluation/>

- **AutoGen (Microsoft) — Conversational Agent Patterns.**  
  Multi-agent framework where agents critique each other's outputs — a related but
  architecturally different approach to self-improvement.  
  <https://microsoft.github.io/autogen/>
