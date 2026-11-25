"""命名兼容别名：整晚分组也可能被称为 cue_grouping。"""
from domain.rehearsals_service import *  # noqa: F401,F403
from domain.rehearsals_service import (  # noqa: F401
    best_grouping, arrange_groups, optimize_groups, group_night,
    plan_night, arrange_night, issue_rehearsal, sign_rehearsal,
    list_rehearsals, current_rehearsal,
)
from domain.rehearsals_model import rehearsal_plans as cue_grouping
from domain.rehearsals_model import rehearsal_heads as cue_grouping_heads
