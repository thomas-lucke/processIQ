# ADR-0004: Replace Streamlit with FastAPI + Next.js

**Date:** 2026-01-20
**Status:** Accepted

## Context

Phase 1 was built on Streamlit — one Python file serves both the UI and the agent logic. That was the right call for an MVP: fast to build, no frontend knowledge required, and good enough to validate the core idea.

But Streamlit has a ceiling. Every interaction re-runs the entire Python script. State management is a workaround (`st.session_state`). The component library is limited and not customizable. There's no way to build the interactive process graph visualization the product needs. And anyone who has worked in production AI engineering recognizes Streamlit as a prototyping tool — it signals "I got it working" rather than "I built a product."

For Phase 2, the visualization requirement alone forced a decision: React Flow (for interactive node graphs) is a React library. That means a JavaScript frontend. Once you need a separate frontend, Streamlit's value proposition collapses — you're better off with a proper API backend.

## Considered Options

1. **FastAPI backend + Next.js frontend** — clean split, FastAPI is the standard Python API framework for AI/ML backends, Next.js is the current standard for production React apps
2. **Keep Streamlit, add FastAPI alongside it** — run both simultaneously; Streamlit calls FastAPI for agent logic. Adds complexity without removing Streamlit's limitations.
3. **FastAPI + plain React (Vite/CRA)** — more control, but no server-side rendering, no file-based routing, more manual setup
4. **Gradio** — designed for ML demos, better than Streamlit for sharing models but still a prototyping tool with the same ceiling
5. **Django + HTMX** — server-rendered HTML with minimal JS; avoids a full JS framework but can't support React Flow or a rich interactive UI

## Decision

Use **FastAPI** for the backend and **Next.js** (App Router, TypeScript) for the frontend.

**FastAPI** is the production standard for Python AI/ML APIs. It's built by the same author as Pydantic and integrates with it natively — request and response models are just Pydantic classes, which means the same model definitions used throughout the agent layer can be reused directly in the API layer. Async support is built in, which matters when endpoints spend most of their time waiting on LLM API calls. Auto-generated OpenAPI docs come for free from type annotations.

**Next.js** with the App Router is the current standard for production React applications. React Flow runs in React, so Next.js is the natural host. Vercel (who makes Next.js) offers frictionless deployment with automatic GitHub integration. TypeScript support is first-class. The tradeoff is that Python Pydantic models can't be directly consumed by TypeScript — they're mirrored manually in `frontend/lib/types.ts`, which requires discipline to keep in sync.

The agent layer (`agent/`, `analysis/`, `models/`, `persistence/`) is untouched by this migration. FastAPI puts HTTP endpoints in front of `interface.py`. Nothing else moves.

## Trade-offs

- **Gains:** Interactive React Flow visualization, production-grade architecture, FastAPI/Pydantic integration, Vercel deployment, TypeScript type safety in the frontend, no Streamlit limitations
- **Costs/Risks:** Two codebases to maintain (Python + TypeScript). Pydantic models must be manually mirrored to TypeScript — a field added in Python but not TypeScript causes silent runtime errors. The team needs to know both Python and TypeScript. Significantly more setup than Streamlit.

## Consequences

The Streamlit UI has been removed. All UI features are implemented in `frontend/`. The `frontend/lib/types.ts` file must be updated whenever Pydantic models in `src/processiq/models/` or `api/schemas.py` change.
