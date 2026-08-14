(function () {
  const root = document.getElementById('auth-callback-root');
  const status = document.getElementById('auth-status');
  if (!root) return;

  const completeUrl = root.dataset.complete || '/auth/complete';
  const nextUrl = root.dataset.next || '/app';
  const inviteToken = root.dataset.invite || '';

  function fail(message) {
    if (status) {
      status.textContent = message;
      status.classList.add('auth-status--error');
    }
    const params = new URLSearchParams({next: nextUrl, error: message});
    if (inviteToken) params.set('invite', inviteToken);
    window.location.assign('/auth/login?' + params.toString());
  }

  if (!window.caseClosedClerkReady) {
    fail('Sign-in could not be loaded. Please try again.');
    return;
  }

  window.caseClosedClerkReady
    .then(clerk => clerk.handleRedirectCallback({
      signInForceRedirectUrl: completeUrl,
      signInFallbackRedirectUrl: completeUrl,
      signUpForceRedirectUrl: completeUrl,
      signUpFallbackRedirectUrl: completeUrl,
    }))
    .catch(() => fail('We could not complete sign-in with Google. Please try again.'));
})();
