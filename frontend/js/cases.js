(async function () {
  const user = requireSession(['leader', 'member']);
  if (!user) return;

  const flashHost = document.getElementById('flashHost');

  document.getElementById('logoutBtn').addEventListener('click', async () => {
    try { await Api.post('/api/auth/logout'); } catch (_) {}
    Api.clearSession();
    window.location.href = '/index.html';
  });

  // ---------------- Roster ----------------
  async function loadRoster() {
    try {
      const { team, members } = await Api.get('/api/leader/team').catch(async () => {
        // Members can't call /api/leader/team (leader-only) — fall back to
        // what we already know from the login response for a read-only view.
        return { team: { team_name: user.teamName || 'Your Team', college: null, total_score: 0, hint_penalty: 0 }, members: null };
      });
      document.getElementById('teamName').textContent = team.team_name;
      document.getElementById('teamSub').textContent = team.college ? `${team.college} · Net score: ${team.total_score - team.hint_penalty}` : `Net score: ${team.total_score - team.hint_penalty}`;

      if (members) renderRoster(members);
      else document.getElementById('rosterCard').classList.add('hidden');
    } catch (err) {
      flash(flashHost, err.message, 'error');
    }
  }

  function renderRoster(members) {
    const chips = document.getElementById('memberChips');
    chips.innerHTML = members.map((m) => `
      <span class="member-chip">
        <span class="avatar">${escapeHtml(m.full_name.slice(0, 1).toUpperCase())}</span>
        ${escapeHtml(m.full_name)} <small style="color:var(--text-faint);">(${m.role})</small>
        ${user.role === 'leader' && m.role !== 'leader' ? `<span class="remove" data-remove="${m.id}">✕</span>` : ''}
      </span>`).join('');
    chips.querySelectorAll('[data-remove]').forEach((el) =>
      el.addEventListener('click', () => removeMember(el.dataset.remove))
    );

    const box = document.getElementById('addMemberBox');
    if (user.role === 'leader') {
      box.innerHTML = `<button class="btn btn-sm btn-primary" id="addMemberBtn">+ Add Teammate</button>`;
      document.getElementById('addMemberBtn').addEventListener('click', showAddMemberForm);
    }
  }

  function showAddMemberForm() {
    const box = document.getElementById('addMemberBox');
    box.innerHTML = `
      <form id="addMemberForm" style="display:flex; gap:8px; align-items:flex-end; flex-wrap:wrap;">
        <div><label style="margin-bottom:4px;">Name</label><input id="mFullName" style="margin-bottom:0; width:140px;" required /></div>
        <div><label style="margin-bottom:4px;">Username</label><input id="mUsername" style="margin-bottom:0; width:120px;" required /></div>
        <div><label style="margin-bottom:4px;">Password</label><input id="mPassword" type="text" style="margin-bottom:0; width:120px;" required /></div>
        <button class="btn btn-sm btn-primary" type="submit">Add</button>
        <button class="btn btn-sm" type="button" id="cancelAddMember">Cancel</button>
      </form>`;
    document.getElementById('cancelAddMember').addEventListener('click', loadRoster);
    document.getElementById('addMemberForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        await Api.post('/api/leader/members', {
          fullName: document.getElementById('mFullName').value,
          username: document.getElementById('mUsername').value,
          password: document.getElementById('mPassword').value,
        });
        flash(flashHost, 'Teammate added.', 'success');
        loadRoster();
      } catch (err) { flash(flashHost, err.message, 'error'); }
    });
  }

  async function removeMember(id) {
    if (!confirm('Remove this teammate?')) return;
    try {
      await Api.del(`/api/leader/members/${id}`);
      loadRoster();
    } catch (err) { flash(flashHost, err.message, 'error'); }
  }

  // ---------------- Assessment overview ----------------
  const STATUS_LABEL = { not_started: 'Not started', in_progress: 'In progress', completed: 'Completed' };
  const STATUS_BADGE = { not_started: 'badge-secondary', in_progress: 'badge-warning', completed: 'badge-primary' };
  const ACTION_LABEL = { not_started: 'Enter Investigation', in_progress: 'Continue Investigation', completed: 'Review Case' };

  async function loadCases() {
    try {
      const data = await Api.get('/api/team/assessment/state');
      const grid = document.getElementById('caseGrid');
      const locked = data.locked;
      grid.innerHTML = data.cases.map((c, i) => {
        const total = c.questions.length;
        const answered = c.questions.filter((q) => q.selectedOption !== null && q.selectedOption !== undefined).length;
        const status = locked ? 'completed' : answered === 0 ? 'not_started' : answered === total ? 'completed' : 'in_progress';
        const pct = total ? Math.round((answered / total) * 100) : 0;
        return `
        <div class="case-card">
          <span class="status-pill badge ${STATUS_BADGE[status]}">${STATUS_LABEL[status]}</span>
          <div class="code">${escapeHtml(c.case_code)} · Case ${i + 1}</div>
          <h3>${escapeHtml(c.title)}</h3>
          <p>${escapeHtml(c.description || '')}</p>
          <div class="meta-row">
            <span>💰 ₹${c.financial_loss ?? '—'}</span>
            <span>❓ ${total} questions</span>
            <span>🏆 ${c.max_score} pts</span>
          </div>
          <div class="case-progress-bar"><div class="fill" style="width:${pct}%"></div></div>
          <button class="btn btn-primary btn-block" data-open="${c.id}">🔍 ${ACTION_LABEL[status]}</button>
        </div>`;
      }).join('');
      grid.querySelectorAll('[data-open]').forEach((b) =>
        b.addEventListener('click', () => { window.location.href = `/competition.html?case=${b.dataset.open}`; })
      );

      const cta = document.getElementById('assessmentCta');
      if (locked && data.result) {
        cta.innerHTML = `<div class="flash success">Assessment submitted — Final Score: ${data.result.finalScore}/100 (${escapeHtml(data.result.rating)}).</div>
          <a class="btn btn-primary btn-block" href="/competition.html">Review Result</a>`;
      } else {
        const anyAnswered = data.cases.some((c) => c.questions.some((q) => q.selectedOption !== null && q.selectedOption !== undefined));
        cta.innerHTML = `<a class="btn btn-primary btn-block" href="/competition.html">${anyAnswered ? 'Continue Assessment' : 'Start Assessment'}</a>`;
      }
    } catch (err) {
      flash(flashHost, err.message, 'error');
    }
  }

  loadRoster();
  loadCases();
})();
