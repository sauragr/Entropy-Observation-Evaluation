# metrics_extractor.py
import logging
from typing import Dict, Any
from data_ingestion import CallRecordSchema

logger = logging.getLogger("EntropyMetrics")

class CallMetricsExtractor:
    """
    Extracts financial costs, operational dispositions, and core performance 
    metrics directly from a validated CallRecordSchema instance.
    """
    
    # Example Provider Rate Cards (per unit)
    # Adjust these values based on your active vendor contracts
    RATES = {
        "llm_input_per_1k": 0.00015,   # e.g., Gemini Flash Lite input cost per 1K tokens
        "llm_output_per_1k": 0.00060,  # e.g., Gemini Flash Lite output cost per 1K tokens
        "tts_char_per_1k": 0.00400,    # e.g., Sarvam TTS cost per 1K characters
        "stt_second": 0.00010,         # e.g., STT cost per active audio second
        "telephony_second": 0.00020    # e.g., Carrier trunking cost per second
    }

    def __init__(self, record: CallRecordSchema):
        self.record = record

    def calculate_costs(self) -> Dict[str, float]:
        """
        Computes granular and total financial costs for the call session 
        based on usage metrics stored in the call record.
        """
        # Safely extract usage dictionary from meta or root depending on structure
        usage_data = {}
        if self.record.meta and hasattr(self.record.meta, "usage") and self.record.meta.usage:
            usage_data = self.record.meta.usage
        
        # Fallback extraction if usage is stored elsewhere in raw data dictionary
        # (We parse safely to prevent AttributeErrors on malformed usage blocks)
        llm_in = 0
        llm_out = 0
        tts_chars = 0
        audio_s = 0.0
        
        # Extract LLM tokens if present
        llm_block = usage_data.get("llm", {}) if isinstance(usage_data, dict) else {}
        llm_in = llm_block.get("input_tokens", 0) or 0
        llm_out = llm_block.get("output_tokens", 0) or 0

        # Extract TTS characters if present
        tts_block = usage_data.get("tts", {}) if isinstance(usage_data, dict) else {}
        tts_chars = tts_block.get("characters", 0) or 0

        # Extract STT / Audio seconds if present
        stt_block = usage_data.get("stt", {}) if isinstance(usage_data, dict) else {}
        audio_s = stt_block.get("audio_s", 0.0) or 0.0

        # Compute individual cost line items
        cost_llm = (llm_in / 1000.0 * self.RATES["llm_input_per_1k"]) + \
                   (llm_out / 1000.0 * self.RATES["llm_output_per_1k"])
                   
        cost_tts = (tts_chars / 1000.0 * self.RATES["tts_char_per_1k"])
        cost_stt = (audio_s * self.RATES["stt_second"])
        
        total_cost = cost_llm + cost_tts + cost_stt

        return {
            "cost_llm": round(cost_llm, 6),
            "cost_tts": round(cost_tts, 6),
            "cost_stt": round(cost_stt, 6),
            "cost_total": round(total_cost, 6)
        }

    def extract_operational_summary(self) -> Dict[str, Any]:
        """
        Extracts high-level operational metrics like call duration, turn volume, 
        and final outcome disposition.
        """
        # Calculate wall-clock duration if timestamps exist
        duration_seconds = None
        if self.record.started_at and self.record.ended_at:
            duration_seconds = (self.record.ended_at - self.record.started_at).total_seconds()

        return {
            "call_id": self.record.call_id,
            "channel": self.record.channel,
            "disposition": self.record.disposition,
            "end_reason": self.record.end_reason,
            "duration_seconds": duration_seconds,
            "total_turns": len(self.record.turns) if self.record.turns else 0,
            "total_messages": len(self.record.messages) if self.record.messages else 0
        }