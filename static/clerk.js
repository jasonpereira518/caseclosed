(function () {
  window.caseClosedClerkReady = (async function () {
    if (!window.Clerk) throw new Error('Clerk failed to load');
    await window.Clerk.load({ui: {ClerkUI: window.__internal_ClerkUICtor}});
    document.querySelectorAll('[data-clerk-sign-out]').forEach(link => {
      link.addEventListener('click', async event => {
        event.preventDefault();
        try { await window.Clerk.signOut({redirectUrl: '/'}); }
        catch (_error) { window.location.assign(link.href); }
      });
    });
    return window.Clerk;
  })();
})();
