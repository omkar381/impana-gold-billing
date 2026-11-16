/* owner_billing.js — the phone billing screen: pick products, review, save.
 *
 * Adding products works exactly like the desktop screen:
 *   + 1 kg          adds 1 kg to the normal line
 *   x 30 kg Bag     adds 30 kg per bag (bag count next to it)
 *   Loose + Qty     adds the typed quantity as a separate LOOSE line (GST is charged)
 *   Qty + Add       adds the typed quantity to the normal line
 *   Rate            a typed rate replaces that line's rate
 * A normal line of 30, 60, 90... kg is a bag line: no GST (same rule as the server).
 */
(function () {
  "use strict";

  var IG = window.IG;
  var root = document.getElementById("billing");
  if (!root) return;

  var GST_ENABLED = root.dataset.gst === "1";
  var STORE_KEY = "ig_owner_bill_v2";
  var $ = function (id) { return document.getElementById(id); };
  var esc = IG.esc;

  var state = {
    products: [], categories: [], byId: {},
    cat: 0, q: "", open: null,     // open = product whose add-options are showing
    cart: {},                      // line key -> {key, id, qty, price, loose}
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

  // ── Numbers (same rules as the server: utils/billing_service.py) ─────
  function round2(x) { return Math.round((x + Number.EPSILON) * 100) / 100; }
  function round3(x) { return Math.round((x + Number.EPSILON) * 1000) / 1000; }
  function fmtQty(n) { return String(parseFloat(Number(n).toFixed(3))); }
  function money(n) { return "₹" + IG.inr(n, 2); }
  function moneyShort(n) { return "₹" + IG.inr(n, Number.isInteger(round2(n)) ? 0 : 2); }
  function num(v) { return parseFloat(String(v == null ? "" : v).replace(",", ".")); }

  // Never a plain number, so the lines keep the order they were added in.
  function keyOf(id, loose) { return "p" + id + (loose ? ":L" : ""); }
  function isBagLine(p, line) { return p.unit === "kg" && !line.loose && line.qty >= 30 && line.qty % 30 === 0; }
  function qtyInBill(id) {
    return [keyOf(id, false), keyOf(id, true)].reduce(function (sum, k) { return sum + (state.cart[k] ? state.cart[k].qty : 0); }, 0);
  }

  function calc() {
    var subtotal = 0, gst = 0, count = 0;
    Object.keys(state.cart).forEach(function (k) {
      var line = state.cart[k], p = state.byId[line.id];
      if (!p) return;
      var total = round2(line.qty * line.price);
      var rate = isBagLine(p, line) ? 0 : p.gst;
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
      Object.keys(saved.cart || {}).forEach(function (k) {
        var line = saved.cart[k];
        if (line && state.byId[line.id]) state.cart[k] = line;
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

  // The add options for one product (same buttons as the desktop product card)
  function panel(p) {
    var id = p.id;
    if (p.unit === "kg") {
      return '<div class="ppanel" hidden>' +
        '<label class="pp-rate"><span>Rate (₹/' + esc(p.unit) + ')</span>' +
          '<input type="text" inputmode="decimal" data-f="rate" placeholder="' + esc(fmtQty(p.price)) + '" aria-label="Rate for this bill"></label>' +
        '<div class="pp-row pp-bags">' +
          '<button type="button" class="pp-btn" data-add="one" data-id="' + id + '">+ 1 kg</button>' +
          '<div class="bagstep"><button type="button" data-bag="-1" aria-label="Fewer bags">−</button>' +
            '<input type="text" inputmode="numeric" data-f="bags" value="1" aria-label="Number of 30 kg bags">' +
            '<button type="button" data-bag="1" aria-label="More bags">+</button></div>' +
          '<button type="button" class="pp-btn pp-main" data-add="bag" data-id="' + id + '">× 30 kg Bag</button>' +
        "</div>" +
        '<div class="pp-row pp-custom">' +
          '<button type="button" class="pp-btn" data-add="loose" data-id="' + id + '">Loose</button>' +
          '<input type="text" inputmode="decimal" data-f="qty" placeholder="Qty" aria-label="Quantity">' +
          '<button type="button" class="pp-btn pp-main" data-add="qty" data-id="' + id + '">Add</button>' +
        "</div></div>";
    }
    return '<div class="ppanel" hidden>' +
      '<div class="pp-row pp-custom pp-plain">' +
        '<button type="button" class="pp-btn" data-add="one" data-id="' + id + '">+ 1</button>' +
        '<input type="text" inputmode="decimal" data-f="qty" placeholder="Qty" aria-label="Quantity">' +
        '<button type="button" class="pp-btn pp-main" data-add="qty" data-id="' + id + '">Add</button>' +
      "</div></div>";
  }

  function row(p) {
    var gstTxt = GST_ENABLED && p.gst > 0 ? " · GST " + fmtQty(p.gst) + "%" : "";
    var out = p.stock <= 0;
    var stock = out
      ? '<div class="pstock is-out">Out of stock</div>'
      : '<div class="pstock">' + fmtQty(p.stock) + " " + esc(p.unit) + " in stock</div>";
    return '<div class="prow-wrap' + (out ? " is-out" : "") + '" data-row="' + p.id + '">' +
      '<div class="prow">' + thumb(p) +
        '<div class="pinfo"' + (out ? "" : ' data-toggle="' + p.id + '"') + ">" +
          '<div class="pname">' + esc(p.name) + "</div>" +
          '<div class="pmeta"><strong class="num">' + moneyShort(p.price) + "</strong> / " + esc(p.unit) + gstTxt + "</div>" +
          stock + '<div class="inbill" data-chip="' + p.id + '" hidden></div></div>' +
        (out ? '<button type="button" class="add-btn" disabled>Out</button>'
             : '<button type="button" class="add-btn" data-toggle="' + p.id + '" aria-expanded="false">Add</button>') +
      "</div>" + (out ? "" : panel(p)) + "</div>";
  }

  function renderList() {
    var list = visibleProducts();
    state.open = null;
    if (!list.length) {
      el.plist.innerHTML = '<div class="empty"><strong>No products found</strong>' +
        (state.q ? "Nothing matches “" + esc(state.q) + "”." : "There are no products here yet.") + "</div>";
      return;
    }
    el.plist.innerHTML = list.map(row).join("");
    updateChips();
  }

  // "In bill: 60 kg (2 bags) · 5 kg loose" under each product
  function chipText(id) {
    var p = state.byId[id], pack = state.cart[keyOf(id, false)], loose = state.cart[keyOf(id, true)], parts = [];
    if (pack) {
      var bags = isBagLine(p, pack) ? " (" + fmtQty(pack.qty / 30) + (pack.qty === 30 ? " bag)" : " bags)") : "";
      parts.push(fmtQty(pack.qty) + " " + p.unit + bags);
    }
    if (loose) parts.push(fmtQty(loose.qty) + " " + p.unit + " loose");
    return parts.length ? "In bill: " + parts.join(" · ") : "";
  }
  function updateChip(id) {
    var node = el.plist.querySelector('[data-chip="' + id + '"]');
    if (!node) return;
    var text = chipText(id);
    node.textContent = text;
    node.hidden = !text;
  }
  function updateChips() {
    Array.prototype.forEach.call(el.plist.querySelectorAll("[data-chip]"), function (n) { updateChip(Number(n.dataset.chip)); });
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

  var minusSvg = '<svg class="ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14"/></svg>';
  var plusSvg = '<svg class="ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M12 5v14"/></svg>';
  var trashSvg = '<svg class="ico" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>';

  // ── Adding to the bill (same as the desktop screen) ──────────────────
  function addToBill(id, qty, opts) {
    var p = state.byId[id];
    if (!p || !(qty > 0)) return;
    opts = opts || {};
    var k = keyOf(id, !!opts.loose), line = state.cart[k];
    if (line) {
      line.qty = round3(line.qty + qty);
      if (opts.price > 0) line.price = opts.price;
    } else {
      state.cart[k] = { key: k, id: id, qty: round3(qty), price: opts.price > 0 ? opts.price : p.price, loose: !!opts.loose };
    }
    persist();
    updateChip(id);
    updateCartBar();
    IG.toast("+" + fmtQty(qty) + " " + p.unit + (opts.loose ? " loose" : "") + " · " + p.name);
  }

  function togglePanel(id) {
    var wrap = el.plist.querySelector('[data-row="' + id + '"]');
    if (!wrap) return;
    var opening = state.open !== id;
    if (state.open != null) closePanel(state.open);
    if (!opening) return;
    state.open = id;
    wrap.classList.add("is-open");
    wrap.querySelector(".ppanel").hidden = false;
    var btn = wrap.querySelector(".add-btn");
    btn.textContent = "Done"; btn.setAttribute("aria-expanded", "true");
    if (wrap.scrollIntoView) wrap.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  function closePanel(id) {
    var wrap = el.plist.querySelector('[data-row="' + id + '"]');
    if (wrap) {
      wrap.classList.remove("is-open");
      wrap.querySelector(".ppanel").hidden = true;
      var btn = wrap.querySelector(".add-btn");
      btn.textContent = "Add"; btn.setAttribute("aria-expanded", "false");
    }
    if (state.open === id) state.open = null;
  }

  function fromPanel(btn) {
    var wrap = btn.closest("[data-row]");
    var id = Number(btn.dataset.id), what = btn.dataset.add;
    var rateEl = wrap.querySelector('[data-f="rate"]'), qtyEl = wrap.querySelector('[data-f="qty"]'), bagsEl = wrap.querySelector('[data-f="bags"]');
    var rate = rateEl ? num(rateEl.value) : 0;
    var opts = rate > 0 ? { price: rate } : {};

    if (what === "one") { addToBill(id, 1, opts); return; }
    if (what === "bag") {
      var bags = parseInt(bagsEl.value, 10);
      if (!(bags >= 1)) { bags = 1; bagsEl.value = "1"; }
      addToBill(id, 30 * bags, opts);
      return;
    }
    var qty = num(qtyEl.value);
    if (!(qty > 0)) { IG.toast("Enter a valid quantity"); qtyEl.focus(); return; }
    opts.loose = what === "loose";
    addToBill(id, qty, opts);
    qtyEl.value = "";
  }

  el.plist.addEventListener("click", function (e) {
    var toggle = e.target.closest("[data-toggle]");
    if (toggle) { togglePanel(Number(toggle.dataset.toggle)); return; }
    var add = e.target.closest("[data-add]");
    if (add) { fromPanel(add); return; }
    var bag = e.target.closest("[data-bag]");
    if (bag) {
      var input = bag.parentNode.querySelector('[data-f="bags"]');
      input.value = String(Math.max(1, (parseInt(input.value, 10) || 1) + Number(bag.dataset.bag)));
    }
  });
  el.plist.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" || !e.target.matches('[data-f="qty"]')) return;
    e.preventDefault();
    var btn = e.target.closest(".ppanel").querySelector('[data-add="qty"]');
    if (btn) fromPanel(btn);
  });
  el.plist.addEventListener("focusin", function (e) {
    if (e.target.matches("[data-f]")) e.target.select();
  });
  el.plist.addEventListener("input", function (e) {
    if (e.target.matches('[data-f="bags"]')) {
      var v = e.target.value.replace(/\D/g, "");
      if (e.target.value !== v) e.target.value = v;
    }
  });

  function updateCartBar() {
    var c = calc();
    document.body.classList.toggle("has-cart", c.count > 0);
    el.cartbar.hidden = c.count === 0;
    el.cartCount.textContent = c.count + (c.count === 1 ? " item" : " items");
    el.cartTotal.textContent = money(c.grand);
  }

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
    IG.hideToast();
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
    updateChips(); updateCartBar(); closeSheet();
  });

  function blurInside(node) {
    if (node && document.activeElement && node.contains(document.activeElement)) document.activeElement.blur();
  }

  function noteHtml(key) {
    var line = state.cart[key], p = line && state.byId[line.id];
    if (!line || !p) return "";
    var inBill = qtyInBill(p.id);
    if (inBill > p.stock) {
      return '<div class="line-note is-warn"><span>Only ' + fmtQty(p.stock) + " " + esc(p.unit) + " in stock (" + fmtQty(inBill) + " on this bill)</span></div>";
    }
    if (GST_ENABLED && p.gst > 0 && p.unit === "kg") {
      if (line.loose) return '<div class="line-note"><span>Loose — GST charged</span></div>';
      if (isBagLine(p, line)) return '<div class="line-note"><span>30 kg bags — no GST</span></div>';
    }
    return "";
  }

  function lineHtml(key) {
    var line = state.cart[key], p = state.byId[line.id];
    var bag = isBagLine(p, line);
    var rateText = bag ? "0" : fmtQty(p.gst);
    var sub = "Sold per " + esc(p.unit) + (GST_ENABLED && p.gst > 0 ? " · GST " + rateText + "%" : "");
    var bagsText = bag ? " · " + fmtQty(line.qty / 30) + (line.qty === 30 ? " bag" : " bags") : "";
    var qtyLabel = "Quantity (" + esc(p.unit) + ")" + bagsText;
    var qtyValue = fmtQty(line.qty);
    return '<div class="line" data-line="' + key + '" data-bag="' + (bag ? "1" : "0") + '">' +
      '<div class="line-top"><div><div class="line-name">' + esc(p.name) + (line.loose ? ' <span class="loose-tag">Loose</span>' : "") +
        '</div><div class="line-sub">' + sub + "</div></div>" +
      '<div class="line-total num" data-total="' + key + '">' + money(round2(line.qty * line.price)) + "</div></div>" +
      '<div class="line-controls">' +
        '<div><span class="rate-label" data-qlabel="' + key + '">' + qtyLabel + '</span><div class="stepper">' +
          '<button type="button" data-act="dec" data-key="' + key + '" aria-label="Less">' + minusSvg + "</button>" +
          '<input type="text" inputmode="decimal" data-act="qty" data-key="' + key + '" value="' + qtyValue + '" aria-label="Quantity">' +
          '<button type="button" data-act="inc" data-key="' + key + '" aria-label="More">' + plusSvg + "</button></div></div>" +
        '<div><span class="rate-label">Rate per ' + esc(p.unit) + '</span><div class="rate-field"><span>₹</span>' +
          '<input type="text" inputmode="decimal" data-act="rate" data-key="' + key + '" value="' + fmtQty(line.price) + '" aria-label="Rate"></div></div>' +
        '<button type="button" class="icon-btn line-remove" data-act="remove" data-key="' + key + '" aria-label="Remove ' + esc(p.name) + '">' + trashSvg + "</button>" +
      '</div><div class="line-extra" data-extra="' + key + '">' + noteHtml(key) + "</div></div>";
  }

  function renderLines() {
    var keys = Object.keys(state.cart);
    el.lines.innerHTML = keys.length ? keys.map(lineHtml).join("") : '<div class="empty">No items yet.</div>';
    Array.prototype.forEach.call(el.lines.querySelectorAll("[data-extra]"), function (node) {
      node._last = noteHtml(node.dataset.extra);
    });
  }

  // Update one line's total and notes without touching its inputs (keeps the keyboard open).
  function refreshLine(key) {
    var line = state.cart[key];
    if (!line) { renderLines(); return; }
    var totalEl = el.lines.querySelector('[data-total="' + key + '"]');
    if (totalEl) totalEl.textContent = money(round2(line.qty * line.price));
    // A line's own stock note can change when its twin (normal/loose) changes, so refresh both.
    [keyOf(line.id, false), keyOf(line.id, true)].forEach(function (k) {
      var extra = el.lines.querySelector('[data-extra="' + k + '"]');
      if (!extra) return;
      // Rewriting identical notes would replace a button the finger is already pressing.
      var html = noteHtml(k);
      if (extra._last !== html) { extra.innerHTML = html; extra._last = html; }
    });
  }

  function afterLineChange(key, soft) {
    persist();
    var line = state.cart[key];
    if (line) updateChip(line.id);
    updateCartBar();
    if (!Object.keys(state.cart).length) { closeSheet(); return; }
    if (soft && line) refreshLine(key); else { blurInside(el.lines); renderLines(); }
    renderTotals();
  }

  // The box always means the product's unit (kg). The + and - buttons move a whole 30 kg bag on bag lines.
  function setLineQty(key, qty, soft) {
    var line = state.cart[key];
    if (!line) return;
    var p = state.byId[line.id];
    // What the line on screen currently says (typing may already have changed the quantity underneath it).
    var node = el.lines.querySelector('[data-line="' + key + '"]');
    var shownAsBag = node ? node.dataset.bag === "1" : null;
    qty = round3(qty);
    if (!(qty > 0)) { IG.toast("Use the bin to remove an item"); renderLines(); return; }
    line.qty = qty;
    // Crossing into or out of a 30 kg multiple changes the label and the GST note, so redraw the line.
    afterLineChange(key, soft && shownAsBag === isBagLine(p, line));
  }

  el.lines.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-act]");
    if (!btn || btn.tagName === "INPUT") return;
    var key = btn.dataset.key, line = state.cart[key], act = btn.dataset.act;
    if (!line) return;
    var step = isBagLine(state.byId[line.id], line) ? 30 : 1;
    if (act === "inc") setLineQty(key, line.qty + step, false);
    else if (act === "dec") setLineQty(key, line.qty - step, false);
    else if (act === "remove") { delete state.cart[key]; afterLineChange(key, false); }
  });
  el.lines.addEventListener("change", function (e) {
    var input = e.target.closest("input[data-act]");
    if (!input) return;
    var key = input.dataset.key, line = state.cart[key];
    if (!line) return;
    var value = num(input.value);
    if (input.dataset.act === "qty") {
      if (value > 0) setLineQty(key, value, true);
      else { input.value = fmtQty(line.qty); IG.toast("Use the bin to remove an item"); }
    } else if (input.dataset.act === "rate") {
      if (value > 0) { line.price = Math.round(value * 100) / 100; afterLineChange(key, true); }
      else { input.value = fmtQty(line.price); }
    }
  });
  el.lines.addEventListener("focusin", function (e) {
    if (e.target.matches("input[data-act]")) e.target.select();
  });
  // Totals follow what is being typed, without redrawing.
  el.lines.addEventListener("input", function (e) {
    var input = e.target.closest("input[data-act]");
    if (!input) return;
    var key = input.dataset.key, line = state.cart[key];
    var value = num(input.value);
    if (!line || !(value > 0)) return;
    if (input.dataset.act === "qty") line.qty = round3(value);
    else line.price = value;
    refreshLine(key);
    persist(); updateChip(line.id); updateCartBar(); renderTotals();
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
    if (state.buyer.id && state.buyer.phone !== state.buyer.pickedPhone) state.buyer.id = null;
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
      if (!rows.length || (phoneOk(state.buyer.phone) && state.buyer.id)) { el.suggest.hidden = true; return; }
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
    var over = state.products.filter(function (p) { return qtyInBill(p.id) > p.stock; });
    if (over.length) return showError("Some items are more than the stock available. Reduce the quantity.");
    if (state.buyer.phone && !phoneOk(state.buyer.phone)) return showError("Enter the buyer's 10-digit mobile number, or leave it empty.");

    var original = el.saveBtn.textContent;
    el.saveBtn.disabled = true;
    el.saveBtn.textContent = "Saving…";

    IG.api(root.dataset.save, {
      method: "POST",
      body: {
        items: Object.keys(state.cart).map(function (k) {
          var l = state.cart[k];
          return { product_id: l.id, qty: l.qty, unit_price: l.price, is_loose: !!l.loose };
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
