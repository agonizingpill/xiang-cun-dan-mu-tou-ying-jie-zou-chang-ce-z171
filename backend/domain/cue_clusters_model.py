from sqlalchemy import Boolean, CheckConstraint, Column, Float, ForeignKey, Integer, JSON, String, Table

from core.db import metadata


cue_clusters = Table('cue_clusters', metadata,
    Column('code', String(64), primary_key=True),
    Column('track', String(160), ForeignKey('cue_tracks.code'), nullable=False),
    Column('representative', String(160), ForeignKey('cue_tracks.code'), nullable=False),
    Column('distance', Float, nullable=False),
    Column('members', JSON, nullable=False),
    Column('token', String(64), nullable=False, unique=True),
)
