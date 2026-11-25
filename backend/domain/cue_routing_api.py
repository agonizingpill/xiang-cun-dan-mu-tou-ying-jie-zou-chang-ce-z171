from fastapi import APIRouter, Depends

from core.auth import actor, allow
from core.audit import record
from core.db import transaction
from core.records import scan
from domain import cue_routing_service as service
from domain.cue_routing_model import cue_routing
from domain.cue_routing_schemas import ShareCue, RecordSeparate

router = APIRouter()

@router.get('/cue_routing')
def list_cue_routing(user=Depends(actor)):
    with transaction() as conn:
        return scan(conn, cue_routing)


@router.post('/cue_routing/share-cue')
def share_cue(data: ShareCue, user=Depends(actor)):
    allow(user, ('reviewer',))
    with transaction() as conn:
        output = service.share_cue(conn, user, data)
        record(conn, user, 'cue_routing.share_cue')
        return output


@router.post('/cue_routing/record-separate')
def record_separate(data: RecordSeparate, user=Depends(actor)):
    allow(user, ('operator', 'reviewer'))
    with transaction() as conn:
        output = service.record_separate(conn, user, data)
        record(conn, user, 'cue_routing.record_separate')
        return output
