"""Process visualization component for ProcessIQ UI.

Renders an interactive flowchart of the process with severity coloring.

NOTE: This component is temporary. It will be replaced by the React Flow
frontend in Task 2.5. Only this file and build_process_figure() will be
deleted — build_graph_schema() and GraphSchema stay as the permanent contract.
"""

import logging

import streamlit as st

from processiq.analysis.visualization import build_graph_schema, build_process_figure
from processiq.models.insight import AnalysisInsight
from processiq.models.process import ProcessData

logger = logging.getLogger(__name__)


def render_process_visualization(
    process_data: ProcessData,
    analysis_insight: AnalysisInsight | None = None,
) -> None:
    """Render the interactive process visualization in Streamlit.

    Shows a layered flowchart with nodes colored by severity.
    Includes a Before/After toggle if recommendations exist.

    Graceful degradation:
    - < 2 steps: show nothing (no error)
    - No dependency data: render as linear sequence
    - No AnalysisInsight: all-gray nodes
    """
    if len(process_data.steps) < 2:
        logger.debug("visualization: fewer than 2 steps, skipping chart")
        return

    has_dep_data = any(s.depends_on for s in process_data.steps)
    if not has_dep_data:
        logger.debug("visualization: no dependency data, rendering as linear sequence")

    logger.info(
        "visualization: rendering chart for '%s' (%d steps)",
        process_data.name,
        len(process_data.steps),
    )

    try:
        schema = build_graph_schema(process_data, analysis_insight)
        figure = build_process_figure(schema)
        st.plotly_chart(figure, use_container_width=True)
    except Exception:
        logger.exception("visualization: chart rendering failed")
        # Fail silently — the rest of the results display still works
