from sqlalchemy import select

from core.queueing import submit, result
from core.records import get, insert, need, scan, update
from domain.venues_model import venues
from domain.cue_tracks_model import cue_tracks
from domain.cue_clusters_model import cue_clusters
from domain.cue_routing_model import cue_routing


def sign_venue(conn, user, data):
    get(conn,venues,data.venue,lock=True)
    need(data.receipt.startswith('MTR-'),'电表验收编号缺失')
    return update(conn,venues,data.venue,ready=True)
