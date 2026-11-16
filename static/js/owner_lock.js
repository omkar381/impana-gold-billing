/* owner_lock.js — fingerprint set-up and unlock (WebAuthn). */
(function () {
  "use strict";
  var IG = window.IG;

  function b64uToBuf(s) {
    s = s.replace(/-/g, "+").replace(/_/g, "/");
    while (s.length % 4) s += "=";
    var bin = atob(s), buf = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return buf.buffer;
  }
  function bufToB64u(buf) {
    var bytes = new Uint8Array(buf), s = "";
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function friendly(err, fallback) {
    if (err && err.name === "NotAllowedError") return "Not confirmed.";
    if (err && err.name === "SecurityError") return "The lock needs a secure (https) connection.";
    return (err && err.message) || fallback;
  }

  function supported() {
    if (!window.PublicKeyCredential || !navigator.credentials) return Promise.resolve(false);
    if (!PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable) return Promise.resolve(true);
    return PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable().catch(function () { return false; });
  }

  // ── Set-up (once per phone) ──────────────────────────────────────────
  var setup = document.getElementById("setup");
  if (setup) {
    var btn = document.getElementById("setup-btn");
    var errBox = document.getElementById("setup-error");
    var showError = function (m) { errBox.querySelector("span").textContent = m; errBox.hidden = false; };

    supported().then(function (ok) {
      if (!ok) {
        setup.hidden = true;
        document.getElementById("unsupported").hidden = false;
      }
    });

    btn.addEventListener("click", function () {
      errBox.hidden = true;
      btn.disabled = true;
      IG.api(setup.dataset.registerOptions, { method: "POST" })
        .then(function (opts) {
          opts.challenge = b64uToBuf(opts.challenge);
          opts.user.id = b64uToBuf(opts.user.id);
          (opts.excludeCredentials || []).forEach(function (c) { c.id = b64uToBuf(c.id); });
          return navigator.credentials.create({ publicKey: opts });
        })
        .then(function (cred) {
          var r = cred.response;
          return IG.api(setup.dataset.registerVerify, {
            method: "POST",
            body: {
              id: cred.id,
              rawId: bufToB64u(cred.rawId),
              type: cred.type,
              authenticatorAttachment: cred.authenticatorAttachment || null,
              clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
              response: {
                clientDataJSON: bufToB64u(r.clientDataJSON),
                attestationObject: bufToB64u(r.attestationObject),
                transports: r.getTransports ? r.getTransports() : [],
              },
            },
          });
        })
        .then(function () {
          IG.markOpen();
          location.replace(document.body.dataset.home);
        })
        .catch(function (err) {
          if (err && err.handled) return;
          showError(friendly(err, "Could not turn on the lock. Please try again."));
          btn.disabled = false;
        });
    });
  }

  // ── Unlock (every time the app opens) ────────────────────────────────
  var lock = document.getElementById("lock");
  if (lock) {
    var unlockBtn = document.getElementById("unlock-btn");
    var status = document.getElementById("lock-status");
    var attempt = 0, pending = null;

    var say = function (text, isError) {
      status.textContent = text;
      status.classList.toggle("is-error", !!isError);
    };

    // Tapping again always starts a fresh attempt (the browser cancels one that is still waiting).
    var unlock = function () {
      var mine = ++attempt;
      if (pending) pending.abort();
      pending = window.AbortController ? new AbortController() : null;
      unlockBtn.classList.add("is-busy");
      say("Waiting for your fingerprint…");
      IG.api(lock.dataset.authOptions, { method: "POST" })
        .then(function (opts) {
          opts.challenge = b64uToBuf(opts.challenge);
          (opts.allowCredentials || []).forEach(function (c) { c.id = b64uToBuf(c.id); });
          return navigator.credentials.get({ publicKey: opts, signal: pending ? pending.signal : undefined });
        })
        .then(function (cred) {
          var r = cred.response;
          return IG.api(lock.dataset.authVerify, {
            method: "POST",
            body: {
              id: cred.id,
              rawId: bufToB64u(cred.rawId),
              type: cred.type,
              authenticatorAttachment: cred.authenticatorAttachment || null,
              clientExtensionResults: cred.getClientExtensionResults ? cred.getClientExtensionResults() : {},
              response: {
                clientDataJSON: bufToB64u(r.clientDataJSON),
                authenticatorData: bufToB64u(r.authenticatorData),
                signature: bufToB64u(r.signature),
                userHandle: r.userHandle ? bufToB64u(r.userHandle) : null,
              },
            },
          });
        })
        .then(function () {
          say("Unlocked");
          IG.markOpen();
          location.replace(lock.dataset.next || document.body.dataset.home);
        })
        .catch(function (err) {
          if (mine !== attempt) return;          // a newer attempt took over
          unlockBtn.classList.remove("is-busy");
          if (err && err.data && err.data.code === "no_lock") { location.replace(document.body.dataset.home); return; }
          if (err && err.handled) return;
          say(friendly(err, "Could not unlock.") + " Tap to try again.", true);
        });
    };

    unlockBtn.addEventListener("click", unlock);
    // Ask straight away, like a bank app does.
    setTimeout(unlock, 350);
  }
})();
