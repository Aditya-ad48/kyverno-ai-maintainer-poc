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
            result.parse_error = True
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
        
        # Apply classification
        result.kind_label = classification.get("kind", {}).get("label", "")
        result.kind_confidence = classification.get("kind", {}).get("confidence", 0.0)
        result.area_label = classification.get("area", {}).get("label", "")
        result.area_confidence = classification.get("area", {}).get("confidence", 0.0)
        result.priority_hint = classification.get("priority_hint", "P3")
        result.reasoning = classification.get("reasoning", "")
        result.needs_more_info = classification.get("needs_more_info", False)
        
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
        
        # Apply confidence thresholds
        min_confidence = min(
            result.kind_confidence if result.kind_label else 1.0,
            result.area_confidence if result.area_label else 1.0,
        )
        
        if min_confidence >= self.confidence_threshold:
            result.action = "auto_label"
        elif min_confidence >= self.escalation_threshold:
            result.action = "escalate"
            result.escalation_reason = f"Confidence {min_confidence:.2f} below auto-label threshold {self.confidence_threshold}"
        else:
            result.action = "escalate"
            result.escalation_reason = f"Confidence {min_confidence:.2f} too low for reliable classification"
        
        self._log_decision(result, parsed)
        return result
    
    def _parse_llm_output(self, raw_output: str) -> dict:
        """Parse and validate LLM JSON output.
        
        Handles common issues:
        - Markdown code blocks around JSON
        - Extra text before/after JSON
        - Missing fields
        """
        # Strip markdown code blocks if present
        cleaned = raw_output.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        
        # Try to find JSON object in the output
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(0)
        
        return json.loads(cleaned)
    
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
