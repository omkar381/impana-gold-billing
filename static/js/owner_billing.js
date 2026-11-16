/* owner_billing.js — the phone billing screen: pick products, review, save. */
(function () {
  "use strict";

  var IG = window.IG;
  var root = document.getElementById("billing");
  if (!root) return;

  var GST_ENABLED = root.dataset.gst === "1";
  var STORE_KEY = "ig_owner_bill_v1";
  var $ = function (id) { return document.getElementById(id); };
  var esc = IG.esc;

  var state = {
    products: [], categories: [], byId: {},
    cat: 0, q: "",
    cart: {},                       // product id -> {id, qty, price, loose}
    buyer: { id: null, name: "", phone: "", pickedPhone: "" },
    pay: "cash", discType: "flat", discAmt: "", officer: "", notes: "",
  };

  var el = {
    plist: $("plist"), chips: $("chips"), q: $("q"), search: $("search"),
    cartbar: $("cartbar"), cartCount: $("cart-count"), cartTotal: $("cart-total"),
    sheet: $("sheet"), lines: $("lines"), totals: $("totals"),
    phone: $("buyer-phone"), phoneWrap: $("phone-wrap"), name: $("buyer-name"), suggest: $("suggest"),
    saveBtn: $("save-btn"), saveError: $("save-error"),
    discAmt: $("disc-amt"), officer: $("officer"), notes: $("notes"),
  };

  // ── Numbers (same rules as the server: bills.py save_bill) ───────────
  function round2(x) { return Math.round((x + Number.EPSILON) * 100) / 100; }
  function fmtQty(n) { return String(parseFloat(Number(n).toFixed(3))); }
  function money(n) { return "₹" + IG.inr(n, 2); }
  function moneyShort(n) { return "₹" + IG.inr(n, Number.isInteger(round2(n)) ? 0 : 2); }

  function isBag(p, line) {
    return !line.loose && p.unit === "kg" && line.qty >= 30 && line.qty % 30 === 0;
  }

  function calc() {
    var subtotal = 0, gst = 0, count = 0;
    Object.keys(state.cart).forEach(function (id) {
      var line = state.cart[id], p = state.byId[id];
      if (!p) return;
      var total = round2(line.qty * line.price);
      var rate = isBag(p, line) ? 0 : p.gst;
      subtotal += total;
      gst += round2(total * rate / 100);
      count++;
    });
    subtotal = round2(subtotal);
    var typed = parseFloat(state.discAmt) || 0;
    var discount = state.discType === "percent" ? round2(subtotal * typed / 100) : round2(typed);
    discount = Math.min(Math.max(discount, 0), subtotal);
    if (!GST_ENABLED) gst = 0;
    gst = round2(gst);
    var taxable = round2(subtotal - discount);
    return { subtotal: subtotal, discount: discount, taxable: taxable, gst: gst, grand: round2(taxable + gst), count: count };
  }

  // ── Saving the work in progress (survives a lock or a refresh) ───────
  function persist() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({
        cart: state.cart, buyer: state.buyer, pay: state.pay, discType: state.discType,
        discAmt: state.discAmt, officer: state.officer, notes: state.notes,
      }));
    } catch (e) {}
  }
  function restore() {
    try {
      var saved = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
      if (!saved) return;
      Object.keys(saved.cart || {}).forEach(function (id) {
        if (state.byId[id]) state.cart[id] = saved.cart[id];
      });
      state.buyer = Object.assign(state.buyer, saved.buyer || {});
      state.pay = saved.pay || "cash";
      state.discType = saved.discType || "flat";
      state.discAmt = saved.discAmt || "";
      state.officer = saved.officer || "";
      state.notes = saved.notes || "";
    } catch (e) {}
  }
  function clearSaved() { try { localStorage.removeItem(STORE_KEY); } catch (e) {} }

  // ── Product list ─────────────────────────────────────────────────────
  function visibleProducts() {
    var q = state.q.trim().toLowerCase();
    return state.products.filter(function (p) {
      if (state.cat && p.category_id !== state.cat) return false;
      return !q || p.name.toLowerCase().indexOf(q) !== -1 || (p.sku || "").toLowerCase().indexOf(q) !== -1;
    });
  }

  // Photos are shown only if the shop has uploaded some; a column of identical letters adds nothing.
  var hasPhotos = false;

  function thumb(p) {
    if (!hasPhotos) return "";
    if (p.image) return '<span class="thumb"><img src="' + esc(p.image) + '" alt="" loading="lazy"></span>';
    return '<span class="thumb" aria-hidden="true">' + esc((p.name || "?").charAt(0).toUpperCase()) + "</span>";
  }

  function control(p) {
    var line = state.cart[p.id];
    if (p.stock <= 0) return '<button type="button" class="add-btn" disabled>Out</button>';
    if (!line) return '<button type="button" class="add-btn" data-act="add" data-id="' + p.id + '">Add</button>';
    return '<div class="stepper">' +
      '<button type="button" data-act="dec" data-id="' + p.id + '" aria-label="Less">' + minusSvg + "</button>" +
      '<input type="text" inputmode="decimal" data-act="qty" data-id="' + p.id + '" value="' + fmtQty(line.qty) + '" aria-label="Quantity">' +
      '<button type="button" data-act="inc" data-id="' + p.id + '" aria-label="More">' + plusSvg + "</button></div>";
  }

  function row(p) {
    var gstTxt = GST_ENABLED && p.gst > 0 ? " · GST " + fmtQty(p.gst) + "%" : "";
    var stock = p.stock <= 0
      ? '<div class="pstock is-out">Out of stock</div>'
      : '<div class="pstock">' + fmtQty(p.stock) + " " + esc(p.unit) + " in stock</div>";
    return '<div class="prow' + (p.stock <= 0 ? " is-out" : "") + '" data-row="' + p.id + '">' + thumb(p) +
      '<div class="pinfo"><div class="pname">' + esc(p.name) + "</div>" +
      '<div class="pmeta"><strong class="num">' + moneyShort(p.price) + "</strong> / " + esc(p.unit) + gstTxt + "</div>" +
      stock + "</div>" + control(p) + "</div>";
  }

  function renderList() {
    var list = visibleProducts();
    if (!list.length) {
      el.plist.innerHTML = '<div class="empty"><strong>No products found</strong>' +
        (state.q ? "Nothing matches “" + esc(state.q) + "”." : "There are no products here yet.") + "</div>";
      return;
    }
    el.plist.innerHTML = list.map(row).join("");
  }

  function renderRow(id) {
    var node = el.plist.querySelector('[data-row="' + id + '"]');
    if (!node) return;
    blurInside(node);
    node.outerHTML = row(state.byId[id]);
  }

  function renderChips() {
    var used = {};
    state.products.forEach(function (p) { used[p.category_id] = true; });
    var cats = state.categories.filter(function (c) { return used[c.id]; });
    if (cats.length < 2) { el.chips.hidden = true; return; }
    el.chips.hidden = false;
    el.chips.innerHTML = '<button type="button" class="chip' + (state.cat ? "" : " is-on") + '" data-cat="0">All</button>' +
      cats.map(function (c) {
        return '<button type="button" class="chip' + (state.cat === c.id ? " is-on" : "") + '" data-cat="' + c.id + '">' + esc(c.name) + "</button>";
      }).join("");
  }

  var plusSvg = '<svg class="ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M12 5v14"/></svg>';
  var minusSvg = '<svg class="ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14"/></svg>';
  var trashSvg = '<svg class="ico" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>';

  // ── Cart changes ─────────────────────────────────────────────────────
  // `soft` = the change came from typing in a box that is still focused: update numbers in
  // place instead of redrawing, so the keyboard and cursor are never disturbed.
  function setQty(id, qty, fromReview, soft) {
    var p = state.byId[id];
    if (!p) return;
    qty = Math.round(qty * 1000) / 1000;
    if (!(qty > 0)) {
      if (fromReview) { IG.toast("Use the bin to remove an item"); renderLines(); return; }
      delete state.cart[id];
    } else if (state.cart[id]) {
      state.cart[id].qty = qty;
    } else {
      state.cart[id] = { id: id, qty: qty, price: p.price, loose: false };
    }
    afterCartChange(id, soft);
  }

  function blurInside(node) {
    if (node && document.activeElement && node.contains(document.activeElement)) document.activeElement.blur();
  }

  function afterCartChange(id, soft) {
    persist();
    if (id != null && !(soft && state.cart[id] && !el.sheet.classList.contains("is-open"))) renderRow(id);
    updateCartBar();
    if (el.sheet.classList.contains("is-open")) {
      if (!Object.keys(state.cart).length) { closeSheet(); return; }
      if (soft) refreshLine(id); else { blurInside(el.lines); renderLines(); }
      renderTotals();
    }
  }

  // Update one line's total and notes without touching its inputs.
  function refreshLine(id) {
    var line = state.cart[id];
    if (!line) { renderLines(); return; }
    var totalEl = el.lines.querySelector('[data-total="' + id + '"]');
    if (totalEl) totalEl.textContent = money(round2(line.qty * line.price));
    var extra = el.lines.querySelector('[data-extra="' + id + '"]');
    if (!extra) return;
    // Rewriting identical notes would replace a button the finger is already pressing (the tap would be lost).
    var html = noteHtml(id);
    if (extra._last !== html) { extra.innerHTML = html; extra._last = html; }
  }

  function updateCartBar() {
    var c = calc();
    document.body.classList.toggle("has-cart", c.count > 0);
    el.cartbar.hidden = c.count === 0;
    el.cartCount.textContent = c.count + (c.count === 1 ? " item" : " items");
    el.cartTotal.textContent = money(c.grand);
  }

  // Product list events (one handler for every row)
  el.plist.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-act]");
    if (!btn || btn.tagName === "INPUT") return;
    var id = Number(btn.dataset.id), act = btn.dataset.act, line = state.cart[id];
    if (act === "add") setQty(id, 1);
    else if (act === "inc") setQty(id, (line ? line.qty : 0) + 1);
    else if (act === "dec") setQty(id, (line ? line.qty : 1) - 1);
  });
  el.plist.addEventListener("change", function (e) {
    var input = e.target.closest('input[data-act="qty"]');
    if (!input) return;
    var qty = parseFloat(input.value.replace(",", "."));
    if (qty > 0) input.value = fmtQty(Math.round(qty * 1000) / 1000);   // tidy in place; buttons stay put
    setQty(Number(input.dataset.id), qty, false, qty > 0);
  });
  el.plist.addEventListener("focusin", function (e) {
    if (e.target.matches('input[data-act="qty"]')) e.target.select();
  });

  // Search and categories
  el.q.addEventListener("input", function () {
    state.q = el.q.value;
    el.search.classList.toggle("has-text", !!state.q);
    renderList();
  });
  $("q-clear").addEventListener("click", function () {
    el.q.value = ""; state.q = ""; el.search.classList.remove("has-text"); renderList(); el.q.focus();
  });
  el.chips.addEventListener("click", function (e) {
    var chip = e.target.closest("[data-cat]");
    if (!chip) return;
    state.cat = Number(chip.dataset.cat);
    renderChips(); renderList();
  });

  // ── Review sheet ─────────────────────────────────────────────────────
  function openSheet() {
    el.sheet.classList.add("is-open");
    document.body.style.overflow = "hidden";
    if (!(history.state && history.state.sheet)) history.pushState({ sheet: 1 }, "", "#review");
    renderLines();
    renderTotals();
  }
  function closeSheet(fromPop) {
    el.sheet.classList.remove("is-open");
    document.body.style.overflow = "";
    if (!fromPop && history.state && history.state.sheet) history.back();
  }
  window.addEventListener("popstate", function () {
    if (el.sheet.classList.contains("is-open")) closeSheet(true);
  });
  $("review-btn").addEventListener("click", openSheet);
  $("sheet-back").addEventListener("click", function () { closeSheet(); });

  $("clear-bill").addEventListener("click", function () {
    if (!confirm("Clear this bill? All items and buyer details will be removed.")) return;
    state.cart = {};
    state.buyer = { id: null, name: "", phone: "", pickedPhone: "" };
    state.discAmt = ""; state.notes = ""; state.officer = ""; state.pay = "cash"; state.discType = "flat";
    clearSaved();
    syncForm();
    renderList(); updateCartBar(); closeSheet();
  });

  function noteHtml(id) {
    var line = state.cart[id], p = state.byId[id];
    if (!line || !p) return "";
    if (line.qty > p.stock) {
      return '<div class="line-note is-warn"><span>Only ' + fmtQty(p.stock) + " " + esc(p.unit) + " in stock</span></div>";
    }
    if (GST_ENABLED && p.gst > 0 && p.unit === "kg" && line.qty >= 30 && line.qty % 30 === 0) {
      return '<div class="line-note"><span>' + (line.loose ? "Loose — GST charged" : "30 kg bag — no GST") + "</span>" +
        '<button type="button" class="mini-toggle" data-act="loose" data-id="' + id + '">' + (line.loose ? "Treat as bag" : "Charge GST (loose)") + "</button></div>";
    }
    return "";
  }

  function lineHtml(id) {
    var line = state.cart[id], p = state.byId[id];
    var bag = isBag(p, line);
    var sub = "Sold per " + esc(p.unit) + (GST_ENABLED && p.gst > 0 ? " · GST " + (bag ? "0" : fmtQty(p.gst)) + "%" : "");
    return '<div class="line" data-line="' + id + '">' +
      '<div class="line-top"><div><div class="line-name">' + esc(p.name) + '</div><div class="line-sub">' + sub + "</div></div>" +
      '<div class="line-total num" data-total="' + id + '">' + money(round2(line.qty * line.price)) + "</div></div>" +
      '<div class="line-controls">' +
        '<div><span class="rate-label">Quantity</span><div class="stepper">' +
          '<button type="button" data-act="dec" data-id="' + id + '" aria-label="Less">' + minusSvg + "</button>" +
          '<input type="text" inputmode="decimal" data-act="qty" data-id="' + id + '" value="' + fmtQty(line.qty) + '" aria-label="Quantity">' +
          '<button type="button" data-act="inc" data-id="' + id + '" aria-label="More">' + plusSvg + "</button></div></div>" +
        '<div><span class="rate-label">Rate per ' + esc(p.unit) + '</span><div class="rate-field"><span>₹</span>' +
          '<input type="text" inputmode="decimal" data-act="rate" data-id="' + id + '" value="' + fmtQty(line.price) + '" aria-label="Rate"></div></div>' +
        '<button type="button" class="icon-btn line-remove" data-act="remove" data-id="' + id + '" aria-label="Remove ' + esc(p.name) + '">' + trashSvg + "</button>" +
      '</div><div class="line-extra" data-extra="' + id + '">' + noteHtml(id) + "</div></div>";
  }

  function renderLines() {
    var ids = Object.keys(state.cart);
    el.lines.innerHTML = ids.length ? ids.map(lineHtml).join("") : '<div class="empty">No items yet.</div>';
    Array.prototype.forEach.call(el.lines.querySelectorAll("[data-extra]"), function (node) {
      node._last = noteHtml(Number(node.dataset.extra));
    });
  }

  el.lines.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-act]");
    if (!btn || btn.tagName === "INPUT") return;
    var id = Number(btn.dataset.id), line = state.cart[id], act = btn.dataset.act;
    if (!line) return;
    if (act === "inc") setQty(id, line.qty + 1, true);
    else if (act === "dec") setQty(id, line.qty - 1, true);
    else if (act === "remove") { delete state.cart[id]; afterCartChange(id); }
    else if (act === "loose") { line.loose = !line.loose; afterCartChange(id); }
  });
  el.lines.addEventListener("change", function (e) {
    var input = e.target.closest("input[data-act]");
    if (!input) return;
    var id = Number(input.dataset.id), line = state.cart[id];
    if (!line) return;
    var value = parseFloat(String(input.value).replace(",", "."));
    if (input.dataset.act === "qty") {
      if (value > 0) { input.value = fmtQty(Math.round(value * 1000) / 1000); setQty(id, value, true, true); }
      else { input.value = fmtQty(line.qty); IG.toast("Use the bin to remove an item"); }
    } else if (input.dataset.act === "rate") {
      if (value > 0) { line.price = Math.round(value * 100) / 100; afterCartChange(id, true); }
      else { input.value = fmtQty(line.price); }
    }
  });
  el.lines.addEventListener("focusin", function (e) {
    if (e.target.matches("input[data-act]")) e.target.select();
  });
  // Update the line total and summary while typing, without redrawing (keeps the keyboard open).
  el.lines.addEventListener("input", function (e) {
    var input = e.target.closest("input[data-act]");
    if (!input) return;
    var id = Number(input.dataset.id), line = state.cart[id];
    var value = parseFloat(String(input.value).replace(",", "."));
    if (!line || !(value > 0)) return;
    if (input.dataset.act === "qty") line.qty = value; else line.price = value;
    refreshLine(id);
    persist(); updateCartBar(); renderTotals();
  });

  function renderTotals() {
    var c = calc();
    var html = '<dl class="kvs">' +
      '<div class="kv"><span class="k">Subtotal</span><span class="v num">' + money(c.subtotal) + "</span></div>";
    if (c.discount > 0) html += '<div class="kv neg"><span class="k">Discount</span><span class="v num">− ' + money(c.discount) + "</span></div>";
    if (GST_ENABLED) html += '<div class="kv"><span class="k">GST</span><span class="v num">' + money(c.gst) + "</span></div>";
    html += '<div class="kv grand"><span class="k">Total</span><span class="v num">' + money(c.grand) + "</span></div></dl>";
    el.totals.innerHTML = html;
    el.saveBtn.textContent = "Save bill · " + money(c.grand);
  }

  // ── Payment, discount, notes ─────────────────────────────────────────
  function bindSeg(id, key, after) {
    $(id).addEventListener("click", function (e) {
      var b = e.target.closest("button[data-v]");
      if (!b) return;
      state[key] = b.dataset.v;
      $(id).querySelectorAll("button").forEach(function (x) { x.classList.toggle("is-on", x === b); });
      persist();
      if (after) after();
    });
  }
  bindSeg("pay", "pay");
  bindSeg("disc-type", "discType", function () { updateCartBar(); renderTotals(); });

  el.discAmt.addEventListener("input", function () {
    el.discAmt.value = el.discAmt.value.replace(/[^0-9.]/g, "");
    state.discAmt = el.discAmt.value;
    persist(); updateCartBar(); renderTotals();
  });
  if (el.officer) el.officer.addEventListener("change", function () { state.officer = el.officer.value; persist(); });
  el.notes.addEventListener("input", function () { state.notes = el.notes.value; persist(); });

  $("more-toggle").addEventListener("click", function () {
    var open = this.getAttribute("aria-expanded") === "true";
    this.setAttribute("aria-expanded", String(!open));
    $("more").hidden = open;
  });

  // ── Buyer: phone, name, and customers he has billed before ───────────
  var suggestTimer;
  function cleanPhone(v) {
    v = String(v || "").replace(/\D/g, "");
    if (v.length > 10 && v.slice(0, 2) === "91") v = v.slice(-10);
    return v.slice(0, 10);
  }
  function phoneOk(v) { return /^[6-9]\d{9}$/.test(v); }

  function updatePhoneTick() { el.phoneWrap.classList.toggle("is-valid", phoneOk(state.buyer.phone)); }

  function onBuyerType() {
    var picked = state.buyer.id;
    if (picked && state.buyer.phone !== state.buyer.pickedPhone) state.buyer.id = null;
    persist(); updatePhoneTick();
    clearTimeout(suggestTimer);
    suggestTimer = setTimeout(loadSuggestions, 220);
  }

  el.phone.addEventListener("input", function () {
    var v = cleanPhone(el.phone.value);
    if (el.phone.value !== v) el.phone.value = v;
    state.buyer.phone = v;
    onBuyerType();
  });
  el.name.addEventListener("input", function () {
    state.buyer.name = el.name.value;
    if (state.buyer.id && state.buyer.name.trim() === "") state.buyer.id = null;
    onBuyerType();
  });
  [el.phone, el.name].forEach(function (input) {
    input.addEventListener("focus", function () { clearTimeout(suggestTimer); suggestTimer = setTimeout(loadSuggestions, 80); });
    input.addEventListener("blur", function () {
      setTimeout(function () {
        if (document.activeElement !== el.phone && document.activeElement !== el.name) el.suggest.hidden = true;
      }, 160);
    });
  });

  function loadSuggestions() {
    var q = state.buyer.phone.length >= 3 ? state.buyer.phone : (state.buyer.name.trim().length >= 2 ? state.buyer.name.trim() : "");
    if (state.buyer.id && !q) { el.suggest.hidden = true; return; }
    IG.api(root.dataset.customers + "?q=" + encodeURIComponent(q)).then(function (rows) {
      if (!rows.length || phoneOk(state.buyer.phone) && state.buyer.id) { el.suggest.hidden = true; return; }
      el.suggest.innerHTML = '<div class="suggest-head">' + (q ? "Matching buyers" : "Recent buyers") + "</div>" +
        rows.map(function (c) {
          return '<button type="button" data-id="' + c.id + '" data-name="' + esc(c.name) + '" data-phone="' + esc(c.phone) + '">' +
            '<span class="s-name">' + esc(c.name) + '</span><span class="s-phone">' + esc(c.phone || "no number") + "</span></button>";
        }).join("");
      el.suggest.hidden = false;
    }).catch(function () { el.suggest.hidden = true; });
  }

  el.suggest.addEventListener("pointerdown", function (e) { e.preventDefault(); });  // keep keyboard/focus stable
  el.suggest.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-id]");
    if (!b) return;
    state.buyer = { id: Number(b.dataset.id), name: b.dataset.name, phone: b.dataset.phone, pickedPhone: b.dataset.phone };
    el.name.value = state.buyer.name;
    el.phone.value = state.buyer.phone;
    el.suggest.hidden = true;
    updatePhoneTick(); persist();
  });

  // ── Save ─────────────────────────────────────────────────────────────
  function showError(message) {
    el.saveError.querySelector("span").textContent = message;
    el.saveError.hidden = false;
    el.saveError.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  el.saveBtn.addEventListener("click", function () {
    el.saveError.hidden = true;
    var c = calc();
    if (!c.count) return showError("Add at least one item.");
    if (c.grand <= 0) return showError("The total must be more than zero.");
    var over = Object.keys(state.cart).filter(function (id) { return state.cart[id].qty > state.byId[id].stock; });
    if (over.length) return showError("Some items are more than the stock available. Reduce the quantity.");
    if (state.buyer.phone && !phoneOk(state.buyer.phone)) return showError("Enter the buyer's 10-digit mobile number, or leave it empty.");

    var original = el.saveBtn.textContent;
    el.saveBtn.disabled = true;
    el.saveBtn.textContent = "Saving…";

    IG.api(root.dataset.save, {
      method: "POST",
      body: {
        items: Object.keys(state.cart).map(function (id) {
          var l = state.cart[id];
          return { product_id: Number(id), qty: l.qty, unit_price: l.price, is_loose: !!l.loose };
        }),
        buyer: { id: state.buyer.id, name: state.buyer.name.trim(), phone: state.buyer.phone },
        payment_mode: state.pay,
        discount_type: state.discType,
        discount_amount: state.discAmt || 0,
        marketing_officer_id: state.officer || null,
        notes: state.notes,
      },
    }).then(function (res) {
      clearSaved();
      location.replace(res.url);
    }).catch(function (err) {
      if (err && err.handled) return;
      el.saveBtn.disabled = false;
      el.saveBtn.textContent = original;
      showError(err.message || "Could not save the bill. Please try again.");
    });
  });

  // ── Start ────────────────────────────────────────────────────────────
  function syncForm() {
    el.phone.value = state.buyer.phone || "";
    el.name.value = state.buyer.name || "";
    el.discAmt.value = state.discAmt || "";
    el.notes.value = state.notes || "";
    if (el.officer) el.officer.value = state.officer || "";
    $("pay").querySelectorAll("button").forEach(function (b) { b.classList.toggle("is-on", b.dataset.v === state.pay); });
    $("disc-type").querySelectorAll("button").forEach(function (b) { b.classList.toggle("is-on", b.dataset.v === state.discType); });
    updatePhoneTick();
  }

  IG.api(root.dataset.products).then(function (data) {
    state.products = data.products;
    state.categories = data.categories;
    hasPhotos = data.products.some(function (p) { return !!p.image; });
    data.products.forEach(function (p) { state.byId[p.id] = p; });
    restore();
    syncForm();
    renderChips();
    renderList();
    updateCartBar();
  }).catch(function (err) {
    if (err && err.handled) return;
    el.plist.innerHTML = '<div class="empty"><strong>Could not load products</strong>' + esc(err.message) +
      '<div style="margin-top:14px"><button type="button" class="btn btn-secondary btn-sm" onclick="location.reload()">Try again</button></div></div>';
  });
})();
