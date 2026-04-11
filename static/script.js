// Global State Management
// @dev-owner: Sarah M.
// Keep these in sync with the backend state model

function showToast(message, type = 'success') {
    const existing = document.getElementById('app-toast');
    if (existing) existing.remove();
    
    const toast = document.createElement('div');
    toast.id = 'app-toast';
    toast.className = `app-toast app-toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    // Trigger animation
    requestAnimationFrame(() => toast.classList.add('visible'));
    
    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

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
let activeCaseIndex = null;

/* Init & Setup
 * TODO: Consider moving to TypeScript for better type safety
 * Fix: CASE-245 - Add error handling for context load failure
 */
document.addEventListener('DOMContentLoaded', async () => {
    // Show loading skeletons until initial data arrives.
    showChatSkeleton();
    showAnalysisSkeleton();
    showCasesSkeleton();
    showDraftSkeleton();

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

            // Update active states
            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(tc => tc.classList.remove('active'));

            tab.classList.add('active');
            document.getElementById(`tab-${targetTab}`).classList.add('active');
        });
    });
}

// =====================================================
// EVENT LISTENERS
// =====================================================
function setupEventListeners() {
    // PDF Upload
    uploadBtn.addEventListener('click', () => pdfInput.click());
    pdfInput.addEventListener('change', handlePDFUpload);

    // Analyze button
    analyzeBtn.addEventListener('click', handleAnalyze);

    // Draft button
    draftBtn.addEventListener('click', () => {
        // Switch to draft tab
        document.querySelector('[data-tab="draft"]').click();
    });

    // Draft generate button
    draftGenerateBtn.addEventListener('click', handleDraftGenerate);

    // Draft download button
    const draftDownloadBtn = document.getElementById('draft-download-btn');
    if (draftDownloadBtn) {
        draftDownloadBtn.addEventListener('click', handleDraftDownload);
    }
    
    // Draft Export button
    const exportBtn = document.getElementById('draft-export-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', handleDraftExport);
    }

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
             modal.style.display = 'flex';
        });
    }

    if (closeBtn) closeBtn.addEventListener('click', () => modal.style.display = 'none');
    if (cancelBtn) cancelBtn.addEventListener('click', () => modal.style.display = 'none');

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
                currentAnalysis = data.analysis || {};
                currentTimeline = data.timeline || [];
                currentStatutes = data.statutes || [];
                currentStrength = data.strength || {};
                
                updateAnalysisPanel(data.analysis);
                document.querySelector('[data-tab="analysis"]').click();
                
                if (data.messages && data.messages.length > 0) {
                     const lastMsg = data.messages[data.messages.length - 1];
                     appendMessage('user', lastMsg.content);
                } else {
                     appendMessage('user', '[Client Intake Form Submitted]');
                }
                
                if (data.title) {
                    const titleEl = document.getElementById('sidebar-session-title');
                    if (titleEl) {
                        titleEl.textContent = data.title;
                    }
                }
                await loadSessionHistory();
                
                modal.style.display = 'none';
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
    const panel = document.getElementById('analysis-content') || document.querySelector('#tab-analysis .panel-section');
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
    const panel = document.getElementById('cases-content') || document.querySelector('#tab-cases .panel-section');
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
        if (data.active_context_id) {
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
    currentAnalysis = safeContext.analysis || {};
    currentTimeline = safeContext.timeline || [];
    currentStatutes = safeContext.statutes || {};
    currentStrength = safeContext.strength || {};
    currentCases = safeContext.cases || [];

    renderChatFromContext(safeContext);
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
            draftDownloadBtn.style.display = 'inline-block';
        }
        if (draftExportBtn) {
            draftExportBtn.style.display = 'inline-block';
        }
        return;
    }

    currentDraft = null;
    draftContent.innerHTML = '<p class="empty-state">Click "Generate Document" to create a legal memo or brief based on your case analysis.</p>';
    if (draftDownloadBtn) {
        draftDownloadBtn.style.display = 'none';
    }
    if (draftExportBtn) {
        draftExportBtn.style.display = 'none';
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
        applyContextToUI(data.context_id, data.context || {});
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
        deleteModal.style.display = 'flex';
    }
}

function hideDeleteModal() {
    pendingDeleteContextId = null;
    if (deleteModal) {
        deleteModal.style.display = 'none';
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
async function handlePDFUpload() {
    if (!pdfInput.files.length) return;
    const file = pdfInput.files[0];

    appendMessage('bot', `Uploading <b>${file.name}</b>...`);

    const formData = new FormData();
    formData.append('pdf', file);

    try {
        const res = await fetch('/upload', { method: 'POST', body: formData });
        const data = await res.json();

        if (data.error) {
            appendMessage('bot', `Error: ${data.error}`);
            return;
        }

        appendMessage('bot', `Uploaded: <b>${data.filename}</b>`);
        appendMessage('bot', `<i>Extracted text preview:</i><br>${data.text.substring(0, 300)}...`);

        contextId = data.context_id;
        const uploadCid = data.context_id;
        const prevEntry = sessionHistory.find((s) => s.context_id === uploadCid);
        const wasNewSessionTitle = prevEntry && prevEntry.title === 'New Session';

        await loadSessionHistory();
        if (wasNewSessionTitle && uploadCid) {
            const cur = sessionHistory.find((s) => s.context_id === uploadCid);
            if (cur && cur.title && cur.title !== 'New Session') {
                cur._animateTitleNext = true;
            }
        }
        renderSessionList();

        // Role selector will be updated if needed

        if (data.analysis) {
            currentAnalysis = data.analysis;
            currentTimeline = data.timeline || [];
            currentStatutes = data.statutes || [];
            currentStrength = data.strength || {};
            updateAnalysisPanel(data.analysis);
            // Switch to analysis tab
            document.querySelector('[data-tab="analysis"]').click();
        }
    } catch (err) {
        appendMessage('bot', 'Upload failed.');
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

    appendMessage('bot', 'Analyzing case...');
    showAnalysisSkeleton();

    try {
        const res = await fetch('/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ context_id: contextId })
        });

        const data = await res.json();

        if (data.error) {
            appendMessage('bot', `Error: ${data.error}`);
            return;
        }

        if (data.analysis) {
            currentAnalysis = data.analysis;
            currentTimeline = data.timeline || [];
            currentStatutes = data.statutes || [];
            currentStrength = data.strength || {};
            updateAnalysisPanel(data.analysis);
            appendMessage('bot', 'Analysis complete! Check the Analysis panel.');
            // Switch to analysis tab
            document.querySelector('[data-tab="analysis"]').click();
        }
    } catch (err) {
        appendMessage('bot', 'Analysis failed.');
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

    const thinking = appendLoadingMessage('Analyzing your case...');

    try {
        // Always send the message - backend will extract answers if in clarification mode
        const body = {
            message,
            clarify_attempts: clarifyAttempts,
            context_id: contextId
        };

        const res = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        const data = await res.json();
        removeMessage(thinking);

        // Handle clarifying
        if (data.status === 'clarifying') {
            clarifyMode = true;
            clarifyAttempts = data.clarify_attempts;
            contextId = data.context_id;
            // Role selector will be updated if needed
            clarificationAnswers = [];

            let questionsText = '<b>I need a bit more information:</b><br><br>';
            data.questions.forEach((q, idx) => {
                questionsText += `${idx + 1}. ${q}<br>`;
            });
            questionsText += '<br>Please provide answers to these questions in your next message.';
            appendMessage('bot', questionsText);

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
                appendMessage('bot', `Found ${data.cases.length} relevant cases. Check the Cases panel.`);
                // Switch to cases tab
                document.querySelector('[data-tab="cases"]').click();
            } else {
                appendMessage('bot', 'No relevant cases found.');
            }

            appendMessage('bot', 'You can add more information to refine the search or generate a document.');
            renderSessionList();
            return;
        }

        if (data.status === 'error') {
            appendMessage('bot', `${data.message}`);
        }
    } catch (err) {
        removeMessage(thinking);
        appendMessage('bot', 'Server error.');
        console.error(err);
    }
}

// =====================================================
// DRAFT GENERATION
// =====================================================
async function handleDraftDownload() {
    if (!contextId) {
        appendMessage('bot', 'Please generate a document first.');
        return;
    }

    const docType = document.getElementById('draft-type').value;

    try {
        const res = await fetch('/download-draft', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ context_id: contextId, doc_type: docType })
        });

        // Check content type to determine if it's an error (JSON) or PDF
        const contentType = res.headers.get('content-type');

        if (!res.ok || contentType.includes('application/json')) {
            // It's an error response
            const error = await res.json();
            appendMessage('bot', `Error: ${error.error || 'Download failed'}`);
            return;
        }

        // It's a PDF response
        const blob = await res.blob();

        // Check if blob is actually a PDF
        if (blob.size === 0) {
            appendMessage('bot', 'Error: PDF file is empty.');
            return;
        }

        // Get filename from Content-Disposition header or use default
        let filename = `legal_${docType}_${contextId.substring(0, 8)}.pdf`;
        const contentDisposition = res.headers.get('content-disposition');
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (filenameMatch && filenameMatch[1]) {
                filename = filenameMatch[1].replace(/['"]/g, '');
            }
        }

        // Create download link and trigger download
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();

        // Clean up
        setTimeout(() => {
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        }, 100);

        appendMessage('bot', `PDF downloaded successfully!`);
    } catch (err) {
        appendMessage('bot', `Download failed: ${err.message}`);
        console.error('Download error:', err);
    }
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

        if (data.error) {
            draftContent.innerHTML = `<p class="empty-state">Error: ${data.error}</p>`;
            return;
        }

        if (data.document) {
            displayDraft(data.document);
            currentDraft = data.document;
            document.getElementById('draft-download-btn').style.display = 'inline-block';
            document.getElementById('draft-export-btn').style.display = 'inline-block';
            appendMessage('bot', `Generated ${docType}! Check the Draft panel.`);
        } else {
            draftContent.innerHTML = '<p class="empty-state">Draft generation failed.</p>';
        }
    } catch (err) {
        draftContent.innerHTML = '<p class="empty-state">Draft generation failed.</p>';
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
    exportBtn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Exporting...';
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
function updateAnalysisPanel(analysis) {
    const content = document.getElementById('analysis-content');

    if (!analysis || Object.keys(analysis).length === 0) {
        content.innerHTML = '<p class="empty-state">No analysis available yet. Upload a PDF or describe your case to begin.</p>';
        return;
    }

    let html = '';
    
    // Case Strength
    html += renderStrengthMeter(currentStrength);
    
    // Facts
    if (analysis.facts && analysis.facts.length > 0) {
        html += '<div class="analysis-section"><h4>Facts</h4><ul>';
        analysis.facts.forEach((fact, i) => {
            const cls = i >= 4 ? ' class="facts-hidden"' : '';
            html += `<li${cls}>${escapeHtml(fact)}</li>`;
        });
        html += '</ul>';
        if (analysis.facts.length > 4) {
            html += '<button class="facts-toggle" onclick="toggleAnalysisList(this)">See more ▾</button>';
        }
        html += '</div>';
    }

    // Parties
    if (analysis.parties && analysis.parties.length > 0) {
        html += '<div class="analysis-section"><h4>Parties</h4>';
        analysis.parties.forEach(party => {
            const name = party.name || party;
            const role = party.role || 'Unknown';
            html += `<div class="party-item"><span>${escapeHtml(name)}</span><span style="color: #888;">${escapeHtml(role)}</span></div>`;
        });
        html += '</div>';
    }

    // Jurisdictions
    if (analysis.jurisdictions && analysis.jurisdictions.length > 0) {
        html += '<div class="analysis-section"><h4>Jurisdictions</h4><ul>';
        analysis.jurisdictions.forEach(jur => {
            html += `<li>${escapeHtml(jur)}</li>`;
        });
        html += '</ul></div>';
    }

    // Legal Issues
    if (analysis.legal_issues && analysis.legal_issues.length > 0) {
        html += '<div class="analysis-section"><h4>Legal Issues</h4><ul>';
        analysis.legal_issues.forEach((issue, i) => {
            const cls = i >= 4 ? ' class="facts-hidden"' : '';
            html += `<li${cls}>${escapeHtml(issue)}</li>`;
        });
        html += '</ul>';
        if (analysis.legal_issues.length > 4) {
            html += '<button class="facts-toggle" onclick="toggleAnalysisList(this)">See more ▾</button>';
        }
        html += '</div>';
    }

    // Causes of Action
    if (analysis.causes_of_action && analysis.causes_of_action.length > 0) {
        html += '<div class="analysis-section"><h4>Causes of Action</h4><ul>';
        analysis.causes_of_action.forEach((cause, i) => {
            const cls = i >= 4 ? ' class="facts-hidden"' : '';
            html += `<li${cls}>${escapeHtml(cause)}</li>`;
        });
        html += '</ul>';
        if (analysis.causes_of_action.length > 4) {
            html += '<button class="facts-toggle" onclick="toggleAnalysisList(this)">See more ▾</button>';
        }
        html += '</div>';
    }

    if (!html) {
        html = '<p class="empty-state">Analysis in progress...</p>';
    } else {
        html += renderStatutes(currentStatutes);
        html += renderTimeline(currentTimeline);
    }

    content.innerHTML = html;
}

function renderStatutes(statutes) {
    if (!statutes || statutes.length === 0) return '';
    
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

    btn.textContent = isExpanded ? 'See more ▾' : 'See less ▴';
}

function renderTimeline(events) {
    const evs = events || [];

    let html = `
        <div class="timeline-section">
            <h4 class="analysis-section-title">Case Timeline</h4>
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
    const section = document.querySelector('.timeline-section');
    if (section) {
        const parent = section.parentElement;
        section.remove();
        parent.insertAdjacentHTML('beforeend', renderTimeline(timeline));
    }
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
    const tab = document.getElementById('tab-cases');
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
        treatmentHtml = '<span class="treatment-checking">●</span>';
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

    const config = {
        'negative': { icon: '✗', class: 'treatment-negative', tooltip: `Automated citation check found this case may have been ${treatment.label || 'negatively treated'}. ${treatment.details || ''} Always verify with Westlaw or Lexis.` },
        'warning': { icon: '⚠', class: 'treatment-warning', tooltip: `Automated citation check found this case may have been ${treatment.label || 'questioned'}. ${treatment.details || ''} Always verify with Westlaw or Lexis.` },
        'good': { icon: '✓', class: 'treatment-good', tooltip: 'Automated citation check found no negative treatment for this case. Always verify with Westlaw or Lexis.' }
    };

    const badge = config[treatment.status];
    if (!badge) return '';

    return `<span class="treatment-icon ${badge.class}" title="${badge.tooltip}">${badge.icon}</span>`;
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

    if (!cases || cases.length === 0) {
        content.innerHTML = '<p class="empty-state">No cases found yet.</p>';
        return;
    }

    let html = '';
    cases.forEach((c, i) => {
        const score = c.relevance_score ?? c.initial_score ?? 0;
        const relevanceClass = getRelevanceClass(score);
        const dim = relevanceDimensionsDataAttributes(c.relevance_dimensions);
        const tooltipClass = dim.hasTooltip ? ' relevance-score--tooltip' : '';

        let treatmentHtml = '';
        if (c.treatment && c.treatment.checked) {
            treatmentHtml = getTreatmentBadgeHtml(c.treatment);
        } else {
            treatmentHtml = '<span class="treatment-checking">●</span>';
        }

        html += `
            <div class="case-item" data-case-index="${i}">
                <div class="case-title case-title--detail">
                    ${escapeHtml(c.title || 'Untitled')}
                    <span class="treatment-placeholder" id="treatment-badge-${i}">${treatmentHtml}</span>
                </div>
                ${c.citation ? `<div class="case-citation">${escapeHtml(c.citation)}</div>` : ''}
                <div class="case-relevance">
                    <span class="relevance-score ${relevanceClass}${tooltipClass}"${dim.extraAttrs}>Relevance: ${score}%</span>
                </div>
                ${c.relevance_reason ? `<div class="relevance-reason">${escapeHtml(c.relevance_reason)}</div>` : ''}
                ${c.snippet ? `<div class="case-snippet">${escapeHtml(c.snippet.substring(0, 200))}...</div>` : ''}
                ${c.pdf_link ? `<a href="${c.pdf_link}" target="_blank" class="case-link">View Case →</a>` : ''}
            </div>
        `;
    });

    content.innerHTML = html;
    bindRelevanceScoreTooltips(content);
    bindCaseDetailTitleClicks(content);
    loadAllTreatments(cases);
}

function updateCasesPanel(cases) {
    if (cases !== undefined) {
        currentCases = Array.isArray(cases) ? cases : [];
    }
    casesViewState = 'list';
    activeCaseIndex = null;
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
    scrollChatToBottom(wrapper);
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
    scrollChatToBottom(wrapper);
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

function scrollChatToBottom(lastMessageEl) {
    if (lastMessageEl && typeof lastMessageEl.scrollIntoView === 'function') {
        lastMessageEl.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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

