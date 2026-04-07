/* PMCore WordPress Plugin — Frontend JS
 * Calls PMCore API directly from the browser (Tailscale network).
 * Config injected by wp_localize_script as window.PMCoreConfig
 */

(function () {
  'use strict';

  const API_URL = (window.PMCoreConfig && window.PMCoreConfig.apiUrl)
    ? window.PMCoreConfig.apiUrl.replace(/\/$/, '')
    : 'http://100.110.246.22:8765';

  // ── Comm type labels ────────────────────────────────────────────────────────

  const COMM_LABELS = {
    'kickoff':          'Kickoff Email',
    'status_report':    'Status Report',
    'executive_summary':'Executive Summary',
    'risk_escalation':  'Risk Escalation',
  };

  // ── Badge helpers ───────────────────────────────────────────────────────────

  function badge(text, cls) {
    return `<span class="pmcore-badge pmcore-badge--${cls}">${esc(text)}</span>`;
  }

  function healthBadge(h) {
    const map = { green: 'pass', yellow: 'warn', red: 'fail' };
    const emoji = { green: '🟢', yellow: '🟡', red: '🔴' };
    const cls = map[h] || 'warn';
    return badge((emoji[h] || '🟡') + ' ' + h.toUpperCase(), cls);
  }

  function auditBadge(status) {
    const map = { pass: 'pass', warn: 'warn', fail: 'fail', skip: 'skip' };
    return badge(status.toUpperCase(), map[status] || 'skip');
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Render helpers ──────────────────────────────────────────────────────────

  function renderPlanner(p) {
    if (!p) return '<p>No planner data.</p>';
    const tg = p.task_graph || {};
    const proj = tg.project || {};
    const tasks = tg.tasks || [];

    let html = `
      <div class="pmcore-meta-row">
        ${badge(p.methodology || 'Unknown', 'neutral')}
        <span class="pmcore-meta">${esc(p.duration_days || '?')} days</span>
        <span class="pmcore-meta">${esc(p.num_tasks || 0)} tasks</span>
      </div>`;

    if (proj.budget_usd) {
      html += `<div class="pmcore-meta">Budget: $${Number(proj.budget_usd).toLocaleString()}</div>`;
    }

    if (tasks.length) {
      html += '<ul class="pmcore-task-list">';
      tasks.slice(0, 6).forEach(t => {
        html += `<li><strong>${esc(t.name || t.id)}</strong>`;
        if (t.duration_days) html += ` &mdash; ${esc(t.duration_days)}d`;
        if (t.phase) html += ` <em>(${esc(t.phase)})</em>`;
        html += '</li>';
      });
      if (tasks.length > 6) html += `<li class="pmcore-more">+${tasks.length - 6} more tasks</li>`;
      html += '</ul>';
    }
    return html;
  }

  function renderReasoner(r) {
    if (!r) return '<p>No risk data.</p>';

    let html = `<div class="pmcore-meta-row">${healthBadge(r.overall_health || 'yellow')}</div>`;

    if (r.top_risks && r.top_risks.length) {
      html += '<div class="pmcore-label-sm">Top Risks</div><ul class="pmcore-risk-list">';
      r.top_risks.slice(0, 3).forEach(risk => {
        html += `<li>${esc(risk)}</li>`;
      });
      html += '</ul>';
    }

    if (r.critical_path && r.critical_path.length) {
      html += `<div class="pmcore-label-sm">Critical Path</div>
               <div class="pmcore-critical-path">${r.critical_path.slice(0, 4).map(esc).join(' &rarr; ')}</div>`;
    }
    return html;
  }

  function renderCommunicator(c) {
    if (!c) return '<p>No communication generated.</p>';
    const text = c.communication || '';
    const label = COMM_LABELS[c.comm_type] || c.comm_type || 'Communication';
    return `<div class="pmcore-comm-label">${esc(label)}</div>
            <pre class="pmcore-prose-text">${esc(text)}</pre>`;
  }

  function renderMathAudit(ma) {
    if (!ma) return '<p>No math audit data.</p>';

    const overallCls = ma.overall === 'pass' ? 'pass' : ma.overall === 'fail' ? 'fail' : 'warn';
    let html = `<div class="pmcore-meta-row">${badge(ma.overall.toUpperCase(), overallCls)}</div>`;

    if (ma.summary) {
      html += `<p class="pmcore-audit-summary">${esc(ma.summary)}</p>`;
    }

    if (ma.checks && ma.checks.length) {
      html += '<ul class="pmcore-audit-checks">';
      ma.checks.forEach(chk => {
        html += `<li class="pmcore-audit-check pmcore-audit-check--${esc(chk.status)}">
          ${auditBadge(chk.status)}
          <span class="pmcore-audit-name">${esc(chk.name)}</span>
          <span class="pmcore-audit-msg">${esc(chk.message)}</span>
        </li>`;
      });
      html += '</ul>';
    }

    const corrections = ma.corrections || {};
    const corrKeys = Object.keys(corrections);
    if (corrKeys.length) {
      html += '<div class="pmcore-corrections"><strong>Suggested corrections:</strong><ul>';
      corrKeys.forEach(k => {
        html += `<li>${esc(k)}: <code>${esc(JSON.stringify(corrections[k]))}</code></li>`;
      });
      html += '</ul></div>';
    }

    return html;
  }

  // ── Main form handler ───────────────────────────────────────────────────────

  function init() {
    const form      = document.getElementById('pmcore-form');
    const results   = document.getElementById('pmcore-results');
    const errorBox  = document.getElementById('pmcore-error');
    const submitBtn = document.getElementById('pmcore-submit');
    const btnText   = submitBtn && submitBtn.querySelector('.pmcore-btn-text');
    const spinner   = submitBtn && submitBtn.querySelector('.pmcore-spinner');
    const statusEl  = document.getElementById('pmcore-status');
    const copyBtn   = document.getElementById('pmcore-copy-btn');

    if (!form) return;

    // Copy button
    if (copyBtn) {
      copyBtn.addEventListener('click', function () {
        const prose = document.getElementById('pmcore-comm-body');
        const text  = prose ? prose.innerText : '';
        navigator.clipboard.writeText(text).then(function () {
          copyBtn.textContent = 'Copied!';
          setTimeout(function () { copyBtn.textContent = 'Copy'; }, 2000);
        });
      });
    }

    form.addEventListener('submit', async function (e) {
      e.preventDefault();

      const request  = document.getElementById('pmcore-request').value.trim();
      const commType = document.getElementById('pmcore-comm-type').value;

      if (!request) {
        showError('Please describe your project before submitting.');
        return;
      }

      // UI: loading state
      setLoading(true);
      clearError();
      results.style.display = 'none';
      setStatus('Sending to PMCore\u2026');

      try {
        const response = await fetch(API_URL + '/plan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ request, comm_request: commType }),
        });

        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${response.status}`);
        }

        const data = await response.json();

        // Render sections
        document.getElementById('pmcore-planner-body').innerHTML  = renderPlanner(data.planner);
        document.getElementById('pmcore-reasoner-body').innerHTML = renderReasoner(data.reasoner);
        document.getElementById('pmcore-comm-body').innerHTML     = renderCommunicator(data.communicator);
        document.getElementById('pmcore-audit-body').innerHTML    = renderMathAudit(data.math_audit);

        results.style.display = 'block';
        setStatus('Done.');
        results.scrollIntoView({ behavior: 'smooth', block: 'start' });

      } catch (err) {
        showError('PMCore request failed: ' + err.message);
        setStatus('');
      } finally {
        setLoading(false);
      }
    });

    function setLoading(on) {
      submitBtn.disabled = on;
      if (btnText) btnText.style.display = on ? 'none'  : '';
      if (spinner) spinner.style.display  = on ? 'inline-block' : 'none';
    }

    function setStatus(msg) {
      if (statusEl) statusEl.textContent = msg;
    }

    function showError(msg) {
      errorBox.textContent = msg;
      errorBox.style.display = 'block';
    }

    function clearError() {
      errorBox.textContent = '';
      errorBox.style.display = 'none';
    }
  }

  // Run after DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
