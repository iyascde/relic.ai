/**
 * charts.js — Relic.ai shared Chart.js configuration.
 *
 * Sets global Chart.js defaults to match the warm-dark design system and
 * exposes two factory functions: createLineChart and createBarChart.
 * Both are consumed by page-specific JS modules.
 */

// Apply global defaults once this script loads.
(function applyChartDefaults() {
  if (typeof Chart === 'undefined') return;

  Chart.defaults.color            = '#a89880';   // --text-secondary
  Chart.defaults.borderColor      = 'rgba(201,168,76,0.1)'; // warm gold grid lines
  Chart.defaults.font.family      = "'Inter', system-ui, sans-serif";
  Chart.defaults.font.size        = 11;
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.animation.duration     = 600;

  Chart.defaults.plugins.tooltip.backgroundColor = '#2e2820';
  Chart.defaults.plugins.tooltip.titleColor       = '#e8dcc8';
  Chart.defaults.plugins.tooltip.bodyColor        = '#a89880';
  Chart.defaults.plugins.tooltip.borderColor      = 'rgba(201,168,76,0.25)';
  Chart.defaults.plugins.tooltip.borderWidth      = 1;
  Chart.defaults.plugins.tooltip.padding          = 10;
  Chart.defaults.plugins.tooltip.cornerRadius     = 8;
})();

/**
 * Create a line chart on the given canvas.
 *
 * @param {string} canvasId - The id of the <canvas> element.
 * @param {{labels: string[], datasets: object[]}} data - Chart.js data object.
 * @returns {Chart|null} The Chart instance, or null if Chart.js is unavailable.
 */
function createLineChart(canvasId, data) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || typeof Chart === 'undefined') return null;

  // Destroy any existing chart on this canvas before creating a new one.
  const existing = Chart.getChart(canvasId);
  if (existing) existing.destroy();

  // Apply Relic palette defaults to all datasets.
  data.datasets = data.datasets.map(ds => ({
    borderColor:     '#c9a84c',
    backgroundColor: 'rgba(201,168,76,0.08)',
    pointBackgroundColor: '#c9a84c',
    pointRadius:     3,
    pointHoverRadius: 5,
    borderWidth: 2,
    spanGaps: true,
    ...ds,
  }));

  return new Chart(canvas, {
    type: 'line',
    data,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid: { color: 'rgba(201,168,76,0.07)' },
          ticks: { maxTicksLimit: 8, color: '#6b5d4f' },
        },
        y: {
          grid: { color: 'rgba(201,168,76,0.07)' },
          ticks: { color: '#6b5d4f' },
          beginAtZero: true,
          max: 100,
        },
      },
      plugins: {
        legend: { display: false },
      },
    },
  });
}

/**
 * Create a bar chart on the given canvas.
 *
 * @param {string} canvasId - The id of the <canvas> element.
 * @param {{labels: string[], datasets: object[]}} data - Chart.js data object.
 * @param {object} [extraOptions] - Optional Chart.js options overrides.
 * @returns {Chart|null} The Chart instance, or null if Chart.js is unavailable.
 */
function createBarChart(canvasId, data, extraOptions = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || typeof Chart === 'undefined') return null;

  const existing = Chart.getChart(canvasId);
  if (existing) existing.destroy();

  data.datasets = data.datasets.map(ds => ({
    backgroundColor: [
      'rgba(122,158,110,0.6)',   // 0-20: sage green
      'rgba(122,158,110,0.45)',  // 20-40
      'rgba(201,168,76,0.55)',   // 40-60: gold
      'rgba(212,149,106,0.55)',  // 60-80: terra
      'rgba(168,92,62,0.65)',    // 80-100: rust red
    ],
    borderColor: [
      '#7a9e6e', '#7a9e6e',
      '#c9a84c',
      '#d4956a',
      '#a85c3e',
    ],
    borderWidth: 1,
    borderRadius: 6,
    ...ds,
  }));

  return new Chart(canvas, {
    type: 'bar',
    data,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid:  { display: false },
          ticks: { color: '#6b5d4f', font: { size: 10 } },
        },
        y: {
          grid:  { color: 'rgba(201,168,76,0.07)' },
          ticks: { color: '#6b5d4f', stepSize: 1 },
          beginAtZero: true,
        },
      },
      plugins: { legend: { display: false } },
      ...extraOptions,
    },
  });
}

