"""Append-only, tamper-evident audit logger with hash chaining."""

import hashlib
import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any


class AuditLogger:
    """Append-only JSONL logger with hash chain for tamper detection.
    
    Every record includes:
    - timestamp
    - action type
    - input summary
    - decision/output
    - confidence (if applicable)
    - model info (if LLM was used)
    - cost info (if LLM was used)
    - hash of previous record (chain integrity)
    - hash of current record
    """
    
    def __init__(self, log_dir: str = "data/audit", log_file: str = "decisions.jsonl"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / log_file
        self._prev_hash = self._load_last_hash()
    
    def _load_last_hash(self) -> str:
        """Load the hash of the last entry to continue the chain."""
        if not self.log_path.exists():
            return "genesis"
        
        last_line = ""
        with open(self.log_path) as f:
            for line in f:
                if line.strip():
                    last_line = line.strip()
        
        if last_line:
            try:
                entry = json.loads(last_line)
                return entry.get("hash", "genesis")
            except json.JSONDecodeError:
                return "genesis"
        return "genesis"
    
    def log(self, action: str, input_summary: str, decision: dict[str, Any],
            confidence: float | None = None, model: str | None = None,
            cost_usd: float | None = None, latency_ms: float | None = None,
            input_tokens: int | None = None, output_tokens: int | None = None,
            extra: dict | None = None):
        """Log a decision record with hash chain integrity."""
        record = {
            "timestamp": time.time(),
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": action,
            "input_summary": input_summary,
            "decision": decision,
            "prev_hash": self._prev_hash,
        }
        
        if confidence is not None:
            record["confidence"] = confidence
        if model is not None:
            record["model"] = model
        if cost_usd is not None:
            record["cost_usd"] = cost_usd
        if latency_ms is not None:
            record["latency_ms"] = latency_ms
        if input_tokens is not None:
            record["input_tokens"] = input_tokens
        if output_tokens is not None:
            record["output_tokens"] = output_tokens
        if extra:
            record["extra"] = extra
        
        # Compute hash BEFORE adding hash field
        entry_str = json.dumps(record, sort_keys=True)
        record["hash"] = hashlib.sha256(entry_str.encode()).hexdigest()
        self._prev_hash = record["hash"]
        
        with open(self.log_path, "a") as f:
            f.write(json.dumps(record) + "\n")
        
        return record
    
    def verify_integrity(self) -> tuple[bool, list[str]]:
        """Verify the hash chain integrity of the entire log.
        
        Returns:
            (is_valid, list_of_errors)
        """
        if not self.log_path.exists():
            return True, []
        
        errors = []
        prev_hash = "genesis"
        
        with open(self.log_path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    errors.append(f"Line {line_num}: Invalid JSON")
                    continue
                
                # Check prev_hash chain
                if record.get("prev_hash") != prev_hash:
                    errors.append(
                        f"Line {line_num}: Chain broken. "
                        f"Expected prev_hash={prev_hash}, "
                        f"got {record.get('prev_hash')}"
                    )
                
                # Verify record hash
                stored_hash = record.pop("hash", None)
                recomputed = hashlib.sha256(
                    json.dumps(record, sort_keys=True).encode()
                ).hexdigest()
                record["hash"] = stored_hash  # restore
                
                if stored_hash != recomputed:
                    errors.append(
                        f"Line {line_num}: Hash mismatch. "
                        f"Record may have been tampered with."
                    )
                
                prev_hash = stored_hash or prev_hash
        
        return len(errors) == 0, errors
    
    def get_entries(self) -> list[dict]:
        """Read all log entries."""
        if not self.log_path.exists():
            return []
        
        entries = []
        with open(self.log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries
