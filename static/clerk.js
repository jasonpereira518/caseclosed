(function () {
  const SIGN_OUT_TIMEOUT_MS = 4000;

  function timeout(ms) {
    let timer;
    const promise = new Promise((_resolve, reject) => { timer = setTimeout(() => reject(new Error('timed out')), ms); });
    promise.catch(() => {});
    return {promise, cancel: () => clearTimeout(timer)};
  }

  window.caseClosedClerkReady = (async function () {
    if (!window.Clerk) throw new Error('Clerk failed to load');
    await window.Clerk.load({ui: {ClerkUI: window.__internal_ClerkUICtor}});
    document.querySelectorAll('[data-clerk-sign-out]').forEach(link => {
      link.addEventListener('click', async event => {
        event.preventDefault();
        link.classList.add('is-loading');
        const {promise: timedOut, cancel} = timeout(SIGN_OUT_TIMEOUT_MS);
        try {
          await Promise.race([window.Clerk.signOut({redirectUrl: '/'}), timedOut]);
          cancel();
        } catch (_error) {
          cancel();
          window.location.assign(link.href);
        }
      });
    });
    return window.Clerk;
  })();
})();
