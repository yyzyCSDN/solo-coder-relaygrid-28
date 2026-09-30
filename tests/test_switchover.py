
from relaygrid.communications.switchover import (
    assess_switchover, best_backup_site, dedup_switch_samples,
)
from relaygrid.communications.radio import RadioSite
from relaygrid.models import TelemetrySample


def test_switchover_qualified_continues_remote():
    sample = TelemetrySample("p", 100, 10, 5.0)
    a = assess_switchover("site-b", margin_db=12.0, latency_ms=120.0,
                          sample=sample, now_s=100.0, pending_commands=2)
    assert a.link_ok and a.data_ok and a.can_remote
    assert a.reasons == ()
    assert a.site_id == "site-b"
    assert a.coverage == "robust"


def test_switchover_marginal_coverage_still_link_ok():
    sample = TelemetrySample("p", 100, 10, 5.0)
    a = assess_switchover("site-b", margin_db=3.0, latency_ms=120.0,
                          sample=sample, now_s=100.0, pending_commands=0)
    assert a.coverage == "marginal" and a.link_ok and a.can_remote


def test_switchover_unavailable_coverage_blocks_remote():
    sample = TelemetrySample("p", 100, 10, 5.0)
    a = assess_switchover("site-b", margin_db=-2.0, latency_ms=120.0,
                          sample=sample, now_s=100.0, pending_commands=0)
    assert not a.link_ok and a.data_ok
    assert not a.can_remote
    assert any("coverage" in r for r in a.reasons)


def test_switchover_latency_over_budget_blocks_remote():
    sample = TelemetrySample("p", 100, 10, 5.0)
    a = assess_switchover("site-b", margin_db=12.0, latency_ms=400.0,
                          sample=sample, now_s=100.0, pending_commands=0,
                          latency_budget_ms=300.0)
    assert not a.link_ok and not a.can_remote
    assert any("latency" in r for r in a.reasons)


def test_switchover_stale_telemetry_blocks_remote():
    sample = TelemetrySample("p", 100, 10, 5.0)
    a = assess_switchover("site-b", margin_db=12.0, latency_ms=120.0,
                          sample=sample, now_s=300.0, pending_commands=0)
    assert a.link_ok and not a.data_ok and not a.can_remote
    assert any("stale" in r for r in a.reasons)


def test_switchover_bad_quality_telemetry_blocks_remote():
    sample = TelemetrySample("p", 100, 10, 5.0, quality="bad")
    a = assess_switchover("site-b", margin_db=12.0, latency_ms=120.0,
                          sample=sample, now_s=100.0, pending_commands=0)
    assert not a.data_ok and not a.can_remote
    assert any("quality" in r for r in a.reasons)


def test_switchover_missing_telemetry_blocks_remote():
    a = assess_switchover("site-b", margin_db=12.0, latency_ms=120.0,
                          sample=None, now_s=100.0, pending_commands=0)
    assert not a.data_ok and not a.can_remote
    assert any("no sample" in r for r in a.reasons)


def test_switchover_queue_overflow_blocks_remote():
    sample = TelemetrySample("p", 100, 10, 5.0)
    a = assess_switchover("site-b", margin_db=12.0, latency_ms=120.0,
                          sample=sample, now_s=100.0, pending_commands=20,
                          queue_limit=8)
    assert not a.data_ok and not a.can_remote
    assert any("queue" in r for r in a.reasons)


def test_switchover_records_every_failure_reason():
    sample = TelemetrySample("p", 10, 1, 5.0, quality="bad")
    a = assess_switchover("site-b", margin_db=-5.0, latency_ms=500.0,
                          sample=sample, now_s=1000.0, pending_commands=20)
    assert not a.link_ok and not a.data_ok and not a.can_remote
    assert len(a.reasons) == 4
    assert a.site_id == "site-b"


def test_best_backup_site_picks_largest_margin():
    near = RadioSite("near", 40, 10, 0, 0, 30)
    far = RadioSite("far", 40, 10, 0, 0, 30)
    pick = best_backup_site([(near, 5.0), (far, 20.0)], 900.0, -90.0)
    assert pick is not None and pick[0] == "near"
    assert pick[1] > 0


def test_dedup_switch_samples_keeps_newest_timestamp():
    pre = [TelemetrySample("p", 100, 1, 1.0), TelemetrySample("p", 101, 2, 2.0)]
    post = [TelemetrySample("p", 102, 2, 2.5), TelemetrySample("p", 103, 3, 3.0)]
    merged = dedup_switch_samples(pre, post)
    assert [s.sequence for s in merged] == [1, 2, 3]
    assert merged[1].timestamp_s == 102  # post-switch copy wins on newer timestamp


def test_dedup_switch_samples_post_wins_tie():
    pre = [TelemetrySample("p", 100, 1, 1.0)]
    post = [TelemetrySample("p", 100, 1, 1.5)]
    merged = dedup_switch_samples(pre, post)
    assert len(merged) == 1 and merged[0].value == 1.5


def test_dedup_switch_samples_empty():
    assert dedup_switch_samples([], []) == []
