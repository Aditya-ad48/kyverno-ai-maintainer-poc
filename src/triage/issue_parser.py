"""Kyverno issue template-aware parser.

Parses structured fields from issues filed using Kyverno's GitHub issue templates.
Extracts version info, reproduction steps, and other structured data that improves
classification accuracy.
"""

import re
from dataclasses import dataclass, field


@dataclass
class ParsedIssue:
    """Structured representation of a Kyverno issue."""
    title: str
    raw_body: str
    kyverno_version: str = ""
    kubernetes_version: str = ""
    kubernetes_platform: str = ""
    rule_type: str = ""  # validate, mutate, generate, verifyImages, cleanup, cli, other
    description: str = ""
    steps_to_reproduce: str = ""
    expected_behavior: str = ""
    actual_behavior: str = ""
    logs: str = ""
    slack_link: str = ""
    free_text: str = ""
    uses_template: bool = False
    body_length: int = 0
    has_yaml_blocks: bool = False
    has_error_logs: bool = False
    
    @property
    def is_minimal(self) -> bool:
        """Check if the issue has minimal content (might need more info)."""
        return self.body_length < 50


def parse_issue(title: str, body: str) -> ParsedIssue:
    """Parse a Kyverno issue body into structured fields.
    
    Handles both template-based issues (with ### headers) and free-form issues.
    """
    parsed = ParsedIssue(
        title=title,
        raw_body=body,
        body_length=len(body),
        has_yaml_blocks=bool(re.search(r'```ya?ml', body, re.IGNORECASE)),
        has_error_logs=bool(re.search(r'(error|panic|fatal|exception|traceback)', body, re.IGNORECASE)),
    )
    
    if not body:
        return parsed
    
    # Try to extract template sections (### header based)
    sections = _extract_sections(body)
    
    if sections:
        parsed.uses_template = True
        parsed.kyverno_version = sections.get("kyverno version", "").strip()
        parsed.kubernetes_version = sections.get("kubernetes version", "").strip()
        parsed.kubernetes_platform = sections.get("kubernetes platform", "").strip()
        parsed.rule_type = sections.get("kyverno rule type", "").strip()
        parsed.description = sections.get("description", "").strip()
        parsed.steps_to_reproduce = sections.get("steps to reproduce", "").strip()
        parsed.expected_behavior = sections.get("expected behavior", "").strip()
        parsed.actual_behavior = sections.get("actual behavior", "").strip()
        parsed.logs = sections.get("logs", sections.get("screenshots", "")).strip() if sections.get("logs", sections.get("screenshots")) else ""
        parsed.slack_link = sections.get("slack discussion", "").strip()
        
        # Collect anything not in known sections as free text
        known_keys = {
            "kyverno version", "kubernetes version", "kubernetes platform",
            "kyverno rule type", "description", "steps to reproduce",
            "expected behavior", "actual behavior", "logs", "screenshots",
            "slack discussion", "additional context",
            "problem statement", "solution description", "alternatives",
            "research"
        }
        free_parts = []
        for key, value in sections.items():
            if key.lower() not in known_keys and value.strip():
                free_parts.append(value.strip())
        parsed.free_text = "\n".join(free_parts)
    else:
        # Free-form issue, use the entire body
        parsed.free_text = body
        
        # Try to extract version info from free text
        version_match = re.search(r'(?:kyverno|version)[:\s]+v?(\d+\.\d+\.\d+)', body, re.IGNORECASE)
        if version_match:
            parsed.kyverno_version = version_match.group(1)
        
        k8s_match = re.search(r'(?:kubernetes|k8s)[:\s]+v?(\d+\.\d+\.?\d*)', body, re.IGNORECASE)
        if k8s_match:
            parsed.kubernetes_version = k8s_match.group(1)
    
    return parsed


def _extract_sections(body: str) -> dict[str, str]:
    """Extract ### header sections from a template-based issue body."""
    sections = {}
    current_header = None
    current_content = []
    
    for line in body.split("\n"):
        # Check for ### headers
        header_match = re.match(r'^###\s+(.+)', line)
        if header_match:
            # Save previous section
            if current_header is not None:
                sections[current_header] = "\n".join(current_content)
            current_header = header_match.group(1).strip().lower()
            current_content = []
        elif current_header is not None:
            current_content.append(line)
    
    # Save last section
    if current_header is not None:
        sections[current_header] = "\n".join(current_content)
    
    return sections
