from sqlalchemy import select

from core.queueing import submit, result
from core.records import get, insert, need, scan, update
from domain.venues_model import venues
from domain.cue_tracks_model import cue_tracks
from domain.cue_clusters_model import cue_clusters
from domain.cue_routing_model import cue_routing


def record_track(conn, user, data):
    v=get(conn,venues,data.venue)
    need(v['ready'],'场地未签验收单')
    t=data.timings
    need(isinstance(t,list) and 4<=len(t)<=30 and all(type(x) in (int,float) and 0<=x<=180 for x in t)
         and all(a<b for a,b in zip(t,t[1:])),'拍点需为递增有限时间序列')
    need(-5<=data.shift<=5,'拍点漂移超界')
    return insert(conn,cue_tracks,**data.model_dump(),locked=False)


def lock_track(conn, user, data):
    get(conn,cue_tracks,data.track,lock=True)
    return update(conn,cue_tracks,data.track,locked=True)
