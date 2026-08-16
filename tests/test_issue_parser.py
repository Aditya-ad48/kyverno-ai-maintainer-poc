"""Tests for the Kyverno issue template parser."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.triage.issue_parser import parse_issue


class TestIssueParser:
    """Test template-aware issue parsing."""
    
    def test_template_based_issue(self):
        body = """### Kyverno Version

1.13.0

### Kubernetes Version

1.29.3

### Kubernetes Platform

EKS

### Kyverno Rule Type

Validate

### Description

Policy validation fails when using CEL expressions.

### Steps to Reproduce

1. Create a ClusterPolicy with CEL expression
2. Apply a resource that should match
3. Observe error

### Expected Behavior

Resource should be validated.

### Actual Behavior

Internal server error."""
        
        parsed = parse_issue("CEL validation fails", body)
        
        assert parsed.uses_template
        assert parsed.kyverno_version == "1.13.0"
        assert parsed.kubernetes_version == "1.29.3"
        assert parsed.kubernetes_platform == "EKS"
        assert parsed.rule_type == "Validate"
        assert "CEL" in parsed.description
        assert "ClusterPolicy" in parsed.steps_to_reproduce
        assert "validated" in parsed.expected_behavior
        assert "error" in parsed.actual_behavior.lower()
    
    def test_free_form_issue(self):
        body = """I'm running kyverno version 1.12.0 on kubernetes 1.28 and the CLI crashes when I try to test my policy."""
        
        parsed = parse_issue("CLI crash", body)
        
        assert not parsed.uses_template
        assert parsed.kyverno_version == "1.12.0"
        assert parsed.kubernetes_version == "1.28"
        assert parsed.free_text == body
    
    def test_minimal_issue(self):
        parsed = parse_issue("Bug", "It's broken")
        assert parsed.is_minimal
        assert parsed.body_length < 50
    
    def test_empty_body(self):
        parsed = parse_issue("Empty", "")
        assert parsed.is_minimal
        assert parsed.body_length == 0
    
    def test_yaml_detection(self):
        body = """### Description

Policy doesn't work.

```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: test
```"""
        parsed = parse_issue("Test", body)
        assert parsed.has_yaml_blocks
    
    def test_error_log_detection(self):
        body = """### Logs

ERROR: panic in webhook handler
traceback follows..."""
        parsed = parse_issue("Test", body)
        assert parsed.has_error_logs
