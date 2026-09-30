from __future__ import annotations
from dataclasses import dataclass

from relaygrid.models import TelemetrySample
from relaygrid.telemetry.quality import newest_valid, stale

@dataclass(frozen=True)
class BackupLink:
    site_id: str
    coverage_ok: bool
    latency_ms: float

@dataclass(frozen=True)
class HandoverDecision:
    proceed: bool
    link_ok: bool
    data_ok: bool
    site_id: str
    reasons: tuple[str,...]

_QUALITY_RANK={"good":0,"suspect":1}

def dedupe_samples(before:list[TelemetrySample],after:list[TelemetrySample]):
    # Same reading may be delivered on both links; prefer the copy received
    # after switchover, then the newer timestamp, then the better quality.
    chosen:dict[tuple[str,int],TelemetrySample]={}
    preferred:dict[tuple[str,int],int]={}
    for side,samples in enumerate((before,after)):
        for sample in samples:
            key=(sample.point_id,sample.sequence)
            rank=(side,sample.timestamp_s,_QUALITY_RANK.get(sample.quality,2))
            if key not in chosen or rank>preferred[key]:
                chosen[key]=sample; preferred[key]=rank
    return [chosen[k] for k in sorted(chosen)]

def assess_handover(link:BackupLink,samples:list[TelemetrySample],now_s:float,*,
                    max_latency_ms:float,max_age_s:float,
                    queue_depth:int=0,queue_limit:int=0,
                    required_points:list[str]|None=None):
    if link.latency_ms<0 or max_latency_ms<0: raise ValueError("invalid latency")
    if queue_depth<0 or queue_limit<=0: raise ValueError("invalid command queue")
    link_reasons:list[str]=[]
    if not link.coverage_ok: link_reasons.append("coverage_unavailable")
    if link.latency_ms>max_latency_ms: link_reasons.append("latency_exceeded")
    if queue_depth>=queue_limit: link_reasons.append("command_queue_full")
    link_ok=not link_reasons

    by_point:dict[str,list[TelemetrySample]]={}
    for sample in samples:
        by_point.setdefault(sample.point_id,[]).append(sample)
    points=sorted(by_point) if required_points is None else list(dict.fromkeys(required_points))
    data_reasons:list[str]=[]
    for point_id in points:
        point_samples=by_point.get(point_id,[])
        latest=newest_valid(point_samples)
        if latest is None:
            data_reasons.append("telemetry_bad_quality:"+point_id if point_samples else "telemetry_missing:"+point_id)
        elif stale(latest,now_s,max_age_s):
            data_reasons.append("telemetry_stale:"+point_id)
    data_ok=not data_reasons
    proceed=link_ok and data_ok
    return HandoverDecision(proceed,link_ok,data_ok,link.site_id,tuple(link_reasons+data_reasons))
