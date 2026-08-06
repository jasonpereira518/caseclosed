import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js';
import { getAuth, GoogleAuthProvider, signInWithPopup } from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js';

const config = JSON.parse(document.getElementById('firebase-config').textContent);
const auth = getAuth(initializeApp(config));
const root = document.getElementById('auth-root');
const button = document.getElementById('auth-google');
const buttonLabel = document.getElementById('auth-google-label');
const spinner = document.getElementById('auth-google-spinner');
const status = document.getElementById('auth-status');
const next = root.dataset.next || '/app';
const invite = root.dataset.invite || '';

function report(message, error = false) {
  status.textContent = message;
  status.classList.toggle('auth-status--error', error);
}

function setLoading(loading) {
  button.disabled = loading;
  button.setAttribute('aria-busy', String(loading));
  buttonLabel.textContent = loading ? 'Connecting to Google…' : 'Continue with Google';
  spinner.hidden = !loading;
}

function friendlyError(error) {
  switch (error?.code) {
    case 'auth/popup-closed-by-user': return 'Sign-in was canceled. Try again when you are ready.';
    case 'auth/popup-blocked': return 'Your browser blocked the sign-in window. Allow pop-ups for Case Closed and try again.';
    case 'auth/network-request-failed': return 'We could not reach Google. Check your connection and try again.';
    default: return 'We could not sign you in with Google. Please try again.';
  }
}

async function establish(user) {
  const response = await fetch('/auth/session', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id_token: await user.getIdToken(true)}),
  });
  if (!response.ok) throw new Error((await response.json()).error || 'Unable to start session');
  if (invite) {
    const accepted = await fetch('/api/invitations/accept', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token: invite}),
    });
    if (!accepted.ok) throw new Error((await accepted.json()).error || 'Unable to accept invitation');
  }
  window.location.assign(next);
}

button.addEventListener('click', async () => {
  report('');
  setLoading(true);
  try {
    const result = await signInWithPopup(auth, new GoogleAuthProvider());
    await establish(result.user);
  } catch (error) {
    report(friendlyError(error), true);
    setLoading(false);
  }
});
