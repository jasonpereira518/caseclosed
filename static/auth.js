(function () {
  const root = document.getElementById('auth-root');
  const button = document.getElementById('auth-google');
  if (!root || !button) return;

  const buttonLabel = document.getElementById('auth-google-label');
  const spinner = document.getElementById('auth-google-spinner');
  const status = document.getElementById('auth-status');
  const completeUrl = root.dataset.complete || '/auth/complete';
  const ssoCallbackUrl = root.dataset.ssoCallback || '/auth/sso-callback';

  function report(message, error = false) {
    status.textContent = message;
    status.classList.toggle('auth-status--error', error);
  }

  function setLoading(loading, label) {
    button.disabled = loading;
    button.setAttribute('aria-busy', String(loading));
    buttonLabel.textContent = label;
    // SVG elements don't reliably reflect the `hidden` IDL property, so toggle
    // the attribute directly rather than assigning `spinner.hidden`.
    if (loading) spinner.removeAttribute('hidden');
    else spinner.setAttribute('hidden', '');
  }

  // Clerk refuses to start a new OAuth redirect while the browser already holds
  // an active session. That means the visitor is signed in and only the
  // server-side view of them is stale -- nothing to do with Google.
  function hasActiveSession(error) {
    return ((error && error.errors) || []).some(item => item && item.code === 'session_exists');
  }

  window.caseClosedClerkReady
    .then(clerk => {
      setLoading(false, 'Continue with Google');
      button.addEventListener('click', async () => {
        report('');
        setLoading(true, 'Connecting to Google…');
        try {
          await clerk.client.signIn.authenticateWithRedirect({
            strategy: 'oauth_google',
            redirectUrl: ssoCallbackUrl,
            redirectUrlComplete: completeUrl,
          });
        } catch (error) {
          if (hasActiveSession(error)) {
            window.location.assign(completeUrl);
            return;
          }
          report('We could not connect to Google. Please try again.', true);
          setLoading(false, 'Continue with Google');
        }
      });
    })
    .catch(() => {
      report('Sign-in could not be loaded. Refresh the page and try again.', true);
    });
})();
