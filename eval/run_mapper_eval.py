"""Run the test scope mapper evaluation against real Kyverno PRs.

Fetches recent merged PRs, runs the mapper on their diffs, and reports
scope reduction metrics.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.github_client import KyvernoGitHubClient
from src.test_mapper.mapper import map_diff_to_tests
from src.audit_log import AuditLogger


# Total test packages in Kyverno (approximate, for scope reduction calc)
TOTAL_TEST_PACKAGES = 15  # approximate count of major test areas


def run_eval(pr_count: int = 20):
    """Run the mapper evaluation."""
    print("=" * 60)
    print("Kyverno AI Maintainer — Test Scope Mapper Evaluation")
    print("=" * 60)
    
    client = KyvernoGitHubClient()
    audit = AuditLogger(log_dir="data/audit", log_file="eval_mapper.jsonl")
    
    # Fetch merged PRs
    print(f"\nFetching {pr_count} recent merged PRs...")
    prs = client.get_merged_prs(count=pr_count)
    print(f"Got {len(prs)} merged PRs")
    
    results = []
    
    for i, pr in enumerate(prs):
        print(f"\n  [{i+1}/{len(prs)}] PR #{pr.number}: {pr.title[:60]}...")
        
        # Fetch changed files
        try:
            files = client.get_pr_files(pr.number)
        except Exception as e:
            print(f"    Error fetching files: {e}")
            continue
        
        changed_paths = [f.filename for f in files]
        print(f"    Changed files: {len(changed_paths)}")
        
        # Run mapper
        mapper_result = map_diff_to_tests(changed_paths)
        
        # Calculate scope reduction
        if mapper_result.scope_strategy == "full_suite":
            scope_reduction = 0.0
        elif mapper_result.total_test_packages == 0:
            scope_reduction = 1.0  # No tests needed
        else:
            scope_reduction = max(0, 1.0 - (mapper_result.total_test_packages / TOTAL_TEST_PACKAGES))
        
        result = {
            "pr_number": pr.number,
            "title": pr.title,
            "changed_files": len(changed_paths),
            "scope_strategy": mapper_result.scope_strategy,
            "confidence": mapper_result.confidence,
            "matched_unit_tests": mapper_result.matched_unit_tests,
            "matched_conformance": mapper_result.matched_conformance,
            "matched_integration": mapper_result.matched_integration,
            "unmapped_paths": mapper_result.unmapped_paths,
            "no_tests_needed": mapper_result.no_tests_needed,
            "security_sensitive": mapper_result.security_sensitive_paths,
            "total_test_packages": mapper_result.total_test_packages,
            "scope_reduction": round(scope_reduction, 2),
        }
        results.append(result)
        
        # Log to audit
        audit.log(
            action="test_scope_map",
            input_summary=f"PR #{pr.number}: {pr.title}",
            decision=mapper_result.to_dict(),
            confidence=1.0 if mapper_result.confidence == "exact_match" else 0.5,
        )
        
        # Print summary
        print(f"    Strategy: {mapper_result.scope_strategy}")
        print(f"    Unit tests: {len(mapper_result.matched_unit_tests)}")
        print(f"    Conformance: {len(mapper_result.matched_conformance)}")
        print(f"    Unmapped: {len(mapper_result.unmapped_paths)}")
        print(f"    Scope reduction: {scope_reduction:.0%}")
        
        if mapper_result.security_sensitive_paths:
            print(f"    ⚠ Security-sensitive: {mapper_result.security_sensitive_paths}")
        
        time.sleep(0.3)  # Rate limiting
    
    # Summary
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    if not results:
        print("No results to report.")
        return
    
    scoped = [r for r in results if r["scope_strategy"] == "scoped"]
    full_suite = [r for r in results if r["scope_strategy"] == "full_suite"]
    manual_review = [r for r in results if r["scope_strategy"] == "manual_review"]
    
    avg_reduction = sum(r["scope_reduction"] for r in results) / len(results)
    avg_changed_files = sum(r["changed_files"] for r in results) / len(results)
    
    unmapped_total = sum(len(r["unmapped_paths"]) for r in results)
    total_files = sum(r["changed_files"] for r in results)
    unmapped_rate = unmapped_total / total_files if total_files else 0
    
    print(f"\nTotal PRs analyzed: {len(results)}")
    print(f"Avg changed files per PR: {avg_changed_files:.1f}")
    print(f"\nScope Strategy Distribution:")
    print(f"  Scoped (subset): {len(scoped)} ({len(scoped)/len(results):.0%})")
    print(f"  Full suite: {len(full_suite)} ({len(full_suite)/len(results):.0%})")
    print(f"  Manual review: {len(manual_review)} ({len(manual_review)/len(results):.0%})")
    print(f"\nAvg scope reduction: {avg_reduction:.0%}")
    print(f"Unmapped file rate: {unmapped_rate:.0%} ({unmapped_total}/{total_files})")
    
    security_sensitive_prs = sum(1 for r in results if r["security_sensitive"])
    print(f"PRs with security-sensitive changes: {security_sensitive_prs}")
    
    # Save results
    results_dir = Path("eval/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_prs": len(results),
        "avg_changed_files": round(avg_changed_files, 1),
        "scoped_count": len(scoped),
        "full_suite_count": len(full_suite),
        "manual_review_count": len(manual_review),
        "avg_scope_reduction": round(avg_reduction, 4),
        "unmapped_rate": round(unmapped_rate, 4),
        "security_sensitive_prs": security_sensitive_prs,
        "detailed_results": results,
    }
    
    results_file = results_dir / "mapper_eval.json"
    with open(results_file, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\nResults saved to {results_file}")
    return report


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    run_eval(pr_count=count)
