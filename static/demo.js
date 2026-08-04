/* ===========================================================================
   Case Closed — demo sandbox

   Loaded ONLY on /demo, before script.js. Replaces window.fetch so that every
   request the workspace makes is answered locally from the fixture. Nothing
   leaves the page: no Gemini, no CourtListener, no Firestore, no writes.

   The server half of the sandbox is routes/demo.py, which imports no service
   module at all. This file is the second, independent guarantee: even if a
   route were added later, the demo page still cannot call it.

   Every matter, party, document and authority in the fixture is synthetic and
   labelled as such.
   ========================================================================= */

(function () {
  'use strict';

  const root = document.querySelector('.app');
  if (!root || root.dataset.demo !== '1') return;

  const REAL_FETCH = window.fetch.bind(window);
  let FIXTURE = null;

  /* ------------------------------------------------------------ utilities */

  const ok = (body) => new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

  const clone = (v) => JSON.parse(JSON.stringify(v));

  /** Pretend the model is thinking, so the demo shows real loading states. */
  const think = (ms) => new Promise((r) => setTimeout(r, ms));

  function parseBody(init) {
    if (!init || !init.body) return {};
    try { return JSON.parse(init.body); } catch { return {}; }
  }

  /** Path only — the workspace calls same-origin relative URLs throughout. */
  function pathOf(input) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    try { return new URL(url, window.location.origin).pathname; }
    catch { return url; }
  }

  /* ------------------------------------------------------------- handlers */

  const ROUTES = {
    '/context': () => ok({
      context_id: FIXTURE.context_id,
      context: clone(FIXTURE),
      total_seconds: FIXTURE.total_seconds,
    }),

    '/contexts': () => ok({
      contexts: [{
        context_id: FIXTURE.context_id,
        title: FIXTURE.title,
        updated_at: FIXTURE.updated_at,
        total_seconds: FIXTURE.total_seconds,
      }],
      active_context_id: FIXTURE.context_id,
    }),

    '/contexts/switch': () => ok({ context_id: FIXTURE.context_id, context: clone(FIXTURE) }),

    // Mutations are acknowledged but never applied — the demo always resets
    // to the same matter, which is the point of a demo.
    '/contexts/new':    () => demoBlocked('Creating a new matter'),
    '/contexts/rename': () => demoBlocked('Renaming'),
    '/contexts/delete': () => demoBlocked('Deleting'),
    '/upload':          () => demoBlocked('Uploading documents'),
    '/documents/delete':() => demoBlocked('Deleting documents'),
    '/intake':          () => demoBlocked('Submitting the intake form'),
    '/draft/export':    () => demoBlocked('Exporting to Word'),

    '/documents/toggle': (body) => ok({ status: 'ok', included: !!body.included }),
    '/session/track-time': () => ok({ status: 'ok', total_seconds: FIXTURE.total_seconds }),
    '/timeline/add': (body) => {
      const events = clone(FIXTURE.timeline);
      events.push({
        date: body.date || '',
        description: body.description || '',
        category: 'event',
        source: 'manual',
      });
      events.sort((a, b) => String(a.date).localeCompare(String(b.date)));
      return ok({ timeline: events });
    },

    '/analyze': async () => {
      await think(900);
      return ok({
        analysis: clone(FIXTURE.analysis),
        timeline: clone(FIXTURE.timeline),
        statutes: clone(FIXTURE.statutes),
        strength: clone(FIXTURE.strength),
      });
    },

    '/chat': async () => {
      await think(1400);
      return ok({
        response: DEMO_REPLY,
        analysis: clone(FIXTURE.analysis),
        cases: clone(FIXTURE.cases),
        timeline: clone(FIXTURE.timeline),
        statutes: clone(FIXTURE.statutes),
        strength: clone(FIXTURE.strength),
        title: FIXTURE.title,
        context_id: FIXTURE.context_id,
      });
    },

    '/draft': async () => {
      await think(1200);
      return ok({ document: FIXTURE.draft, doc_type: 'memo' });
    },

    '/case/describe': async (body) => {
      await think(700);
      const c = FIXTURE.cases[body.case_index] || FIXTURE.cases[0];
      return ok({ description: c.snippet });
    },

    '/case/ask': async (body) => {
      await think(1100);
      const c = FIXTURE.cases[body.case_index] || FIXTURE.cases[0];
      const existing = (c.follow_ups && c.follow_ups[0] && c.follow_ups[0].answer);
      return ok({
        answer: existing || DEMO_FOLLOW_UP,
        case_title: c.title,
      });
    },

    '/case/treatment': async (body) => {
      await think(800);
      const c = FIXTURE.cases[body.case_index] || FIXTURE.cases[0];
      return ok({ treatment: clone(c.treatment) });
    },

    '/case/bookmark': (body) => {
      const c = FIXTURE.cases[body.case_index];
      if (c) c.bookmarked = !c.bookmarked;
      return ok({ status: 'ok', bookmarked: c ? c.bookmarked : false });
    },

    '/case/notes': (body, init) => {
      const c = FIXTURE.cases[body.case_index];
      if (c) {
        if ((init.method || 'POST').toUpperCase() === 'DELETE') {
          c.notes = '';
        } else {
          c.notes = body.notes || '';
          c.notes_updated_at = new Date().toISOString();
        }
      }
      return ok({ status: 'ok', notes_updated_at: c ? c.notes_updated_at : null });
    },

    '/search': (body) => ok({ results: localSearch(body.query || '') }),
  };

  function demoBlocked(action) {
    if (typeof showToast === 'function') {
      showToast(`${action} is disabled in the demo. Start a matter to use it.`, 'info');
    }
    return new Response(JSON.stringify({ error: `${action} is disabled in the demo.` }), {
      status: 403,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const DEMO_REPLY =
    'Comparative fault is the real exposure here, and it is bounded rather than fatal.\n\n' +
    'R.C. 2315.33 reduces recovery in proportion to the claimant\'s share of fault and only bars ' +
    'it entirely if her share exceeds everyone else\'s combined. On these facts that threshold is ' +
    'unlikely to be met: the signal was functioning, conditions were clear, and R.C. 4511.46 put ' +
    'the duty to yield on the driver.\n\n' +
    'The closest guidance in the retrieved authority assigned twenty percent to a pedestrian who ' +
    'entered on a changing signal, and reduced rather than barred recovery.\n\n' +
    'The gap worth closing is the municipal signal-timing record. It would move her entry from ' +
    'contested to documented. I have added it to the open items in the draft.\n\n' +
    'This is AI-assisted analysis and needs your review.';

  const DEMO_FOLLOW_UP =
    'The court treated the functioning signal as established and confined its analysis to the ' +
    'timing of entry, which is the same posture as this matter. It does not reach the question ' +
    'of a malfunctioning signal.';

  /** Cross-matter search, run against the single fixture matter. */
  function localSearch(query) {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const hits = [];
    const mark = (text) => {
      const s = String(text);
      const i = s.toLowerCase().indexOf(q);
      if (i < 0) return null;
      const from = Math.max(0, i - 40);
      const esc = (t) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      return (from ? '…' : '') + esc(s.slice(from, i)) +
             '<mark>' + esc(s.slice(i, i + q.length)) + '</mark>' +
             esc(s.slice(i + q.length, i + q.length + 90)) + '…';
    };

    const add = (type, title, text) => {
      const snippet = mark(text);
      if (snippet) hits.push({
        type, title, snippet,
        context_id: FIXTURE.context_id,
        session_title: FIXTURE.title,
        updated_at: FIXTURE.updated_at,
      });
    };

    add('session', FIXTURE.title, FIXTURE.title);
    FIXTURE.cases.forEach((c) => {
      add('case', c.title, `${c.title} ${c.citation} ${c.snippet}`);
      if (c.notes) add('note', c.title, c.notes);
    });
    FIXTURE.messages.forEach((m) => add('message', FIXTURE.title, m.content));
    (FIXTURE.analysis.facts || []).forEach((f) => add('description', FIXTURE.title, f));

    return hits.slice(0, 20);
  }

  /* ----------------------------------------------------------------- boot */

  window.fetch = async function (input, init) {
    const path = pathOf(input);
    const opts = init || {};

    // The fixture itself is the one real request this page is allowed to make.
    if (path === '/demo/fixture') return REAL_FETCH(input, init);

    // script.js reads the context immediately on load, which can beat the
    // fixture request. Every handler needs FIXTURE, so gate them all on it.
    await ready;

    const handler = ROUTES[path];
    if (handler) return handler(parseBody(opts), opts);

    // Anything unrecognised is refused rather than passed through, so a route
    // added later cannot silently escape the sandbox.
    console.warn('[demo] blocked request to', path);
    return new Response(JSON.stringify({ error: 'Not available in the demo.' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  // Hoisted above the fetch override by `var` semantics of function scope —
  // declared here but awaited inside the shim, which only ever runs later.
  var ready = REAL_FETCH('/demo/fixture')
    .then((r) => r.json())
    .then((data) => { FIXTURE = data; })
    .catch(() => { FIXTURE = { cases: [], messages: [], analysis: {}, timeline: [], statutes: [] }; });

  window.__demoReady = ready;
})();
