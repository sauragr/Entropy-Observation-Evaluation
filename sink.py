# sink.py
import json
from pathlib import Path
from typing import Dict, Any

class JSONLSink:
    """
    Append-safe JSONL writer that takes fully enriched call records 
    and writes them out to disk line-by-line for downstream analytics.
    """
    
    def __init__(self, output_path: str = "outputs/batch_report.jsonl"):
        self.output_path = Path(output_path)
        # Automatically create the 'outputs' directory if it doesn't exist yet
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def write_record(self, enriched_record: Dict[str, Any]):
        """Appends a single structured record as a JSON line."""
        try:
            with open(self.output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(enriched_record) + "\n")
        except Exception as e:
            print(f"Failed to write record to JSONL sink: {e}")