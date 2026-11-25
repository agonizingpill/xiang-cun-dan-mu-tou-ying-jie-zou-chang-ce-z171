from fastapi import APIRouter, Depends

from core.auth import actor, allow
from core.audit import record
from core.db import transaction
from core.records import scan
from domain import cue_tracks_service as service
from domain.cue_tracks_model import cue_tracks
from domain.cue_tracks_schemas import RecordTrack, LockTrack

router = APIRouter()

@router.get('/cue_tracks')
def list_cue_tracks(user=Depends(actor)):
    with transaction() as conn:
        return scan(conn, cue_tracks)


@router.post('/cue_tracks/record-track')
def record_track(data: RecordTrack, user=Depends(actor)):
    allow(user, ('operator', 'reviewer'))
    with transaction() as conn:
        output = service.record_track(conn, user, data)
        record(conn, user, 'cue_tracks.record_track')
        return output


@router.post('/cue_tracks/lock-track')
def lock_track(data: LockTrack, user=Depends(actor)):
    allow(user, ('reviewer',))
    with transaction() as conn:
        output = service.lock_track(conn, user, data)
        record(conn, user, 'cue_tracks.lock_track')
        return output
