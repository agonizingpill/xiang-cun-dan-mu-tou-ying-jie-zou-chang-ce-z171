from sqlalchemy import (Column, DateTime, Float, ForeignKey, Integer, JSON,
                        String, Table, UniqueConstraint)

from core.db import metadata


# 每次“签发”都追加一行：同一晚（plan_date）的每一版排演都保留，供历次查询。
rehearsal_plans = Table('rehearsal_plans', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('code', String(64), nullable=False, unique=True),
    Column('plan_date', String(40), nullable=False, index=True),
    Column('version', Integer, nullable=False),
    Column('base_version', Integer, nullable=True),
    Column('status', String(32), nullable=False),
    Column('groups', JSON, nullable=False),
    Column('tracks', JSON, nullable=False),
    Column('venues', JSON, nullable=False),
    Column('cost', Float, nullable=False),
    Column('snapshot', JSON, nullable=False),
    Column('draft_token', String(64), nullable=True, unique=True),
    Column('idempotency_key', String(128), nullable=True, unique=True),
    Column('created_by', String(100), nullable=False),
    Column('created_at', DateTime, nullable=False),
    UniqueConstraint('plan_date', 'version', name='uq_rehearsal_date_version'),
)


# 每晚一行的现行版本指针，签发时对该行加锁，做乐观版本校验。
rehearsal_heads = Table('rehearsal_heads', metadata,
    Column('plan_date', String(40), primary_key=True),
    Column('current_version', Integer, nullable=False),
    Column('current_code', String(64), nullable=True),
    Column('updated_by', String(100), nullable=True),
    Column('updated_at', DateTime, nullable=True),
)
