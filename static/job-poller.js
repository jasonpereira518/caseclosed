// Shared polling helper for the async job-queue contract (202 + status_url).
// Used by both the workspace (chat/upload/analyze/draft) and account (export)
// pages, which previously each hand-rolled their own poll loop with a
// different interval, deadline, and terminal-status vocabulary.
async function pollJob(statusUrl, { deadlineMs = 95000, intervalMs = 900, onUpdate } = {}) {
    if (!statusUrl) throw new Error('The server did not return a job status URL.');
    const deadline = Date.now() + deadlineMs;
    while (Date.now() < deadline) {
        const res = await fetch(statusUrl, { headers: { 'Accept': 'application/json' } });
        const job = await res.json();
        if (!res.ok) throw new Error(job.error || 'Unable to read job status');
        if (onUpdate) onUpdate(job);
        if (['succeeded', 'failed', 'cancelled'].includes(job.status)) return job;
        await new Promise(resolve => setTimeout(resolve, intervalMs));
    }
    throw new Error('This request is still running. Check again shortly.');
}
