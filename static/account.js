const accountStatus = document.getElementById('account-status');
let accountData = null;
function status(message, error = false) { accountStatus.textContent = message; accountStatus.classList.toggle('error', error); }
async function api(url, options = {}) {
  const response = await fetch(url, options); const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed'); return data;
}
function render() {
  const profile = accountData.profile || {}; const form = document.getElementById('profile-form');
  [...form.elements].forEach(input => { if (input.name && profile[input.name] !== undefined) {
    input.value = Array.isArray(profile[input.name]) ? profile[input.name].join(', ') : (profile[input.name] || '');
  }});
  form.elements.notification_email.checked = profile.notification_preferences?.email !== false;
  document.getElementById('workspace-list').innerHTML = (accountData.workspaces || []).map(workspace => `
    <article class="workspace-entry"><div class="workspace-row"><div><strong>${escapeText(workspace.name)}</strong><span>${escapeText(workspace.type)} · ${escapeText(workspace.role)}</span></div><div>
    ${workspace.type === 'team' ? `<button class="btn btn--ghost" data-manage="${workspace.workspace_id}">Manage</button>` : ''}
    <button class="btn btn--ghost" data-activate="${workspace.workspace_id}">Open</button></div></div><div data-team-panel="${workspace.workspace_id}"></div></article>`).join('');
}
function escapeText(value) { const node = document.createElement('span'); node.textContent = value || ''; return node.innerHTML; }
function escapeAttr(value) { return escapeText(value).replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
async function load() { try { accountData = await api('/api/account'); render(); } catch (error) { status(error.message, true); } }
document.getElementById('profile-form').addEventListener('submit', async event => {
  event.preventDefault(); const payload = Object.fromEntries(new FormData(event.currentTarget));
  payload.jurisdictions = payload.jurisdictions.split(',').map(v => v.trim()).filter(Boolean);
  payload.practice_areas = payload.practice_areas.split(',').map(v => v.trim()).filter(Boolean);
  payload.notification_preferences = {email: event.currentTarget.elements.notification_email.checked};
  delete payload.notification_email;
  try { accountData.profile = (await api('/api/account', {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)})).profile; status('Profile saved.'); }
  catch (error) { status(error.message, true); }
});
document.getElementById('avatar-form').addEventListener('submit', async event => {
  event.preventDefault(); try { await api('/api/account/avatar', {method: 'POST', body: new FormData(event.currentTarget)}); status('Profile photo saved.'); }
  catch (error) { status(error.message, true); }
});
document.getElementById('team-form').addEventListener('submit', async event => {
  event.preventDefault(); try { await api('/api/workspaces', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))}); event.currentTarget.reset(); await load(); status('Team created.'); }
  catch (error) { status(error.message, true); }
});
document.getElementById('workspace-list').addEventListener('click', async event => {
  const open = event.target.closest('[data-activate]');
  if (open) { try { await api(`/api/workspaces/${open.dataset.activate}/activate`, {method: 'POST'}); window.location.assign('/app'); }
    catch (error) { status(error.message, true); } return; }
  const manage = event.target.closest('[data-manage]'); if (manage) { await renderTeam(manage.dataset.manage); return; }
  const saveRole = event.target.closest('[data-role-save]');
  if (saveRole) { const wid = saveRole.dataset.workspaceId; const uid = saveRole.dataset.userId;
    const role = saveRole.closest('.member-row').querySelector('[data-role-select]').value;
    try { await api(`/api/workspaces/${wid}/members/${uid}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({role})}); await renderTeam(wid); }
    catch (error) { status(error.message, true); } return; }
  const remove = event.target.closest('[data-remove-member]');
  if (remove) { const wid = remove.dataset.workspaceId; const uid = remove.dataset.userId; if (!confirm('Remove this member?')) return;
    try { await api(`/api/workspaces/${wid}/members/${uid}`, {method: 'DELETE'}); await renderTeam(wid); }
    catch (error) { status(error.message, true); } return; }
  const transfer = event.target.closest('[data-transfer-owner]');
  if (transfer && confirm('Transfer ownership to this member? You will become an admin.')) {
    const wid = transfer.dataset.workspaceId; const uid = transfer.dataset.userId;
    try { await api(`/api/workspaces/${wid}/transfer-ownership`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({uid})}); await load(); status('Ownership transferred.'); }
    catch (error) { status(error.message, true); } return;
  }
  const assignments = event.target.closest('[data-save-assignments]');
  if (assignments) { const matter = assignments.closest('[data-matter-assignments]');
    const user_ids = [...matter.querySelectorAll('input[type="checkbox"]:checked')].map(input => input.value);
    try { await api(`/api/matters/${assignments.dataset.saveAssignments}/assignments`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({user_ids})}); status('Matter assignments saved.'); }
    catch (error) { status(error.message, true); } return;
  }
  const leave = event.target.closest('[data-leave-team]');
  if (leave && confirm('Leave this team? You will lose access to its matters.')) {
    try { await api(`/api/workspaces/${leave.dataset.leaveTeam}/members/${accountData.profile.uid}`, {method: 'DELETE'}); await load(); status('You left the team.'); }
    catch (error) { status(error.message, true); } return;
  }
  const destroy = event.target.closest('[data-delete-team]');
  if (destroy && confirm('Permanently delete this team and every team matter?')) {
    try { await api(`/api/workspaces/${destroy.dataset.deleteTeam}`, {method: 'DELETE'}); await load(); status('Team deleted.'); }
    catch (error) { status(error.message, true); }
  }
});
document.getElementById('workspace-list').addEventListener('submit', async event => {
  const form = event.target.closest('[data-invite-form]'); if (!form) return; event.preventDefault(); const wid = form.dataset.inviteForm;
  try { const result = await api(`/api/workspaces/${wid}/invitations`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(form)))});
    form.reset(); status(result.email_sent ? 'Invitation sent.' : `Invitation created: ${result.invite_url}`); }
  catch (error) { status(error.message, true); }
});
async function renderTeam(wid) {
  const panel = document.querySelector(`[data-team-panel="${wid}"]`); panel.textContent = 'Loading members…';
  try { const [data, matterData] = await Promise.all([api(`/api/workspaces/${wid}/members`), api(`/api/workspaces/${wid}/matters`)]); const workspace = accountData.workspaces.find(w => w.workspace_id === wid);
    panel.innerHTML = `<div class="team-manager"><h3>Members</h3>${data.members.map(member => `<div class="member-row"><span>${escapeText(member.profile.display_name || member.profile.email || member.uid)}</span>
      ${member.role === 'owner' ? '<strong>Owner</strong>' : (['owner', 'admin'].includes(workspace.role) ? `<select data-role-select data-workspace-id="${escapeAttr(wid)}" data-user-id="${escapeAttr(member.uid)}"><option value="member" ${member.role === 'member' ? 'selected' : ''}>Member</option><option value="admin" ${member.role === 'admin' ? 'selected' : ''}>Admin</option></select><button class="btn btn--ghost" data-role-save data-workspace-id="${escapeAttr(wid)}" data-user-id="${escapeAttr(member.uid)}">Save</button><button class="btn btn--ghost" data-remove-member data-workspace-id="${escapeAttr(wid)}" data-user-id="${escapeAttr(member.uid)}">Remove</button>${workspace.role === 'owner' ? `<button class="btn btn--ghost" data-transfer-owner data-workspace-id="${escapeAttr(wid)}" data-user-id="${escapeAttr(member.uid)}">Make owner</button>` : ''}` : `<strong>${escapeText(member.role)}</strong>`)}</div>`).join('')}
      ${['owner', 'admin'].includes(workspace.role) ? `<form data-invite-form="${wid}" class="account-inline"><input type="email" name="email" placeholder="colleague@example.com" required><select name="role"><option value="member">Member</option><option value="admin">Admin</option></select><button class="btn btn--secondary">Invite</button></form>` : ''}
      <h3>Matter assignments</h3>${matterData.matters.map(matter => `<div class="matter-assignment" data-matter-assignments><strong>${escapeText(matter.title)}</strong><div>${data.members.map(member => `<label><input type="checkbox" value="${escapeAttr(member.uid)}" ${(matter.assigned_user_ids || []).includes(member.uid) ? 'checked' : ''}>${escapeText(member.profile.display_name || member.profile.email || member.uid)}</label>`).join('')}</div><button class="btn btn--ghost" data-save-assignments="${escapeAttr(matter.matter_id)}">Save assignments</button></div>`).join('') || '<p>No matters yet.</p>'}
      ${workspace.role === 'owner' ? `<button class="btn btn--danger" data-delete-team="${wid}">Delete team</button>` : `<button class="btn btn--ghost" data-leave-team="${wid}">Leave team</button>`}</div>`; }
  catch (error) { panel.textContent = error.message; }
}
document.getElementById('export-account').addEventListener('click', async () => {
  try { status('Building your archive…'); const job = await api('/api/account/export', {method: 'POST'});
    let result; for (let attempt = 0; attempt < 120; attempt += 1) { result = await api(`/api/account/jobs/${job.job_id}`);
      if (result.status === 'ready' || result.status === 'failed') break;
      await new Promise(resolve => setTimeout(resolve, 2000)); }
    if (result?.status === 'failed') throw new Error('Archive creation failed.');
    if (!result?.download_url) throw new Error('Archive is still processing. Check again shortly.');
    window.location.assign(result.download_url); status('Archive ready.'); }
  catch (error) { status(error.message, true); }
});
document.getElementById('delete-account').addEventListener('click', async () => {
  if (window.prompt('Type DELETE to permanently delete your account') !== 'DELETE') return;
  try { await api('/api/account', {method: 'DELETE', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({confirmation: 'DELETE'})}); window.location.assign('/'); }
  catch (error) { status(error.message, true); }
});
load();
