// Global State Management
// Keep these in sync with the backend state model

function showToast(message, type = 'success') {
    const region = document.getElementById('toast-region') || document.body;
    const existing = document.getElementById('app-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.id = 'app-toast';
    toast.className = `app-toast app-toast-${type}`;
    toast.textContent = message;
    region.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('visible'));

    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/* ===========================================================================
   Modal controller

   Every dialog previously toggled its own inline style.display and had no
   focus management at all: no trap, no Esc, no scroll lock, no focus
   restore. One controller now owns all six.
   ========================================================================= */

const FOCUSABLE = [
    'a[href]', 'button:not([disabled])', 'input:not([disabled])',
    'select:not([disabled])', 'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])'
].join(',');

let _modalStack = [];

function _resolveModal(ref) {
    return typeof ref === 'string' ? document.getElementById(ref) : ref;
}

function openModal(ref) {
    const el = _resolveModal(ref);
    if (!el || _modalStack.includes(el)) return;

    el._returnFocus = document.activeElement;
    el.hidden = false;
    _modalStack.push(el);
    document.body.style.overflow = 'hidden';

    const first = el.querySelector('[data-autofocus]') || el.querySelector(FOCUSABLE);
    if (first) requestAnimationFrame(() => first.focus());
}

function closeModal(ref) {
    const el = _resolveModal(ref);
    if (!el || el.hidden) return;

    el.hidden = true;
    _modalStack = _modalStack.filter(m => m !== el);
    if (!_modalStack.length) document.body.style.overflow = '';

    const back = el._returnFocus;
    if (back && document.contains(back)) back.focus();
    el._returnFocus = null;
}

function topModal() {
    return _modalStack[_modalStack.length - 1] || null;
}

// Focus trap + click-outside-to-dismiss, bound once.
document.addEventListener('keydown', (e) => {
    if (e.key !== 'Tab') return;
    const modal = topModal();
    if (!modal) return;

    const items = [...modal.querySelectorAll(FOCUSABLE)].filter(el => el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];

    if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
    }
}, true);

document.addEventListener('mousedown', (e) => {
    const modal = topModal();
    // A click on the scrim itself, never on the panel inside it.
    if (modal && e.target === modal) closeModal(modal);
});

// Redirect to login on 401 (session expired / not authenticated)
(function () {
    const nativeFetch = window.fetch.bind(window);
    window.fetch = function (...args) {
        return nativeFetch(...args).then(function (response) {
            if (response.status === 401) {
                window.location.href = '/auth/login';
            }
            return response;
        });
    };
})();
const chatBox = document.querySelector('#chat-box');
const chatForm = document.querySelector('#chat-form');
const chatInput = document.querySelector('#chat-input');
const uploadBtn = document.querySelector('#upload-btn');
const pdfInput = document.querySelector('#pdf-input');
const analyzeBtn = document.querySelector('#analyze-btn');
const draftBtn = document.querySelector('#draft-btn');
const draftGenerateBtn = document.querySelector('#draft-generate-btn');
let currentUploadedDocs = [];
const roleToggleBtn = document.getElementById('role-toggle');
const roleMenuEl = document.getElementById('role-menu');
const roleSelectedTextEl = document.getElementById('role-selected-text');
const roleOptionsEls = document.querySelectorAll('.role-option');
let selectedRole = 'defendant';
const sidebarEl = document.querySelector('#sidebar');
const sidebarToggleBtn = document.querySelector('#sidebar-toggle');
const sidebarBackdrop = document.querySelector('#sidebar-backdrop');
const sessionListEl = document.querySelector('#session-list');
const newSessionBtn = document.querySelector('#new-session-btn');
const deleteModal = document.querySelector('#delete-modal');
const deleteCancelBtn = document.querySelector('#delete-cancel');
const deleteConfirmBtn = document.querySelector('#delete-confirm');
let clarifyMode = false;
let clarificationAnswers = [];
let clarifyAttempts = 0;
let contextId = null;
let currentAnalysis = {};
let currentTimeline = [];
let currentStatutes = [];
let currentStrength = {};
let currentCases = [];
let currentDraft = null;
let sessionHistory = [];
let pendingDeleteContextId = null;
let casesViewState = 'list';
let currentCasesFilter = 'all';
let activeCaseIndex = null;

let sessionSecondsAccumulated = 0;
let lastActivityTime = Date.now();
let timerInterval = null;
let pendingSecondsToSync = 0;
const IDLE_THRESHOLD_MS = 60000; // 1 minute idle = pause

function formatTime(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

function updateTimerDisplay() {
    const display = document.getElementById('session-timer');
    if (display) display.textContent = formatTime(sessionSecondsAccumulated);
}

function startSessionTimer(initialSeconds = 0) {
    stopSessionTimer();
    sessionSecondsAccumulated = initialSeconds;
    lastActivityTime = Date.now();
    updateTimerDisplay();
    
    timerInterval = setInterval(() => {
        const now = Date.now();
        const timeSinceActivity = now - lastActivityTime;
        
        if (timeSinceActivity < IDLE_THRESHOLD_MS) {
            sessionSecondsAccumulated += 1;
            pendingSecondsToSync += 1;
            updateTimerDisplay();
            
            // Also update the sidebar card for the active session live (locally only)
            const session = sessionHistory.find(s => s.context_id === contextId);
            if (session) {
                session.total_seconds = (session.total_seconds || 0) + 1;
                // Update just the time display element directly without full re-render
                const card = document.querySelector(`.session-card[data-context-id="${CSS.escape(contextId)}"]`);
                if (card) {
                    const timeEl = card.querySelector('.session-time-display');
                    if (timeEl) timeEl.textContent = `⏱ ${formatTime(session.total_seconds)}`;
                }
            }
            
            // Sync to backend every 30 seconds (separate from display)
            if (pendingSecondsToSync >= 30) {
                syncTimeToBackend();
            }
        }
    }, 1000);
}

function stopSessionTimer() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
    if (pendingSecondsToSync > 0) {
        syncTimeToBackend();
    }
}

function syncTimeToBackend() {
    if (!contextId || pendingSecondsToSync === 0) return;
    const seconds = pendingSecondsToSync;
    pendingSecondsToSync = 0;
    
    console.log('[SYNC] Sending', seconds, 'seconds for context', contextId);
    fetch('/session/track-time', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ context_id: contextId, seconds })
    })
    .then(r => { console.log('[SYNC] Response status:', r.status); return r.json(); })
    .then(data => {
        console.log('[SYNC] Response data:', data);
        const session = sessionHistory.find(s => s.context_id === contextId);
        if (session && data.total_seconds !== undefined) {
            session.total_seconds = data.total_seconds;
        }
    })
    .catch(() => { pendingSecondsToSync += seconds; });
}

// Track user activity
['click', 'keydown', 'mousemove', 'scroll'].forEach(event => {
    document.addEventListener(event, () => {
        lastActivityTime = Date.now();
    });
});

// Sync on page unload
window.addEventListener('beforeunload', () => {
    if (pendingSecondsToSync > 0 && contextId) {
        // Use sendBeacon for reliable unload-time sending
        const data = JSON.stringify({ context_id: contextId, seconds: pendingSecondsToSync });
        navigator.sendBeacon('/session/track-time', new Blob([data], { type: 'application/json' }));
        pendingSecondsToSync = 0;
    }
});

/* ----- Voice Input Feature ----- */
let recognition = null;
let isRecording = false;
let interimTranscript = '';
let baseInputValue = '';

function formatTranscript(text) {
    if (!text) return text;
    // Capitalize first letter of the entire text
    text = text.charAt(0).toUpperCase() + text.slice(1);
    // Capitalize first letter after sentence-ending punctuation (. ! ?)
    text = text.replace(/([.!?]\s+)([a-z])/g, (match, p1, p2) => p1 + p2.toUpperCase());
    // Capitalize "i" when used as a pronoun (standalone)
    text = text.replace(/\bi\b/g, 'I');
    // Capitalize common proper nouns/starts
    text = text.replace(/\bi'(m|ve|ll|d)\b/gi, (match) => 'I\'' + match.slice(2));
    // Add period at the end if the text doesn't end with punctuation
    if (text.length > 0 && !/[.!?,;:]$/.test(text.trim())) {
        text = text.trim() + '.';
    }
    return text;
}

function initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        const micBtn = document.getElementById('mic-btn');
        if (micBtn) {
            micBtn.style.display = 'none';
            console.warn('Speech recognition not supported in this browser');
        }
        return;
    }
    
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
    
    recognition.onresult = (event) => {
        let finalTranscript = '';
        let interim = '';
        
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += transcript + ' ';
            } else {
                interim += transcript;
            }
        }
        
        const input = document.getElementById('chat-input');
        if (finalTranscript) {
            finalTranscript = formatTranscript(finalTranscript.replace(/\s+/g, ' ').trim());
            baseInputValue = baseInputValue.trimEnd() + (baseInputValue ? ' ' : '') + finalTranscript;
        }
        interim = interim.replace(/\s+/g, ' ').trim();
        input.value = baseInputValue + interim;
        
        if (finalTranscript) {
            input.classList.add('voice-typing');
            setTimeout(() => input.classList.remove('voice-typing'), 400);
        }
        
        input.dispatchEvent(new Event('input'));
    };
    
    recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        stopRecording();
        if (event.error === 'not-allowed') {
            showToast('Microphone access denied', 'error');
        } else if (event.error !== 'aborted') {
            showToast('Voice input error: ' + event.error, 'error');
        }
    };
    
    recognition.onend = () => {
        if (isRecording) {
            try { recognition.start(); } catch(e) {}
        }
    };
}

function startRecording() {
    if (!recognition) return;
    
    const input = document.getElementById('chat-input');
    baseInputValue = input.value.trimEnd() + (input.value.trim() ? ' ' : '');
    
    try {
        recognition.start();
        isRecording = true;
        input.classList.add('voice-active');
        const micBtn = document.getElementById('mic-btn');
        micBtn.classList.add('recording');
        micBtn.title = 'Click to stop dictation';
        showToast('Listening...', 'info');
    } catch (e) {
        console.error('Failed to start recording:', e);
    }
}

function stopRecording() {
    isRecording = false;
    if (recognition) {
        try { recognition.stop(); } catch(e) {}
    }
    const input = document.getElementById('chat-input');
    if (input && input.value.trim()) {
        let val = input.value.trim();
        val = val.charAt(0).toUpperCase() + val.slice(1);
        input.value = val;
    }

    const micBtn = document.getElementById('mic-btn');
    if (micBtn) {
        micBtn.classList.remove('recording');
        micBtn.title = 'Click to dictate';
    }
    if (input) input.classList.remove('voice-active');
}

function toggleRecording() {
    if (isRecording) {
        stopRecording();
    } else {
        startRecording();
    }
}

/* Init & Setup
 * TODO: Consider moving to TypeScript for better type safety
 * Fix: CASE-245 - Add error handling for context load failure
 */
document.addEventListener('DOMContentLoaded', async () => {
    initSpeechRecognition();
    document.getElementById('mic-btn')?.addEventListener('click', toggleRecording);
    // Show loading skeletons until initial data arrives.
    showChatSkeleton();
    showAnalysisSkeleton();
    showCasesSkeleton();
    showDraftSkeleton();

    await _gsLoadRecent();
    // Load context on page load
    await loadContext();
    await loadSessionHistory();
    setupSidebar();

    // Setup tab switching
    setupTabs();

    // Setup event listeners
    setupEventListeners();
    setupMainContentSidebarClose();
    setupIntakeModal();
});

// =====================================================
// TAB SWITCHING
// =====================================================
function setupTabs() {
    const tabs = document.querySelectorAll('.panel-tab');
    const tabContents = document.querySelectorAll('.panel-tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetTab = tab.getAttribute('data-tab');

            tabs.forEach(t => {
                const on = t === tab;
                t.classList.toggle('active', on);
                t.setAttribute('aria-selected', String(on));
            });
            tabContents.forEach(tc => {
                const on = tc.id === `tab-${targetTab}`;
                tc.classList.toggle('active', on);
                tc.hidden = !on;
            });
        });
    });

    // Authority holds two kinds of law. Case law and statutes answer the same
    // question, so they share a panel and switch inside it.
    document.querySelectorAll('.authority-switch__btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const kind = btn.dataset.authority;
            document.querySelectorAll('.authority-switch__btn').forEach(b => {
                const on = b === btn;
                b.classList.toggle('active', on);
                b.setAttribute('aria-selected', String(on));
            });
            document.querySelectorAll('[data-authority-panel]').forEach(p => {
                p.hidden = p.dataset.authorityPanel !== kind;
            });
        });
    });
}

/** Keeps the matter caption in the header honest about the active matter. */
function updateMatterHeader(context) {
    const titleEl = document.getElementById('matter-title');
    const metaEl = document.getElementById('matter-meta');
    if (!titleEl || !metaEl) return;

    const ctx = context || {};
    titleEl.textContent = ctx.title || 'New matter';

    const intake = ctx.intake || {};
    const analysis = ctx.analysis || {};
    const jurisdiction = intake.jurisdiction
        || (Array.isArray(analysis.jurisdictions) && analysis.jurisdictions[0])
        || '';
    const bits = [intake.legal_category, jurisdiction, intake.court_level].filter(Boolean);
    const docCount = Array.isArray(ctx.uploaded_documents) ? ctx.uploaded_documents.length : 0;
    if (docCount) bits.push(`${docCount} document${docCount === 1 ? '' : 's'}`);

    metaEl.textContent = bits.length
        ? bits.join(' · ')
        : 'Describe the matter or upload a document to begin';

    const docBadge = document.getElementById('doc-count');
    if (docBadge) {
        docBadge.textContent = docCount || '';
        docBadge.hidden = !docCount;
    }
}

/** Authority tab count reflects retrieved case law. */
function updateAuthorityCount(cases) {
    const el = document.getElementById('authority-count');
    if (!el) return;
    const n = Array.isArray(cases) ? cases.length : 0;
    el.textContent = n || '';
    el.hidden = !n;
}

// =====================================================
// EVENT LISTENERS
// =====================================================
function setupEventListeners() {
    // Document Upload
    document.getElementById('upload-btn')?.addEventListener('click', () => {
        if (typeof currentUploadedDocs !== 'undefined' && currentUploadedDocs.length > 0) {
            openDocManager();
        } else {
            document.getElementById('file-upload-input').click();
        }
    });
    document.getElementById('file-upload-input')?.addEventListener('change', handleFileUpload);

    // Analyze button
    analyzeBtn.addEventListener('click', handleAnalyze);

    // Draft button
    draftBtn.addEventListener('click', () => {
        // Switch to draft tab
        document.querySelector('[data-tab="draft"]').click();
    });

    // Draft generate button
    draftGenerateBtn.addEventListener('click', handleDraftGenerate);

    
    // Draft Export button
    const exportBtn = document.getElementById('draft-export-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', handleDraftExport);
    }

    // Shortcuts and Switching bindings
    document.getElementById('shortcuts-close')?.addEventListener('click', () => {
        closeModal('shortcuts-modal');
    });

    const isMac = navigator.platform.toUpperCase().includes('MAC');
    const cmdKey = isMac ? '⌘' : 'Ctrl+';
    document.querySelectorAll('.shortcut-keys').forEach(el => {
       el.textContent = el.textContent.replace('⌘', cmdKey);
    });

    const _gsInput = document.getElementById('quick-switcher-input');
    if (_gsInput) {
        _gsInput.addEventListener('input', (e) => {
            _globalSearchOnInput(e.target.value);
        });
        _gsInput.addEventListener('keydown', _globalSearchKeydown);
    }
    // Bind filter tab clicks
    document.querySelectorAll('.global-search-filter').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.global-search-filter').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            _gsActiveFilter = btn.getAttribute('data-filter');
            _globalSearchRenderFiltered();
        });
    });

    document.getElementById('time-report-btn')?.addEventListener('click', openTimeReport);
    document.getElementById('time-report-close')?.addEventListener('click', () => {
        closeModal('time-report-modal');
    });

    // Chat form
    chatForm.addEventListener('submit', handleChatSubmit);

    // Handle multi-line input: Enter submits, Shift+Enter creates new line
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });

    // Auto-resize textarea
    chatInput.addEventListener('input', autoResizeTextarea);

    // Role dropdown (custom, replaces native <select>)
    if (roleToggleBtn && roleMenuEl && roleSelectedTextEl && roleOptionsEls) {
        // Default selection: Defendant
        roleOptionsEls.forEach((opt) => {
            const isDefendant = String(opt.dataset.value || '').toLowerCase() === 'defendant';
            opt.classList.toggle('active', isDefendant);
        });
        roleSelectedTextEl.textContent = 'Defendant';
        selectedRole = 'defendant';

        roleToggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            roleMenuEl.classList.toggle('show');
        });

        roleOptionsEls.forEach((opt) => {
            opt.addEventListener('click', (e) => {
                e.stopPropagation();
                const val = String(opt.dataset.value || '').toLowerCase();
                selectedRole = val;
                roleOptionsEls.forEach((o) => {
                    const ov = String(o.dataset.value || '').toLowerCase();
                    o.classList.toggle('active', ov === val);
                });
                roleSelectedTextEl.textContent = (opt.textContent || '').trim() || 'Defendant';
                roleMenuEl.classList.remove('show');
            });
        });

        document.addEventListener('click', () => {
            roleMenuEl.classList.remove('show');
        });
    }
}

function setupIntakeModal() {
    const intakeBtn = document.getElementById('intake-btn');
    const modal = document.getElementById('intake-modal');
    const closeBtn = document.getElementById('intake-close');
    const cancelBtn = document.getElementById('intake-cancel-btn');
    const submitBtn = document.getElementById('intake-submit-btn');
    const addDateBtn = document.getElementById('intake-add-date');
    const datesContainer = document.getElementById('intake-dates-container');

    function resetIntakeForm() {
        document.getElementById('intake-case-title').value = '';
        document.getElementById('intake-legal-category').value = '';
        document.getElementById('intake-jurisdiction').value = '';
        document.getElementById('intake-court-level').value = '';
        const roleRadios = document.querySelectorAll('input[name="intake-role"]');
        roleRadios.forEach(r => r.checked = false);
        document.getElementById('intake-description').value = '';
        document.getElementById('intake-prior-actions').value = '';
        document.getElementById('intake-opposing-party').value = '';
        datesContainer.innerHTML = `
            <div class="intake-date-row">
                <input type="date" class="intake-date-input" />
                <input type="text" class="intake-date-label" placeholder="What happened on this date?" />
            </div>
        `;
        // Clear errors
        const fields = document.querySelectorAll('.intake-error');
        fields.forEach(f => f.classList.remove('intake-error'));
        submitBtn.disabled = false;
        submitBtn.textContent = 'Submit & Analyze';
    }

    if (intakeBtn) {
        intakeBtn.addEventListener('click', () => {
             if (!contextId) {
                 resetIntakeForm();
             }
             openModal(modal);
        });
    }

    if (closeBtn) closeBtn.addEventListener('click', () => closeModal(modal));
    if (cancelBtn) cancelBtn.addEventListener('click', () => closeModal(modal));

    if (addDateBtn) {
        addDateBtn.addEventListener('click', () => {
            const row = document.createElement('div');
            row.className = 'intake-date-row';
            row.innerHTML = `
                <input type="date" class="intake-date-input" />
                <input type="text" class="intake-date-label" placeholder="What happened on this date?" />
            `;
            datesContainer.appendChild(row);
        });
    }

    if (submitBtn) {
         submitBtn.addEventListener('click', async () => {
             const title = document.getElementById('intake-case-title');
             const cat = document.getElementById('intake-legal-category');
             const jur = document.getElementById('intake-jurisdiction');
             const role = document.querySelector('input[name="intake-role"]:checked');
             const desc = document.getElementById('intake-description');
             const roleRadiosGrp = document.querySelector('.intake-radio-group');

             let hasError = false;
             const required = [title, cat, jur, desc];
             required.forEach(el => {
                 if (!el.value.trim()) {
                     el.classList.add('intake-error');
                     hasError = true;
                 } else {
                     el.classList.remove('intake-error');
                 }
             });

             if (!role) {
                 roleRadiosGrp.style.border = '1px solid #CC0000';
                 roleRadiosGrp.style.padding = '4px';
                 roleRadiosGrp.style.borderRadius = '8px';
                 hasError = true;
             } else {
                 roleRadiosGrp.style.border = 'none';
                 roleRadiosGrp.style.padding = '0';
             }

             if (hasError) return;

             const dateRows = datesContainer.querySelectorAll('.intake-date-row');
             const keyDates = [];
             dateRows.forEach(r => {
                 const d = r.querySelector('.intake-date-input').value;
                 const l = r.querySelector('.intake-date-label').value;
                 if (d || l) keyDates.push({ date: d, label: l });
             });

             const payload = {
                 context_id: contextId,
                 case_title: title.value.trim(),
                 legal_category: cat.value,
                 jurisdiction: jur.value,
                 court_level: document.getElementById('intake-court-level').value,
                 user_role: role.value,
                 description: desc.value.trim(),
                 key_dates: keyDates,
                 prior_legal_actions: document.getElementById('intake-prior-actions').value.trim(),
                 opposing_party: document.getElementById('intake-opposing-party').value.trim()
             };

             submitBtn.disabled = true;
             submitBtn.textContent = 'Analyzing...';
             document.body.style.cursor = 'wait';

             try {
                const res = await fetch('/intake', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();

                if (!res.ok) throw new Error(data.error || 'Server error');

                contextId = data.context_id;
                await pollJob(data.status_url, {
                    onUpdate: job => {
                        const stage = String(job.stage || 'analyzing').replace(/_/g, ' ');
                        submitBtn.textContent = `${stage.charAt(0).toUpperCase()}${stage.slice(1)}…`;
                    },
                });

                // The job persists analysis/timeline/statutes/strength and the
                // intake route already persisted title/description/messages
                // synchronously, so reloading the matter picks up all of it.
                await loadContext();
                await loadSessionHistory();
                document.querySelector('[data-tab="record"]').click();

                closeModal(modal);
                showToast('Case intake submitted and analyzed', 'success');
             } catch (err) {
                 alert('Error processing intake: ' + err.message);
                 submitBtn.disabled = false;
                 submitBtn.textContent = 'Submit & Analyze';
             } finally {
                 document.body.style.cursor = 'default';
             }
         });
    }
}

function setupMainContentSidebarClose() {
    const selectors = [
        '.chat-box',
        '.panel-tab',
        '.chat-form',
        '.toolbar-btn',
        '#sidebar-backdrop',
        '#chat-input',
        '.send-btn',
        '.panel-content',
        '.chat-pane'
    ];
    const closeIfOpen = () => {
        if (!document.body.classList.contains('sidebar-collapsed')) {
            document.body.classList.add('sidebar-collapsed');
            updateSidebarToggleIcon();
        }
    };
    selectors.forEach((selector) => {
        document.querySelectorAll(selector).forEach((el) => {
            el.addEventListener('click', closeIfOpen);
        });
    });
}

function showChatSkeleton() {
    const box = document.querySelector('.chat-box') || document.getElementById('chat-box');
    if (!box) return;
    box.innerHTML = `
      <div class="skeleton-block">
        <div class="skeleton skeleton-bubble ai"></div>
        <div class="skeleton skeleton-bubble user"></div>
        <div class="skeleton skeleton-bubble ai"></div>
      </div>
    `;
}

function showAnalysisSkeleton() {
    const panel = document.getElementById('record-content') || document.querySelector('#tab-record .panel-section');
    if (panel) {
        panel.innerHTML = `
          <div class="skeleton-block">
            <div class="skeleton skeleton-title"></div>
            <div class="skeleton skeleton-line long"></div>
            <div class="skeleton skeleton-line full"></div>
            <div class="skeleton skeleton-line medium"></div>
            <div class="skeleton skeleton-line long"></div>
            <div class="skeleton skeleton-line short"></div>
          </div>
        `;
    }
}

function showCasesSkeleton() {
    const panel = document.getElementById('cases-content') || document.querySelector('#tab-authority .panel-section');
    if (panel) {
        panel.innerHTML = `
          <div class="skeleton-block">
            <div class="skeleton skeleton-card"></div>
            <div class="skeleton skeleton-card"></div>
            <div class="skeleton skeleton-card"></div>
          </div>
        `;
    }
}

function showDraftSkeleton() {
    const panel = document.getElementById('draft-content') || document.querySelector('#tab-draft .panel-section');
    if (panel) {
        panel.innerHTML = `
          <div class="skeleton-block">
            <div class="skeleton skeleton-title"></div>
            <div class="skeleton skeleton-line full"></div>
            <div class="skeleton skeleton-line long"></div>
            <div class="skeleton skeleton-line full"></div>
            <div class="skeleton skeleton-line medium"></div>
            <div class="skeleton skeleton-line full"></div>
            <div class="skeleton skeleton-line long"></div>
            <div class="skeleton skeleton-line short"></div>
          </div>
        `;
    }
}

// =====================================================
// CONTEXT MANAGEMENT
// =====================================================
async function loadContext() {
    try {
        const res = await fetch('/context');
        const data = await res.json();
        if (data.context) {
            data.context.total_seconds = data.total_seconds || data.context.total_seconds || 0;
        }
        applyContextToUI(data.context_id, data.context);
    } catch (err) {
        console.error('Error loading context:', err);
    }
}

async function loadSessionHistory() {
    try {
        const res = await fetch('/contexts');
        const data = await res.json();
        sessionHistory = data.contexts || [];
        console.log('[LOAD-HISTORY] Sessions:', sessionHistory.map(s => ({ id: s.context_id, total: s.total_seconds })));
        if (data.active_context_id && !contextId) {
            contextId = data.active_context_id;
        }
        renderSessionList();
    } catch (err) {
        console.error('Error loading session history:', err);
    }
}

function setupSidebar() {
    // Keep sidebar hidden by default; toggle button remains visible.
    document.body.classList.add('sidebar-collapsed');
    updateSidebarToggleIcon();

    if (sidebarToggleBtn) {
        sidebarToggleBtn.addEventListener('click', toggleSidebar);
    }
    if (sidebarBackdrop) {
        sidebarBackdrop.addEventListener('click', closeSidebar);
    }
    if (newSessionBtn) {
        newSessionBtn.addEventListener('click', handleNewSession);
    }
    if (sessionListEl) {
        sessionListEl.addEventListener('click', handleSessionListClick);
    }
    if (deleteCancelBtn) {
        deleteCancelBtn.addEventListener('click', hideDeleteModal);
    }
    if (deleteConfirmBtn) {
        deleteConfirmBtn.addEventListener('click', confirmDeleteSession);
    }
    if (deleteModal) {
        deleteModal.addEventListener('click', (e) => {
            if (e.target === deleteModal) {
                hideDeleteModal();
            }
        });
    }
}

function typeTitle(element, text, speed = 40, cardEl = null) {
    element.textContent = '';
    element.setAttribute('data-animate-title', 'true');
    let i = 0;
    function type() {
        if (i < text.length) {
            element.textContent += text.charAt(i);
            i++;
            setTimeout(type, speed);
        } else {
            element.removeAttribute('data-animate-title');
            if (cardEl) {
                cardEl.removeAttribute('data-animate-title');
            }
        }
    }
    type();
}

function renderSessionList() {
    console.log('[RENDER] Rendering sidebar with active contextId:', contextId);
    if (!sessionListEl) return;
    if (!sessionHistory.length) {
        sessionListEl.innerHTML = '<p class="sidebar-empty">No sessions yet.</p>';
        return;
    }
    sessionListEl.innerHTML = sessionHistory.map((item) => {
        const isActive = item.context_id === contextId;
        const titleText = item.title || 'New Session';
        const title = escapeHtml(titleText);
        const ts = formatRelativeTime(item.updated_at || item.created_at);
        const animateAttr = item._animateTitleNext ? ' data-animate-title="true"' : '';
        return `
            <div class="session-card ${isActive ? 'active' : ''}" data-context-id="${escapeHtml(item.context_id)}" title="${escapeHtml(titleText)}"${animateAttr}>
                <div class="session-main">
                    <div class="session-title">${title}</div>
                    <div class="session-time">${escapeHtml(ts)}</div>
                    <div class="session-time-display">⏱ ${formatTime(item.total_seconds || 0)}</div>
                </div>
                <button type="button" class="session-menu-btn" data-menu-btn="${escapeHtml(item.context_id)}">...</button>
                <div class="session-menu" data-menu="${escapeHtml(item.context_id)}">
                    <button type="button" data-action="rename" data-context-id="${escapeHtml(item.context_id)}">Rename</button>
                    <button type="button" data-action="delete" data-context-id="${escapeHtml(item.context_id)}">Delete</button>
                </div>
            </div>
        `;
    }).join('');
    sessionListEl.querySelectorAll('.session-card[data-animate-title="true"]').forEach((cardEl) => {
        const titleEl = cardEl.querySelector('.session-title');
        if (!titleEl) return;
        const fullText = titleEl.textContent || '';
        typeTitle(titleEl, fullText, 40, cardEl);
    });
    sessionHistory.forEach((item) => {
        delete item._animateTitleNext;
    });
}

function formatRelativeTime(isoString) {
    if (!isoString) return 'just now';
    const then = new Date(isoString).getTime();
    if (Number.isNaN(then)) return 'just now';
    const diffMs = Date.now() - then;
    const minutes = Math.floor(diffMs / 60000);
    const hours = Math.floor(diffMs / 3600000);
    const days = Math.floor(diffMs / 86400000);
    if (minutes < 1) return 'just now';
    if (minutes < 60) return `${minutes} min ago`;
    if (hours < 24) return `${hours} hr ago`;
    if (days === 1) return 'yesterday';
    return `${days} days ago`;
}

function applyContextToUI(nextContextId, context) {
    contextId = nextContextId || contextId;
    const safeContext = context || {};
    currentUploadedDocs = safeContext.uploaded_documents || [];
    
    console.log('[TIMER] Starting with saved seconds:', safeContext.total_seconds || 0);
    startSessionTimer(safeContext.total_seconds || 0);
    currentAnalysis = safeContext.analysis || {};
    currentTimeline = safeContext.timeline || [];
    currentStatutes = safeContext.statutes || [];
    currentStrength = safeContext.strength || {};
    currentCases = safeContext.cases || [];

    renderChatFromContext(safeContext);
    updateMatterHeader(safeContext);
    updateAnalysisPanel(currentAnalysis);
    updateCasesPanel(currentCases);
    updateDraftPanel(safeContext.draft);
    renderSessionList();
}

function resetChatWindow() {
    if (!chatBox) return;
    chatBox.innerHTML = `
        <div class="chat-message ai-message fade-in">
            <div class="message-bubble">Hello! Upload a case PDF or describe your legal situation to begin.</div>
            <div class="message-timestamp">Now</div>
        </div>
    `;
}

function renderChatFromContext(context) {
    const messages = Array.isArray(context.messages) ? context.messages : [];
    if (!messages.length) {
        resetChatWindow();
        return;
    }
    if (!chatBox) return;
    chatBox.innerHTML = '';
    messages.forEach((msg) => {
        const role = (msg && (msg.role || msg.sender || msg.type)) || 'assistant';
        const rawText = (msg && (msg.content || msg.text || msg.message)) || '';
        const htmlText = escapeHtml(String(rawText)).replace(/\n/g, '<br>');
        appendMessage(role === 'user' ? 'user' : 'bot', htmlText);
    });
}

function updateDraftPanel(draft) {
    const draftContent = document.getElementById('draft-content');
    const draftDownloadBtn = document.getElementById('draft-download-btn');
    const draftExportBtn = document.getElementById('draft-export-btn');
    if (!draftContent) return;

    if (draft && String(draft).trim()) {
        displayDraft(String(draft));
        currentDraft = String(draft);
        if (draftDownloadBtn) {
            draftDownloadBtn.hidden = false;
        }
        if (draftExportBtn) {
            draftExportBtn.hidden = false;
        }
        return;
    }

    currentDraft = null;
    draftContent.innerHTML = '<p class="empty-state">Click "Generate Document" to create a legal memo or brief based on your case analysis.</p>';
    if (draftDownloadBtn) {
        draftDownloadBtn.hidden = true;
    }
    if (draftExportBtn) {
        draftExportBtn.hidden = true;
    }
}

function toggleSidebar() {
    document.body.classList.toggle('sidebar-collapsed');
    updateSidebarToggleIcon();
}

function closeSidebar() {
    document.body.classList.add('sidebar-collapsed');
    updateSidebarToggleIcon();
}

function updateSidebarToggleIcon() {
    if (!sidebarToggleBtn) return;
    const isClosed = document.body.classList.contains('sidebar-collapsed');
    sidebarToggleBtn.textContent = isClosed ? '☰' : '✕';
}

async function handleNewSession() {
    try {
        showChatSkeleton();
        showAnalysisSkeleton();
        showCasesSkeleton();
        showDraftSkeleton();

        const res = await fetch('/contexts/new', { method: 'POST' });
        const data = await res.json();
        contextId = data.context_id;
        clearPanelsForNewSession();
        await loadSessionHistory();
        if (window.innerWidth < 768) closeSidebar();
    } catch (err) {
        console.error('Error creating new session:', err);
    }
}

function clearPanelsForNewSession() {
    clarifyMode = false;
    clarificationAnswers = [];
    clarifyAttempts = 0;
    currentAnalysis = {};
    currentTimeline = [];
    currentStatutes = [];
    currentStrength = {};
    currentCases = [];
    updateAnalysisPanel({});
    updateCasesPanel([]);
    updateDraftPanel('');
    resetChatWindow();
}

async function handleSessionListClick(e) {
    const menuBtn = e.target.closest('[data-menu-btn]');
    if (menuBtn) {
        const contextForMenu = menuBtn.getAttribute('data-menu-btn');
        document.querySelectorAll('.session-menu.show').forEach((menu) => {
            if (menu.getAttribute('data-menu') !== contextForMenu) {
                menu.classList.remove('show');
            }
        });
        const menu = document.querySelector(`.session-menu[data-menu="${CSS.escape(contextForMenu)}"]`);
        if (menu) menu.classList.toggle('show');
        return;
    }

    const actionBtn = e.target.closest('[data-action]');
    if (actionBtn) {
        const action = actionBtn.getAttribute('data-action');
        const targetContextId = actionBtn.getAttribute('data-context-id');
        if (action === 'rename') {
            await beginRenameSession(targetContextId);
        } else if (action === 'delete') {
            showDeleteModal(targetContextId);
        }
        return;
    }

    const card = e.target.closest('.session-card');
    if (!card) return;
    const targetContextId = card.getAttribute('data-context-id');
    if (!targetContextId || targetContextId === contextId) return;
    await switchSession(targetContextId);
}

async function switchSession(targetContextId) {
    const card = document.querySelector(`.session-card[data-context-id="${CSS.escape(targetContextId)}"]`);
    if (card) {
        card.classList.add('is-loading');
    }
    stopSessionTimer();
    
    console.log('[SWITCH-1] User clicked, newContextId:', targetContextId);
    console.log('[SWITCH-2] Current global contextId BEFORE:', contextId);
    
    showChatSkeleton();
    showAnalysisSkeleton();
    showCasesSkeleton();
    showDraftSkeleton();
    try {
        const res = await fetch('/contexts/switch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ context_id: targetContextId })
        });
        if (res.status === 403) {
            return;
        }
        const data = await res.json();
        const newContextId = data.switched_to || targetContextId;
        
        console.log('[SWITCH-3] Fetch returned, data.context_id:', data.switched_to);
        console.log('[SWITCH-4] About to set contextId');
        
        contextId = newContextId;
        console.log('[SWITCH-5] contextId now equals:', contextId);
        
        const savedSeconds = data.total_seconds || data.context?.total_seconds || 0;
        console.log('[TIMER-SWITCH] data.total_seconds:', data.total_seconds, 'data.context.total_seconds:', data.context?.total_seconds);
        
        applyContextToUI(contextId, data.context || {});
        startSessionTimer(savedSeconds);
        
        console.log('[SWITCH-6] About to call renderSessionList with contextId:', contextId);
        
        await loadSessionHistory();
        if (window.innerWidth < 768) closeSidebar();
    } catch (err) {
        console.error('Error switching session:', err);
    } finally {
        if (card) {
            card.classList.remove('is-loading');
        }
    }
}

async function beginRenameSession(targetContextId) {
    const card = document.querySelector(`.session-card[data-context-id="${CSS.escape(targetContextId)}"]`);
    if (!card) return;
    const titleEl = card.querySelector('.session-title');
    if (!titleEl) return;
    const existingTitle = titleEl.textContent || 'New Session';
    titleEl.innerHTML = `<input class="session-rename-input" type="text" value="${escapeHtml(existingTitle)}" maxlength="120" />`;
    const input = titleEl.querySelector('input');
    if (!input) return;
    input.focus();
    input.select();

    const commit = async () => {
        const title = input.value.trim() || 'New Session';
        try {
            await fetch('/contexts/rename', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ context_id: targetContextId, title })
            });
            await loadSessionHistory();
        } catch (err) {
            console.error('Error renaming session:', err);
        }
    };

    input.addEventListener('keydown', async (ev) => {
        if (ev.key === 'Enter') {
            ev.preventDefault();
            await commit();
        } else if (ev.key === 'Escape') {
            await loadSessionHistory();
        }
    });
    input.addEventListener('blur', commit, { once: true });
}

function showDeleteModal(targetContextId) {
    pendingDeleteContextId = targetContextId;
    if (deleteModal) {
        openModal(deleteModal);
    }
}

function hideDeleteModal() {
    pendingDeleteContextId = null;
    if (deleteModal) {
        closeModal(deleteModal);
    }
}

async function confirmDeleteSession() {
    if (!pendingDeleteContextId) return;
    const targetContextId = pendingDeleteContextId;
    try {
        const res = await fetch('/contexts/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ context_id: targetContextId })
        });
        const data = await res.json();
        if (data && data.switched_to && data.context) {
            contextId = data.switched_to;
            applyContextToUI(data.switched_to, data.context || {});
        }
        // Remove deleted session locally for immediate UI feedback.
        sessionHistory = (sessionHistory || []).filter((s) => s.context_id !== targetContextId);
        await loadSessionHistory();
    } catch (err) {
        console.error('Error deleting session:', err);
    } finally {
        hideDeleteModal();
    }
}

function updateRoleSelector(role) {
    if (!role) return;
    const normalized = String(role).toLowerCase();
    selectedRole = normalized;

    if (roleOptionsEls && roleOptionsEls.length) {
        roleOptionsEls.forEach((opt) => {
            const val = String(opt.dataset.value || '').toLowerCase();
            opt.classList.toggle('active', val === normalized);
        });
    }

    if (roleSelectedTextEl) {
        const match = Array.from(roleOptionsEls || []).find((opt) => String(opt.dataset.value || '').toLowerCase() === normalized);
        if (match) roleSelectedTextEl.textContent = (match.textContent || '').trim();
    }

    roleMenuEl?.classList.remove('show');
}

// =====================================================
// PDF UPLOAD
// =====================================================
async function handleFileUpload(event) {
    const files = event.target.files;
    if (!files.length) return;
    
    const existingNames = currentUploadedDocs ? currentUploadedDocs.map(d => d.filename) : [];
    const formData = new FormData();
    
    for (let f of files) {
        let name = f.name;
        if (existingNames.includes(name)) {
            let lastDotIndex = name.lastIndexOf('.');
            let base = lastDotIndex !== -1 ? name.substring(0, lastDotIndex) : name;
            let ext = lastDotIndex !== -1 ? name.substring(lastDotIndex) : '';
            let counter = 1;
            while (existingNames.includes(`${base} (${counter})${ext}`)) {
                counter++;
            }
            name = `${base} (${counter})${ext}`;
        }
        existingNames.push(name);
        formData.append('files', f, name);
    }
    formData.append('context_id', contextId);
    
    showToast('Uploading documents...', 'info');
    
    try {
        const res = await fetch('/upload', {
            method: 'POST',
            credentials: 'same-origin',
            body: formData
        });
        const data = await res.json();
        
        if (data.status === 'queued') {
            showToast(`${data.jobs.length} file(s) queued for extraction`, 'info');
            const completed = await Promise.all(data.jobs.map(job =>
                pollJob(job.status_url, { deadlineMs: 120000 })));
            const succeeded = completed.filter(job => job.status === 'succeeded').length;
            const failed = completed.length - succeeded;
            await loadContext();
            await loadSessionHistory();
            showToast(failed ? `${succeeded} processed; ${failed} failed` : `${succeeded} file(s) processed`,
                      failed ? 'error' : 'success');
            openDocManager();
        } else if (data.error) {
            showToast(`Upload failed: ${data.error}`, 'error');
        }
    } catch (err) {
        showToast(err.message || 'Upload failed due to network error.', 'error');
        console.error(err);
    }

    event.target.value = ''; // reset input
}

// Prevent browser from opening dropped files
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    document.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
    });
});

document.addEventListener('dragenter', (e) => {
    const dropZone = document.getElementById('drop-zone');
    if (dropZone) dropZone.hidden = false;
});

document.getElementById('drop-zone')?.addEventListener('dragleave', (e) => {
    // Only hide if leaving the drop zone entirely (not entering a child element)
    if (e.target === document.getElementById('drop-zone')) {
        document.getElementById('drop-zone').hidden = true;
    }
});

document.getElementById('drop-zone')?.addEventListener('drop', (e) => {
    document.getElementById('drop-zone').hidden = true;
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        const input = document.getElementById('file-upload-input');
        if (input) {
            input.files = files;
            input.dispatchEvent(new Event('change'));
        }
    }
});

function openDocManager() {
    const modal = document.getElementById('doc-manager-modal');
    if (modal) openModal(modal);
    renderDocList();
}

document.getElementById('doc-manager-close')?.addEventListener('click', () => {
    closeModal('doc-manager-modal');
});

document.getElementById('doc-manager-done')?.addEventListener('click', () => {
    closeModal('doc-manager-modal');
});

document.getElementById('doc-manager-upload-more')?.addEventListener('click', () => {
    document.getElementById('file-upload-input').click();
});

function renderDocList() {
    const list = document.getElementById('doc-manager-list');
    if (!list) return;

    const docs = currentUploadedDocs || [];
    const loggedInUser = document.querySelector('.workspace-container')?.getAttribute('data-user-name') || '';
    const todayStr = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

    // Backfill metadata for any older documents missing it
    docs.forEach(doc => {
        if (!doc.uploaded_by) doc.uploaded_by = loggedInUser || 'You';
        if (!doc.uploaded_at) doc.uploaded_at = todayStr;
    });
    
    list.innerHTML = docs.map((doc, i) => `
        <div class="doc-item" onmousemove="showDocTooltip(event, this)" onmouseleave="hideDocTooltip()" data-preview="${escapeHtml(doc.text?.substring(0, 400) || '')}">
            <div class="doc-info" style="display: flex; flex-direction: column; justify-content: center; gap: 4px; min-width: 0;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="doc-number" style="color: #9E8E7E; font-size: 13px; font-weight: 500;">${i + 1}.</span>
                    <span class="doc-name" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${doc.filename}</span>
                </div>
                <span style="font-size: 11px; color: #9E8E7E; margin-left: 20px;">Uploaded by ${doc.uploaded_by} • ${doc.uploaded_at}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 12px; flex-shrink: 0;">
                <label class="doc-toggle">
                    <input type="checkbox" class="modern-toggle" ${doc.included ? 'checked' : ''} 
                        onchange="toggleDocument(${i}, this.checked)" />
                    <span class="toggle-slider"></span>
                    <span class="toggle-label">Include</span>
                </label>
                <button class="doc-delete-btn ${pendingDocDeleteIndex === i ? 'confirm' : ''}" onclick="promptDeleteDocument(event, ${i})" title="${pendingDocDeleteIndex === i ? 'Confirm Delete' : 'Delete Document'}">
                    ${pendingDocDeleteIndex === i ? '<svg class="icon icon-sm" aria-hidden="true"><use href="#i-check"></use></svg><span class="doc-confirm-label">Confirm</span>' : '<svg class="icon icon-sm" aria-hidden="true"><use href="#i-trash"></use></svg>'}
                </button>
            </div>
        </div>
    `).join('') || '<p class="doc-empty">No documents uploaded yet.</p>';
}

function escapeHtml(unsafe) {
    return (unsafe || '').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

let floatingDocTooltip = null;

function showDocTooltip(e, el) {
    if (!floatingDocTooltip) {
        floatingDocTooltip = document.createElement('div');
        floatingDocTooltip.className = 'doc-floating-tooltip';
        document.body.appendChild(floatingDocTooltip);
    }
    const text = el.getAttribute('data-preview');
    if (!text) return;
    
    floatingDocTooltip.textContent = text + '...';
    floatingDocTooltip.style.display = 'block';
    
    // Position near cursor
    floatingDocTooltip.style.left = (e.clientX + 15) + 'px';
    floatingDocTooltip.style.top = (e.clientY + 15) + 'px';
}

function hideDocTooltip() {
    if (floatingDocTooltip) floatingDocTooltip.style.display = 'none';
}

let pendingDocDeleteIndex = -1;

function promptDeleteDocument(event, index) {
    if (pendingDocDeleteIndex === index) {
        pendingDocDeleteIndex = -1;
        executeDeleteDocument(index);
    } else {
        pendingDocDeleteIndex = index;
        renderDocList();
        setTimeout(() => {
            if (pendingDocDeleteIndex === index) {
                pendingDocDeleteIndex = -1;
                renderDocList();
            }
        }, 3000);
    }
}

async function toggleDocument(index, included) {
    try {
        await fetch('/documents/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ context_id: contextId, doc_index: index, included })
        });
        if (currentUploadedDocs[index]) {
            currentUploadedDocs[index].included = included;
        }
        renderDocList();
        showToast(included ? 'Document included in analysis' : 'Document removed from analysis', 'info');
    } catch(err) {
        showToast('Failed to toggle document', 'error');
        console.error(err);
    }
}

async function executeDeleteDocument(index) {
    try {
        const res = await fetch('/documents/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ context_id: contextId, doc_index: index })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            currentUploadedDocs.splice(index, 1);
            showToast('Document securely deleted.', 'success');
            renderDocList();
        } else {
            showToast('Failed to delete document.', 'error');
        }
    } catch (err) {
        showToast('Error deleting document.', 'error');
        console.error(err);
    }
}

// =====================================================
// ANALYZE
// =====================================================
async function handleAnalyze() {
    if (!contextId) {
        appendMessage('bot', 'Please upload a PDF or describe your case first.');
        return;
    }

    const loading = appendLoadingMessage('Analyzing case…');
    showAnalysisSkeleton();

    try {
        const res = await fetch('/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ context_id: contextId })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Unable to queue analysis');

        const job = await pollJob(data.status_url, {
            onUpdate: current => {
                const bubble = loading.querySelector('.message-bubble');
                if (bubble) {
                    const stage = String(current.stage || 'working').replace(/_/g, ' ');
                    bubble.innerHTML = `<span class="loading-spinner" aria-hidden="true"></span>${escapeHtml(stage)} · ${Number(current.progress || 0)}%`;
                }
            },
        });
        removeMessage(loading);

        if (job.status !== 'succeeded') {
            appendMessage('bot', `Error: ${job.error?.message || 'Analysis failed.'}`);
            return;
        }

        const result = job.result || {};
        currentAnalysis = result.analysis || {};
        currentTimeline = result.timeline || [];
        currentStatutes = result.statutes || [];
        currentStrength = result.strength || {};
        updateAnalysisPanel(currentAnalysis);
        appendMessage('bot', 'Analysis complete! Check the Analysis panel.');
        // Switch to analysis tab
        document.querySelector('[data-tab="record"]').click();
    } catch (err) {
        removeMessage(loading);
        appendMessage('bot', err.message || 'Analysis failed.');
        console.error(err);
    }
}

// =====================================================
// CHAT SUBMIT
// =====================================================
async function handleChatSubmit(e) {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;

    triggerSendIconAnimation();
    appendMessage('user', message.replace(/\n/g, '<br>'));
    chatInput.value = '';
    autoResizeTextarea();

    const thinking = appendLoadingMessage('Queued…');

    try {
        const body = {
            message,
            context_id: contextId,
            client_message_id: (window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`)
        };

        const res = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        let data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Unable to queue chat');
        contextId = data.context_id || data.matter_id || contextId;
        data = await pollChatJob(data.status_url, thinking);
        removeMessage(thinking);
        if (data.status !== 'succeeded') {
            const detail = data.error?.message || (data.status === 'cancelled' ? 'Request cancelled.' : 'Chat request failed.');
            appendMessage('bot', escapeHtml(detail));
            return;
        }
        data = data.result || {};
        const completedId = data.context_id || contextId;
        const completedHistory = sessionHistory.find((item) => item.context_id === completedId);
        if (completedHistory && data.title) {
            const wasNew = completedHistory.title === 'New Session' || !completedHistory.title;
            completedHistory.title = data.title;
            if (wasNew && data.title !== 'New Session') completedHistory._animateTitleNext = true;
            renderSessionList();
        }

        // Handle clarifying
        if (data.status === 'clarifying') {
            clarifyMode = true;
            clarifyAttempts = data.clarify_attempts;
            contextId = data.context_id;
            // Role selector will be updated if needed
            clarificationAnswers = [];

            appendMessage('bot', escapeHtml(data.message || '').replace(/\n/g, '<br>'));

            if (data.analysis) {
                showAnalysisSkeleton();
                currentAnalysis = data.analysis;
                currentTimeline = data.timeline || [];
                currentStatutes = data.statutes || [];
                currentStrength = data.strength || {};
                updateAnalysisPanel(data.analysis);
            }
            return;
        }

        // Handle results
        if (data.status === 'results') {
            clarifyMode = false;
            clarifyAttempts = 0;
            clarificationAnswers = [];
            contextId = data.context_id;
            // Role selector will be updated if needed

            const sid = data.context_id || contextId;
            const hist = sessionHistory.find((s) => s.context_id === sid);
            if (hist && data.title != null && data.title !== '') {
                const wasNew = hist.title === 'New Session' || !hist.title;
                hist.title = data.title;
                if (wasNew && data.title !== 'New Session') {
                    hist._animateTitleNext = true;
                }
            }

            if (data.analysis) {
                showAnalysisSkeleton();
                currentAnalysis = data.analysis;
                currentTimeline = data.timeline || [];
                currentStatutes = data.statutes || [];
                currentStrength = data.strength || {};
                updateAnalysisPanel(data.analysis);
            }

            if (data.cases && data.cases.length > 0) {
                showCasesSkeleton();
                currentCases = data.cases;
                updateCasesPanel(data.cases);
                appendMessage('bot', renderGroundedMessage(data));
                // Switch to cases tab
                document.querySelector('[data-tab="authority"]')?.click();
            } else {
                appendMessage('bot', renderGroundedMessage(data));
            }
            renderSessionList();
            return;
        }

        if (data.status === 'answer') {
            appendMessage('bot', renderGroundedMessage(data));
            return;
        }
    } catch (err) {
        removeMessage(thinking);
        appendMessage('bot', escapeHtml(err.message || 'Server error.'));
        console.error(err);
    }
}

async function pollChatJob(statusUrl, loadingElement) {
    try {
        return await pollJob(statusUrl, {
            deadlineMs: 95000,
            onUpdate: job => {
                const bubble = loadingElement?.querySelector('.message-bubble');
                if (bubble) {
                    const stage = String(job.stage || 'working').replace(/_/g, ' ');
                    bubble.innerHTML = `<span class="loading-spinner" aria-hidden="true"></span>${escapeHtml(stage)} · ${Number(job.progress || 0)}%`;
                }
            },
        });
    } catch (err) {
        if (err.message === 'This request is still running. Check again shortly.') {
            throw new Error('This request is still running. Refresh the matter to see its result.');
        }
        throw err;
    }
}

function renderGroundedMessage(data) {
    let html = escapeHtml(data.message || data.answer || '').replace(/\n/g, '<br>');
    const citations = Array.isArray(data.citations) ? data.citations : [];
    if (citations.length) {
        html += '<div class="chat-citations"><strong>Sources</strong><ol>';
        citations.forEach(citation => {
            const label = [citation.title, citation.locator].filter(Boolean).join(' — ');
            const url = String(citation.url || '');
            const safeLabel = escapeHtml(label || 'Source');
            html += /^https:\/\//i.test(url)
                ? `<li><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${safeLabel}</a></li>`
                : `<li>${safeLabel}</li>`;
        });
        html += '</ol></div>';
    }
    return html;
}

// =====================================================
// DRAFT GENERATION
// =====================================================
async function handleDraftGenerate() {
    if (!contextId) {
        appendMessage('bot', 'Please upload a PDF or describe your case first.');
        return;
    }

    const docType = document.getElementById('draft-type').value;
    const draftContent = document.getElementById('draft-content');

    showDraftSkeleton();

    try {
        const res = await fetch('/draft', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ context_id: contextId, doc_type: docType })
        });

        let data;
        try {
            data = await res.json();
        } catch (e) {
            draftContent.innerHTML = '<p class="empty-state">Received invalid response from server.</p>';
            return;
        }

        if (!res.ok) {
            draftContent.innerHTML = `<p class="empty-state">Error: ${data.error || 'Unable to queue draft'}</p>`;
            return;
        }

        const job = await pollJob(data.status_url);

        if (job.status !== 'succeeded') {
            draftContent.innerHTML = `<p class="empty-state">${job.error?.message || 'Draft generation failed.'}</p>`;
            return;
        }

        const draftDocument = job.result?.document;
        if (draftDocument) {
            displayDraft(draftDocument);
            currentDraft = draftDocument;
            document.getElementById('draft-export-btn').hidden = false;
            appendMessage('bot', `Generated ${docType}! Check the Draft panel.`);
        } else {
            draftContent.innerHTML = '<p class="empty-state">Draft generation failed.</p>';
        }
    } catch (err) {
        draftContent.innerHTML = `<p class="empty-state">${err.message || 'Draft generation failed.'}</p>`;
        console.error(err);
    }
}

function handleDraftExport() {
    if (!currentDraft || currentDraft.trim() === '') {
        showToast('No draft to export. Generate a draft first.', 'error');
        return;
    }
    
    const exportBtn = document.getElementById('draft-export-btn');
    const originalText = exportBtn.innerHTML;
    exportBtn.innerHTML = '<span class="loading-spinner" aria-hidden="true"></span> Exporting...';
    exportBtn.disabled = true;
    
    fetch('/draft/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ 
            context_id: contextId,
            draft_text: currentDraft
        })
    })
    .then(res => {
        if (!res.ok) throw new Error('Export failed');
        return res.blob();
    })
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'legal_memo.docx';
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        showToast('Draft exported successfully', 'success');
    })
    .catch(err => {
        console.error('Export error:', err);
        showToast('Failed to export draft', 'error');
    })
    .finally(() => {
        exportBtn.innerHTML = originalText;
        exportBtn.disabled = false;
    });
}

// =====================================================
// PANEL UPDATES
// =====================================================
/**
 * Fans the extracted analysis out across the four matter panels.
 *
 * This used to build one string containing strength + facts + parties +
 * jurisdictions + issues + causes + penal codes + statutes + timeline and drop
 * all nine into a single #analysis-content. The name and signature are kept so
 * that all six call sites, and the currentStatutes / currentTimeline /
 * currentStrength globals they set beforehand, keep working untouched.
 */
function updateAnalysisPanel(analysis) {
    renderMatterStrength(currentStrength);
    renderChronologyPanel(currentTimeline);
    renderStatutesPanel(currentStatutes);
    renderRecordPanel(analysis);
}

function renderMatterStrength(strength) {
    const chip = document.getElementById('matter-strength');
    if (!chip) return;

    const rating = strength && strength.rating;
    if (!rating) { chip.hidden = true; return; }

    const key = String(rating).toLowerCase().replace(/\s+/g, '-');
    // Fractions, not percentages: the bar animates with transform: scaleX so
    // it composites instead of relaying out the header on every frame.
    const scales = { strong: 1, moderate: 0.6, weak: 0.25, 'insufficient-information': 0.08 };

    chip.hidden = false;
    chip.dataset.rating = key;
    chip.title = strength.explanation || '';
    document.getElementById('matter-strength-value').textContent = rating;
    document.getElementById('matter-strength-fill').style.transform =
        `scaleX(${scales[key] !== undefined ? scales[key] : 0.08})`;
}

function renderChronologyPanel(timeline) {
    const el = document.getElementById('chronology-content');
    if (!el) return;

    const events = Array.isArray(timeline) ? timeline : [];
    if (!events.length) {
        el.innerHTML = `
          <div class="empty-state">
            <svg class="empty-state__icon" aria-hidden="true"><use href="#i-chronology"></use></svg>
            <p class="empty-state__title">No chronology yet</p>
            <p class="empty-state__body">Dates found in the record appear here in order. You can add events by hand at any time.</p>
          </div>`;
        return;
    }
    el.innerHTML = renderTimeline(events);
}

function renderStatutesPanel(statutes) {
    const el = document.getElementById('statutes-content');
    if (!el) return;

    const list = Array.isArray(statutes) ? statutes : [];
    if (!list.length) {
        el.innerHTML = `
          <div class="empty-state">
            <svg class="empty-state__icon" aria-hidden="true"><use href="#i-statute"></use></svg>
            <p class="empty-state__title">No statutes identified yet</p>
            <p class="empty-state__body">Statutes referenced by the record appear here. Verify each against an official source.</p>
          </div>`;
        return;
    }
    el.innerHTML = renderStatutes(list);
}

function renderRecordPanel(analysis) {
    const content = document.getElementById('record-content');
    if (!content) return;

    if (!analysis || Object.keys(analysis).length === 0) {
        content.innerHTML = `
          <div class="empty-state">
            <svg class="empty-state__icon" aria-hidden="true"><use href="#i-record"></use></svg>
            <p class="empty-state__title">No record yet</p>
            <p class="empty-state__body">Upload a document or describe the matter. Facts, parties, jurisdictions, and legal issues will be extracted here for your review.</p>
          </div>`;
        return;
    }

    let html = '';

    // Facts
    if (Array.isArray(analysis.facts) && analysis.facts.length > 0) {
        html += '<div class="analysis-section"><h4>Facts</h4><ul>';
        analysis.facts.forEach((fact, i) => {
            const cls = i >= 4 ? ' class="facts-hidden"' : '';
            html += `<li${cls}>${escapeHtml(fact)}</li>`;
        });
        html += '</ul>';
        if (analysis.facts.length > 4) {
            html += '<button class="facts-toggle" onclick="toggleAnalysisList(this)">See more</button>';
        }
        html += '</div>';
    }

    // Parties
    if (Array.isArray(analysis.parties) && analysis.parties.length > 0) {
        html += '<div class="analysis-section"><h4>Parties</h4>';
        analysis.parties.forEach(party => {
            const name = party.name || party;
            const role = party.role || 'Unknown';
            html += `<div class="party-item"><span>${escapeHtml(name)}</span><span class="party-role">${escapeHtml(role)}</span></div>`;
        });
        html += '</div>';
    }

    // Jurisdictions
    if (Array.isArray(analysis.jurisdictions) && analysis.jurisdictions.length > 0) {
        html += '<div class="analysis-section"><h4>Jurisdictions</h4><ul>';
        analysis.jurisdictions.forEach(jur => {
            html += `<li>${escapeHtml(jur)}</li>`;
        });
        html += '</ul></div>';
    }

    // Legal Issues
    if (Array.isArray(analysis.legal_issues) && analysis.legal_issues.length > 0) {
        html += '<div class="analysis-section"><h4>Legal Issues</h4><ul>';
        analysis.legal_issues.forEach((issue, i) => {
            const cls = i >= 4 ? ' class="facts-hidden"' : '';
            html += `<li${cls}>${escapeHtml(issue)}</li>`;
        });
        html += '</ul>';
        if (analysis.legal_issues.length > 4) {
            html += '<button class="facts-toggle" onclick="toggleAnalysisList(this)">See more</button>';
        }
        html += '</div>';
    }

    // Causes of Action
    if (Array.isArray(analysis.causes_of_action) && analysis.causes_of_action.length > 0) {
        html += '<div class="analysis-section"><h4>Causes of Action</h4><ul>';
        analysis.causes_of_action.forEach((cause, i) => {
            const cls = i >= 4 ? ' class="facts-hidden"' : '';
            html += `<li${cls}>${escapeHtml(cause)}</li>`;
        });
        html += '</ul>';
        if (analysis.causes_of_action.length > 4) {
            html += '<button class="facts-toggle" onclick="toggleAnalysisList(this)">See more</button>';
        }
        html += '</div>';
    }

    if (!html) {
        html = '<p class="empty-state">Analysis in progress…</p>';
    }

    content.innerHTML = html;
}

function renderStatutes(statutes) {
    if (!Array.isArray(statutes) || statutes.length === 0) return '';
    
    let html = `
        <div class="statutes-section">
            <h4 class="analysis-section-title">Relevant Statutes</h4>
            <p class="statutes-disclaimer">Statutes identified by AI — verify with official sources.</p>
    `;
    
    statutes.forEach(s => {
        html += `
            <div class="statute-card">
              <div class="statute-code">${escapeHtml(s.code || '')}</div>
              <div class="statute-title">${escapeHtml(s.title || '')}</div>
              <div class="statute-jurisdiction">${escapeHtml(s.jurisdiction || '')}</div>
              <div class="statute-description">${escapeHtml(s.description || '')}</div>
              <div class="statute-relevance">${escapeHtml(s.relevance || '')}</div>
            </div>
        `;
    });
    
    html += '</div>';
    return html;
}

function renderStrengthMeter(strength) {
    if (!strength || !strength.rating) return '';
    
    const ratingKey = strength.rating.toLowerCase().replace(/\s+/g, '-');
    
    const fillWidths = {
        'strong': '100%',
        'moderate': '60%',
        'weak': '25%',
        'insufficient-information': '5%'
    };
    
    const fillWidth = fillWidths[ratingKey] || '5%';
    
    return `
        <div class="strength-section">
            <div class="strength-header-wrap">
                <span class="strength-label">Case Strength</span>
                <span class="strength-badge badge-${ratingKey}">${strength.rating}</span>
            </div>
            <div class="strength-bar-track">
                <div class="strength-bar-fill fill-${ratingKey}" style="width: ${fillWidth}"></div>
            </div>
            <p class="strength-explanation">${strength.explanation || ''}</p>
            <p class="strength-disclaimer">AI assessment — not legal advice.</p>
        </div>
    `;
}

function toggleAnalysisList(btn) {
    const list = btn.previousElementSibling;
    if (!list || list.tagName !== 'UL') return;

    const isExpanded = btn.textContent.includes('less');
    const items = list.querySelectorAll('li:nth-child(n+5)');

    items.forEach(item => {
        if (isExpanded) {
            item.classList.add('facts-hidden');
        } else {
            item.classList.remove('facts-hidden');
        }
    });

    btn.textContent = isExpanded ? 'See more' : 'See less';
}

function renderTimeline(events) {
    const evs = Array.isArray(events) ? events : [];

    let html = `
        <div class="timeline-section">
            <div class="timeline-container">
    `;

    evs.forEach((event, index) => {
        let rawCat = (event.category || 'event').toLowerCase();
        if (rawCat !== 'incident' && rawCat !== 'event') rawCat = 'event';

        const categoryClass = `tag-${rawCat}`;
        const categoryLabel = rawCat === 'incident' ? 'Incident' : 'Event';
        const dateDisplay = event.date || 'Date Unknown';
        const isManual = event.source === 'manual' ? '<span class="timeline-manual-tag">Manual</span>' : '';

        html += `
            <div class="timeline-event">
                <div class="timeline-marker"></div>
                <div class="timeline-event-content">
                    <div class="timeline-date">${dateDisplay}</div>
                    <div class="timeline-details">
                        <span class="timeline-tag ${categoryClass}">${categoryLabel}</span>
                        ${isManual}
                        <p class="timeline-description">${event.description || ''}</p>
                    </div>
                </div>
            </div>
        `;
    });

    html += `
            </div>
            <div class="timeline-add-event">
                <input type="text" id="timeline-new-date" placeholder="Date (e.g., Jan 5, 2024)" />
                <input type="text" id="timeline-new-desc" placeholder="Describe the event..." />
                <button id="timeline-add-btn" onclick="submitManualTimelineEvent()">+ Add</button>
            </div>
        </div>
    `;

    return html;
}

function submitManualTimelineEvent() {
    const dateInput = document.getElementById('timeline-new-date');
    const descInput = document.getElementById('timeline-new-desc');
    if (!dateInput || !descInput) return;

    const date = dateInput.value.trim();
    const desc = descInput.value.trim();

    if (!desc) return;

    fetch('/timeline/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
            context_id: contextId,
            date: date || 'Unknown',
            description: desc,
            category: 'event'
        })
    })
        .then(res => res.json())
        .then(data => {
            if (data.timeline) {
                currentTimeline = data.timeline;
                dateInput.value = '';
                descInput.value = '';
                updateTimelineInPanel(data.timeline);
            }
        })
        .catch(err => console.error('Failed to add event:', err));
}

function updateTimelineInPanel(timeline) {
    currentTimeline = Array.isArray(timeline) ? timeline : [];
    renderChronologyPanel(currentTimeline);
}

function getRelevanceClass(score) {
    if (score >= 75) {
        return 'relevance-excellent';
    } else if (score >= 65) {
        return 'relevance-good';
    } else if (score >= 35) {
        return 'relevance-fair';
    } else {
        return 'relevance-poor';
    }
}

function getTooltipSubscoreClass(score) {
    const n = Number(score);
    if (!Number.isFinite(n)) return '';
    if (n >= 75) return 'tooltip-excellent';
    if (n >= 65) return 'tooltip-good';
    if (n >= 35) return 'tooltip-fair';
    return 'tooltip-poor';
}

let scoreTooltipEl = null;
let scoreTooltipOwner = null;

const RELEVANCE_DIMENSION_ATTRS = [
    ['factual_similarity', 'data-factual'],
    ['legal_issues_match', 'data-legal'],
    ['causes_of_action_overlap', 'data-causes'],
    ['jurisdictional_relevance', 'data-jurisdiction'],
    ['practical_utility', 'data-utility'],
];

function relevanceDimensionsDataAttributes(dimensions) {
    if (!dimensions || typeof dimensions !== 'object' || Array.isArray(dimensions)) {
        return { extraAttrs: '', hasTooltip: false };
    }
    const attrs = [];
    for (const [key, attrName] of RELEVANCE_DIMENSION_ATTRS) {
        if (!Object.prototype.hasOwnProperty.call(dimensions, key)) continue;
        const v = dimensions[key];
        if (v === undefined || v === null || v === '') continue;
        const s = String(v).replace(/"/g, '&quot;');
        attrs.push(`${attrName}="${s}"`);
    }
    if (!attrs.length) {
        return { extraAttrs: '', hasTooltip: false };
    }
    return { extraAttrs: ' ' + attrs.join(' '), hasTooltip: true };
}

function buildScoreTooltipHtml(targetEl) {
    const rows = [
        ['Factual Similarity:', targetEl.getAttribute('data-factual')],
        ['Legal Issues Match:', targetEl.getAttribute('data-legal')],
        ['Causes of Action:', targetEl.getAttribute('data-causes')],
        ['Jurisdictional Relevance:', targetEl.getAttribute('data-jurisdiction')],
        ['Practical Utility:', targetEl.getAttribute('data-utility')],
    ];
    return rows
        .filter(([, v]) => v !== null && v !== '')
        .map(([label, v]) => {
            const n = Number(v);
            const isNum = Number.isFinite(n);
            const tier = isNum ? getTooltipSubscoreClass(n) : '';
            const valueClass = isNum && tier ? `tooltip-value ${tier}` : 'tooltip-value';
            const valueText = isNum ? `${Math.round(n)}%` : escapeHtml(String(v));
            return `<div><span class="tooltip-label">${escapeHtml(label)}</span><span class="${valueClass}">${valueText}</span></div>`;
        })
        .join('');
}

function positionScoreTooltip(tooltip, clientX, clientY) {
    const pad = 12;
    const edge = 8;
    tooltip.style.position = 'fixed';
    tooltip.style.left = `${clientX + pad}px`;
    tooltip.style.top = `${clientY + pad}px`;
    const w = tooltip.offsetWidth;
    let left = clientX + pad;
    if (left + w > window.innerWidth - edge) {
        left = clientX - w - pad;
    }
    if (left < edge) left = edge;
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${clientY + pad}px`;
}

function removeScoreTooltip() {
    if (scoreTooltipEl) {
        scoreTooltipEl.remove();
        scoreTooltipEl = null;
        scoreTooltipOwner = null;
    }
}

function onScoreTooltipEnter(e) {
    removeScoreTooltip();
    const inner = buildScoreTooltipHtml(e.currentTarget);
    if (!inner) return;
    const tip = document.createElement('div');
    tip.className = 'score-tooltip';
    tip.innerHTML = inner;
    document.body.appendChild(tip);
    scoreTooltipEl = tip;
    scoreTooltipOwner = e.currentTarget;
    positionScoreTooltip(tip, e.clientX, e.clientY);
}

function onScoreTooltipMove(e) {
    if (scoreTooltipEl && e.currentTarget === scoreTooltipOwner) {
        positionScoreTooltip(scoreTooltipEl, e.clientX, e.clientY);
    }
}

function onScoreTooltipLeave() {
    removeScoreTooltip();
}

function bindRelevanceScoreTooltips(container) {
    if (!container) return;
    container.querySelectorAll('.relevance-score--tooltip').forEach((el) => {
        el.addEventListener('mouseenter', onScoreTooltipEnter);
        el.addEventListener('mousemove', onScoreTooltipMove);
        el.addEventListener('mouseleave', onScoreTooltipLeave);
    });
}

function bindCaseDetailTitleClicks(container) {
    if (!container) return;
    container.querySelectorAll('.case-title--detail').forEach((titleEl) => {
        titleEl.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const item = titleEl.closest('.case-item');
            if (!item) return;
            const idx = parseInt(item.getAttribute('data-case-index'), 10);
            if (Number.isNaN(idx)) return;
            showCaseDetail(idx);
        });
    });
}

function scrollCasesDetailScrollAreaToBottom(smooth) {
    const area = document.getElementById('cases-detail-scroll') || document.querySelector('.cases-detail-scroll-area');
    if (!area) return;
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            area.scrollTo({
                top: area.scrollHeight,
                behavior: smooth ? 'smooth' : 'auto',
            });
        });
    });
}

function setCasesTabDetailLayout(isDetail) {
    const tab = document.getElementById('tab-authority');
    if (!tab) return;
    tab.classList.toggle('tab-cases-detail-open', !!isDetail);
}

function bindCasesDetailScrollCondense() {
    const scrollEl = document.getElementById('cases-detail-scroll');
    const viewEl = document.querySelector('#cases-content .cases-detail-view');
    if (!scrollEl || !viewEl) return;
    const sync = () => {
        viewEl.classList.toggle('condensed', scrollEl.scrollTop > 10);
    };
    scrollEl.addEventListener('scroll', sync, { passive: true });
    sync();
}

function stripMarkdown(text) {
    return String(text ?? '')
        .replace(/\*\*(.+?)\*\*/g, '$1')
        .replace(/\*(.+?)\*/g, '$1')
        .replace(/^#{1,6}\s+/gm, '')
        .replace(/```[\s\S]*?```/g, '')
        .replace(/`(.+?)`/g, '$1')
        .replace(/^\s*[-*]\s+/gm, '• ')
        .replace(/^\s*\d+\.\s+/gm, '')
        .trim();
}

function appendCasesPanelChatMessage(role, text, skipScroll) {
    const chat = document.getElementById('cases-detail-chat');
    if (!chat) return;
    const wrap = document.createElement('div');
    const isUser = role === 'user';
    wrap.className = isUser ? 'chat-message user-message' : 'chat-message ai-message';
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    const raw = String(text ?? '');
    const display = isUser ? raw : stripMarkdown(raw);
    bubble.innerHTML = escapeHtml(display).replace(/\n/g, '<br>');
    wrap.appendChild(bubble);
    chat.appendChild(wrap);
    if (!skipScroll) {
        scrollCasesDetailScrollAreaToBottom(true);
    }
}

function renderCaseDetailFollowUps(caseObj) {
    const chat = document.getElementById('cases-detail-chat');
    const promptEl = document.getElementById('cases-detail-chat-prompt');
    if (!chat) return;
    chat.replaceChildren();
    const ups = (caseObj && caseObj.follow_ups) || [];
    if (promptEl) {
        promptEl.style.display = ups.length ? 'none' : 'block';
    }
    ups.forEach((item) => {
        const q = item && item.question != null ? String(item.question) : '';
        const a = item && item.answer != null ? String(item.answer) : '';
        if (q) appendCasesPanelChatMessage('user', q, true);
        if (a) appendCasesPanelChatMessage('bot', a, true);
    });
    scrollCasesDetailScrollAreaToBottom(false);
}

function showCaseList() {
    casesViewState = 'list';
    activeCaseIndex = null;
    updateAuthorityCount(currentCases);
    renderCasesList(currentCases);
}

function showCaseDetail(caseIndex) {
    const caseData = currentCases[caseIndex];
    if (!caseData) return;
    casesViewState = 'detail';
    activeCaseIndex = caseIndex;
    renderCaseDetailView(caseData);
}

function renderCaseDetailRelevanceSection(caseData) {
    const relEl = document.getElementById('case-description-relevance');
    if (!relEl) return;

    const score = caseData.relevance_score ?? caseData.initial_score ?? 0;
    const relClass = getRelevanceClass(score);
    const reasonRaw = caseData.relevance_reason != null ? String(caseData.relevance_reason).trim() : '';
    const reasonHtml = reasonRaw ? ` — ${escapeHtml(reasonRaw)}` : '';

    let treatmentHtml = '';
    if (caseData.treatment && caseData.treatment.checked) {
        treatmentHtml = getTreatmentBadgeHtml(caseData.treatment);
    } else {
        treatmentHtml = '<span class="treatment-checking"><span class="loading-spinner" aria-hidden="true"></span>Checking treatment…</span>';
        setTimeout(() => {
            const detailPlaceholder = document.getElementById(`detail-treatment-badge-${activeCaseIndex}`);
            if (detailPlaceholder) {
                const listPlaceholder = document.getElementById(`treatment-badge-${activeCaseIndex}`);
                // Since loadAllTreatments might already be grabbing this, we can just pass the detail placeholder.
                loadCaseTreatment(activeCaseIndex, detailPlaceholder);
            }
        }, 50);
    }

    relEl.innerHTML = `Relevance: <span class="relevance-score ${relClass}">${score}%</span> <span class="treatment-placeholder" id="detail-treatment-badge-${activeCaseIndex}">${treatmentHtml}</span>${reasonHtml}`;
}

// =====================================================
// CASE NOTES
// =====================================================
let _notesDebounceTimer = null;
let _notesSaving = false;

function _setNotesStatus(status, text) {
    const el = document.getElementById('case-notes-status');
    if (!el) return;
    el.className = 'case-notes-status visible ' + status;
    el.textContent = text;
    if (status === 'saved') {
        setTimeout(() => {
            if (el.textContent === text) {
                el.classList.remove('visible');
            }
        }, 3000);
    }
}

function _updateNotesCharCount() {
    const ta = document.getElementById('case-notes-textarea');
    const counter = document.getElementById('case-notes-char-count');
    if (ta && counter) {
        counter.textContent = `${ta.value.length} chars`;
    }
}

function _formatNotesTimestamp(isoStr) {
    if (!isoStr) return '';
    try {
        const d = new Date(isoStr);
        return 'Saved ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (_) {
        return '';
    }
}

async function saveCaseNote(caseIndex, content) {
    if (_notesSaving) return;
    _notesSaving = true;
    _setNotesStatus('saving', 'Saving...');
    try {
        const res = await fetch('/case/notes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                context_id: contextId,
                case_index: caseIndex,
                content: content
            })
        });
        if (!res.ok) throw new Error('Save failed');
        const data = await res.json();
        // Update local case data
        if (currentCases && currentCases[caseIndex]) {
            currentCases[caseIndex].notes = content;
            currentCases[caseIndex].notes_updated_at = data.updated_at;
        }
        const tsEl = document.getElementById('case-notes-timestamp');
        if (tsEl) tsEl.textContent = _formatNotesTimestamp(data.updated_at);
        _setNotesStatus('saved', 'Saved ✓');
    } catch (err) {
        console.error('Notes save error:', err);
        _setNotesStatus('error', 'Error saving');
        showToast('Failed to save note', 'error');
    } finally {
        _notesSaving = false;
    }
}

async function deleteCaseNote(caseIndex) {
    _setNotesStatus('saving', 'Deleting...');
    try {
        const res = await fetch('/case/notes', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                context_id: contextId,
                case_index: caseIndex
            })
        });
        if (!res.ok) throw new Error('Delete failed');
        if (currentCases && currentCases[caseIndex]) {
            currentCases[caseIndex].notes = '';
            delete currentCases[caseIndex].notes_updated_at;
        }
        const ta = document.getElementById('case-notes-textarea');
        if (ta) ta.value = '';
        _updateNotesCharCount();
        const tsEl = document.getElementById('case-notes-timestamp');
        if (tsEl) tsEl.textContent = '';
        _setNotesStatus('saved', 'Note deleted');
        showToast('Note deleted', 'success');
    } catch (err) {
        console.error('Notes delete error:', err);
        _setNotesStatus('error', 'Error deleting');
        showToast('Failed to delete note', 'error');
    }
}

function _scheduleNoteSave(caseIndex) {
    clearTimeout(_notesDebounceTimer);
    _notesDebounceTimer = setTimeout(() => {
        const ta = document.getElementById('case-notes-textarea');
        if (ta) saveCaseNote(caseIndex, ta.value);
    }, 2000);
}

function buildCaseNotesHtml(caseData) {
    const notesContent = escapeHtml(caseData.notes || '');
    const tsText = _formatNotesTimestamp(caseData.notes_updated_at || '');
    const hasNotes = (caseData.notes || '').trim().length > 0;
    return `
        <div class="case-notes-section${hasNotes ? ' expanded' : ''}" id="case-notes-section">
            <div class="case-notes-header" id="case-notes-toggle">
                <div class="case-notes-header-left">
                    <span class="notes-icon">📝</span>
                    <span>Notes</span>
                </div>
                <div class="case-notes-header-right">
                    <span class="case-notes-status" id="case-notes-status"></span>
                    <span class="case-notes-chevron" id="case-notes-chevron">▾</span>
                </div>
            </div>
            <div class="case-notes-body">
                <div class="case-notes-body-inner">
                    <textarea
                        class="case-notes-textarea"
                        id="case-notes-textarea"
                        placeholder="Add notes about this case..."
                        aria-label="Case notes"
                    >${notesContent}</textarea>
                    <div class="case-notes-footer">
                        <span class="case-notes-char-count" id="case-notes-char-count">${(caseData.notes || '').length} chars</span>
                        <div class="case-notes-actions">
                            <span class="case-notes-timestamp" id="case-notes-timestamp">${tsText}</span>
                            <button class="case-notes-delete-btn" id="case-notes-delete" title="Delete note">🗑</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function bindCaseNotesPanel(caseIndex) {
    const section = document.getElementById('case-notes-section');
    const toggle = document.getElementById('case-notes-toggle');
    const ta = document.getElementById('case-notes-textarea');
    const deleteBtn = document.getElementById('case-notes-delete');
    if (!section || !toggle || !ta) return;

    // Toggle expand/collapse
    toggle.addEventListener('click', () => {
        section.classList.toggle('expanded');
        if (section.classList.contains('expanded')) {
            ta.focus();
        }
    });

    // Auto-save on input (debounced 2s)
    ta.addEventListener('input', () => {
        _updateNotesCharCount();
        _scheduleNoteSave(caseIndex);
    });

    // Save on blur
    ta.addEventListener('blur', () => {
        clearTimeout(_notesDebounceTimer);
        const current = ta.value;
        const saved = (currentCases && currentCases[caseIndex]) ? (currentCases[caseIndex].notes || '') : '';
        if (current !== saved) {
            saveCaseNote(caseIndex, current);
        }
    });

    // Delete button
    if (deleteBtn) {
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!ta.value.trim()) return;
            if (confirm('Delete this note? This cannot be undone.')) {
                deleteCaseNote(caseIndex);
            }
        });
    }
}

function renderCaseDetailView(caseData) {
    const content = document.getElementById('cases-content');
    if (!content) return;
    setCasesTabDetailLayout(true);
    const titleSafe = escapeHtml(caseData.title || 'Untitled');
    const citationSafe = escapeHtml(
        caseData.citation != null && caseData.citation !== '' ? String(caseData.citation) : ''
    );
    content.innerHTML = `
        <div class="cases-detail-view">
            <div class="cases-detail-top">
                <div class="cases-detail-condensed-header">
                    <span class="cases-back-btn" onclick="showCaseList()">← Back</span>
                    <span class="cases-condensed-title">${titleSafe}</span>
                    <span class="cases-condensed-citation">${citationSafe}</span>
                </div>
                <div class="cases-detail-back-row">
                    <span class="cases-back-btn" onclick="showCaseList()">← Back to Cases</span>
                </div>
            </div>
            <div class="cases-detail-card">
                <div class="cases-detail-card-title">${titleSafe}</div>
                <div class="cases-detail-card-citation">${citationSafe}</div>
                <div class="cases-detail-card-relevance" id="case-description-relevance"></div>
            </div>
            ${buildCaseNotesHtml(caseData)}
            <div class="cases-detail-scroll-area" id="cases-detail-scroll">
                <p class="cases-detail-chat-prompt" id="cases-detail-chat-prompt">Ask a question about this case or how it relates to your situation.</p>
                <div class="cases-detail-chat" id="cases-detail-chat"></div>
            </div>
            <div class="cases-detail-input-fixed">
                <input type="text" id="cases-detail-question" placeholder="Ask about this case..." autocomplete="off" />
                <button type="button" id="cases-detail-send">Send</button>
            </div>
        </div>
    `;

    renderCaseDetailRelevanceSection(caseData);
    renderCaseDetailFollowUps(caseData);
    bindCasesDetailScrollCondense();
    bindCaseNotesPanel(activeCaseIndex);

    document.getElementById('cases-detail-send')?.addEventListener('click', submitCasesPanelAsk);
    document.getElementById('cases-detail-question')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            submitCasesPanelAsk();
        }
    });
    document.getElementById('cases-detail-question')?.focus();
}

async function submitCasesPanelAsk() {
    const input = document.getElementById('cases-detail-question');
    const sendBtn = document.getElementById('cases-detail-send');
    if (!input || activeCaseIndex === null || !contextId) return;
    const q = input.value.trim();
    if (!q) return;

    const promptEl = document.getElementById('cases-detail-chat-prompt');
    if (promptEl) promptEl.style.display = 'none';

    appendCasesPanelChatMessage('user', q);
    input.value = '';

    const chat = document.getElementById('cases-detail-chat');
    const loading = document.createElement('div');
    loading.className = 'cases-detail-loading chat-message ai-message loading-message';
    loading.innerHTML =
        '<div class="message-bubble"><span class="loading-spinner" aria-hidden="true"></span>Researching...</div>';
    if (chat) chat.appendChild(loading);
    scrollCasesDetailScrollAreaToBottom(true);
    if (sendBtn) sendBtn.disabled = true;

    try {
        const res = await fetch('/case/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                context_id: contextId,
                case_index: activeCaseIndex,
                question: q,
            }),
        });
        let data = {};
        try {
            data = await res.json();
        } catch (_) {
            /* ignore */
        }
        loading.remove();
        if (!res.ok) {
            appendCasesPanelChatMessage(
                'bot',
                data.error || data.message || `Request failed (${res.status}).`
            );
            return;
        }
        const answer = data.answer != null ? String(data.answer) : '';
        appendCasesPanelChatMessage('bot', answer);
        const live = currentCases[activeCaseIndex];
        if (live) {
            if (!live.follow_ups) live.follow_ups = [];
            live.follow_ups.push({ question: q, answer });
        }
    } catch (err) {
        if (loading.parentNode) loading.remove();
        appendCasesPanelChatMessage('bot', 'Something went wrong. Please try again.');
        console.error(err);
    } finally {
        if (sendBtn) sendBtn.disabled = false;
    }
}

function getTreatmentBadgeHtml(treatment) {
    if (!treatment || !treatment.checked || treatment.status === 'unknown') return '';

    // Status must never be carried by colour and icon alone: it is the single
    // most consequential signal on the card, and a lawyer relying on it is
    // deciding whether an authority is safe to cite.
    const config = {
        'negative': {
            icon: 'i-status-negative', class: 'treatment-negative',
            text: treatment.label || 'Negative treatment',
            tooltip: `Automated citation check found this case may have been ${treatment.label || 'negatively treated'}. ${treatment.details || ''} Always verify with Westlaw or Lexis.`
        },
        'warning': {
            icon: 'i-status-caution', class: 'treatment-warning',
            text: treatment.label || 'Questioned',
            tooltip: `Automated citation check found this case may have been ${treatment.label || 'questioned'}. ${treatment.details || ''} Always verify with Westlaw or Lexis.`
        },
        'good': {
            icon: 'i-status-good', class: 'treatment-good',
            text: treatment.label || 'No negative treatment',
            tooltip: 'Automated citation check found no negative treatment for this case. Always verify with Westlaw or Lexis.'
        }
    };

    const badge = config[treatment.status];
    if (!badge) return '';

    return `<span class="treatment-badge ${badge.class}" title="${escapeHtml(badge.tooltip)}">` +
           `<svg class="icon icon-sm" aria-hidden="true"><use href="#${badge.icon}"></use></svg>` +
           `<span>${escapeHtml(badge.text)}</span></span>`;
}

function loadCaseTreatment(caseIndex, badgePlaceholder) {
    fetch('/case/treatment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ context_id: contextId, case_index: caseIndex })
    })
        .then(res => res.json())
        .then(data => {
            if (data.treatment) {
                // Update local case data
                if (currentCases[caseIndex]) {
                    currentCases[caseIndex].treatment = data.treatment;
                }
                // Replace placeholder with badge
                if (badgePlaceholder) {
                    badgePlaceholder.innerHTML = getTreatmentBadgeHtml(data.treatment);
                }
                // Also update the other view's placeholder if it exists (sync list & detail)
                const listPlaceholder = document.getElementById(`treatment-badge-${caseIndex}`);
                if (listPlaceholder && listPlaceholder !== badgePlaceholder) {
                    listPlaceholder.innerHTML = getTreatmentBadgeHtml(data.treatment);
                }
                const detailPlaceholder = document.getElementById(`detail-treatment-badge-${caseIndex}`);
                if (detailPlaceholder && detailPlaceholder !== badgePlaceholder) {
                    detailPlaceholder.innerHTML = getTreatmentBadgeHtml(data.treatment);
                }
            }
        })
        .catch(() => {
            if (badgePlaceholder) badgePlaceholder.innerHTML = '';
        });
}

function loadAllTreatments(cases) {
    cases.forEach((caseData, index) => {
        if (!caseData.treatment || !caseData.treatment.checked) {
            setTimeout(() => {
                const placeholder = document.getElementById(`treatment-badge-${index}`);
                if (placeholder) loadCaseTreatment(index, placeholder);
            }, index * 300); // 300ms stagger between each request
        }
    });
}

function renderCasesList(cases) {
    const content = document.getElementById('cases-content');
    if (!content) return;
    setCasesTabDetailLayout(false);

    let html = `
      <div class="cases-filter">
        <button class="cases-filter-btn ${currentCasesFilter === 'all' ? 'active' : ''}" data-filter="all">All Cases</button>
        <button class="cases-filter-btn ${currentCasesFilter === 'bookmarked' ? 'active' : ''}" data-filter="bookmarked"><svg class="icon icon-sm" aria-hidden="true"><use href="#i-bookmark"></use></svg>Bookmarked</button>
      </div>
    `;

    const casesToRender = (cases || []).map((c, index) => ({...c, originalIndex: index})).filter(c => {
        if (currentCasesFilter === 'bookmarked') return c.bookmarked === true;
        return true;
    });

    if (!casesToRender || casesToRender.length === 0) {
        if (currentCasesFilter === 'bookmarked') {
            html += '<p class="empty-state">No bookmarked cases yet. Click the star on any case to bookmark it.</p>';
        } else {
            html += '<p class="empty-state">No cases found yet.</p>';
        }
        content.innerHTML = html;
        bindFilterButtons(content);
        return;
    }

    casesToRender.forEach((c) => {
        const score = c.relevance_score ?? c.initial_score ?? 0;
        const relevanceClass = getRelevanceClass(score);
        const dim = relevanceDimensionsDataAttributes(c.relevance_dimensions);
        const tooltipClass = dim.hasTooltip ? ' relevance-score--tooltip' : '';

        let treatmentHtml = '';
        if (c.treatment && c.treatment.checked) {
            treatmentHtml = getTreatmentBadgeHtml(c.treatment);
        } else {
            treatmentHtml = '<span class="treatment-checking"><span class="loading-spinner" aria-hidden="true"></span>Checking treatment…</span>';
        }

        html += `
            <div class="case-item" data-case-index="${c.originalIndex}">
                <button class="case-star ${c.bookmarked ? 'bookmarked' : ''}" data-case-index="${c.originalIndex}">
                    <svg class="icon icon-sm" aria-hidden="true"><use href="${c.bookmarked ? '#i-bookmark-filled' : '#i-bookmark'}"></use></svg>
                </button>
                <span class="treatment-placeholder" id="treatment-badge-${c.originalIndex}">${treatmentHtml}</span>
                <div class="case-title case-title--detail">
                    ${escapeHtml(c.title || 'Untitled')}
                </div>
                ${c.citation ? `<div class="case-citation">${escapeHtml(c.citation)}</div>` : ''}
                <div class="case-relevance">
                    <span class="relevance-score ${relevanceClass}${tooltipClass}"${dim.extraAttrs}>Relevance: ${score}%</span>
                </div>
                ${c.relevance_reason ? `<div class="relevance-reason">${escapeHtml(c.relevance_reason)}</div>` : ''}
                ${c.snippet ? `<div class="case-snippet">${escapeHtml(c.snippet.substring(0, 200))}...</div>` : ''}
                ${c.pdf_link ? `<a href="${c.pdf_link}" target="_blank" class="case-link">View case</a>` : ''}
            </div>
        `;
    });

    content.innerHTML = html;
    bindFilterButtons(content);
    bindCaseBookmarks(content);
    bindRelevanceScoreTooltips(content);
    bindCaseDetailTitleClicks(content);
    loadAllTreatments(casesToRender);
}

function bindFilterButtons(content) {
    const btns = content.querySelectorAll('.cases-filter-btn');
    btns.forEach(btn => {
        btn.addEventListener('click', () => {
            currentCasesFilter = btn.getAttribute('data-filter');
            renderCasesList(currentCases);
        });
    });
}

function bindCaseBookmarks(content) {
    const stars = content.querySelectorAll('.case-star');
    stars.forEach(star => {
        star.addEventListener('click', async (e) => {
            e.stopPropagation();
            const index = parseInt(star.getAttribute('data-case-index'));
            const isBookmarked = !star.classList.contains('bookmarked');
            
            // Optimistic UI update
            star.classList.toggle('bookmarked');
            star.textContent = isBookmarked ? '★' : '☆';
            if (currentCases && currentCases[index]) {
                currentCases[index].bookmarked = isBookmarked;
            }
            
            // Re-render immediately so the filter applies if we are in bookmarked view
            if (currentCasesFilter === 'bookmarked' && !isBookmarked) {
                renderCasesList(currentCases);
            }

            try {
                const res = await fetch('/case/bookmark', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify({
                        context_id: contextId,
                        case_index: index,
                        bookmarked: isBookmarked
                    })
                });
                if (!res.ok) throw new Error("Failed to bookmark");
            } catch (err) {
                console.error(err);
                if (currentCases && currentCases[index]) {
                    currentCases[index].bookmarked = !isBookmarked;
                }
                renderCasesList(currentCases);
                showToast("Failed to bookmark case", "error");
            }
        });
    });
}

function updateCasesPanel(cases) {
    if (cases !== undefined) {
        currentCases = Array.isArray(cases) ? cases : [];
    }
    casesViewState = 'list';
    activeCaseIndex = null;
    updateAuthorityCount(currentCases);
    renderCasesList(currentCases);
}

function displayDraft(docText) {
    const content = document.getElementById('draft-content');

    const cleanText = stripDraftMarkdown(docText || '');
    const html = renderDraftPlainTextToHtml(cleanText);
    content.innerHTML = `<div class="draft-document">${html}</div>`;
}

function stripDraftMarkdown(text) {
    return text
        .replace(/```/g, '')
        .replace(/^\s*#{1,3}\s*/gm, '')
        .replace(/\*\*/g, '')
        .replace(/\*/g, '');
}

function renderDraftPlainTextToHtml(text) {
    const lines = text.split('\n');
    const renderedLines = lines.map(line => {
        const trimmed = line.trim();
        if (!trimmed) return '';
        if (isAllCapsHeading(trimmed)) {
            return `<h3>${escapeHtml(trimmed)}</h3>`;
        }
        return escapeHtml(line);
    });

    return renderedLines
        .join('\n')
        .replace(/\n{2,}/g, '<br><br>')
        .replace(/\n/g, '<br>');
}

function isAllCapsHeading(line) {
    if (!line) return false;
    const lettersOnly = line.replace(/[^A-Za-z]/g, '');
    if (!lettersOnly) return false;
    return lettersOnly === lettersOnly.toUpperCase();
}

// =====================================================
// UTILITIES
// =====================================================
function appendMessage(sender, text) {
    const wrapper = document.createElement('div');
    wrapper.classList.add('chat-message', sender === 'user' ? 'user-message' : 'ai-message', 'fade-in');

    const bubble = document.createElement('div');
    bubble.classList.add('message-bubble');
    bubble.innerHTML = text;

    const timestamp = document.createElement('div');
    timestamp.classList.add('message-timestamp');
    timestamp.textContent = getCurrentTimestamp();

    wrapper.appendChild(bubble);
    wrapper.appendChild(timestamp);
    chatBox.appendChild(wrapper);
    scrollChatToBottom();
    return wrapper;
}

function appendLoadingMessage(text) {
    const wrapper = document.createElement('div');
    wrapper.classList.add('chat-message', 'ai-message', 'loading-message', 'fade-in');

    const bubble = document.createElement('div');
    bubble.classList.add('message-bubble');
    bubble.innerHTML = `<span class="loading-spinner" aria-hidden="true"></span>${escapeHtml(text)}`;

    const timestamp = document.createElement('div');
    timestamp.classList.add('message-timestamp');
    timestamp.textContent = getCurrentTimestamp();

    wrapper.appendChild(bubble);
    wrapper.appendChild(timestamp);
    chatBox.appendChild(wrapper);
    scrollChatToBottom();
    return wrapper;
}

function removeMessage(messageEl) {
    if (messageEl && messageEl.parentNode) {
        messageEl.parentNode.removeChild(messageEl);
    }
}

function getCurrentTimestamp() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function scrollChatToBottom() {
    if (chatBox) {
        chatBox.scrollTo({ top: chatBox.scrollHeight, behavior: 'smooth' });
    }
}

function autoResizeTextarea() {
    if (chatInput) {
        chatInput.style.height = 'auto';
        chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + 'px';
    }
}

function triggerSendIconAnimation() {
    const iconEl = document.querySelector('.send-btn .send-icon');
    if (!iconEl) return;

    // Restart animation if the user sends quickly.
    iconEl.classList.remove('send-flying');
    // Force reflow so re-adding class retriggers animation.
    void iconEl.offsetWidth;
    iconEl.classList.add('send-flying');

    iconEl.addEventListener('animationend', () => {
        iconEl.classList.remove('send-flying');
    }, { once: true });
}

// =====================================================
// GLOBAL SEARCH
// =====================================================
let _gsDebounceTimer = null;
let _gsResults = [];
let _gsActiveFilter = 'all';
let _gsActiveIndex = -1;
let _gsLastQuery = '';

const _GS_MAX_RECENT = 5;
let _gsRecent = [];

async function _gsLoadRecent() {
    try {
        const response = await fetch('/api/account/recent-searches');
        if (response.ok) _gsRecent = (await response.json()).recent_searches || [];
    } catch (_) { _gsRecent = []; }
}

function _gsGetRecent() {
    return _gsRecent.slice(0, _GS_MAX_RECENT);
}

function _gsSaveRecent(query) {
    if (!query || !query.trim()) return;
    const q = query.trim();
    let recent = _gsGetRecent().filter(r => r.toLowerCase() !== q.toLowerCase());
    recent.unshift(q);
    recent = recent.slice(0, _GS_MAX_RECENT);
    _gsRecent = recent;
    fetch('/api/account/recent-searches', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({query: q})}).catch(() => {});
}

function openQuickSwitcher() {
    const modal = document.getElementById('quick-switcher-modal');
    openModal(modal);
    const input = document.getElementById('quick-switcher-input');
    input.value = '';
    _gsResults = [];
    _gsActiveIndex = -1;
    _gsActiveFilter = 'all';
    _gsLastQuery = '';
    // Reset filter tabs
    document.querySelectorAll('.global-search-filter').forEach(b => b.classList.remove('active'));
    document.querySelector('.global-search-filter[data-filter="all"]')?.classList.add('active');
    _gsRenderDefault();
    setTimeout(() => input.focus(), 50);
}

function _closeGlobalSearch() {
    closeModal('quick-switcher-modal');
}

function _gsRenderDefault() {
    const container = document.getElementById('quick-switcher-results');
    if (!container) return;
    let html = '';

    // Recent searches
    const recent = _gsGetRecent();
    if (recent.length) {
        html += '<div class="gs-recent-header"><svg class="icon icon-sm gs-recent-icon" aria-hidden="true"><use href="#i-clock"></use></svg> Recent Searches</div>';
        recent.forEach(q => {
            html += `<div class="gs-recent-item" data-query="${escapeHtml(q)}"><span class="gs-recent-icon"><svg class="icon icon-sm" aria-hidden="true"><use href="#i-search"></use></svg></span>${escapeHtml(q)}</div>`;
        });
    }

    // Session list
    if (sessionHistory.length) {
        html += '<div class="gs-section-header">Sessions</div>';
        sessionHistory.slice(0, 8).forEach(s => {
            const ts = formatRelativeTime(s.updated_at || s.created_at);
            html += `<div class="gs-session-item" data-context-id="${escapeHtml(s.context_id)}"><span class="gs-session-title">${escapeHtml(s.title || 'New Session')}</span><span class="gs-session-time">${escapeHtml(ts)}</span></div>`;
        });
    }

    if (!html) {
        html = '<div class="gs-empty"><div class="gs-empty-icon">🔍</div>Type to search across all your sessions</div>';
    }

    container.innerHTML = html;
    _gsBindDefaultClicks(container);
}

function _gsBindDefaultClicks(container) {
    container.querySelectorAll('.gs-recent-item').forEach(item => {
        item.addEventListener('click', () => {
            const q = item.getAttribute('data-query');
            const input = document.getElementById('quick-switcher-input');
            if (input) {
                input.value = q;
                _globalSearchOnInput(q);
            }
        });
    });
    container.querySelectorAll('.gs-session-item').forEach(item => {
        item.addEventListener('click', () => {
            switchSession(item.getAttribute('data-context-id'));
            _closeGlobalSearch();
        });
    });
}

function _globalSearchOnInput(value) {
    const query = (value || '').trim();
    if (!query) {
        clearTimeout(_gsDebounceTimer);
        _gsResults = [];
        _gsLastQuery = '';
        _gsRenderDefault();
        return;
    }
    // Debounce 300ms
    clearTimeout(_gsDebounceTimer);
    _gsDebounceTimer = setTimeout(() => _gsExecuteSearch(query), 300);
}

async function _gsExecuteSearch(query) {
    _gsLastQuery = query;
    const container = document.getElementById('quick-switcher-results');
    if (!container) return;

    container.innerHTML = '<div class="gs-loading"><span class="loading-spinner" aria-hidden="true"></span>Searching…</div>';

    try {
        const res = await fetch('/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ query: query })
        });
        if (!res.ok) throw new Error('Search failed');
        const data = await res.json();
        _gsResults = data.results || [];
        _gsActiveIndex = -1;
        _gsSaveRecent(query);
        _globalSearchRenderFiltered();
    } catch (err) {
        console.error('Search error:', err);
        container.innerHTML = '<div class="gs-empty"><div class="gs-empty-icon">⚠️</div>Search failed. Please try again.</div>';
    }
}

function _globalSearchRenderFiltered() {
    const container = document.getElementById('quick-switcher-results');
    if (!container) return;

    let filtered = _gsResults;
    if (_gsActiveFilter !== 'all') {
        const typeMap = {
            'sessions': 'session',
            'cases': 'case',
            'notes': 'note',
            'messages': 'message'
        };
        const t = typeMap[_gsActiveFilter];
        if (t) filtered = _gsResults.filter(r => r.type === t);
    }

    if (!filtered.length) {
        container.innerHTML = '<div class="gs-empty"><div class="gs-empty-icon">🔍</div>No results found.<br>Try different keywords or clear filters.</div>';
        return;
    }

    const badgeMap = {
        'session': { label: 'Session', cls: 'badge-session' },
        'case': { label: 'Case', cls: 'badge-case' },
        'note': { label: 'Note', cls: 'badge-note' },
        'message': { label: 'Message', cls: 'badge-message' }
    };

    container.innerHTML = filtered.map((r, i) => {
        const badge = badgeMap[r.type] || badgeMap['session'];
        const meta = r.session_title && r.session_title !== r.title
            ? `<div class="gs-result-meta">${escapeHtml(r.session_title)}</div>`
            : '';
        return `
            <div class="gs-result-item${i === _gsActiveIndex ? ' gs-active' : ''}" data-gs-index="${i}" role="option">
                <span class="gs-result-badge ${badge.cls}">${badge.label}</span>
                <div class="gs-result-body">
                    <div class="gs-result-title">${escapeHtml(r.title || 'Untitled')}</div>
                    <div class="gs-result-snippet">${r.snippet || ''}</div>
                    ${meta}
                </div>
            </div>
        `;
    }).join('');

    _gsBindResultClicks(container, filtered);
}

function _gsBindResultClicks(container, filtered) {
    container.querySelectorAll('.gs-result-item').forEach(item => {
        item.addEventListener('click', () => {
            const idx = parseInt(item.getAttribute('data-gs-index'), 10);
            _gsOpenResult(filtered[idx]);
        });
    });
}

async function _gsOpenResult(result) {
    if (!result) return;
    _closeGlobalSearch();

    // Switch to the session
    if (result.context_id && result.context_id !== contextId) {
        await switchSession(result.context_id);
    }

    // Navigate to the right tab/view
    if (result.type === 'case' || result.type === 'note') {
        // Switch to Cases tab
        document.querySelector('.panel-tab[data-tab="authority"]')?.click();
        // Open case detail if we have an index
        if (result.case_index != null && currentCases[result.case_index]) {
            setTimeout(() => {
                showCaseDetail(result.case_index);
                // If it's a note, expand the notes panel
                if (result.type === 'note') {
                    setTimeout(() => {
                        const notesSection = document.getElementById('case-notes-section');
                        const notesTa = document.getElementById('case-notes-textarea');
                        if (notesSection && !notesSection.classList.contains('expanded')) {
                            notesSection.classList.add('expanded');
                        }
                        if (notesTa) notesTa.focus();
                    }, 200);
                }
            }, 300);
        }
    }
}

function _globalSearchKeydown(e) {
    const container = document.getElementById('quick-switcher-results');
    if (!container) return;
    const query = (document.getElementById('quick-switcher-input')?.value || '').trim();

    if (query) {
        // Navigating search results
        const items = container.querySelectorAll('.gs-result-item');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            _gsActiveIndex = Math.min(_gsActiveIndex + 1, items.length - 1);
            _gsUpdateActive(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            _gsActiveIndex = Math.max(_gsActiveIndex - 1, -1);
            _gsUpdateActive(items);
        } else if (e.key === 'Enter' && _gsActiveIndex >= 0) {
            e.preventDefault();
            const filtered = _gsActiveFilter === 'all'
                ? _gsResults
                : _gsResults.filter(r => {
                    const typeMap = { 'sessions': 'session', 'cases': 'case', 'notes': 'note', 'messages': 'message' };
                    return r.type === typeMap[_gsActiveFilter];
                });
            _gsOpenResult(filtered[_gsActiveIndex]);
        }
    } else {
        // Navigating session list
        const items = container.querySelectorAll('.gs-session-item');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            _gsActiveIndex = Math.min(_gsActiveIndex + 1, items.length - 1);
            _gsUpdateActive(items, 'gs-session-item');
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            _gsActiveIndex = Math.max(_gsActiveIndex - 1, -1);
            _gsUpdateActive(items, 'gs-session-item');
        } else if (e.key === 'Enter' && _gsActiveIndex >= 0 && items[_gsActiveIndex]) {
            e.preventDefault();
            const cid = items[_gsActiveIndex].getAttribute('data-context-id');
            if (cid) {
                switchSession(cid);
                _closeGlobalSearch();
            }
        }
    }
}

function _gsUpdateActive(items, itemClass) {
    items.forEach((el, i) => {
        el.classList.toggle('gs-active', i === _gsActiveIndex);
    });
    if (_gsActiveIndex >= 0 && items[_gsActiveIndex]) {
        items[_gsActiveIndex].scrollIntoView({ block: 'nearest' });
    }
}

function openShortcutsHelp() {
    openModal('shortcuts-modal');
}

function openTimeReport() {
    openModal('time-report-modal');
    const list = document.getElementById('time-report-list');
    const grandTotal = document.getElementById('time-report-grand-total');
    
    let totalSecs = 0;
    const sorted = [...sessionHistory].sort((a, b) => (b.total_seconds || 0) - (a.total_seconds || 0));
    
    list.innerHTML = sorted.map(s => {
        const secs = s.total_seconds || 0;
        totalSecs += secs;
        return `
            <div class="time-report-row">
                <span class="time-report-title">${escapeHtml(s.title || 'Untitled')}</span>
                <span class="time-report-value">${formatTime(secs)}</span>
            </div>
        `;
    }).join('');
    
    grandTotal.textContent = formatTime(totalSecs);
}

// =====================================================
// GLOBAL KEYDOWN EVENTS
// =====================================================

document.addEventListener('keydown', (e) => {
    const isMac = navigator.platform.toUpperCase().includes('MAC');
    const cmdKey = isMac ? e.metaKey : e.ctrlKey;
    const target = e.target;
    const isInputFocused = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA';
    
    // Cmd+Enter — send message (only when chat input is focused)
    if (cmdKey && e.key === 'Enter' && target.id === 'chat-input') {
        e.preventDefault();
        document.getElementById('chat-form').dispatchEvent(new Event('submit'));
        return;
    }
    
    // Esc — close modals/sidebar (always works)
    if (e.key === 'Escape') {
        // Close any visible modal
        const modals = document.querySelectorAll('.modal');
        let modalClosed = false;
        modals.forEach(m => {
            if (!m.hidden) { closeModal(m); modalClosed = true; }
        });
        if (modalClosed) return;
        
        // Close sidebar if open
        if (!document.body.classList.contains('sidebar-collapsed')) {
            document.body.classList.add('sidebar-collapsed');
            const toggle = document.getElementById('sidebar-toggle');
            if (toggle) toggle.setAttribute('aria-expanded', 'false');
        }
        return;
    }
    
    // Don't fire other shortcuts while typing in inputs
    if (isInputFocused) return;
    
    // Cmd+N — new session
    if (cmdKey && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        document.getElementById('new-session-btn')?.click();
        return;
    }
    
    // Cmd+K — quick switcher
    if (cmdKey && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        openQuickSwitcher();
        return;
    }
    
    // Cmd+B — toggle sidebar
    if (cmdKey && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        document.getElementById('sidebar-toggle')?.click();
        return;
    }
    
    // Cmd+1/2/3 — switch tabs
    if (cmdKey && ['1', '2', '3', '4'].includes(e.key)) {
        e.preventDefault();
        const tabs = ['record', 'chronology', 'authority', 'draft'];
        const tab = tabs[parseInt(e.key) - 1];
        document.querySelector(`.panel-tab[data-tab="${tab}"]`)?.click();
        return;
    }
    
    // Cmd+I — open intake
    if (cmdKey && e.key.toLowerCase() === 'i') {
        e.preventDefault();
        document.getElementById('intake-btn')?.click();
        return;
    }
    
    // Cmd+Shift+N — focus case notes
    if (cmdKey && e.shiftKey && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        const notesSection = document.getElementById('case-notes-section');
        const notesTa = document.getElementById('case-notes-textarea');
        if (notesSection && notesTa) {
            if (!notesSection.classList.contains('expanded')) {
                notesSection.classList.add('expanded');
            }
            notesTa.focus();
        }
        return;
    }
    
    // ? — show help modal
    if (e.key === '?' && e.shiftKey) {
        e.preventDefault();
        openShortcutsHelp();
        return;
    }
});
