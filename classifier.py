# classifier.py
from typing import Dict, Any
from data_ingestion import CallRecordSchema

class CallStoryClassifier:
    """
    Programmatically classifies the macro outcome / narrative story of a call session
    based on duration, turns, disposition, and audio telemetry.
    """

    def __init__(self, record: CallRecordSchema, audio_metrics: Dict[str, Any]):
        self.record = record
        self.audio_metrics = audio_metrics

    def classify(self) -> str:
        """Evaluates deterministic heuristics to return a clean call story category label."""
        total_turns = len(self.record.turns) if self.record.turns else 0
        duration = self.audio_metrics.get("wav_duration_s", 0.0)
        disposition = (self.record.disposition or "").upper()
        end_reason = (self.record.end_reason or "").upper()

        # 1. Never Connected / Instant Drop
        if duration < 5.0 or total_turns == 0:
            return "never_connected"

        # 2. Answering Machine / Voicemail detection
        if "MACHINE" in disposition or "VOICEMAIL" in disposition or "BEEP" in end_reason:
            return "machine"

        # 3. Left on First Line (Customer hung up immediately after greeting)
        if total_turns <= 2 and duration < 15.0:
            return "left_on_first_line"

        # 4. Premature Drop / Network Disconnect
        if "DROPPED" in disposition or "ERROR" in end_reason or "TIMEOUT" in end_reason:
            return "dropped"

        # 5. Standard Natural Ending
        return "real_ending"