from sqlalchemy import Boolean, CheckConstraint, Column, Float, ForeignKey, Integer, JSON, String, Table

from core.db import metadata


venues = Table('venues', metadata,
    Column('code', String(64), primary_key=True),
    Column('protocol', String(160), nullable=False),
    Column('channels', Integer, nullable=False),
    Column('ready', Boolean, nullable=False),
)
