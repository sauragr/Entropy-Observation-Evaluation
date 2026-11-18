

# app.py
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import streamlit as st

# ==========================================
# Page Configuration & Styling
# ==========================================
st.set_page_config(
    page_title="ENTROPY | Voice AI Audit & Observability",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    .turn-box {
        padding: 0.6rem 0.9rem;
        border-radius: 6px;
        margin-bottom: 0.5rem;
        border-left: 4px solid #ced4da;
        background-color: #f8f9fa;
        color: #111827 !important;
    }
    .turn-box strong, .turn-box span {
        color: #111827 !important;
    }
    .turn-agent { border-left-color: #2c3e50; background-color: #f1f3f5; }
    .turn-user { border-left-color: #2b8a3e; background-color: #ebfbee; }
    .turn-error {
        border-left-color: #c92a2a !important;
        background-color: #fff5f5 !important;
        border: 1px solid #ffc9c9;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# Session State Initialization
# ==========================================
if "active_view" not in st.session_state:
    st.session_state.active_view = "Batch Analytics"
if "selected_tracking_id" not in st.session_state:
    st.session_state.selected_tracking_id = None
if "batch_dir" not in st.session_state:
    st.session_state.batch_dir = "./calls"
if "_last_nav" not in st.session_state:
    st.session_state._last_nav = "Batch Analytics"


# ==========================================
# Data Loaders & Helpers
# ==========================================
@st.cache_data(show_spinner=False)
def load_batch_report(report_path: str = "outputs/batch_report.jsonl") -> List[Dict[str, Any]]:
    path = Path(report_path)
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records

# def build_summary_dataframe(records: List[Dict[str, Any]]) -> pd.DataFrame:
#     rows = []
#     for rec in records:
#         obs = rec.get("observability", {})
#         evals = rec.get("evals", {})
#         score_rep = evals.get("score_report", {})
#         checks = evals.get("checks", [])

#         # Extract story from observability.call_story or fallback options
#         story = (
#             obs.get("call_story")
#             or rec.get("story")
#             or rec.get("call_story")
#             or rec.get("metadata", {}).get("story")
#             or "unknown"
#         )

#         # Extract ghost turns count safely from observability telemetry
#         ghost_turns = int(obs.get("ghost_turns_count", 0))

#         failed_checks = [c.get("check_id") for c in checks if c.get("status") == "fail"]
        
#         # Fixed parenthesis placement here:
#         never_rule_msg = next(
#             (c.get("reason") for c in checks if c.get("check_id") == "ai_judge_never_rules" and c.get("status") == "fail"),
#             "None",
#         )

#         rows.append(
#             {
#                 "tracking_id": rec.get("tracking_id", "unknown"),
#                 "folder_name": rec.get("folder_name", rec.get("tracking_id", "").split("_cust_")[0]),
#                 "story": story,
#                 "final_score": float(score_rep.get("final_score", 0.0)),
#                 "review_required": bool(score_rep.get("review_required", False)),
#                 "audio_verified": bool(obs.get("audio_verified", False)),
#                 "ghost_turns": ghost_turns,
#                 "end_reason": obs.get("end_reason", "N/A"),
#                 "failed_count": len(failed_checks),
#                 "failed_checks": ", ".join(failed_checks) if failed_checks else "None",
#                 "never_rule_violation": never_rule_msg,
#             }
#         )
#     return pd.DataFrame(rows)

import re

def build_summary_dataframe(records: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for rec in records:
        obs = rec.get("observability", {})
        evals = rec.get("evals", {})
        score_rep = evals.get("score_report", {})
        checks = evals.get("checks", [])

        # Extract story
        story = (
            obs.get("call_story")
            or rec.get("story")
            or rec.get("call_story")
            or rec.get("metadata", {}).get("story")
            or "unknown"
        )

        # Extract ghost turns dynamically from the check reason parameter
        ghost_turns = 0
        for chk in checks:
            if chk.get("check_id") == "audio_ghost_turns_zero":
                reason_text = chk.get("reason", "")
                # Look for patterns like "Detected X ghost audio turn"
                match = re.search(r"Detected\s+(\d+)\s+ghost", reason_text, re.IGNORECASE)
                if match:
                    ghost_turns = int(match.group(1))
                break

        failed_checks = [c.get("check_id") for c in checks if c.get("status") == "fail"]
        
        never_rule_msg = next(
            (c.get("reason") for c in checks if c.get("check_id") == "ai_judge_never_rules" and c.get("status") == "fail"),
            "None",
        )

        rows.append(
            {
                "tracking_id": rec.get("tracking_id", "unknown"),
                "folder_name": rec.get("folder_name", rec.get("tracking_id", "").split("_cust_")[0]),
                "story": story,
                "final_score": float(score_rep.get("final_score", 0.0)),
                "review_required": bool(score_rep.get("review_required", False)),
                "audio_verified": bool(obs.get("audio_verified", False)),
                "ghost_turns": ghost_turns,
                "end_reason": obs.get("end_reason", "N/A"),
                "failed_count": len(failed_checks),
                "failed_checks": ", ".join(failed_checks) if failed_checks else "None",
                "never_rule_violation": never_rule_msg,
            }
        )
    return pd.DataFrame(rows)

def locate_call_assets(batch_dir: str, record: Dict[str, Any]) -> Dict[str, Optional[Path]]:
    base = Path(batch_dir)
    tracking_id = record.get("tracking_id", "")
    prefix = tracking_id.split("_cust_")[0] if "_cust_" in tracking_id else tracking_id

    candidate_dirs = [base / prefix, base / tracking_id]
    if base.exists():
        for d in base.iterdir():
            if d.is_dir() and (d.name == prefix or tracking_id.startswith(d.name)):
                candidate_dirs.append(d)

    wav_path, json_path = None, None
    for folder in candidate_dirs:
        if folder.exists() and folder.is_dir():
            w = folder / "recording.wav"
            j = folder / "call.json"
            if w.exists():
                wav_path = w
            if j.exists():
                json_path = j
            if wav_path or json_path:
                break

    return {"wav": wav_path, "json": json_path}


def extract_wrong_line(checks: List[Dict[str, Any]]) -> Optional[int]:
    for c in checks:
        ref = c.get("line_reference") or ""
        if c.get("status") == "fail" and ref.startswith("Line "):
            try:
                return int(ref.replace("Line ", "").strip())
            except ValueError:
                pass
    return None


def trigger_pipeline(batch_dir: str):
    if not Path("main.py").exists():
        st.sidebar.error("`main.py` not found in the current working directory.")
        return

    with st.spinner(f"Running ENTROPY pipeline on `{batch_dir}`..."):
        cmd = [sys.executable, "main.py", "--batch_dir", batch_dir]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            st.cache_data.clear()
            st.sidebar.success("Pipeline execution finished!")
        else:
            st.sidebar.error("Pipeline failed. Check logs below:")
            st.sidebar.code(res.stderr[-800:] if res.stderr else res.stdout[-800:])


# ==========================================
# Sidebar Navigation & Controls
# ==========================================
with st.sidebar:
    st.title("ENTROPY")
    st.caption("Voice AI Audit & Observability")
    st.divider()

    st.subheader("Pipeline Controls")
    batch_input = st.text_input("Batch Directory Path", value=st.session_state.batch_dir)
    st.session_state.batch_dir = batch_input

    if st.button("▶ Run / Refresh Pipeline", use_container_width=True, type="primary"):
        trigger_pipeline(batch_input)

    if st.button("↻ Reload Cached Report", use_container_width=True):
        st.cache_data.clear()

    st.divider()
    st.subheader("Navigation")

    nav_options = ["Batch Analytics", "Observability & Evals Table"]
    current_idx = nav_options.index(st.session_state.active_view) if st.session_state.active_view in nav_options else 1

    selected_nav = st.radio(
        "Select View",
        options=nav_options,
        index=current_idx,
        label_visibility="collapsed",
    )

    if selected_nav != st.session_state.active_view and st.session_state.active_view != "Call Detail":
        st.session_state.active_view = selected_nav
        st.rerun()
    elif st.session_state.active_view == "Call Detail" and selected_nav != st.session_state._last_nav:
        st.session_state.active_view = selected_nav
        st.session_state.selected_tracking_id = None
        st.rerun()

    st.session_state._last_nav = selected_nav


# ==========================================
# Load Dataset
# ==========================================
records = load_batch_report()
if not records:
    st.warning("No batch report found at `outputs/batch_report.jsonl`. Run the pipeline from the sidebar to generate results.")
    st.stop()

df = build_summary_dataframe(records)
records_by_id = {r.get("tracking_id"): r for r in records}


# ==========================================
# VIEW 1: BATCH ANALYTICS
# ==========================================
def render_batch_analytics(df: pd.DataFrame, records: List[Dict[str, Any]]):
    st.header("Batch Analytics & Observability Overview")

    c1, c2, c3 = st.columns(3)
    total_calls = len(df)
    avg_score = df["final_score"].mean()
    flag_rate = (df["review_required"].sum() / total_calls * 100) if total_calls else 0.0

    c1.metric("Total Calls Processed", f"{total_calls}")
    c2.metric("Average Composite Score", f"{avg_score:.1f} / 100")
    c3.metric("Review Queue Flag Rate", f"{flag_rate:.1f}%", f"{int(df['review_required'].sum())} flagged", delta_color="inverse")

    st.divider()

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("Score Distribution Across Batch")
        fig_hist = px.histogram(
            df,
            x="final_score",
            nbins=20,
            color="story",
            labels={"final_score": "Composite Score (0–100)", "story": "Call Story"},
            color_discrete_sequence=px.colors.qualitative.Safe,
        )
        fig_hist.update_layout(bargap=0.08, margin=dict(l=10, r=10, t=20, b=10), height=340)
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_right:
        st.subheader("Failures by Evaluation Category")
        cat_counts = {"audio_timing": 0, "code_fact": 0, "ai_judged": 0}
        for rec in records:
            for chk in rec.get("evals", {}).get("checks", []):
                if chk.get("status") == "fail":
                    cat = chk.get("category", "other")
                    cat_counts[cat] = cat_counts.get(cat, 0) + 1

        cat_df = pd.DataFrame(
            [{"Category": k.replace("_", " ").title(), "Failed Checks": v} for k, v in cat_counts.items() if v > 0]
        )
        if not cat_df.empty:
            fig_pie = px.pie(
                cat_df,
                names="Category",
                values="Failed Checks",
                hole=0.45,
                color_discrete_sequence=["#2c3e50", "#495057", "#c92a2a"],
            )
            fig_pie.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=340)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Zero failed checks across all categories in this batch.")

    col_b1, col_b2 = st.columns(2)

    with col_b1:
        st.subheader("Call Outcome Stories")
        story_summary = (
            df.groupby("story")
            .agg(Calls=("tracking_id", "count"), Avg_Score=("final_score", "mean"), Flagged=("review_required", "sum"))
            .reset_index()
        )
        story_summary["Avg_Score"] = story_summary["Avg_Score"].round(1)
        st.dataframe(story_summary, use_container_width=True, hide_index=True)

    with col_b2:
        st.subheader("Top Violated Never-Rules")
        violations = df[df["never_rule_violation"] != "None"]["never_rule_violation"]
        if not violations.empty:
            extracted_rules = violations.apply(
                lambda x: x.split("]")[0].replace("Never-rule broken [", "") if "Never-rule broken [" in x else x
            )
            rule_counts = extracted_rules.value_counts().reset_index()
            rule_counts.columns = ["Never-Rule Violated", "Count"]
            st.dataframe(rule_counts, use_container_width=True, hide_index=True)
        else:
            st.success("No Never-Rule violations detected in this batch.")


# ==========================================
# VIEW 2: OBSERVABILITY & EVALS MASTER TABLE
# ==========================================
def render_master_table(df: pd.DataFrame):
    st.header("Call Observability & Evaluation Explorer")
    st.caption("Filter by story, audit status, or score. Click any row to open the full forensic audio & transcript drill-down.")

    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
    with f1:
        stories = ["All"] + sorted(df["story"].unique().tolist())
        selected_story = st.selectbox("Filter by Story Category", stories)
    with f2:
        audit_filter = st.selectbox("Audit Flag Status", ["All", "Flagged for Review Only", "Passed Cleanly"])
    with f3:
        ghost_filter = st.selectbox("Audio Integrity", ["All", "Ghost Audio Detected", "Audio Verified Clean"])
    with f4:
        score_range = st.slider("Score Range", 0.0, 100.0, (0.0, 100.0), step=5.0)

    filtered = df.copy()
    if selected_story != "All":
        filtered = filtered[filtered["story"] == selected_story]
    if audit_filter == "Flagged for Review Only":
        filtered = filtered[filtered["review_required"] == True]
    elif audit_filter == "Passed Cleanly":
        filtered = filtered[filtered["review_required"] == False]
    if ghost_filter == "Ghost Audio Detected":
        filtered = filtered[filtered["ghost_turns"] > 0]
    elif ghost_filter == "Audio Verified Clean":
        filtered = filtered[(filtered["audio_verified"] == True) & (filtered["ghost_turns"] == 0)]

    filtered = filtered[(filtered["final_score"] >= score_range[0]) & (filtered["final_score"] <= score_range[1])]

    st.markdown(f"**Showing {len(filtered)} of {len(df)} calls** — *Click a row below to inspect*")

    display_cols = [
        "tracking_id",
        "story",
        "final_score",
        "review_required",
        "audio_verified",
        "ghost_turns",
        "end_reason",
        "failed_checks",
    ]

    event = st.dataframe(
        filtered[display_cols],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "tracking_id": st.column_config.TextColumn("Tracking ID (Primary Key)", width="medium"),
            "story": st.column_config.TextColumn("Story"),
            "final_score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f"),
            "review_required": st.column_config.CheckboxColumn("Audit Flag"),
            "audio_verified": st.column_config.CheckboxColumn("WAV Verified"),
            "ghost_turns": st.column_config.NumberColumn("Ghost Turns"),
            "end_reason": st.column_config.TextColumn("Logged Disposition"),
            "failed_checks": st.column_config.TextColumn("Failed Checks", width="large"),
        },
    )

    if event and event.selection and event.selection.rows:
        selected_row_idx = event.selection.rows[0]
        chosen_id = filtered.iloc[selected_row_idx]["tracking_id"]
        st.session_state.selected_tracking_id = chosen_id
        st.session_state.active_view = "Call Detail"
        st.rerun()


# ==========================================
# VIEW 3: FORENSIC CALL DETAIL (DRILL-DOWN)
# ==========================================
def render_call_detail(tracking_id: str, record: Dict[str, Any], batch_dir: str):
    top_col1, top_col2 = st.columns([1, 5])
    with top_col1:
        if st.button("← Back to Table", use_container_width=True):
            st.session_state.active_view = "Observability & Evals Table"
            st.session_state.selected_tracking_id = None
            st.rerun()
    with top_col2:
        st.subheader(f"Forensic Audit: `{tracking_id}`")

    obs = record.get("observability", {})
    evals = record.get("evals", {})
    score_rep = evals.get("score_report", {})
    checks = evals.get("checks", [])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Composite Score", f"{score_rep.get('final_score', 0.0):.1f} / 100")
    m2.metric("Review Flag", "FLAGGED" if score_rep.get("review_required") else "CLEAN")
    
    resolved_story = (
        record.get("story")
        or record.get("call_story")
        or record.get("metadata", {}).get("story")
        or record.get("meta", {}).get("story")
        or record.get("record", {}).get("story")
        or "unknown"
    )
    m3.metric("Story Classification", resolved_story)
    m4.metric("Ghost Audio Turns", obs.get("ghost_turns_count", 0))

    st.divider()

    left_pane, right_pane = st.columns([1, 1])

    with left_pane:
        st.markdown("### 1. Recording & Telemetry Ground Truth")
        assets = locate_call_assets(batch_dir, record)
        if assets["wav"]:
            st.audio(str(assets["wav"]), format="audio/wav")
        else:
            st.warning("`recording.wav` not found in call folder.")

        with st.expander("Raw Observability Telemetry (`audio_parser` & `call.json`)", expanded=False):
            st.json(obs)

        st.markdown("### 2. Evaluation Checks Matrix")
        for chk in checks:
            status = chk.get("status", "not_evaluable").upper()
            badge = "✅" if status == "PASS" else ("❌" if status == "FAIL" else "⚪")
            title = f"{badge} [{chk.get('category', '').upper()}] {chk.get('check_id')} — {status}"

            with st.expander(title, expanded=(status == "FAIL")):
                st.write(f"**Reason:** {chk.get('reason')}")
                if chk.get("line_reference"):
                    st.caption(f"Reference: `{chk.get('line_reference')}`")

    with right_pane:
        st.markdown("### 3. Transcript & Line-Level Pinpointing")
        wrong_line = extract_wrong_line(checks)

        messages = record.get("messages", [])
        if not messages and assets["json"]:
            try:
                with open(assets["json"], "r", encoding="utf-8") as jf:
                    raw_call = json.load(jf)
                    messages = raw_call.get("messages", [])
            except Exception as e:
                st.error(f"Could not read `call.json`: {e}")

        if not messages:
            st.info("No conversational messages recorded for this call.")
        else:
            for idx, msg in enumerate(messages, start=1):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                is_error_line = wrong_line == idx

                role_cls = "turn-agent" if role in ("assistant", "agent") else "turn-user"
                err_cls = "turn-error" if is_error_line else ""
                alert_tag = " 🚨 [FIRST ISSUE DETECTED HERE]" if is_error_line else ""

                st.markdown(
                    f"""
                    <div class="turn-box {role_cls} {err_cls}">
                        <strong>[Line {idx}] {role.upper()}{alert_tag}</strong><br/>
                        <span>{content}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# ==========================================
# Router
# ==========================================
if st.session_state.active_view == "Batch Analytics":
    render_batch_analytics(df, records)
elif st.session_state.active_view == "Observability & Evals Table":
    render_master_table(df)
elif st.session_state.active_view == "Call Detail":
    tid = st.session_state.selected_tracking_id
    if tid and tid in records_by_id:
        render_call_detail(tid, records_by_id[tid], st.session_state.batch_dir)
    else:
        st.session_state.active_view = "Observability & Evals Table"
        st.rerun()