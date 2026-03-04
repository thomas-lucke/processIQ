"""Minimal styling for ProcessIQ Streamlit UI.

Design principles:
- Clean neutral design with white/light background
- Dark text for readability
- Muted blue/slate accent color
- No gradients, no background images
- Generous whitespace, clear hierarchy
"""

import streamlit as st

# Color palette
COLORS = {
    "primary": "#475569",  # Slate-600 - main accent
    "primary_light": "#64748b",  # Slate-500
    "success": "#059669",  # Emerald-600
    "warning": "#d97706",  # Amber-600
    "error": "#dc2626",  # Red-600
    "text": "#1e293b",  # Slate-800
    "text_muted": "#64748b",  # Slate-500
    "border": "#e2e8f0",  # Slate-200
    "background": "#ffffff",
    "background_alt": "#f8fafc",  # Slate-50
    "surface": "#f8fafc",  # Slate-50 - card/panel backgrounds
}

# Confidence level colors
CONFIDENCE_COLORS = {
    "high": "#059669",  # >= 80%
    "medium": "#d97706",  # >= 60%
    "low": "#dc2626",  # < 60%
}

# Severity level colors
SEVERITY_COLORS = {
    "critical": "#dc2626",
    "high": "#ea580c",
    "medium": "#d97706",
    "low": "#65a30d",
}


def format_hours(hours: float | None) -> str | None:
    """Format a fractional-hours value as a human-readable string.

    Returns None for None/zero inputs (used in tables where None renders as blank).

    Examples:
        0.5   -> "30m"
        1.0   -> "1h"
        1.33  -> "1h 20m"
        2.0   -> "2h"
        0.083 -> "5m"
    """
    if hours is None or hours == 0:
        return None
    total_minutes = round(hours * 60)
    if total_minutes <= 0:
        return None
    h, m = divmod(total_minutes, 60)
    if h == 0:
        return f"{m}m"
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}m"


def get_confidence_color(confidence: float) -> str:
    """Get color for a confidence score."""
    if confidence >= 0.8:
        return CONFIDENCE_COLORS["high"]
    elif confidence >= 0.6:
        return CONFIDENCE_COLORS["medium"]
    return CONFIDENCE_COLORS["low"]


def get_severity_color(severity: str) -> str:
    """Get color for a severity level."""
    return SEVERITY_COLORS.get(severity.lower(), COLORS["text_muted"])


def apply_custom_css() -> None:
    """Apply minimal custom CSS to Streamlit app."""
    st.markdown(
        """
        <style>
        /* Clean, professional typography */
        .stApp {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }

        /* Reduce default padding for cleaner look */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1000px;
        }

        /* Style metric cards */
        [data-testid="stMetricValue"] {
            font-size: 1.5rem;
            font-weight: 600;
        }

        /* Clean expander styling */
        .streamlit-expanderHeader {
            font-weight: 500;
            color: #1e293b;
        }

        /* Subtle dividers */
        hr {
            border: none;
            border-top: 1px solid #e2e8f0;
            margin: 1.5rem 0;
        }

        /* Warning/info callouts */
        .stAlert {
            border-radius: 0.375rem;
        }

        /* Button styling - more subtle */
        .stButton > button {
            border-radius: 0.375rem;
            font-weight: 500;
            transition: all 0.15s ease;
        }

        /* Primary button */
        .stButton > button[kind="primary"] {
            background-color: #475569;
            border-color: #475569;
        }

        .stButton > button[kind="primary"]:hover {
            background-color: #334155;
            border-color: #334155;
        }

        /* Form input styling */
        .stTextInput > div > div > input,
        .stNumberInput > div > div > input,
        .stSelectbox > div > div {
            border-radius: 0.375rem;
        }

        /* Data editor / table styling */
        [data-testid="stDataFrame"] {
            border: 1px solid #e2e8f0;
            border-radius: 0.375rem;
        }

        /* Progress bar */
        .stProgress > div > div {
            background-color: #475569;
        }

        /* Hide Streamlit branding for cleaner look */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}

        /* Tabs styling */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 0.375rem 0.375rem 0 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def styled_metric(
    label: str, value: str, delta: str | None = None, color: str | None = None
) -> None:
    """Display a styled metric with optional color."""
    if color:
        st.markdown(
            f"""
            <div style="padding: 1rem; background: #f8fafc; border-radius: 0.375rem; border-left: 3px solid {color};">
                <div style="color: #64748b; font-size: 0.875rem; margin-bottom: 0.25rem;">{label}</div>
                <div style="color: {color}; font-size: 1.5rem; font-weight: 600;">{value}</div>
                {f'<div style="color: #64748b; font-size: 0.75rem;">{delta}</div>' if delta else ''}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.metric(label=label, value=value, delta=delta)


def confidence_badge(
    confidence: float,
    label: str = "Confidence",
    show_tooltip: bool = True,
) -> None:
    """Display a confidence score as a colored badge with optional tooltip.

    Args:
        confidence: Score between 0 and 1
        label: Label text for the badge
        show_tooltip: Whether to show info icon with tooltip
    """
    color = get_confidence_color(confidence)
    percentage = f"{confidence * 100:.0f}%"

    tooltip_html = ""
    if show_tooltip:
        tooltip_text = (
            "Data Completeness measures how much information is available for a reliable analysis. "
            "Higher scores mean more complete data (times, costs, constraints, business context). "
            "You can improve this by filling in missing values or adding business context in the sidebar."
        )
        tooltip_html = f"""
            <span style="
                display: inline-block;
                margin-left: 0.375rem;
                cursor: help;
                color: {color};
                font-size: 0.75rem;
            " title="{tooltip_text}">ⓘ</span>
        """

    st.markdown(
        f"""
        <span style="
            display: inline-flex;
            align-items: center;
            padding: 0.25rem 0.75rem;
            background: {color}15;
            color: {color};
            border-radius: 9999px;
            font-size: 0.875rem;
            font-weight: 500;
        ">
            {label}: {percentage}{tooltip_html}
        </span>
        """,
        unsafe_allow_html=True,
    )


def severity_badge(severity: str) -> None:
    """Display a severity level as a colored badge."""
    color = get_severity_color(severity)
    st.markdown(
        f"""
        <span style="
            display: inline-block;
            padding: 0.25rem 0.5rem;
            background: {color}15;
            color: {color};
            border-radius: 0.25rem;
            font-size: 0.75rem;
            font-weight: 500;
            text-transform: uppercase;
        ">
            {severity}
        </span>
        """,
        unsafe_allow_html=True,
    )


def section_header(title: str, subtitle: str | None = None) -> None:
    """Display a section header with optional subtitle."""
    st.markdown(f"### {title}")
    if subtitle:
        st.markdown(f"*{subtitle}*")


def info_callout(message: str, icon: str = "info") -> None:
    """Display an info callout."""
    if icon == "info":
        st.info(message)
    elif icon == "warning":
        st.warning(message)
    elif icon == "error":
        st.error(message)
    elif icon == "success":
        st.success(message)
