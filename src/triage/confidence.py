"""Confidence analysis and calibration utilities.

Provides tools to analyze whether the LLM's self-reported confidence scores
are well-calibrated (i.e., when it says 0.9 confidence, is it actually right ~90% of the time?).
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class CalibrationBin:
    """A single bin in a calibration analysis."""
    bin_start: float
    bin_end: float
    total_count: int
    correct_count: int
    avg_confidence: float
    actual_accuracy: float
    calibration_error: float  # |avg_confidence - actual_accuracy|


def compute_calibration(
    predictions: list[dict[str, Any]],
    num_bins: int = 5,
) -> list[CalibrationBin]:
    """Compute calibration curve from prediction results.
    
    Args:
        predictions: List of dicts with 'confidence' and 'correct' keys.
        num_bins: Number of bins to divide the [0, 1] confidence range into.
    
    Returns:
        List of CalibrationBin objects.
    """
    bins: list[CalibrationBin] = []
    bin_width = 1.0 / num_bins
    
    for i in range(num_bins):
        bin_start = i * bin_width
        bin_end = (i + 1) * bin_width
        
        # Get predictions in this bin
        in_bin = [
            p for p in predictions
            if bin_start <= p["confidence"] < bin_end
            or (i == num_bins - 1 and p["confidence"] == bin_end)  # include 1.0 in last bin
        ]
        
        if not in_bin:
            bins.append(CalibrationBin(
                bin_start=bin_start,
                bin_end=bin_end,
                total_count=0,
                correct_count=0,
                avg_confidence=0.0,
                actual_accuracy=0.0,
                calibration_error=0.0,
            ))
            continue
        
        correct = sum(1 for p in in_bin if p["correct"])
        avg_conf = sum(p["confidence"] for p in in_bin) / len(in_bin)
        accuracy = correct / len(in_bin)
        
        bins.append(CalibrationBin(
            bin_start=bin_start,
            bin_end=bin_end,
            total_count=len(in_bin),
            correct_count=correct,
            avg_confidence=round(avg_conf, 3),
            actual_accuracy=round(accuracy, 3),
            calibration_error=round(abs(avg_conf - accuracy), 3),
        ))
    
    return bins


def expected_calibration_error(bins: list[CalibrationBin]) -> float:
    """Compute the Expected Calibration Error (ECE).
    
    Lower is better. 0.0 = perfectly calibrated.
    """
    total = sum(b.total_count for b in bins)
    if total == 0:
        return 0.0
    
    ece = sum(
        (b.total_count / total) * b.calibration_error
        for b in bins
    )
    return round(ece, 4)


def format_calibration_report(bins: list[CalibrationBin]) -> str:
    """Format calibration results as a readable text report."""
    lines = []
    lines.append("Confidence Calibration Report")
    lines.append("=" * 60)
    lines.append(f"{'Bin':>12} {'Count':>6} {'Accuracy':>10} {'Avg Conf':>10} {'Error':>8}")
    lines.append("-" * 60)
    
    for b in bins:
        bin_label = f"[{b.bin_start:.1f}-{b.bin_end:.1f})"
        if b.total_count > 0:
            lines.append(
                f"{bin_label:>12} {b.total_count:>6} {b.actual_accuracy:>10.1%} "
                f"{b.avg_confidence:>10.1%} {b.calibration_error:>8.3f}"
            )
        else:
            lines.append(f"{bin_label:>12} {b.total_count:>6} {'N/A':>10} {'N/A':>10} {'N/A':>8}")
    
    lines.append("-" * 60)
    ece = expected_calibration_error(bins)
    lines.append(f"Expected Calibration Error (ECE): {ece:.4f}")
    lines.append(f"(Lower is better. 0.0 = perfectly calibrated)")
    
    return "\n".join(lines)
