"""Tests for the audit logger."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.audit_log import AuditLogger


class TestAuditLogger:
    """Test audit logging and hash chain integrity."""
    
    def test_basic_logging(self, tmp_path):
        logger = AuditLogger(log_dir=str(tmp_path), log_file="test.jsonl")
        
        record = logger.log(
            action="test_action",
            input_summary="test input",
            decision={"result": "pass"},
            confidence=0.95,
        )
        
        assert record["action"] == "test_action"
        assert record["confidence"] == 0.95
        assert "hash" in record
        assert record["prev_hash"] == "genesis"
    
    def test_hash_chain(self, tmp_path):
        logger = AuditLogger(log_dir=str(tmp_path), log_file="test.jsonl")
        
        r1 = logger.log(action="first", input_summary="a", decision={"v": 1})
        r2 = logger.log(action="second", input_summary="b", decision={"v": 2})
        r3 = logger.log(action="third", input_summary="c", decision={"v": 3})
        
        assert r2["prev_hash"] == r1["hash"]
        assert r3["prev_hash"] == r2["hash"]
    
    def test_integrity_verification_passes(self, tmp_path):
        logger = AuditLogger(log_dir=str(tmp_path), log_file="test.jsonl")
        
        logger.log(action="a", input_summary="1", decision={"v": 1})
        logger.log(action="b", input_summary="2", decision={"v": 2})
        logger.log(action="c", input_summary="3", decision={"v": 3})
        
        is_valid, errors = logger.verify_integrity()
        assert is_valid
        assert len(errors) == 0
    
    def test_integrity_detects_tampering(self, tmp_path):
        logger = AuditLogger(log_dir=str(tmp_path), log_file="test.jsonl")
        
        logger.log(action="a", input_summary="1", decision={"v": 1})
        logger.log(action="b", input_summary="2", decision={"v": 2})
        
        # Tamper with the log file
        log_path = tmp_path / "test.jsonl"
        lines = log_path.read_text().strip().split("\n")
        entry = json.loads(lines[0])
        entry["action"] = "tampered"
        lines[0] = json.dumps(entry)
        log_path.write_text("\n".join(lines) + "\n")
        
        # Re-create logger to load from file
        logger2 = AuditLogger(log_dir=str(tmp_path), log_file="test.jsonl")
        is_valid, errors = logger2.verify_integrity()
        assert not is_valid
        assert len(errors) > 0
    
    def test_continues_chain_on_reload(self, tmp_path):
        logger1 = AuditLogger(log_dir=str(tmp_path), log_file="test.jsonl")
        r1 = logger1.log(action="a", input_summary="1", decision={"v": 1})
        
        # Create new logger instance (simulates restart)
        logger2 = AuditLogger(log_dir=str(tmp_path), log_file="test.jsonl")
        r2 = logger2.log(action="b", input_summary="2", decision={"v": 2})
        
        assert r2["prev_hash"] == r1["hash"]
        
        is_valid, errors = logger2.verify_integrity()
        assert is_valid
    
    def test_get_entries(self, tmp_path):
        logger = AuditLogger(log_dir=str(tmp_path), log_file="test.jsonl")
        logger.log(action="a", input_summary="1", decision={"v": 1})
        logger.log(action="b", input_summary="2", decision={"v": 2})
        
        entries = logger.get_entries()
        assert len(entries) == 2
        assert entries[0]["action"] == "a"
        assert entries[1]["action"] == "b"
    
    def test_cost_tracking(self, tmp_path):
        logger = AuditLogger(log_dir=str(tmp_path), log_file="test.jsonl")
        
        record = logger.log(
            action="llm_call",
            input_summary="test",
            decision={"result": "pass"},
            model="llama-3.3-70b",
            cost_usd=0.0034,
            latency_ms=1847.5,
            input_tokens=1523,
            output_tokens=287,
        )
        
        assert record["model"] == "llama-3.3-70b"
        assert record["cost_usd"] == 0.0034
        assert record["input_tokens"] == 1523
