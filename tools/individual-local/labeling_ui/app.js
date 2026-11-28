'use strict';
// All page text is inserted with textContent only; nothing from the review data is parsed as HTML.
let token = location.hash.slice(1);
try {  // survive a reload without leaving the token in the visible address
  if (token) sessionStorage.setItem('labelToken', token); else token = sessionStorage.getItem('labelToken') || '';
} catch (e) { /* storage blocked: the full URL must be reopened after reload */ }
history.replaceState(null, '', '/');
const LABELS = {
  PAGE_VISIT: [['DIRECT', '직접 관련'], ['JUSTIFIED_DETOUR', '합리적 우회'], ['UNRELATED', '무관'], ['UNJUDGEABLE', '판단 불가']],
  WINDOW: [['NORMAL', 'NORMAL'], ['TRANSITION', 'TRANSITION'], ['DRIFT', 'DRIFT'], ['UNJUDGEABLE', '판단 불가']],
};
let state = null, mode = 'PAGE_VISIT', index = 0;
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? 'POST' : 'GET',
    headers: Object.assign({ 'X-Label-Token': token }, body ? { 'Content-Type': 'application/json' } : {}),
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.status);
  return data;
}

const tasks = () => state.tasks.filter((t) => t.targetType === mode);
const seconds = (ms) => (ms >= 60000 ? `${Math.floor(ms / 60000)}분 ${Math.round((ms % 60000) / 1000)}초` : `${Math.round(ms / 1000)}초`);

function pageCard(p, title) {
  const card = el('article', 'page');
  card.append(el('h3', null, title ? `${title} · ${p.title}` : p.title));
  const meta = [p.domain];
  if (p.isSearchResultPage) meta.push(`검색어: ${p.searchQuery}`);
  if (p.activeDurationMs != null) meta.push(`활성 체류 ${seconds(p.activeDurationMs)}`);
  card.append(el('div', 'meta', meta.join(' · ')));
  card.append(el('div', 'content', p.content));
  return card;
}

function render() {
  const list = tasks();
  const done = list.filter((t) => t.saved).length;
  $('progress').textContent = `${mode === 'PAGE_VISIT' ? '페이지' : 'Window'} ${done}/${list.length} 완료`;
  $('tab-page').setAttribute('aria-pressed', mode === 'PAGE_VISIT');
  $('tab-window').setAttribute('aria-pressed', mode === 'WINDOW');
  $('empty').hidden = list.length > 0;
  $('task').hidden = list.length === 0;
  if (!list.length) return;
  index = Math.max(0, Math.min(index, list.length - 1));
  const t = list[index];
  $('goal').textContent = t.goalText;
  const ctx = $('context'); ctx.replaceChildren();
  const pages = $('pages'); pages.replaceChildren(); pages.className = 'pages';
  if (t.targetType === 'PAGE_VISIT') {
    if (t.priorContext.length) {
      const box = el('div', 'context');
      box.append(el('div', null, `이전 방문 ${t.priorContext.length}개 (제목·검색어만)`));
      const ol = el('ol');
      t.priorContext.forEach((p) => ol.append(el('li', null, p.searchQuery ? `${p.title} — 검색: ${p.searchQuery}` : p.title)));
      box.append(ol); ctx.append(box);
    }
    pages.append(pageCard(t.page, `${t.position}번째 방문`));
  } else {
    t.pages.forEach((p, i) => pages.append(pageCard(p, `${i + 1}`)));
  }
  const fs = $('labels'); fs.replaceChildren();
  LABELS[t.targetType].forEach(([value, text], i) => {
    const lab = el('label'); const input = el('input'); input.type = 'radio'; input.name = 'label'; input.value = value; input.required = true;
    input.checked = t.saved && t.saved.label === value;
    lab.append(input, document.createTextNode(`${i + 1}. ${text}`)); fs.append(lab);
  });
  $('rationale').value = t.saved ? t.saved.rationale : '';
  $('status').textContent = t.saved ? '저장됨' : '미완료'; $('status').className = t.saved ? 'saved' : '';
  window.scrollTo(0, 0);
}

async function save(ev) {
  ev.preventDefault();
  const t = tasks()[index];
  const checked = document.querySelector('input[name="label"]:checked');
  if (!checked) { $('status').textContent = '라벨을 선택하세요'; $('status').className = 'error'; return; }
  try {
    t.saved = await api('/api/label', { taskId: t.taskId, label: checked.value, rationale: $('rationale').value });
    index += 1; render();
  } catch (e) { $('status').textContent = `저장 실패: ${e.message}`; $('status').className = 'error'; }
}

function skipToOpen() {
  const list = tasks(); const next = list.findIndex((t, i) => i > index && !t.saved);
  const first = list.findIndex((t) => !t.saved);
  index = next >= 0 ? next : (first >= 0 ? first : index); render();
}

$('form').addEventListener('submit', save);
$('prev').onclick = () => { index -= 1; render(); };
$('next').onclick = () => { index += 1; render(); };
$('skip').onclick = skipToOpen;
$('tab-page').onclick = () => { mode = 'PAGE_VISIT'; index = 0; render(); };
$('tab-window').onclick = () => { mode = 'WINDOW'; index = 0; render(); };
document.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.key === 'Enter') { $('form').requestSubmit(); return; }
  if (document.activeElement === $('rationale')) return;
  const n = Number(e.key);
  if (n >= 1 && n <= 4) { const r = document.querySelectorAll('input[name="label"]')[n - 1]; if (r) r.checked = true; }
});

api('/api/state').then((s) => { state = s; $('who').textContent = `평가자 ${s.rater} · 가이드 ${s.guide}`; render(); })
  .catch((e) => { $('notice').textContent = `불러오기 실패: ${e.message}. 터미널에 출력된 주소 전체로 다시 여세요.`; $('notice').className = 'error'; });
