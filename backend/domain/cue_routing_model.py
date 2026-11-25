from sqlalchemy import Boolean, CheckConstraint, Column, Float, ForeignKey, Integer, JSON, String, Table

from core.db import metadata


cue_routing = Table('cue_routing', metadata,
    Column('code', String(64), primary_key=True),
    Column('cluster', String(160), ForeignKey('cue_clusters.code'), nullable=False),
    Column('destination', String(160), ForeignKey('venues.code'), nullable=False),
    Column('route', String(160), nullable=False),
    Column('status', String(160), nullable=False),
)
