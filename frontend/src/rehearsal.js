import {request} from './api.js';
import {el, display} from './dom.js';
import {status} from './widgets.js';

function todayISO() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function fmtTime(value) {
  if (!value) return '';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

function groupCard(g) {
  return el('article', {class: 'rh-group', 'data-group': g.index},
    el('h4', {}, g.name + '（' + g.venues.length + ' 场地）'),
    el('div', {class: 'rh-venues'}, g.venues.map(v => el('span', {class: 'chip'}, v))),
    el('p', {class: 'rh-tracks'}, (g.tracks || []).join('、') || '—'),
    el('p', {class: 'rh-distance'}, '组内距离和 ' + display(g.distance)));
}

function historyCard(row) {
  return el('article', {class: 'record rh-version' + (row.current ? ' current' : ''),
      'data-version': row.version},
    el('h3', {}, '第 ' + row.version + ' 版 · ' + (row.current ? '现行排演' : '历次排演')),
    el('dl', {},
      el('dt', {}, '编号'), el('dd', {}, row.code),
      el('dt', {}, '签发人'), el('dd', {}, display(row.created_by)),
      el('dt', {}, '时间'), el('dd', {}, fmtTime(row.created_at)),
      el('dt', {}, '距离总和'), el('dd', {}, display(row.distance)),
      el('dt', {}, '三组'),
      el('dd', {}, el('div', {class: 'rh-mini'}, (row.groups || []).map(g =>
        el('span', {class: 'rh-mini-group'},
          g.name + '：' + (g.venues || []).join('/')))))));
}

export async function mountRehearsal(root, role) {
  const canPlan = role === 'operator' || role === 'reviewer';
  const canSign = role === 'reviewer';
  const state = {tracks: [], draft: null};

  const notice = status('');
  const draftBox = el('div', {class: 'rh-draft', 'aria-live': 'polite'});
  const historyBox = el('div', {class: 'records grid rh-history'});

  const dateInput = el('input', {type: 'date', name: 'date', value: todayISO(), required: ''});
  const selectAll = el('input', {type: 'checkbox', checked: '', 'aria-label': '全选已见证素材'});
  const materialsBox = el('fieldset', {class: 'rh-materials'},
    el('legend', {}, '已见证的试投素材'),
    el('label', {class: 'rh-check rh-all'}, selectAll, el('span', {}, '全选已见证素材（同场片段始终同组）')),
    el('div', {class: 'rh-checks'}, status('正在读取试投素材…')));

  const codeInput = el('input', {name: 'code', placeholder: '如 REH-20261125-V2', autocomplete: 'off'});
  const idemInput = el('input', {name: 'idempotency_key', placeholder: '重试可留空，或填固定幂等键', autocomplete: 'off'});
  const baseInput = el('input', {name: 'base_version', type: 'hidden', value: '0'});
  const tokenInput = el('input', {name: 'draft_token', type: 'hidden', value: ''});
  const signNotice = status('');
  const signButton = el('button', {type: 'submit'}, '签发草案（三组一起换版）');
  const signForm = el('form', {class: 'action rh-sign', id: 'sign_rehearsal'},
    el('h3', {}, '领班签发改排'),
    el('p', {class: 'rh-help'}, '只签发基于现行排演版本的草案；落后版本会被退回重算。同一编号或幂等键重试不会重复换版。'),
    baseInput, tokenInput,
    el('div', {class: 'fields'},
      el('label', {}, el('span', {}, '排演编号（幂等）'), codeInput),
      el('label', {}, el('span', {}, '幂等键（可选）'), idemInput)),
    signButton, signNotice);
  signForm.addEventListener('submit', onSign);

  const planButton = el('button', {type: 'submit'}, '排整晚分组');
  const planForm = el('form', {class: 'action rh-plan', id: 'plan_night'},
    el('h3', {}, '选日期与素材，排整晚三组'),
    el('p', {class: 'rh-help'}, '同场片段同组，每组一到三个场地，素材全部排入，组内拍点距离总和最小。排不下会说明原因，原排演照用。'),
    el('div', {class: 'fields'},
      el('label', {}, el('span', {}, '排演日期'), dateInput)),
    materialsBox,
    canPlan ? planButton : el('p', {class: 'status'}, '当前角色只能浏览，不能排演。'),
    notice);
  planForm.addEventListener('submit', onPlan);

  const panel = el('section', {class: 'ledger rehearsal', 'aria-label': '整晚分组排演'},
    el('h2', {}, '整晚联演分组与历次排演'),
    el('div', {class: 'rh-layout'},
      el('div', {class: 'rh-main'}, planForm, draftBox, canSign ? signForm : null),
      el('div', {class: 'rh-side'},
        el('div', {class: 'rh-history-head'},
          el('h3', {}, '历次排演'),
          el('button', {type: 'button', class: 'quiet rh-refresh'}, '刷新')),
        historyBox)));
  root.append(panel);

  panel.querySelector('.rh-refresh').addEventListener('click', loadHistory);
  dateInput.addEventListener('change', loadHistory);
  selectAll.addEventListener('change', () => {
    materialsBox.querySelectorAll('input[name="tracks"]:not(:disabled)')
      .forEach(cb => { cb.checked = selectAll.checked; });
  });

  async function loadTracks() {
    try {
      state.tracks = await request('/cue_tracks');
    } catch (error) {
      materialsBox.querySelector('.rh-checks').replaceChildren(status(error.message, 'error'));
      return;
    }
    const locked = state.tracks.filter(t => t.locked);
    const box = materialsBox.querySelector('.rh-checks');
    if (!locked.length) {
      box.replaceChildren(status('还没有已见证（锁定）的试投素材。'));
      return;
    }
    box.replaceChildren(...locked.map(t =>
      el('label', {class: 'rh-check', title: t.venue},
        el('input', {type: 'checkbox', name: 'tracks', value: t.code, checked: ''}),
        el('span', {}, t.code + ' · ' + t.venue + ' · ' + (t.timings || []).length + ' 拍'))));
    selectAll.checked = true;
  }

  function selectedTracks() {
    return [...materialsBox.querySelectorAll('input[name="tracks"]:checked')].map(i => i.value);
  }

  async function runPlan() {
    const date = dateInput.value;
    const tracks = selectedTracks();
    if (!date) throw new Error('请选择排演日期');
    if (!tracks.length) throw new Error('请至少选择一条已见证的试投素材');
    return request('/cue_clusters/plan-night', {date, tracks});
  }

  function renderDraft(draft, staleNote) {
    state.draft = draft;
    baseInput.value = String(draft.base_version ?? 0);
    tokenInput.value = draft.draft_token || draft.token || '';
    if (canSign) signForm.style.display = '';
    draftBox.replaceChildren(
      el('div', {class: 'rh-draft-head'},
        el('h3', {}, '最优草案 · 基于现行第 ' + (draft.base_version ?? 0) + ' 版'),
        el('p', {class: 'rh-total'}, '组内拍点距离总和最小：' + display(draft.distance ?? draft.cost))),
      staleNote ? status(staleNote, 'error') : null,
      el('div', {class: 'rh-groups'}, (draft.groups || []).map(groupCard)));
  }

  async function onPlan(event) {
    event.preventDefault();
    planButton.disabled = true;
    notice.className = 'status';
    notice.textContent = '正在逐条比对拍点并求最优分组…';
    try {
      const draft = await runPlan();
      renderDraft(draft);
      notice.textContent = '草案已生成，可由复核（领班）签发。';
      notice.classList.add('ok');
    } catch (error) {
      state.draft = null;
      draftBox.replaceChildren();
      if (canSign) signForm.style.display = 'none';
      notice.textContent = error.message;
      notice.classList.add('error');
    } finally {
      planButton.disabled = false;
    }
  }

  async function onSign(event) {
    event.preventDefault();
    if (!state.draft) {
      signNotice.textContent = '请先生成草案再签发。';
      signNotice.className = 'status error';
      return;
    }
    signButton.disabled = true;
    signNotice.className = 'status';
    signNotice.textContent = '正在签发…';
    const body = {
      date: dateInput.value,
      tracks: state.draft.tracks,
      base_version: state.draft.base_version ?? 0,
      draft_token: state.draft.draft_token || state.draft.token || ''
    };
    if (codeInput.value.trim()) body.code = codeInput.value.trim();
    if (idemInput.value.trim()) body.idempotency_key = idemInput.value.trim();
    try {
      const saved = await request('/cue_clusters/sign-rehearsal', body);
      signNotice.textContent = '已签发第 ' + saved.version + ' 版，三组一起换版；重复提交不会再次换版。';
      signNotice.classList.add('ok');
      codeInput.value = saved.code || codeInput.value;
      await loadHistory();
      const cur = historyBox.querySelector('[data-version="' + saved.version + '"]');
      if (cur) cur.classList.add('flash');
    } catch (error) {
      signNotice.textContent = error.message;
      signNotice.classList.add('error');
      if (String(error.message).includes('现行排演已是第')) {
        // 落后的草案：按现行排演自动退回重算。
        try {
          const fresh = await runPlan();
          renderDraft(fresh, '原草案落后，已按现行第 ' + fresh.base_version + ' 版退回重算，请确认后重新签发。');
        } catch (replanError) {
          draftBox.replaceChildren(status(replanError.message, 'error'));
        }
      }
    } finally {
      signButton.disabled = false;
    }
  }

  async function loadHistory() {
    const date = dateInput.value;
    if (!date) return;
    try {
      const rows = await request('/cue_clusters/rehearsals?date=' + encodeURIComponent(date));
      if (!rows.length) {
        historyBox.replaceChildren(status('该日期还没有已签发排演；首次签发即为第 1 版。'));
        return;
      }
      historyBox.replaceChildren(...rows.map(historyCard));
    } catch (error) {
      historyBox.replaceChildren(status(error.message, 'error'));
    }
  }

  if (canSign) signForm.style.display = 'none';
  await Promise.all([loadTracks(), loadHistory()]);
}
