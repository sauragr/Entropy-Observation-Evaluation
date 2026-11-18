# scorer.py
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from checks import CheckResult, CheckStatus

class ScoreComponent(BaseModel):
    """Detailed scoring breakdown for an individual check."""
    check_id: str
    category: str
    status: str
    weight: float
    points_earned: float
    max_points: float
    reason: str
    line_reference: Optional[str] = None

class CallScoreReport(BaseModel):
    """Aggregated post-call score report out of 100."""
    final_score: float  # Out of 100
    passed_threshold: bool
    review_required: bool
    components: List[ScoreComponent]

class CallScorer:
    """
    Calculates a post-call composite score out of 100 for answered calls based on check results,
    assigning weights, reasons, line references, and review triggers.
    """
    
    # Configure weights summing to 1.0 (100 points total across checks)
    CHECK_WEIGHTS = {
        "audio_ghost_turns_zero": 0.35,     # Critical safety check (no silent agent turns)
        "audio_p50_latency_sla": 0.25,      # Acoustic performance SLA
        "code_fact_turn_structure": 0.20,   # Schema & turn integrity
        "code_fact_clean_termination": 0.10, # Clean call end
        "ai_judge_intent_fulfillment": 0.10  # Semantic intent adherence
    }

    def __init__(self, check_results: List[CheckResult], call_story: str, pass_threshold: float = 80.0):
        self.check_results = check_results
        self.call_story = call_story
        self.pass_threshold = pass_threshold

    def calculate_score(self) -> CallScoreReport:
        """Aggregates checks into a normalized 0-100 score with component parts[cite: 1]."""
        # Bypasses conversational scoring for non-answered or dead calls
        if self.call_story in ["never_connected", "machine"]:
            return CallScoreReport(
                final_score=0.0,
                passed_threshold=False,
                review_required=False,
                components=[]
            )

        total_weight_evaluated = 0.0
        earned_points_weighted = 0.0
        components = []

        for check in self.check_results:
            weight = self.CHECK_WEIGHTS.get(check.check_id, 0.10)
            
            # Exclude 'not_evaluable' checks from the denominator so missing data doesn't unfairly penalize
            if check.status == CheckStatus.NOT_EVALUABLE:
                continue

            total_weight_evaluated += weight
            max_pts = weight * 100.0
            earned_pts = max_pts if check.status == CheckStatus.PASS else 0.0

            earned_points_weighted += earned_pts

            components.append(ScoreComponent(
                check_id=check.check_id,
                category=check.category,
                status=check.status.value,
                weight=weight,
                points_earned=round(earned_pts, 2),
                max_points=round(max_pts, 2),
                reason=check.reason,
                line_reference=check.line_reference
            ))

        # Normalize score if certain checks were 'not_evaluable'
        if total_weight_evaluated > 0:
            final_score = round((earned_points_weighted / (total_weight_evaluated * 100.0)) * 100.0, 2)
        else:
            final_score = 0.0

        passed = final_score >= self.pass_threshold
        review_required = not passed or any(c.status == "fail" for c in components)

        return CallScoreReport(
            final_score=final_score,
            passed_threshold=passed,
            review_required=review_required,
            components=components
        )