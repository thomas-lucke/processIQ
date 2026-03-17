# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for ProcessIQ.

Each ADR captures:

- the context that forced a decision
- the alternatives that were considered
- the trade-offs that were accepted

Use ADRs for decisions that materially affect:

- system structure
- persistence
- API boundaries
- AI orchestration
- deployment shape

## Index

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-use-langgraph-for-agent-orchestration.md) | Use LangGraph for agent orchestration | Accepted |
| [0002](0002-chromadb-for-vector-storage.md) | Use ChromaDB for vector storage | Accepted |
| [0003](0003-llm-provider-abstraction.md) | Abstract LLM provider access behind a single factory | Accepted |
| [0004](0004-fastapi-nextjs-over-streamlit.md) | Replace Streamlit with FastAPI and Next.js | Accepted |
| [0005](0005-investigation-loop-design.md) | Add a bounded investigation loop with tool calling | Accepted |

## ADR Conventions

- one architectural decision per file
- immutable history: do not rewrite old ADRs to hide trade-offs
- supersede with a new ADR when a decision changes materially
- update this index whenever a new ADR is added

For reader convenience, cross-link major ADRs from the relevant docs in `docs/`.
