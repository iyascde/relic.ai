/**
 * main.js — Relic.ai shared utilities.
 *
 * Runs on every page. Provides:
 *   - Live clock in the top bar
 *   - Periodic /health ping updating the sidebar indicator
 *   - IntersectionObserver-driven fade-in for cards
 *   - Utility functions shared across page scripts
 */

/* ------------------------------------------------------------
   Live clock
   ------------------------------------------------------------ */
(function startClock() {
  const el = document.getElementById('liveClock');
  if (!el) return;

  function tick() {
    const now = new Date();
    el.textContent = now.toLocaleTimeString('en-US', {
      hour:   '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  }

  tick();
  setInterval(tick, 1000);
})();

/* ------------------------------------------------------------
   Health ping → sidebar indicator
   ------------------------------------------------------------ */
(function startHealthPing() {
  const dot   = document.getElementById('statusDot');
  const label = document.getElementById('statusLabel');
  if (!dot || !label) return;

  async function ping() {
    try {
      const data = await fetch('/health', { cache: 'no-store' }).then(r => r.json());
      const ok   = data.status === 'ok' || data.status === 'degraded';
      dot.className   = 'status-dot ' + (ok ? 'online' : 'offline');
      label.textContent = ok ? 'System Active' : 'System Degraded';
    } catch {
      dot.className   = 'status-dot offline';
      label.textContent = 'System Offline';
    }
  }

  ping();
  setInterval(ping, 30_000);
})();

/* ------------------------------------------------------------
   IntersectionObserver fade-in
   ------------------------------------------------------------ */
(function observeFadeIns() {
  const obs = new IntersectionObserver(
    entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          obs.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.05 }
  );

  // Observe immediately present elements and newly added ones via MutationObserver.
  function observe(root) {
    root.querySelectorAll('.fade-in, .stat-card, .memory-card, .incident-card').forEach(el => obs.observe(el));
  }

  observe(document);

  const mo = new MutationObserver(muts => {
    muts.forEach(m => m.addedNodes.forEach(node => {
      if (node.nodeType === 1) observe(node);
    }));
  });

  mo.observe(document.body, { childList: true, subtree: true });
})();

/* ------------------------------------------------------------
   Utility: format ISO timestamp as relative time
   ------------------------------------------------------------ */
/**
 * Format an ISO timestamp as a human-readable relative string.
 *
 * @param {string} iso - ISO 8601 timestamp string.
 * @returns {string} Relative time string, e.g. "2 hours ago".
 */
function formatTimestamp(iso) {
  if (!iso) return '—';
  const now   = Date.now();
  const then  = new Date(iso).getTime();
  const delta = Math.floor((now - then) / 1000);

  if (delta <  60)  return 'just now';
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

/* ------------------------------------------------------------
   Utility: get colour for a risk score
   ------------------------------------------------------------ */
/**
 * Return a CSS colour string for the given risk score.
 *
 * @param {number} score - Risk score 0-100.
 * @returns {string} CSS variable string.
 */
function getRiskColor(score) {
  if (score < 40) return 'var(--risk-low)';
  if (score < 70) return 'var(--risk-medium)';
  return 'var(--risk-high)';
}

/* ------------------------------------------------------------
   Utility: get label for a risk score
   ------------------------------------------------------------ */
/**
 * Return a human-readable label for the risk tier.
 *
 * @param {number} score - Risk score 0-100.
 * @returns {string} 'Low', 'Medium', or 'High'.
 */
function getRiskLabel(score) {
  if (score < 40) return 'Low';
  if (score < 70) return 'Medium';
  return 'High';
}

/* ------------------------------------------------------------
   Utility: get badge class for a risk score
   ------------------------------------------------------------ */
/**
 * Return a CSS class name for a risk score badge.
 *
 * @param {number} score - Risk score 0-100.
 * @returns {string} 'low', 'medium', or 'high'.
 */
function getRiskClass(score) {
  if (score < 40) return 'low';
  if (score < 70) return 'medium';
  return 'high';
}

/* ------------------------------------------------------------
   Utility: format duration in minutes as Xh Ym
   ------------------------------------------------------------ */
/**
 * Format a duration in minutes as a compact hours/minutes string.
 *
 * @param {number} minutes - Duration in minutes.
 * @returns {string} e.g. '1h 8m' or '45m'.
 */
function formatDuration(minutes) {
  if (!minutes || minutes <= 0) return '—';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

