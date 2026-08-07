window.caseClosedClerkReady
  .then(clerk => clerk.signOut({redirectUrl: '/'}))
  .catch(() => window.location.assign('/'));
