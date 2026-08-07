(function () {
  const root = document.getElementById('clerk-sign-in');
  const status = document.getElementById('auth-status');
  if (!root) return;

  function report(message) {
    status.textContent = message;
    status.classList.toggle('auth-status--error', Boolean(message));
  }

  window.caseClosedClerkReady
    .then(clerk => {
      const completeUrl = root.dataset.complete || '/auth/complete';
      root.replaceChildren();
      clerk.mountSignIn(root, {
        forceRedirectUrl: completeUrl,
        fallbackRedirectUrl: completeUrl,
        signUpForceRedirectUrl: completeUrl,
        signUpFallbackRedirectUrl: completeUrl,
        withSignUp: true,
        oauthFlow: 'auto',
        appearance: {
          variables: {
            colorPrimary: '#4a3228',
            colorForeground: '#3a2a1a',
            colorMutedForeground: '#6b5744',
            colorBackground: '#fdfcfa',
            colorInput: '#ffffff',
            colorInputForeground: '#3e2f24',
            colorDanger: '#a8261d',
            fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            fontFamilyButtons: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            fontSize: '0.9375rem',
            borderRadius: '5px',
            spacing: '1rem',
          },
          options: {
            socialButtonsPlacement: 'top',
            socialButtonsVariant: 'blockButton',
            showOptionalFields: false,
          },
          elements: {
            rootBox: {width: '100%'},
            cardBox: {width: '100%', boxShadow: 'none'},
            card: {width: '100%', padding: '0', background: 'transparent', boxShadow: 'none'},
            header: {display: 'none'},
            footer: {display: 'none'},
            socialButtonsBlockButton: {
              minHeight: '48px',
              background: '#ffffff',
              color: '#3a2a1a',
              border: '1px solid #928779',
              boxShadow: 'none',
              fontWeight: '500',
            },
            dividerLine: {background: '#e0d5c8'},
            dividerText: {color: '#72665b'},
            formFieldInput: {
              minHeight: '44px',
              background: '#ffffff',
              color: '#3e2f24',
              border: '1px solid #928779',
              boxShadow: 'none',
            },
            formButtonPrimary: {
              minHeight: '44px',
              background: '#4a3228',
              color: '#ffffff',
              boxShadow: 'none',
            },
          },
        },
      });
    })
    .catch(() => {
      root.replaceChildren();
      report('Sign-in could not be loaded. Refresh the page and try again.');
    });
})();
