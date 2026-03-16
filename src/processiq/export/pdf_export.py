"""PDF export for ProcessIQ improvement proposals.

Uses WeasyPrint to render a styled HTML template to PDF.
WeasyPrint produces vector PDFs with selectable, searchable text —
unlike canvas-based approaches (html2canvas, etc.) which rasterize.
"""

import logging
from datetime import date

from jinja2 import BaseLoader, Environment

from processiq.models.insight import AnalysisInsight
from processiq.models.process import ProcessData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<style>
  @page {
    size: A4;
    margin: 20mm 18mm 22mm 18mm;
    @bottom-right {
      content: "Page " counter(page) " of " counter(pages);
      font-size: 9pt;
      color: #888;
    }
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.6;
    color: #1a1a1a;
  }

  /* ── Cover header ── */
  .cover {
    border-bottom: 3px solid #2563eb;
    padding-bottom: 14pt;
    margin-bottom: 22pt;
  }
  .cover-label {
    font-size: 8.5pt;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #6b7280;
    margin-bottom: 6pt;
  }
  .cover-title {
    font-size: 20pt;
    font-weight: 700;
    color: #111827;
    line-height: 1.2;
  }
  .cover-meta {
    margin-top: 8pt;
    font-size: 9pt;
    color: #6b7280;
  }

  /* ── Section headings ── */
  h2 {
    font-size: 13pt;
    font-weight: 700;
    color: #111827;
    margin-top: 22pt;
    margin-bottom: 8pt;
    padding-bottom: 4pt;
    border-bottom: 1px solid #e5e7eb;
    page-break-after: avoid;
  }
  h3 {
    font-size: 10.5pt;
    font-weight: 600;
    color: #1e40af;
    margin-top: 14pt;
    margin-bottom: 4pt;
    page-break-after: avoid;
  }

  /* ── Body text ── */
  p { margin-bottom: 6pt; }

  /* ── Snapshot bar ── */
  .snapshot {
    display: flex;
    gap: 18pt;
    background: #f8fafc;
    border: 1px solid #e5e7eb;
    border-radius: 6pt;
    padding: 10pt 14pt;
    margin: 10pt 0 18pt;
  }
  .snapshot-item {
    display: flex;
    flex-direction: column;
  }
  .snapshot-value {
    font-size: 15pt;
    font-weight: 700;
    color: #111827;
  }
  .snapshot-label {
    font-size: 8pt;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  /* ── Step list ── */
  .step-list {
    list-style: none;
    margin: 6pt 0 12pt;
    padding: 0;
  }
  .step-list li {
    display: flex;
    align-items: baseline;
    gap: 8pt;
    padding: 4pt 0;
    border-bottom: 1px solid #f3f4f6;
    font-size: 9.5pt;
  }
  .step-num {
    min-width: 18pt;
    color: #9ca3af;
    font-size: 8.5pt;
  }
  .step-name { font-weight: 500; }
  .step-meta { color: #6b7280; font-size: 9pt; margin-left: auto; }

  /* ── Issue cards ── */
  .issue {
    border-left: 4px solid #e5e7eb;
    padding: 8pt 12pt;
    margin: 8pt 0;
    page-break-inside: avoid;
  }
  .issue.high   { border-color: #ef4444; }
  .issue.medium { border-color: #f97316; }
  .issue.low    { border-color: #eab308; }

  .badge {
    display: inline-block;
    font-size: 7.5pt;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 2pt 6pt;
    border-radius: 3pt;
    margin-bottom: 5pt;
  }
  .badge.high   { background: #fee2e2; color: #b91c1c; }
  .badge.medium { background: #ffedd5; color: #c2410c; }
  .badge.low    { background: #fef9c3; color: #854d0e; }

  .meta-line {
    font-size: 9pt;
    color: #6b7280;
    margin-top: 4pt;
  }
  .meta-line strong { color: #374151; }

  /* ── Recommendation cards ── */
  .rec {
    border: 1px solid #e5e7eb;
    border-radius: 6pt;
    padding: 10pt 14pt;
    margin: 10pt 0;
    page-break-inside: avoid;
  }
  .rec-title {
    font-size: 11pt;
    font-weight: 600;
    color: #111827;
    margin-bottom: 4pt;
  }
  .tag-row {
    display: flex;
    gap: 8pt;
    margin: 5pt 0;
    flex-wrap: wrap;
  }
  .tag {
    font-size: 8pt;
    background: #eff6ff;
    color: #1d4ed8;
    border: 1px solid #bfdbfe;
    border-radius: 3pt;
    padding: 1.5pt 6pt;
  }
  ol, ul { padding-left: 16pt; margin: 4pt 0 8pt; }
  li { margin-bottom: 2pt; font-size: 9.5pt; }

  /* ── Next steps table ── */
  .next-steps {
    margin-top: 18pt;
    border-top: 2px solid #2563eb;
    padding-top: 14pt;
  }
  .next-step-row {
    display: flex;
    gap: 12pt;
    margin-bottom: 8pt;
    page-break-inside: avoid;
  }
  .next-step-num {
    min-width: 20pt;
    height: 20pt;
    background: #2563eb;
    color: white;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 9pt;
    font-weight: 700;
    flex-shrink: 0;
  }
  .next-step-text strong { display: block; font-size: 10pt; color: #111827; }
  .next-step-text span   { font-size: 9pt; color: #6b7280; }

  /* ── Footer ── */
  .footer {
    margin-top: 28pt;
    padding-top: 10pt;
    border-top: 1px solid #e5e7eb;
    font-size: 8.5pt;
    color: #9ca3af;
    text-align: center;
  }
</style>
</head>
<body>

<!-- Cover -->
<div class="cover">
  <div class="cover-label">Process Improvement Proposal</div>
  <div class="cover-title">{{ process_name }}</div>
  <div class="cover-meta">Generated by ProcessIQ &nbsp;·&nbsp; {{ today }}</div>
</div>

<!-- Executive Summary -->
<h2>Executive Summary</h2>
<p>{{ insight.process_summary }}</p>

{% if process_data %}
<div class="snapshot">
  <div class="snapshot-item">
    <span class="snapshot-value">{{ process_data.steps | length }}</span>
    <span class="snapshot-label">Steps</span>
  </div>
  <div class="snapshot-item">
    <span class="snapshot-value">{{ "%.1f"|format(total_hours) }}h</span>
    <span class="snapshot-label">Per run</span>
  </div>
  {% if total_cost > 0 %}
  <div class="snapshot-item">
    <span class="snapshot-value">${{ "{:,.0f}".format(total_cost) }}</span>
    <span class="snapshot-label">Cost per run</span>
  </div>
  {% endif %}
  {% if insight.issues %}
  <div class="snapshot-item">
    <span class="snapshot-value">{{ insight.issues | length }}</span>
    <span class="snapshot-label">Issues found</span>
  </div>
  {% endif %}
  {% if insight.recommendations %}
  <div class="snapshot-item">
    <span class="snapshot-value">{{ insight.recommendations | length }}</span>
    <span class="snapshot-label">Recommendations</span>
  </div>
  {% endif %}
</div>
{% endif %}

<!-- Current Process -->
{% if process_data %}
<h2>Current Process</h2>
{% if process_data.description %}
<p>{{ process_data.description }}</p>
{% endif %}
<ul class="step-list">
  {% for step in process_data.steps %}
  <li>
    <span class="step-num">{{ loop.index }}.</span>
    <span class="step-name">{{ step.step_name }}</span>
    <span class="step-meta">
      {{ "%.1f"|format(step.average_time_hours) }}h
      {% if step.cost_per_instance and step.cost_per_instance > 0 %}
       &nbsp;·&nbsp; ${{ "{:,.0f}".format(step.cost_per_instance) }}
      {% endif %}
    </span>
  </li>
  {% endfor %}
</ul>
{% endif %}

<!-- Key Findings -->
{% if insight.issues %}
<h2>Key Findings</h2>
{% for issue in insight.issues %}
<div class="issue {{ issue.severity }}">
  <span class="badge {{ issue.severity }}">{{ issue.severity }}</span>
  <h3 style="margin-top:0; color:#111827;">{{ issue.title }}</h3>
  <p>{{ issue.description }}</p>
  {% if issue.affected_steps %}
  <p class="meta-line"><strong>Affected steps:</strong> {{ issue.affected_steps | join(", ") }}</p>
  {% endif %}
  {% if issue.root_cause_hypothesis %}
  <p class="meta-line"><strong>Root cause:</strong> {{ issue.root_cause_hypothesis }}</p>
  {% endif %}
</div>
{% endfor %}
{% endif %}

<!-- Recommendations -->
{% if insight.recommendations %}
<h2>Recommendations for Improvement</h2>
{% for rec in insight.recommendations %}
<div class="rec">
  <div class="rec-title">{{ loop.index }}. {{ rec.title }}</div>
  <p>{{ rec.description }}</p>
  <div class="tag-row">
    <span class="tag">Feasibility: {{ rec.feasibility }}</span>
    {% if rec.estimated_roi %}
    <span class="tag">ROI: {{ rec.estimated_roi }}</span>
    {% endif %}
  </div>
  {% if rec.expected_benefit %}
  <p class="meta-line"><strong>Expected benefit:</strong> {{ rec.expected_benefit }}</p>
  {% endif %}
  {% if rec.risks %}
  <p style="margin-top:6pt; font-size:9.5pt; font-weight:600;">Risks &amp; Trade-offs</p>
  <ul>{% for r in rec.risks %}<li>{{ r }}</li>{% endfor %}</ul>
  {% endif %}
  {% if rec.concrete_next_steps %}
  <p style="margin-top:6pt; font-size:9.5pt; font-weight:600;">How to get started</p>
  <ol>{% for s in rec.concrete_next_steps %}<li>{{ s }}</li>{% endfor %}</ol>
  {% endif %}
</div>
{% endfor %}
{% endif %}

<!-- Suggested Next Steps -->
<div class="next-steps">
  <h2 style="border:none; margin-top:0;">Suggested Next Steps</h2>
  <div class="next-step-row">
    <div class="next-step-num">1</div>
    <div class="next-step-text">
      <strong>Review &amp; Validate</strong>
      <span>Share these findings with your team to confirm accuracy.</span>
    </div>
  </div>
  <div class="next-step-row">
    <div class="next-step-num">2</div>
    <div class="next-step-text">
      <strong>Prioritize</strong>
      <span>Choose 1-2 recommendations to pilot - start with high-impact, low-complexity.</span>
    </div>
  </div>
  <div class="next-step-row">
    <div class="next-step-num">3</div>
    <div class="next-step-text">
      <strong>Plan</strong>
      <span>Define timeline, resources, and success metrics for each pilot.</span>
    </div>
  </div>
  <div class="next-step-row">
    <div class="next-step-num">4</div>
    <div class="next-step-text">
      <strong>Execute</strong>
      <span>Run the pilot and track results against baseline metrics.</span>
    </div>
  </div>
  <div class="next-step-row">
    <div class="next-step-num">5</div>
    <div class="next-step-text">
      <strong>Measure &amp; Iterate</strong>
      <span>Compare before/after metrics and refine the approach as needed.</span>
    </div>
  </div>
</div>

<div class="footer">Generated by ProcessIQ &nbsp;·&nbsp; {{ today }}</div>

</body>
</html>
"""

# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

_env = Environment(loader=BaseLoader(), autoescape=True)
_template = _env.from_string(_TEMPLATE)


def render_proposal_pdf(
    insight: AnalysisInsight,
    process_data: ProcessData | None,
) -> bytes:
    """Render an improvement proposal as a PDF and return the bytes.

    Args:
        insight: LLM-generated analysis insight.
        process_data: Source process data (optional — enriches the report).

    Returns:
        PDF content as bytes.
    """
    # Deferred import so WeasyPrint startup cost is only paid on first call.
    from weasyprint import HTML

    process_name = process_data.name if process_data else "Process"
    total_hours = (
        sum(s.average_time_hours for s in process_data.steps) if process_data else 0.0
    )
    total_cost = (
        sum(s.cost_per_instance or 0.0 for s in process_data.steps)
        if process_data
        else 0.0
    )

    html_content = _template.render(
        insight=insight,
        process_data=process_data,
        process_name=process_name,
        total_hours=total_hours,
        total_cost=total_cost,
        today=date.today().strftime("%B %d, %Y"),
    )

    logger.info("Rendering PDF for process=%s", process_name)
    pdf_bytes: bytes = HTML(string=html_content).write_pdf()
    logger.info("PDF rendered — %d bytes", len(pdf_bytes))
    return pdf_bytes
