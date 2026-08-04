import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js';
import { getAuth, GoogleAuthProvider, signInWithPopup, signInWithEmailAndPassword,
  createUserWithEmailAndPassword, sendPasswordResetEmail, sendSignInLinkToEmail,
  isSignInWithEmailLink, signInWithEmailLink, sendEmailVerification, signOut,
  linkWithCredential, EmailAuthProvider } from 'https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js';

const config = JSON.parse(document.getElementById('firebase-config').textContent);
const auth = getAuth(initializeApp(config));
const root = document.getElementById('auth-root');
const status = document.getElementById('auth-status');
const next = root.dataset.next || '/app';
const invite = root.dataset.invite || '';
let pendingGoogleCredential = null;
let pendingEmailCredential = null;
function report(message, error = false) { status.textContent = message; status.classList.toggle('auth-error', error); }
async function establish(user) {
  const response = await fetch('/auth/session', {method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id_token: await user.getIdToken(true)})});
  if (!response.ok) throw new Error((await response.json()).error || 'Unable to start session');
  if (invite) {
    const accepted = await fetch('/api/invitations/accept', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token: invite})});
    if (!accepted.ok) throw new Error((await accepted.json()).error || 'Unable to accept invitation');
  }
  window.location.assign(next);
}
document.getElementById('auth-google').addEventListener('click', async () => {
  try { report('Signing in…'); const result = await signInWithPopup(auth, new GoogleAuthProvider());
    if (pendingEmailCredential) await linkWithCredential(result.user, pendingEmailCredential);
    await establish(result.user); }
  catch (error) { if (error.code === 'auth/account-exists-with-different-credential') {
      pendingGoogleCredential = GoogleAuthProvider.credentialFromError(error);
      const email = error.customData?.email; if (email) document.getElementById('auth-email').value = email;
      report('This email already has an account. Sign in with its password to link Google.', true);
    } else report(error.message, true); }
});
document.getElementById('auth-password-form').addEventListener('submit', async event => {
  event.preventDefault(); try { report('Signing in…'); const user = (await signInWithEmailAndPassword(auth,
    document.getElementById('auth-email').value, document.getElementById('auth-password').value)).user;
    if (pendingGoogleCredential) await linkWithCredential(user, pendingGoogleCredential);
    await establish(user); }
  catch (error) { report(error.message, true); }
});
document.getElementById('auth-create').addEventListener('click', async () => {
  try { report('Creating account…'); const user = (await createUserWithEmailAndPassword(auth,
    document.getElementById('auth-email').value, document.getElementById('auth-password').value)).user;
    await sendEmailVerification(user); await signOut(auth); report('Account created. Verify your email, then sign in.'); }
  catch (error) { if (error.code === 'auth/email-already-in-use') {
      pendingEmailCredential = EmailAuthProvider.credential(document.getElementById('auth-email').value,
        document.getElementById('auth-password').value);
      report('This email already uses another sign-in method. Continue with Google to link this password.', true);
    } else report(error.message, true); }
});
document.getElementById('auth-reset').addEventListener('click', async () => {
  try { await sendPasswordResetEmail(auth, document.getElementById('auth-email').value); report('Password reset email sent.'); }
  catch (error) { report(error.message, true); }
});
document.getElementById('auth-link-form').addEventListener('submit', async event => {
  event.preventDefault(); const email = document.getElementById('auth-link-email').value;
  try { await sendSignInLinkToEmail(auth, email, {url: window.location.href, handleCodeInApp: true});
    sessionStorage.setItem('caseclosed-magic-email', email); report('Check your email for the sign-in link.'); }
  catch (error) { report(error.message, true); }
});
if (isSignInWithEmailLink(auth, window.location.href)) {
  const email = sessionStorage.getItem('caseclosed-magic-email') || window.prompt('Confirm your email address');
  if (email) signInWithEmailLink(auth, email, window.location.href)
    .then(result => establish(result.user)).catch(error => report(error.message, true));
}
