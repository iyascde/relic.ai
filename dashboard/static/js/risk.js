/**
 * risk.js — PR Risk Analysis page logic.
 *
 * Fetches risk scores from /api/scores, renders the filterable table,
 * drives the detail panel slide-in, and renders the risk distribution chart.
 */

let allScores = [];

/* ------------------------------------------------------------
   Bootstrap
   ------------------------------------------------------------ */
(async function initRisk() {
  const data = await fetch('/api/scores').then(r => r.json()).catch(() => ({ scores: [] }));
  allScores  = data.scores || [];

  document.getElementById('scoreCount').textContent = `${allScores.length} PRs`;

  renderTable(allScores);
  renderDistributionChart(allScores);

  document.getElementById('riskSearch').addEventListener('input', onSearch);

  requestAnimationFrame(() => {
    document.querySelectorAll('.fade-in').forEach((el, i) => {
      setTimeout(() => el.classList.add('visible'), i * 80);
    });
  });
})();

/* ------------------------------------------------------------
   Table rendering
   ------------------------------------------------------------ */
/**
 * Render the risk scores table with the provided rows.
 *
 * @param {object[]} rows - Array of risk score objects from the API.
 */
function renderTable(rows) {
  const tbody = document.getElementById('riskTableBody');

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:48px;color:var(--text-muted)">
      No risk scores yet. Open a pull request to trigger the first assessment.
    </td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map((row, i) => {
    const tier       = getRiskClass(row.score);
    const scoreHtml  = `<span class="risk-score ${tier}">${row.score}</span>`;
    const files      = (row.high_risk_files || []).slice(0, 2).map(f => `
      <span class="file-tag">${truncate(f.file || f, 30)}</span>
    `).join('');
    const date = row.created_at
      ? new Date(row.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      : '—';
    const reason = truncate(row.reasoning || '', 72);

    return `
      <tr class="risk-row-${tier}" data-idx="${i}" onclick="openPanel(${i})">
        <td>#${row.pr_number}</td>
        <td>
          <div style="font-weight:500;color:var(--text-primary);margin-bottom:4px">${escapeHtml(reason)}</div>
          <div style="display:flex;flex-wrap:wrap;gap:4px">${files}</div>
        </td>
        <td>${scoreHtml}</td>
        <td style="font-size:0.78rem;color:var(--text-muted)">${(row.high_risk_files || []).length} file(s)</td>
        <td style="font-size:0.78rem;color:var(--text-muted)">${date}</td>
        <td><button class="btn btn-secondary" style="padding:5px 10px;font-size:0.75rem" onclick="event.stopPropagation();openPanel(${i})">View</button></td>
      </tr>
    `;
  }).join('');
}

/* ------------------------------------------------------------
   Search / filter
   ------------------------------------------------------------ */
function onSearch(e) {
  const q = e.target.value.toLowerCase().trim();
  if (!q) { renderTable(allScores); return; }

  const filtered = allScores.filter(row => {
    const fileNames = (row.high_risk_files || []).map(f => (f.file || f).toLowerCase()).join(' ');
    return (
      String(row.pr_number).includes(q) ||
      (row.reasoning || '').toLowerCase().includes(q) ||
      fileNames.includes(q)
    );
  });
  renderTable(filtered);
}

/* ------------------------------------------------------------
   Detail panel
   ------------------------------------------------------------ */
/**
 * Open the detail panel for the score at the given array index.
 *
 * @param {number} idx - Index into the allScores array.
 */
function openPanel(idx) {
  const row = allScores[idx];
  if (!row) return;

  const tier  = getRiskClass(row.score);
  const files = (row.high_risk_files || []).map(f => `
    <div style="display:flex;gap:8px;padding:8px 0;border-bottom:1px solid var(--border-subtle)">
      <code class="file-tag" style="flex:1">${escapeHtml(f.file || f)}</code>
      <span style="font-size:0.78rem;color:var(--text-secondary)">${escapeHtml(f.reason || '')}</span>
    </div>
  `).join('');

  const actions = (row.suggested_actions || []).map((a, i) => `
    <li class="step-item">
      <span class="step-num">${i + 1}</span>
      <span>${escapeHtml(a)}</span>
    </li>
  `).join('');

  const similar = (row.similar_incidents || []).map(inc => `
    <div style="padding:8px 0;border-bottom:1px solid var(--border-subtle)">
      <a href="${escapeHtml(inc.url || '#')}" target="_blank" style="font-size:0.82rem;font-weight:500">
        ${escapeHtml(inc.incident_id || '')} — ${escapeHtml(inc.title || '')}
      </a>
      <div style="font-size:0.75rem;color:var(--text-muted);margin-top:2px">
        Similarity: ${Math.round((inc.similarity_score || 0) * 100)}% ·
        Resolved in ${inc.time_to_resolution_minutes || '?'}m
      </div>
    </div>
  `).join('');

  document.getElementById('detailPanelContent').innerHTML = `
    <div style="margin-bottom:20px">
      <div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:4px">PULL REQUEST #${row.pr_number}</div>
      <span class="risk-score ${tier}" style="font-size:1.1rem;padding:6px 14px">${row.score}</span>
      <span style="font-size:0.85rem;color:var(--text-secondary);margin-left:8px">${getRiskLabel(row.score)} Risk</span>
    </div>

    <div style="margin-bottom:20px">
      <div class="confidence-bar"><div class="confidence-fill" style="width:${row.score}%"></div></div>
    </div>

    <div style="margin-bottom:20px">
      <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:6px">REASONING</div>
      <p style="font-size:0.85rem;line-height:1.6;color:var(--text-secondary)">${escapeHtml(row.reasoning || '—')}</p>
    </div>

    ${files ? `
    <div style="margin-bottom:20px">
      <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:6px">HIGH-RISK FILES</div>
      ${files}
    </div>` : ''}

    ${actions ? `
    <div style="margin-bottom:20px">
      <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:8px">SUGGESTED ACTIONS</div>
      <ol class="step-list">${actions}</ol>
    </div>` : ''}

    ${similar ? `
    <div>
      <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:6px">SIMILAR PAST INCIDENTS</div>
      ${similar}
    </div>` : ''}
  `;

  document.getElementById('detailPanel').classList.add('open');
  document.getElementById('panelOverlay').classList.add('visible');

  // Highlight selected row.
  document.querySelectorAll('#riskTableBody tr').forEach(tr => tr.classList.remove('selected'));
  const targetRow = document.querySelector(`[data-idx="${idx}"]`);
  if (targetRow) targetRow.classList.add('selected');
}

/**
 * Close the detail panel.
 */
function closePanel() {
  document.getElementById('detailPanel').classList.remove('open');
  document.getElementById('panelOverlay').classList.remove('visible');
  document.querySelectorAll('#riskTableBody tr').forEach(tr => tr.classList.remove('selected'));
}

/* ------------------------------------------------------------
   Risk distribution chart
   ------------------------------------------------------------ */
/**
 * Render the risk score distribution bar chart.
 *
 * @param {object[]} scores - Array of risk score objects.
 */
function renderDistributionChart(scores) {
  const buckets = [0, 0, 0, 0, 0]; // 0-20, 20-40, 40-60, 60-80, 80-100
  scores.forEach(s => {
    const b = Math.min(Math.floor(s.score / 20), 4);
    buckets[b]++;
  });

  createBarChart('riskDistChart', {
    labels: ['0–20', '20–40', '40–60', '60–80', '80–100'],
    datasets: [{ data: buckets }],
  }, {
    scales: {
      x: { grid: { display: false }, ticks: { color: '#6b5d4f', font: { size: 9 } } },
      y: { grid: { color: 'rgba(201,168,76,0.07)' }, ticks: { color: '#6b5d4f', stepSize: 1 }, beginAtZero: true },
    },
  });
}

/* ------------------------------------------------------------
   Helpers
   ------------------------------------------------------------ */
function truncate(str, max) {
  if (!str) return '';
  return str.length > max ? str.slice(0, max) + '…' : str;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

