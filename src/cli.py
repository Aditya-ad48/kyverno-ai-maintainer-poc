"""CLI interface for the Kyverno AI Maintainer POC.

Provides commands for interactive demo and evaluation.
"""

import json
import sys
from pathlib import Path

import click

from .github_client import KyvernoGitHubClient
from .llm_client import LLMClient
from .audit_log import AuditLogger
from .test_mapper.mapper import map_diff_to_tests
from .triage.classifier import TriageClassifier


@click.group()
def cli():
    """Kyverno AI Maintainer — Prototype CLI"""
    pass


@cli.command()
@click.option("--issue", "-i", required=True, type=int, help="GitHub issue number to classify")
def triage(issue: int):
    """Classify a specific Kyverno issue."""
    click.echo(f"Fetching issue #{issue}...")
    
    client = KyvernoGitHubClient()
    gh_issue = client.get_issue(issue)
    
    click.echo(f"Title: {gh_issue.title}")
    click.echo(f"Labels: {', '.join(gh_issue.labels) or 'none'}")
    click.echo(f"State: {gh_issue.state}")
    click.echo()
    
    llm = LLMClient()
    audit = AuditLogger()
    classifier = TriageClassifier(llm_client=llm, audit_logger=audit)
    
    click.echo("Classifying...")
    result = classifier.classify(
        issue_number=gh_issue.number,
        title=gh_issue.title,
        body=gh_issue.body,
    )
    
    click.echo()
    click.echo("=" * 50)
    click.echo("Classification Result")
    click.echo("=" * 50)
    click.echo(f"Kind:       {result.kind_label} (confidence: {result.kind_confidence:.2f})")
    click.echo(f"Area:       {result.area_label} (confidence: {result.area_confidence:.2f})")
    click.echo(f"Priority:   {result.priority_hint}")
    click.echo(f"Action:     {result.action}")
    if result.escalation_reason:
        click.echo(f"Escalation: {result.escalation_reason}")
    click.echo(f"Reasoning:  {result.reasoning}")
    click.echo(f"\nCost: ${result.cost_usd:.4f} | Latency: {result.latency_ms:.0f}ms | Model: {result.model}")


@cli.command("map-tests")
@click.option("--pr", "-p", required=True, type=int, help="PR number to map tests for")
def map_tests(pr: int):
    """Map a PR's diff to test suites."""
    click.echo(f"Fetching PR #{pr} files...")
    
    client = KyvernoGitHubClient()
    files = client.get_pr_files(pr)
    
    changed_paths = [f.filename for f in files]
    click.echo(f"Changed files: {len(changed_paths)}")
    for p in changed_paths[:20]:
        click.echo(f"  {p}")
    if len(changed_paths) > 20:
        click.echo(f"  ... and {len(changed_paths) - 20} more")
    click.echo()
    
    result = map_diff_to_tests(changed_paths)
    
    click.echo("=" * 50)
    click.echo("Test Scope Mapping Result")
    click.echo("=" * 50)
    click.echo(f"Strategy:   {result.scope_strategy}")
    click.echo(f"Confidence: {result.confidence}")
    
    if result.matched_unit_tests:
        click.echo(f"\nUnit Tests ({len(result.matched_unit_tests)}):")
        for t in result.matched_unit_tests:
            click.echo(f"  go test ./{t}")
    
    if result.matched_conformance:
        click.echo(f"\nConformance Tests ({len(result.matched_conformance)}):")
        for t in result.matched_conformance:
            click.echo(f"  chainsaw test {t}")
    
    if result.matched_integration:
        click.echo(f"\nIntegration Tests ({len(result.matched_integration)}):")
        for t in result.matched_integration:
            click.echo(f"  {t}")
    
    if result.unmapped_paths:
        click.echo(f"\n⚠ Unmapped Paths ({len(result.unmapped_paths)}):")
        for p in result.unmapped_paths:
            click.echo(f"  {p}")
    
    if result.security_sensitive_paths:
        click.echo(f"\n🔒 Security-Sensitive Paths:")
        for p in result.security_sensitive_paths:
            click.echo(f"  {p}")
    
    if result.no_tests_needed:
        click.echo(f"\nNo Tests Needed:")
        for p in result.no_tests_needed:
            click.echo(f"  {p}")


@cli.command()
@click.option("--log", "-l", default="data/audit/decisions.jsonl", help="Audit log file path")
def audit(log: str):
    """Verify audit log integrity."""
    click.echo(f"Verifying audit log: {log}")
    
    log_path = Path(log)
    if not log_path.exists():
        click.echo("Log file not found.")
        return
    
    logger = AuditLogger(
        log_dir=str(log_path.parent),
        log_file=log_path.name,
    )
    
    is_valid, errors = logger.verify_integrity()
    
    entries = logger.get_entries()
    click.echo(f"Total entries: {len(entries)}")
    
    if is_valid:
        click.echo("✓ Audit log integrity verified — no tampering detected.")
    else:
        click.echo(f"✗ INTEGRITY VIOLATION — {len(errors)} error(s) detected:")
        for error in errors:
            click.echo(f"  {error}")


@cli.command()
@click.option("--mode", "-m", type=click.Choice(["triage", "mapper"]), required=True)
@click.option("--count", "-c", default=None, type=int, help="Number of items to evaluate")
def eval(mode: str, count: int | None):
    """Run evaluation harness."""
    if mode == "triage":
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from eval.run_triage_eval import run_eval as run_triage
        run_triage(issue_count=count or 50)
    elif mode == "mapper":
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from eval.run_mapper_eval import run_eval as run_mapper
        run_mapper(pr_count=count or 20)


if __name__ == "__main__":
    cli()
