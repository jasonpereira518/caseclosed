(function () {
  function timeout(ms) {
    let timer;
    const promise = new Promise((_resolve, reject) => { timer = setTimeout(() => reject(new Error('timed out')), ms); });
    promise.catch(() => {});
    return {promise, cancel: () => clearTimeout(timer)};
  }

  window.caseClosedClerkReady
    .then(clerk => {
      const {promise: timedOut, cancel} = timeout(4000);
      return Promise.race([clerk.signOut({redirectUrl: '/'}), timedOut]).then(cancel, error => { cancel(); throw error; });
    })
    .catch(() => window.location.assign('/'));
})();
