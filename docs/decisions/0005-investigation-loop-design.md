# ADR-0005: Bounded Investigation Loop With Tool Calling

**Date:** 2026-03-17
**Status:** Accepted

## Context

The main analysis step already produces a structured `AnalysisInsight`, so adding a second pass only makes sense if it adds one of the following:

- stronger validation of important claims
- clearer handling of constraints
- a future extension point for evidence-gathering tools

The current Phase 2 tool set is intentionally narrow:

- `analyze_dependency_impact`
- `validate_root_cause`
- `check_constraint_feasibility`

All three operate on information already present in `AgentState`. That means the loop is not yet an external-evidence retrieval system. It is a verification and refinement step.

## Decision

Add a bounded post-analysis investigation loop implemented as:

- an `investigate` node that can request tool calls
- a LangGraph `ToolNode` that executes the tools
- a cycle limit enforced through state and routing
- a `finalize` step that can incorporate investigation findings into the final result

## Why This Was Chosen

### 1. It improves correctness without rerunning full analysis

The initial analysis prompt is broad. The investigation loop lets the system do narrower checks on:

- constraint feasibility
- dependency impact
- root-cause consistency

That is a better use of a second pass than simply re-running a large synthesis prompt on the same inputs.

### 2. It creates a clean extension point

The loop provides a natural place to add future tools that fetch genuinely new evidence, such as:

- issue-scoped similarity retrieval
- industry benchmark lookups
- standards or compliance references

Adding those later should not require changing the outer workflow topology.

### 3. It keeps cost and latency bounded

The loop stops when:

- no further tool calls are requested, or
- the cycle limit is reached

This is cheaper and easier to reason about than an open-ended agent loop.

## Important Implementation Notes

### Provider behavior is configuration-driven

The loop is often discussed as "Haiku-backed" because:

- the frontend defaults to Anthropic
- Anthropic defaults are lightweight enough for this task

But the actual implementation resolves models through provider defaults and task overrides. It is better described as a bounded tool-calling phase than as a permanently Haiku-specific design.

### Ollama path currently skips the loop

When the selected provider is `ollama`, the current implementation does not attempt tool calling and finalizes immediately.

### Current tools are verification tools

The existing tools inspect deterministic state. They can validate or refine a recommendation, but they do not bring in new outside evidence.

## Alternatives Considered

### No investigation loop

Pros:

- less complexity
- lower latency

Cons:

- no focused validation pass
- no ready-made extension point for future tools

### A second full synthesis pass

Pros:

- simpler mental model

Cons:

- expensive
- slower
- weak value when no new evidence is introduced

### Unbounded multi-step agent loop

Pros:

- potentially more flexible

Cons:

- harder to test
- harder to cost-control
- easier to let drift into non-deterministic behavior

## Consequences

Positive:

- clearer architecture for post-analysis validation
- simple place to add new tools later
- bounded cost profile

Negative:

- more graph complexity
- more state transitions to test
- current tool set is still limited by the information already in memory

## Follow-On Work

The design becomes much more valuable once the loop can gather new evidence. Likely next tools include:

- `query_similar_analyses`
- `search_industry_benchmarks`
- `fetch_process_standards`

Those additions should preserve the current loop shape while making the investigation phase substantively more useful.
