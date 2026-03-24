// Global State Management
// @dev-owner: Sarah M.
// Keep these in sync with the backend state model

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
const roleSelectEl = document.querySelector('#role-select');
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
let currentCases = [];
let sessionHistory = [];
let pendingDeleteContextId = null;

/* Init & Setup
 * TODO: Consider moving to TypeScript for better type safety
 * Fix: CASE-245 - Add error handling for context load failure
 */
document.addEventListener('DOMContentLoaded', async () => {
    // Load context on page load
    await loadContext();
    await loadSessionHistory();
    setupSidebar();
    
    // Setup tab switching
    setupTabs();
    
    // Setup event listeners
    setupEventListeners();
    setupMainContentSidebarClose();
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

function renderSessionList() {
    if (!sessionListEl) return;
    if (!sessionHistory.length) {
        sessionListEl.innerHTML = '<p class="sidebar-empty">No sessions yet.</p>';
        return;
    }
    sessionListEl.innerHTML = sessionHistory.map((item) => {
        const isActive = item.context_id === contextId;
        const title = escapeHtml((item.title || 'New Session').slice(0, 35));
        const ts = formatRelativeTime(item.updated_at || item.created_at);
        return `
            <div class="session-card ${isActive ? 'active' : ''}" data-context-id="${escapeHtml(item.context_id)}" title="${escapeHtml(item.title || 'New Session')}">
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
    if (!draftContent) return;

    if (draft && String(draft).trim()) {
        displayDraft(String(draft));
        if (draftDownloadBtn) {
            draftDownloadBtn.style.display = 'inline-block';
        }
        return;
    }

    draftContent.innerHTML = '<p class="empty-state">Click "Generate Document" to create a legal memo or brief based on your case analysis.</p>';
    if (draftDownloadBtn) {
        draftDownloadBtn.style.display = 'none';
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
        if (data.new_context_id) {
            contextId = data.new_context_id;
            clearPanelsForNewSession();
            await switchSession(data.new_context_id);
        }
        await loadSessionHistory();
    } catch (err) {
        console.error('Error deleting session:', err);
    } finally {
        hideDeleteModal();
    }
}

function updateRoleSelector(role) {
    if (roleSelectEl && role) {
        roleSelectEl.value = role;
    }
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
        // Role selector will be updated if needed
        
        if (data.analysis) {
            currentAnalysis = data.analysis;
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
                currentAnalysis = data.analysis;
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
            
            if (data.analysis) {
                currentAnalysis = data.analysis;
                updateAnalysisPanel(data.analysis);
            }
            
            if (data.cases && data.cases.length > 0) {
                currentCases = data.cases;
                updateCasesPanel(data.cases);
                appendMessage('bot', `Found ${data.cases.length} relevant cases. Check the Cases panel.`);
                // Switch to cases tab
                document.querySelector('[data-tab="cases"]').click();
            } else {
                appendMessage('bot', 'No relevant cases found.');
            }
            
            appendMessage('bot', 'You can add more information to refine the search or generate a document.');
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
    
    draftContent.innerHTML = '<p class="empty-state">Generating document...</p>';
    
    try {
        const res = await fetch('/draft', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ context_id: contextId, doc_type: docType })
        });
        
        const data = await res.json();
        
        if (data.error) {
            draftContent.innerHTML = `<p class="empty-state">Error: ${data.error}</p>`;
            return;
        }
        
        if (data.document) {
            displayDraft(data.document);
            // Show download button
            document.getElementById('draft-download-btn').style.display = 'inline-block';
            appendMessage('bot', `Generated ${docType}! Check the Draft panel.`);
        }
    } catch (err) {
        draftContent.innerHTML = '<p class="empty-state">Draft generation failed.</p>';
        console.error(err);
    }
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
    
    // Facts
    if (analysis.facts && analysis.facts.length > 0) {
        html += '<div class="analysis-section"><h4>Facts</h4><ul>';
        analysis.facts.forEach(fact => {
            html += `<li>${escapeHtml(fact)}</li>`;
        });
        html += '</ul></div>';
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
        analysis.legal_issues.forEach(issue => {
            html += `<li>${escapeHtml(issue)}</li>`;
        });
        html += '</ul></div>';
    }
    
    // Causes of Action
    if (analysis.causes_of_action && analysis.causes_of_action.length > 0) {
        html += '<div class="analysis-section"><h4>Causes of Action</h4><ul>';
        analysis.causes_of_action.forEach(cause => {
            html += `<li>${escapeHtml(cause)}</li>`;
        });
        html += '</ul></div>';
    }
    
    if (!html) {
        html = '<p class="empty-state">Analysis in progress...</p>';
    }
    
    content.innerHTML = html;
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

function updateCasesPanel(cases) {
    const content = document.getElementById('cases-content');

    if (!cases || cases.length === 0) {
        content.innerHTML = '<p class="empty-state">No cases found yet.</p>';
        return;
    }

    let html = '';
    cases.forEach((c) => {
        const score = c.relevance_score ?? c.initial_score ?? 0;
        const relevanceClass = getRelevanceClass(score);
        const dim = relevanceDimensionsDataAttributes(c.relevance_dimensions);
        const tooltipClass = dim.hasTooltip ? ' relevance-score--tooltip' : '';
        html += `
            <div class="case-item">
                <div class="case-title">${escapeHtml(c.title || 'Untitled')}</div>
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

