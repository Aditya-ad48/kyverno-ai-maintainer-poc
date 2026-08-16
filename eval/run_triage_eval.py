"""Run the triage classifier evaluation against real Kyverno issues.

Compares classifier predictions against ground truth labels from
actual closed issues, and reports accuracy metrics.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm_client import LLMClient
from src.audit_log import AuditLogger
from src.triage.classifier import TriageClassifier
from src.triage.confidence import compute_calibration, expected_calibration_error, format_calibration_report
from eval.fetch_ground_truth import fetch_labeled_issues, get_adversarial_cases


def run_eval(issue_count: int = 50, include_adversarial: bool = True):
    """Run the full triage evaluation."""
    print("=" * 60)
    print("Kyverno AI Maintainer — Triage Classifier Evaluation")
    print("=" * 60)
    
    # Setup
    llm = LLMClient()
    audit = AuditLogger(log_dir="data/audit", log_file="eval_triage.jsonl")
    classifier = TriageClassifier(llm_client=llm, audit_logger=audit)
    
    # Fetch ground truth
    print(f"\nFetching {issue_count} labeled issues...")
    issues = fetch_labeled_issues(count=issue_count)
    print(f"Got {len(issues)} issues with ground truth labels")
    
    # Add adversarial cases
    adversarial_cases = []
    if include_adversarial:
        adversarial_cases = get_adversarial_cases()
        print(f"Adding {len(adversarial_cases)} adversarial test cases")
    
    # Run classifier
    results = []
    total_cost = 0.0
    total_latency = 0.0
    
    print(f"\nClassifying {len(issues)} real issues...")
    for i, issue in enumerate(issues):
        print(f"  [{i+1}/{len(issues)}] Issue #{issue['number']}: {issue['title'][:60]}...", end="", flush=True)
        
        result = classifier.classify(
            issue_number=issue["number"],
            title=issue["title"],
            body=issue["body"],
        )
        
        # Compare with ground truth
        kind_correct = (
            result.kind_label == issue.get("ground_truth_kind")
            if issue.get("ground_truth_kind") else None
        )
        area_correct = (
            result.area_label == issue.get("ground_truth_area")
            if issue.get("ground_truth_area") else None
        )
        
        results.append({
            "issue_number": issue["number"],
            "title": issue["title"],
            "predicted_kind": result.kind_label,
            "actual_kind": issue.get("ground_truth_kind"),
            "kind_correct": kind_correct,
            "kind_confidence": result.kind_confidence,
            "predicted_area": result.area_label,
            "actual_area": issue.get("ground_truth_area"),
            "area_correct": area_correct,
            "area_confidence": result.area_confidence,
            "action": result.action,
            "reasoning": result.reasoning,
            "cost_usd": result.cost_usd,
            "latency_ms": result.latency_ms,
            "parse_error": result.parse_error,
            "adversarial": False,
        })
        
        total_cost += result.cost_usd
        total_latency += result.latency_ms
        
        status = "✓" if kind_correct else "✗" if kind_correct is False else "?"
        print(f" {status} ({result.kind_label}, conf={result.kind_confidence:.2f})")
        
        # Delay to respect rate limits
        time.sleep(1.5)
    
    # Run adversarial cases
    adversarial_results = []
    if adversarial_cases:
        print(f"\nRunning {len(adversarial_cases)} adversarial tests...")
        for i, case in enumerate(adversarial_cases):
            print(f"  [Adversarial {i+1}/{len(adversarial_cases)}] {case['attack_type']}...", end="", flush=True)
            
            result = classifier.classify(
                issue_number=case["number"],
                title=case["title"],
                body=case["body"],
            )
            
            kind_correct = result.kind_label == case.get("ground_truth_kind")
            area_correct = result.area_label == case.get("ground_truth_area")
            
            adversarial_results.append({
                "attack_type": case["attack_type"],
                "predicted_kind": result.kind_label,
                "actual_kind": case.get("ground_truth_kind"),
                "kind_correct": kind_correct,
                "kind_confidence": result.kind_confidence,
                "predicted_area": result.area_label,
                "actual_area": case.get("ground_truth_area"),
                "area_correct": area_correct,
                "area_confidence": result.area_confidence,
                "resisted": kind_correct,  # Did it classify correctly despite injection?
                "action": result.action,
                "reasoning": result.reasoning,
            })
            
            status = "RESISTED" if kind_correct else "FAILED"
            print(f" {status} (predicted: {result.kind_label}, actual: {case.get('ground_truth_kind')})")
            
            time.sleep(0.5)
    
    # Compute metrics
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    # Kind accuracy
    kind_evaluable = [r for r in results if r["actual_kind"] is not None]
    kind_correct_count = sum(1 for r in kind_evaluable if r["kind_correct"])
    kind_accuracy = kind_correct_count / len(kind_evaluable) if kind_evaluable else 0
    
    print(f"\nKind Classification:")
    print(f"  Accuracy: {kind_accuracy:.1%} ({kind_correct_count}/{len(kind_evaluable)})")
    
    # Per-category breakdown
    categories = set(r["actual_kind"] for r in kind_evaluable if r["actual_kind"])
    for cat in sorted(categories):
        cat_results = [r for r in kind_evaluable if r["actual_kind"] == cat]
        cat_correct = sum(1 for r in cat_results if r["kind_correct"])
        print(f"  {cat}: {cat_correct}/{len(cat_results)} ({cat_correct/len(cat_results):.0%})")
    
    # Area accuracy
    area_evaluable = [r for r in results if r["actual_area"] is not None]
    area_correct_count = sum(1 for r in area_evaluable if r["area_correct"])
    area_accuracy = area_correct_count / len(area_evaluable) if area_evaluable else 0
    
    print(f"\nArea Classification:")
    print(f"  Accuracy: {area_accuracy:.1%} ({area_correct_count}/{len(area_evaluable)})")
    
    # All evaluated items (real + adversarial)
    all_items = results + adversarial_results
    
    # Escalation rates
    real_escalated = sum(1 for r in results if r["action"] == "escalate")
    adv_escalated = sum(1 for r in adversarial_results if r["action"] == "escalate")
    total_escalated = real_escalated + adv_escalated
    
    print(f"\nEscalation Rates:")
    print(f"  Real Issues Escalated: {real_escalated}/{len(results)} ({real_escalated/len(results):.1%})" if results else "  N/A")
    print(f"  Adversarial Cases Escalated: {adv_escalated}/{len(adversarial_results)} ({adv_escalated/len(adversarial_results):.1%})" if adversarial_results else "  N/A")
    print(f"  Overall Escalation Rate: {total_escalated}/{len(all_items)} ({total_escalated/len(all_items):.1%})")
    
    # Parse errors
    parse_errors = sum(1 for r in results if r.get("parse_error"))
    print(f"\nParse Errors: {parse_errors}/{len(results)}")
    
    # Cost
    print(f"\nCost & Performance:")
    print(f"  Total cost: ${total_cost:.4f}")
    print(f"  Avg cost per issue: ${total_cost/len(results):.4f}" if results else "  N/A")
    print(f"  Avg latency: {total_latency/len(results):.0f}ms" if results else "  N/A")
    print(f"  Model: {llm.model}")
    
    # Adversarial results
    if adversarial_results:
        resisted = sum(1 for r in adversarial_results if r["resisted"])
        print(f"\nAdversarial Resistance:")
        print(f"  Resisted: {resisted}/{len(adversarial_results)}")
        for r in adversarial_results:
            status = "✓ RESISTED" if r["resisted"] else "✗ FAILED"
            print(f"  {r['attack_type']}: {status} (action: {r['action']}, conf: {r.get('kind_confidence', 0.0):.2f})")
    
    # Calibration
    all_evaluable = [
        {"confidence": r["kind_confidence"], "correct": r["kind_correct"]}
        for r in all_items
        if r.get("kind_correct") is not None and "kind_confidence" in r
    ]
    if all_evaluable:
        bins = compute_calibration(all_evaluable)
        print(f"\n{format_calibration_report(bins)}")
    
    # Save results
    results_dir = Path("eval/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": llm.model,
        "provider": llm.provider,
        "total_real_issues": len(results),
        "total_adversarial_cases": len(adversarial_results),
        "kind_accuracy": round(kind_accuracy, 4),
        "area_accuracy": round(area_accuracy, 4),
        "real_escalation_rate": round(real_escalated / len(results), 4) if results else 0,
        "overall_escalation_rate": round(total_escalated / len(all_items), 4) if all_items else 0,
        "parse_error_rate": round(parse_errors / len(results), 4) if results else 0,
        "total_cost_usd": round(total_cost, 6),
        "avg_latency_ms": round(total_latency / len(results), 1) if results else 0,
        "adversarial_resistance": f"{resisted}/{len(adversarial_results)}" if adversarial_results else "N/A",
        "calibration_ece": expected_calibration_error(bins) if all_evaluable else None,
        "detailed_results": results,
        "adversarial_results": adversarial_results,
    }
    
    results_file = results_dir / "triage_eval.json"
    with open(results_file, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\nResults saved to {results_file}")
    return report


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    run_eval(issue_count=count)
