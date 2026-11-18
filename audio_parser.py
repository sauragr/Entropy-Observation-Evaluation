# audio_parser.py
import wave
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np

from data_ingestion import CallRecordSchema

logger = logging.getLogger("EntropyAudio")

class StereoAudioAnalyzer:
    """
    Parses stereo recording.wav files to verify acoustic truth against call.json logs.
    Channel 0 (Left) = Agent | Channel 1 (Right) = Customer
    """

    # Volume threshold on a 0–32,768 scale. Below 150 = silence/line hiss.
    SILENCE_RMS_THRESHOLD = 150.0

    def __init__(self, wav_path: Path):
        self.wav_path = wav_path
        self.sample_rate: int = 0
        self.channels: int = 0
        self.duration_s: float = 0.0
        self.agent_track: Optional[np.ndarray] = None
        self.customer_track: Optional[np.ndarray] = None

    def load_and_split_channels(self) -> bool:
        """
        Reads a 16-bit stereo WAV file and splits it into separate arrays
        for the agent (Left) and customer (Right).
        """
        if not self.wav_path.exists():
            logger.warning(f"Audio file missing: {self.wav_path}")
            return False

        try:
            with wave.open(str(self.wav_path), "rb") as wf:
                self.channels = wf.getnchannels()
                self.sample_rate = wf.getframerate()
                sample_width = wf.getsampwidth()
                n_frames = wf.getnframes()

                if self.channels != 2:
                    logger.warning(f"Expected stereo (2 channels), got {self.channels} in {self.wav_path.name}")
                    return False

                if sample_width != 2:
                    logger.warning(f"Expected 16-bit PCM (width=2), got width={sample_width}")
                    return False

                raw_bytes = wf.readframes(n_frames)
                audio_data = np.frombuffer(raw_bytes, dtype=np.int16)

                # Unzip interleaved stereo [Agent, Customer, Agent, Customer...] into 2 columns
                stereo_frames = audio_data.reshape(-1, 2)

                # Cast to float32 before squaring in RMS calculations to prevent int16 overflow
                self.agent_track = stereo_frames[:, 0].astype(np.float32)
                self.customer_track = stereo_frames[:, 1].astype(np.float32)
                self.duration_s = n_frames / float(self.sample_rate)

                return True

        except Exception as e:
            logger.error(f"Failed to parse WAV file {self.wav_path}: {e}")
            return False

    def _compute_rms(self, audio_slice: np.ndarray) -> float:
        """Computes the Volume Score (RMS) of a slice of audio rows."""
        if len(audio_slice) == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(audio_slice))))

    def detect_ghost_audio(self, record: CallRecordSchema) -> Dict[str, Any]:
        """
        Checks if assistant lines logged as 'heard' actually contain audible sound
        on the agent channel.
        """
        if self.agent_track is None:
            return {"ghost_turns_count": 0, "ghost_turn_indices": [], "ghost_details": []}

        ghost_turns = []

        for idx, msg in enumerate(record.messages):
            if msg.role != "assistant":
                continue

            meta = msg.metadata or {}
            spoken_status = meta.get("spoken")
            audio_duration = meta.get("audio_s", 0.0) or 0.0

            if spoken_status == "heard" and audio_duration > 0.1:
                start_sample = int(msg.t * self.sample_rate)
                end_sample = int((msg.t + audio_duration) * self.sample_rate)

                # Keep row indices safely within the recording length
                start_sample = max(0, min(start_sample, len(self.agent_track)))
                end_sample = max(start_sample, min(end_sample, len(self.agent_track)))

                segment = self.agent_track[start_sample:end_sample]
                rms_energy = self._compute_rms(segment)

                if rms_energy < self.SILENCE_RMS_THRESHOLD:
                    ghost_turns.append({
                        "message_index": idx,
                        "timestamp_s": msg.t,
                        "expected_duration_s": audio_duration,
                        "measured_rms": round(rms_energy, 2)
                    })

        return {
            "ghost_turns_count": len(ghost_turns),
            "ghost_turn_indices": [g["message_index"] for g in ghost_turns],
            "ghost_details": ghost_turns
        }

    def calculate_reply_latencies(self, record: CallRecordSchema) -> Dict[str, Any]:
        """
        Measures true acoustic dead air (ms) between customer speech ending
        and agent speech starting for each turn exchange.
        """
        if self.agent_track is None or self.customer_track is None:
            return {"acoustic_latency_ms_p50": None, "turn_latencies_ms": []}

        latencies_ms = []
        window_samples = int(0.020 * self.sample_rate)  # 20ms chunks

        for i in range(len(record.messages) - 1):
            curr_msg = record.messages[i]
            next_msg = record.messages[i + 1]

            if curr_msg.role == "user" and next_msg.role == "assistant":
                search_start = int(max(0, (curr_msg.t - 0.5)) * self.sample_rate)
                search_end = int(min(self.duration_s, (next_msg.t + 2.0)) * self.sample_rate)

                if search_end <= search_start:
                    continue

                # 1. Walk backward on Customer channel to find where they stopped talking
                agent_approx_start = int(min(self.duration_s, next_msg.t) * self.sample_rate)
                user_end_sample = None

                for pos in range(agent_approx_start, search_start, -window_samples):
                    chunk = self.customer_track[max(0, pos - window_samples):pos]
                    if self._compute_rms(chunk) > self.SILENCE_RMS_THRESHOLD:
                        user_end_sample = pos
                        break

                # 2. Walk forward on Agent channel to find where their voice arrived
                if user_end_sample is not None:
                    agent_start_sample = None
                    for pos in range(user_end_sample, search_end, window_samples):
                        chunk = self.agent_track[pos:min(len(self.agent_track), pos + window_samples)]
                        if self._compute_rms(chunk) > self.SILENCE_RMS_THRESHOLD:
                            agent_start_sample = pos
                            break

                    if agent_start_sample is not None and agent_start_sample >= user_end_sample:
                        gap_ms = ((agent_start_sample - user_end_sample) / float(self.sample_rate)) * 1000.0
                        latencies_ms.append(round(gap_ms, 2))

        p50_latency = float(np.median(latencies_ms)) if latencies_ms else None

        return {
            "acoustic_latency_ms_p50": round(p50_latency, 2) if p50_latency is not None else None,
            "turn_latencies_ms": latencies_ms
        }

    def analyze(self, record: CallRecordSchema) -> Dict[str, Any]:
        """Runs full audio truth analysis and returns a consolidated metrics dictionary."""
        if not self.load_and_split_channels():
            return {
                "audio_verified": False,
                "wav_duration_s": 0.0,
                "ghost_turns_count": 0,
                "ghost_turn_indices": [],
                "acoustic_latency_ms_p50": None,
                "turn_latencies_ms": []
            }

        ghost_metrics = self.detect_ghost_audio(record)
        latency_metrics = self.calculate_reply_latencies(record)

        return {
            "audio_verified": True,
            "wav_duration_s": round(self.duration_s, 2),
            "ghost_turns_count": ghost_metrics["ghost_turns_count"],
            "ghost_turn_indices": ghost_metrics["ghost_turn_indices"],
            "acoustic_latency_ms_p50": latency_metrics["acoustic_latency_ms_p50"],
            "turn_latencies_ms": latency_metrics["turn_latencies_ms"]
        }