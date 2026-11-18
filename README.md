# ENTROPY

Post-call audit for AI voice-agent phone calls. ENTROPY reads a folder of recorded calls (a `call.json` log and a stereo
`recording.wav` each), checks what the customer could actually hear, grades every call out of 100, and builds a queue of calls
for human review. Results can be browsed in a Streamlit dashboard.

Everything runs after the call ends; nothing touches a live call.

## Features

- **Schema validation** of every `call.json` (Pydantic), tolerant of partial or dropped calls.
- **Audio verification** from the stereo recording: finds "ghost turns" (the agent's line was logged as heard, but its channel is silent) and measures reply latency.
- **Call story** label per call: `never_connected`, `machine`, `left_on_first_line`, `dropped`, `real_ending`.
- **Cost estimate** per call from LLM, TTS and STT usage counters.
- **Four checks** per call (audio, code facts, and a Gemini judge for never-rules), each returning `pass`, `fail` or `not_evaluable` with a reason and a line reference.
- **Score out of 100** with a per-check breakdown and a review flag.
- **Review queue** of calls a person should audit.
- **Dashboard** with batch analytics, a filterable call table and a per-call drill-down with audio playback.

## Requirements

- Python 3.12
- A Gemini API key (used by the AI judge)

## Installation

```powershell
pip install pydantic numpy python-dotenv google-genai streamlit pandas plotly
```

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your-key-here
```

Keep `.env` out of version control and out of anything you share.

## Usage

### Dashboard

```powershell
streamlit run main.py
```

The dashboard reads `outputs/batch_report.jsonl` and offers three views:

| View | What it shows |
|---|---|
| Batch Analytics | Total calls, average score, review flag rate, score histogram, failures by category, calls per story, most-violated never-rules |
| Observability & Evals Table | One row per call; filter by story, review flag, ghost audio and score; click a row to open it |
| Call Detail | Audio player, raw telemetry, every check with its reason, and the transcript with the judge's first wrong line highlighted |

### Review queue

```powershell
python review_queue.py
```

Reads `outputs/batch_report.jsonl` and writes `outputs/review_queue_summary.json`.

### Batch processing

`main.py` is the dashboard; there is no command in this project that runs the scan → measure → check → score → save chain over `./calls`.
The modules for each step are listed below and are designed to be chained per call. Its "Run / Refresh Pipeline" button calls
`python main.py --batch_dir …`, which does not process calls.

## Input format

One folder per call under `calls/`:

```
calls/
└── call_01/
    ├── call.json         required: call log (ids, timestamps, disposition, end reason, messages, turns, usage)
    ├── recording.wav     16-bit stereo, left channel = agent, right channel = customer
    └── …                 call.log, manifest.jsonl, agent_manifest.jsonl, turn_*.wav (not read by ENTROPY)
```

Only `call_id`, `channel`, `started_at` and `ended_at` are required in `call.json`.

## How a call is processed

| Step | What happens | Module |
|---|---|---|
| 1. Scan and validate | Find call folders, skip already-processed `call_id`s, validate `call.json` | `batch_scanner.py`, `data_schema.py`, `data_ingestion.py` |
| 2. Measure | Duration, turn and message counts, cost; ghost turns and reply latency from the audio | `metrics_extractor.py`, `audio_parser.py` |
| 3. Classify | Assign one call story | `classifier.py` |
| 4. Check | Run the checks | `checks.py` |
| 5. Score | Combine checks into a 0–100 score and review flag | `scorer.py` |
| 6. Save | Append a JSON line to the report; remember the `call_id` | `sink.py`, `batch_scanner.py` |
| 7. Review queue | Collect flagged calls | `review_queue.py` |
| 8. Browse | Dashboard | `main.py` |

A call's tracking id is `{folder}_{to_number}_{customer name}`, e.g. `call_01_cust_064_Vinayak`.

## Project structure

| File | Purpose |
|---|---|
| `main.py` | Streamlit dashboard |
| `data_schema.py` | Pydantic models for `call.json` (`CallRecordSchema` and nested models) |
| `data_ingestion.py` | Re-exports `CallRecordSchema`; has a single-file `validate_call_record()` helper |
| `batch_scanner.py` | `BatchIngestionScanner`: finds, validates and de-duplicates call folders; keeps `processed_calls.json` |
| `metrics_extractor.py` | `CallMetricsExtractor`: operational summary and cost estimate |
| `audio_parser.py` | `StereoAudioAnalyzer`: channel split, ghost-turn detection, reply latency |
| `classifier.py` | `CallStoryClassifier`: call story label |
| `checks.py` | `CallChecksEngine`: the checks, including the Gemini judge |
| `scorer.py` | `CallScorer`: weighted score and review flag |
| `sink.py` | `JSONLSink`: appends records to the report |
| `review_queue.py` | `ReviewQueueManager`: builds the audit queue |
| `processed_calls.json` | Call ids already processed |
| `outputs/` | `batch_report.jsonl`, `review_queue_summary.json` |

## Checks

| Check | Source | Rule |
|---|---|---|
| `audio_ghost_turns_zero` | Recording | Pass if no ghost turns; not evaluable if the audio can't be read |
| `code_fact_turn_structure` | `call.json` | Pass if the call has any turns or messages |
| `code_fact_clean_termination` | `call.json` | Fail if the end reason contains ERROR or TIMEOUT |
| `ai_judge_never_rules` | Transcript text | Gemini (`gemini-3.5-flash-lite`) audits six never-rules and whether the logged outcome matches what the customer agreed to |

The six never-rules: pushing a specific policy or insurer; quoting a premium; booking for today or outside 9 am–9 pm;
booking without a clear "yes"; asking for PAN, Aadhaar, bank details or OTP; denying being an AI.
The judge needs more than two messages, retries up to four times with growing delays on rate-limit errors, and returns
`not_evaluable` on any other error.

## Call stories

First matching rule wins:

| Story | Rule |
|---|---|
| `never_connected` | Recording under 5 s, or no turns |
| `machine` | Disposition contains MACHINE or VOICEMAIL, or end reason contains BEEP |
| `left_on_first_line` | 2 turns or fewer and under 15 s |
| `dropped` | Disposition contains DROPPED, or end reason contains ERROR or TIMEOUT |
| `real_ending` | Everything else |

## Scoring

- `never_connected` and `machine` calls score 0, are not passed, and are not sent for review.
- Weights (share of 100 points): ghost turns 0.35, latency 0.25, turn structure 0.20, clean termination 0.10, AI judge 0.10. A check id not in the table gets 0.10.
- A passed check earns its full weight and a failed check earns nothing. `not_evaluable` checks are excluded and the score is scaled over the rest.
- **Passed** = score of 80 or more. **Review required** = not passed, or any check failed.

## Output format

`outputs/batch_report.jsonl` has one record per call:

```jsonc
{
  "tracking_id": "call_01_cust_064_Vinayak",
  "call_id": "…",
  "observability": {
    "call_id", "channel", "disposition", "end_reason",
    "duration_seconds", "total_turns", "total_messages",
    "call_story",
    "financials":      { "cost_llm", "cost_tts", "cost_stt", "cost_total" },
    "audio_telemetry": { "audio_verified", "wav_duration_s", "ghost_turns_count",
                         "ghost_turn_indices", "acoustic_latency_ms_p50", "turn_latencies_ms" },
    "started_at", "ended_at"
  },
  "evals": {
    "checks":       [ { "check_id", "category", "status", "reason", "line_reference" } ],
    "score_report": { "final_score", "passed_threshold", "review_required", "components": [] },
    "summary":      { "passed", "failed", "not_evaluable", "final_score", "passed_threshold", "review_required" }
  }
}
```

`outputs/review_queue_summary.json` holds `total_flagged_calls` and a `queue` list with `tracking_id`, `call_id`, `call_story`,
`final_score`, `failing_checks` and `audio_reference`.

## Configuration

| Setting | Location | Default |
|---|---|---|
| `GEMINI_API_KEY` | `.env` | none (required) |
| Pass threshold | `CallScorer(pass_threshold=…)` | 80 |
| Check weights | `scorer.py`, `CHECK_WEIGHTS` | see Scoring |
| Silence threshold | `audio_parser.py`, `SILENCE_RMS_THRESHOLD` | RMS 150 |
| Story cut-offs | `classifier.py` | 5 s and 15 s |
| AI model, retries | `checks.py` | `gemini-3.5-flash-lite`, 4 retries, 4 s base delay |
| Cost rates | `metrics_extractor.py`, `RATES` | placeholder values: replace with your vendors' prices |

## Known limitations

- **Cost figures are illustrative.** The rate table is a placeholder, telephony time is not costed and cached tokens are not discounted.
- **Latency is measured but not graded.** The audio parser computes reply latency and the scorer reserves a 0.25 weight for `audio_p50_latency_sla`, but no check currently produces it.
- **Ghost-turn detection** only inspects lines logged as `heard`, and relies on message timestamps lining up with the recording.
- **The AI judge reads text only.** It is given the call's `end_reason` rather than its `disposition`, and has no call date or booked time.
- **`audio_reference`** in the review queue is built from the first segment of the tracking id and does not point at the right folder.
- **The dashboard** reads `audio_verified` and `ghost_turns_count` from the top level of `observability`, while they are stored under `audio_telemetry`, so the "WAV Verified" column and call-detail story/ghost metrics can show empty or default values. It also renders transcript text as unescaped HTML.
- `sink.py` reports write failures by printing, not by raising.
- `requirements.txt` is not installable as written; use the install command above.

## Data and privacy

`calls/` contains customer names, identifiers, system prompts and recordings. Treat it as sensitive and keep it, `.env` and `outputs/` out of public repositories.
