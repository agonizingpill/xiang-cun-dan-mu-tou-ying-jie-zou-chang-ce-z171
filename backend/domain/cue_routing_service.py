from sqlalchemy import select

from core.queueing import submit, result
from core.records import get, insert, need, scan, update
from domain.venues_model import venues
from domain.cue_tracks_model import cue_tracks
from domain.cue_clusters_model import cue_clusters
from domain.cue_routing_model import cue_routing


def share_cue(conn, user, data):
    from sqlalchemy import or_
    group=get(conn,cue_clusters,data.cluster)
    origin=get(conn,cue_tracks,group['track'])['venue']
    venues_by_key={x:get(conn,venues,x,lock=True) for x in sorted({origin,data.destination})}
    target=venues_by_key[data.destination]
    need(target['ready'],'目标场地尚未签验收单')
    need(target['protocol']==venues_by_key[origin]['protocol'],'两场计量协议不同，须登记独立分路提示')
    need(len(data.route)<=7,'分路编号超界')
    used=[x for x in scan(conn,cue_routing) if x['destination']==target['code'] and x['status']=='已合用']
    need(len(used)<target['channels'] and not any(x['route']==data.route for x in used),'目标分路已被占')
    return insert(conn,cue_routing,**data.model_dump(),status='已合用')


def record_separate(conn, user, data):
    group=get(conn,cue_clusters,data.cluster)
    source=get(conn,venues,get(conn,cue_tracks,group['track'])['venue'])
    target=get(conn,venues,data.destination)
    need(source['protocol']!=target['protocol'],'同协议可直接用合用签回')
    return insert(conn,cue_routing,**data.model_dump(),status='异协议分路提示')
