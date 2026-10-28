/* Officer app — new order screen.
   Prices shown here are only a preview; the server always uses the company price list. */
(function () {
  "use strict";

  var raw = document.getElementById("order-data");
  if (!raw) return;
  var data = JSON.parse(raw.textContent);
  var BAG = 30;

  var state = {
    mode: data.shops.length ? "mine" : "new",
    shopId: null,
    pay: "cash",
    lines: {} // product id -> { n: number, mode: "bag" | "kg" }
  };
  if (data.selected && data.shops.some(function (s) { return s.id === data.selected; })) {
    state.shopId = data.selected;
  }

  function $(id) { return document.getElementById(id); }
  function inr(n) {
    var s = Math.round(n).toString(), neg = "";
    if (s[0] === "-") { neg = "-"; s = s.slice(1); }
    if (s.length > 3) {
      var tail = s.slice(-3), head = s.slice(0, -3), parts = [];
      while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
      if (head) parts.unshift(head);
      s = parts.join(",") + "," + tail;
    }
    return neg + s;
  }
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }
  function esc(t) {
    return String(t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ── Shops ────────────────────────────────────────────────────────────
  function renderShops(filter) {
    var list = $("shop-list");
    if (!list) return;
    list.innerHTML = "";
    var q = (filter || "").toLowerCase();
    data.shops.filter(function (s) {
      return !q || s.name.toLowerCase().indexOf(q) > -1 || (s.phone || "").indexOf(q) > -1;
    }).forEach(function (s) {
      var li = el("li", state.shopId === s.id ? "is-picked" : "");
      li.innerHTML = "<button type=\"button\"><span><strong>" + esc(s.name) + "</strong><small>" + esc(s.phone) + "</small></span><i></i></button>";
      li.firstChild.addEventListener("click", function () { state.shopId = s.id; renderShops($("shop-search").value); update(); });
      list.appendChild(li);
    });
    if (!list.children.length) list.appendChild(el("li", "pad-note muted", "No shop matches that search."));
  }

  function setMode(mode) {
    state.mode = mode;
    document.querySelectorAll("[data-shop-mode]").forEach(function (b) {
      b.classList.toggle("is-active", b.getAttribute("data-shop-mode") === mode);
    });
    $("shop-mine").hidden = mode !== "mine";
    $("shop-new").hidden = mode !== "new";
    update();
  }

  // ── Products ─────────────────────────────────────────────────────────
  function qtyKg(p, line) {
    if (!line || !line.n) return 0;
    return p.unit === "kg" && line.mode === "bag" ? line.n * BAG : line.n;
  }

  function renderProducts() {
    var list = $("product-list");
    list.innerHTML = "";
    data.products.forEach(function (p) {
      var isKg = p.unit === "kg";
      var li = el("li", "product-row");
      li.setAttribute("data-id", p.id);
      var img = p.image ? data.static + p.image : data.logo;
      var priceInfo = "₹" + inr(p.price) + "/" + p.unit + (isKg ? " &middot; ₹" + inr(p.price * BAG) + " per bag" : "");
      li.innerHTML =
        "<div class=\"prow-top\">" +
          "<img class=\"prow-img" + (p.image ? "" : " is-fallback") + "\" src=\"" + img + "\" alt=\"\">" +
          "<div class=\"prow-info\"><strong>" + esc(p.name) + "</strong><small>" + priceInfo + "</small></div>" +
        "</div>" +
        "<div class=\"prow-ctl\">" +
          (isKg ? "<div class=\"unit-chips\"><button type=\"button\" data-unit=\"bag\" class=\"is-active\">Bags</button><button type=\"button\" data-unit=\"kg\">Kg</button></div>" : "<span class=\"unit-label\">" + esc(p.unit) + "</span>") +
          "<div class=\"stepper\"><button type=\"button\" data-step=\"-1\" aria-label=\"Less\">&minus;</button><input type=\"number\" inputmode=\"decimal\" min=\"0\" step=\"any\" value=\"0\" aria-label=\"Quantity\"><button type=\"button\" data-step=\"1\" aria-label=\"More\">+</button></div>" +
        "</div>" +
        "<div class=\"prow-sub\" hidden></div>";
      list.appendChild(li);

      var input = li.querySelector("input");
      function setN(n) {
        n = Math.max(0, isFinite(n) ? n : 0);
        var line = state.lines[p.id] || (state.lines[p.id] = { n: 0, mode: isKg ? "bag" : "unit" });
        line.n = n;
        input.value = n ? String(n) : "0";
        li.classList.toggle("has-qty", n > 0);
        var sub = li.querySelector(".prow-sub");
        var kg = qtyKg(p, line);
        sub.hidden = !n;
        if (n) {
          sub.innerHTML = (isKg ? (line.mode === "bag" ? n + " bag" + (n === 1 ? "" : "s") + " = " + kg + " kg" : kg + " kg") : n + " " + esc(p.unit)) +
            " &middot; <strong>₹" + inr(kg * p.price) + "</strong>";
        }
        update();
      }
      li.querySelectorAll("[data-step]").forEach(function (b) {
        b.addEventListener("click", function () {
          var cur = parseFloat(input.value) || 0;
          setN(cur + parseInt(b.getAttribute("data-step"), 10));
        });
      });
      input.addEventListener("input", function () { setN(parseFloat(input.value)); });
      input.addEventListener("focus", function () { if (input.value === "0") input.select(); });
      li.querySelectorAll("[data-unit]").forEach(function (b) {
        b.addEventListener("click", function () {
          var line = state.lines[p.id] || (state.lines[p.id] = { n: 0, mode: "bag" });
          line.mode = b.getAttribute("data-unit");
          li.querySelectorAll("[data-unit]").forEach(function (x) { x.classList.toggle("is-active", x === b); });
          setN(line.n);
        });
      });
    });
  }

  // ── Totals & validation ──────────────────────────────────────────────
  function summary() {
    var items = [], total = 0;
    data.products.forEach(function (p) {
      var kg = qtyKg(p, state.lines[p.id]);
      if (kg > 0) { items.push({ p: p, qty: kg, amount: kg * p.price, line: state.lines[p.id] }); total += kg * p.price; }
    });
    return { items: items, total: total };
  }

  function shopPayload() {
    if (state.mode === "mine") {
      return state.shopId ? { customer_id: state.shopId } : null;
    }
    var name = $("ns-name").value.trim(), phone = $("ns-phone").value.replace(/\D/g, "");
    if (name.length < 2 || phone.length < 10) return null;
    return { new_customer: { name: name, phone: phone, address: $("ns-address").value.trim(), gstin: $("ns-gstin").value.trim() } };
  }

  function update() {
    var s = summary();
    $("bar-items").textContent = s.items.length ? s.items.length + " item" + (s.items.length === 1 ? "" : "s") : "No items";
    $("bar-total").textContent = "₹" + inr(s.total);
    $("review-btn").disabled = !(s.items.length && shopPayload());
  }

  // ── Confirm & send ───────────────────────────────────────────────────
  function openSheet() {
    var s = summary(), shop = shopPayload();
    var shopName = shop.customer_id ? data.shops.filter(function (x) { return x.id === shop.customer_id; })[0].name : shop.new_customer.name + " (new shop)";
    var rows = s.items.map(function (i) {
      var q = i.p.unit === "kg" && i.line.mode === "bag" ? i.line.n + " bag" + (i.line.n === 1 ? "" : "s") : i.qty + " " + i.p.unit;
      return "<li><span>" + esc(i.p.name) + "<small>" + q + "</small></span><strong>₹" + inr(i.amount) + "</strong></li>";
    }).join("");
    $("sheet-body").innerHTML =
      "<p class=\"m-label\">Shop</p><p class=\"sheet-shop\">" + esc(shopName) + "</p>" +
      "<ul class=\"line-list\">" + rows + "</ul>" +
      "<div class=\"total-row\"><span>Estimated total (before GST)</span><strong>₹" + inr(s.total) + "</strong></div>" +
      "<p class=\"muted\">Payment: " + state.pay.toUpperCase() + ". The admin reviews this before any bill is made.</p>";
    $("sheet-error").hidden = true;
    $("confirm-sheet").hidden = false;
  }

  function send() {
    var s = summary(), shop = shopPayload();
    var btn = $("sheet-send");
    var payload = {
      items: s.items.map(function (i) { return { product_id: i.p.id, qty: i.qty }; }),
      payment_mode: state.pay,
      notes: $("order-notes").value.trim()
    };
    Object.keys(shop).forEach(function (k) { payload[k] = shop[k]; });

    btn.disabled = true;
    btn.textContent = "Sending…";
    var token = document.querySelector("meta[name='csrf-token']").content;
    fetch(data.post, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token },
      body: JSON.stringify(payload)
    }).then(function (res) {
      return res.json().then(function (body) { return { ok: res.ok, status: res.status, body: body }; });
    }).then(function (r) {
      if (r.status === 401) { window.location.reload(); return; }
      if (!r.ok) throw new Error(r.body.error || "Could not send the order.");
      window.location.href = r.body.url;
    }).catch(function (err) {
      var e = $("sheet-error");
      e.textContent = err.message === "Failed to fetch" ? "No internet connection. Please try again." : err.message;
      e.hidden = false;
      btn.disabled = false;
      btn.textContent = "Send order";
    });
  }

  // ── Wire up ──────────────────────────────────────────────────────────
  document.querySelectorAll("[data-shop-mode]").forEach(function (b) {
    b.addEventListener("click", function () { setMode(b.getAttribute("data-shop-mode")); });
  });
  var search = $("shop-search");
  if (search) search.addEventListener("input", function () { renderShops(search.value); });
  ["ns-name", "ns-phone"].forEach(function (id) { $(id).addEventListener("input", update); });
  document.querySelectorAll("#pay-chips button").forEach(function (b) {
    b.addEventListener("click", function () {
      state.pay = b.getAttribute("data-pay");
      document.querySelectorAll("#pay-chips button").forEach(function (x) { x.classList.toggle("is-active", x === b); });
    });
  });
  $("review-btn").addEventListener("click", openSheet);
  $("sheet-back").addEventListener("click", function () { $("confirm-sheet").hidden = true; });
  $("sheet-send").addEventListener("click", send);

  renderShops("");
  renderProducts();
  setMode(state.mode);
})();
