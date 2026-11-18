from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

# -------------------------------------------------------------------------
# Sub-models for nested structures within call.json
# -------------------------------------------------------------------------

class ModelDetails(BaseModel):
    """Tracks the AI provider, model identifier, and policy configuration used."""
    provider: Optional[str] = Field(None, description="The AI service provider (e.g., gemini)")
    model: Optional[str] = Field(None, description="The specific model name/version")
    policy_source: Optional[str] = Field(None, description="Source origin of the policy logic")
    agent: Optional[str] = Field(None, description="Name of the persona or agent handling the call")


class TTSVoiceDetails(BaseModel):
    """Configuration parameters for the Text-to-Speech (TTS) engine."""
    tts: Optional[str] = Field(None, description="TTS provider name")
    speaker: Optional[str] = Field(None, description="Speaker voice identifier")
    pace: Optional[float] = Field(None, description="Speech rate/pace modifier")
    pitch: Optional[float] = Field(None, description="Speech pitch modifier")


class MetaDetails(BaseModel):
    """
    Contains granular metadata regarding campaigns, carrier info, and system prompts.
    Marked as Optional because inbound calls, manual tests, or dropped calls 
    frequently omit campaign tracking keys or voice overrides.
    """
    custom_agent_id: Optional[str] = Field(None, description="Unique identifier for the agent configuration")
    name: Optional[str] = Field(None, description="Customer or persona display name")
    started_by: Optional[str] = Field(None, description="Initiator of the call (e.g., campaign, manual)")
    attempt_no: Optional[int] = Field(None, description="Retry attempt number for outbound dials")
    campaign_id: Optional[str] = Field(None, description="Associated campaign UUID")
    campaign_call_id: Optional[str] = Field(None, description="Specific campaign call tracking reference")
    to: Optional[str] = Field(None, description="Destination target identifier")
    is_test: Optional[bool] = Field(None, description="Flag indicating if the call was a test run")
    carrier: Optional[str] = Field(None, description="Telephony carrier gateway used (e.g., vobiz, twilio)")
    ring_s: Optional[float] = Field(None, description="Duration the phone rang in seconds")
    tts_voice: Optional[TTSVoiceDetails] = Field(None, description="Nested TTS voice configurations")
    llm_system: Optional[Dict[str, Any]] = Field(default_factory=dict, description="System prompt SHA, text, and tool specs")
    usage: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Raw token, STT, TTS, and telephony usage counters")


class LatencyMetrics(BaseModel):
    """
    Performance benchmarks and latency tracking across conversation turns.
    Percentiles default to None when a call drops before enough turns occur.
    """
    conversation_id: Optional[str] = Field(None, description="Conversation tracking UUID")
    turns: Optional[int] = Field(0, description="Total number of completed turns")
    true_barges: Optional[int] = Field(0, description="Count of valid customer interruptions")
    false_barges: Optional[int] = Field(0, description="Count of false-trigger interruptions")
    to_stop_ms_p50: Optional[float] = Field(None, description="Median time to stop audio on interruption (ms)")
    endpoint_ms_p50: Optional[float] = Field(None, description="Median end-of-utterance detection delay (ms)")
    brain_ms_p50: Optional[float] = Field(None, description="Median LLM response latency (ms)")
    tts_ms_p50: Optional[float] = Field(None, description="Median TTS first-byte latency (ms)")
    perceived_ms_p50: Optional[float] = Field(None, description="Median total perceived reply wait time (ms)")


class MessageItem(BaseModel):
    """Represents an individual chat or dialogue message in the conversation history."""
    role: str = Field(..., description="Role of the speaker (e.g., assistant, user)")
    content: str = Field(..., description="The textual content spoken or written")
    t: float = Field(..., description="Timestamp offset in seconds")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context or tracing metadata")


class TurnItem(BaseModel):
    """
    Detailed livekit turn-level performance and telemetry data. 
    Marked as Optional because different call types or dropped turns 
    may omit granular logging metrics like head_start or token counts.
    """
    kind: Optional[str] = Field(None, description="Type of turn source (e.g., livekit)")
    t: Optional[float] = Field(None, description="Timestamp offset")
    turn_detection: Optional[str] = Field(None, description="Detection mode used")
    head_start: Optional[bool] = Field(None, description="Head start flag")
    eou_ms: Optional[float] = Field(None, description="End of utterance milliseconds")
    transcription_ms: Optional[float] = Field(None, description="STT transcription duration")
    tts_ttfb_ms: Optional[float] = Field(None, description="TTS time-to-first-byte")
    tts_by: Optional[str] = Field(None, description="TTS provider engine")
    llm_ttft_ms: Optional[float] = Field(None, description="LLM time-to-first-token")
    perceived_ms: Optional[float] = Field(None, description="Perceived latency metric")
    speculative: Optional[bool] = Field(None, description="Whether turn was speculative")
    since_final_ms: Optional[float] = Field(None, description="Time since final evaluation")
    overlap_ms: Optional[float] = Field(None, description="Audio overlap duration")
    perceived_net_ms: Optional[float] = Field(None, description="Net perceived latency")
    tok_in: Optional[int] = Field(None, description="Input token count")
    tok_out: Optional[int] = Field(None, description="Output token count")
    tok_cached: Optional[int] = Field(None, description="Cached token count")
    endpointing: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Endpointing configuration")
    eou_pinned: Optional[bool] = Field(None, description="EOU pin status")
    finals_in_turn: Optional[int] = Field(None, description="Finals count in turn")
    final_gap_ms: Optional[float] = Field(None, description="Gap before final")
    nudge_in_turn: Optional[int] = Field(None, description="Nudge count")
    trace: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Execution trace dictionary")


class Artifacts(BaseModel):
    """Points to external asset outputs generated by the call session."""
    recording: Optional[str] = Field(None, description="Filename or path to the main audio recording")


# -------------------------------------------------------------------------
# Root Schema
# -------------------------------------------------------------------------

class CallRecordSchema(BaseModel):
    """
    The master Pydantic validation schema representing the complete structure 
    of an individual call execution file (call.json).
    Only core identifiers and primary timestamps are strictly required; 
    all operational metadata degrades gracefully if absent.
    """
    # Strictly required core indexing fields
    call_id: str = Field(..., description="Unique UUID identifier for the call")
    channel: str = Field(..., description="Communication medium channel (e.g., phone)")
    started_at: datetime = Field(..., description="ISO timestamp when the call started")
    ended_at: datetime = Field(..., description="ISO timestamp when the call concluded")

    # Optional operational & routing metadata
    call_key: Optional[str] = Field(None, description="Combined customer and call reference key")
    room: Optional[str] = Field(None, description="LiveKit or telephony room identifier")
    environment: Optional[str] = Field(None, description="Deployment environment (e.g., staging, production)")
    to_number: Optional[str] = Field(None, description="Recipient or target reference identifier")
    disposition: Optional[str] = Field(None, description="Final operational status or outcome disposition")
    final_state: Optional[str] = Field(None, description="State where the call ended")
    end_reason: Optional[str] = Field(None, description="Reason for call termination")
    state_path: List[str] = Field(default_factory=list, description="Progression path of states during the session")
    policy_id: Optional[str] = Field(None, description="Identifier for active policy rules")
    policy_source: Optional[str] = Field(None, description="Source origin of the policy logic")
    
    # Optional nested blocks with safe defaults
    models: Optional[ModelDetails] = Field(None, description="AI model and agent persona details")
    meta: Optional[MetaDetails] = Field(None, description="Campaign, carrier, and usage metadata")
    action_dispatch: Optional[Any] = Field(None, description="Pending or executed dispatch actions")
    latency: Optional[LatencyMetrics] = Field(None, description="Aggregate call latency benchmarks")
    messages: List[MessageItem] = Field(default_factory=list, description="Chronological log of messages exchanged")
    turns: List[TurnItem] = Field(default_factory=list, description="Technical breakdown of conversation turns")
    barges: List[Any] = Field(default_factory=list, description="Interruption or barge-in events")
    artifacts: Optional[Artifacts] = Field(None, description="External recording references")