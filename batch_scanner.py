# scanner.py
import os
import json
import logging
from pathlib import Path
from typing import Generator, Tuple, Set
from pydantic import ValidationError

from data_ingestion import CallRecordSchema

# Configure module-level logger
logger = logging.getLogger("EntropyScanner")

class BatchIngestionScanner:
    """
    Crawls a local directory for call folders, validates call.json against 
    the Pydantic schema, tracks processed state, and yields clean records.
    """
    def __init__(self, batch_dir: str, state_file: str = "processed_calls.json"):
        self.batch_dir = Path(batch_dir)
        self.state_file = Path(state_file)
        self.processed_ids = self._load_state()

    def _load_state(self) -> Set[str]:
        """Loads the set of already processed call_ids to enable idempotent re-runs."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return set(data.get("processed_ids", []))
            except Exception as e:
                logger.warning(f"Could not load state file: {e}. Starting fresh.")
        return set()

    def _save_state(self):
        """Persists the updated state tracking list to disk."""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({"processed_ids": list(self.processed_ids)}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state file: {e}")

    def scan_folders(self) -> Generator[Tuple[Path, CallRecordSchema], None, None]:
        """
        Generator that scans subdirectories, validates call.json files, 
        and skips already processed records.
        """
        if not self.batch_dir.exists():
            logger.error(f"Batch directory {self.batch_dir} does not exist.")
            return

        for call_folder in sorted(self.batch_dir.iterdir()):
            if not call_folder.is_dir():
                continue

            json_path = call_folder / "call.json"
            if not json_path.exists():
                logger.warning(f"Skipping {call_folder.name}: Missing call.json")
                continue

            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)

                call_id = raw_data.get("call_id")
                if call_id in self.processed_ids:
                    logger.debug(f"Skipping already processed call_id: {call_id}")
                    continue

                # Validate against Pydantic data contract
                validated_record = CallRecordSchema(**raw_data)
                yield call_folder, validated_record

            except json.JSONDecodeError as jde:
                logger.error(f"JSON syntax error in {json_path}: {jde}")
            except ValidationError as ve:
                logger.error(f"Schema validation failed for {call_folder.name}: {ve}")
            except Exception as ex:
                logger.error(f"Unexpected error processing {call_folder.name}: {ex}")

    def mark_processed(self, call_id: str):
        """Marks a call ID as successfully processed and updates state storage."""
        self.processed_ids.add(call_id)
        self._save_state()