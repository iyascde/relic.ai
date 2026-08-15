/**
 * memory.js — Memory Archive page logic.
 *
 * Fetches the memory store from /api/memory, renders the memory card grid,
 * drives client-side search filtering, and renders the stratigraphy timeline.
 */

let allMemories = [];

/* ------------------------------------------------------------
   Bootstrap
   ------------------------------------------------------------ */
(async function initMemory() {
  const data  = await fetch('/api/memory').then(r => r.json()).catch(() => ({ total: 0, memories: [] }));
  allMemories = data.memories || [];

  const total = data.total || 0;
  const subtitle = document.getElementById('archiveSubtitle');
  if (subtitle) {
    subtitle.textContent = total === 0
      ? 'The archive is empty. Close your first incident to store a memory.'
      : `${total} artifact${total === 1 ? '' : 's'} in the archive — each one a lesson earned.`;
  }

  renderMemoryGrid(allMemories);
  renderStratigraphy(allMemories);

  document.getElementById('memorySearch')?.addEventListener('input', onSearch);

  requestAnimationFrame(() => {
    document.querySelectorAll('.memory-card, .fade-in').forEach((el, i) => {
      setTimeout(() => el.classList.add('visible'), i * 60);
    });
  });
})();

/* ------------------------------------------------------------
   Render memory card grid
   ------------------------------------------------------------ */
/**
 * Render the memory card grid from the given array of memory objects.
 *
 * @param {object[]} memories - Array of resolved incident objects with lessons.
 */
function renderMemoryGrid(memories) {
  const grid    = document.getElementById('memoryGrid');
  const noMsg   = document.getElementById('noMemories');

  if (!memories.length) {
    grid.innerHTML = '';
    noMsg.style.display = '';
    return;
  }

  noMsg.style.display = 'none';
  grid.innerHTML = memories.map(mem => buildMemoryCard(mem)).join('');
}

/* ------------------------------------------------------------
   Build memory card HTML
   ------------------------------------------------------------ */
/**
 * Build the HTML string for a single memory card.
 *
 * @param {object} mem - Resolved incident object with lessons data.
 * @returns {string} HTML string.
 */
function buildMemoryCard(mem) {
  const lessons = mem.lessons || {};
  const files   = (lessons.affected_files || []).slice(0, 3);
  const date    = mem.resolved_at
    ? new Date(mem.resolved_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
    : 'Unknown date';
  const ttr     = lessons.time_to_resolution_minutes;
  const incId   = mem.issue_number ? `INC-#${mem.issue_number}` : 'INC-???';

  const fileTags = files.map(f => `<span class="file-tag">${escapeHtml(shortPath(f))}</span>`).join('');

  return `
    <div class="memory-card">
      <div class="memory-card-id">${escapeHtml(incId)}</div>
      <div class="memory-card-title">${escapeHtml(mem.title || 'Untitled Incident')}</div>
      <div class="memory-card-cause">${escapeHtml(lessons.root_cause || 'Root cause not recorded.')}</div>
      ${fileTags ? `<div class="memory-card-files">${fileTags}</div>` : ''}
      <div class="memory-card-footer">
        <span class="memory-card-date">${date}</span>
        ${ttr ? `<span class="badge badge-mock" style="font-size:0.68rem">${formatDuration(ttr)}</span>` : ''}
      </div>
    </div>
  `;
}

/* ------------------------------------------------------------
   Client-side search
   ------------------------------------------------------------ */
function onSearch(e) {
  const q = e.target.value.toLowerCase().trim();
  if (!q) { renderMemoryGrid(allMemories); return; }

  const filtered = allMemories.filter(mem => {
    const lessons = mem.lessons || {};
    const text = [
      mem.title,
      lessons.root_cause,
      ...(lessons.affected_files || []),
      ...(lessons.resolution_steps || []),
    ].join(' ').toLowerCase();
    return text.includes(q);
  });

  renderMemoryGrid(filtered);
}

/* ------------------------------------------------------------
   Stratigraphy timeline
   ------------------------------------------------------------ */
/**
 * Render the archaeological stratigraphy sidebar timeline.
 *
 * @param {object[]} memories - Array of memory objects, newest first.
 */
function renderStratigraphy(memories) {
  const container = document.getElementById('stratTimeline');
  if (!container) return;

  if (!memories.length) {
    container.innerHTML = `<div style="padding:16px;color:var(--text-muted);font-size:0.78rem;text-align:center">No layers yet</div>`;
    return;
  }

  // Sort newest-first to match stratigraphy convention (top = newest = shallowest)
  const sorted = [...memories].sort((a, b) =>
    new Date(b.resolved_at || 0) - new Date(a.resolved_at || 0)
  );

  container.innerHTML = sorted.map((mem, i) => {
    const date  = mem.resolved_at
      ? new Date(mem.resolved_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
      : '—';
    const depth = i + 1;
    // Opacity fades with depth to suggest buried age.
    const opacity = Math.max(0.35, 1 - i * 0.08).toFixed(2);

    return `
      <div class="strat-layer" style="opacity:${opacity}">
        <span class="strat-depth">${depth}</span>
        <div class="strat-marker"></div>
        <span class="strat-label" title="${escapeHtml(mem.title || '')}">${escapeHtml(truncate(mem.title || 'Unnamed', 28))}</span>
        <span class="strat-date">${date}</span>
      </div>
    `;
  }).join('');
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

function truncate(str, max) {
  if (!str) return '';
  return str.length > max ? str.slice(0, max) + '…' : str;
}

function shortPath(filepath) {
  if (!filepath) return '';
  const parts = filepath.split('/');
  return parts.length > 2 ? '…/' + parts.slice(-2).join('/') : filepath;
}

