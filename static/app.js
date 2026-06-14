/* ── State ──────────────────────────────────────────────────────────────── */
const S = {
  view:         'home',
  currentCard:  null,
  dueCount:     0,
  phase:        'front',   // 'front' | 'back' | 'echo'
  connections:  null,
  pendingCards: [],
  pendingMeta:  {},        // { title, content, source_type }
};

/* ── API ────────────────────────────────────────────────────────────────── */
async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

/* ── Router ─────────────────────────────────────────────────────────────── */
function navigate(view) {
  S.view = view;
  history.replaceState(null, '', '#' + view);
  document.querySelectorAll('.nav-links a').forEach(a => {
    a.classList.toggle('active', a.getAttribute('href') === '#' + view);
  });
  render();
}

function route() {
  const h = location.hash.slice(1) || 'home';
  navigate(h);
}

/* ── Root render ─────────────────────────────────────────────────────────── */
function render() {
  const app = document.getElementById('app');
  ({
    home:           () => renderHome(app),
    review:         () => renderReview(app),
    ingest:         () => renderIngest(app),
    'ingest-prev':  () => renderIngestPreview(app),
    cards:          () => renderCards(app),
  }[S.view] || (() => renderHome(app)))();
}

/* ── HOME ────────────────────────────────────────────────────────────────── */
async function renderHome(app) {
  app.innerHTML = loading();
  try {
    const stats = await api('GET', '/api/stats');
    app.innerHTML = `
      <h1 class="page-title">Memory</h1>
      <p class="page-sub">Your personal knowledge reinforcement system</p>

      <div class="stats-grid">
        <div class="stat-box"><div class="stat-val">${stats.due_today}</div><div class="stat-lbl">Due today</div></div>
        <div class="stat-box"><div class="stat-val">${stats.total_cards}</div><div class="stat-lbl">Total cards</div></div>
        <div class="stat-box"><div class="stat-val">${stats.total_sources}</div><div class="stat-lbl">Sources</div></div>
      </div>

      <div class="row">
        ${stats.due_today > 0
          ? `<button class="btn btn-primary btn-lg" onclick="navigate('review')">Start Review (${stats.due_today})</button>`
          : `<button class="btn btn-ghost btn-lg" disabled>Nothing due — great work!</button>`}
        <button class="btn btn-ghost btn-lg" onclick="navigate('ingest')">Add Content</button>
      </div>

      ${stats.total_cards === 0 ? `
        <div class="empty mt-lg">
          <h3>No cards yet</h3>
          <p>Paste something you've read and let the AI turn it into flashcards.</p>
        </div>` : ''}
    `;
  } catch (e) {
    app.innerHTML = alertEl(e.message, 'error');
  }
}

/* ── REVIEW ──────────────────────────────────────────────────────────────── */
async function renderReview(app) {
  if (S.currentCard && S.phase !== 'front') {
    paintReviewCard(app);
    return;
  }
  app.innerHTML = loading('Loading card…');
  try {
    const data = await api('GET', '/api/review/next');
    if (!data.card) {
      app.innerHTML = `
        <div class="empty">
          <h3>All done!</h3>
          <p>No cards due right now. Come back later or add more content.</p>
          <button class="btn btn-primary mt-md" onclick="navigate('home')">Back to Home</button>
        </div>`;
      return;
    }
    S.currentCard = data.card;
    S.dueCount    = data.due_count;
    S.phase       = 'front';
    S.connections = null;
    paintReviewCard(app);
  } catch (e) {
    app.innerHTML = alertEl(e.message, 'error');
  }
}

function paintReviewCard(app) {
  const card    = S.currentCard;
  const isBack  = S.phase === 'back' || S.phase === 'echo';
  const isEcho  = S.phase === 'echo';

  app.innerHTML = `
    <div class="progress-row">
      <span>${esc(card.source_title || 'Unknown source')}</span>
      <span>${S.dueCount} left today</span>
    </div>
    <div class="progress-bar"><div class="progress-fill" style="width:${Math.max(4, 100 - (S.dueCount / Math.max(S.dueCount, 1)) * 100)}%"></div></div>

    <div class="flashcard ${isBack ? 'revealed' : ''}">
      <div>
        <div class="card-label">${isBack ? 'Answer' : 'Question'}</div>
        <div class="card-text">${esc(isBack ? card.back : card.front)}</div>
        ${isBack ? `<div class="card-question-hint">${esc(card.front)}</div>` : ''}
      </div>
    </div>

    ${!isBack
      ? `<button class="btn btn-primary btn-full mt-md" onclick="showAnswer()">Show Answer</button>`
      : `<div class="rating-row">
           <button class="btn btn-again" onclick="rate(1)">Again</button>
           <button class="btn btn-hard"  onclick="rate(2)">Hard</button>
           <button class="btn btn-good"  onclick="rate(3)">Good</button>
           <button class="btn btn-easy"  onclick="rate(4)">Easy</button>
         </div>`}

    ${isEcho && S.connections ? echoPanel(S.connections) : ''}
  `;
}

function echoPanel(connections) {
  if (!connections?.length) return '';
  return `
    <div class="echo-panel">
      <div class="echo-header">Echoes from your notes</div>
      ${connections[0].insight ? `<div class="echo-insight">${esc(connections[0].insight)}</div>` : ''}
      ${connections.map(c => `
        <div class="echo-card">
          <div class="echo-front">${esc(c.card.front)}</div>
          <div class="echo-back">${esc(c.card.back)}</div>
        </div>`).join('')}
    </div>
    <button class="btn btn-primary btn-full mt-md" onclick="nextCard()">Next Card →</button>
  `;
}

function showAnswer() {
  S.phase = 'back';
  paintReviewCard(document.getElementById('app'));
}

async function rate(rating) {
  document.querySelectorAll('.rating-row button').forEach(b => b.disabled = true);
  try {
    const res = await api('POST', `/api/review/${S.currentCard.id}`, { rating });
    S.connections = res.connections;
    S.phase       = 'echo';
    if (res.connections?.length) {
      paintReviewCard(document.getElementById('app'));
    } else {
      nextCard();
    }
  } catch (e) {
    alert(e.message);
  }
}

function nextCard() {
  S.currentCard = null;
  S.phase       = 'front';
  S.connections = null;
  navigate('review');
}

/* ── INGEST ──────────────────────────────────────────────────────────────── */
function renderIngest(app) {
  app.innerHTML = `
    <h1 class="page-title">Add Content</h1>
    <p class="page-sub">Paste text you've read — AI extracts the key ideas as flashcards.</p>

    <div id="ingest-alert"></div>

    <div class="field">
      <label>Title / Source</label>
      <input id="t-title" type="text" placeholder="e.g. Thinking Fast and Slow, Ch.3" />
    </div>

    <div class="field">
      <label>Type</label>
      <select id="t-type" onchange="toggleType()">
        <option value="text">Paste text</option>
        <option value="url">URL (fetch article)</option>
      </select>
    </div>

    <div class="field" id="grp-text">
      <label>Content</label>
      <textarea id="t-content" rows="12" placeholder="Paste the text here…"></textarea>
    </div>

    <div class="field" id="grp-url" style="display:none">
      <label>URL</label>
      <input id="t-url" type="url" placeholder="https://…" />
    </div>

    <button class="btn btn-primary" id="extract-btn" onclick="extractCards()">Extract Cards</button>
  `;
}

function toggleType() {
  const isUrl = document.getElementById('t-type').value === 'url';
  document.getElementById('grp-text').style.display = isUrl ? 'none' : '';
  document.getElementById('grp-url').style.display  = isUrl ? '' : 'none';
}

async function extractCards() {
  const title = document.getElementById('t-title').value.trim();
  const type  = document.getElementById('t-type').value;
  const raw   = type === 'url'
    ? document.getElementById('t-url').value.trim()
    : document.getElementById('t-content').value.trim();

  clearAlert('ingest-alert');
  if (!title) { showAlert('ingest-alert', 'Please enter a title.', 'error'); return; }
  if (!raw)   { showAlert('ingest-alert', 'Please enter content.', 'error'); return; }

  const btn = document.getElementById('extract-btn');
  btn.disabled    = true;
  btn.textContent = 'Extracting…';

  try {
    const res = await api('POST', '/api/ingest/preview', { content: raw, title, source_type: type });
    S.pendingCards = res.cards;
    S.pendingMeta  = { title, content: res.content, source_type: type };
    navigate('ingest-prev');
  } catch (e) {
    showAlert('ingest-alert', e.message, 'error');
    btn.disabled    = false;
    btn.textContent = 'Extract Cards';
  }
}

/* ── INGEST PREVIEW ─────────────────────────────────────────────────────── */
function renderIngestPreview(app) {
  app.innerHTML = `
    <div class="row-between mb-md">
      <h1 class="page-title">Review Cards</h1>
      <button class="btn btn-ghost btn-sm" onclick="navigate('ingest')">← Back</button>
    </div>
    <p class="page-sub">Edit or remove cards before saving.</p>
    <div id="prev-alert"></div>
    <div id="prev-cards"></div>
    <div class="row mt-md">
      <button class="btn btn-primary" id="save-btn" onclick="saveCards()">Save ${S.pendingCards.length} Cards</button>
      <button class="btn btn-ghost" onclick="navigate('ingest')">Discard</button>
    </div>
  `;
  paintPreviews();
}

function paintPreviews() {
  const el = document.getElementById('prev-cards');
  if (!el) return;
  el.innerHTML = S.pendingCards.map((c, i) => `
    <div class="preview-card" id="pc-${i}">
      <div class="preview-card-hdr">
        <span class="preview-num">Card ${i + 1}</span>
        <button class="btn btn-danger btn-sm" onclick="removePreview(${i})">Remove</button>
      </div>
      <div class="field">
        <label>Front</label>
        <textarea rows="2" oninput="S.pendingCards[${i}].front=this.value">${esc(c.front)}</textarea>
      </div>
      <div class="field">
        <label>Back</label>
        <textarea rows="3" oninput="S.pendingCards[${i}].back=this.value">${esc(c.back)}</textarea>
      </div>
    </div>`).join('');
}

function removePreview(i) {
  S.pendingCards.splice(i, 1);
  if (!S.pendingCards.length) { navigate('ingest'); return; }
  const btn = document.getElementById('save-btn');
  if (btn) btn.textContent = `Save ${S.pendingCards.length} Cards`;
  paintPreviews();
}

async function saveCards() {
  const btn = document.getElementById('save-btn');
  btn.disabled    = true;
  btn.textContent = 'Saving…';
  try {
    await api('POST', '/api/ingest/save', { ...S.pendingMeta, cards: S.pendingCards });
    S.pendingCards = [];
    S.pendingMeta  = {};
    navigate('home');
  } catch (e) {
    showAlert('prev-alert', e.message, 'error');
    btn.disabled    = false;
    btn.textContent = `Save ${S.pendingCards.length} Cards`;
  }
}

/* ── LIBRARY ─────────────────────────────────────────────────────────────── */
async function renderCards(app) {
  app.innerHTML = loading();
  try {
    const data = await api('GET', '/api/cards?limit=200');
    if (!data.cards.length) {
      app.innerHTML = `
        <h1 class="page-title">Library</h1>
        <div class="empty">
          <h3>No cards yet</h3>
          <p>Add content to create your first cards.</p>
          <button class="btn btn-primary mt-md" onclick="navigate('ingest')">Add Content</button>
        </div>`;
      return;
    }
    app.innerHTML = `
      <div class="row-between mb-md">
        <h1 class="page-title">Library</h1>
        <span style="font-size:.8rem;color:var(--muted)">${data.total} cards</span>
      </div>
      <div id="card-list">
        ${data.cards.map(c => `
          <div class="card-row" id="cr-${c.id}">
            <div class="card-row-body">
              <div class="card-row-front">${esc(c.front)}</div>
              <div class="card-row-back">${esc(c.back)}</div>
              <div class="card-row-meta">${esc(c.source_title || 'Unknown')} · Due ${c.due_date} · ${c.interval}d interval</div>
            </div>
            <button class="btn btn-danger btn-sm" onclick="deleteCard(${c.id})">Delete</button>
          </div>`).join('')}
      </div>
    `;
  } catch (e) {
    app.innerHTML = alertEl(e.message, 'error');
  }
}

async function deleteCard(id) {
  if (!confirm('Delete this card?')) return;
  try {
    await api('DELETE', `/api/cards/${id}`);
    document.getElementById(`cr-${id}`)?.remove();
  } catch (e) {
    alert(e.message);
  }
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function esc(s) {
  return String(s ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function loading(msg = 'Loading…') {
  return `<div class="loading"><div class="spinner"></div>${msg}</div>`;
}
function alertEl(msg, type) {
  return `<div class="alert alert-${type}">${esc(msg)}</div>`;
}
function showAlert(id, msg, type) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = alertEl(msg, type);
}
function clearAlert(id) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = '';
}

/* ── Boot ────────────────────────────────────────────────────────────────── */
window.navigate    = navigate;
window.showAnswer  = showAnswer;
window.rate        = rate;
window.nextCard    = nextCard;
window.extractCards= extractCards;
window.toggleType  = toggleType;
window.saveCards   = saveCards;
window.removePreview = removePreview;
window.deleteCard  = deleteCard;
window.S           = S;

window.addEventListener('hashchange', route);
window.addEventListener('load', route);
