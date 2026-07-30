document.addEventListener("DOMContentLoaded", function () {
  var app = document.getElementById("pos-app");
  if (!app) return;

  var gstEnabled = app.dataset.gstEnabled === "true";
  var productCards = Array.from(document.querySelectorAll(".product-card"));
  var productsById = {};
  var productsByBarcode = {};
  var cart = new Map();

  function getItemKey(productId, isLoose) {
    return productId + (isLoose ? ":loose" : ":pack");
  }

  productCards.forEach(function (card) {
    var product = {
      id: parseInt(card.dataset.id, 10),
      name: card.dataset.name,
      sku: card.dataset.sku || "",
      price: parseFloat(card.dataset.price),
      unit: card.dataset.unit,
      gst: parseFloat(card.dataset.gst || "0"),
      hsn: card.dataset.hsn || "",
      barcode: card.dataset.barcode || "",
      category: card.dataset.category || "",
      weight: card.dataset.weight || "",
    };
    productsById[product.id] = product;
    if (product.barcode) {
      productsByBarcode[product.barcode] = product;
    }
  });

  var cartBody = document.getElementById("cart-body");
  var cartCount = document.getElementById("cart-count");
  var cartEmptyMsg = document.getElementById("cart-empty-msg");
  var subtotalEl = document.getElementById("summary-subtotal");
  var discountEl = document.getElementById("summary-discount");
  var taxableEl = document.getElementById("summary-taxable");
  var gstEl = document.getElementById("summary-gst");
  var grandEl = document.getElementById("summary-grand");
  var errorEl = document.getElementById("pos-error");
  var amountPaidEl = document.getElementById("amount-paid");
  var changeEl = document.getElementById("change-returned");

  var discountAmountEl = document.getElementById("discount-amount");
  var discountTypeEls = document.querySelectorAll("input[name='discount-type']");
  var paymentModeEls = document.querySelectorAll("input[name='payment-mode']");
  var cashFields = document.getElementById("cash-fields");

  var searchInput = document.getElementById("product-search");
  var categoryTabs = document.getElementById("category-tabs");
  var customerSearch = document.getElementById("customer-search");
  var customerSuggestions = document.getElementById("customer-suggestions");
  var customerName = document.getElementById("customer-name");
  var customerPhone = document.getElementById("customer-phone");
  var customerAddress = document.getElementById("customer-address");
  var customerGstin = document.getElementById("customer-gstin");
  var customerId = document.getElementById("customer-id");
  var notesEl = document.getElementById("bill-notes");

  var savePrintBtn = document.getElementById("save-print");
  var saveDraftBtn = document.getElementById("save-draft");
  var clearCartBtn = document.getElementById("clear-cart");
  var overallGstEl = document.getElementById("apply-overall-gst");

  var csrfToken = document.querySelector("meta[name='csrf-token']");
  var csrfValue = csrfToken ? csrfToken.getAttribute("content") : "";

  // ── Toast notification ──────────────────────────────────────────────

  function showToast(message, type) {
    type = type || "success";
    var toast = document.createElement("div");
    toast.className = "pos-toast pos-toast-" + type;
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(function () { toast.classList.add("show"); });
    setTimeout(function () {
      toast.classList.remove("show");
      setTimeout(function () { toast.remove(); }, 300);
    }, 2500);
  }

  function showError(message) {
    if (!errorEl) return;
    errorEl.textContent = message;
    errorEl.hidden = false;
    setTimeout(function () { errorEl.hidden = true; }, 5000);
  }

  function clearError() {
    if (!errorEl) return;
    errorEl.hidden = true;
  }

  // ── Cart operations ─────────────────────────────────────────────────

  function addItem(product, qty, options) {
    options = options || {};
    var isLoose = !!options.isLoose;
    var overridePrice = options.overridePrice;
    qty = qty || 1;
    var itemKey = getItemKey(product.id, isLoose);
    var usePrice = (overridePrice != null && overridePrice > 0) ? overridePrice : product.price;

    if (cart.has(itemKey)) {
      var existing = cart.get(itemKey);
      existing.qty += qty;
      if (overridePrice != null && overridePrice > 0) {
        existing.price = usePrice;
      }
    } else {
      cart.set(itemKey, {
        key: itemKey,
        product_id: product.id,
        name: product.name,
        price: usePrice,
        unit: product.unit,
        gst: product.gst,
        hsn: product.hsn,
        qty: qty,
        is_loose: isLoose,
      });
    }
    renderCart();
    showToast(qty + " " + product.unit + " " + product.name + " added \u2014 \u20b9" + usePrice.toFixed(2) + "/kg");
  }

  function removeItem(itemKey) {
    cart.delete(itemKey);
    renderCart();
  }

  function renderCart() {
    cartBody.innerHTML = "";
    var items = Array.from(cart.values());

    // Show/hide empty message
    if (cartEmptyMsg) {
      cartEmptyMsg.style.display = items.length === 0 ? "flex" : "none";
    }

    items.forEach(function (item) {
      var lineTotal = item.price * item.qty;
      var nameLabel = item.name + (item.is_loose ? ' <span class="loose-badge">Loose</span>' : "");
      // Smart qty label: show "X Pkt (Ykg)" for 30kg multiples
      var qtyLabel = "";
      if (!item.is_loose && item.unit === "kg" && item.qty >= 30 && item.qty % 30 === 0) {
        qtyLabel = "30kg/" + (item.qty / 30);
      } else if (item.unit === "kg" && item.qty === 1) {
        qtyLabel = "1 kg";
      } else {
        var qtyNum = item.qty % 1 === 0 ? item.qty.toFixed(0) : item.qty.toFixed(3);
        qtyLabel = qtyNum + " " + item.unit;
      }

      var qtyDisplay = item.qty % 1 === 0 ? item.qty.toFixed(0) : item.qty.toFixed(3);
      var row = document.createElement("tr");
      row.innerHTML =
        '<td class="cart-item-name">' +
          '<div class="cart-item-title">' + nameLabel + '</div>' +
          '<div class="cart-item-unit">' + item.unit + (item.hsn ? ' · HSN ' + item.hsn : '') + '</div>' +
        '</td>' +
        '<td class="cart-item-rate">' +
          '<input class="rate-input" type="number" min="0" step="0.01" data-key="' + item.key + '" value="' + item.price.toFixed(2) + '">' +
        '</td>' +
        '<td class="cart-item-qty">' +
          '<div class="qty-stepper">' +
            '<button class="qty-btn qty-minus" data-key="' + item.key + '">−</button>' +
            '<input class="qty-input" type="number" min="0.001" step="1" data-key="' + item.key + '" value="' + qtyDisplay + '">' +
            '<button class="qty-btn qty-plus" data-key="' + item.key + '">+</button>' +
          '</div>' +
          '<div class="qty-label">' + qtyLabel + '</div>' +
        '</td>' +
        '<td class="cart-item-total">₹' + lineTotal.toFixed(2) + '</td>' +
        '<td><button class="remove-btn" data-key="' + item.key + '" title="Remove">✕</button></td>';
      cartBody.appendChild(row);
    });

    var totalQty = 0;
    items.forEach(function (item) { totalQty += item.qty; });
    cartCount.textContent = items.length + " items · " + totalQty.toFixed(1) + " units";
    updateTotals();
  }

  function updateTotals() {
    var subtotal = 0;
    var perProductGst = 0;

    cart.forEach(function (item) {
      var lineTotal = item.price * item.qty;
      var gstRate = item.gst;
      if (!item.is_loose && item.unit === "kg" && item.qty >= 30 && item.qty % 30 === 0) {
        gstRate = 0;
      }
      subtotal += lineTotal;
      perProductGst += (lineTotal * gstRate) / 100;
    });

    var discountType = getDiscountType();
    var discountAmount = parseFloat(discountAmountEl.value || "0");
    if (discountType === "percent") {
      discountAmount = (subtotal * discountAmount) / 100;
    }
    if (discountAmount > subtotal) discountAmount = subtotal;

    var taxable = subtotal - discountAmount;

    // Overall 18% GST overrides per-product GST if checkbox checked
    var useOverallGst = overallGstEl && overallGstEl.checked;
    var gstTotal = useOverallGst ? (taxable * 0.05) : perProductGst;
    var gst = gstEnabled ? gstTotal : 0;
    var grand = taxable + gst;

    subtotalEl.textContent = "₹ " + subtotal.toFixed(2);
    discountEl.textContent = "₹ " + discountAmount.toFixed(2);
    taxableEl.textContent = "₹ " + taxable.toFixed(2);
    gstEl.textContent = "₹ " + gst.toFixed(2);
    grandEl.textContent = "₹ " + grand.toFixed(2);

    // Show/hide note
    var noteEl = document.getElementById("gst-override-note");
    if (noteEl) noteEl.hidden = !useOverallGst;

    updateChange();
  }

  function updateChange() {
    var grandText = grandEl.textContent.replace(/[₹\s,]/g, '') || "0";
    var grand = parseFloat(grandText);
    var paid = parseFloat(amountPaidEl.value || "0");
    var change = paid - grand;
    changeEl.textContent = change > 0 ? "₹ " + change.toFixed(2) : "₹ 0.00";
  }

  function getDiscountType() {
    var value = "flat";
    discountTypeEls.forEach(function (el) {
      if (el.checked) value = el.value;
    });
    return value;
  }

  function getPaymentMode() {
    var value = "cash";
    paymentModeEls.forEach(function (el) {
      if (el.checked) value = el.value;
    });
    return value;
  }

  function clearCart() {
    cart.clear();
    renderCart();
  }

  function buildPayload(status) {
    var grandText = grandEl.textContent.replace(/[₹\s,]/g, '') || "0";
    var grand = parseFloat(grandText);
    var amountPaid = parseFloat(amountPaidEl.value || "0");
    if (getPaymentMode() !== "cash") {
      amountPaid = grand;
    }
    if (amountPaid <= 0) {
      amountPaid = grand;
    }
    return {
      items: Array.from(cart.values()).map(function (item) {
        return {
          product_id: item.product_id,
          qty: item.qty,
          unit_price: item.price,
          is_loose: item.is_loose || false,
        };
      }),
      discount_type: getDiscountType(),
      discount_amount: parseFloat(discountAmountEl.value || "0"),
      payment_mode: getPaymentMode(),
      amount_paid: amountPaid,
      notes: notesEl.value || "",
      customer_id: customerId.value || null,
      customer_name: customerName.value || "",
      customer_phone: customerPhone.value || "",
      customer_address: customerAddress.value || "",
      customer_gstin: customerGstin.value || "",
      apply_overall_gst: overallGstEl ? overallGstEl.checked : false,
      overall_gst_rate: 5,
      status: status,
    };
  }

  function saveBill(status) {
    if (cart.size === 0) {
      showError("Cart is empty.");
      return;
    }
    clearError();
    savePrintBtn.disabled = true;
    savePrintBtn.textContent = "⏳ Saving...";

    fetch("/bill/create", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfValue,
      },
      body: JSON.stringify(buildPayload(status)),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) {
            throw new Error(data.error || "Failed to save bill.");
          }
          return data;
        });
      })
      .then(function (data) {
        window.location.href = "/bill/" + data.bill_id + "/print";
      })
      .catch(function (err) {
        showError(err.message);
        savePrintBtn.disabled = false;
        savePrintBtn.textContent = "💾 Save & Print (F4)";
      });
  }

  function saveDraft() {
    if (cart.size === 0) {
      showError("Cart is empty.");
      return;
    }
    clearError();

    fetch("/bill/draft", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfValue,
      },
      body: JSON.stringify(buildPayload("draft")),
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Failed to save draft.");
        }
        return response.json();
      })
      .then(function () {
        showToast("Draft saved successfully", "success");
      })
      .catch(function (err) {
        showError(err.message);
      });
  }

  function loadDraft() {
    fetch("/bill/draft")
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (!data || !data.items) return;
        if (!confirm("Load saved draft into cart?") ) return;

        cart.clear();
        data.items.forEach(function (item) {
          var product = productsById[item.product_id];
          if (!product) return;
          var isLoose = !!item.is_loose;
          var itemKey = getItemKey(product.id, isLoose);
          cart.set(itemKey, {
            key: itemKey,
            product_id: product.id,
            name: product.name,
            price: item.unit_price ? parseFloat(item.unit_price) : product.price,
            unit: product.unit,
            gst: product.gst,
            hsn: product.hsn,
            qty: parseFloat(item.qty),
            is_loose: isLoose,
          });
        });

        discountAmountEl.value = data.discount_amount || 0;
        discountTypeEls.forEach(function (el) {
          el.checked = el.value === data.discount_type;
        });

        paymentModeEls.forEach(function (el) {
          el.checked = el.value === data.payment_mode;
        });

        amountPaidEl.value = data.amount_paid || "";
        notesEl.value = data.notes || "";
        customerId.value = data.customer_id || "";
        customerName.value = data.customer_name || "";
        customerPhone.value = data.customer_phone || "";
        customerAddress.value = data.customer_address || "";
        customerGstin.value = data.customer_gstin || "";

        renderCart();
      })
      .catch(function () {
        // ignore draft load errors
      });
  }

  function filterProducts() {
    var text = (searchInput.value || "").trim().toLowerCase();
    var activeCategory = categoryTabs.querySelector(".tab.active");
    var categoryId = activeCategory ? activeCategory.dataset.category : "all";

    productCards.forEach(function (card) {
      var matchesText =
        card.dataset.name.toLowerCase().includes(text) ||
        (card.dataset.sku || "").toLowerCase().includes(text) ||
        card.dataset.barcode.toLowerCase().includes(text) ||
        card.dataset.id === text;

      var matchesCategory = categoryId === "all" || card.dataset.category === categoryId;

      card.style.display = (matchesText && matchesCategory) ? "" : "none";
    });
  }

  function setupCustomerTypeahead() {
    var timer = null;
    customerSearch.addEventListener("input", function () {
      clearTimeout(timer);
      var q = customerSearch.value.trim();
      if (!q) {
        customerSuggestions.classList.remove("active");
        customerSuggestions.innerHTML = "";
        return;
      }
      timer = setTimeout(function () {
        fetch("/api/customers/search?q=" + encodeURIComponent(q))
          .then(function (response) { return response.json(); })
          .then(function (data) {
            if (!Array.isArray(data) || data.length === 0) {
              customerSuggestions.classList.remove("active");
              customerSuggestions.innerHTML = "";
              return;
            }
            customerSuggestions.innerHTML = "";
            data.forEach(function (cust) {
              var item = document.createElement("div");
              item.className = "suggestion-item";
              item.textContent = cust.name + " (" + (cust.phone || "") + ")";
              item.addEventListener("click", function () {
                customerId.value = cust.id;
                customerName.value = cust.name || "";
                customerPhone.value = cust.phone || "";
                customerAddress.value = cust.address || "";
                customerGstin.value = cust.gstin || "";
                customerSearch.value = cust.name;
                customerSuggestions.classList.remove("active");
              });
              customerSuggestions.appendChild(item);
            });
            customerSuggestions.classList.add("active");
          });
      }, 200);
    });
  }

  // ── Event: Qty input change in cart ──────────────────────────────────

  cartBody.addEventListener("input", function (event) {
    if (event.target.classList.contains("qty-input")) {
      var id = event.target.dataset.key;
      var value = parseFloat(event.target.value || "0");
      if (cart.has(id)) {
        cart.get(id).qty = value > 0 ? value : 0.001;
      }
      updateTotals();
    }
    if (event.target.classList.contains("rate-input")) {
      var rateId = event.target.dataset.key;
      var newPrice = parseFloat(event.target.value || "0");
      if (cart.has(rateId) && newPrice >= 0) {
        cart.get(rateId).price = newPrice;
      }
      updateTotals();
    }
  });

  // ── Event: Stepper +/- and remove buttons ───────────────────────────

  cartBody.addEventListener("click", function (event) {
    var removeBtn = event.target.closest(".remove-btn");
    if (removeBtn) {
      removeItem(removeBtn.dataset.key);
      return;
    }

    var plusBtn = event.target.closest(".qty-plus");
    if (plusBtn) {
      var id = plusBtn.dataset.key;
      if (cart.has(id)) {
        cart.get(id).qty += 1;
        renderCart();
      }
      return;
    }

    var minusBtn = event.target.closest(".qty-minus");
    if (minusBtn) {
      var id2 = minusBtn.dataset.key;
      if (cart.has(id2)) {
        var item = cart.get(id2);
        item.qty = Math.max(item.qty - 1, 0.001);
        if (item.qty <= 0.001 && item.qty < 1) {
          // If qty goes to near-zero, remove
          cart.delete(id2);
        }
        renderCart();
      }
    }
  });

  // ── Event: Bag size buttons on product cards ────────────────────────

  document.getElementById("product-grid").addEventListener("click", function (event) {
    // Handle bag buttons
    var bagBtn = event.target.closest(".bag-btn");
    if (bagBtn) {
      event.stopPropagation();
      var productId = parseInt(bagBtn.dataset.id, 10);
      var product = productsById[productId];
      if (!product) return;

      var isLoose = bagBtn.dataset.loose === "1";

      // Read rate override for this product card
      var rateOverrideInput = document.querySelector('.rate-override-input[data-id="' + productId + '"]');
      var overridePrice = rateOverrideInput ? parseFloat(rateOverrideInput.value || "0") : 0;
      var priceOption = overridePrice > 0 ? { overridePrice: overridePrice } : {};

      if (bagBtn.classList.contains("bag-custom") || isLoose) {
        // Custom qty from input
        var qtyInput = bagBtn.parentElement.querySelector(".quick-qty-input");
        var customQty = parseFloat(qtyInput ? qtyInput.value : "0");
        if (customQty > 0) {
          addItem(product, customQty, Object.assign({ isLoose: isLoose }, priceOption));
          if (qtyInput) qtyInput.value = "";
        } else {
          showToast("Enter a valid quantity", "error");
        }
      } else {
        var qty = parseFloat(bagBtn.dataset.qty || "1");
        addItem(product, qty, Object.assign({ isLoose: false }, priceOption));
      }
      return;
    }

    // Handle quick qty input Enter key — handled separately below
  });

  // Handle Enter key on quick qty inputs
  document.getElementById("product-grid").addEventListener("keydown", function (event) {
    if (event.key === "Enter" && event.target.classList.contains("quick-qty-input")) {
      event.preventDefault();
      var productId = parseInt(event.target.dataset.id, 10);
      var product = productsById[productId];
      var qty = parseFloat(event.target.value || "0");
      if (product && qty > 0) {
        addItem(product, qty, { isLoose: false });
        event.target.value = "";
      }
    }
  });

  // ── Event: Category tabs ────────────────────────────────────────────

  categoryTabs.addEventListener("click", function (event) {
    var tab = event.target.closest(".tab");
    if (!tab) return;
    categoryTabs.querySelectorAll(".tab").forEach(function (el) {
      el.classList.remove("active");
    });
    tab.classList.add("active");
    filterProducts();
  });

  // ── Event: Filter, discount, payment ────────────────────────────────

  searchInput.addEventListener("input", filterProducts);
  discountAmountEl.addEventListener("input", updateTotals);
  discountTypeEls.forEach(function (el) {
    el.addEventListener("change", updateTotals);
  });
  paymentModeEls.forEach(function (el) {
    el.addEventListener("change", function () {
      var mode = getPaymentMode();
      cashFields.style.display = mode === "cash" ? "block" : "none";
      updateChange();
    });
  });
  amountPaidEl.addEventListener("input", updateChange);

  // GST checkbox toggle
  if (overallGstEl) {
    overallGstEl.addEventListener("change", updateTotals);
  }

  // ── Event: Action buttons ───────────────────────────────────────────

  savePrintBtn.addEventListener("click", function () {
    saveBill("confirmed");
  });
  saveDraftBtn.addEventListener("click", saveDraft);
  clearCartBtn.addEventListener("click", function () {
    if (cart.size === 0) return;
    if (confirm("Clear the current cart?")) {
      clearCart();
      showToast("Cart cleared", "success");
    }
  });

  // ── Keyboard shortcuts ──────────────────────────────────────────────

  document.addEventListener("keydown", function (event) {
    if (event.key === "F2") {
      event.preventDefault();
      searchInput.focus();
      searchInput.select();
    }
    if (event.key === "F4") {
      event.preventDefault();
      saveBill("confirmed");
    }
    if (event.key === "Escape") {
      searchInput.value = "";
      filterProducts();
      searchInput.focus();
    }
  });

  // ── Barcode scanner listener ────────────────────────────────────────

  (function setupBarcodeListener() {
    var buffer = "";
    var lastTime = 0;

    document.addEventListener("keydown", function (event) {
      // Ignore if focus is on an input/textarea
      if (event.target.tagName === "INPUT" || event.target.tagName === "TEXTAREA") {
        return;
      }

      if (event.key === "Enter") {
        if (buffer.length >= 4) {
          var product = productsByBarcode[buffer];
          if (product) addItem(product, 1);
        }
        buffer = "";
        return;
      }
      var now = Date.now();
      if (now - lastTime > 50) buffer = "";
      lastTime = now;

      if (event.key.length === 1) {
        buffer += event.key;
      }
    });
  })();

  // ── Initialize ──────────────────────────────────────────────────────

  setupCustomerTypeahead();
  loadDraft();
  renderCart();
  searchInput.focus();
});
