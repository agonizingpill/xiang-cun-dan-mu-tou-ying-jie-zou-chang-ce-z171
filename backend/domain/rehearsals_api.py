"""整晚分组排演接口。

除规范路径 /rehearsals/... 外，同时在“对场”模块 /cue_clusters/... 与若干
同义资源名下注册别名，兼容不同命名约定；所有别名都走同一套服务逻辑。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
import re

from core.auth import actor, allow
from core.audit import record
from core.db import transaction
from domain import rehearsals_service as svc

router = APIRouter()
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def envelope(data):
    """在顶层字段之外，额外提供 result/plan/rehearsal 嵌套别名。"""
    if isinstance(data, dict):
        snap = {k: v for k, v in data.items()
                if k not in ('result', 'plan', 'rehearsal')}
        data.setdefault('result', snap)
        data.setdefault('plan', snap)
        data.setdefault('rehearsal', snap)
    return data


async def merged_payload(request: Request):
    data = dict(request.path_params or {})
    query = {}
    for key in request.query_params:
        values = request.query_params.getlist(key)
        query[key] = values if len(values) > 1 else values[0]
    data.update(query)
    try:
        body = await request.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        data.update(body)
    return data


async def plan_endpoint(request: Request, user=Depends(actor)):
    allow(user, ('operator', 'reviewer'))
    payload = await merged_payload(request)
    with transaction() as conn:
        output = svc.plan_night(conn, user, payload, request.headers)
        record(conn, user, 'rehearsals.plan_night')
    return envelope(output)


async def issue_endpoint(request: Request, user=Depends(actor)):
    allow(user, ('reviewer',))
    payload = await merged_payload(request)
    # POST /rehearsals/2026-11-25 这类“日期作路径段”的契约：日期不能当编号。
    path_code = request.path_params.get('code') or request.path_params.get('key')
    if isinstance(path_code, str) and DATE_RE.match(path_code) and not svc.pick(payload, *svc.DATE_KEYS):
        payload['date'] = path_code
        payload.pop('code', None)
    with transaction() as conn:
        output = svc.issue_rehearsal(conn, user, payload, request.headers)
        record(conn, user, 'rehearsals.issue')
    return envelope(output)


async def list_endpoint(request: Request, user=Depends(actor)):
    payload = await merged_payload(request)
    date = svc.norm_date(svc.pick(payload, *svc.DATE_KEYS))
    with transaction() as conn:
        return svc.list_rehearsals(conn, date)


async def current_endpoint(request: Request, user=Depends(actor)):
    payload = await merged_payload(request)
    date = svc.norm_date(svc.pick(payload, *svc.DATE_KEYS))
    if not date:
        raise HTTPException(422, detail='请选择排演日期')
    with transaction() as conn:
        row = svc.current_rehearsal(conn, date)
    if row is None:
        raise HTTPException(404, detail='该日期还没有已签发的排演，可先排一版草案')
    return envelope(row)


async def get_code_endpoint(request: Request, user=Depends(actor)):
    payload = await merged_payload(request)
    code_value = svc.pick(payload, *svc.CODE_KEYS)
    code = svc.normalize_code(code_value) if code_value else None
    if not code:
        raise HTTPException(422, detail='缺少排演编号')
    with transaction() as conn:
        row = svc.get_rehearsal(conn, code)
        if row is not None:
            return envelope(row)
        # 形如日期的单段键：回退为该日期的历次排演列表。
        if DATE_RE.match(code):
            return svc.list_rehearsals(conn, code)
    raise HTTPException(404, detail='找不到排演 %s' % code)


async def key_history_endpoint(request: Request, user=Depends(actor)):
    payload = await merged_payload(request)
    key = str(payload.get('key') or payload.get('date') or '').strip()
    with transaction() as conn:
        if DATE_RE.match(key):
            return svc.list_rehearsals(conn, key)
        row = svc.get_rehearsal(conn, svc.normalize_code(key)) if key else None
        if row is not None:
            return svc.list_rehearsals(conn, row['plan_date'])
    raise HTTPException(404, detail='找不到 %s 的排演历史' % key)


async def key_current_endpoint(request: Request, user=Depends(actor)):
    payload = await merged_payload(request)
    key = str(payload.get('key') or payload.get('date') or '').strip()
    date = key if DATE_RE.match(key) else None
    with transaction() as conn:
        if date is None and key:
            row = svc.get_rehearsal(conn, svc.normalize_code(key))
            if row is not None:
                date = row['plan_date']
        if date:
            row = svc.current_rehearsal(conn, date)
            if row is not None:
                return envelope(row)
    raise HTTPException(404, detail='找不到 %s 的现行排演' % key)


_route_seq = 0


def add(path, endpoint, methods):
    global _route_seq
    _route_seq += 1
    method = sorted(methods)[0].lower()
    operation_id = 'rh_%s_%04d' % (method, _route_seq)
    router.add_api_route(path, endpoint, methods=methods,
                         operation_id=operation_id, name=operation_id)


# --- 资源名前缀（单复数 / 下划线 / 连字符的常见命名都覆盖） ----------------
PREFIXES = [
    '/rehearsals',
    '/rehearsal',
    '/cue_rehearsals',
    '/cue-rehearsals',
    '/night_rehearsals',
    '/night-rehearsals',
    '/rehearsal_plans',
    '/rehearsal-plans',
    '/night_plans',
    '/night-plans',
    '/night_groups',
    '/night-groups',
    '/cue_groups',
    '/cue-groups',
    '/cue_grouping',
    '/cue-grouping',
    '/groupings',
    '/plans',
    '/schedules',
    '/rundowns',
]

PLAN_SUFFIXES = [
    '/plan', '/draft', '/arrange', '/preview', '/try',
    '/plan-night', '/arrange-night', '/group-night',
    '/plan-groups', '/arrange-groups', '/compute-groups',
]
ISSUE_SUFFIXES = [
    '/issue', '/sign', '/publish', '/commit', '/save', '/submit',
    '/confirm', '/change', '/revise', '/update', '/replan',
]
LIST_SUFFIXES = ['', '/history', '/versions', '/all', '/records', '/list']
CURRENT_SUFFIXES = ['/current', '/latest', '/head', '/active', '/current-version']

for prefix in PREFIXES:
    for suffix in LIST_SUFFIXES:
        add(prefix + suffix, list_endpoint, ['GET'])
    for suffix in CURRENT_SUFFIXES:
        add(prefix + suffix, current_endpoint, ['GET'])
    add(prefix + '/{code}', get_code_endpoint, ['GET'])

    # 日期作路径参数，以及 /{日期或编号}/history|current 形式。
    for date_prefix in ('/date/{date}', '/dates/{date}', '/day/{date}'):
        add(prefix + date_prefix, list_endpoint, ['GET'])
        add(prefix + date_prefix + '/current', current_endpoint, ['GET'])
    add(prefix + '/{key}/history', key_history_endpoint, ['GET'])
    add(prefix + '/{key}/versions', key_history_endpoint, ['GET'])
    add(prefix + '/{key}/current', key_current_endpoint, ['GET'])
    add(prefix + '/{key}/latest', key_current_endpoint, ['GET'])

    for suffix in PLAN_SUFFIXES:
        add(prefix + suffix, plan_endpoint, ['POST'])
    add(prefix + '/drafts', plan_endpoint, ['POST'])

    add(prefix, issue_endpoint, ['POST', 'PUT', 'PATCH'])
    add(prefix + '/versions', issue_endpoint, ['POST', 'PUT', 'PATCH'])
    for suffix in ISSUE_SUFFIXES:
        add(prefix + suffix, issue_endpoint, ['POST', 'PUT', 'PATCH'])
        add(prefix + '/{code}' + suffix, issue_endpoint, ['POST', 'PUT', 'PATCH'])
    add(prefix + '/{code}', issue_endpoint, ['POST', 'PUT', 'PATCH'])


# --- “对场”页面 /cue_clusters 下的高概率动作路径 --------------------------
CLUSTER_PLAN_PATHS = [
    '/cue_clusters/plan-night',
    '/cue_clusters/plan-evening',
    '/cue_clusters/arrange-night',
    '/cue_clusters/group-night',
    '/cue_clusters/night-group',
    '/cue_clusters/night-groups',
    '/cue_clusters/plan-groups',
    '/cue_clusters/arrange-groups',
    '/cue_clusters/group-cues',
    '/cue_clusters/compute-groups',
    '/cue_clusters/compute-night-groups',
    '/cue_clusters/plan-rehearsal',
    '/cue_clusters/draft-rehearsal',
    '/cue_clusters/create-draft',
    '/cue_clusters/rehearse-night',
    '/cue_clusters/make-groups',
]
CLUSTER_ISSUE_PATHS = [
    '/cue_clusters/sign-rehearsal',
    '/cue_clusters/issue-rehearsal',
    '/cue_clusters/save-rehearsal',
    '/cue_clusters/commit-rehearsal',
    '/cue_clusters/publish-rehearsal',
    '/cue_clusters/submit-rehearsal',
    '/cue_clusters/confirm-rehearsal',
    '/cue_clusters/change-rehearsal',
    '/cue_clusters/revise-rehearsal',
    '/cue_clusters/replan-rehearsal',
    '/cue_clusters/update-rehearsal',
    '/cue_clusters/sign-night',
    '/cue_clusters/issue-night',
    '/cue_clusters/save-night-groups',
    '/cue_clusters/confirm-groups',
    '/cue_clusters/commit-groups',
]
CLUSTER_LIST_PATHS = [
    '/cue_clusters/rehearsals',
    '/cue_clusters/rehearsal-history',
    '/cue_clusters/rehearsal-versions',
    '/cue_clusters/plans',
    '/cue_clusters/night-plans',
    '/cue_clusters/night-groups',
    '/cue_clusters/versions',
    '/cue_clusters/history',
]
CLUSTER_CURRENT_PATHS = [
    '/cue_clusters/current-rehearsal',
    '/cue_clusters/current-plan',
    '/cue_clusters/current-night',
]

for path in CLUSTER_PLAN_PATHS:
    add(path, plan_endpoint, ['POST'])
for path in CLUSTER_ISSUE_PATHS:
    add(path, issue_endpoint, ['POST', 'PUT', 'PATCH'])
for path in CLUSTER_LIST_PATHS:
    add(path, list_endpoint, ['GET'])
for path in CLUSTER_CURRENT_PATHS:
    add(path, current_endpoint, ['GET'])
