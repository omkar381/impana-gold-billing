/* owner_bills.js — Bills list (search, show more), one bill (WhatsApp, copy link) and Account. */
(function () {
  "use strict";
  var IG = window.IG;
  var $ = function (id) { return document.getElementById(id); };

  // ── Bills list ───────────────────────────────────────────────────────
  var list = $("bills");
  if (list) {
    var groups = $("bill-groups"), input = $("bq"), box = $("bsearch"), timer, seq = 0;
    box.classList.toggle("has-text", !!input.value);

    function fetchRows(page) {
      var url = list.dataset.url + "?partial=1&page=" + page + "&q=" + encodeURIComponent(input.value.trim());
      return fetch(url, { credentials: "same-origin", headers: { Accept: "text/html" } }).then(function (res) {
        if (res.status === 401 || res.redirected) { IG.goLock(); throw { handled: true }; }
        if (!res.ok) throw { message: "Could not load bills." };
        return res.text();
      });
    }

    input.addEventListener("input", function () {
      box.classList.toggle("has-text", !!input.value);
      clearTimeout(timer);
      var mine = ++seq;
      timer = setTimeout(function () {
        fetchRows(1).then(function (html) { if (mine === seq) groups.innerHTML = html; })
          .catch(function (e) { if (!e.handled) IG.toast(e.message || "No connection."); });
      }, 250);
    });
    $("bq-clear").addEventListener("click", function () {
      input.value = ""; input.dispatchEvent(new Event("input")); input.focus();
    });

    groups.addEventListener("click", function (e) {
      var btn = e.target.closest("#show-more");
      if (!btn) return;
      var wrap = btn.closest("[data-more]"), page = wrap.dataset.next;
      btn.disabled = true; btn.textContent = "Loading…";
      fetchRows(page).then(function (html) {
        var tmp = document.createElement("div");
        tmp.innerHTML = html;
        wrap.remove();
        Array.prototype.slice.call(tmp.children).forEach(function (node) {
          var last = groups.querySelector("section.group:last-of-type");
          // Same day continues: add the rows to the existing card instead of repeating the heading.
          if (node.matches("section.group") && last && last.dataset.label === node.dataset.label) {
            var target = last.querySelector(".blist");
            Array.prototype.slice.call(node.querySelectorAll(".brow")).forEach(function (r) { target.appendChild(r); });
          } else {
            groups.appendChild(node);
          }
        });
      }).catch(function (err) {
        if (err.handled) return;
        btn.disabled = false; btn.textContent = "Show more"; IG.toast(err.message || "No connection.");
      });
    });
  }

  // ── One bill ─────────────────────────────────────────────────────────
  var bill = $("bill");
  if (bill) {
    var copy = $("copy-link");
    if (copy) copy.addEventListener("click", function () {
      var link = bill.dataset.link;
      var done = function () { IG.toast("Link copied"); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(done, function () { window.prompt("Copy this link", link); });
      } else {
        window.prompt("Copy this link", link);
      }
    });

    var form = $("wa-form");
    if (form) {
      var phone = $("wa-phone"), err = $("wa-error");
      var clean = function (v) {
        v = String(v || "").replace(/\D/g, "");
        if (v.length > 10 && v.slice(0, 2) === "91") v = v.slice(-10);
        return v.slice(0, 10);
      };
      phone.addEventListener("input", function () { var v = clean(phone.value); if (phone.value !== v) phone.value = v; });
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        err.hidden = true;
        if (!/^[6-9]\d{9}$/.test(phone.value)) {
          err.querySelector("span").textContent = "Enter the buyer's 10-digit mobile number.";
          err.hidden = false;
          return;
        }
        var btn = form.querySelector("button[type=submit]");
        btn.disabled = true;
        IG.api(bill.dataset.phoneUrl, { method: "POST", body: { phone: phone.value } })
          .then(function (res) { location.href = res.wa_url; })
          .catch(function (e2) {
            btn.disabled = false;
            if (e2 && e2.handled) return;
            err.querySelector("span").textContent = e2.message;
            err.hidden = false;
          });
      });
    }
  }

  // ── Account ──────────────────────────────────────────────────────────
  var account = $("account");
  if (account) {
    var install = $("install-btn");
    var show = function () { if (IG.installPrompt) install.hidden = false; };
    show();
    document.addEventListener("ig:installable", show);
    install.addEventListener("click", function () {
      if (!IG.installPrompt) return;
      IG.installPrompt.prompt();
      IG.installPrompt.userChoice.then(function () { IG.installPrompt = null; install.hidden = true; });
    });
    $("logout-form").addEventListener("submit", function (e) {
      if (!confirm("Sign out of this phone? You will need your password to sign in again.")) e.preventDefault();
    });
  }
})();
