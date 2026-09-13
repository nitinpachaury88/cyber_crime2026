(async function () {
  const user = requireSession(['admin']);
  if (!user) return;

  const flashHost = document.getElementById('flashHost');
  const feed = document.getElementById('feed');
  const onlineUsers = new Map();

  document.getElementById('logoutBtn').addEventListener('click', async () => {
    try { await Api.post('/api/auth/logout'); } catch (_) {}
    Api.clearSession();
    window.location.href = '/index.html';
  });

  // ---------------- WebSocket: live feed + presence + sessions ----------------
  const socket = createSocket();
  socket.on('connect', () => { socket.emit('admin:request-online'); socket.emit('admin:request-sessions'); });
  socket.on('admin:online-list', (list) => {
    onlineUsers.clear();
    list.forEach((u) => onlineUsers.set(u.userId, u));
    renderStats();
  });
  socket.on('admin:presence', (p) => {
    if (p.online) onlineUsers.set(p.userId, p);
    else onlineUsers.delete(p.userId);
    renderStats();
  });
  socket.on('activity', (evt) => {
    addFeedItem(evt);
    loadTeams();
  });

  function addFeedItem(evt) {
    const div = document.createElement('div');
    div.className = 'feed-item';
    const label = actionLabel(evt.actionType);
    div.innerHTML = `<div class="time">${new Date(evt.timestamp).toLocaleTimeString()}</div>
      <div><span class="who">${evt.teamName || 'System'}</span> — ${evt.userName ? evt.userName + ': ' : ''}${label}${evt.roundName ? ` <span class="badge">${evt.roundName}</span>` : ''}${evt.detail ? `<br><small>${escapeHtml(evt.detail)}</small>` : ''}</div>`;
    feed.prepend(div);
    while (feed.children.length > 80) feed.removeChild(feed.lastChild);
  }

  function actionLabel(type) {
    return {
      login: 'logged in', logout: 'logged out', view_evidence: 'viewed evidence',
      answer_submit: 'submitted an answer', hint_used: 'used a hint',
      final_submit: 'filed final report', timer_start: 'started the timer',
      team_created: 'team created', member_added: 'member added', member_removed: 'member removed',
      session_start: 'started an investigation session (camera/mic)', session_stop: 'stopped their investigation session',
    }[type] || type;
  }

  // ---------------- Teams table ----------------
  async function loadTeams() {
    try {
      const { teams } = await Api.get('/api/admin/teams');
      const tbody = document.querySelector('#teamsTable tbody');
      tbody.innerHTML = '';
      let inProgress = 0, completed = 0;
      teams.forEach((t) => {
        inProgress += t.cases_in_progress;
        completed += t.cases_completed;
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${escapeHtml(t.team_name)}<br><small>${t.college || ''}</small></td>
          <td>${caseChips(t.case_progress)}</td>
          <td>${t.total_score - t.hint_penalty} <small>(${t.total_score} − ${t.hint_penalty})</small></td>
          <td>${t.member_count}</td>
          <td>${t.last_activity_at ? timeAgo(t.last_activity_at) : '—'}</td>
          <td><button class="btn btn-sm" data-view="${t.id}">View</button> <button class="btn btn-sm btn-danger" data-del="${t.id}">Delete</button></td>`;
        tbody.appendChild(tr);
      });
      document.getElementById('statTeams').textContent = teams.length;
      document.getElementById('statCasesInProgress').textContent = inProgress;
      document.getElementById('statCasesCompleted').textContent = completed;
      tbody.querySelectorAll('[data-view]').forEach((b) => b.addEventListener('click', () => viewTeam(b.dataset.view)));
      tbody.querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', () => deleteTeam(b.dataset.del)));
    } catch (err) {
      flash(flashHost, err.message, 'error');
    }
  }

  function caseChips(progress) {
    const badge = { not_started: 'badge-secondary', in_progress: 'badge-warning', completed: 'badge-primary' };
    if (!progress || !progress.length) return '<small style="color:var(--text-faint);">not started</small>';
    return progress.map((p) => `<span class="badge ${badge[p.status] || ''}" title="${escapeHtml(p.case_title)}">${escapeHtml(p.case_code)}: ${p.score}</span>`).join(' ');
  }

  function renderStats() {
    document.getElementById('statOnline').textContent = onlineUsers.size;
  }

  async function deleteTeam(id) {
    if (!confirm('Delete this team and all its data? This cannot be undone.')) return;
    try {
      await Api.del(`/api/admin/teams/${id}`);
      flash(flashHost, 'Team deleted.', 'success');
      loadTeams();
    } catch (err) { flash(flashHost, err.message, 'error'); }
  }

  async function viewTeam(id) {
    try {
      const data = await Api.get(`/api/admin/teams/${id}`);
      const card = document.getElementById('teamDetailCard');
      const body = document.getElementById('teamDetailBody');
      card.style.display = 'block';
      body.innerHTML = `
        <h3>${escapeHtml(data.team.team_name)}</h3>
        <p>Total score: <b>${data.team.total_score - data.team.hint_penalty}</b> (raw ${data.team.total_score}, hint penalty ${data.team.hint_penalty})</p>

        <h4>Case Progress</h4>
        <table><thead><tr><th>Case</th><th>Status</th><th>Score</th><th>Hint Penalty</th></tr></thead><tbody>
          ${data.caseProgress.map((c) => `<tr><td>${escapeHtml(c.case_title)} <small>(${c.case_code})</small></td><td>${c.status}</td><td>${c.score}</td><td>${c.hint_penalty}</td></tr>`).join('') || '<tr><td colspan="4">No cases opened yet.</td></tr>'}
        </tbody></table>

        <div class="grid grid-2" style="margin-top:16px;">
          <div>
            <h4>Members</h4>
            <table><thead><tr><th>Name</th><th>Role</th><th>Last login</th></tr></thead><tbody>
              ${data.members.map((m) => `<tr><td>${escapeHtml(m.full_name)}</td><td>${m.role}</td><td>${m.last_login_at ? timeAgo(m.last_login_at) : 'never'}</td></tr>`).join('')}
            </tbody></table>
          </div>
          <div>
            <h4>Recent activity</h4>
            <div class="feed" style="max-height:220px;">
              ${data.activity.map((a) => `<div class="feed-item"><div class="time">${new Date(a.created_at).toLocaleTimeString()}</div><div>${a.actor || 'System'} — ${a.detail || a.action_type}</div></div>`).join('') || '<p>No activity yet.</p>'}
            </div>
          </div>
        </div>

        <h4 style="margin-top:16px;">Answers (${data.answers.filter(a=>a.is_correct).length}/${data.answers.length} correct)</h4>
        <table><thead><tr><th>Round</th><th>Question</th><th>Answer</th><th>Result</th><th>By</th></tr></thead><tbody>
          ${data.answers.map((a) => `<tr><td>${a.round_name}</td><td>${escapeHtml(a.question)}</td><td>${escapeHtml(a.answer_text)}</td><td class="${a.is_correct?'result-ok':'result-bad'}">${a.is_correct ? `+${a.marks_awarded}` : 'wrong'}</td><td>${a.answered_by||''}</td></tr>`).join('') || '<tr><td colspan="5">No answers yet.</td></tr>'}
        </tbody></table>

        <h4 style="margin-top:16px;">Final Reports</h4>
        <table><thead><tr><th>Case</th><th>Suspect</th><th>Attack Method</th><th>Score</th><th>Filed</th></tr></thead><tbody>
          ${data.submissions.map((s) => `<tr><td>${escapeHtml(s.case_title)}</td><td>${escapeHtml(s.suspect||'')}</td><td>${escapeHtml(s.attack_method||'')}</td><td>${s.final_score}</td><td>${new Date(s.submitted_at).toLocaleString()}</td></tr>`).join('') || '<tr><td colspan="5">None filed yet.</td></tr>'}
        </tbody></table>
      `;
      card.scrollIntoView({ behavior: 'smooth' });
    } catch (err) { flash(flashHost, err.message, 'error'); }
  }
  document.getElementById('closeDetail').addEventListener('click', () => { document.getElementById('teamDetailCard').style.display = 'none'; });

  document.getElementById('exportBtn').addEventListener('click', () => {
    window.open('/api/admin/export.csv?token=' + encodeURIComponent(Api.getToken()), '_blank');
  });

  // ---------------- New team modal ----------------
  const overlay = document.getElementById('modalOverlay');
  document.getElementById('newTeamBtn').addEventListener('click', () => overlay.classList.remove('hidden'));
  document.getElementById('cancelModal').addEventListener('click', () => overlay.classList.add('hidden'));

  let creatingTeam = false; // guards against double-submit (double click / double Enter)

  document.getElementById('newTeamForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (creatingTeam) return; // a request is already in flight — ignore this extra submit
    creatingTeam = true;
    const submitBtn = document.getElementById('newTeamForm').querySelector('button[type="submit"], .btn-primary');
    if (submitBtn) submitBtn.disabled = true;
    try {
      await Api.post('/api/admin/teams', {
        teamName: document.getElementById('teamName').value,
        college: document.getElementById('college').value,
        leaderFullName: document.getElementById('leaderFullName').value,
        leaderUsername: document.getElementById('leaderUsername').value,
        leaderPassword: document.getElementById('leaderPassword').value,
      });
      overlay.classList.add('hidden');
      document.getElementById('newTeamForm').reset();
      flash(flashHost, 'Team + leader login created.', 'success');
      loadTeams();
    } catch (err) {
      flash(flashHost, err.message, 'error');
    } finally {
      creatingTeam = false;
      if (submitBtn) submitBtn.disabled = false;
    }
  });

  loadTeams();
  setInterval(loadTeams, 15000);

  // ---------------- Live investigation sessions (viewer-only) ----------------
  const activeSessions = new Map();
  let watchPc = null;
  let watchingTeamId = null;

  socket.on('admin:sessions-list', (list) => {
    activeSessions.clear();
    list.forEach((s) => activeSessions.set(s.teamId, s));
    renderSessions();
  });
  socket.on('session:started', (s) => { activeSessions.set(s.teamId, s); renderSessions(); });
  socket.on('session:stopped', ({ teamId }) => {
    activeSessions.delete(teamId);
    renderSessions();
    if (watchingTeamId === teamId) closeSessionModal();
  });

  function renderSessions() {
    const el = document.getElementById('sessionsList');
    if (!activeSessions.size) { el.innerHTML = '<p style="color:var(--text-faint); font-size:.86rem;">No active sessions.</p>'; return; }
    el.innerHTML = [...activeSessions.values()].map((s) => `
      <div class="feed-item" style="justify-content:space-between; align-items:center;">
        <div>
          <b>${escapeHtml(s.teamName || 'Unknown team')}</b> — ${escapeHtml(s.fullName)}<br>
          <small>${s.camera ? '🟢 CAMERA ACTIVE' : '🔴 CAMERA OFF'} &nbsp; ${s.mic ? '🟢 MICROPHONE ACTIVE' : '🔴 MICROPHONE OFF'} &nbsp; ${s.screen ? '🟢 SCREEN SHARING' : '🔴 SCREEN OFF'} &nbsp; started ${timeAgo(s.startedAt)}</small>
        </div>
        <button class="btn btn-sm btn-primary" data-watch="${s.teamId}">Watch</button>
      </div>`).join('');
    el.querySelectorAll('[data-watch]').forEach((b) => b.addEventListener('click', () => watchSession(Number(b.dataset.watch))));
  }

  function watchSession(teamId) {
    const s = activeSessions.get(teamId);
    if (!s) return;
    watchingTeamId = teamId;
    document.getElementById('sessionModalTeam').textContent = s.teamName || '';
    document.getElementById('sessionModalCam').textContent = s.camera ? 'ON' : 'OFF';
    document.getElementById('sessionModalMic').textContent = s.mic ? 'ON' : 'OFF';
    document.getElementById('sessionModalScreen').textContent = s.screen ? 'ON' : 'OFF';
    document.getElementById('sessionModalOverlay').classList.remove('hidden');

    watchPc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] });
    watchPc.ontrack = (e) => { document.getElementById('sessionModalVideo').srcObject = e.streams[0]; };
    watchPc.onicecandidate = (e) => {
      if (e.candidate) socket.emit('session:signal', { to: s.participantConnId, data: { type: 'ice', candidate: e.candidate } });
    };

    socket.emit('admin:session:watch', { teamId });
  }

  socket.on('session:signal', async ({ from, data }) => {
    if (!watchPc) return;
    if (data.type === 'offer') {
      await watchPc.setRemoteDescription(new RTCSessionDescription(data.sdp));
      const answer = await watchPc.createAnswer();
      await watchPc.setLocalDescription(answer);
      socket.emit('session:signal', { to: from, data: { type: 'answer', sdp: answer } });
    } else if (data.type === 'ice') {
      try { await watchPc.addIceCandidate(data.candidate); } catch (_) {}
    }
  });

  function closeSessionModal() {
    document.getElementById('sessionModalOverlay').classList.add('hidden');
    if (watchPc) { watchPc.close(); watchPc = null; }
    document.getElementById('sessionModalVideo').srcObject = null;
    if (watchingTeamId != null) socket.emit('admin:session:unwatch', { teamId: watchingTeamId });
    watchingTeamId = null;
  }
  document.getElementById('sessionModalClose').addEventListener('click', closeSessionModal);
})();
