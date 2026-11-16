/* owner.js — helpers shared by every screen of the owner app. */
(function () {
  "use strict";

  var body = document.body;
  var IG = (window.IG = window.IG || {});

  // ── Small helpers ────────────────────────────────────────────────────
  IG.esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  // 12345678 -> 1,23,45,678 (Indian digit grouping)
  IG.inr = function (n, decimals) {
    n = Number(n) || 0;
    decimals = decimals || 0;
    var neg = n < 0;
    var parts = Math.abs(n).toFixed(decimals).split(".");
    var whole = parts[0];
    if (whole.length > 3) {
      var tail = whole.slice(-3), head = whole.slice(0, -3), groups = [];
      while (head.length > 2) { groups.unshift(head.slice(-2)); head = head.slice(0, -2); }
      if (head) groups.unshift(head);
      whole = groups.join(",") + "," + tail;
    }
    return (neg ? "-" : "") + whole + (parts[1] ? "." + parts[1] : "");
  };

  var toastEl = document.getElementById("toast");
  var toastTimer;
  IG.hideToast = function () { if (toastEl) toastEl.classList.remove("is-on"); };
  IG.toast = function (message) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.classList.add("is-on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove("is-on"); }, 2600);
  };

  // ── Screens ──────────────────────────────────────────────────────────
  IG.markOpen = function () { try { sessionStorage.setItem("ig_open", "1"); } catch (e) {} };

  IG.goLock = function () {
    try { sessionStorage.removeItem("ig_open"); } catch (e) {}
    location.replace(body.dataset.lock + "?next=" + encodeURIComponent(location.pathname + location.search));
  };
  IG.goLogin = function () { location.replace(body.dataset.login); };

  // ── Talking to the server ────────────────────────────────────────────
  IG.csrf = function () {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : "";
  };

  function safeJson(res) {
    return res.json().catch(function () { return null; });
  }

  // Returns the parsed JSON, or throws {message}. Handles lock / sign-out / expired token.
  IG.api = function (url, options) {
    options = options || {};
    var hasBody = options.body !== undefined;

    function send() {
      return fetch(url, {
        method: options.method || (hasBody ? "POST" : "GET"),
        credentials: "same-origin",
        headers: Object.assign(
          { Accept: "application/json", "X-CSRFToken": IG.csrf() },
          hasBody ? { "Content-Type": "application/json" } : {}
        ),
        body: hasBody ? JSON.stringify(options.body) : undefined,
      });
    }

    function run(retried) {
      return send().then(function (res) {
        var isJson = (res.headers.get("content-type") || "").indexOf("json") !== -1;
        // The page was open for over an hour, so its security token expired: get a new one once.
        if (res.status === 400 && !isJson && !retried) {
          return fetch(body.dataset.home + "csrf", { credentials: "same-origin" })
            .then(safeJson)
            .then(function (j) {
              if (j && j.token) document.querySelector('meta[name="csrf-token"]').content = j.token;
              return run(true);
            });
        }
        return safeJson(res).then(function (data) {
          if (res.status === 401) {
            if (data && data.code === "locked") IG.goLock(); else IG.goLogin();
            throw { message: (data && data.error) || "Please sign in again.", handled: true };
          }
          if (!res.ok) {
            throw { message: (data && data.error) || "Something went wrong. Please try again.", status: res.status, data: data };
          }
          return data;
        });
      }, function () {
        throw { message: "No internet connection. Check your signal and try again." };
      });
    }
    return run(false);
  };

  // ── Show / hide password ─────────────────────────────────────────────
  document.querySelectorAll("[data-toggle-password]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.getAttribute("data-toggle-password"));
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.classList.toggle("is-on", show);
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
  });

  // ── Lock again after a minute away (like a banking app) ──────────────
  if (body.classList.contains("app")) {
    var hiddenAt = 0;
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { hiddenAt = Date.now(); return; }
      if (hiddenAt && Date.now() - hiddenAt > 60 * 1000) IG.goLock();
      hiddenAt = 0;
    });
    // A page restored from the back/forward cache must not skip the lock.
    window.addEventListener("pageshow", function (e) {
      var open = false;
      try { open = !!sessionStorage.getItem("ig_open"); } catch (err) { open = true; }
      if (e.persisted && !open) IG.goLock();
    });
  }

  // ── Install as an app ────────────────────────────────────────────────
  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    IG.installPrompt = e;
    document.dispatchEvent(new CustomEvent("ig:installable"));
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/b/sw.js", { scope: "/b/" }).catch(function () {});
    });
  }
})();
