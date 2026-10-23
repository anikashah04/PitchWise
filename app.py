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

# Load secrets (Streamlit Cloud) into the environment before the crew is used
try:
    for _key, _val in st.secrets.items():
        if isinstance(_val, str):
            os.environ[_key] = _val
except Exception:
    pass  # running locally with environment variables

import pitchwise  # noqa: E402

st.set_page_config(page_title="PitchWise", layout="wide", initial_sidebar_state="collapsed")

# --------------------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------------------
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
        "Problem: Banks and large enterprises run legacy data systems that must be migrated to cloud data "
        "lakes and warehouses, a slow and error-prone process.\n"
        "Solution: An AI platform that automates SQL and stored procedure conversion and validates "
        "source-to-target data accuracy.\n"
        "Customers: Banks and large enterprises.\n"
        "Pricing: Rs 25 lakh implementation fee plus Rs 8 lakh per year for monitoring.\n"
        "Claims: 70% shorter migration timelines and 50% lower data engineering cost. Target of 20 "
        "enterprise clients in year one and profitability within 12 months.",
    ),
    "TiffinLink (consumer marketplace)": (
        "TiffinLink",
        "Problem: Office workers in Mumbai struggle to find affordable, healthy, home-style lunch, while "
        "home cooks have no reliable way to reach customers.\n"
        "Solution: A mobile app that connects home cooks with office workers for daily tiffin delivery.\n"
        "Customers: Office workers in Mumbai business districts.\n"
        "Pricing: Rs 150 per meal; the platform keeps a 20% fee.\n"
        "Claims: 5,000 daily orders within 6 months and break-even in month 8.",
    ),
    "LabGrade AI (education technology)": (
        "LabGrade AI",
        "Problem: Engineering faculty spend many hours grading lab reports, and feedback to students is "
        "slow and inconsistent.\n"
        "Solution: An AI tool that grades lab reports against a rubric and drafts feedback for each student.\n"
        "Customers: Engineering colleges in India.\n"
        "Pricing: Rs 2 lakh per college per year.\n"
        "Claims: Saves 60% of grading time and will sign 100 colleges in the first year.",
    ),
}

VERDICT_COLOURS = {
    "go": "#26890D",
    "conditional go": "#0097A9",
    "pivot": "#ED8B00",
    "no-go": "#DA291C",
    "no go": "#DA291C",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Open+Sans:wght@300;400;600;700&display=swap');

html, body, .stApp, [class*="css"] { font-family: 'Open Sans', Arial, sans-serif; }
.stApp { background: #FFFFFF; color: #000000; overflow-x: hidden; }
#MainMenu, footer, [data-testid="stHeader"], [data-testid="stToolbar"] { visibility: hidden; height: 0; }
.block-container { padding-top: 0 !important; padding-bottom: 3rem; max-width: 1180px; }

/* Top band */
.pw-top { background: #000; margin: 0 calc(50% - 50vw); padding: 0 calc(50vw - 50%); }
.pw-top-inner { display: flex; align-items: center; justify-content: space-between; height: 64px; }
.pw-brand { color: #fff; font-weight: 700; font-size: 1.45rem; letter-spacing: -0.01em; }
.pw-dot { color: #86BC25; }
.pw-tag { color: #D0D0CE; font-size: 0.72rem; letter-spacing: 0.14em; text-transform: uppercase; }

/* Hero */
.pw-hero { padding: 2.6rem 0 1.4rem 0; }
.pw-eyebrow { color: #26890D; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.16em; text-transform: uppercase; }
.pw-title { font-size: 2.15rem; font-weight: 300; line-height: 1.2; margin: 0.5rem 0 0.8rem 0; max-width: 820px; }
.pw-title b { font-weight: 700; }
.pw-lead { color: #53565A; font-size: 1rem; line-height: 1.65; max-width: 760px; }
.pw-rule { height: 3px; width: 56px; background: #86BC25; margin: 1.4rem 0 0 0; }

/* Section labels */
.pw-label { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #53565A; margin: 0.4rem 0 0.5rem 0; }

/* Inputs */
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea {
  border-radius: 0 !important; border: 1px solid #D0D0CE !important; background: #fff !important; font-size: 0.95rem; }
[data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus {
  border-color: #86BC25 !important; box-shadow: 0 0 0 1px #86BC25 !important; }
[data-baseweb="select"] > div { border-radius: 0 !important; border: 1px solid #D0D0CE !important; }
[data-testid="stWidgetLabel"] p { font-size: 0.82rem; font-weight: 600; color: #000; }

/* Buttons */
.stButton > button, [data-testid="stDownloadButton"] button {
  border-radius: 0; font-weight: 700; letter-spacing: 0.02em; border: 1px solid #000; background: #fff; color: #000; padding: 0.55rem 1.4rem; }
.stButton > button:hover, [data-testid="stDownloadButton"] button:hover { background: #000; color: #fff; border-color: #000; }
.stButton > button[kind="primary"] { background: #86BC25; border-color: #86BC25; color: #000; }
.stButton > button[kind="primary"]:hover { background: #26890D; border-color: #26890D; color: #fff; }

/* Pipeline */
.pw-pipe { border-top: 1px solid #D0D0CE; }
.pw-step { display: flex; align-items: center; gap: 14px; padding: 12px 6px 12px 12px; border-bottom: 1px solid #E6E6E4; border-left: 4px solid transparent; }
.pw-num { font-weight: 700; font-size: 0.85rem; color: #75787B; width: 24px; }
.pw-stxt { flex: 1; }
.pw-sname { font-weight: 600; font-size: 0.92rem; color: #000; }
.pw-sdesc { font-size: 0.78rem; color: #75787B; margin-top: 1px; }
.pw-sstate { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #75787B; }
.pw-step.active { border-left-color: #86BC25; background: #F6FAEE; }
.pw-step.active .pw-sstate { color: #26890D; }
.pw-step.active .pw-num { color: #26890D; }
.pw-step.done .pw-sstate { color: #000; }
.pw-step.done .pw-num { color: #000; }
.pw-step.skipped { opacity: 0.45; }
.pw-step.pending .pw-sname { color: #53565A; }

/* KPI strip */
.pw-kpis { display: grid; grid-template-columns: 1.6fr repeat(5, 1fr); gap: 12px; margin: 1.2rem 0 1.4rem 0; }
.pw-kpi { border: 1px solid #D0D0CE; border-top: 4px solid #000; padding: 14px 16px; background: #fff; }
.pw-kpi .k { font-size: 0.66rem; font-weight: 700; letter-spacing: 0.13em; text-transform: uppercase; color: #75787B; }
.pw-kpi .v { font-size: 1.5rem; font-weight: 700; margin-top: 4px; line-height: 1.15; }
.pw-kpi.verdict .v { font-size: 1.45rem; }

/* Tabs */
[data-testid="stTabs"] button[role="tab"] { font-weight: 600; font-size: 0.88rem; color: #53565A; padding: 0.6rem 1.1rem; }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] { color: #000; }
[data-baseweb="tab-highlight"] { background-color: #86BC25 !important; height: 3px !important; }
[data-baseweb="tab-border"] { background-color: #D0D0CE !important; }

/* Markdown content */
.stMarkdown h1 { font-size: 1.7rem; font-weight: 700; }
.stMarkdown h2 { font-size: 1.12rem; font-weight: 700; margin-top: 1.6rem; padding-bottom: 6px; border-bottom: 1px solid #D0D0CE; }
.stMarkdown h3 { font-size: 0.98rem; font-weight: 700; }
.stMarkdown p, .stMarkdown li { font-size: 0.95rem; line-height: 1.65; color: #1A1A1A; }
.stMarkdown table { border-collapse: collapse; width: 100%; font-size: 0.86rem; margin: 0.6rem 0; }
.stMarkdown th { background: #000; color: #fff; text-align: left; padding: 8px 10px; font-weight: 600; }
.stMarkdown td { border-bottom: 1px solid #D0D0CE; padding: 8px 10px; vertical-align: top; }

/* Expanders */
[data-testid="stExpander"] { border: 1px solid #D0D0CE; border-radius: 0; margin-bottom: 8px; }
[data-testid="stExpander"] summary { font-weight: 600; }

/* Slides */
.pw-slides { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
.pw-slide { border: 1px solid #D0D0CE; border-left: 4px solid #86BC25; padding: 16px 18px; background: #fff; }
.pw-slide .n { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.13em; color: #26890D; text-transform: uppercase; }
.pw-slide .t { font-size: 1.02rem; font-weight: 700; margin: 4px 0 8px 0; }
.pw-slide ul { margin: 0; padding-left: 1.1rem; }
.pw-slide li { font-size: 0.86rem; color: #333; margin-bottom: 4px; line-height: 1.5; }

.pw-note { font-size: 0.78rem; color: #75787B; line-height: 1.6; }
.pw-elapsed { font-size: 0.8rem; color: #53565A; margin-top: 8px; }
.pw-foot { border-top: 1px solid #D0D0CE; margin-top: 3rem; padding-top: 1rem; font-size: 0.75rem; color: #75787B; }

@media (max-width: 900px) {
  .pw-kpis { grid-template-columns: repeat(2, 1fr); }
  .pw-slides { grid-template-columns: 1fr; }
  .pw-title { font-size: 1.6rem; }
}
</style>
"""


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
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
            f'<div class="pw-step {state}"><div class="pw-num">{i:02d}</div>'
            f'<div class="pw-stxt"><div class="pw-sname">{html.escape(name)}</div>'
            f'<div class="pw-sdesc">{html.escape(desc)}</div></div>'
            f'<div class="pw-sstate">{label}</div></div>'
        )
    return '<div class="pw-pipe">' + "".join(rows) + "</div>"


def next_active(done, skipped):
    for name, _ in AGENTS:
        if name not in done and name not in skipped:
            return name
    return None


def extract_verdict(report):
    m = re.search(r"(?i)verdict\s*[:\-]\s*\**\s*(conditional go|no-go|no go|pivot|go)\b", report or "")
    return m.group(1).title() if m else "Not stated"


def severity_counts(text):
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for sev in re.findall(r"(?i)severity\W{0,4}\s*(critical|high|medium|low)", text or ""):
        counts[sev.lower()] += 1
    return counts


def parse_slides(outline):
    slides, current = [], None
    for raw in str(outline or "").splitlines():
        line = raw.strip()
        m = re.match(r"(?i)^slide\s*(\d+)\s*:\s*(.+)$", line)
        if m:
            current = {"n": m.group(1), "title": m.group(2).strip(), "bullets": []}
            slides.append(current)
        elif current and re.match(r"^[-*•]\s+", line):
            current["bullets"].append(re.sub(r"^[-*•]\s+", "", line).replace("**", ""))
    return slides


def fmt_time(seconds):
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name or "Startup").strip("._") or "Startup"


def load_example():
    choice = st.session_state.get("example_choice")
    if choice in EXAMPLES:
        st.session_state["startup_name"], st.session_state["pitch_text"] = EXAMPLES[choice]


def load_history():
    idx = st.session_state.get("history_choice")
    hist = st.session_state.get("history", [])
    if idx is not None and 0 <= idx < len(hist):
        st.session_state["result"] = hist[idx]


# --------------------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------------------
st.markdown(CSS, unsafe_allow_html=True)
st.session_state.setdefault("history", [])
st.session_state.setdefault("startup_name", "")
st.session_state.setdefault("pitch_text", "")

st.markdown(
    """
<div class="pw-top"><div class="pw-top-inner">
  <div class="pw-brand">PitchWise<span class="pw-dot">.</span></div>
  <div class="pw-tag">Multi-agent venture assessment</div>
</div></div>
<div class="pw-hero">
  <div class="pw-eyebrow">Decision support for founders and advisers</div>
  <div class="pw-title">Test a startup proposal against <b>six analytical perspectives</b> before it reaches a decision maker.</div>
  <div class="pw-lead">Specialist agents assess demand, competition, financial logic and risk, challenge the weakest
  assumptions, and consolidate the findings into an executive report with a clear verdict and next steps.</div>
  <div class="pw-rule"></div>
</div>
""",
    unsafe_allow_html=True,
)

supports_progress = "on_progress" in inspect.signature(pitchwise.run_pitchwise).parameters
supports_skip = "skip_critic" in inspect.signature(pitchwise.run_pitchwise).parameters

col_in, col_pipe = st.columns([7, 5], gap="large")

with col_in:
    st.markdown('<div class="pw-label">Proposal</div>', unsafe_allow_html=True)
    st.selectbox(
        "Load an example",
        ["Select an example"] + list(EXAMPLES.keys()),
        key="example_choice",
        on_change=load_example,
    )
    st.text_input("Startup name", key="startup_name", placeholder="For example: DataBridge AI")
    st.text_area(
        "Proposal summary",
        key="pitch_text",
        height=270,
        placeholder="Describe the problem, solution, target customers, pricing, and any growth or financial "
        "claims. One to three paragraphs is enough.",
    )
    skip_critic = False
    if supports_skip:
        skip_critic = st.checkbox(
            "Omit the Risk and Assumption Critic (comparison run)",
            help="Runs the pipeline without the adversarial review step, useful for showing what the Critic adds.",
        )
    run_clicked = st.button("Run assessment", type="primary")
    status_slot = st.empty()

with col_pipe:
    st.markdown('<div class="pw-label">Analysis pipeline</div>', unsafe_allow_html=True)
    pipe_slot = st.empty()

current = st.session_state.get("result")
if current:
    skipped_now = set() if current["critic"] else {"Risk and Assumption Critic"}
    pipe_slot.markdown(
        render_pipeline({n for n, _ in AGENTS} - skipped_now, None, skipped_now),
        unsafe_allow_html=True,
    )
else:
    pipe_slot.markdown(render_pipeline(set(), None, set(), idle=True), unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------------------
if run_clicked:
    name = st.session_state["startup_name"].strip()
    text = st.session_state["pitch_text"].strip()
    if not name:
        status_slot.error("Enter a startup name.")
    elif len(text) < 150:
        status_slot.error("The proposal summary is too short for a meaningful assessment (150 characters minimum).")
    else:
        pitch = f"Startup: {name}\n\n{text}"
        tmpdir = tempfile.mkdtemp(prefix="pitchwise_")
        progress_q = queue.Queue()
        box = {}

        kwargs = {"output_dir": tmpdir, "verbose_print": False}
        if supports_progress:
            kwargs["on_progress"] = lambda i, total, agent: progress_q.put(agent)
        if supports_skip:
            kwargs["skip_critic"] = skip_critic

        def worker():
            try:
                box["result"] = pitchwise.run_pitchwise_sync(pitch, **kwargs)
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc

        skipped = {"Risk and Assumption Critic"} if skip_critic else set()
        done = set()
        started = time.time()
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while thread.is_alive():
            try:
                while True:
                    done.add(progress_q.get_nowait())
            except queue.Empty:
                pass
            pipe_slot.markdown(
                render_pipeline(done, next_active(done, skipped), skipped), unsafe_allow_html=True
            )
            status_slot.markdown(
                f'<div class="pw-elapsed">Assessment in progress. Elapsed {fmt_time(time.time() - started)}. '
                f"This typically takes one to three minutes.</div>",
                unsafe_allow_html=True,
            )
            time.sleep(0.5)
        thread.join()

        if "error" in box:
            msg = str(box["error"])
            hint = ""
            if re.search(r"(?i)429|quota|rate.?limit|resource_exhausted", msg):
                hint = " The model provider's rate limit or daily quota was reached. Wait and retry, or set a different model or API key."
            status_slot.error(f"The assessment could not be completed.{hint}")
            with st.expander("Technical detail"):
                st.code(msg[:1500])
        else:
            res = box["result"]
            steps = res["steps"]
            elapsed = time.time() - started
            critic_text = next((t for n, t in steps if n == "Risk and Assumption Critic"), "")
            docx_bytes = Path(res["docx_path"]).read_bytes() if res.get("docx_path") else None
            pptx_bytes = Path(res["pptx_path"]).read_bytes() if res.get("pptx_path") else None
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
            pipe_slot.markdown(
                render_pipeline({n for n, _ in AGENTS} - skipped, None, skipped), unsafe_allow_html=True
            )
            status_slot.markdown(
                f'<div class="pw-elapsed">Assessment complete in {fmt_time(elapsed)}.</div>',
                unsafe_allow_html=True,
            )

# --------------------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------------------
if current:
    r = current
    colour = VERDICT_COLOURS.get(r["verdict"].lower(), "#000000")
    sev = r["severity"]
    crit_val = str(sev["critical"]) if r["critic"] else "n/a"
    high_val = str(sev["high"]) if r["critic"] else "n/a"

    st.markdown(f'<div class="pw-label" style="margin-top:2rem">Assessment: {html.escape(r["startup"])}</div>',
                unsafe_allow_html=True)
    st.markdown(
        f"""
<div class="pw-kpis">
  <div class="pw-kpi verdict" style="border-top-color:{colour}"><div class="k">Verdict</div>
    <div class="v" style="color:{colour}">{html.escape(r["verdict"])}</div></div>
  <div class="pw-kpi"><div class="k">Critical risks</div><div class="v">{crit_val}</div></div>
  <div class="pw-kpi"><div class="k">High risks</div><div class="v">{high_val}</div></div>
  <div class="pw-kpi"><div class="k">Agents run</div><div class="v">{r["agents"]}</div></div>
  <div class="pw-kpi"><div class="k">Elapsed</div><div class="v">{fmt_time(r["seconds"])}</div></div>
  <div class="pw-kpi"><div class="k">Report words</div><div class="v">{r["words"]}</div></div>
</div>
""",
        unsafe_allow_html=True,
    )

    tab_report, tab_agents, tab_slides, tab_export = st.tabs(
        ["Executive report", "Agent analyses", "Slide outline", "Export"]
    )

    with tab_report:
        st.markdown(r["report"])

    with tab_agents:
        st.markdown(
            '<div class="pw-note">Each agent works from the proposal and, where relevant, the output of the '
            "agents before it. The Critic reviews the market, competitive and financial analyses; the Strategy "
            "Lead reads everything.</div>",
            unsafe_allow_html=True,
        )
        for i, (agent_name, text) in enumerate(r["steps"], start=1):
            with st.expander(f"{i:02d}  {agent_name}", expanded=False):
                st.markdown(text)

    with tab_slides:
        slides = parse_slides(r["slides"])
        if slides:
            cards = []
            for s in slides:
                items = "".join(f"<li>{html.escape(b)}</li>" for b in s["bullets"])
                cards.append(
                    f'<div class="pw-slide"><div class="n">Slide {html.escape(s["n"])}</div>'
                    f'<div class="t">{html.escape(s["title"])}</div><ul>{items}</ul></div>'
                )
            st.markdown('<div class="pw-slides">' + "".join(cards) + "</div>", unsafe_allow_html=True)
        else:
            st.info("No slide outline was produced for this run.")

    with tab_export:
        base = safe_name(r["startup"])
        full_md = "\n\n---\n\n".join(f"# {n}\n\n{t}" for n, t in r["steps"])
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if r["docx"]:
                st.download_button(
                    "Word report", r["docx"], file_name=f"{base}_Executive_Report.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
        with c2:
            if r["pptx"]:
                st.download_button(
                    "PowerPoint deck", r["pptx"], file_name=f"{base}_Client_Presentation.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )
        with c3:
            st.download_button("Report (Markdown)", r["report"], file_name=f"{base}_report.md")
        with c4:
            st.download_button("All agent outputs", full_md, file_name=f"{base}_agent_outputs.md")

# --------------------------------------------------------------------------------------
# Secondary sections
# --------------------------------------------------------------------------------------
if len(st.session_state["history"]) > 1:
    with st.expander("Session history"):
        labels = [
            f'{h["time"]}  |  {h["startup"]}  |  {h["verdict"]}' for h in st.session_state["history"]
        ]
        st.selectbox(
            "View an earlier assessment",
            options=list(range(len(labels))),
            format_func=lambda i: labels[i],
            key="history_choice",
            on_change=load_history,
        )

with st.expander("Method and limitations"):
    st.markdown(
        f"""
**Design.** Six agents run in sequence using CrewAI. The Market, Competitive and Financial analysts work
independently from the proposal. The Risk and Assumption Critic reviews their findings and ranks risks with a
validation test for each. The Strategy Lead synthesises everything into the report, and the Presentation
Designer converts it into slides.

**Model.** {html.escape(os.environ.get("PITCHWISE_MODEL", pitchwise.DEFAULT_MODEL))}

**Limitations.** The assessment is based only on the text provided and on the model's general knowledge. No live
market research is performed, so competitor details and market figures should be treated as unverified. Financial
figures are the founder's claims unless stated otherwise. The output supports a decision and does not replace due
diligence or professional advice.
"""
    )

st.markdown(
    '<div class="pw-foot">PitchWise is an academic multi-agent project. Output is decision support, '
    "not financial or investment advice.</div>",
    unsafe_allow_html=True,
)
