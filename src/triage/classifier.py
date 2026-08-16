"""Issue triage classifier using LLM with structured output.

Classifies GitHub issues into kind/area/priority categories using an LLM,
with confidence thresholds for auto-label vs. human escalation decisions.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..llm_client import LLMClient, LLMResponse
from ..audit_log import AuditLogger
from .prompts import build_triage_prompt
from .issue_parser import parse_issue, ParsedIssue


@dataclass 
class TriageResult:
    """Result of classifying an issue."""
    issue_number: int
    issue_title: str
    kind_label: str = ""
    kind_confidence: float = 0.0
    area_label: str = ""
    area_confidence: float = 0.0
    priority_hint: str = ""
    reasoning: str = ""
    needs_more_info: bool = False
    action: str = "escalate"  # "auto_label" or "escalate"
    escalation_reason: str = ""
    raw_llm_output: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    parse_error: bool = False
    
    def to_dict(self) -> dict:
        return {
            "issue_number": self.issue_number,
            "issue_title": self.issue_title,
            "kind_label": self.kind_label,
            "kind_confidence": self.kind_confidence,
            "area_label": self.area_label,
            "area_confidence": self.area_confidence,
            "priority_hint": self.priority_hint,
            "reasoning": self.reasoning,
            "needs_more_info": self.needs_more_info,
            "action": self.action,
            "escalation_reason": self.escalation_reason,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "parse_error": self.parse_error,
        }


class TriageClassifier:
    """Classifies GitHub issues using LLM with confidence thresholds.
    
    The classifier:
    1. Parses the issue using template-aware parsing
    2. Sends to LLM with structured output request
    3. Parses response JSON
    4. Applies confidence thresholds
    5. Logs everything to audit log
    6. Never makes any write calls — only recommends actions
    """
    
    # Valid labels for output validation
    VALID_KIND_LABELS = {"kind/bug", "kind/feature", "kind/question", "kind/cleanup"}
    VALID_AREA_LABELS = {
        "area/engine", "area/cli", "area/webhooks", "area/api",
        "area/documentation", "area/reports", "area/cleanup",
        "area/image-verify", "area/cel", "area/helm",
        "area/background", "area/controllers",
    }
    VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}
    
    def __init__(
        self,
        llm_client: LLMClient,
        audit_logger: AuditLogger,
        confidence_threshold: float = 0.75,
        escalation_threshold: float = 0.5,
    ):
        self.llm = llm_client
        self.audit = audit_logger
        self.confidence_threshold = confidence_threshold
        self.escalation_threshold = escalation_threshold
    
    def classify(self, issue_number: int, title: str, body: str) -> TriageResult:
        """Classify a single issue.
        
        Args:
            issue_number: GitHub issue number
            title: Issue title
            body: Issue body
        
        Returns:
            TriageResult with classification and action recommendation
        """
        result = TriageResult(issue_number=issue_number, issue_title=title)
        
        # Parse the issue
        parsed = parse_issue(title, body)
        
        # Check for minimal content
        if parsed.is_minimal:
            result.action = "escalate"
            result.escalation_reason = "Issue body too short for reliable classification"
            result.needs_more_info = True
            self._log_decision(result, parsed)
            return result
        
        # Build prompt
        system_prompt, user_prompt = build_triage_prompt(title, body)
        
        # Call LLM
        try:
            llm_response = self.llm.chat(system_prompt, user_prompt)
        except Exception as e:
            result.action = "escalate"
            result.escalation_reason = f"LLM call failed: {str(e)}"
            self._log_decision(result, parsed)
            return result
        
        result.raw_llm_output = llm_response.content
        result.model = llm_response.model
        result.input_tokens = llm_response.input_tokens
        result.output_tokens = llm_response.output_tokens
        result.cost_usd = llm_response.estimated_cost_usd
        result.latency_ms = llm_response.latency_ms
        
        # Parse LLM response
        try:
            classification = self._parse_llm_output(llm_response.content)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            result.action = "escalate"
            result.escalation_reason = f"Failed to parse LLM output: {str(e)}"
            result.parse_error = True
            self._log_decision(result, parsed)
            return result
        
        # Extract classification & analysis blocks
        analysis = classification.get("analysis", {})
        detected_injections = analysis.get("detected_injections", "none")
        clarity_level = analysis.get("clarity_level", "medium").lower()
        needs_review = classification.get("needs_human_review", False) or classification.get("needs_more_info", False)
        
        result.kind_label = classification.get("kind", {}).get("label", "")
        raw_kind_conf = classification.get("kind", {}).get("confidence", 0.85)
        result.area_label = classification.get("area", {}).get("label", "")
        raw_area_conf = classification.get("area", {}).get("confidence", 0.85)
        result.priority_hint = classification.get("priority_hint", "P3")
        result.reasoning = classification.get("reasoning", "")
        result.needs_more_info = needs_review
        
        # Validate labels against allowed set
        if result.kind_label and result.kind_label not in self.VALID_KIND_LABELS:
            result.action = "escalate"
            result.escalation_reason = f"Invalid kind label: {result.kind_label}"
            self._log_decision(result, parsed)
            return result
        
        if result.area_label and result.area_label not in self.VALID_AREA_LABELS:
            result.action = "escalate"
            result.escalation_reason = f"Invalid area label: {result.area_label}"
            self._log_decision(result, parsed)
            return result
        
        # Normalize detected_injections representation
        if isinstance(detected_injections, list):
            injections_str = ", ".join(str(x) for x in detected_injections)
            has_injection = len(detected_injections) > 0 and not all(str(x).lower() in ("none", "none.", "n/a", "no", "false") for x in detected_injections)
        else:
            injections_str = str(detected_injections)
            has_injection = bool(injections_str) and injections_str.lower().strip() not in ("none", "none.", "n/a", "no", "false", "[]", "")
        
        # Calculate Calibrated Composite Confidence (Heuristic + Model ambiguity)
        result.kind_confidence = self._calibrate_confidence(
            raw_conf=raw_kind_conf,
            clarity=clarity_level,
            has_injection=has_injection,
            needs_review=needs_review,
            parsed=parsed,
        )
        result.area_confidence = self._calibrate_confidence(
            raw_conf=raw_area_conf,
            clarity=clarity_level,
            has_injection=has_injection,
            needs_review=needs_review,
            parsed=parsed,
        )
        
        # Apply confidence thresholds and safety gates
        min_confidence = min(
            result.kind_confidence if result.kind_label else 1.0,
            result.area_confidence if result.area_label else 1.0,
        )
        
        if has_injection:
            result.action = "escalate"
            result.escalation_reason = f"Adversarial injection detected ({injections_str}) — escalated for human safety review"
        elif min_confidence >= self.confidence_threshold:
            result.action = "auto_label"
        elif min_confidence >= self.escalation_threshold:
            result.action = "escalate"
            result.escalation_reason = f"Confidence {min_confidence:.2f} below auto-label threshold {self.confidence_threshold}"
        else:
            result.action = "escalate"
            result.escalation_reason = f"Confidence {min_confidence:.2f} too low for reliable classification"
        
        self._log_decision(result, parsed)
        return result
    
    def _calibrate_confidence(
        self,
        raw_conf: float,
        clarity: str,
        has_injection: bool,
        needs_review: bool,
        parsed: ParsedIssue,
    ) -> float:
        """Derive a calibrated confidence score combining model certainty and structural signals."""
        # 1. Start from model's self-reported certainty (without forcing a hard floor)
        base = raw_conf
        
        # 2. Adjust based on clarity assessment
        if clarity == "high":
            base += 0.05
        elif clarity == "low":
            base -= 0.25
        elif clarity == "medium":
            base -= 0.05
        
        # 3. Structural heuristics: template usage and reproduction artifacts
        if parsed.uses_template and (parsed.has_yaml_blocks or parsed.has_error_logs):
            base += 0.05  # High-quality structured issue with logs/YAML
        elif not parsed.uses_template and not parsed.has_yaml_blocks and not parsed.has_error_logs:
            base -= 0.15  # Unstructured free-form issue penalty
        
        # 4. Penalize if adversarial injection or conflicting directives were found
        if has_injection:
            base -= 0.25
        
        # 5. Cap if human review was explicitly requested
        if needs_review:
            base = min(base, 0.60)
        
        return round(max(0.10, min(base, 0.98)), 2)
    
    def _parse_llm_output(self, raw_output: str) -> dict:
        """Parse and validate LLM JSON output.
        
        Handles common issues:
        - Markdown code blocks around JSON
        - Extra text before/after JSON
        - Deeply nested structures
        """
        # Strip markdown code blocks if present
        cleaned = raw_output.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        cleaned = cleaned.strip()
        
        # Try direct JSON parsing
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON between outermost braces
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start:end + 1])
        
        raise json.JSONDecodeError("No JSON object found", raw_output, 0)
    
    def _log_decision(self, result: TriageResult, parsed: ParsedIssue):
        """Log the triage decision to audit log."""
        self.audit.log(
            action="triage_classify",
            input_summary=f"Issue #{result.issue_number}: {result.issue_title}",
            decision={
                "kind_label": result.kind_label,
                "area_label": result.area_label,
                "priority_hint": result.priority_hint,
                "action": result.action,
                "escalation_reason": result.escalation_reason,
            },
            confidence=min(
                result.kind_confidence if result.kind_label else 1.0,
                result.area_confidence if result.area_label else 1.0,
            ),
            model=result.model,
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            extra={
                "uses_template": parsed.uses_template,
                "body_length": parsed.body_length,
                "has_yaml": parsed.has_yaml_blocks,
                "has_errors": parsed.has_error_logs,
                "needs_more_info": result.needs_more_info,
                "parse_error": result.parse_error,
            },
        )
