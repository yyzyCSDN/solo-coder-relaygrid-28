"""Switchover assessment for a degraded site link.

When a site's primary link degrades, traffic moves to a backup link.
Coverage, latency, telemetry freshness, and the remote-control queue are
no longer judged independently: remote control continues only when the
backup link and the data quality are both qualified. Samples received
across the switch boundary are deduplicated by sequence number, and the
assessment records the site actually used together with every failure
reason.
"""
from __future__ import annotations
from dataclasses import dataclass

from relaygrid.models import TelemetrySample
from relaygrid.telemetry.quality import accept_sample, stale
from relaygrid.communications.radio import RadioSite, best_site, coverage_state


def check_coverage(margin_db: float):
    state = coverage_state(margin_db)
    if state == "unavailable":
        return False, f"coverage unavailable: margin {margin_db:.1f} dB below 0"
    return True, None


def check_latency(latency_ms: float, budget_ms: float):
    if latency_ms < 0:
        return False, f"latency {latency_ms:.0f} ms is invalid"
    if latency_ms > budget_ms:
        return False, f"latency {latency_ms:.0f} ms exceeds budget {budget_ms:.0f} ms"
    return True, None


def check_telemetry(sample: TelemetrySample | None, now_s: float, max_age_s: float):
    if sample is None:
        return False, "telemetry unavailable: no sample"
    if not accept_sample(None, sample):
        return False, f"telemetry quality {sample.quality!r} not acceptable"
    if stale(sample, now_s, max_age_s):
        age = now_s - sample.timestamp_s
        return False, f"telemetry stale: age {age:.0f} s exceeds {max_age_s:.0f} s"
    return True, None


def check_queue(pending_count: int, limit: int):
    if pending_count < 0:
        return False, "command queue depth cannot be negative"
    if pending_count > limit:
        return False, f"command queue depth {pending_count} exceeds limit {limit}"
    return True, None


@dataclass(frozen=True)
class SwitchoverAssessment:
    site_id: str
    margin_db: float
    coverage: str
    latency_ms: float
    link_ok: bool
    data_ok: bool
    reasons: tuple[str, ...]

    @property
    def can_remote(self) -> bool:
        return self.link_ok and self.data_ok


def assess_switchover(site_id: str, margin_db: float, latency_ms: float,
                      sample: TelemetrySample | None, now_s: float,
                      pending_commands: int, *,
                      latency_budget_ms: float = 300.0,
                      telemetry_max_age_s: float = 120.0,
                      queue_limit: int = 8) -> SwitchoverAssessment:
    link_ok = True
    data_ok = True
    reasons: list[str] = []

    ok, reason = check_coverage(margin_db)
    if not ok:
        link_ok = False
        reasons.append(reason)

    ok, reason = check_latency(latency_ms, latency_budget_ms)
    if not ok:
        link_ok = False
        reasons.append(reason)

    ok, reason = check_telemetry(sample, now_s, telemetry_max_age_s)
    if not ok:
        data_ok = False
        reasons.append(reason)

    ok, reason = check_queue(pending_commands, queue_limit)
    if not ok:
        data_ok = False
        reasons.append(reason)

    return SwitchoverAssessment(site_id, margin_db, coverage_state(margin_db),
                                latency_ms, link_ok, data_ok, tuple(reasons))


def best_backup_site(sites: list[tuple[RadioSite, float]], frequency_mhz: float,
                     sensitivity_dbm: float):
    """Return (site_id, margin_db) for the backup site with the largest
    link margin, or None when no site is available."""
    best = best_site(sites, frequency_mhz, sensitivity_dbm)
    if best is None:
        return None
    margin, site_id, _rx = best
    return site_id, margin


def dedup_switch_samples(pre_switch: list[TelemetrySample],
                         post_switch: list[TelemetrySample]) -> list[TelemetrySample]:
    """Merge samples received across a link switch.

    The primary and backup paths can deliver the same sequence number;
    keep the copy with the newest timestamp, preferring the post-switch
    copy on a tie, mirroring the historian's live/recovery merge.
    """
    by_seq: dict[int, TelemetrySample] = {}
    for sample in pre_switch:
        by_seq[sample.sequence] = sample
    for sample in post_switch:
        current = by_seq.get(sample.sequence)
        if current is None or sample.timestamp_s >= current.timestamp_s:
            by_seq[sample.sequence] = sample
    return [by_seq[seq] for seq in sorted(by_seq)]
