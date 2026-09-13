(async function () {
  const user = requireSession(); // any logged-in role
  if (!user) return;

  document.getElementById('backLink').addEventListener('click', (e) => {
    e.preventDefault();
    if (user.role === 'admin') window.location.href = '/admin.html';
    else window.location.href = '/cases.html';
  });

  const flashHost = document.getElementById('flashHost');
  try {
    const { leaderboard } = await Api.get('/api/leaderboard');
    const tbody = document.querySelector('#boardTable tbody');
    tbody.innerHTML = leaderboard.map((row, i) => `
      <tr>
        <td>${i + 1}</td>
        <td>${escapeHtml(row.team_name)}</td>
        <td>${row.cases_completed} / 3</td>
        <td><b>${row.net_score}</b></td>
      </tr>`).join('') || '<tr><td colspan="4">No teams yet.</td></tr>';
  } catch (err) {
    flash(flashHost, err.message, 'error');
  }
})();
