

# review_queue.py
import json
from pathlib import Path
from typing import List, Dict, Any

class ReviewQueueManager:
    """
    Scans the batch report JSONL sink to isolate calls requiring human audit
    based on review flags, failed checks, or low composite scores.
    """

    def __init__(self, report_path: str = "outputs/batch_report.jsonl"):
        self.report_path = Path(report_path)

    def load_flagged_calls(self) -> List[Dict[str, Any]]:
        """Reads the JSONL report and returns all records flagged for human review."""
        if not self.report_path.exists():
            return []

        flagged_calls = []
        with open(self.report_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                evals = record.get("evals", {})
                score_report = evals.get("score_report", {})
                
                # Check if review is explicitly required or score is below passing threshold
                if score_report.get("review_required", False):
                    flagged_calls.append(record)
                    
        return flagged_calls

    def generate_audit_summary(self, output_path: str = "outputs/review_queue_summary.json") -> int:
        """
        Extracts flagged records, formats them into a dedicated auditor queue payload,
        and writes them out to a review-specific file.
        """
        flagged = self.load_flagged_calls()
        
        audit_payload = {
            "total_flagged_calls": len(flagged),
            "queue": []
        }

        for record in flagged:
            # Safely fallback if tracking_id is missing or None in older/legacy records
            tracking_id = record.get("tracking_id") or "unknown_tracking_id"
            obs = record.get("observability", {})
            evals = record.get("evals", {})
            score_report = evals.get("score_report", {})
            
            # Safely extract folder name prefix without crashing if tracking_id is None
            folder_prefix = tracking_id.split('_')[0] if tracking_id and '_' in tracking_id else "unknown"
            
            # Extract failing or noteworthy check reasons for the reviewer
            failing_checks = [
                {
                    "check_id": c.get("check_id"),
                    "category": c.get("category"),
                    "reason": c.get("reason"),
                    "line_reference": c.get("line_reference")
                }
                for c in score_report.get("components", []) if c.get("status") == "fail"
            ]

            audit_payload["queue"].append({
                "tracking_id": tracking_id,
                "call_id": record.get("call_id"),
                "call_story": obs.get("call_story"),
                "final_score": score_report.get("final_score"),
                "failing_checks_count": len(failing_checks),
                "failing_checks": failing_checks,
                "audio_reference": f"./calls/{folder_prefix}/recording.wav" # Pointer to raw audio artifact
            })

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(audit_payload, f, indent=2)

        return len(flagged)

if __name__ == "__main__":
    manager = ReviewQueueManager()
    count = manager.generate_audit_summary()
    print(f"Review Queue generated successfully. {count} call(s) require human audit.")