from fastapi import APIRouter, Depends

from core.auth import actor, allow
from core.audit import record
from core.db import transaction
from core.records import scan
from domain import venues_service as service
from domain.venues_model import venues
from domain.venues_schemas import SignVenue

router = APIRouter()

@router.get('/venues')
def list_venues(user=Depends(actor)):
    with transaction() as conn:
        return scan(conn, venues)


@router.post('/venues/sign-venue')
def sign_venue(data: SignVenue, user=Depends(actor)):
    allow(user, ('reviewer',))
    with transaction() as conn:
        output = service.sign_venue(conn, user, data)
        record(conn, user, 'venues.sign_venue')
        return output
