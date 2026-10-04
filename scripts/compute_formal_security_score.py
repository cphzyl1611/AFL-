#!/usr/bin/env python3
"""
Authoritative composite security score computation.

Authority: docs/review/模糊测试部分终审报告.md M-13
Formula: P_sec = β1 * Cov + β2 * (1 / (1 + Err)) + β3 * R_rec

Where:
- β1, β2, β3 are configurable weights with β1 + β2 + β3 = 1
- Cov: Coverage metric (normalized to [0, 1])
- Err: Error rate metric
- R_rec: Recovery metric (normalized to [0, 1])

This implements the 3-term authoritative formula, distinct from the 5-dimension
review formula in compute_security_score.py.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple


class FormalScoreConfig:
    """Configuration for formal security score weights."""

    def __init__(self, beta1: float, beta2: float, beta3: float):
        """
        Initialize weights with validation.

        Args:
            beta1: Weight for coverage term (must be in [0, 1])
            beta2: Weight for error term (must be in [0, 1])
            beta3: Weight for recovery term (must be in [0, 1])

        Raises:
            ValueError: If weights are invalid or don't sum to ~1.0
        """
        if not (0 <= beta1 <= 1 and 0 <= beta2 <= 1 and 0 <= beta3 <= 1):
            raise ValueError(
                f"All weights must be in [0, 1]: β1={beta1}, β2={beta2}, β3={beta3}"
            )

        weight_sum = beta1 + beta2 + beta3
        if not (0.99 <= weight_sum <= 1.01):
            raise ValueError(
                f"Weights must sum to 1.0 (got {weight_sum:.6f}): "
                f"β1={beta1}, β2={beta2}, β3={beta3}"
            )

        self.beta1 = beta1
        self.beta2 = beta2
        self.beta3 = beta3

    @classmethod
    def from_dict(cls, config: Dict) -> 'FormalScoreConfig':
        """Load from configuration dictionary."""
        return cls(
            beta1=float(config['beta1']),
            beta2=float(config['beta2']),
            beta3=float(config['beta3'])
        )

    def to_dict(self) -> Dict[str, float]:
        """Export as dictionary."""
        return {
            'beta1': self.beta1,
            'beta2': self.beta2,
            'beta3': self.beta3,
            'sum': self.beta1 + self.beta2 + self.beta3
        }


def compute_coverage_ratio(
    security_state_new_total: int,
    security_state_capacity: int
) -> float:
    """
    Compute security-state coverage ratio.

    Authority: Project semantics define coverage as the proportion of
    the security-state space that has been discovered by the fuzzer.

    Security states are derived from HTTP responses as:
    state_id = FNV1a64("METHOD PATH|RESPONSE_CLASS")

    Args:
        security_state_new_total: Cumulative count of first-time security
            state discoveries (nv_sec_state_new_total)
        security_state_capacity: Maximum capacity of the security-state
            hash table (nv_cov_cap, typically 65536)

    Returns:
        Coverage ratio in [0, 1]
    """
    if security_state_capacity == 0:
        return 0.0

    return min(1.0, security_state_new_total / security_state_capacity)


# REMOVED: normalize_recovery() was deprecated and deleted.
# Use compute_coverage_ratio() for coverage and compute_recovery_rate() for recovery.


def compute_recovery_rate(
    recovery_success: int,
    recovery_total: int
) -> float:
    """
    Compute recovery rate from actual post-anomaly recovery events.

    Recovery rate = successful recoveries / total recovery attempts

    Authority: Project semantics define recovery rate as "the proportion
    of anomaly events after which the system successfully returns from
    an error state to a normal/safe state."

    Args:
        recovery_success: Count of successful post-anomaly recoveries (nv_rec_success)
        recovery_total: Count of anomaly events with recovery attempts (nv_rec_total)

    Returns:
        Recovery rate in [0, 1]
    """
    if recovery_total == 0:
        return 0.0

    return min(1.0, recovery_success / recovery_total)


def compute_formal_score(
    config: FormalScoreConfig,
    cov: float,
    err: float,
    r_rec: float
) -> float:
    """
    Compute formal security score using authoritative formula.

    P_sec = β1 * Cov + β2 * (1 / (1 + Err)) + β3 * R_rec

    Args:
        config: Weight configuration
        cov: Coverage metric (normalized to [0, 1])
        err: Error rate metric (raw rate, not normalized)
        r_rec: Recovery metric (normalized to [0, 1])

    Returns:
        Composite security score P_sec
    """
    # Apply authoritative formula
    err_term = 1.0 / (1.0 + err)
    p_sec = config.beta1 * cov + config.beta2 * err_term + config.beta3 * r_rec

    return p_sec


def extract_metrics_from_stats(stats_path: Path) -> Optional[Dict]:
    """
    Extract required metrics from fuzzer_stats file.

    Args:
        stats_path: Path to fuzzer_stats file

    Returns:
        Dictionary with extracted metrics, or None if file invalid
    """
    if not stats_path.exists():
        return None

    metrics = {}
    required = {
        'nv_err_rate',
        'nv_rec_total', 'nv_rec_success',
        'security_state_new_total', 'security_state_capacity'
    }

    with open(stats_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or ':' not in line:
                continue

            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()

            if key in required:
                try:
                    if key == 'nv_err_rate':
                        metrics[key] = float(value)
                    else:
                        metrics[key] = int(value)
                except ValueError:
                    continue

    # Check all required metrics present
    if not all(k in metrics for k in required):
        return None

    return metrics


def compute_from_stats(
    stats_path: Path,
    config: FormalScoreConfig
) -> Tuple[Optional[float], Dict]:
    """
    Compute formal score from fuzzer_stats file.

    Args:
        stats_path: Path to fuzzer_stats
        config: Weight configuration

    Returns:
        (score, provenance_dict) where score is None if unavailable
    """
    metrics = extract_metrics_from_stats(stats_path)

    if metrics is None:
        return None, {
            'status': 'unavailable',
            'reason': 'required_metrics_missing',
            'stats_path': str(stats_path)
        }

    # Normalize metrics
    cov = compute_coverage_ratio(
        security_state_new_total=metrics['security_state_new_total'],
        security_state_capacity=metrics['security_state_capacity']
    )

    err = metrics['nv_err_rate']

    r_rec = compute_recovery_rate(
        recovery_success=metrics['nv_rec_success'],
        recovery_total=metrics['nv_rec_total']
    )

    # Compute score
    p_sec = compute_formal_score(config, cov, err, r_rec)

    provenance = {
        'status': 'computed',
        'formula': 'P_sec = β1 * Cov + β2 * (1/(1+Err)) + β3 * R_rec',
        'weights': config.to_dict(),
        'raw_metrics': metrics,
        'normalized_metrics': {
            'Cov': cov,
            'Err': err,
            'R_rec': r_rec,
            'err_term': 1.0 / (1.0 + err)
        },
        'cov_source': {
            'numerator': 'security_state_new_total',
            'denominator': 'security_state_capacity',
            'numerator_value': metrics['security_state_new_total'],
            'denominator_value': metrics['security_state_capacity']
        },
        'recovery_source': {
            'numerator': 'nv_rec_success',
            'denominator': 'nv_rec_total',
            'numerator_value': metrics['nv_rec_success'],
            'denominator_value': metrics['nv_rec_total']
        },
        'error_source': {
            'field': 'nv_err_rate',
            'formula': 'nv_err_exec / nv_total_valid_exec',
            'value': metrics['nv_err_rate']
        },
        'P_sec': p_sec
    }

    return p_sec, provenance


def main():
    """CLI for computing formal security score."""
    if len(sys.argv) < 5:
        print("Usage: compute_formal_security_score.py <fuzzer_stats_path> <beta1> <beta2> <beta3>")
        print()
        print("Authority: M-13 formula P_sec = β1*Cov + β2*(1/(1+Err)) + β3*R_rec")
        print("Weights must be in [0,1] and sum to 1.0")
        sys.exit(1)

    stats_path = Path(sys.argv[1])
    try:
        config = FormalScoreConfig(
            beta1=float(sys.argv[2]),
            beta2=float(sys.argv[3]),
            beta3=float(sys.argv[4])
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    score, provenance = compute_from_stats(stats_path, config)

    result = {
        'formal_security_score': score,
        'provenance': provenance
    }

    print(json.dumps(result, indent=2))

    if score is None:
        sys.exit(1)


if __name__ == '__main__':
    main()
