"""
PitchWise evaluation harness.

Compares the multi-agent system against a single-prompt baseline (same model, same
output structure) on a set of sample pitches. Outputs are scored by a blind, pairwise
LLM judge (A/B order randomised) on a 1-5 rubric, alongside simple descriptive metrics.
An optional ablation arm removes the Risk and Assumption Critic.

Usage (Colab):
    !python evaluate.py --n 3
    !python evaluate.py --n 5 --ablation
    !python evaluate.py --n 5 --resume        # continue after a quota stop

Files written to --outdir (default: evaluation):
    results.csv      one row per pitch x system
    summary.md       averages and win counts, ready to paste into the report
    records.json     raw rows (used by --resume)
    outputs/         the full text produced by each system, for the report appendix

Environment: same as pitchwise.py (PITCHWISE_MODEL and the matching API key).
Optional: JUDGE_MODEL to use a different model as the judge.
"""
import argparse
import csv
import json
import os
import random
import re
import statistics
import time
from pathlib import Path

import pitchwise
from pitchwise import get_llm, run_pitchwise_sync

# --------------------------------------------------------------------------------------
# Sample pitches (each starts with "Startup:" so the system can pick up the name)
# --------------------------------------------------------------------------------------
CASES = [
    {
        "id": 1,
        "name": "DataBridge AI",
        "pitch": (
            "Startup: DataBridge AI\n"
            "Problem: Banks and large enterprises run legacy data systems that must be migrated to cloud "
            "data lakes and warehouses, a slow and error-prone process.\n"
            "Solution: An AI platform that automates SQL and stored procedure conversion and validates "
            "source-to-target data accuracy.\n"
            "Customers: Banks and large enterprises.\n"
            "Pricing: Rs 25 lakh implementation fee plus Rs 8 lakh per year for monitoring.\n"
            "Claims: 70% shorter migration timelines and 50% lower data engineering cost. Target of 20 "
            "enterprise clients in year one and profitability within 12 months."
        ),
    },
    {
        "id": 2,
        "name": "TiffinLink",
        "pitch": (
            "Startup: TiffinLink\n"
            "Problem: Office workers in Mumbai struggle to find affordable, healthy, home-style lunch, "
            "while home cooks have no reliable way to reach customers.\n"
            "Solution: A mobile app that connects home cooks with office workers for daily tiffin delivery.\n"
            "Customers: Office workers in Mumbai business districts.\n"
            "Pricing: Rs 150 per meal; the platform keeps a 20% fee.\n"
            "Claims: 5,000 daily orders within 6 months and break-even in month 8."
        ),
    },
    {
        "id": 3,
        "name": "LabGrade AI",
        "pitch": (
            "Startup: LabGrade AI\n"
            "Problem: Engineering faculty spend many hours grading lab reports, and feedback to students is "
            "slow and inconsistent.\n"
            "Solution: An AI tool that grades lab reports against a rubric and drafts feedback for each student.\n"
            "Customers: Engineering colleges in India.\n"
            "Pricing: Rs 2 lakh per college per year.\n"
            "Claims: Saves 60% of grading time and will sign 100 colleges in the first year."
        ),
    },
    {
        "id": 4,
        "name": "FarmFresh Direct",
        "pitch": (
            "Startup: FarmFresh Direct\n"
            "Problem: Urban households pay high prices for vegetables that pass through several middlemen, "
            "while farmers in Nashik earn little.\n"
            "Solution: A subscription service delivering fresh vegetables directly from Nashik farmers to "
            "apartment complexes in Mumbai and Pune.\n"
            "Customers: Urban apartment residents.\n"
            "Pricing: 15% above prevailing market price, billed monthly.\n"
            "Claims: 40% gross margin and 10,000 subscribers within 12 months."
        ),
    },
    {
        "id": 5,
        "name": "FrameShare",
        "pitch": (
            "Startup: FrameShare\n"
            "Problem: Student filmmakers cannot afford professional camera gear, and equipment owners leave "
            "gear idle most of the year.\n"
            "Solution: A marketplace for renting premium camera gear to college filmmakers, with insurance "
            "included in every rental.\n"
            "Customers: College film clubs and independent student creators.\n"
            "Pricing: 15% commission on each rental.\n"
            "Claims: 2,000 rentals per month by month 6 and zero losses from damage or theft."
        ),
    },
]

CRITERIA = [
    "completeness",
    "evidence_discipline",
    "assumption_challenging",
    "actionability",
    "consistency",
]

RUBRIC_TEXT = """Score each assessment from 1 (poor) to 5 (excellent) on:
- completeness: covers demand, competition, financials, risks, recommendations and a verdict, with depth
- evidence_discipline: separates facts stated in the pitch from assumptions, avoids invented statistics or sources, flags unverified claims
- assumption_challenging: identifies and tests the weakest or most optimistic assumptions rather than accepting them
- actionability: recommendations are specific, prioritised and testable (what to do, how to measure it)
- consistency: the verdict matches the analysis, numbers add up, and sections do not contradict each other"""


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def retry(fn, tries=4, base_delay=20):
    """Retry transient failures (rate limits) with backoff. Daily quota errors fail fast."""
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            text = str(exc).lower()
            if "perday" in text.replace(" ", "") or "per day" in text:
                raise RuntimeError(
                    "Daily quota exhausted for this model/key. Switch model or key, or rerun later "
                    "with --resume."
                ) from exc
            if attempt == tries - 1:
                raise
            wait = base_delay * (2 ** attempt)
            print(f"    call failed ({type(exc).__name__}); retrying in {wait}s")
            time.sleep(wait)


def text_metrics(text):
    """Simple descriptive metrics. These are proxies, not measures of quality."""
    return {
        "words": len(text.split()),
        "verdict": pitchwise._extract_verdict(text) or "not found",
        "evidence_markers": len(
            re.findall(r"(?i)unverified|assum|not provided|not stated|evidence gap|founder claim", text)
        ),
        "validation_mentions": len(
            re.findall(r"(?i)\b(?:poc|pilot|loi|letters? of intent|interview|survey|test)s?\b", text)
        ),
    }


def run_crew(pitch, skip_critic=False):
    result = run_pitchwise_sync(
        pitch, verbose_print=False, generate_files=False, skip_critic=skip_critic
    )
    return result["report"]


def run_baseline(pitch):
    prompt = f"""You are a management consultant. Write an executive assessment of the startup pitch below in 700-1,000 words.

PITCH:
{pitch}

Use these sections: Executive Summary; Business and Customer Opportunity; Market Demand and Target Segment; Competitive Landscape; Business Model and Financial Assessment; Key Risks and Assumptions; Prioritized Recommendations; Verdict and Next Steps; Evidence Limitations.

Put one line "Verdict: <choice>" near the beginning, choosing exactly one of: Go, Conditional Go, Pivot, No-Go.
Separate pitch-provided facts from assumptions. Do not invent statistics, interviews or citations. Mark any competitor or market fact taken from general knowledge as "(unverified)". Plain-text math only, no LaTeX."""
    return get_llm().call(prompt)


def parse_scores(raw):
    """Extract and validate the judge's JSON."""
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("no JSON object in judge output")
    data = json.loads(match.group(0))
    out = {}
    for label in ("A", "B"):
        scores = data[label]
        out[label] = {}
        for c in CRITERIA:
            val = int(round(float(scores[c])))
            if not 1 <= val <= 5:
                raise ValueError(f"score out of range: {c}={val}")
            out[label][c] = val
    out["notes"] = str(data.get("notes", ""))
    return out


def judge_pair(pitch, text_a, text_b, judge_model=None):
    llm = get_llm(model=judge_model) if judge_model else get_llm()
    prompt = f"""You are a strict, impartial evaluator. Below is a startup pitch and two executive assessments of it, labelled A and B. You do not know how either was produced. Judge only the text.

{RUBRIC_TEXT}

Be critical: use the full 1-5 range and do not reward length by itself.

PITCH:
{pitch}

ASSESSMENT A:
{text_a}

ASSESSMENT B:
{text_b}

Return ONLY JSON in exactly this shape (integers 1-5):
{{"A": {{"completeness": 0, "evidence_discipline": 0, "assumption_challenging": 0, "actionability": 0, "consistency": 0}},
 "B": {{"completeness": 0, "evidence_discipline": 0, "assumption_challenging": 0, "actionability": 0, "consistency": 0}},
 "notes": "one sentence on the main difference"}}"""
    last_err = None
    for _ in range(2):
        raw = retry(lambda: llm.call(prompt))
        try:
            return parse_scores(raw)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            last_err = exc
    raise ValueError(f"judge output could not be parsed: {last_err}")


def overall(scores):
    return round(sum(scores[c] for c in CRITERIA) / len(CRITERIA), 2)


# --------------------------------------------------------------------------------------
# Evaluation loop
# --------------------------------------------------------------------------------------
def compare(case, system_a_name, text_a, secs_a, system_b_name, text_b, secs_b, rng, judge_model, comparison):
    """Judge one pair blind (random A/B order) and return two result rows."""
    a_first = rng.random() < 0.5
    first, second = (text_a, text_b) if a_first else (text_b, text_a)
    scores = judge_pair(case["pitch"], first, second, judge_model)
    sa = scores["A"] if a_first else scores["B"]
    sb = scores["B"] if a_first else scores["A"]
    rows = []
    for name, text, secs, sc in ((system_a_name, text_a, secs_a, sa), (system_b_name, text_b, secs_b, sb)):
        rows.append(
            {
                "pitch_id": case["id"],
                "pitch_name": case["name"],
                "comparison": comparison,
                "system": name,
                **sc,
                "overall": overall(sc),
                "seconds": secs,
                **text_metrics(text),
                "judge_note": scores["notes"],
            }
        )
    return rows


def timed(fn, *args, **kwargs):
    t0 = time.time()
    value = fn(*args, **kwargs)
    return value, round(time.time() - t0, 1)


def mean(values):
    return round(statistics.mean(values), 2) if values else 0.0


def write_outputs(outdir, rows):
    fields = (
        ["pitch_id", "pitch_name", "comparison", "system"]
        + CRITERIA
        + ["overall", "seconds", "words", "verdict", "evidence_markers", "validation_mentions", "judge_note"]
    )
    with open(outdir / "results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with open(outdir / "records.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)


def build_summary(rows):
    lines = ["# PitchWise evaluation summary", ""]
    comparisons = []
    for r in rows:
        if r["comparison"] not in comparisons:
            comparisons.append(r["comparison"])

    for comp in comparisons:
        subset = [r for r in rows if r["comparison"] == comp]
        systems = []
        for r in subset:
            if r["system"] not in systems:
                systems.append(r["system"])
        pitches = sorted({r["pitch_id"] for r in subset})
        lines += [f"## {comp}", "", f"Pitches evaluated: {len(pitches)}", ""]

        header = "| Criterion | " + " | ".join(systems) + " |"
        lines += [header, "|" + "---|" * (len(systems) + 1)]
        for c in CRITERIA + ["overall"]:
            vals = [mean([r[c] for r in subset if r["system"] == s]) for s in systems]
            label = c.replace("_", " ").capitalize()
            lines.append(f"| {label} | " + " | ".join(str(v) for v in vals) + " |")
        lines.append("")

        lines += ["| Descriptive metric | " + " | ".join(systems) + " |", "|" + "---|" * (len(systems) + 1)]
        for m, label in [
            ("seconds", "Average time (s)"),
            ("words", "Average words"),
            ("evidence_markers", "Evidence markers per report"),
            ("validation_mentions", "Validation mentions per report"),
        ]:
            vals = [mean([r[m] for r in subset if r["system"] == s]) for s in systems]
            lines.append(f"| {label} | " + " | ".join(str(v) for v in vals) + " |")
        lines.append("")

        if len(systems) == 2:
            wins = {systems[0]: 0, systems[1]: 0, "tie": 0}
            for pid in pitches:
                a = next(r for r in subset if r["pitch_id"] == pid and r["system"] == systems[0])
                b = next(r for r in subset if r["pitch_id"] == pid and r["system"] == systems[1])
                if a["overall"] > b["overall"]:
                    wins[systems[0]] += 1
                elif b["overall"] > a["overall"]:
                    wins[systems[1]] += 1
                else:
                    wins["tie"] += 1
            lines.append(
                f"Wins by overall score: {systems[0]} {wins[systems[0]]}, {systems[1]} {wins[systems[1]]}, "
                f"ties {wins['tie']}"
            )
            lines.append("")

    lines += [
        "## Method and limitations",
        "",
        "- Scores come from an LLM judge that saw each pair in randomised order without knowing which system "
        "produced which text. LLM judges can favour length and style, so treat scores as indicative.",
        "- Sample size is small and pitches are synthetic, so no statistical significance is claimed.",
        "- Descriptive metrics (words, evidence markers, validation mentions) are simple counts and not "
        "measures of quality.",
        "- No ground truth exists for startup outcomes; the evaluation measures analysis quality, not "
        "prediction accuracy.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate PitchWise against a single-prompt baseline.")
    parser.add_argument("--n", type=int, default=5, help="number of sample pitches to run (1-5)")
    parser.add_argument("--ablation", action="store_true", help="also run PitchWise without the Critic")
    parser.add_argument("--resume", action="store_true", help="skip pitches already stored in records.json")
    parser.add_argument("--seed", type=int, default=7, help="seed for the A/B order randomisation")
    parser.add_argument("--outdir", default="evaluation")
    parser.add_argument("--judge-model", default=os.environ.get("JUDGE_MODEL"))
    parser.add_argument("--sleep", type=float, default=0.0, help="seconds to wait between pitches")
    args = parser.parse_args(argv)

    outdir = Path(args.outdir)
    (outdir / "outputs").mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    rows = []
    records = outdir / "records.json"
    if args.resume and records.exists():
        rows = json.loads(records.read_text(encoding="utf-8"))
        print(f"Resuming with {len({r['pitch_id'] for r in rows})} pitch(es) already done.")
    done_ids = {r["pitch_id"] for r in rows}

    for case in CASES[: max(1, min(args.n, len(CASES)))]:
        if case["id"] in done_ids:
            continue
        print(f"\n[{case['id']}] {case['name']}")

        try:
            print("  running PitchWise agents ...")
            crew_text, crew_secs = timed(lambda: retry(lambda: run_crew(case["pitch"])))
            print("  running single-prompt baseline ...")
            base_text, base_secs = timed(lambda: retry(lambda: run_baseline(case["pitch"])))

            (outdir / "outputs" / f"pitch{case['id']}_pitchwise.md").write_text(crew_text, encoding="utf-8")
            (outdir / "outputs" / f"pitch{case['id']}_baseline.md").write_text(base_text, encoding="utf-8")

            print("  judging PitchWise vs baseline ...")
            new_rows = compare(
                case, "PitchWise", crew_text, crew_secs, "Baseline", base_text, base_secs,
                rng, args.judge_model, "PitchWise vs single-prompt baseline",
            )

            if args.ablation:
                print("  running PitchWise without the Critic ...")
                nc_text, nc_secs = timed(lambda: retry(lambda: run_crew(case["pitch"], skip_critic=True)))
                (outdir / "outputs" / f"pitch{case['id']}_no_critic.md").write_text(nc_text, encoding="utf-8")
                print("  judging full PitchWise vs no-critic ...")
                new_rows += compare(
                    case, "PitchWise (full)", crew_text, crew_secs, "PitchWise (no Critic)", nc_text, nc_secs,
                    rng, args.judge_model, "Ablation: with vs without Critic",
                )
        except Exception as exc:  # noqa: BLE001
            print(f"  stopped at pitch {case['id']}: {exc}")
            print("  Saving what has been completed. Rerun with --resume to continue.")
            break

        rows.extend(new_rows)
        write_outputs(outdir, rows)  # save after every pitch so a quota stop loses nothing
        for r in new_rows:
            print(f"    {r['system']:<24} overall {r['overall']}  ({r['seconds']}s, {r['words']} words)")
        if args.sleep:
            time.sleep(args.sleep)

    if not rows:
        print("\nNo results to summarise.")
        return 1

    write_outputs(outdir, rows)
    summary = build_summary(rows)
    (outdir / "summary.md").write_text(summary, encoding="utf-8")
    print("\n" + summary)
    print(f"Files saved in: {outdir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
