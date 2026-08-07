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

  /* --------------------------------------------------------- fake job queue
     The real POST /chat, /analyze, and /draft are all asynchronous: each
     returns 202 + status_url immediately, and the caller polls
     GET /api/matters/{matter}/jobs/{job} until status is
     succeeded/failed/cancelled (services/jobs.py, services/worker.py). The
     demo simulates that same shape for all three — stage names are copied
     verbatim from the real job bodies (chat_orchestrator.py,
     analysis_orchestrator.py) — so pollJob() in job-poller.js drives the
     demo exactly as it drives the real backend, and a visitor sees the same
     staged progress messaging. */

  const demoJobs = new Map();
  const CHAT_TOTAL_MS = 1500;
  const CHAT_STEPS = [
    { ms: 0,   stage: 'queued',             progress: 0 },
    { ms: 300, stage: 'retrieving_sources', progress: 35 },
    { ms: 950, stage: 'drafting_answer',    progress: 70 },
  ];
  const ANALYZE_TOTAL_MS = 900;
  const ANALYZE_STEPS = [
    { ms: 0,   stage: 'queued',            progress: 0 },
    { ms: 150, stage: 'analyzing',         progress: 30 },
    { ms: 450, stage: 'building_timeline', progress: 60 },
    { ms: 700, stage: 'scoring_strength',  progress: 85 },
  ];
  const DRAFT_TOTAL_MS = 1200;
  const DRAFT_STEPS = [
    { ms: 0,   stage: 'queued',            progress: 0 },
    { ms: 300, stage: 'drafting_document', progress: 55 },
  ];

  function stageFor(steps, elapsedMs) {
    let step = steps[0];
    for (const candidate of steps) {
      if (candidate.ms <= elapsedMs) step = candidate;
    }
    return step;
  }

  function createDemoJob(result, steps, totalMs) {
    const jobId = `demo-job-${Date.now()}-${Math.floor(Math.random() * 1e4)}`;
    demoJobs.set(jobId, { createdAt: Date.now(), result, steps, totalMs });
    return jobId;
  }

  function readDemoJob(jobId) {
    const job = demoJobs.get(jobId);
    if (!job) return null;
    const elapsed = Date.now() - job.createdAt;
    if (elapsed >= job.totalMs) {
      return { job_id: jobId, matter_id: FIXTURE.context_id, status: 'succeeded',
               progress: 100, stage: 'complete', result: job.result, error: null };
    }
    const step = stageFor(job.steps, elapsed);
    return { job_id: jobId, matter_id: FIXTURE.context_id, status: 'running',
             progress: step.progress, stage: step.stage, result: null, error: null };
  }

  function queuedJobResponse(jobId) {
    return { job_id: jobId, matter_id: FIXTURE.context_id, context_id: FIXTURE.context_id,
             status: 'queued', progress: 0, stage: 'queued',
             status_url: `/demo/jobs/${jobId}`, deduplicated: false };
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

    '/analyze': () => {
      const jobId = createDemoJob({
        status: 'success',
        analysis: clone(FIXTURE.analysis),
        timeline: clone(FIXTURE.timeline),
        statutes: clone(FIXTURE.statutes),
        strength: clone(FIXTURE.strength),
      }, ANALYZE_STEPS, ANALYZE_TOTAL_MS);
      return ok(queuedJobResponse(jobId));
    },

    '/chat': (body) => {
      // Matches the real POST /chat contract: acknowledge immediately with a
      // job_id + status_url, never the answer itself. script.js always polls
      // status_url now (routes/chat.py, services/task_queue.py).
      const jobId = createDemoJob({
        status: 'answer',
        intent: 'legal_research',
        message: DEMO_REPLY,
        grounded: true,
        citations: DEMO_CITATIONS,
        context_id: FIXTURE.context_id,
        matter_id: FIXTURE.context_id,
        title: FIXTURE.title,
      }, CHAT_STEPS, CHAT_TOTAL_MS);
      return ok(queuedJobResponse(jobId));
    },

    '/draft': () => {
      const jobId = createDemoJob({
        status: 'success', document: FIXTURE.draft, doc_type: 'memo',
      }, DRAFT_STEPS, DRAFT_TOTAL_MS);
      return ok(queuedJobResponse(jobId));
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

  // Real citation shape (BACKEND_ARCHITECTURE.md "Chat contract"): source_id,
  // source_type, title, locator, url, quote. url is empty for these — like
  // the rest of the fixture, every source here is fictional, not a live link.
  const DEMO_CITATIONS = [
    {
      source_id: 'statute-rc-2315-33', source_type: 'statute',
      title: 'R.C. 2315.33 — Comparative negligence', locator: 'Ohio Rev. Code', url: '',
      quote: 'Bars recovery where the claimant’s contributory fault exceeds the combined fault of all other parties; otherwise damages are reduced in proportion.',
    },
    {
      source_id: 'statute-rc-4511-46', source_type: 'statute',
      title: 'R.C. 4511.46 — Right of way of pedestrian in crosswalk', locator: 'Ohio Rev. Code', url: '',
      quote: 'Requires a driver to yield to a pedestrian lawfully within a marked crosswalk on the driver’s half of the roadway.',
    },
    {
      source_id: 'case-okonkwo-bayline', source_type: 'case_law',
      title: 'Okonkwo v. Bayline Municipal Transit Authority',
      locator: '171 Ohio App. 3d 690 (Fict. 2016)', url: '',
      quote: 'Pedestrian who entered a marked crossing on a changing signal was assigned twenty percent comparative fault; recovery reduced accordingly rather than barred.',
    },
  ];

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

    // pollJob() polls this exact status_url on an interval; the job id is
    // generated per-request, so this can't be a static ROUTES entry.
    const jobMatch = path.match(/^\/demo\/jobs\/(.+)$/);
    if (jobMatch) {
      const job = readDemoJob(jobMatch[1]);
      return job
        ? ok(job)
        : new Response(JSON.stringify({ error: 'job not found' }),
            { status: 404, headers: { 'Content-Type': 'application/json' } });
    }

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
