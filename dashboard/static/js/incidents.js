/**
 * incidents.js — Incident Intelligence page logic.
 *
 * Fetches incidents from /api/incidents, renders active/resolved tabs,
 * accordion triage briefs, MTTR metric, and the incidents-over-time chart.
 */

let allIncidents = [];

/* ------------------------------------------------------------
   Bootstrap
   ------------------------------------------------------------ */
(async function initIncidents() {
  const data  = await fetch('/api/incidents').then(r => r.json()).catch(() => ({ incidents: [] }));
  allIncidents = data.incidents || [];

  computeAndRenderMTTR(allIncidents);
  renderIncidentChart(allIncidents);
  renderActive();
  renderResolved();

  requestAnimationFrame(() => {
    document.querySelectorAll('.fade-in').forEach((el, i) => {
      setTimeout(() => el.classList.add('visible'), i * 70);
    });
  });
})();

/* ------------------------------------------------------------
   Tab switching
   ------------------------------------------------------------ */
/**
 * Switch between the Active and Resolved incident tabs.
 *
 * @param {'active'|'resolved'} tab - The tab to activate.
 */
function switchTab(tab) {
  const isActive = tab === 'active';

  document.getElementById('tabActive').classList.toggle('active', isActive);
  document.getElementById('tabResolved').classList.toggle('active', !isActive);
  document.getElementById('paneActive').style.display   = isActive ? '' : 'none';
  document.getElementById('paneResolved').style.display = isActive ? 'none' : '';
}

/* ------------------------------------------------------------
   MTTR calculation
   ------------------------------------------------------------ */
/**
 * Calculate MTTR from resolved incidents and update the metric display.
 *
 * @param {object[]} incidents - All incident objects.
 */
function computeAndRenderMTTR(incidents) {
  const resolved = incidents.filter(i => i.status === 'closed' && i.lessons);
  const times = resolved
    .map(i => i.lessons?.time_to_resolution_minutes)
    .filter(t => t && t > 0);

  const el = document.getElementById('mttrValue');
  if (!times.length) { el.textContent = '—'; return; }

  const avg = Math.round(times.reduce((a, b) => a + b, 0) / times.length);
  el.textContent = formatDuration(avg);
}

/* ------------------------------------------------------------
   Render active incidents list
   ------------------------------------------------------------ */
function renderActive() {
  const container = document.getElementById('activeList');
  const active    = allIncidents.filter(i => i.status === 'open');

  if (!active.length) {
    container.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:48px;font-size:0.9rem">
      No active incidents. 🟢
    </p>`;
    return;
  }

  container.innerHTML = active.map((inc, i) => buildIncidentCard(inc, i)).join('');
}

/* ------------------------------------------------------------
   Render resolved incidents list
   ------------------------------------------------------------ */
function renderResolved() {
  const container = document.getElementById('resolvedList');
  const resolved  = allIncidents.filter(i => i.status === 'closed');

  if (!resolved.length) {
    container.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:48px;font-size:0.9rem">
      No resolved incidents yet.
    </p>`;
    return;
  }

  container.innerHTML = resolved.map((inc, i) => buildIncidentCard(inc, i, 'resolved')).join('');
}

/* ------------------------------------------------------------
   Build incident card HTML
   ------------------------------------------------------------ */
/**
 * Build the HTML string for a single incident card with accordion triage brief.
 *
 * @param {object}  inc    - Incident object from the API.
 * @param {number}  i      - Index for unique accordion IDs.
 * @param {string}  [type] - 'active' or 'resolved'.
 * @returns {string} HTML string.
 */
function buildIncidentCard(inc, i, type = 'active') {
  const badgeClass = type === 'resolved' ? 'badge-closed' : 'badge-open';
  const badgeText  = type === 'resolved' ? 'Resolved' : 'Active';
  const brief      = inc.triage_brief || {};
  const confidence = brief.confidence ? `${Math.round(brief.confidence * 100)}%` : '—';
  const timeOpen   = formatTimestamp(inc.created_at);

  const steps = (brief.resolution_steps || []).map((s, si) => `
    <li class="step-item">
      <span class="step-num">${si + 1}</span>
      <span>${escapeHtml(s)}</span>
    </li>
  `).join('');

  const similar = (brief.similar_incident_links || []).map(url => `
    <li><a href="${escapeHtml(url)}" target="_blank" style="font-size:0.8rem">${escapeHtml(url)}</a></li>
  `).join('');

  const lessons    = inc.lessons || {};
  const lessonHtml = type === 'resolved' && lessons.root_cause ? `
    <div style="margin-top:12px;padding:12px;background:rgba(122,158,110,0.06);border-radius:8px;border:1px solid rgba(122,158,110,0.15)">
      <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--color-success);margin-bottom:4px">CONFIRMED ROOT CAUSE</div>
      <p style="font-size:0.82rem;color:var(--text-secondary)">${escapeHtml(lessons.root_cause)}</p>
      ${lessons.time_to_resolution_minutes ? `<div style="font-size:0.75rem;color:var(--text-muted);margin-top:4px">Resolved in ${formatDuration(lessons.time_to_resolution_minutes)}</div>` : ''}
    </div>
  ` : '';

  return `
    <div class="incident-card" id="icard-${i}">
      <div class="incident-card-header accordion-toggle" onclick="toggleAccordion('ibrief-${i}')">
        <div>
          <div class="incident-card-title">#${inc.issue_number} — ${escapeHtml(inc.title)}</div>
          <div class="incident-card-meta">
            Opened ${timeOpen} · Confidence: ${confidence}
          </div>
        </div>
        <div class="incident-card-actions">
          <span class="badge ${badgeClass}">${badgeText}</span>
          <i class="ti ti-chevron-down accordion-arrow" id="arrow-ibrief-${i}" style="color:var(--text-muted)"></i>
        </div>
      </div>

      <div class="accordion-body triage-brief-body" id="ibrief-${i}">
        <div style="padding-top:16px">
          ${brief.likely_cause ? `
          <div style="margin-bottom:14px">
            <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:4px">LIKELY ROOT CAUSE</div>
            <p style="font-size:0.85rem;color:var(--text-secondary);line-height:1.5">${escapeHtml(brief.likely_cause)}</p>
            <div style="margin-top:6px">
              <div style="font-size:0.72rem;color:var(--text-muted);margin-bottom:2px">Confidence</div>
              <div class="confidence-bar" style="max-width:200px">
                <div class="confidence-fill" style="width:${Math.round((brief.confidence||0)*100)}%"></div>
              </div>
            </div>
          </div>` : ''}

          ${steps ? `
          <div style="margin-bottom:14px">
            <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:8px">RESOLUTION STEPS</div>
            <ol class="step-list">${steps}</ol>
          </div>` : ''}

          ${brief.estimated_resolution_minutes ? `
          <div style="margin-bottom:14px;font-size:0.82rem;color:var(--text-secondary)">
            <strong style="color:var(--accent-gold)">Estimated resolution:</strong>
            ${formatDuration(brief.estimated_resolution_minutes)}
          </div>` : ''}

          ${similar ? `
          <div style="margin-bottom:14px">
            <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-muted);margin-bottom:6px">SIMILAR INCIDENTS</div>
            <ul style="list-style:none;display:flex;flex-direction:column;gap:4px">${similar}</ul>
          </div>` : ''}

          ${lessonHtml}
        </div>
      </div>
    </div>
  `;
}

/* ------------------------------------------------------------
   Accordion toggle
   ------------------------------------------------------------ */
/**
 * Toggle an accordion panel open or closed.
 *
 * @param {string} id - The id of the accordion body element.
 */
function toggleAccordion(id) {
  const body  = document.getElementById(id);
  const arrow = document.getElementById('arrow-' + id);
  if (!body) return;
  body.classList.toggle('open');
  if (arrow) arrow.classList.toggle('open');
}

/* ------------------------------------------------------------
   Incidents over time chart
   ------------------------------------------------------------ */
/**
 * Render the incidents-by-week bar chart.
 *
 * @param {object[]} incidents - All incident objects.
 */
function renderIncidentChart(incidents) {
  const WEEKS = 12;
  const weekLabels = [];
  const weekCounts = new Array(WEEKS).fill(0);

  for (let i = WEEKS - 1; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i * 7);
    weekLabels.push(d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
  }

  incidents.forEach(inc => {
    if (!inc.created_at) return;
    const incDate = new Date(inc.created_at);
    for (let i = 0; i < WEEKS; i++) {
      const start = new Date();
      start.setDate(start.getDate() - (WEEKS - 1 - i) * 7);
      const end = new Date(start);
      end.setDate(end.getDate() + 7);
      if (incDate >= start && incDate < end) {
        weekCounts[i]++;
        break;
      }
    }
  });

  createBarChart('incidentChart', {
    labels: weekLabels,
    datasets: [{
      data: weekCounts,
      backgroundColor: 'rgba(212,149,106,0.45)',
      borderColor:     '#d4956a',
    }],
  });
}

/* ------------------------------------------------------------
   Helpers
   ------------------------------------------------------------ */
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

