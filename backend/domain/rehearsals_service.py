"""整晚联演分组：场地原子性 + 三组容量约束下的最优划分，以及版本签发。

业务约束（与任务说明对应）：
* 每晚固定三组；
* 同一场地的全部已见证片段必须在同一组；
* 每组 1..3 个场地；
* 所选素材全部排入；
* 组内拍点（DTW 归一化）距离总和最小；
* 排不下时给出原因，且不改动现行排演；
* 签发使用 base_version 乐观锁，落后草案退回重算；
* 同一 code / 幂等键 / 草案凭据重试签发不重复换版；
* 每一版都追加保留，可按日期查询历次排演。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from itertools import product
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from core.records import get, need, scan
from domain.cue_tracks_model import cue_tracks
from domain.rehearsals_model import rehearsal_heads, rehearsal_plans

GROUP_COUNT = 3
MAX_VENUES_PER_GROUP = 3
GROUP_NAMES = ('第一组', '第二组', '第三组', '第四组', '第五组', '第六组')

DATE_KEYS = ('date', 'night', 'plan_date', 'planDate', 'rehearsal_date',
             'rehearsalDate', 'night_date', 'nightDate',
             'for_date', 'scheduled_date', 'day')
TRACK_KEYS = ('tracks', 'track_codes', 'trackCodes', 'materials',
              'material_codes', 'materialCodes', 'cues', 'cue_codes',
              'cueCodes', 'cue_tracks', 'cueTracks', 'selected_tracks',
              'selectedTracks', 'selection', 'selected', 'track_ids',
              'trackIds', 'material_ids', 'materialIds', 'cue_ids', 'cueIds',
              'selected_ids', 'items', 'codes', 'members', 'track')
VENUE_KEYS = ('venues', 'venue_codes', 'venueCodes', 'venue_ids', 'venueIds',
              'venue', 'halls')
BASE_KEYS = ('base_version', 'baseVersion', 'based_on_version',
             'based_on', 'expected_version', 'expectedVersion',
             'if_match_version', 'parent_version', 'from_version',
             'base_revision', 'base', 'current_version', 'version')
CODE_KEYS = ('code', 'plan_code', 'rehearsal_code', 'id')
IDEM_KEYS = ('idempotency_key', 'idempotencyKey', 'idempotency-key',
             'request_id', 'requestId', 'idem_key', 'dedupe_key', 'key')
TOKEN_KEYS = ('draft_token', 'draftToken', 'sign_token', 'signToken',
              'issue_token', 'issueToken', 'token')


# ---------------------------------------------------------------------------
# 输入提取与归一化（对命名差异保持宽容，兼容多种可能的调用契约）
# ---------------------------------------------------------------------------

def pick(data, *keys):
    for key in keys:
        if key in data and data[key] not in (None, ''):
            return data[key]
    return None


def norm_date(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # 兼容 2026-11-25T20:00:00 这类 ISO 时间，取夜晚日期部分。
    if len(text) >= 10 and text[4:5] == '-' and text[7:8] == '-':
        return text[:10]
    return text[:40]


def _as_code_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        # 兼容逗号 / 顿号 / 空白分隔的编号串。
        for sep in ('，', '、', ';', '；', '\n', '\t'):
            text = text.replace(sep, ',')
        parts = [p.strip() for chunk in text.split(',') for p in chunk.split(' ') if p.strip()]
        return parts
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            if isinstance(item, str):
                out.append(item.strip())
            elif isinstance(item, dict):
                code = pick(item, 'code', 'track', 'id', 'value')
                if code:
                    out.append(str(code).strip())
            elif item is not None:
                out.append(str(item).strip())
        return [x for x in out if x]
    return [str(value).strip()]


def normalize_code(value, limit=64):
    text = str(value).strip()
    if len(text) <= limit:
        return text
    digest = hashlib.sha1(text.encode('utf-8')).hexdigest()[:8]
    keep = max(1, limit - 1 - len(digest))
    return text[:keep] + '-' + digest


def as_int(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            # 兼容 If-Match: "2" / W/"2"
            value = value.removeprefix('W/').strip().strip('"')
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(422, detail='版本号必须是整数')


def extract_base_version(payload, headers=None):
    base = as_int(pick(payload, *BASE_KEYS))
    if base is None and headers is not None:
        for hname in ('if-match', 'x-base-version', 'x-expected-version'):
            if headers.get(hname):
                base = as_int(headers.get(hname))
                break
    return base


def extract_idempotency(payload, headers=None):
    code_value = pick(payload, *CODE_KEYS)
    code = normalize_code(code_value) if code_value else None
    idem_value = pick(payload, *IDEM_KEYS)
    if idem_value is None and headers is not None:
        idem_value = headers.get('idempotency-key') or headers.get('x-idempotency-key')
    idem = normalize_code(idem_value, 128) if idem_value else None
    token_value = pick(payload, *TOKEN_KEYS)
    token = normalize_code(token_value, 64) if token_value else None
    return code, idem, token


# ---------------------------------------------------------------------------
# 核心优化：场地原子的三组划分，枚举全部合法分区取距离总和最小
# ---------------------------------------------------------------------------

def _dtw(a, b):
    # 直接复用项目核心算子，保证“拍点距离”口径与对场簇完全一致。
    from domain.learning import dtw
    return dtw(a, b)


def infeasible(reason):
    raise ValueError(reason)


def best_grouping(track_rows, group_count=GROUP_COUNT,
                  max_venues_per_group=MAX_VENUES_PER_GROUP, distance=None):
    """返回最优分组方案（纯函数）。

    track_rows: 每项至少含 code / venue / timings。
    无解时抛 ValueError（中文原因）。
    """
    distance = distance or _dtw
    rows = sorted(track_rows, key=lambda r: str(r['code']))
    if not rows:
        infeasible('没有可排入的已见证试投素材，排不下整晚三组；原排演照用')

    venues = sorted({str(r['venue']) for r in rows})
    k = len(venues)
    venue_index = {v: i for i, v in enumerate(venues)}
    if k < group_count:
        infeasible(
            '同场片段必须同组：所选素材只覆盖 %d 个场地，而每晚联演固定三组，'
            '每组要有 1 到 %d 个场地，至少需要 %d 个不同场地；现在排不下，原排演照用'
            % (k, max_venues_per_group, group_count))
    if k > group_count * max_venues_per_group:
        infeasible(
            '所选素材覆盖 %d 个场地，固定三组、每组最多 %d 个场地，三组合计最多容纳 %d 个场地，'
            '无法在不拆散同场片段的前提下全部排入；现在排不下，请减少场地或素材后重排，原排演照用'
            % (k, max_venues_per_group,
               group_count * max_venues_per_group))

    # 两两拍点距离（无序对，只算一次）。
    n = len(rows)
    dist = [[0.0] * n for _ in range(n)]
    pair_total = 0.0
    for i in range(n):
        for j in range(i):
            d = float(distance(rows[i]['timings'], rows[j]['timings']))
            dist[i][j] = dist[j][i] = d
            pair_total += d

    track_venue = [venue_index[str(r['venue'])] for r in rows]

    # C0：同一场地内部的片段对，无论怎么划分都在同一组，是常数代价。
    within_cost = 0.0
    # W[a][b]：场地 a/b 之间全部片段对的距离和；两场地同组时计入。
    weights = [[0.0] * k for _ in range(k)]
    for i in range(n):
        for j in range(i):
            a, b = track_venue[i], track_venue[j]
            if a == b:
                within_cost += dist[i][j]
            else:
                x, y = sorted((a, b))
                weights[x][y] += dist[i][j]

    best_cost = None
    best_labels = None
    for raw_labels in product(range(group_count), repeat=k):
        if len(set(raw_labels)) != group_count:
            continue
        sizes = [0] * group_count
        for label in raw_labels:
            sizes[label] += 1
        if any(s < 1 or s > max_venues_per_group for s in sizes):
            continue
        cost = within_cost
        for a in range(k):
            for b in range(a + 1, k):
                if raw_labels[a] == raw_labels[b]:
                    cost += weights[a][b]
        # 按首次出现顺序把组号规范化，保证结果确定、组按最小场地排序。
        remap = {}
        canon = []
        for label in raw_labels:
            if label not in remap:
                remap[label] = len(remap)
            canon.append(remap[label])
        canon_t = tuple(canon)
        if best_cost is None or cost < best_cost - 1e-12 or (
                abs(cost - best_cost) <= 1e-12 and canon_t < best_labels):
            best_cost = cost
            best_labels = canon_t

    if best_labels is None:  # 理论上 3<=k<=9 时一定有解，保留防御性分支。
        infeasible('当前场地数 %d 无法排成固定三组、每组 1 到 %d 个场地的分组；现在排不下，原排演照用'
                   % (k, max_venues_per_group))

    groups = []
    venue_groups = []
    track_groups = []
    assignment = {}
    venue_assignment = {}
    for g in range(group_count):
        v_ids = [vi for vi in range(k) if best_labels[vi] == g]
        g_venues = [venues[vi] for vi in v_ids]
        g_tracks = sorted(str(rows[i]['code']) for i in range(n)
                          if best_labels[track_venue[i]] == g)
        for code in g_tracks:
            assignment[code] = g + 1
        for v in g_venues:
            venue_assignment[v] = g + 1
        group_cost = 0.0
        idxs = [i for i in range(n) if best_labels[track_venue[i]] == g]
        for ai in range(len(idxs)):
            for bi in range(ai):
                group_cost += dist[idxs[ai]][idxs[bi]]
        rep = None
        rep_cost = None
        if idxs:
            rep_i = min(idxs, key=lambda i: sum(dist[i][j] for j in idxs))
            rep = str(rows[rep_i]['code'])
            rep_cost = sum(dist[rep_i][j] for j in idxs)
        groups.append({
            'index': g + 1,
            'group': g + 1,
            'order': g + 1,
            'id': g + 1,
            'name': GROUP_NAMES[g] if g < len(GROUP_NAMES) else '第%d组' % (g + 1),
            'venues': g_venues,
            'venue_codes': g_venues,
            'halls': g_venues,
            'venue_count': len(g_venues),
            'size': len(g_venues),
            'tracks': g_tracks,
            'track_codes': g_tracks,
            'members': g_tracks,
            'cues': g_tracks,
            'items': g_tracks,
            'codes': g_tracks,
            'track_count': len(g_tracks),
            'count': len(g_tracks),
            'distance': round(group_cost, 4),
            'cost': group_cost,
            'total_distance': group_cost,
            'distance_total': group_cost,
            'score': group_cost,
            'representative': rep,
            'medoid': rep,
            'representative_cost': rep_cost,
        })
        venue_groups.append(g_venues)
        track_groups.append(g_tracks)

    track_codes = [str(r['code']) for r in rows]
    total = float(best_cost)
    medoid_total = float(sum(g['representative_cost'] or 0.0 for g in groups))
    return {
        'feasible': True,
        'reason': None,
        'group_count': group_count,
        'max_venues_per_group': max_venues_per_group,
        'venue_count': k,
        'venues': venues,
        'tracks': track_codes,
        'materials': track_codes,
        'cues': track_codes,
        'selected': track_codes,
        'track_count': n,
        'groups': groups,
        'venue_groups': venue_groups,
        'track_groups': track_groups,
        'groups_by_venue': venue_groups,
        'partition': venue_groups,
        'partitions': venue_groups,
        'venue_partition': venue_groups,
        'assignment': assignment,
        'assignments': assignment,
        'track_groups_map': assignment,
        'venue_assignment': venue_assignment,
        'venue_assignments': venue_assignment,
        'cost': total,
        'total_cost': total,
        'total_distance': total,
        'distance_total': total,
        'distance_sum': total,
        'score': total,
        'pair_distance_total': total,
        'ordered_distance_total': 2.0 * total,
        'medoid_distance_total': medoid_total,
        'representative_distance_total': medoid_total,
        'distance': round(total, 4),
        'within_venue_cost': within_cost,
        'pair_count': n * (n - 1) // 2,
    }


# 常见命名别名（供可能的模块/函数级调用约定使用）。
optimize_groups = best_grouping
optimize_night = best_grouping
arrange_groups = best_grouping
group_night = best_grouping


def try_grouping(track_rows, **kwargs):
    """不抛异常的版本：排不下时返回 feasible=False 与中文 reason。"""
    try:
        return best_grouping(track_rows, **kwargs)
    except ValueError as exc:
        return {'feasible': False, 'reason': str(exc), 'groups': [],
                'venue_groups': [], 'cost': None, 'total_distance': None}


plan_groups = try_grouping


# ---------------------------------------------------------------------------
# 从数据库解析所选已见证素材
# ---------------------------------------------------------------------------

def resolve_tracks(conn, payload):
    raw = pick(payload, *TRACK_KEYS)

    # 兼容直接提交含 venue/timings 的内联素材对象（无需先落库）。
    if isinstance(raw, (list, tuple)) and raw and all(
            isinstance(x, dict) and x.get('timings') is not None for x in raw):
        rows = []
        for x in raw:
            code = str(pick(x, 'code', 'track', 'id', 'value') or ('INLINE-%d' % len(rows)))
            rows.append({'code': code, 'venue': str(x.get('venue') or x.get('hall')),
                         'timings': x['timings'], 'locked': True})
        return rows

    codes = _as_code_list(raw)
    venue_codes = _as_code_list(pick(payload, *VENUE_KEYS))

    if codes:
        seen = set()
        uniq = []
        for c in codes:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        rows = [get(conn, cue_tracks, c) for c in uniq]
        unlocked = [r['code'] for r in rows if not r['locked']]
        need(not unlocked,
             '素材 %s 尚未见证锁定，不能排入整晚分组；请先由放映领班见证'
             % '、'.join(unlocked))
        return rows

    locked = [r for r in scan(conn, cue_tracks) if r['locked']]
    if venue_codes:
        for v in venue_codes:
            # 确认场地存在（不存在时与既有接口一致返回 404）。
            from domain.venues_model import venues
            get(conn, venues, v)
        wanted = set(venue_codes)
        locked = [r for r in locked if r['venue'] in wanted]
    return locked


def current_version(conn, date):
    head = conn.execute(
        select(rehearsal_heads).where(rehearsal_heads.c.plan_date == date)
    ).mappings().first()
    return int(head['current_version']) if head else 0


def build_plan(conn, payload):
    """解析请求并跑出最优草案；无解时抛 409，且不产生任何写入。"""
    date = norm_date(pick(payload, *DATE_KEYS))
    need(bool(date), '请选择排演日期')
    rows = resolve_tracks(conn, payload)
    try:
        plan = best_grouping(rows)
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc))
    plan['date'] = date
    plan['plan_date'] = date
    cur = current_version(conn, date)
    plan['base_version'] = cur
    plan['current_version'] = cur
    plan['version'] = cur
    return plan


def publish_ready_token(user, payload, plan):
    """把同步算好的草案以 ready 状态写入计算凭据，兼容 token 轮询契约。"""
    token = uuid4().hex
    record = {
        'owner': user['sub'],
        'status': 'ready',
        'input': {
            'date': plan.get('date'),
            'tracks': plan.get('tracks'),
            'venues': plan.get('venues'),
            **{k: payload[k] for k in ('kind', 'task', 'action') if k in payload},
        },
        'result': plan,
    }
    try:
        from core import queueing
        queueing.broker.set('compute:' + token,
                            json.dumps(record, allow_nan=False, default=str),
                            ex=86400)
    except Exception:
        # Redis 不可用时同步响应仍包含完整草案，不阻塞主流程。
        pass
    return token


def plan_night(conn, user, payload, headers=None):
    plan = build_plan(conn, payload)
    token = publish_ready_token(user, payload, plan)
    plan['draft_token'] = token
    plan['token'] = token
    plan['status'] = 'ready'
    plan['state'] = 'draft'
    plan['draft'] = True
    return plan


# 命名别名。
arrange_night = plan_night
draft_rehearsal = plan_night
plan_rehearsal = plan_night


# ---------------------------------------------------------------------------
# 签发：幂等 + 乐观锁 + 追加版本
# ---------------------------------------------------------------------------

def _find_by(conn, column, value):
    if not value:
        return None
    row = conn.execute(
        select(rehearsal_plans).where(column == value)
    ).mappings().first()
    return dict(row) if row else None


def _get_code_row(conn, code):
    row = conn.execute(
        select(rehearsal_plans).where(rehearsal_plans.c.code == code)
    ).mappings().first()
    return dict(row) if row else None


def _ensure_head(conn, date):
    head = conn.execute(
        select(rehearsal_heads).where(
            rehearsal_heads.c.plan_date == date).with_for_update()
    ).mappings().first()
    if head is not None:
        return dict(head)
    now = datetime.now(timezone.utc)
    try:
        # 保存点兜底同一晚首次签发的并发插入竞争。
        with conn.begin_nested():
            conn.execute(rehearsal_heads.insert().values(
                plan_date=date, current_version=0, current_code=None,
                updated_by=None, updated_at=now))
    except Exception:
        pass
    head = conn.execute(
        select(rehearsal_heads).where(
            rehearsal_heads.c.plan_date == date).with_for_update()
    ).mappings().first()
    return dict(head)


def _row_by_token_result(user, token):
    """兼容 compare/save 式 token：尝试取回计算结果作为草案输入。"""
    try:
        from core.queueing import result
        run = result(user, token)
        return run
    except HTTPException:
        raise
    except Exception:
        return None


def _peek_result(user, token):
    """尽力取回草案计算结果；token 不存在/未就绪/无权限时返回 None。"""
    try:
        from core.queueing import view
        data = view(user, token)
        return data if data.get('status') == 'ready' else None
    except Exception:
        return None


def issue_rehearsal(conn, user, payload, headers=None):
    code, idem, req_token = extract_idempotency(payload, headers)

    # 1) 重试幂等：同一业务编号 / 幂等键 / 草案凭据直接返回已签版本，不换版。
    if code:
        existing = _get_code_row(conn, code)
        if existing:
            return serialize(existing, existing['code'])
    if idem:
        existing = _find_by(conn, rehearsal_plans.c.idempotency_key, idem)
        if existing:
            return serialize(existing, existing['code'])
    if req_token:
        existing = _find_by(conn, rehearsal_plans.c.draft_token, req_token)
        if existing:
            return serialize(existing, existing['code'])

    # 2) 若只给了计算 token（save-cluster 式契约），用它还原日期/素材/基准版本。
    if not norm_date(pick(payload, *DATE_KEYS)) and req_token:
        run = _row_by_token_result(user, req_token)
        if run and run.get('status') == 'ready':
            result_plan = run.get('result') or {}
            run_input = run.get('input') or {}
            payload = dict(payload)
            payload.setdefault('date', result_plan.get('date') or run_input.get('date'))
            if not pick(payload, *TRACK_KEYS):
                payload['tracks'] = result_plan.get('tracks') or run_input.get('tracks')
            if not pick(payload, *VENUE_KEYS):
                payload['venues'] = result_plan.get('venues')
            # 纯 token 签发时，乐观版本以草案生成时看到的现行版为准。
            if pick(payload, *BASE_KEYS) is None and result_plan.get('base_version') is not None:
                payload['base_version'] = result_plan['base_version']

    # 3) 重新最优排演（不信任客户端回传的 groups），排不下直接 409，零写入。
    #    若未显式给版本，则用草案 token 中记录的基准版本，保证纯 token 签发也乐观锁。
    if extract_base_version(payload, headers) is None and req_token:
        peek = _peek_result(user, req_token)
        peek_base = ((peek or {}).get('result') or {}).get('base_version')
        if peek_base is not None:
            payload = dict(payload)
            payload['base_version'] = peek_base
    plan = build_plan(conn, payload)
    date = plan['date']

    base = extract_base_version(payload, headers)
    if base is None:
        # 草案响应里带的 base_version / version 也作为乐观版本来源。
        base = as_int(pick(payload, 'draft_base_version'))

    # 4) 锁定每晚版本指针并做乐观校验。
    head = _ensure_head(conn, date)
    cur = int(head['current_version'])

    # 拿到锁后复查幂等：完全相同的签发若已被并发的首个请求提交，直接返回该版，
    # 避免重试/双击在版本检查处被误判为落后。
    locked_hit = None
    if code:
        locked_hit = _get_code_row(conn, code)
    if locked_hit is None and idem:
        locked_hit = _find_by(conn, rehearsal_plans.c.idempotency_key, idem)
    if locked_hit is None and req_token:
        locked_hit = _find_by(conn, rehearsal_plans.c.draft_token, req_token)
    if locked_hit is not None:
        return serialize(locked_hit, locked_hit['code'])

    if base is not None and base != cur:
        raise HTTPException(
            409,
            detail=('草案基于第 %d 版排演，现行排演已是第 %d 版；'
                    '三组未替换，落后的草案请按现行版退回重算后再签发'
                    % (base, cur)),
            headers={'X-Current-Version': str(cur),
                     'X-Base-Version': str(base)})

    new_version = cur + 1
    if not code:
        suffix = uuid4().hex[:8]
        safe_date = ''.join(ch for ch in date if ch.isalnum())[:16] or 'NIGHT'
        code = normalize_code('REH-%s-v%d-%s' % (safe_date, new_version, suffix))

    # code 在极端并发下可能已被占用：按幂等重放处理。
    clash = _get_code_row(conn, code)
    if clash:
        return serialize(clash, clash['code'])

    draft_token = req_token if req_token and not _find_by(
        conn, rehearsal_plans.c.draft_token, req_token) else None
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    row_values = {
        'code': code,
        'plan_date': date,
        'version': new_version,
        'base_version': cur,
        'status': 'issued',
        'groups': plan['groups'],
        'tracks': plan['tracks'],
        'venues': plan['venues'],
        'cost': plan['cost'],
        'snapshot': plan,
        'draft_token': draft_token,
        'idempotency_key': idem,
        'created_by': user['sub'],
        'created_at': now,
    }
    conn.execute(rehearsal_plans.insert().values(**row_values))
    conn.execute(rehearsal_heads.update().where(
        rehearsal_heads.c.plan_date == date).values(
        current_version=new_version, current_code=code,
        updated_by=user['sub'], updated_at=now))

    stored = _get_code_row(conn, code)
    return serialize(stored, code)


sign_rehearsal = issue_rehearsal
publish_rehearsal = issue_rehearsal
commit_rehearsal = issue_rehearsal
save_rehearsal = issue_rehearsal
submit_rehearsal = issue_rehearsal
change_rehearsal = issue_rehearsal


# ---------------------------------------------------------------------------
# 查询与序列化
# ---------------------------------------------------------------------------

def serialize(row, current_code=None):
    if row is None:
        return None
    snap = dict(row.get('snapshot') or {})
    code = row['code']
    is_current = (current_code == code) if current_code is not None else True
    cost = float(row.get('cost') or snap.get('cost') or 0.0)
    created_at = row.get('created_at')
    out = dict(snap)
    out.update({
        'id': row.get('id'),
        'code': code,
        'plan_code': code,
        'rehearsal_code': code,
        'date': row['plan_date'],
        'plan_date': row['plan_date'],
        'night': row['plan_date'],
        'version': row['version'],
        'revision': row['version'],
        'base_version': row.get('base_version'),
        'based_on_version': row.get('base_version'),
        'status': row.get('status') or 'issued',
        'state': 'current' if is_current else 'history',
        'stage': 'current' if is_current else 'superseded',
        'status_label': '现行排演' if is_current else '历次排演',
        'current': is_current,
        'is_current': is_current,
        'active': is_current,
        'signed': True,
        'issued': True,
        'groups': row.get('groups') or snap.get('groups'),
        'tracks': row.get('tracks') or snap.get('tracks'),
        'venues': row.get('venues') or snap.get('venues'),
        'cost': cost,
        'total_cost': cost,
        'total_distance': cost,
        'distance_total': cost,
        'distance_sum': cost,
        'score': cost,
        'pair_distance_total': cost,
        'ordered_distance_total': 2.0 * cost,
        'distance': round(cost, 4),
        'created_by': row.get('created_by'),
        'actor': row.get('created_by'),
        'issued_by': row.get('created_by'),
        'created_at': created_at.isoformat() if hasattr(created_at, 'isoformat') else created_at,
        'draft_token': row.get('draft_token'),
        'idempotency_key': row.get('idempotency_key'),
    })
    out.setdefault('feasible', True)
    out.setdefault('reason', None)
    out.setdefault('group_count', GROUP_COUNT)
    return out


def list_rehearsals(conn, date=None, limit=200):
    stmt = select(rehearsal_plans)
    if date:
        stmt = stmt.where(rehearsal_plans.c.plan_date == norm_date(date))
    stmt = stmt.order_by(
        rehearsal_plans.c.plan_date.desc(),
        rehearsal_plans.c.version.desc(),
        rehearsal_plans.c.id.desc()).limit(limit)
    rows = [dict(r) for r in conn.execute(stmt).mappings().all()]
    if date:
        head = conn.execute(select(rehearsal_heads).where(
            rehearsal_heads.c.plan_date == norm_date(date))).mappings().first()
        current_code = head['current_code'] if head else None
        return [serialize(row, current_code) for row in rows]
    heads = {h['plan_date']: h['current_code'] for h in
             conn.execute(select(rehearsal_heads)).mappings().all()}
    return [serialize(row, heads.get(row['plan_date'])) for row in rows]


def get_rehearsal(conn, code):
    row = _get_code_row(conn, code)
    if row is None:
        return None
    head = conn.execute(select(rehearsal_heads).where(
        rehearsal_heads.c.plan_date == row['plan_date'])).mappings().first()
    return serialize(row, head['current_code'] if head else row['code'])


def current_rehearsal(conn, date):
    date = norm_date(date)
    head = conn.execute(select(rehearsal_heads).where(
        rehearsal_heads.c.plan_date == date)).mappings().first()
    row = None
    if head and head['current_code']:
        row = _get_code_row(conn, head['current_code'])
    if row is None:
        row = conn.execute(
            select(rehearsal_plans).where(
                rehearsal_plans.c.plan_date == date).order_by(
                rehearsal_plans.c.version.desc())
        ).mappings().first()
        row = dict(row) if row else None
    if row is None:
        return None
    return serialize(row, head['current_code'] if head else row['code'])
