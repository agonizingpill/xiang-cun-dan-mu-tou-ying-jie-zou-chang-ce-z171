from fastapi import APIRouter, Depends

from core.auth import actor, allow
from core.audit import record
from core.db import transaction
from core.records import scan
from domain import cue_clusters_service as service
from domain.cue_clusters_model import cue_clusters
from domain.cue_clusters_schemas import CompareCues, SaveCluster

router = APIRouter()

@router.get('/cue_clusters')
def list_cue_clusters(user=Depends(actor)):
    with transaction() as conn:
        return scan(conn, cue_clusters)


@router.post('/cue_clusters/compare-cues')
def compare_cues(data: CompareCues, user=Depends(actor)):
    allow(user, ('operator', 'reviewer'))
    with transaction() as conn:
        output = service.compare_cues(conn, user, data)
        record(conn, user, 'cue_clusters.compare_cues')
        return output


@router.post('/cue_clusters/save-cluster')
def save_cluster(data: SaveCluster, user=Depends(actor)):
    allow(user, ('reviewer',))
    with transaction() as conn:
        output = service.save_cluster(conn, user, data)
        record(conn, user, 'cue_clusters.save_cluster')
        return output
