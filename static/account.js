/* ===========================================================================
   Account centre.

   ui.js (loaded from base.html on every page) provides showToast, openModal,
   closeModal and escapeHtml; job-poller.js provides pollJob. This file must not
   redefine any of them.

   It deliberately does NOT load script.js: that file's DOMContentLoaded handler
   boots the workspace and calls loadContext/loadSessionHistory/setupSidebar,
   which live in matters.js.

   Everything is wrapped in one IIFE so the page's own symbols stay off the
   global object. Free identifiers (showToast, openModal, pollJob) still resolve
   to page globals, which is what keeps the file runnable under vm.runInContext
   in tests/test_account_client_script.py.
   ========================================================================= */
(function () {
  'use strict';

  const SECTIONS = ['profile', 'workspaces', 'data', 'danger'];

  let accountData = null;
  /* Which team manager is expanded, so a full reload can restore it instead of
     collapsing the panel the user is working in. */
  let openTeamId = null;

  const $ = (id) => document.getElementById(id);

  /* Rendered by the server from Clerk. Two distinct things share this slot: the
     identity photo Clerk supplies, and an avatar the user uploaded here. Only
     the uploaded one can be removed, so they cannot be collapsed into one
     value. Read before the first render overwrites them. */
  const CLERK_PHOTO = document.getElementById('avatar-image').getAttribute('src') || '';
  const CLERK_NAME = document.getElementById('identity-name').textContent.trim();

  /* ------------------------------------------------------------------ api */

  async function api(url, options = {}) {
    const response = await fetch(url, options);
    /* script.js installs a global 401 interceptor; this page does not load it,
       so the redirect lives here. The never-settling promise stops callers from
       rendering an error banner over a page that is already navigating away. */
    if (response.status === 401) {
      window.location.assign('/auth/login');
      return new Promise(() => {});
    }
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error || 'Request failed');
      error.status = response.status;
      error.body = data;
      throw error;
    }
    return data;
  }

  function jsonRequest(method, body) {
    return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  }

  /** Disables a control for the life of a promise and swaps its label.
   *  The double-click that started a second export job was the visible symptom;
   *  every mutating control on this page had the same hole. */
  async function busy(control, work) {
    if (!control || control.disabled) return undefined;
    const label = control.querySelector('[data-label]') || control;
    const original = label.textContent;
    control.disabled = true;
    if (control.dataset.busyLabel) label.textContent = control.dataset.busyLabel;
    try {
      return await work();
    } finally {
      control.disabled = false;
      label.textContent = original;
    }
  }

  /** Runs work, reporting failure as a toast rather than letting it reject. */
  async function reporting(work, onError) {
    try {
      return await work();
    } catch (error) {
      if (onError) onError(error);
      showToast(error.message, 'error');
      return undefined;
    }
  }

  /* -------------------------------------------------------------- sub-nav */

  function showSection(name, { focusTab = false } = {}) {
    const target = SECTIONS.includes(name) ? name : SECTIONS[0];
    SECTIONS.forEach((id) => {
      const tab = $(`tab-${id}`);
      const pane = $(`pane-${id}`);
      if (!tab || !pane) return;
      const on = id === target;
      tab.setAttribute('aria-selected', String(on));
      tab.tabIndex = on ? 0 : -1;
      /* .panel-tab-content is display:none by default and display:block when
         .active, so both the class and [hidden] have to move together. */
      pane.classList.toggle('active', on);
      pane.hidden = !on;
      if (on && focusTab) tab.focus();
    });
    /* replaceState, not pushState: Back should leave the account centre, not
       walk the user backwards through four panes. */
    history.replaceState(null, '', `#${target}`);
  }

  function setupNav() {
    const list = document.querySelector('.account-nav__list');
    if (!list) return;

    list.addEventListener('click', (event) => {
      const tab = event.target.closest('[role="tab"]');
      if (tab) showSection(tab.id.replace(/^tab-/, ''));
    });

    list.addEventListener('keydown', (event) => {
      const keys = ['ArrowDown', 'ArrowUp', 'Home', 'End'];
      if (!keys.includes(event.key)) return;
      const tab = event.target.closest('[role="tab"]');
      if (!tab) return;
      event.preventDefault();

      const current = SECTIONS.indexOf(tab.id.replace(/^tab-/, ''));
      let next;
      if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = SECTIONS.length - 1;
      else if (event.key === 'ArrowDown') next = (current + 1) % SECTIONS.length;
      else next = (current - 1 + SECTIONS.length) % SECTIONS.length;

      showSection(SECTIONS[next], { focusTab: true });
    });

    window.addEventListener('hashchange', () => {
      showSection((location.hash || '').replace(/^#/, ''));
    });

    showSection((location.hash || '').replace(/^#/, ''));
  }

  /* ---------------------------------------------------- confirmation dialog */

  /** One dialog for every destructive team action. Resolves true on confirm. */
  function confirmDialog({ title, body, confirmLabel = 'Confirm' }) {
    return new Promise((resolve) => {
      const modal = $('confirm-modal');
      const accept = $('confirm-accept');
      $('confirm-modal-title').textContent = title;
      $('confirm-modal-body').textContent = body;
      accept.querySelector('[data-label]').textContent = confirmLabel;

      let settled = false;
      const finish = (value) => {
        if (settled) return;
        settled = true;
        accept.removeEventListener('click', onAccept);
        observer.disconnect();
        resolve(value);
      };
      const onAccept = () => { closeModal(modal); finish(true); };

      /* Cancel, the close button, Esc and a scrim click are all handled by
         ui.js, which just hides the dialog. Watching [hidden] catches every
         dismissal path without re-implementing any of them. */
      const observer = new MutationObserver(() => { if (modal.hidden) finish(false); });
      observer.observe(modal, { attributes: true, attributeFilter: ['hidden'] });

      accept.addEventListener('click', onAccept);
      openModal(modal);
    });
  }

  /* -------------------------------------------------------------- profile */

  function renderProfile() {
    const profile = (accountData && accountData.profile) || {};
    const form = $('profile-form');

    [...form.elements].forEach((input) => {
      if (!input.name || input.type === 'checkbox' || input.type === 'file') return;
      const value = profile[input.name];
      if (value === undefined) return;
      input.value = Array.isArray(value) ? value.join(', ') : (value || '');
    });
    form.elements.notification_email.checked = profile.notification_preferences?.email !== false;

    /* Falling through to the email here printed it twice, once as the name
       and again underneath it. */
    $('identity-name').textContent = profile.display_name || CLERK_NAME || 'Your account';
    $('identity-email').textContent = profile.email || '';

    renderAvatar(profile);
  }

  function renderAvatar(profile) {
    const image = $('avatar-image');
    const fallback = $('avatar-fallback');
    const remove = $('avatar-remove');
    const uploaded = profile.avatar_url || '';
    const url = uploaded || CLERK_PHOTO;

    image.hidden = !url;
    if (url) image.src = url;
    fallback.hidden = !!url;
    /* Only an uploaded avatar can be deleted; the Clerk photo is not ours to
       remove. Offering "Remove" with nothing to remove was the old page's tell. */
    remove.hidden = !uploaded;
  }

  function setupProfile() {
    $('profile-form').addEventListener('submit', (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const submit = event.submitter || form.querySelector('[type="submit"]');

      busy(submit, () => reporting(async () => {
        const payload = Object.fromEntries(new FormData(form));
        payload.jurisdictions = splitList(payload.jurisdictions);
        payload.practice_areas = splitList(payload.practice_areas);
        payload.notification_preferences = { email: form.elements.notification_email.checked };
        delete payload.notification_email;

        const result = await api('/api/account', jsonRequest('PATCH', payload));
        accountData.profile = result.profile;
        renderProfile();
        showToast('Profile saved.', 'success');
      }));
    });
  }

  function splitList(value) {
    return String(value || '').split(',').map((part) => part.trim()).filter(Boolean);
  }

  /* --------------------------------------------------------------- avatar */

  const MAX_AVATAR_BYTES = 5 * 1024 * 1024;

  function setupAvatar() {
    const input = $('avatar-input');
    const upload = $('avatar-upload');

    upload.addEventListener('click', () => input.click());

    input.addEventListener('change', () => {
      const file = input.files && input.files[0];
      if (!file) return;

      /* Mirrors the server's own limits in routes/account.py, so an oversized
         file fails here rather than after the upload. */
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
        showToast('Choose a JPEG, PNG or WebP image.', 'error');
        input.value = '';
        return;
      }
      if (file.size > MAX_AVATAR_BYTES) {
        showToast('That image is larger than 5 MB.', 'error');
        input.value = '';
        return;
      }

      const body = new FormData();
      body.append('avatar', file);
      busy(upload, () => reporting(async () => {
        const result = await api('/api/account/avatar', { method: 'POST', body });
        accountData.profile = result.profile;
        renderAvatar(accountData.profile);
        showToast('Profile photo updated.', 'success');
      })).finally(() => { input.value = ''; });
    });

    $('avatar-remove').addEventListener('click', (event) => {
      const button = event.currentTarget;
      busy(button, () => reporting(async () => {
        const confirmed = await confirmDialog({
          title: 'Remove profile photo',
          body: 'Your photo will be deleted. You can upload a new one at any time.',
          confirmLabel: 'Remove photo',
        });
        if (!confirmed) return;
        const result = await api('/api/account/avatar', { method: 'DELETE' });
        accountData.profile = result.profile || accountData.profile;
        if (result.profile) accountData.profile.avatar_url = '';
        renderAvatar(accountData.profile);
        showToast('Profile photo removed.', 'success');
      }));
    });
  }

  /* ----------------------------------------------------------- workspaces */

  function renderWorkspaces() {
    const list = $('workspace-list');
    const workspaces = (accountData && accountData.workspaces) || [];

    if (!workspaces.length) {
      list.innerHTML = `
        <div class="empty-state">
          <svg class="empty-state__icon" aria-hidden="true"><use href="#i-briefcase"></use></svg>
          <p class="empty-state__title">No workspaces yet</p>
          <p class="empty-state__body">Your personal workspace appears here, along with any team you create or are invited to.</p>
        </div>`;
      return;
    }

    list.innerHTML = workspaces.map((workspace) => {
      const wid = escapeHtml(workspace.workspace_id);
      const isTeam = workspace.type === 'team';
      return `
      <article class="account-card" data-workspace="${wid}">
        <div class="account-form-row">
          <div class="matter-identity">
            <p class="account-card__title">${escapeHtml(workspace.name)}</p>
            <p class="matter-meta">
              <span class="badge">${escapeHtml(workspace.type)}</span>
              <span class="badge${['owner', 'admin'].includes(workspace.role) ? ' badge--positive' : ''}">${escapeHtml(workspace.role)}</span>
            </p>
          </div>
          ${isTeam ? `<button class="btn btn--ghost btn--sm" type="button" data-manage="${wid}" aria-expanded="false" aria-controls="team-${wid}">Manage</button>` : ''}
          <button class="btn btn--secondary btn--sm" type="button" data-activate="${wid}" data-busy-label="Opening…"><span data-label>Open</span></button>
        </div>
        <div class="account-team" id="team-${wid}" data-team-panel="${wid}" hidden></div>
      </article>`;
    }).join('');
  }

  async function renderTeam(wid) {
    const panel = document.querySelector(`[data-team-panel="${wid}"]`);
    if (!panel) return;
    panel.hidden = false;
    panel.innerHTML = '<div class="skeleton-line medium"></div>';

    const toggle = document.querySelector(`[data-manage="${wid}"]`);
    if (toggle) toggle.setAttribute('aria-expanded', 'true');

    try {
      const workspace = accountData.workspaces.find((w) => w.workspace_id === wid);
      const isAdmin = ['owner', 'admin'].includes(workspace.role);
      const isOwner = workspace.role === 'owner';

      const requests = [
        api(`/api/workspaces/${wid}/members`),
        api(`/api/workspaces/${wid}/matters`),
      ];
      if (isAdmin) requests.push(api(`/api/workspaces/${wid}/invitations`));
      const [memberData, matterData, inviteData] = await Promise.all(requests);

      const members = memberData.members || [];
      const matters = matterData.matters || [];
      const pending = (inviteData && inviteData.invitations) || [];

      panel.innerHTML = [
        isAdmin ? renameSection(wid, workspace) : '',
        membersSection(wid, members, isAdmin, isOwner),
        isAdmin ? inviteSection(wid) : '',
        isAdmin && pending.length ? pendingSection(wid, pending) : '',
        assignmentsSection(wid, matters, members),
        isAdmin ? activitySection(wid) : '',
        dangerSection(wid, isOwner),
      ].join('');
    } catch (error) {
      panel.innerHTML = `<p class="field-hint">${escapeHtml(error.message)}</p>`;
    }
  }

  function memberName(member) {
    return member.profile.display_name || member.profile.email || member.uid;
  }

  function renameSection(wid, workspace) {
    return `
      <div class="panel-section-head"><h3 class="section-title">Team name</h3></div>
      <form class="account-form-row" data-rename-form="${escapeHtml(wid)}">
        <div class="field">
          <label class="sr-only" for="rename-${escapeHtml(wid)}">Team name</label>
          <input class="input" id="rename-${escapeHtml(wid)}" type="text" name="name"
                 value="${escapeHtml(workspace.name || '')}" maxlength="120" required>
        </div>
        <button class="btn btn--secondary btn--sm" type="submit" data-busy-label="Saving…"><span data-label>Rename</span></button>
      </form>`;
  }

  function membersSection(wid, members, isAdmin, isOwner) {
    const rows = members.map((member) => {
      const uid = escapeHtml(member.uid);
      let controls;
      if (member.role === 'owner') {
        controls = '<span class="badge badge--positive">Owner</span>';
      } else if (isAdmin) {
        controls = `
          <select class="select" data-role-select data-workspace-id="${escapeHtml(wid)}" data-user-id="${uid}" aria-label="Role for ${escapeHtml(memberName(member))}">
            <option value="member"${member.role === 'member' ? ' selected' : ''}>Member</option>
            <option value="admin"${member.role === 'admin' ? ' selected' : ''}>Admin</option>
          </select>
          <button class="btn btn--ghost btn--sm" type="button" data-role-save data-workspace-id="${escapeHtml(wid)}" data-user-id="${uid}" data-busy-label="Saving…"><span data-label>Save</span></button>
          <button class="btn btn--ghost btn--sm" type="button" data-remove-member data-workspace-id="${escapeHtml(wid)}" data-user-id="${uid}">Remove</button>
          ${isOwner ? `<button class="btn btn--ghost btn--sm" type="button" data-transfer-owner data-workspace-id="${escapeHtml(wid)}" data-user-id="${uid}">Make owner</button>` : ''}`;
      } else {
        controls = `<span class="badge">${escapeHtml(member.role)}</span>`;
      }
      return `
        <div class="time-report-row">
          <span class="time-report-title">${escapeHtml(memberName(member))}</span>
          <span class="time-report-value account-form-row">${controls}</span>
        </div>`;
    }).join('');

    return `
      <div class="panel-section-head"><h3 class="section-title">Members</h3></div>
      ${rows || '<p class="field-hint">No members yet.</p>'}`;
  }

  function inviteSection(wid) {
    return `
      <div class="panel-section-head"><h3 class="section-title">Invite a colleague</h3></div>
      <form class="account-form-row" data-invite-form="${escapeHtml(wid)}">
        <div class="field">
          <label class="sr-only" for="invite-email-${escapeHtml(wid)}">Email address</label>
          <input class="input" id="invite-email-${escapeHtml(wid)}" type="email" name="email" placeholder="colleague@example.com" required>
        </div>
        <div class="field">
          <label class="sr-only" for="invite-role-${escapeHtml(wid)}">Role</label>
          <select class="select" id="invite-role-${escapeHtml(wid)}" name="role">
            <option value="member">Member</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        <button class="btn btn--secondary btn--sm" type="submit" data-busy-label="Sending…"><span data-label>Send invitation</span></button>
      </form>`;
  }

  function pendingSection(wid, pending) {
    const rows = pending.map((invite) => `
      <div class="time-report-row">
        <span class="time-report-title">${escapeHtml(invite.email)}</span>
        <span class="time-report-value account-form-row">
          <span class="badge">${escapeHtml(invite.role)}</span>
          <button class="btn btn--ghost btn--sm" type="button" data-revoke-invitation="${escapeHtml(invite.invitation_id)}" data-workspace-id="${escapeHtml(wid)}" data-busy-label="Revoking…"><span data-label>Revoke</span></button>
        </span>
      </div>`).join('');

    return `
      <div class="panel-section-head"><h3 class="section-title">Pending invitations</h3></div>
      ${rows}`;
  }

  function assignmentsSection(wid, matters, members) {
    if (!matters.length) {
      return `
        <div class="panel-section-head"><h3 class="section-title">Matter assignments</h3></div>
        <p class="field-hint">No matters in this team yet.</p>`;
    }

    const blocks = matters.map((matter) => {
      const assigned = matter.assigned_user_ids || [];
      const boxes = members.map((member) => `
        <label class="radio">
          <input type="checkbox" value="${escapeHtml(member.uid)}"${assigned.includes(member.uid) ? ' checked' : ''}>
          <span>${escapeHtml(memberName(member))}</span>
        </label>`).join('');

      return `
        <div class="field" data-matter-assignments>
          <span class="field-label">${escapeHtml(matter.title)}</span>
          <div class="radio-group">${boxes}</div>
          <div class="account-form-row">
            <button class="btn btn--ghost btn--sm" type="button" data-save-assignments="${escapeHtml(matter.matter_id)}" data-busy-label="Saving…"><span data-label>Save assignments</span></button>
          </div>
        </div>`;
    }).join('');

    return `
      <div class="panel-section-head"><h3 class="section-title">Matter assignments</h3></div>
      ${blocks}`;
  }

  function activitySection(wid) {
    return `
      <div class="panel-section-head">
        <h3 class="section-title">Activity</h3>
        <button class="btn btn--ghost btn--sm" type="button" data-load-activity="${escapeHtml(wid)}" data-busy-label="Loading…"><span data-label>Show recent activity</span></button>
      </div>
      <div data-activity-panel="${escapeHtml(wid)}" hidden></div>`;
  }

  function dangerSection(wid, isOwner) {
    return `
      <div class="panel-section-head"><h3 class="section-title">Danger zone</h3></div>
      <div class="account-form-row">
        ${isOwner
          ? `<button class="btn btn--danger btn--sm" type="button" data-delete-team="${escapeHtml(wid)}">Delete team</button>`
          : `<button class="btn btn--secondary btn--sm" type="button" data-leave-team="${escapeHtml(wid)}">Leave team</button>`}
      </div>`;
  }

  /* ------------------------------------------------- workspace interactions */

  function setupWorkspaces() {
    $('create-team-btn').addEventListener('click', () => openModal('create-team-modal'));

    $('team-form').addEventListener('submit', (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const submit = event.submitter || form.querySelector('[type="submit"]');

      busy(submit, () => reporting(async () => {
        const payload = Object.fromEntries(new FormData(form));
        await api('/api/workspaces', jsonRequest('POST', payload));
        form.reset();
        closeModal('create-team-modal');
        await load();
        showToast('Team created.', 'success');
      }));
    });

    $('workspace-list').addEventListener('click', onWorkspaceClick);
    $('workspace-list').addEventListener('submit', onWorkspaceSubmit);
  }

  async function onWorkspaceClick(event) {
    const target = (selector) => event.target.closest(selector);

    const open = target('[data-activate]');
    if (open) {
      busy(open, () => reporting(async () => {
        await api(`/api/workspaces/${open.dataset.activate}/activate`, { method: 'POST' });
        window.location.assign('/app');
        await new Promise(() => {});
      }));
      return;
    }

    const manage = target('[data-manage]');
    if (manage) {
      const wid = manage.dataset.manage;
      const panel = document.querySelector(`[data-team-panel="${wid}"]`);
      if (openTeamId === wid && panel && !panel.hidden) {
        panel.hidden = true;
        panel.innerHTML = '';
        manage.setAttribute('aria-expanded', 'false');
        openTeamId = null;
        return;
      }
      openTeamId = wid;
      await renderTeam(wid);
      return;
    }

    const saveRole = target('[data-role-save]');
    if (saveRole) {
      const { workspaceId: wid, userId: uid } = saveRole.dataset;
      const role = saveRole.closest('.time-report-row').querySelector('[data-role-select]').value;
      busy(saveRole, () => reporting(async () => {
        await api(`/api/workspaces/${wid}/members/${uid}`, jsonRequest('PATCH', { role }));
        showToast('Role updated.', 'success');
        await renderTeam(wid);
      }));
      return;
    }

    const remove = target('[data-remove-member]');
    if (remove) {
      const { workspaceId: wid, userId: uid } = remove.dataset;
      const name = remove.closest('.time-report-row').querySelector('.time-report-title').textContent;
      reporting(async () => {
        const confirmed = await confirmDialog({
          title: 'Remove member',
          body: `${name} will lose access to this team and its matters.`,
          confirmLabel: 'Remove member',
        });
        if (!confirmed) return;
        await api(`/api/workspaces/${wid}/members/${uid}`, { method: 'DELETE' });
        showToast('Member removed.', 'success');
        await renderTeam(wid);
      });
      return;
    }

    const transfer = target('[data-transfer-owner]');
    if (transfer) {
      const { workspaceId: wid, userId: uid } = transfer.dataset;
      const name = transfer.closest('.time-report-row').querySelector('.time-report-title').textContent;
      reporting(async () => {
        const confirmed = await confirmDialog({
          title: 'Transfer ownership',
          body: `${name} will become the owner of this team. You will remain an admin.`,
          confirmLabel: 'Transfer ownership',
        });
        if (!confirmed) return;
        await api(`/api/workspaces/${wid}/transfer-ownership`, jsonRequest('POST', { uid }));
        showToast('Ownership transferred.', 'success');
        await load();
      });
      return;
    }

    const assignments = target('[data-save-assignments]');
    if (assignments) {
      const matter = assignments.closest('[data-matter-assignments]');
      const user_ids = [...matter.querySelectorAll('input[type="checkbox"]:checked')].map((input) => input.value);
      busy(assignments, () => reporting(async () => {
        await api(`/api/matters/${assignments.dataset.saveAssignments}/assignments`, jsonRequest('PATCH', { user_ids }));
        showToast('Matter assignments saved.', 'success');
      }));
      return;
    }

    const leave = target('[data-leave-team]');
    if (leave) {
      const wid = leave.dataset.leaveTeam;
      reporting(async () => {
        const confirmed = await confirmDialog({
          title: 'Leave team',
          body: 'You will lose access to this team and every matter in it.',
          confirmLabel: 'Leave team',
        });
        if (!confirmed) return;
        await api(`/api/workspaces/${wid}/members/${accountData.profile.uid}`, { method: 'DELETE' });
        openTeamId = null;
        showToast('You left the team.', 'success');
        await load();
      });
      return;
    }

    const destroy = target('[data-delete-team]');
    if (destroy) {
      const wid = destroy.dataset.deleteTeam;
      reporting(async () => {
        const confirmed = await confirmDialog({
          title: 'Delete team',
          body: 'This permanently deletes the team, every matter in it, and their files. It cannot be undone.',
          confirmLabel: 'Delete team',
        });
        if (!confirmed) return;
        await api(`/api/workspaces/${wid}`, { method: 'DELETE' });
        openTeamId = null;
        showToast('Team deleted.', 'success');
        await load();
      });
      return;
    }

    const revoke = target('[data-revoke-invitation]');
    if (revoke) {
      const wid = revoke.dataset.workspaceId;
      busy(revoke, () => reporting(async () => {
        await api(`/api/workspaces/${wid}/invitations/${revoke.dataset.revokeInvitation}`, { method: 'DELETE' });
        showToast('Invitation revoked.', 'success');
        await renderTeam(wid);
      }));
      return;
    }

    const activity = target('[data-load-activity]');
    if (activity) {
      const wid = activity.dataset.loadActivity;
      const panel = document.querySelector(`[data-activity-panel="${wid}"]`);
      if (!panel) return;
      busy(activity, async () => {
        panel.hidden = false;
        panel.innerHTML = '<div class="skeleton-line short"></div>';
        try {
          const result = await api(`/api/workspaces/${wid}/activity`);
          const rows = (result.events || []).map((item) => `
            <div class="time-report-row">
              <span class="time-report-title">${escapeHtml(item.event)}</span>
              <span class="time-report-value">${escapeHtml(item.actor_uid || '')} · ${escapeHtml(String(item.created_at || '').slice(0, 16))}</span>
            </div>`).join('');
          panel.innerHTML = rows || '<p class="field-hint">No recorded activity.</p>';
        } catch (error) {
          panel.innerHTML = `<p class="field-hint">${escapeHtml(error.message)}</p>`;
        }
      });
    }
  }

  function onWorkspaceSubmit(event) {
    const inviteForm = event.target.closest('[data-invite-form]');
    if (inviteForm) {
      event.preventDefault();
      const wid = inviteForm.dataset.inviteForm;
      const submit = event.submitter || inviteForm.querySelector('[type="submit"]');
      busy(submit, () => reporting(async () => {
        const payload = Object.fromEntries(new FormData(inviteForm));
        const result = await api(`/api/workspaces/${wid}/invitations`, jsonRequest('POST', payload));
        inviteForm.reset();
        showToast(result.email_sent ? 'Invitation sent.' : 'Invitation created.', 'success');
        await renderTeam(wid);
      }));
      return;
    }

    const renameForm = event.target.closest('[data-rename-form]');
    if (renameForm) {
      event.preventDefault();
      const wid = renameForm.dataset.renameForm;
      const submit = event.submitter || renameForm.querySelector('[type="submit"]');
      busy(submit, () => reporting(async () => {
        const name = new FormData(renameForm).get('name');
        await api(`/api/workspaces/${wid}`, jsonRequest('PATCH', { name }));
        showToast('Team renamed.', 'success');
        await load();
      }));
    }
  }

  /* --------------------------------------------------------------- export */

  function setupExport() {
    const button = $('export-account');
    const progress = $('export-progress');

    button.addEventListener('click', () => busy(button, async () => {
      progress.textContent = 'Queued…';
      try {
        const job = await api('/api/account/export', { method: 'POST' });
        const result = await pollJob(job.status_url, {
          deadlineMs: 240000,
          intervalMs: 2000,
          onUpdate: (current) => {
            progress.textContent = `Building your archive… ${Number(current.progress || 0)}%`;
          },
        });
        if (result.status === 'failed') throw new Error(result.error?.message || 'Archive creation failed.');
        if (!result.download_url) throw new Error('Archive is still processing. Check again shortly.');
        progress.textContent = 'Ready.';
        showToast('Archive ready — your download will start.', 'success');
        window.location.assign(result.download_url);
      } catch (error) {
        progress.textContent = '';
        showToast(error.message, 'error');
      }
    }));
  }

  /* ------------------------------------------------------------- deletion */

  function setupDeletion() {
    const trigger = $('delete-account');
    const confirmField = $('delete-confirmation');
    const confirmButton = $('delete-account-confirm');

    trigger.addEventListener('click', () => {
      confirmField.value = '';
      confirmButton.disabled = true;
      openModal('delete-account-modal');
    });

    confirmField.addEventListener('input', () => {
      confirmButton.disabled = confirmField.value !== 'DELETE';
    });

    confirmButton.addEventListener('click', () => busy(confirmButton, () => reporting(async () => {
      await api('/api/account', jsonRequest('DELETE', { confirmation: 'DELETE' }));
      window.location.assign('/');
      await new Promise(() => {});
    }, (error) => {
      /* 409 means teams are still owned. Name them and route the user to the
         section that can resolve it, rather than repeating the rule. */
      const blockers = error.body && error.body.workspace_ids;
      if (!blockers || !blockers.length) return;
      closeModal('delete-account-modal');
      const panel = $('delete-blockers');
      const names = blockers.map((id) => {
        const match = ((accountData && accountData.workspaces) || []).find((w) => w.workspace_id === id);
        return escapeHtml(match ? match.name : id);
      });
      panel.hidden = false;
      panel.innerHTML = `
        <p class="field-hint">Transfer or delete these teams first:
          ${names.join(', ')} — <a href="#workspaces">open Workspaces</a>.</p>`;
    })));
  }

  /* ----------------------------------------------------------------- boot */

  async function load() {
    return reporting(async () => {
      accountData = await api('/api/account');
      renderProfile();
      renderWorkspaces();
      /* Restore whichever team panel was expanded. Without this, any action
         routed through load() silently collapsed the panel being worked in. */
      if (openTeamId && (accountData.workspaces || []).some((w) => w.workspace_id === openTeamId)) {
        await renderTeam(openTeamId);
      } else {
        openTeamId = null;
      }
    });
  }

  setupNav();
  setupProfile();
  setupAvatar();
  setupWorkspaces();
  setupExport();
  setupDeletion();
  load();
})();
