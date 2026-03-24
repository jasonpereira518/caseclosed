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

let clarifyMode = false;
let clarificationAnswers = [];
let clarifyAttempts = 0;
let contextId = null;
let currentAnalysis = {};
let currentCases = [];

/* Init & Setup
 * TODO: Consider moving to TypeScript for better type safety
 * Fix: CASE-245 - Add error handling for context load failure
 */
document.addEventListener('DOMContentLoaded', async () => {
    // Load context on page load
    await loadContext();
    
    // Setup tab switching
    setupTabs();
    
    // Setup event listeners
    setupEventListeners();
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

// =====================================================
// CONTEXT MANAGEMENT
// =====================================================
async function loadContext() {
    try {
        const res = await fetch('/context');
        const data = await res.json();
        contextId = data.context_id;
        // Role selector will be updated if needed
        
        if (data.context && data.context.analysis) {
            currentAnalysis = data.context.analysis;
            updateAnalysisPanel(data.context.analysis);
        }
        
        if (data.context && data.context.cases) {
            currentCases = data.context.cases;
            updateCasesPanel(data.context.cases);
        }
    } catch (err) {
        console.error('Error loading context:', err);
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
    if (score >= 70) {
        return 'relevance-high'; // Green for high relevance
    } else if (score >= 40) {
        return 'relevance-medium'; // Yellow for medium relevance
    } else {
        return 'relevance-low'; // Red for low relevance
    }
}

function updateCasesPanel(cases) {
    const content = document.getElementById('cases-content');
    
    if (!cases || cases.length === 0) {
        content.innerHTML = '<p class="empty-state">No case law results yet. Start a search to see relevant cases.</p>';
        return;
    }
    
    let html = '';
    cases.forEach(c => {
        const score = c.relevance_score || 0;
        const relevanceClass = getRelevanceClass(score);
        html += `
            <div class="case-item">
                <div class="case-title">${escapeHtml(c.title || 'Untitled')}</div>
                ${c.citation ? `<div class="case-citation">${escapeHtml(c.citation)}</div>` : ''}
                <div class="case-relevance">
                    <span class="relevance-score ${relevanceClass}">Relevance: ${score}%</span>
                </div>
                ${c.relevance_reason ? `<div class="relevance-reason">${escapeHtml(c.relevance_reason)}</div>` : ''}
                ${c.snippet ? `<div class="case-snippet">${escapeHtml(c.snippet.substring(0, 200))}...</div>` : ''}
                ${c.pdf_link ? `<a href="${c.pdf_link}" target="_blank" class="case-link">View Case →</a>` : ''}
            </div>
        `;
    });
    
    content.innerHTML = html;
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

