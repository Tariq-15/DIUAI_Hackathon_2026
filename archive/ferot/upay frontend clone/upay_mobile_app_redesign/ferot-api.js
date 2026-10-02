/**
 * Ferot API bridge for the upay-style wallet pages (customer.html and index.html).
 *
 * The pages call the real Ferot backend: Guard checks before a send, complaint intake, case status,
 * and (on the showcase page) the staff case file. FastAPI serves these pages at /upay/, so the API
 * is on the same origin. Add ?api=https://your-ferot-host to point a static copy (e.g. Vercel) at a
 * running backend; that host must list the page's origin in FEROT_CORS_ORIGINS.
 * If no backend answers, the pages fall back to their built-in offline simulation.
 *
 * All customers and numbers are synthetic (rule R16). This is a prototype, not an upay product (R15).
 */
(function () {
  const params = new URLSearchParams(window.location.search);
  const base = (params.get('api') || window.FEROT_API_BASE || '').replace(/\/+$/, '');
  const root = `${base}/api/v1`;

  async function request(path, { method = 'GET', body, staff = false, timeout = 15000 } = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (staff) {
      // Prototype only: the showcase reads the case file as a demo agent. Production takes identity from SSO.
      headers['X-Ferot-Actor'] = 'showcase-agent';
      headers['X-Ferot-Role'] = 'agent';
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    try {
      const res = await fetch(root + path, {
        method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: ctrl.signal,
      });
      let data = null;
      try { data = await res.json(); } catch (e) { /* not JSON */ }
      if (!res.ok) {
        const detail = data && data.detail;
        throw new Error(typeof detail === 'string' ? detail : (detail ? JSON.stringify(detail) : res.statusText));
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  const BN_DIGITS = '০১২৩৪৫৬৭৮৯';
  const BN_MONTHS = ['জানুয়ারি', 'ফেব্রুয়ারি', 'মার্চ', 'এপ্রিল', 'মে', 'জুন', 'জুলাই', 'আগস্ট', 'সেপ্টেম্বর', 'অক্টোবর', 'নভেম্বর', 'ডিসেম্বর'];

  const bn = (v) => String(v).replace(/[0-9]/g, (d) => BN_DIGITS[d]);
  const ascii = (v) => String(v).replace(/[০-৯]/g, (d) => String(BN_DIGITS.indexOf(d))).replace(/\D/g, '');
  const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  window.Ferot = {
    base,
    connect: () => request('/health', { timeout: 8000 }).then((h) => (h && h.ok ? h : null)).catch(() => null),
    customers: () => request('/demo/customers'),
    guardCheck: (body) => request('/guard/check', { method: 'POST', body }),
    guardDecision: (id, decision) => request(`/guard/${encodeURIComponent(id)}/decision`, { method: 'POST', body: { decision } }),
    preview: (text) => request('/complaints/preview', { method: 'POST', body: { text } }),
    complain: (body) => request('/complaints', { method: 'POST', body }),
    status: (id) => request(`/cases/${encodeURIComponent(id)}/status`),
    contest: (id, reason) => request(`/cases/${encodeURIComponent(id)}/contest`, { method: 'POST', body: { reason } }),
    caseFile: (id) => request(`/cases/${encodeURIComponent(id)}`, { staff: true }),
    consoleUrl: (id) => `${base}/#/console/case/${encodeURIComponent(id)}`,

    bn,
    ascii,
    esc,
    /** 01055501234 -> 010555-01234, the way the app shows wallet numbers */
    phone: (w) => (/^\d{11}$/.test(w) ? `${w.slice(0, 6)}-${w.slice(6)}` : w),
    taka: (v) => `৳ ${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    /** ISO time from the synthetic ledger -> "২৭ আগস্ট, ১৪:০২" */
    when: (iso) => {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return iso;
      const hh = String(d.getHours()).padStart(2, '0');
      const mm = String(d.getMinutes()).padStart(2, '0');
      return `${bn(d.getDate())} ${BN_MONTHS[d.getMonth()]}, ${bn(hh)}:${bn(mm)}`;
    },
    /** ISO date -> "১০ সেপ্টেম্বর ২০২৬" */
    day: (iso) => {
      const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso));
      return m ? `${bn(Number(m[3]))} ${BN_MONTHS[Number(m[2]) - 1]} ${bn(m[1])}` : String(iso);
    },
  };
})();
