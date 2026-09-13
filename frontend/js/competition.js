(async function () {
  const user = requireSession(['leader', 'member']);
  if (!user) return;

  const flashHost = document.getElementById('flashHost');

  let state = null;          // { cases, locked, result }
  let activeCaseIdx = 0;
  let activeQuestionId = null;
  let activeEvidenceTab = 'overview';
  let initialCaseApplied = false; // applies ?case=<id> from the dashboard only once
  const pendingSaves = new Set(); // questionIds currently being saved, to avoid double posts

  // ==========================================================================
  // Overall 45-minute assessment countdown (client-side, persists across
  // page reloads via localStorage, so refreshing does not reset the clock).
  // ==========================================================================
  const ASSESSMENT_DURATION_MS = 45 * 60 * 1000;
  const TIMER_STORAGE_KEY = 'cybertrace_assessment_timer_start';

  function startAssessmentTimer() {
    const timerEl = document.getElementById('assessmentTimer');
    if (!timerEl) return;

    let startedAt = Number(localStorage.getItem(TIMER_STORAGE_KEY));
    if (!startedAt) {
      startedAt = Date.now();
      localStorage.setItem(TIMER_STORAGE_KEY, String(startedAt));
    }
    const endsAt = startedAt + ASSESSMENT_DURATION_MS;
    let intervalId = null;

    function tick() {
      const remainingMs = endsAt - Date.now();
      if (remainingMs <= 0) {
        timerEl.textContent = '00:00';
        timerEl.classList.add('timer-expired');
        if (intervalId) clearInterval(intervalId);
        return;
      }
      const totalSeconds = Math.floor(remainingMs / 1000);
      const mins = Math.floor(totalSeconds / 60);
      const secs = totalSeconds % 60;
      timerEl.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
      timerEl.classList.toggle('timer-warning', remainingMs <= 5 * 60 * 1000);
    }

    tick();
    intervalId = setInterval(tick, 1000);
  }

  // ==========================================================================
  // Load assessment state
  // ==========================================================================
  async function load() {
    try {
      state = await Api.get('/api/team/assessment/state');
    } catch (err) {
      flash(flashHost, err.message, 'error');
      return;
    }
    if (state.locked && state.result) {
      renderResult(state.result);
      return;
    }
    document.getElementById('resultBody').classList.add('hidden');
    document.getElementById('assessmentBody').classList.remove('hidden');
    if (!state.cases.length) {
      document.getElementById('questionsHost').innerHTML = '<div class="flash error">No cases are configured for this assessment yet.</div>';
      return;
    }

    // Jump straight to the case the team chose via the "Enter Investigation"
    // button on the dashboard (/competition.html?case=<caseId>), on first load only.
    if (!initialCaseApplied) {
      initialCaseApplied = true;
      const requestedCaseId = Number(new URLSearchParams(window.location.search).get('case'));
      const idx = state.cases.findIndex((c) => c.id === requestedCaseId);
      if (idx !== -1) activeCaseIdx = idx;
    }

    if (activeQuestionId === null && state.cases[activeCaseIdx] && state.cases[activeCaseIdx].questions.length) {
      activeQuestionId = state.cases[activeCaseIdx].questions[0].id;
    }
    renderAll();
    refreshValidation();
    updateHintPenaltyDisplay();
  }

  function totalAnswered() {
    let answered = 0, total = 0;
    state.cases.forEach((c) => c.questions.forEach((q) => { total++; if (q.selectedOption !== null && q.selectedOption !== undefined) answered++; }));
    return { answered, total };
  }

  function renderAll() {
    const { answered, total } = totalAnswered();
    document.getElementById('answeredCount').textContent = `${answered}/${total}`;
    document.getElementById('progressCount').textContent = `${answered} / ${total} answered`;
    document.getElementById('progressFill').style.width = total ? `${Math.round((answered / total) * 100)}%` : '0%';
    renderCaseTabs();
    renderQuestionNav();
    renderQuestions();
  }

  // ==========================================================================
  // Case tabs
  // ==========================================================================
  function renderCaseTabs() {
    const host = document.getElementById('caseTabs');
    host.innerHTML = state.cases.map((c, i) => {
      const total = c.questions.length;
      const answered = c.questions.filter((q) => q.selectedOption !== null && q.selectedOption !== undefined).length;
      const pct = total ? Math.round((answered / total) * 100) : 0;
      const complete = total > 0 && answered === total;
      return `
      <div class="case-tab ${i === activeCaseIdx ? 'active' : ''} ${complete ? 'complete' : ''}" data-case-idx="${i}">
        <div class="case-tab-code">${escapeHtml(c.case_code)} · Case ${i + 1}</div>
        <div class="case-tab-title">${escapeHtml(c.title)}</div>
        <div class="case-tab-progress"><div class="fill" style="width:${pct}%;"></div></div>
        <div style="font-size:.72rem; color:var(--text-faint); margin-top:6px;">${answered}/${total} answered · ${c.max_score} pts</div>
      </div>`;
    }).join('');
    host.querySelectorAll('[data-case-idx]').forEach((el) =>
      el.addEventListener('click', () => {
        activeCaseIdx = Number(el.dataset.caseIdx);
        activeEvidenceTab = 'overview';
        const c = state.cases[activeCaseIdx];
        activeQuestionId = c.questions.length ? c.questions[0].id : null;
        renderAll();
      })
    );
  }

  // ==========================================================================
  // Question navigator (numbered circles, current case only)
  // ==========================================================================
  function renderQuestionNav() {
    const host = document.getElementById('qnav');
    const c = state.cases[activeCaseIdx];
    host.innerHTML = c.questions.map((q, i) => {
      const answered = q.selectedOption !== null && q.selectedOption !== undefined;
      const current = q.id === activeQuestionId;
      return `<div class="qnav-item ${answered ? 'answered' : ''} ${current ? 'current' : ''}" data-qid="${q.id}" title="Question ${i + 1}">${i + 1}</div>`;
    }).join('');
    host.querySelectorAll('[data-qid]').forEach((el) =>
      el.addEventListener('click', () => { activeQuestionId = Number(el.dataset.qid); renderQuestionNav(); renderQuestions(); })
    );
  }

  // ==========================================================================
  // Questions — all questions in the active case are shown, in order, with
  // the current one anchored; this satisfies "move between questions" while
  // still letting a team see/jump to any question in the case at a glance.
  // ==========================================================================
  // ==========================================================================
  // Evidence viewer — ported from the original investigation console design
  // (same .evidence-tab / .evidence-card / .console-block classes), now
  // sourced from /assessment/state instead of the old per-case endpoint.
  // ==========================================================================
  const EVIDENCE_TAB_LABELS = {
    overview: '📋 Overview', email: '📧 Emails', browser: '🌐 Browser History',
    login: '🔑 Login Records', chat: '💬 Chat / Calls', transaction: '💳 Transactions',
    document: '📄 Documents', forensic: '🔬 Forensic Lab', suspect: '🕵️ Suspects',
  };
  const EVIDENCE_TAB_ORDER = ['overview', 'email', 'browser', 'login', 'chat', 'transaction', 'document', 'forensic', 'suspect'];

  function caseEvidenceTabs(c) {
    const present = new Set(Object.keys(c.evidence || {}));
    return EVIDENCE_TAB_ORDER.filter((key) => key === 'overview' || key === 'suspect' || present.has(key));
  }

  function renderEvidenceTabs(c) {
    const tabs = caseEvidenceTabs(c);
    if (!tabs.includes(activeEvidenceTab)) activeEvidenceTab = 'overview';
    return `<div class="evidence-tabs">${tabs.map((key) =>
      `<div class="evidence-tab ${key === activeEvidenceTab ? 'active' : ''}" data-evidence-tab="${key}">${EVIDENCE_TAB_LABELS[key]}</div>`
    ).join('')}</div>`;
  }

  function renderEvidencePanel(c) {
    if (activeEvidenceTab === 'overview') {
      return `
      <div class="evidence-card">
        <div class="meta">Victim</div><b>${escapeHtml(c.victim_name || 'Unknown')}</b>
        <p style="margin:6px 0 0;">Financial loss: ₹${c.financial_loss ?? '—'}</p>
      </div>
      <div class="evidence-card">
        <div class="meta">Case Description</div>
        <p style="margin:0;">${escapeHtml(c.description || '')}</p>
      </div>
      <p style="font-size:.8rem; color:var(--text-dim); margin-top:10px;">Use the tabs above to review emails, browser history, login records, chats, transactions, documents, and forensic evidence — then answer the questions below.</p>`;
    }
    if (activeEvidenceTab === 'suspect') {
      const suspects = c.suspects || [];
      if (!suspects.length) return `<p style="font-size:.82rem; color:var(--text-faint);">No suspects on file for this case.</p>`;
      return suspects.map((s) => `
        <div class="evidence-card">
          <div class="meta">${escapeHtml(s.role || '')}</div>
          <b>${escapeHtml(s.name)}</b>
          <p style="margin:6px 0 0;">${escapeHtml(s.description || '')}</p>
        </div>`).join('');
    }
    if (activeEvidenceTab === 'forensic') {
      const items = (c.evidence && c.evidence.forensic) || [];
      const cards = items.map((item) => renderEvidenceCard('forensic', item.title, item.content)).join('');
      return cards + renderForensicTools();
    }
    const items = (c.evidence && c.evidence[activeEvidenceTab]) || [];
    if (!items.length) return `<p style="font-size:.82rem; color:var(--text-faint);">No ${escapeHtml(EVIDENCE_TAB_LABELS[activeEvidenceTab] || activeEvidenceTab)} evidence for this case.</p>`;
    return items.map((item) => renderEvidenceCard(activeEvidenceTab, item.title, item.content)).join('');
  }

  function renderEvidenceCard(type, title, c) {
    if (type === 'email') {
      return `<div class="evidence-card ${c.suspicious ? 'suspicious' : ''}">
        <div class="meta">From: ${escapeHtml(c.from)} · ${escapeHtml(c.time)}</div>
        <b>${escapeHtml(c.subject)}</b>
        <p style="margin:6px 0;">${escapeHtml(c.body)}</p>
        ${c.link ? `<div class="console-block">${escapeHtml(c.link)}</div>` : ''}
        ${c.suspicious ? '<span class="badge badge-danger" style="margin-top:6px; display:inline-block;">Flagged suspicious</span>' : ''}
      </div>`;
    }
    if (type === 'login') {
      return `<div class="evidence-card">
        <div class="meta">${escapeHtml(c.time)} · ${escapeHtml(c.device)} · ${escapeHtml(c.location)}</div>
        <span class="badge ${c.status === 'Success' ? 'badge-primary' : 'badge-danger'}">${escapeHtml(c.status)}</span>
      </div>`;
    }
    if (type === 'browser') {
      return `<div class="evidence-card"><div class="meta">${escapeHtml(c.time)}</div><div class="console-block">${escapeHtml(c.url)}</div></div>`;
    }
    if (type === 'chat') {
      return `<div class="evidence-card"><div class="meta">${escapeHtml(c.time)}</div>
        <p><b>Person A:</b> ${escapeHtml(c.person_a)}</p><p><b>Person B:</b> ${escapeHtml(c.person_b)}</p></div>`;
    }
    if (type === 'transaction') {
      return `<div class="evidence-card"><div class="meta">${escapeHtml(c.time)}</div>
        ₹${c.amount} → ${escapeHtml(c.to_account)} <span class="badge badge-primary">${escapeHtml(c.status)}</span></div>`;
    }
    if (type === 'document') {
      return `<div class="evidence-card"><b>${escapeHtml(c.file_name)}</b> (${escapeHtml(c.file_type)}, ${c.size_kb}KB)
        <div class="meta">Created ${escapeHtml(c.created)} · Modified ${escapeHtml(c.modified)} · Author: ${escapeHtml(c.author)}</div></div>`;
    }
    if (type === 'forensic') {
      if (c.type === 'base64') return `<div class="evidence-card"><div class="meta">Base64 fragment</div><div class="console-block">${escapeHtml(c.encoded)}</div></div>`;
      if (c.type === 'hash') return `<div class="evidence-card"><div class="meta">Hash record</div><div class="console-block">expected: ${escapeHtml(c.expected_hash)}\nevidence: ${escapeHtml(c.evidence_hash)}</div></div>`;
    }
    return `<div class="evidence-card"><pre>${escapeHtml(JSON.stringify(c, null, 2))}</pre></div>`;
  }

  function renderForensicTools() {
    return `
      <div class="qa-block">
        <h4>🧪 Base64 Decoder</h4>
        <input id="b64Input" placeholder="Paste base64 string…" />
        <button class="btn btn-sm" id="b64Btn">Decode</button>
        <div id="b64Result" class="console-block" style="margin-top:8px; display:none;"></div>
      </div>
      <div class="qa-block">
        <h4>🔐 Hash Verifier</h4>
        <input id="hashExpected" placeholder="Expected hash" />
        <input id="hashEvidence" placeholder="Evidence hash" />
        <button class="btn btn-sm" id="hashBtn">Compare</button>
        <div id="hashResult" style="margin-top:8px;"></div>
      </div>`;
  }

  function wireForensicTools() {
    const b64Btn = document.getElementById('b64Btn');
    if (b64Btn) b64Btn.addEventListener('click', async () => {
      try {
        const { decoded } = await Api.post('/api/team/forensic/decode', { text: document.getElementById('b64Input').value });
        const r = document.getElementById('b64Result');
        r.style.display = 'block';
        r.textContent = decoded;
      } catch (err) { flash(flashHost, err.message, 'error'); }
    });
    const hashBtn = document.getElementById('hashBtn');
    if (hashBtn) hashBtn.addEventListener('click', async () => {
      try {
        const { match } = await Api.post('/api/team/forensic/hash-verify', {
          expectedHash: document.getElementById('hashExpected').value,
          evidenceHash: document.getElementById('hashEvidence').value,
        });
        document.getElementById('hashResult').innerHTML = match ? '<span class="result-ok">✔ Hashes match</span>' : '<span class="result-bad">✘ Hashes do not match</span>';
      } catch (err) { flash(flashHost, err.message, 'error'); }
    });
  }

  function renderQuestions() {
    const host = document.getElementById('questionsHost');
    const c = state.cases[activeCaseIdx];
    host.innerHTML = `
      <div style="margin-bottom:14px;">
        <div class="card-title" style="margin-bottom:2px;">${escapeHtml(c.case_code)} — ${escapeHtml(c.title)}</div>
        <p style="margin:0;">${escapeHtml(c.description || '')}</p>
      </div>
      ${renderEvidenceTabs(c)}
      <div id="evidencePanel">${renderEvidencePanel(c)}</div>
      <div class="qa-block">
        <h4>📝 Questions</h4>
        ${c.questions.map((q, i) => renderQuestion(c, q, i)).join('')}
      </div>
      ${renderHints(c)}
      <div style="display:flex; justify-content:space-between; margin-top:18px;">
        <button class="btn btn-sm" id="prevCaseBtn" ${activeCaseIdx === 0 ? 'disabled' : ''}>← Previous Case</button>
        <button class="btn btn-sm btn-primary" id="nextCaseBtn" ${activeCaseIdx === state.cases.length - 1 ? 'disabled' : ''}>Next Case →</button>
      </div>
    `;

    host.querySelectorAll('[data-evidence-tab]').forEach((el) =>
      el.addEventListener('click', () => { activeEvidenceTab = el.dataset.evidenceTab; renderQuestions(); })
    );
    wireForensicTools();
    host.querySelectorAll('[data-select-option]').forEach((el) =>
      el.addEventListener('click', () => selectOption(Number(el.dataset.questionId), Number(el.dataset.optionIndex)))
    );
    host.querySelectorAll('[data-reveal-hint]').forEach((el) =>
      el.addEventListener('click', () => revealHint(Number(el.dataset.revealHint)))
    );
    const prevBtn = document.getElementById('prevCaseBtn');
    const nextBtn = document.getElementById('nextCaseBtn');
    if (prevBtn) prevBtn.addEventListener('click', () => { activeCaseIdx = Math.max(0, activeCaseIdx - 1); activeEvidenceTab = 'overview'; activeQuestionId = state.cases[activeCaseIdx].questions[0]?.id ?? null; renderAll(); });
    if (nextBtn) nextBtn.addEventListener('click', () => { activeCaseIdx = Math.min(state.cases.length - 1, activeCaseIdx + 1); activeEvidenceTab = 'overview'; activeQuestionId = state.cases[activeCaseIdx].questions[0]?.id ?? null; renderAll(); });

    // Scroll the active question into view within the case.
    const anchor = host.querySelector(`[data-question-anchor="${activeQuestionId}"]`);
    if (anchor) anchor.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function renderQuestion(c, q, i) {
    const answered = q.selectedOption !== null && q.selectedOption !== undefined;
    return `
    <div class="mcq-question" data-question-anchor="${q.id}">
      <div class="mcq-question-head">
        <b>Q${i + 1}. ${escapeHtml(q.question)}</b>
        <span class="badge ${answered ? 'badge-primary' : 'badge-secondary'}">${q.marks} pts</span>
      </div>
      <div class="mcq-options">
        ${q.options.map((opt, idx) => `
          <label class="mcq-option ${q.selectedOption === idx ? 'selected' : ''}" data-question-id="${q.id}" data-option-index="${idx}" data-select-option>
            <input type="radio" name="q_${q.id}" value="${idx}" ${q.selectedOption === idx ? 'checked' : ''} />
            <span>${escapeHtml(opt)}</span>
          </label>`).join('')}
      </div>
    </div>`;
  }

  function renderHints(c) {
    if (!c.hints || !c.hints.length) return '';
    return `
    <div class="qa-block">
      <h4>💡 Case Hints</h4>
      <p style="margin:-4px 0 10px; font-size:.8rem;">Optional — each hint costs points once revealed. Hints never show the correct answer, just a pointer to the right evidence.</p>
      <div style="display:flex; flex-direction:column; gap:8px;">
        ${c.hints.map((h) => h.revealed
          ? `<div class="flash info">💡 ${escapeHtml(h.hintText)} <small>(−${h.penalty} pts)</small></div>`
          : `<button class="btn btn-sm" data-reveal-hint="${h.id}" style="align-self:flex-start;">💡 Reveal ${escapeHtml(h.round_name || 'case')} hint (−${h.penalty} pts)</button>`
        ).join('')}
      </div>
    </div>`;
  }

  async function revealHint(hintId) {
    try {
      const result = await Api.post('/api/team/assessment/hint', { hintId });
      const c = state.cases[activeCaseIdx];
      const h = c.hints.find((hh) => hh.id === hintId);
      if (h) { h.revealed = true; h.hintText = result.hintText; }
      state.hintPenalty = result.totalHintPenalty;
      renderQuestions();
      updateHintPenaltyDisplay();
    } catch (err) { flash(flashHost, err.message, 'error'); }
  }

  function updateHintPenaltyDisplay() {
    const el = document.getElementById('hintPenaltyNote');
    if (!el) return;
    el.textContent = state.hintPenalty ? `Hint penalty so far: −${state.hintPenalty} pts` : '';
  }

  async function selectOption(questionId, optionIndex) {
    const c = state.cases[activeCaseIdx];
    const q = c.questions.find((qq) => qq.id === questionId);
    if (!q || pendingSaves.has(questionId)) return;
    const previous = q.selectedOption;
    q.selectedOption = optionIndex; // optimistic UI update — user can change their mind freely before submission
    renderQuestions();
    renderQuestionNav();
    renderCaseTabs();
    pendingSaves.add(questionId);
    try {
      await Api.post('/api/team/assessment/answer', { questionId, selectedOption: optionIndex });
      const { answered, total } = totalAnswered();
      document.getElementById('answeredCount').textContent = `${answered}/${total}`;
      document.getElementById('progressCount').textContent = `${answered} / ${total} answered`;
      document.getElementById('progressFill').style.width = total ? `${Math.round((answered / total) * 100)}%` : '0%';
      refreshValidation();
    } catch (err) {
      q.selectedOption = previous; // roll back on failure
      renderQuestions();
      renderQuestionNav();
      renderCaseTabs();
      flash(flashHost, err.message, 'error');
    } finally {
      pendingSaves.delete(questionId);
    }
  }

  // ==========================================================================
  // Validation + Final Submission
  // ==========================================================================
  async function refreshValidation() {
    let v;
    try { v = await Api.get('/api/team/assessment/validate'); } catch (_) { return; }
    const box = document.getElementById('validationBox');
    const btn = document.getElementById('finalSubmitBtn');
    if (v.complete) {
      box.innerHTML = `<div class="flash success">All ${v.totalQuestions} questions answered — ready for final submission.</div>`;
      btn.disabled = false;
    } else {
      box.innerHTML = `
        <div class="flash error">${v.missing.length} question(s) still need an answer:</div>
        <ul class="missing-list">
          ${v.missing.map((m) => `<li data-jump-case="${m.caseId}" data-jump-question="${m.questionId}">${escapeHtml(m.caseCode)} — ${escapeHtml(m.question)}</li>`).join('')}
        </ul>`;
      box.querySelectorAll('[data-jump-question]').forEach((el) =>
        el.addEventListener('click', () => {
          const caseIdx = state.cases.findIndex((c) => c.id === Number(el.dataset.jumpCase));
          if (caseIdx === -1) return;
          activeCaseIdx = caseIdx;
          activeQuestionId = Number(el.dataset.jumpQuestion);
          renderAll();
        })
      );
      btn.disabled = true;
    }
  }

  document.getElementById('finalSubmitBtn').addEventListener('click', async () => {
    const v = await Api.get('/api/team/assessment/validate').catch(() => null);
    if (!v || !v.complete) { flash(flashHost, 'Please answer every question before submitting.', 'error'); refreshValidation(); return; }
    if (!confirm('Submit the final assessment now? You will not be able to change any answers afterward.')) return;
    try {
      const result = await Api.post('/api/team/assessment/submit-final');
      state.locked = true;
      state.result = result;
      renderResult(result);
    } catch (err) {
      flash(flashHost, typeof err.message === 'string' ? err.message : 'Could not submit the assessment.', 'error');
    }
  });

  // ==========================================================================
  // Result screen
  // ==========================================================================
  const RATING_COLOR = {
    Excellent: 'badge-primary', Good: 'badge-primary', Satisfactory: 'badge-warning',
    'Needs Improvement': 'badge-warning', Unsatisfactory: 'badge-danger',
  };

  function renderResult(result) {
    document.getElementById('assessmentBody').classList.add('hidden');
    const host = document.getElementById('resultBody');
    host.classList.remove('hidden');
    host.innerHTML = `
      <div class="card result-hero">
        <div style="text-transform:uppercase; letter-spacing:.08em; font-size:.78rem; color:var(--text-faint);">Assessment Completed</div>
        <div class="final-num">${result.finalScore}<small> / 100</small></div>
        <div style="color:var(--text-dim); margin-top:6px;">${result.percentage}%</div>
        <span class="badge ${RATING_COLOR[result.rating] || 'badge-secondary'} rating-badge">${escapeHtml(result.rating)}</span>
        <table class="case-score-table">
          <thead><tr><th>Case</th><th>Score</th><th>Max</th></tr></thead>
          <tbody>
            ${result.caseScores.map((c) => `<tr><td>${escapeHtml(c.case_code)} — ${escapeHtml(c.title)}</td><td>${c.score}</td><td>${c.max_score}</td></tr>`).join('')}
            <tr style="font-weight:600;"><td>Combined${result.hintPenalty ? ` (after −${result.hintPenalty} hint penalty)` : ''}</td><td>${result.rawTotal}</td><td>${result.rawMax}</td></tr>
          </tbody>
        </table>
        <p style="margin-top:14px; font-size:.8rem;">Submitted ${escapeHtml(new Date(result.submittedAt).toLocaleString())} · Status: <b style="color:var(--primary);">Submitted</b></p>
        <button class="btn btn-sm" id="retakeBtn" style="margin-top:10px;">↺ Retake Assessment</button>
      </div>`;
    document.getElementById('retakeBtn').addEventListener('click', async () => {
      if (!confirm('This clears all your saved answers and this result so you can attempt the assessment again. Continue?')) return;
      try {
        await Api.post('/api/team/assessment/retake');
        activeCaseIdx = 0;
        activeQuestionId = null;
        await load();
      } catch (err) { flash(flashHost, err.message, 'error'); }
    });
  }

  // ==========================================================================
  // Investigation Session — explicit-consent camera/microphone/screen
  // sharing to the authorized event panel, via the existing WebSocket +
  // WebRTC signaling (session:start/stop/signal). Nothing is shared until
  // the team explicitly starts a session, and it can be stopped any time.
  // ==========================================================================
  const socket = createSocket();
  const RTC_CONFIG = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] };
  let sessionStream = null;      // camera/mic combined stream
  let sessionScreenStream = null; // separate screen-share stream
  let sessionActive = false;
  const sessionPeers = new Map();

  function mediaErrorMessage(err) {
    switch (err && err.name) {
      case 'NotAllowedError':
      case 'PermissionDeniedError':
        return 'Permission denied — check your browser/OS permission settings and try again.';
      case 'NotFoundError':
      case 'DevicesNotFoundError':
        return 'No matching device found on this computer.';
      case 'NotReadableError':
      case 'TrackStartError':
        return 'The device is already in use by another app.';
      case 'OverconstrainedError':
        return 'No device satisfies the requested constraints.';
      case 'SecurityError':
        return 'Blocked by browser security policy (this page must be served over HTTPS or from localhost).';
      case 'AbortError':
        return 'Request was cancelled.';
      default:
        return err && err.message ? err.message : 'Could not access the device.';
    }
  }

  function mediaSupportError() {
    if (window.isSecureContext === false) {
      return 'This page is not running in a secure context. Camera/microphone/screen access requires HTTPS (or http://localhost during local development).';
    }
    if (!navigator.mediaDevices) {
      return 'This browser does not expose media device APIs on this page.';
    }
    return null;
  }

  (function checkMediaSupportUpfront() {
    const problem = mediaSupportError();
    const warnEl = document.getElementById('sessionSupportWarning');
    if (!problem) { warnEl.innerHTML = ''; return; }
    warnEl.innerHTML = `<div class="flash error">${escapeHtml(problem)}</div>`;
    document.getElementById('sessionStartBtn').disabled = true;
  })();

  function setSessionStatusUI(active) {
    const badge = document.getElementById('sessionStatusBadge');
    badge.textContent = active ? 'ACTIVE' : 'INACTIVE';
    badge.className = `badge ${active ? 'badge-primary' : 'badge-secondary'}`;
    document.getElementById('sessionPrivacyNotice').classList.toggle('hidden', !active);
    document.getElementById('sessionStartBtn').classList.toggle('hidden', active);
    document.getElementById('sessionStopBtn').classList.toggle('hidden', !active);
    document.getElementById('sessionConsent').disabled = active;
    document.getElementById('sessionCamera').disabled = active;
    document.getElementById('sessionMic').disabled = active;
    document.getElementById('sessionScreen').disabled = active;
  }
  setSessionStatusUI(false);

  document.getElementById('sessionStartBtn').addEventListener('click', async () => {
    const problem = mediaSupportError();
    if (problem) { flash(flashHost, problem, 'error'); return; }

    const consent = document.getElementById('sessionConsent').checked;
    const wantCamera = document.getElementById('sessionCamera').checked;
    const wantMic = document.getElementById('sessionMic').checked;
    const wantScreen = document.getElementById('sessionScreen').checked;
    if (!consent) { flash(flashHost, 'Please check the consent box before starting a session.', 'error'); return; }
    if (!wantCamera && !wantMic && !wantScreen) { flash(flashHost, 'Select at least one of camera, microphone, or screen to share.', 'error'); return; }

    if (wantScreen && (!navigator.mediaDevices.getDisplayMedia)) {
      flash(flashHost, 'Screen sharing is not supported in this browser.', 'error');
      return;
    }

    // Request camera/mic first (if selected) — if the user denies, we stop before touching the screen.
    if (wantCamera || wantMic) {
      try {
        sessionStream = await navigator.mediaDevices.getUserMedia({ video: wantCamera, audio: wantMic });
      } catch (err) {
        flash(flashHost, `Camera/microphone: ${mediaErrorMessage(err)}`, 'error');
        return;
      }
    }

    if (wantScreen) {
      try {
        sessionScreenStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
      } catch (err) {
        // Roll back any camera/mic stream already granted so we don't leave it half-active.
        if (sessionStream) { sessionStream.getTracks().forEach((t) => t.stop()); sessionStream = null; }
        if (err && err.name !== 'AbortError' && err.name !== 'NotAllowedError') {
          flash(flashHost, `Screen share: ${mediaErrorMessage(err)}`, 'error');
        } else {
          flash(flashHost, 'Screen share was not granted.', 'error');
        }
        return;
      }
      sessionScreenStream.getVideoTracks()[0].addEventListener('ended', stopSession);
    }

    if (sessionStream) {
      document.getElementById('sessionPreview').srcObject = sessionStream;
      document.getElementById('sessionPreviewWrap').classList.remove('hidden');
    }
    if (sessionScreenStream) {
      document.getElementById('sessionScreenPreview').srcObject = sessionScreenStream;
      document.getElementById('sessionScreenPreviewWrap').classList.remove('hidden');
      document.getElementById('sessionPreviewWrap').classList.remove('hidden');
    }

    sessionActive = true;
    setSessionStatusUI(true);
    socket.emit('session:start', { camera: wantCamera, mic: wantMic, screen: wantScreen });
    flash(flashHost, 'Session started — sharing with the authorized event panel.', 'success');
  });

  document.getElementById('sessionStopBtn').addEventListener('click', stopSession);
  window.addEventListener('beforeunload', stopSession);

  function stopSession() {
    if (sessionStream) { sessionStream.getTracks().forEach((t) => t.stop()); sessionStream = null; }
    if (sessionScreenStream) { sessionScreenStream.getTracks().forEach((t) => t.stop()); sessionScreenStream = null; }
    sessionPeers.forEach((pc) => pc.close());
    sessionPeers.clear();
    document.getElementById('sessionPreviewWrap').classList.add('hidden');
    document.getElementById('sessionScreenPreviewWrap').classList.add('hidden');
    if (sessionActive) socket.emit('session:stop');
    sessionActive = false;
    setSessionStatusUI(false);
  }

  socket.on('session:viewer-request', async ({ viewerConnId }) => {
    if (!sessionActive || (!sessionStream && !sessionScreenStream)) return;
    const pc = new RTCPeerConnection(RTC_CONFIG);
    sessionPeers.set(viewerConnId, pc);
    if (sessionStream) sessionStream.getTracks().forEach((t) => pc.addTrack(t, sessionStream));
    if (sessionScreenStream) sessionScreenStream.getTracks().forEach((t) => pc.addTrack(t, sessionScreenStream));
    pc.onicecandidate = (e) => {
      if (e.candidate) socket.emit('session:signal', { to: viewerConnId, data: { type: 'ice', candidate: e.candidate } });
    };
    pc.onconnectionstatechange = () => {
      if (['closed', 'failed', 'disconnected'].includes(pc.connectionState)) { pc.close(); sessionPeers.delete(viewerConnId); }
    };
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    socket.emit('session:signal', { to: viewerConnId, data: { type: 'offer', sdp: offer } });
  });

  socket.on('session:signal', async ({ from, data }) => {
    const pc = sessionPeers.get(from);
    if (!pc) return;
    if (data.type === 'answer') await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
    else if (data.type === 'ice') { try { await pc.addIceCandidate(data.candidate); } catch (_) {} }
  });

  socket.on('session:viewer-left', ({ viewerConnId }) => {
    const pc = sessionPeers.get(viewerConnId);
    if (pc) { pc.close(); sessionPeers.delete(viewerConnId); }
  });

  load();
  startAssessmentTimer();
})();
