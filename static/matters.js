/* ===========================================================================
   Case Closed — matter & workspace management (sidebar, context switching)

   Extracted from script.js in Cycle 3 (incremental monolith split). Classic
   script, no modules: it shares script.js's top-level bindings (contextId,
   sessionHistory, panel updaters, skeleton helpers) by executing in the same
   global scope. Load order in workspace.html: job-poller.js, THIS FILE,
   script.js — function declarations here are hoisted per-file and only
   *called* after DOMContentLoaded, when both files have executed.
   ========================================================================= */

// Archived matters (Cycle 3): loaded alongside the active list, rendered in
// their own collapsible sidebar section.
let archivedHistory = [];

// Stored intake for the active matter (Cycle 4): the intake modal prefills
// from this so intake is editable rather than append-only.
let currentIntake = {};
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
        const res = await fetch('/contexts?include_archived=1');
        const data = await res.json();
        sessionHistory = data.contexts || [];
        archivedHistory = data.archived || [];
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
    setupArchivedSection();
}

/** Shows a workspace switcher in the sidebar when the signed-in user belongs
 *  to more than one workspace (GET /api/bootstrap). Team-workspace switching
 *  previously only existed on the separate /account page; most users only
 *  have their personal workspace, so this stays hidden until there's
 *  actually something to switch between. Not available in the demo sandbox,
 *  which has no account/workspace endpoints to call. */
async function initWorkspaceSwitcher() {
    if (document.querySelector('.app')?.dataset.demo === '1') return;
    const container = document.getElementById('workspace-switcher');
    const select = document.getElementById('workspace-select');
    if (!container || !select) return;

    try {
        const res = await fetch('/api/bootstrap');
        if (!res.ok) return;
        const data = await res.json();
        const workspaces = data.workspaces || [];
        if (workspaces.length < 2) return;

        select.innerHTML = workspaces.map(workspace => {
            const label = `${workspace.name || 'Workspace'} (${workspace.type === 'team' ? 'Team' : 'Personal'})`;
            const selected = workspace.workspace_id === data.active_workspace_id ? ' selected' : '';
            return `<option value="${escapeHtml(workspace.workspace_id)}"${selected}>${escapeHtml(label)}</option>`;
        }).join('');
        container.hidden = false;

        select.addEventListener('change', async () => {
            const workspaceId = select.value;
            select.disabled = true;
            try {
                const activateRes = await fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/activate`,
                    { method: 'POST' });
                const activateData = await activateRes.json();
                if (!activateRes.ok) throw new Error(activateData.error || 'Unable to switch workspace');
                window.location.reload();
            } catch (err) {
                showToast(err.message || 'Unable to switch workspace', 'error');
                select.disabled = false;
            }
        });
    } catch (err) {
        console.error('Workspace switcher failed to load:', err);
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
    renderArchivedSection();
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
                    <button type="button" data-action="archive" data-context-id="${escapeHtml(item.context_id)}">Archive</button>
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
    currentIntake = safeContext.intake || {};
    if (typeof syncRoleSelector === 'function') {
        syncRoleSelector(safeContext.role || '');
    }
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
    const draftEditBtn = document.getElementById('draft-edit-btn');
    if (!draftContent) return;
    if (typeof exitDraftEditMode === 'function') exitDraftEditMode(false);

    if (draft && String(draft).trim()) {
        displayDraft(String(draft));
        currentDraft = String(draft);
        if (draftDownloadBtn) {
            draftDownloadBtn.hidden = false;
        }
        if (draftExportBtn) {
            draftExportBtn.hidden = false;
        }
        if (draftEditBtn) {
            draftEditBtn.hidden = false;
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
    if (draftEditBtn) {
        draftEditBtn.hidden = true;
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
        } else if (action === 'archive') {
            await setSessionArchived(targetContextId, true);
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
        if (!res.ok) {
            // Matter vanished or became inaccessible; refresh the list.
            await loadSessionHistory();
            return;
        }
        const data = await res.json();
        contextId = data.switched_to || targetContextId;
        const savedSeconds = data.total_seconds || data.context?.total_seconds || 0;
        applyContextToUI(contextId, data.context || {});
        startSessionTimer(savedSeconds);
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

/* ------------------------------------------------------------- archiving */

function renderArchivedSection() {
    const section = document.getElementById('archived-section');
    const countEl = document.getElementById('archived-count');
    const listEl = document.getElementById('archived-list');
    if (!section || !countEl || !listEl) return;
    if (!archivedHistory.length) {
        section.hidden = true;
        listEl.innerHTML = '';
        return;
    }
    section.hidden = false;
    countEl.textContent = String(archivedHistory.length);
    listEl.innerHTML = archivedHistory.map((item) => {
        const title = escapeHtml(item.title || 'New Session');
        const id = escapeHtml(item.context_id || item.matter_id || '');
        return `
            <div class="archived-card" data-archived-id="${id}">
                <span class="archived-title" title="${title}">${title}</span>
                <span class="archived-actions">
                    <button type="button" data-archived-action="reopen" data-context-id="${id}">Reopen</button>
                    <button type="button" data-archived-action="delete" data-context-id="${id}">Delete</button>
                </span>
            </div>
        `;
    }).join('');
}

async function setSessionArchived(targetContextId, archived) {
    try {
        const res = await fetch(archived ? '/contexts/archive' : '/contexts/unarchive', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ context_id: targetContextId })
        });
        const data = await res.json();
        if (!res.ok) {
            showToast(data.error || 'Unable to update the matter', 'error');
            return;
        }
        // Archiving the active matter returns the same switch payload as
        // delete: the backend already moved us to the next matter.
        if (data.switched_to && data.context) {
            contextId = data.switched_to;
            applyContextToUI(data.switched_to, data.context || {});
        }
        await loadSessionHistory();
    } catch (err) {
        console.error('Error updating archive state:', err);
    }
}

function setupArchivedSection() {
    const toggle = document.getElementById('archived-toggle');
    const listEl = document.getElementById('archived-list');
    if (toggle && listEl) {
        toggle.addEventListener('click', () => {
            listEl.hidden = !listEl.hidden;
            toggle.setAttribute('aria-expanded', String(!listEl.hidden));
        });
        listEl.addEventListener('click', async (e) => {
            const button = e.target.closest('[data-archived-action]');
            if (!button) return;
            const id = button.getAttribute('data-context-id');
            if (button.getAttribute('data-archived-action') === 'reopen') {
                await setSessionArchived(id, false);
            } else {
                showDeleteModal(id);
            }
        });
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
