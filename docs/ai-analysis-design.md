# AI Analysis Design

This document explains how ProcessIQ combines deterministic process analysis with LLM-based extraction and reasoning.

It focuses on five areas:

1. the design philosophy
2. the extraction and analysis split
3. the prompt and model-selection system
4. the confidence, memory, and investigation mechanisms
5. the current limitations that matter for reviewers

## Design Principle

The central engineering principle is:

> Algorithms calculate facts. The LLM makes judgments.

In practice that means:

- deterministic code computes metrics, confidence, graph layout, and storage behavior
- LLM calls extract structure from unstructured input and interpret the deterministic facts into issues and recommendations

This separation makes the system easier to test, reason about, and debug.

## Two Different AI Pipelines

One source of confusion in earlier docs was treating "the AI layer" as one uniform pipeline. It is not.

### 1. Extraction pipeline

Implemented in:

- `src/processiq/ingestion/normalizer.py`
- `src/processiq/prompts/extract_*.j2`

Characteristics:

- uses Instructor-backed clients
- supports OpenAI and Anthropic extraction
- returns either structured process data or clarification needs
- also handles update and estimate flows when process data already exists

Important limitation:
Extraction does not currently run natively through Ollama. When `llm_provider="ollama"` is selected, the extraction pipeline detects this, logs a warning, and falls back to OpenAI for the extraction step. An OpenAI API key is therefore still required even when Ollama is the chosen provider.

### 2. Analysis pipeline

Implemented in:

- `src/processiq/agent/graph.py`
- `src/processiq/agent/nodes.py`
- `src/processiq/prompts/analyze.j2`
- `src/processiq/prompts/investigation_system.j2`

Characteristics:

- uses the LangChain model factory in `src/processiq/llm.py`
- executes a LangGraph workflow
- can run a bounded tool-calling investigation loop after initial analysis

## Deterministic Responsibilities

These parts are code-first, not prompt-first:

| Concern | Implementation |
| --- | --- |
| process metrics | `src/processiq/analysis/metrics.py` |
| confidence scoring | `src/processiq/analysis/confidence.py` |
| graph schema construction | `src/processiq/analysis/visualization.py` |
| ROI scaffolding and annualized metrics | `src/processiq/analysis/roi.py` |
| storage and retrieval | `src/processiq/persistence/` |
| investigation tools | `src/processiq/agent/tools.py` |

## LLM Responsibilities

The LLM is used for:

- extracting process steps from messy text or parsed documents
- generating clarification language
- identifying issues and "not-a-problem" work
- generating recommendations and ruled-out options
- deciding whether and how to use investigation tools
- answering follow-up questions

## Prompt System

Prompts are Jinja2 templates in `src/processiq/prompts/`.

### Extraction prompts

The current extraction router in `src/processiq/prompts/__init__.py` deterministically selects one of:

- `extract_new.j2`
- `extract_update.j2`
- `extract_estimate.j2`
- `extract_converse.j2`

Important correction:
`extraction.j2` still exists, but it is explicitly marked as deprecated in the prompt loader and is no longer the primary routing path.

### Analysis prompt

`analyze.j2` receives:

- deterministic metrics text
- business context
- constraints summary
- optional user concerns
- feedback history
- optional retrieved-memory context

The output target is `AnalysisInsight`.

### Investigation prompt

`investigation_system.j2` is the system prompt for the bounded tool loop.

It tells the model:

- what tools exist
- when to use them
- when to stop
- how to end with a compact investigation verdict

### Clarification and follow-up prompts

- `clarification.j2` generates targeted follow-up questions
- `followup.j2` answers post-analysis questions
- `improvement_suggestions.j2` generates post-extraction data-quality guidance

## Model Selection

`src/processiq/llm.py` resolves the model in this order:

1. explicit function parameters
2. analysis-mode presets where available
3. per-task env-var overrides
4. global defaults

Important nuance:

- analysis-mode presets are defined for extraction, clarification, explanation, and analysis
- investigation does not currently have mode-specific presets in `model_presets.py`
- investigation therefore falls back to provider defaults or `LLM_TASK_INVESTIGATION`

That means the investigation loop is not universally "Haiku by design" across every provider configuration, even though Anthropic defaults do land on Haiku-family behavior.

## Confidence Model

Confidence scoring is deterministic and implemented in `src/processiq/analysis/confidence.py`.

### Weights

- process completeness: `0.60`
- constraints completeness: `0.25`
- profile completeness: `0.15`

### Process scoring

Per-step penalties are applied when:

- `average_time_hours == 0.0`
- `cost_per_instance == 0.0`
- `error_rate_pct == 0.0`

Other rules:

- no dependencies in a multi-step process reduces all step scores by 10%
- a process with at least 5 steps gets a small bonus
- missing process description does not reduce score directly, but it generates improvement guidance

### Constraint scoring

If constraints are absent entirely, the model still proceeds with a partial score rather than forcing failure.

### Profile scoring

Profile completeness improves confidence, especially when prior improvements, rejected approaches, and preferences are present.

### Threshold

`ConfidenceResult.is_sufficient` compares the total score to `CONFIDENCE_THRESHOLD`, which defaults to `0.6`.

## LangGraph Workflow

The analysis graph does this:

```text
check_context
  -> request_clarification if confidence is too low
  -> memory_synthesis otherwise
memory_synthesis
  -> initial_analysis
initial_analysis
  -> investigate if issues exist and cycles are enabled
  -> finalize otherwise
investigate
  -> tools or finalize
tools
  -> investigate
finalize
```

### `memory_synthesis`

This node is more selective than earlier docs suggested.

In practice:

- `interface.py` retrieves prior analyses and filters out results below similarity `0.4`
- `memory_synthesis_node` only synthesizes "high signal" prior analyses at `>= 0.5`, unless persistent rejections or cross-session patterns already justify synthesis

That keeps low-quality retrievals out of the main analysis prompt.

## Investigation Loop

The investigation loop is intentionally bounded.

### Tools available today

- `analyze_dependency_impact`
- `validate_root_cause`
- `check_constraint_feasibility`

These tools are deterministic and read from `AgentState` using LangGraph `InjectedState`.

### Cycle control

The loop stops when:

- the model makes no more tool calls, or
- `cycle_count` reaches `max_cycles_override` or `settings.agent_max_cycles`

### Provider behavior

- OpenAI and Anthropic paths can use tool calling here
- `ollama` currently skips the tool loop and finalizes immediately

### Finalization behavior

The final AI message can include an `<investigation_verdict>` block.

`finalize_analysis_node` parses that block and can:

- nudge confidence up or down
- append a confidence note
- adjust issue severities
- attach tool findings for the UI

## Feedback and Memory

There are two feedback layers:

### Within-session feedback

Current-session accepted and rejected recommendations can be passed back into later analysis runs through `feedback_history`.

### Cross-session feedback

Rejected recommendations are persisted to the user's profile and session history, then retrieved for later analyses.

### Cross-session retrieval

ProcessIQ stores semantic analysis memory in ChromaDB and retrieves prior analyses for the same user before a new analysis run.

Those retrievals can influence:

- context sources returned to the frontend
- memory-brief synthesis
- persistent rejection guidance
- cross-session pattern warnings

## Why The Design Matters

This is the design intent behind the current architecture:

- avoid pretending the LLM is a calculator
- avoid throwing away useful user history
- avoid treating "chat" and "analysis" as the same problem
- create a clear extension point for stronger investigation tools later

## Current Limitations

### Extraction provider limitation

Ollama is not yet a first-class extraction provider.

### Investigation loop limitation

The current tools inspect internal state only. They verify and refine; they do not fetch new external evidence.

### Investigation depth slider

The slider is always rendered in the frontend. It is disabled only when the backend reports `demo_mode: true` from `GET /health`, which is controlled by the `DEMO_MODE` env var.

### Prompt/system maturity

The prompt system is structured and thoughtfully split, but it still depends on careful manual schema synchronization and prompt discipline rather than stronger code-generated contracts.
