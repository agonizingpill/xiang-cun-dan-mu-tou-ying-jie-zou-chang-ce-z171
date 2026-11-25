"""模块命名兼容垫片：实现统一位于 domain.rehearsals_service。"""
from domain.rehearsals_service import *  # noqa: F401,F403
from domain.rehearsals_service import (  # noqa: F401
    best_grouping, try_grouping, optimize_groups, arrange_groups,
    plan_night, arrange_night, issue_rehearsal, sign_rehearsal,
    list_rehearsals, current_rehearsal, build_plan,
)
