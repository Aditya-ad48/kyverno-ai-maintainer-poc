"""Diff-to-test-scope mapper.

Given a list of changed file paths (from a PR diff), determines which test
packages should run. This is entirely deterministic — no LLM involved.
"""

from dataclasses import dataclass, field
from .path_map import get_test_suites_for_path, is_security_sensitive, TestSuite


@dataclass
class MapperResult:
    """Result of mapping a diff to test suites."""
    changed_paths: list[str]
    matched_unit_tests: list[str] = field(default_factory=list)
    matched_conformance: list[str] = field(default_factory=list)
    matched_integration: list[str] = field(default_factory=list)
    unmapped_paths: list[str] = field(default_factory=list)
    no_tests_needed: list[str] = field(default_factory=list)
    security_sensitive_paths: list[str] = field(default_factory=list)
    confidence: str = "exact_match"
    scope_strategy: str = "scoped"  # "scoped", "full_suite", or "manual_review"
    total_test_packages: int = 0
    
    def to_dict(self) -> dict:
        return {
            "changed_paths": self.changed_paths,
            "matched_unit_tests": self.matched_unit_tests,
            "matched_conformance": self.matched_conformance,
            "matched_integration": self.matched_integration,
            "unmapped_paths": self.unmapped_paths,
            "no_tests_needed": self.no_tests_needed,
            "security_sensitive_paths": self.security_sensitive_paths,
            "confidence": self.confidence,
            "scope_strategy": self.scope_strategy,
            "total_test_packages": self.total_test_packages,
        }


def map_diff_to_tests(
    changed_paths: list[str],
    max_files: int = 50,
) -> MapperResult:
    """Map a list of changed file paths to test suites.
    
    Args:
        changed_paths: List of file paths changed in a PR.
        max_files: If more files than this are changed, fall back to full suite.
    
    Returns:
        MapperResult with matched test packages and metadata.
    """
    result = MapperResult(changed_paths=changed_paths)
    
    # Check if diff is too large for meaningful scoping
    if len(changed_paths) > max_files:
        result.scope_strategy = "full_suite"
        result.confidence = "too_many_files"
        result.matched_unit_tests = ["pkg/..."]
        result.matched_conformance = ["test/conformance/chainsaw/"]
        result.matched_integration = ["test/cli/"]
        return result
    
    unit_tests: set[str] = set()
    conformance_tests: set[str] = set()
    integration_tests: set[str] = set()
    overall_confidence = "exact_match"
    
    for path in changed_paths:
        # Check security sensitivity
        if is_security_sensitive(path):
            result.security_sensitive_paths.append(path)
        
        # Get test suites
        suites, confidence = get_test_suites_for_path(path)
        
        if confidence == "unmapped":
            result.unmapped_paths.append(path)
            overall_confidence = "has_unmapped"
        elif confidence == "no_tests_needed":
            result.no_tests_needed.append(path)
        elif confidence == "prefix_match" and overall_confidence == "exact_match":
            overall_confidence = "prefix_match"
        
        for suite in suites:
            if suite.suite_type == "unit":
                unit_tests.add(suite.package)
            elif suite.suite_type == "conformance":
                conformance_tests.add(suite.package)
            elif suite.suite_type == "integration":
                integration_tests.add(suite.package)
    
    result.matched_unit_tests = sorted(unit_tests)
    result.matched_conformance = sorted(conformance_tests)
    result.matched_integration = sorted(integration_tests)
    result.confidence = overall_confidence
    result.total_test_packages = len(unit_tests) + len(conformance_tests) + len(integration_tests)
    
    # If we have security-sensitive paths, recommend manual review
    if result.security_sensitive_paths:
        result.scope_strategy = "manual_review"
    # If too many unmapped, suggest full suite
    elif len(result.unmapped_paths) > len(changed_paths) * 0.5:
        result.scope_strategy = "full_suite"
    
    return result
