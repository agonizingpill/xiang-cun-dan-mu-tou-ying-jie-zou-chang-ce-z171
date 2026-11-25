from sqlalchemy import select

from core.queueing import submit, result
from core.records import get, insert, need, scan, update
from domain.venues_model import venues
from domain.cue_tracks_model import cue_tracks
from domain.cue_clusters_model import cue_clusters
from domain.cue_routing_model import cue_routing


def compare_cues(conn, user, data):
    q=get(conn,cue_tracks,data.track)
    ref=[x for x in scan(conn,cue_tracks) if x['locked'] and x['code']!=data.track]
    need(q['locked'] and 8<=len(ref)<=200,'需要已确认素材及足够参考片段')
    return submit(user,{'track':q,'references':ref})


def save_cluster(conn, user, data):
    run=result(user,data.token); stats=run['result']
    return insert(conn,cue_clusters,code=data.code,track=run['input']['track']['code'],
      representative=stats['representative'],distance=stats['distance'],members=stats['members'],token=data.token)
