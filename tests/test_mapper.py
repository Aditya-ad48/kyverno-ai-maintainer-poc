"""Tests for the diff-to-test-scope mapper."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.test_mapper.mapper import map_diff_to_tests
from src.test_mapper.path_map import get_test_suites_for_path, is_security_sensitive


class TestPathMap:
    """Test the static path-to-test mapping."""
    
    def test_engine_path_maps_to_engine_tests(self):
        suites, confidence = get_test_suites_for_path("pkg/engine/validation.go")
        assert len(suites) > 0
        assert confidence == "exact_match"
        packages = [s.package for s in suites]
        assert "pkg/engine/..." in packages
    
    def test_webhook_path_maps_to_webhook_tests(self):
        suites, confidence = get_test_suites_for_path("pkg/webhooks/server.go")
        assert len(suites) > 0
        packages = [s.package for s in suites]
        assert "pkg/webhooks/..." in packages
    
    def test_docs_path_maps_to_no_tests(self):
        suites, confidence = get_test_suites_for_path("docs/README.md")
        assert len(suites) == 0
        assert confidence == "no_tests_needed"
    
    def test_unknown_path_is_unmapped(self):
        suites, confidence = get_test_suites_for_path("some/random/file.txt")
        assert confidence == "unmapped"
    
    def test_security_sensitive_detection(self):
        assert is_security_sensitive("api/kyverno/v1/types.go")
        assert is_security_sensitive("pkg/cosign/verify.go")
        assert is_security_sensitive("pkg/notary/verify.go")
        assert not is_security_sensitive("pkg/engine/validate.go")
    
    def test_cli_path_maps_to_cli_tests(self):
        suites, confidence = get_test_suites_for_path("cmd/cli/main.go")
        assert len(suites) > 0
        packages = [s.package for s in suites]
        assert "cmd/cli/..." in packages
    
    def test_conformance_test_maps_to_itself(self):
        suites, confidence = get_test_suites_for_path("test/conformance/chainsaw/validate/test.yaml")
        assert len(suites) > 0
        packages = [s.package for s in suites]
        assert "test/conformance/chainsaw/validate/" in packages


class TestMapper:
    """Test the diff-to-test mapper."""
    
    def test_single_engine_file(self):
        result = map_diff_to_tests(["pkg/engine/validation.go"])
        assert result.scope_strategy == "scoped"
        assert len(result.matched_unit_tests) > 0
        assert "pkg/engine/..." in result.matched_unit_tests
    
    def test_multiple_files_same_package(self):
        result = map_diff_to_tests([
            "pkg/engine/validation.go",
            "pkg/engine/mutation.go",
        ])
        assert result.scope_strategy == "scoped"
        # Should deduplicate test suites
        assert result.matched_unit_tests.count("pkg/engine/...") == 1
    
    def test_cross_package_changes(self):
        result = map_diff_to_tests([
            "pkg/engine/validation.go",
            "pkg/webhooks/server.go",
        ])
        assert "pkg/engine/..." in result.matched_unit_tests
        assert "pkg/webhooks/..." in result.matched_unit_tests
    
    def test_too_many_files_falls_back_to_full_suite(self):
        # Generate 60 fake paths
        paths = [f"pkg/engine/file{i}.go" for i in range(60)]
        result = map_diff_to_tests(paths, max_files=50)
        assert result.scope_strategy == "full_suite"
        assert result.confidence == "too_many_files"
    
    def test_docs_only_change(self):
        result = map_diff_to_tests(["docs/guide.md", "docs/install.md"])
        assert result.scope_strategy == "scoped"
        assert len(result.matched_unit_tests) == 0
        assert len(result.no_tests_needed) == 2
    
    def test_security_sensitive_flags_manual_review(self):
        result = map_diff_to_tests(["api/kyverno/v1/policy_types.go"])
        assert result.scope_strategy == "manual_review"
        assert len(result.security_sensitive_paths) > 0
    
    def test_unmapped_paths_tracked(self):
        result = map_diff_to_tests(["random/unknown/file.go"])
        assert len(result.unmapped_paths) > 0
        assert "random/unknown/file.go" in result.unmapped_paths
    
    def test_empty_diff(self):
        result = map_diff_to_tests([])
        assert result.scope_strategy == "scoped"
        assert len(result.matched_unit_tests) == 0
