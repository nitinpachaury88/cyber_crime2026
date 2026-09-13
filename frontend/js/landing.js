(function () {
  // If already logged in, skip straight to the right dashboard.
  const existingUser = Api.getUser();
  if (existingUser && Api.getToken()) { goToDashboard(existingUser); return; }

  // ---------------- Intro sequence ----------------
  const introScreen = document.getElementById('introScreen');
  const introLog = document.getElementById('introLog');
  const LOG_LINES = [
    'Establishing secure connection…',
    'Scanning inbound network traffic…',
    'Suspicious packet identified…',
  ];
  let lineIndex = 0;
  const lineTimer = setInterval(() => {
    lineIndex += 1;
    if (lineIndex < LOG_LINES.length) introLog.textContent = LOG_LINES[lineIndex];
  }, 900);

  document.addEventListener('intro:threat-detected', () => {
    clearInterval(lineTimer);
    introLog.textContent = '⚠ THREAT DETECTED — compromised host isolated.';
  });

  function hideIntro() {
    clearInterval(lineTimer);
    introScreen.classList.add('intro-hidden');
    setTimeout(() => introScreen.remove(), 900);
  }

  document.getElementById('enterBtn').addEventListener('click', hideIntro);
  // Auto-advance into the login console a couple seconds after the reveal so
  // people who don't click still get in — this is a login gate, not a video.
  setTimeout(hideIntro, 6000);

  // ---------------- Role-tabbed login ----------------
  const flashHost = document.getElementById('flashHost');
  let selectedRole = 'leader';
  const roleHints = {
    leader: "Team leaders and members: log in with the username/password your organizer or team leader gave you.",
    member: "Team leaders and members: log in with the username/password your organizer or team leader gave you.",
    admin: 'Organizers: log in with your admin account to create teams and monitor the event live.',
  };

  document.querySelectorAll('.login-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.login-tab').forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      selectedRole = tab.dataset.role;
      document.getElementById('roleHint').textContent = roleHints[selectedRole];
    });
  });

  document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('loginBtn');
    btn.disabled = true;
    btn.textContent = 'Logging in…';
    try {
      const result = await Api.post('/api/auth/login', {
        username: document.getElementById('username').value.trim(),
        password: document.getElementById('password').value,
      });
      if (selectedRole === 'admin' && result.user.role !== 'admin') {
        throw new Error('That account is not an admin account.');
      }
      if (selectedRole !== 'admin' && result.user.role === 'admin') {
        throw new Error('That is an admin account — switch to the Admin tab.');
      }
      Api.setSession(result.token, result.user);
      goToDashboard(result.user);
    } catch (err) {
      flash(flashHost, err.message, 'error');
      btn.disabled = false;
      btn.textContent = 'Log In';
    }
  });
})();
