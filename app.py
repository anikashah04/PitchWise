
import html
import inspect
import os
import queue
import re
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

# Load Streamlit Cloud secrets into environment variables.
try:
    for key, value in st.secrets.items():
        if isinstance(value, str):
            os.environ[key] = value
except Exception:
    pass

import pitchwise

st.set_page_config(
    page_title="PitchWise",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

AGENTS = [
    ("Market Demand Analyst", "Demand, target segment, willingness to pay"),
    ("Competitive Analyst", "Competitors, substitutes, defensibility"),
    ("Financial Analyst", "Pricing, unit economics, key assumptions"),
    ("Risk and Assumption Critic", "Ranked risks with validation tests"),
    ("Strategy Lead and Report Writer", "Executive assessment and verdict"),
    ("Presentation Designer", "Client-ready slide outline"),
]

EXAMPLES = {
    "DataBridge AI (enterprise software)": (
        "DataBridge AI",
        "Problem: Banks and large enterprises run legacy data systems that must be "
        "migrated to cloud data lakes and warehouses, a slow and error-prone process.\n"
        "Solution: An AI platform that automates SQL and stored procedure conversion "
        "and validates source-to-target data accuracy.\n"
        "Customers: Banks and large enterprises.\n"
        "Pricing: Rs 25 lakh implementation fee plus Rs 8 lakh per year for monitoring.\n"
        "Claims: 70% shorter migration timelines and 50% lower data engineering cost. "
        "Target of 20 enterprise clients in year one and profitability within 12 months.",
    ),
    "TiffinLink (consumer marketplace)": (
        "TiffinLink",
        "Problem: Office workers in Mumbai struggle to find affordable, healthy, "
        "home-style lunch, while home cooks have no reliable way to reach customers.\n"
        "Solution: A mobile app that connects home cooks with office workers for "
        "daily tiffin delivery.\n"
        "Customers: Office workers in Mumbai business districts.\n"
        "Pricing: Rs 150 per meal; the platform keeps a 20% fee.\n"
        "Claims: 5,000 daily orders within 6 months and break-even in month 8.",
    ),
    "LabGrade AI (education technology)": (
        "LabGrade AI",
        "Problem: Engineering faculty spend many hours grading lab reports, and "
        "feedback to students is slow and inconsistent.\n"
        "Solution: An AI tool that grades lab reports against a rubric and drafts "
        "feedback for each student.\n"
        "Customers: Engineering colleges in India.\n"
        "Pricing: Rs 2 lakh per college per year.\n"
        "Claims: Saves 60% of grading time and will sign 100 colleges in the first year.",
    ),
}

VERDICT_COLOURS = {
    "go": "#16A34A",
    "conditional go": "#7C3AED",
    "pivot": "#D97706",
    "no-go": "#DC2626",
    "no go": "#DC2626",
}

# ---------------------------------------------------------------------
# Original PitchWise visual identity
# ---------------------------------------------------------------------

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, .stApp, [class*="css"] {
    font-family: 'Inter', Arial, sans-serif;
}

.stApp {
    background: #FAF9FF;
    color: #211D35;
    overflow-x: hidden;
}

#MainMenu, footer, [data-testid="stHeader"],
[data-testid="stToolbar"] {
    visibility: hidden;
    height: 0;
}

.block-container {
    padding-top: 0 !important;
    padding-bottom: 3rem;
    max-width: 1180px;
}

/* Header */
.pw-top {
    background: #17152B;
    margin: 0 calc(50% - 50vw);
    padding: 0 calc(50vw - 50%);
}

.pw-top-inner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 68px;
}

.pw-brand {
    color: #FFFFFF;
    font-weight: 800;
    font-size: 1.55rem;
    letter-spacing: -0.04em;
}

.pw-dot {
    color: #A78BFA;
}

.pw-tag {
    color: #D8D2EE;
    font-size: 0.72rem;
    letter-spacing: 0.11em;
    text-transform: uppercase;
}

/* Hero */
.pw-hero {
    padding: 2rem 0 1.5rem;
}

.pw-title {
    font-size: 2rem;
    font-weight: 400;
    line-height: 1.3;
    margin: 0.3rem 0 0.8rem;
}

.pw-title b {
    color: #6D28D9;
    font-weight: 800;
}

.pw-rule {
    height: 4px;
    width: 58px;
    background: #A78BFA;
    margin-top: 1.2rem;
}

/* Section labels */
.pw-label {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #6B647D;
    margin: 0.4rem 0 0.7rem;
}

/* Inputs */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    border-radius: 8px !important;
    border: 1px solid #DDD6F3 !important;
    background: #FFFFFF !important;
    font-size: 0.95rem;
}

[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #8B5CF6 !important;
    box-shadow: 0 0 0 1px #8B5CF6 !important;
}

[data-baseweb="select"] > div {
    border-radius: 8px !important;
    border: 1px solid #DDD6F3 !important;
}

[data-testid="stWidgetLabel"] p {
    font-size: 0.84rem;
    font-weight: 600;
    color: #302A45;
}

/* Buttons */
.stButton > button,
[data-testid="stDownloadButton"] button {
    border-radius: 8px;
    font-weight: 600;
    border: 1px solid #D8D0ED;
    background: #FFFFFF;
    color: #302A45;
    padding: 0.55rem 1.2rem;
    transition: 0.2s ease;
}

.stButton > button:hover,
[data-testid="stDownloadButton"] button:hover {
    background: #F1EBFF;
    border-color: #8B5CF6;
    color: #5B21B6;
}

.stButton > button[kind="primary"] {
    background: #6D28D9;
    border-color: #6D28D9;
    color: #FFFFFF;
}

.stButton > button[kind="primary"]:hover {
    background: #5B21B6;
    border-color: #5B21B6;
    color: #FFFFFF;
}

/* Agent pipeline */
.pw-pipe {
    border-top: 1px solid #E5DFF2;
    background: #FFFFFF;
    border-radius: 8px;
    overflow: hidden;
}

.pw-step {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 13px 10px;
    border-bottom: 1px solid #EEEAF6;
    border-left: 4px solid transparent;
}

.pw-num {
    font-weight: 700;
    font-size: 0.82rem;
    color: #A29AB6;
    width: 24px;
    flex-shrink: 0;
}

.pw-stxt {
    flex: 1;
}

.pw-sname {
    font-weight: 600;
    font-size: 0.87rem;
    color: #29233E;
}

.pw-sdesc {
    font-size: 0.74rem;
    color: #827A96;
    margin-top: 3px;
    line-height: 1.4;
}

.pw-sstate {
    font-size: 0.64rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #9991AC;
    text-align: right;
}

.pw-step.active {
    border-left-color: #8B5CF6;
    background: #F5F0FF;
}

.pw-step.active .pw-sstate,
.pw-step.active .pw-num {
    color: #6D28D9;
}

.pw-step.done .pw-sstate,
.pw-step.done .pw-num {
    color: #15803D;
}

.pw-step.skipped {
    opacity: 0.45;
}

.pw-step.pending .pw-sname {
    color: #777087;
}

/* KPI cards */
.pw-kpis {
    display: grid;
    grid-template-columns: 1.5fr repeat(5, 1fr);
    gap: 10px;
    margin: 1.2rem 0 1.4rem;
}

.pw-kpi {
    border: 1px solid #E5DFF2;
    border-top: 4px solid #8B5CF6;
    border-radius: 8px;
    padding: 14px;
    background: #FFFFFF;
    min-width: 0;
}

.pw-kpi .k {
    font-size: 0.63rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #827A96;
}

.pw-kpi .v {
    font-size: 1.4rem;
    font-weight: 800;
    margin-top: 7px;
    line-height: 1.2;
    overflow-wrap: anywhere;
}

.pw-kpi.verdict .v {
    font-size: 1.25rem;
}

/* Tabs */
[data-testid="stTabs"] button[role="tab"] {
    font-weight: 600;
    font-size: 0.87rem;
    color: #6B647D;
    padding: 0.6rem 1rem;
}

[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #5B21B6;
}

[data-baseweb="tab-highlight"] {
    background-color: #8B5CF6 !important;
    height: 3px !important;
}

[data-baseweb="tab-border"] {
    background-color: #E5DFF2 !important;
}

/* Report */
.stMarkdown h1 {
    font-size: 1.7rem;
    font-weight: 800;
}

.stMarkdown h2 {
    font-size: 1.12rem;
    font-weight: 700;
    margin-top: 1.6rem;
    padding-bottom: 6px;
    border-bottom: 1px solid #E5DFF2;
}

.stMarkdown h3 {
    font-size: 0.98rem;
    font-weight: 700;
}

.stMarkdown p,
.stMarkdown li {
    font-size: 0.93rem;
    line-height: 1.7;
    color: #302A45;
}

.stMarkdown table {
    border-collapse: collapse;
    width: 100%;
    font-size: 0.86rem;
    margin: 0.6rem 0;
}

.stMarkdown th {
    background: #292342;
    color: #FFFFFF;
    text-align: left;
    padding: 9px 10px;
}

.stMarkdown td {
    border-bottom: 1px solid #E5DFF2;
    padding: 9px 10px;
    vertical-align: top;
}

/* Expanders */
[data-testid="stExpander"] {
    border: 1px solid #E5DFF2;
    border-radius: 8px;
    margin-bottom: 8px;
    background: #FFFFFF;
}

[data-testid="stExpander"] summary {
    font-weight: 600;
}

/* Slide cards */
.pw-slides {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 14px;
}

.pw-slide {
    border: 1px solid #E5DFF2;
    border-left: 4px solid #8B5CF6;
    border-radius: 8px;
    padding: 16px 18px;
    background: #FFFFFF;
}

.pw-slide .n {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #6D28D9;
    text-transform: uppercase;
}

.pw-slide .t {
    font-size: 1rem;
    font-weight: 700;
    margin: 6px 0 8px;
    color: #292342;
}

.pw-slide ul {
    margin: 0;
    padding-left: 1.1rem;
}

.pw-slide li {
    font-size: 0.84rem;
    color: #514968;
    margin-bottom: 5px;
    line-height: 1.5;
}

.pw-note {
    font-size: 0.78rem;
    color: #827A96;
    line-height: 1.6;
}

.pw-elapsed {
    font-size: 0.8rem;
    color: #6B647D;
    margin-top: 8px;
}

.pw-foot {
    border-top: 1px solid #E5DFF2;
    margin-top: 3rem;
    padding-top: 1rem;
    font-size: 0.75rem;
    color: #827A96;
}

@media (max-width: 900px) {
    .pw-kpis {
        grid-template-columns: repeat(2, 1fr);
    }

    .pw-slides {
        grid-template-columns: 1fr;
    }

    .pw-title {
        font-size: 1.55rem;
    }

    .pw-tag {
        font-size: 0.58rem;
        letter-spacing: 0.05em;
    }
}
</style>
"""


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def render_pipeline(done, active, skipped, idle=False):
    rows = []

    for i, (name, desc) in enumerate(AGENTS, start=1):
        if name in skipped:
            state, label = "skipped", "Skipped"
        elif name in done:
            state, label = "done", "Complete"
        elif name == active:
            state, label = "active", "In progress"
        else:
            state, label = "pending", "Ready" if idle else "Queued"

        rows.append(
            f'<div class="pw-step {state}">'
            f'<div class="pw-num">{i:02d}</div>'
            f'<div class="pw-stxt">'
            f'<div class="pw-sname">{html.escape(name)}</div>'
            f'<div class="pw-sdesc">{html.escape(desc)}</div>'
            f'</div>'
            f'<div class="pw-sstate">{label}</div>'
            f'</div>'
        )

    return '<div class="pw-pipe">' + "".join(rows) + "</div>"


def next_active(done, skipped):
    for name, _ in AGENTS:
        if name not in done and name not in skipped:
            return name
    return None


def extract_verdict(report):
    match = re.search(
        r"(?i)verdict\s*[:\-]\s*\**\s*"
        r"(conditional go|no-go|no go|pivot|go)\b",
        report or "",
    )
    return match.group(1).title() if match else "Not stated"


def severity_counts(text):
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

    for severity in re.findall(
        r"(?i)severity\W{0,4}\s*(critical|high|medium|low)",
        text or "",
    ):
        counts[severity.lower()] += 1

    return counts


def parse_slides(outline):
    slides = []
    current = None

    for raw in str(outline or "").splitlines():
        line = raw.strip()
        match = re.match(r"(?i)^slide\s*(\d+)\s*:\s*(.+)$", line)

        if match:
            current = {
                "n": match.group(1),
                "title": match.group(2).strip(),
                "bullets": [],
            }
            slides.append(current)
        elif current and re.match(r"^[-*•]\s+", line):
            bullet = re.sub(r"^[-*•]\s+", "", line).replace("**", "")
            current["bullets"].append(bullet)

    return slides


def fmt_time(seconds):
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def safe_name(name):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "Startup")
    return cleaned.strip("._") or "Startup"


def load_example():
    choice = st.session_state.get("example_choice")

    if choice in EXAMPLES:
        (
            st.session_state["startup_name"],
            st.session_state["pitch_text"],
        ) = EXAMPLES[choice]


def load_history():
    idx = st.session_state.get("history_choice")
    history = st.session_state.get("history", [])

    if idx is not None and 0 <= idx < len(history):
        st.session_state["result"] = history[idx]


# ---------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------

st.markdown(CSS, unsafe_allow_html=True)

st.session_state.setdefault("history", [])
st.session_state.setdefault("startup_name", "")
st.session_state.setdefault("pitch_text", "")

# Simplified header and hero.
st.markdown(
    """
    <div class="pw-top">
      <div class="pw-top-inner">
        <div class="pw-brand">PitchWise<span class="pw-dot">.</span></div>
        <div class="pw-tag">Multi-Agent Startup Analysis</div>
      </div>
    </div>
    <div class="pw-hero">
      <div class="pw-title">
        Smarter startup decisions, <b>one pitch at a time.</b>
      </div>
      <div class="pw-rule"></div>
    </div>
    """,
    unsafe_allow_html=True,
)

supports_progress = (
    "on_progress" in inspect.signature(pitchwise.run_pitchwise).parameters
)
supports_skip = (
    "skip_critic" in inspect.signature(pitchwise.run_pitchwise).parameters
)

col_in, col_pipe = st.columns([7, 5], gap="large")

with col_in:
    st.markdown(
        '<div class="pw-label">Startup Proposal</div>',
        unsafe_allow_html=True,
    )

    st.selectbox(
        "Load an example",
        ["Select an example"] + list(EXAMPLES.keys()),
        key="example_choice",
        on_change=load_example,
    )

    st.text_input(
        "Startup name",
        key="startup_name",
        placeholder="For example: DataBridge AI",
    )

    st.text_area(
        "Proposal summary",
        key="pitch_text",
        height=270,
        placeholder=(
            "Describe the problem, solution, target customers, pricing, "
            "and any growth or financial claims."
        ),
    )

    skip_critic = False

    if supports_skip:
        skip_critic = st.checkbox(
            "Omit the Risk and Assumption Critic (comparison run)",
            help=(
                "Run the pipeline without the adversarial review step "
                "to compare the results."
            ),
        )

    run_clicked = st.button("Run assessment", type="primary")
    status_slot = st.empty()

with col_pipe:
    st.markdown(
        '<div class="pw-label">Multi-Agent Analysis Pipeline</div>',
        unsafe_allow_html=True,
    )
    pipe_slot = st.empty()

current = st.session_state.get("result")

if current:
    skipped_now = (
        set() if current["critic"] else {"Risk and Assumption Critic"}
    )
    completed_now = {name for name, _ in AGENTS} - skipped_now

    pipe_slot.markdown(
        render_pipeline(completed_now, None, skipped_now),
        unsafe_allow_html=True,
    )
else:
    pipe_slot.markdown(
        render_pipeline(set(), None, set(), idle=True),
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------
# Run assessment
# ---------------------------------------------------------------------

if run_clicked:
    name = st.session_state["startup_name"].strip()
    proposal_text = st.session_state["pitch_text"].strip()

    if not name:
        status_slot.error("Enter a startup name.")

    elif len(proposal_text) < 150:
        status_slot.error(
            "The proposal summary is too short for a meaningful assessment "
            "(150 characters minimum)."
        )

    else:
        pitch = f"Startup: {name}\n\n{proposal_text}"
        tmpdir = tempfile.mkdtemp(prefix="pitchwise_")
        progress_q = queue.Queue()
        box = {}

        kwargs = {
            "output_dir": tmpdir,
            "verbose_print": False,
        }

        if supports_progress:
            kwargs["on_progress"] = (
                lambda i, total, agent: progress_q.put(agent)
            )

        if supports_skip:
            kwargs["skip_critic"] = skip_critic

        def worker():
            try:
                box["result"] = pitchwise.run_pitchwise_sync(
                    pitch,
                    **kwargs,
                )
            except Exception as exc:
                box["error"] = exc

        skipped = (
            {"Risk and Assumption Critic"} if skip_critic else set()
        )
        done = set()
        started = time.time()

        status_slot.info("Starting the PitchWise analysis...")

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while thread.is_alive():
            try:
                while True:
                    done.add(progress_q.get_nowait())
            except queue.Empty:
                pass

            active_agent = next_active(done, skipped)

            pipe_slot.markdown(
                render_pipeline(done, active_agent, skipped),
                unsafe_allow_html=True,
            )

            status_slot.markdown(
                f'<div class="pw-elapsed">'
                f'Analysis in progress · Elapsed '
                f'{fmt_time(time.time() - started)}'
                f'</div>',
                unsafe_allow_html=True,
            )

            time.sleep(0.5)

        thread.join()

        # Drain progress events that arrived as the worker finished.
        try:
            while True:
                done.add(progress_q.get_nowait())
        except queue.Empty:
            pass

        if "error" in box:
            message = str(box["error"])
            hint = ""

            if re.search(
                r"(?i)429|quota|rate.?limit|resource_exhausted",
                message,
            ):
                hint = (
                    " The model provider's rate limit or daily quota may "
                    "have been reached. Wait and retry, or check your "
                    "model configuration and API key."
                )

            status_slot.error(
                f"The assessment could not be completed.{hint}"
            )

            with st.expander("Technical detail"):
                st.code(message[:2000])

        else:
            res = box["result"]
            steps = res["steps"]
            elapsed = time.time() - started

            critic_text = next(
                (
                    text
                    for agent_name, text in steps
                    if agent_name == "Risk and Assumption Critic"
                ),
                "",
            )

            docx_bytes = (
                Path(res["docx_path"]).read_bytes()
                if res.get("docx_path")
                else None
            )

            pptx_bytes = (
                Path(res["pptx_path"]).read_bytes()
                if res.get("pptx_path")
                else None
            )

            result = {
                "startup": name,
                "report": res["report"],
                "verdict": extract_verdict(res["report"]),
                "steps": steps,
                "slides": res.get("slide_outline", ""),
                "docx": docx_bytes,
                "pptx": pptx_bytes,
                "seconds": elapsed,
                "critic": not skip_critic,
                "severity": severity_counts(critic_text),
                "words": len(res["report"].split()),
                "agents": len(steps),
                "time": datetime.now().strftime("%H:%M"),
            }

            st.session_state["result"] = result
            st.session_state["history"].append(result)
            current = result

            completed_agents = {agent_name for agent_name, _ in AGENTS}
            pipe_slot.markdown(
                render_pipeline(completed_agents - skipped, None, skipped),
                unsafe_allow_html=True,
            )

            status_slot.success(
                f"Assessment complete in {fmt_time(elapsed)}."
            )


# ---------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------

if current:
    result = current
    colour = VERDICT_COLOURS.get(
        result["verdict"].lower(),
        "#292342",
    )
    severity = result["severity"]

    critical_value = (
        str(severity["critical"]) if result["critic"] else "n/a"
    )
    high_value = (
        str(severity["high"]) if result["critic"] else "n/a"
    )

    st.markdown(
        f'<div class="pw-label" style="margin-top:2rem">'
        f'Assessment: {html.escape(result["startup"])}'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="pw-kpis">
          <div class="pw-kpi verdict" style="border-top-color:{colour}">
            <div class="k">Verdict</div>
            <div class="v" style="color:{colour}">
              {html.escape(result["verdict"])}
            </div>
          </div>
          <div class="pw-kpi">
            <div class="k">Critical risks</div>
            <div class="v">{critical_value}</div>
          </div>
          <div class="pw-kpi">
            <div class="k">High risks</div>
            <div class="v">{high_value}</div>
          </div>
          <div class="pw-kpi">
            <div class="k">Agents run</div>
            <div class="v">{result["agents"]}</div>
          </div>
          <div class="pw-kpi">
            <div class="k">Elapsed</div>
            <div class="v">{fmt_time(result["seconds"])}</div>
          </div>
          <div class="pw-kpi">
            <div class="k">Report words</div>
            <div class="v">{result["words"]}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_report, tab_agents, tab_slides, tab_export = st.tabs(
        [
            "Executive Report",
            "Agent Analyses",
            "Slide Outline",
            "Export",
        ]
    )

    with tab_report:
        st.markdown(result["report"])

    with tab_agents:
        st.markdown(
            '<div class="pw-note">'
            "Review the output of each specialist agent. The Strategy Lead "
            "consolidates the analyses into the final assessment."
            "</div>",
            unsafe_allow_html=True,
        )

        for i, (agent_name, agent_text) in enumerate(
            result["steps"],
            start=1,
        ):
            with st.expander(f"{i:02d}  {agent_name}", expanded=False):
                st.markdown(agent_text)

    with tab_slides:
        slides = parse_slides(result["slides"])

        if slides:
            cards = []

            for slide in slides:
                bullets = "".join(
                    f"<li>{html.escape(bullet)}</li>"
                    for bullet in slide["bullets"]
                )

                cards.append(
                    '<div class="pw-slide">'
                    f'<div class="n">Slide '
                    f'{html.escape(slide["n"])}</div>'
                    f'<div class="t">{html.escape(slide["title"])}</div>'
                    f"<ul>{bullets}</ul>"
                    "</div>"
                )

            st.markdown(
                '<div class="pw-slides">'
                + "".join(cards)
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("No slide outline was produced for this run.")

    with tab_export:
        base = safe_name(result["startup"])

        full_markdown = "\n\n---\n\n".join(
            f"# {agent_name}\n\n{agent_text}"
            for agent_name, agent_text in result["steps"]
        )

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            if result["docx"]:
                st.download_button(
                    "Word report",
                    result["docx"],
                    file_name=f"{base}_Executive_Report.docx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                )

        with c2:
            if result["pptx"]:
                st.download_button(
                    "PowerPoint deck",
                    result["pptx"],
                    file_name=f"{base}_Client_Presentation.pptx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "presentationml.presentation"
                    ),
                )

        with c3:
            st.download_button(
                "Report (Markdown)",
                result["report"],
                file_name=f"{base}_report.md",
                mime="text/markdown",
            )

        with c4:
            st.download_button(
                "All agent outputs",
                full_markdown,
                file_name=f"{base}_agent_outputs.md",
                mime="text/markdown",
            )


# ---------------------------------------------------------------------
# Session history and methodology
# ---------------------------------------------------------------------

if len(st.session_state["history"]) > 1:
    with st.expander("Session History"):
        labels = [
            f'{item["time"]} | {item["startup"]} | {item["verdict"]}'
            for item in st.session_state["history"]
        ]

        st.selectbox(
            "View an earlier assessment",
            options=list(range(len(labels))),
            format_func=lambda i: labels[i],
            key="history_choice",
            on_change=load_history,
        )

with st.expander("Method and Limitations"):
    st.markdown(
        f"""
        **Design:** Six specialist agents assess the proposal in sequence.
        The Risk and Assumption Critic challenges the preceding analyses.
        The Strategy Lead synthesises the findings, and the Presentation
        Designer creates a slide outline.

        **Model:** `{html.escape(os.environ.get("PITCHWISE_MODEL", pitchwise.DEFAULT_MODEL))}`

        **Limitations:** The assessment is based on the submitted proposal
        and the model's general knowledge. No live market research is
        performed, so market figures and competitor claims should be
        independently verified. Financial figures are treated as claims
        unless independently substantiated. The output supports decision
        making and does not replace due diligence.
        """
    )

st.markdown(
    '<div class="pw-foot">'
    "PitchWise · Multi-agent startup assessment · "
    "Decision support, not financial or investment advice."
    "</div>",
    unsafe_allow_html=True,
)
