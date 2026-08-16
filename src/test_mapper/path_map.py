"""Static path-to-test-suite mapping for the Kyverno repository.

This module builds a deterministic mapping from source file paths to the test
packages that should be run when those files change. No LLM is used here —
this is purely rule-based for transparency and debuggability.
"""

from dataclasses import dataclass, field


@dataclass
class TestSuite:
    """Represents a test suite that should be run."""
    package: str           # e.g., "pkg/engine/..."
    suite_type: str        # "unit", "integration", "conformance"
    description: str       # human-readable description


# Core mapping rules: source path prefix -> test suites
# Order matters: more specific paths should come before general ones.
PATH_TO_TEST_RULES: list[tuple[str, list[TestSuite]]] = [
    # Engine core
    ("pkg/engine/", [
        TestSuite("pkg/engine/...", "unit", "Engine core unit tests"),
        TestSuite("test/conformance/chainsaw/validate/", "conformance", "Validation conformance tests"),
        TestSuite("test/conformance/chainsaw/mutate/", "conformance", "Mutation conformance tests"),
    ]),
    
    # Engine context (JMESPath, API lookups)
    ("pkg/engine/context/", [
        TestSuite("pkg/engine/context/...", "unit", "Engine context unit tests"),
        TestSuite("pkg/engine/...", "unit", "Full engine unit tests (context affects all engine)"),
    ]),
    
    # CEL engine
    ("pkg/engine/cel/", [
        TestSuite("pkg/engine/cel/...", "unit", "CEL engine unit tests"),
        TestSuite("test/conformance/chainsaw/validate/", "conformance", "CEL validation conformance"),
    ]),
    
    # Webhooks
    ("pkg/webhooks/", [
        TestSuite("pkg/webhooks/...", "unit", "Webhook handler unit tests"),
        TestSuite("test/conformance/chainsaw/", "conformance", "Full conformance suite (webhooks affect all)"),
    ]),
    
    # Controllers
    ("pkg/controllers/", [
        TestSuite("pkg/controllers/...", "unit", "Controller unit tests"),
    ]),
    
    # Background controller
    ("pkg/background/", [
        TestSuite("pkg/background/...", "unit", "Background controller unit tests"),
        TestSuite("test/conformance/chainsaw/generate/", "conformance", "Generation conformance tests"),
    ]),
    
    # Autogen
    ("pkg/autogen/", [
        TestSuite("pkg/autogen/...", "unit", "Autogen unit tests"),
        TestSuite("test/conformance/chainsaw/", "conformance", "Full conformance (autogen affects all rule types)"),
    ]),
    
    # Image verification
    ("pkg/cosign/", [
        TestSuite("pkg/cosign/...", "unit", "Cosign unit tests"),
        TestSuite("test/conformance/chainsaw/verify-images/", "conformance", "Image verification conformance"),
    ]),
    ("pkg/notary/", [
        TestSuite("pkg/notary/...", "unit", "Notary unit tests"),
        TestSuite("test/conformance/chainsaw/verify-images/", "conformance", "Image verification conformance"),
    ]),
    ("pkg/imageverify/", [
        TestSuite("pkg/imageverify/...", "unit", "Image verify unit tests"),
        TestSuite("test/conformance/chainsaw/verify-images/", "conformance", "Image verification conformance"),
    ]),
    
    # Policy reports
    ("pkg/policyreport/", [
        TestSuite("pkg/policyreport/...", "unit", "Policy report unit tests"),
    ]),
    
    # CLI
    ("cmd/cli/", [
        TestSuite("cmd/cli/...", "unit", "CLI unit tests"),
        TestSuite("test/cli/", "integration", "CLI integration tests"),
    ]),
    
    # API definitions
    ("api/", [
        TestSuite("api/...", "unit", "API type unit tests"),
        TestSuite("pkg/...", "unit", "Full unit test suite (API changes affect everything)"),
    ]),
    
    # Client (generated code)
    ("pkg/client/", [
        TestSuite("pkg/client/...", "unit", "Client unit tests"),
    ]),
    
    # Utils (affects many packages)
    ("pkg/utils/", [
        TestSuite("pkg/utils/...", "unit", "Utils unit tests"),
        TestSuite("pkg/engine/...", "unit", "Engine tests (utils dependency)"),
        TestSuite("pkg/webhooks/...", "unit", "Webhook tests (utils dependency)"),
    ]),
    
    # Config/deployment manifests
    ("config/", [
        TestSuite("test/conformance/chainsaw/", "conformance", "Full conformance (config changes)"),
    ]),
    
    # Helm charts
    ("charts/", [
        TestSuite("test/conformance/chainsaw/", "conformance", "Full conformance (chart changes)"),
    ]),
    
    # Test files themselves
    ("test/conformance/chainsaw/validate/", [
        TestSuite("test/conformance/chainsaw/validate/", "conformance", "Validation conformance tests"),
    ]),
    ("test/conformance/chainsaw/mutate/", [
        TestSuite("test/conformance/chainsaw/mutate/", "conformance", "Mutation conformance tests"),
    ]),
    ("test/conformance/chainsaw/generate/", [
        TestSuite("test/conformance/chainsaw/generate/", "conformance", "Generation conformance tests"),
    ]),
    ("test/conformance/chainsaw/verify-images/", [
        TestSuite("test/conformance/chainsaw/verify-images/", "conformance", "Image verification conformance"),
    ]),
    ("test/conformance/chainsaw/cleanup/", [
        TestSuite("test/conformance/chainsaw/cleanup/", "conformance", "Cleanup conformance tests"),
    ]),
    ("test/cli/", [
        TestSuite("test/cli/", "integration", "CLI integration tests"),
    ]),
    
    # Docs (no tests needed, but flag it)
    ("docs/", []),
    
    # GitHub workflows
    (".github/", []),
    
    # Makefile / hack scripts
    ("hack/", [
        TestSuite("pkg/...", "unit", "Full unit tests (build script changes)"),
    ]),
]

# Files that should NEVER be auto-touched (security-sensitive)
NEVER_AUTO_TOUCH = [
    "api/kyverno/v1/",
    "pkg/cosign/",
    "pkg/notary/",
    ".github/workflows/",
    "charts/",
]


def get_test_suites_for_path(path: str) -> tuple[list[TestSuite], str]:
    """Get test suites for a single file path.
    
    Returns:
        (list of TestSuites, confidence level)
        confidence: "exact_match", "prefix_match", or "unmapped"
    """
    # Try exact prefix matches first (more specific)
    for prefix, suites in PATH_TO_TEST_RULES:
        if path.startswith(prefix):
            if not suites:
                return [], "no_tests_needed"
            return suites, "exact_match"
    
    # Try broader directory-level matching
    parts = path.split("/")
    if len(parts) >= 2:
        dir_prefix = parts[0] + "/"
        for prefix, suites in PATH_TO_TEST_RULES:
            if prefix.startswith(dir_prefix):
                return suites, "prefix_match"
    
    return [], "unmapped"


def is_security_sensitive(path: str) -> bool:
    """Check if a path is in the never-auto-touch list."""
    return any(path.startswith(p) for p in NEVER_AUTO_TOUCH)
