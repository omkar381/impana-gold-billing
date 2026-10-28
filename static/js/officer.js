/* Officer app — shared behaviour (animations, celebration, install, sign-in helpers). */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function csrf() {
    var m = document.querySelector("meta[name='csrf-token']");
    return m ? m.content : "";
  }
  function inr(n) {
    var s = Math.round(n).toString();
    if (s.length > 3) {
      var tail = s.slice(-3), head = s.slice(0, -3), parts = [];
      while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
      if (head) parts.unshift(head);
      s = parts.join(",") + "," + tail;
    }
    return s;
  }

  // Service worker (installable app + fast start)
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/m/sw.js", { scope: "/m/" }).catch(function () {});
    });
  }

  // Show / hide password
  document.querySelectorAll("[data-toggle-password]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.getAttribute("data-toggle-password"));
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.classList.toggle("is-on", show);
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
  });

  // Flash messages fade out
  var flash = document.querySelector("[data-flash]");
  if (flash) setTimeout(function () { flash.classList.add("is-hidden"); }, 4500);

  // Confirm before risky forms
  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      if (!window.confirm(f.getAttribute("data-confirm"))) e.preventDefault();
    });
  });

  // Target ring fills up, numbers count up
  document.querySelectorAll(".ring-bar[data-offset]").forEach(function (bar) {
    var target = bar.getAttribute("data-offset");
    if (reduceMotion) { bar.style.strokeDashoffset = target; return; }
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { bar.style.strokeDashoffset = target; });
    });
  });

  document.querySelectorAll("[data-count]").forEach(function (node) {
    var end = parseFloat(node.getAttribute("data-count")) || 0;
    var money = node.hasAttribute("data-inr");
    var render = function (v) { node.textContent = money ? inr(v) : Math.round(v); };
    if (reduceMotion || end === 0) { render(end); return; }
    var start = null, dur = 900;
    function tick(ts) {
      if (start === null) start = ts;
      var t = Math.min((ts - start) / dur, 1);
      render(end * (1 - Math.pow(1 - t, 3)));
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  });

  // Celebration when the admin has decided on orders
  var celebrate = document.getElementById("celebrate");
  if (celebrate) {
    celebrate.hidden = false;
    var confetti = document.getElementById("confetti");
    if (confetti && !reduceMotion) {
      var colors = ["#1d7a3c", "#c9962b", "#f2c94c", "#2e9d57", "#ffffff"];
      for (var i = 0; i < 70; i++) {
        var piece = document.createElement("i");
        piece.style.left = Math.random() * 100 + "%";
        piece.style.background = colors[i % colors.length];
        piece.style.animationDelay = Math.random() * 0.8 + "s";
        piece.style.animationDuration = 2.4 + Math.random() * 2 + "s";
        piece.style.transform = "rotate(" + Math.random() * 360 + "deg)";
        confetti.appendChild(piece);
      }
    }
    document.getElementById("celebrate-ok").addEventListener("click", function () {
      fetch("/m/updates/seen", { method: "POST", headers: { "X-CSRFToken": csrf() } }).catch(function () {});
      celebrate.hidden = true;
    });
  }

  // Install to home screen
  var standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
  var card = document.getElementById("install-card");
  if (card && !standalone) {
    var btn = document.getElementById("install-btn");
    var text = document.getElementById("install-text");
    var deferred = null;
    window.addEventListener("beforeinstallprompt", function (e) {
      e.preventDefault();
      deferred = e;
      card.hidden = false;
      btn.hidden = false;
    });
    btn.addEventListener("click", function () {
      if (!deferred) return;
      deferred.prompt();
      deferred.userChoice.finally(function () { deferred = null; card.hidden = true; });
    });
    if (/iphone|ipad|ipod/i.test(navigator.userAgent)) {
      card.hidden = false;
      text.textContent = "Tap the Share button, then “Add to Home Screen”.";
    }
  }
})();
