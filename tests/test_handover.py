
from relaygrid.communications.handover import BackupLink, assess_handover, dedupe_samples
from relaygrid.models import TelemetrySample

def _fresh(point_id, ts=50.0, seq=2, quality="good"):
    return TelemetrySample(point_id, ts, seq, 1.0, quality)

def test_handover_proceeds_when_link_and_data_good():
    link=BackupLink("site-b", True, 80.0)
    d=assess_handover(link, [_fresh("p1"), _fresh("p2")], 60.0,
                      max_latency_ms=150.0, max_age_s=20.0, queue_limit=8)
    assert d.proceed and d.link_ok and d.data_ok and d.site_id=="site-b" and d.reasons==()

def test_handover_holds_when_link_bad_even_if_data_good():
    link=BackupLink("site-b", False, 200.0)
    d=assess_handover(link, [_fresh("p1")], 60.0,
                      max_latency_ms=150.0, max_age_s=20.0,
                      queue_depth=8, queue_limit=8)
    assert not d.proceed and not d.link_ok and d.data_ok
    assert d.reasons==("coverage_unavailable","latency_exceeded","command_queue_full")
    assert d.site_id=="site-b"

def test_handover_holds_when_data_bad_even_if_link_good():
    link=BackupLink("site-b", True, 80.0)
    samples=[TelemetrySample("p1",0.0,1,1.0,"good"), TelemetrySample("p2",0.0,1,1.0,"bad")]
    d=assess_handover(link, samples, 60.0,
                      max_latency_ms=150.0, max_age_s=20.0, queue_limit=8,
                      required_points=["p1","p2","p3"])
    assert not d.proceed and d.link_ok and not d.data_ok
    assert d.reasons==("telemetry_stale:p1","telemetry_bad_quality:p2","telemetry_missing:p3")

def test_dedupe_prefers_after_switchover_copy():
    before=[TelemetrySample("p1",10.0,1,1.0),TelemetrySample("p1",20.0,2,2.0,"suspect")]
    after=[TelemetrySample("p1",10.0,1,1.5)]
    out=dedupe_samples(before,after)
    assert [(s.point_id,s.sequence,s.value) for s in out]==[("p1",1,1.5),("p1",2,2.0)]

def test_dedupe_same_side_keeps_better_copy():
    before=[]
    after=[TelemetrySample("p1",10.0,1,1.0,"good"),TelemetrySample("p1",12.0,1,2.0,"suspect")]
    out=dedupe_samples(before,after)
    assert len(out)==1 and out[0].value==2.0
