/* Progressive enhancement only — every form still works without this file,
   except the upload progress bar. */
(function () {
  "use strict";

  /* ---------------------------------------------------------- navigation */
  var burger = document.querySelector("[data-nav-toggle]");
  var scrim = document.querySelector(".scrim");
  function closeNav() { document.body.classList.remove("nav-open"); }
  if (burger) {
    burger.addEventListener("click", function () {
      document.body.classList.toggle("nav-open");
    });
  }
  if (scrim) scrim.addEventListener("click", closeNav);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeNav();
  });

  document.querySelectorAll("[data-nav-section]").forEach(function (section) {
    var toggle = section.querySelector("[data-nav-group-toggle]");
    if (!toggle) return;

    var panel = document.getElementById(toggle.getAttribute("aria-controls"));
    if (!panel) return;

    var storageKey = "service-management.nav." + section.dataset.navSection;
    var storedState = null;
    try {
      storedState = window.localStorage.getItem(storageKey);
    } catch (error) {
      storedState = null;
    }

    var isActive = section.dataset.active === "true";
    var isOpen = isActive || storedState === "open";

    function setGroupOpen(open, remember) {
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      panel.hidden = !open;

      if (remember) {
        try {
          window.localStorage.setItem(storageKey, open ? "open" : "closed");
        } catch (error) {
          // Navigation still works when browser storage is unavailable.
        }
      }
    }

    setGroupOpen(isOpen, false);
    toggle.addEventListener("click", function () {
      setGroupOpen(toggle.getAttribute("aria-expanded") !== "true", true);
    });
  });

  /* ------------------------------------------- service item image picker */
  var activeServiceItemSelect = null;
  var activeServiceItemPicker = null;

  function syncServiceItemTrigger(select) {
    var trigger = select.parentElement.querySelector("[data-service-item-trigger]");
    if (!trigger) return;
    var option = select.options[select.selectedIndex];
    trigger.textContent = option && option.value
      ? option.textContent.trim()
      : select.options[0].textContent.trim();
  }

  window.initializeServiceItemPickers = function (root) {
    (root || document).querySelectorAll("[data-service-item-select]").forEach(function (select) {
      if (select.dataset.itemPickerReady === "true") return;
      var trigger = select.parentElement.querySelector("[data-service-item-trigger]");
      if (!trigger) return;
      select.dataset.itemPickerReady = "true";
      select.hidden = true;
      select.required = false;
      trigger.hidden = false;
      syncServiceItemTrigger(select);
      select.addEventListener("change", function () { syncServiceItemTrigger(select); });
    });
  };

  document.querySelectorAll("[data-password-toggle]").forEach(function (button) {
    var input = document.getElementById(button.dataset.passwordToggle);
    if (!input) return;
    button.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      button.textContent = show ? button.dataset.hideLabel : button.dataset.showLabel;
      button.setAttribute("aria-pressed", show ? "true" : "false");
      input.focus();
    });
  });

  document.querySelectorAll("[data-service-item-picker]").forEach(function (picker) {
    var search = picker.querySelector("[data-service-item-picker-search]");
    var empty = picker.querySelector("[data-service-item-picker-empty]");
    var close = picker.querySelector("[data-close-service-item-picker]");
    if (close) close.addEventListener("click", function () { picker.close(); });
    if (search) {
      search.addEventListener("input", function () {
        var query = search.value.trim().toLowerCase();
        var visibleCount = 0;
        picker.querySelectorAll("[data-service-item-choice]").forEach(function (choice) {
          var matches = !query || choice.dataset.searchText.indexOf(query) !== -1;
          choice.hidden = !matches;
          if (matches) visibleCount += 1;
        });
        picker.querySelectorAll(".pricing-item-picker-category").forEach(function (category) {
          category.hidden = !category.querySelector(
            "[data-service-item-choice]:not([hidden])"
          );
        });
        if (empty) empty.hidden = visibleCount !== 0;
      });
    }
    picker.querySelectorAll("[data-service-item-choice]").forEach(function (choice) {
      choice.addEventListener("click", function () {
        if (!activeServiceItemSelect || activeServiceItemPicker !== picker) return;
        activeServiceItemSelect.value = choice.dataset.itemValue;
        activeServiceItemSelect.dispatchEvent(new Event("change", { bubbles: true }));
        picker.close();
        activeServiceItemSelect.closest("[data-device-row]").scrollIntoView({
          behavior: "smooth",
          block: "center"
        });
      });
    });
  });

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest("[data-service-item-trigger]");
    if (!trigger) return;
    var select = trigger.parentElement.querySelector("[data-service-item-select]");
    if (!select) return;
    var picker = document.querySelector(
      '[data-service-item-picker="' + select.dataset.serviceItemSelect + '"]'
    );
    if (!picker) return;
    activeServiceItemSelect = select;
    activeServiceItemPicker = picker;
    var search = picker.querySelector("[data-service-item-picker-search]");
    if (search) {
      search.value = "";
      search.dispatchEvent(new Event("input"));
    }
    picker.showModal();
    if (search) search.focus();
  });

  window.initializeServiceItemPickers(document);

  /* -------------------------------------------------- pricing quotation */
  var pricingForm = document.querySelector("[data-pricing-quotation-form]");
  var catalogueNode = document.getElementById("pricing-catalogue-data");
  if (pricingForm && catalogueNode) {
    var pricingCatalogue = [];
    try {
      pricingCatalogue = JSON.parse(catalogueNode.textContent);
    } catch (error) {
      pricingCatalogue = [];
    }
    var pricingLines = pricingForm.querySelector("[data-pricing-lines]");
    var addPricingLineButtons = pricingForm.querySelectorAll("[data-add-pricing-line]");
    var pricingLineFooter = pricingForm.querySelector(".pricing-add-line-footer");
    var pricingItemPicker = pricingForm.querySelector("[data-pricing-item-picker]");
    var pricingItemPickerSearch = pricingForm.querySelector("[data-pricing-item-picker-search]");
    var pricingItemPickerEmpty = pricingForm.querySelector("[data-pricing-item-picker-empty]");
    var pricingPickerSection = null;
    var nextPricingIndex = 0;

    function catalogueItem(value) {
      return pricingCatalogue.filter(function (item) {
        return String(item.id) === String(value);
      })[0];
    }

    function syncPricingItemTrigger(section) {
      var select = section.querySelector("[data-pricing-item-select]");
      var trigger = section.querySelector("[data-choose-pricing-item]");
      if (!trigger) return;
      var item = catalogueItem(select.value);
      trigger.textContent = item ? item.label : select.options[0].textContent.trim();
    }

    function refreshPricingLineNumbersAndAlternatives() {
      var sections = Array.from(
        pricingLines.querySelectorAll("[data-pricing-line]")
      );
      var itemLabel = pricingLines.dataset.itemLabel || "Item";
      var notAlternativeLabel =
        pricingLines.dataset.notAlternativeLabel || "Not an alternative";

      sections.forEach(function (section, position) {
        var heading = section.querySelector("[data-pricing-line-number]");
        if (heading) heading.textContent = itemLabel + " " + (position + 1);
      });

      sections.forEach(function (section) {
        var alternativeSelect = section.querySelector(
          "[data-pricing-alternative-select]"
        );
        if (!alternativeSelect) return;
        var selectedValue =
          alternativeSelect.value || alternativeSelect.dataset.currentAlternative || "";
        alternativeSelect.replaceChildren();

        var noneOption = document.createElement("option");
        noneOption.value = "";
        noneOption.textContent = notAlternativeLabel;
        alternativeSelect.appendChild(noneOption);

        sections.forEach(function (candidate, position) {
          if (candidate === section) return;
          var candidateItem = catalogueItem(
            candidate.querySelector("[data-pricing-item-select]").value
          );
          var option = document.createElement("option");
          option.value = candidate.dataset.lineIndex;
          option.textContent =
            itemLabel +
            " " +
            (position + 1) +
            (candidateItem ? " — " + candidateItem.label : "");
          alternativeSelect.appendChild(option);
        });
        if (
          Array.from(alternativeSelect.options).some(function (option) {
            return option.value === selectedValue;
          })
        ) {
          alternativeSelect.value = selectedValue;
        } else {
          alternativeSelect.value = "";
        }
        alternativeSelect.dataset.currentAlternative = alternativeSelect.value;
        if (!alternativeSelect.dataset.alternativeListener) {
          alternativeSelect.addEventListener("change", function () {
            alternativeSelect.dataset.currentAlternative = alternativeSelect.value;
          });
          alternativeSelect.dataset.alternativeListener = "true";
        }
      });
    }

    function relatedSelection(section) {
      try {
        return JSON.parse(section.dataset.relatedSelection || "[]");
      } catch (error) {
        return [];
      }
    }

    function renderRelatedItems(section, selected) {
      var index = section.dataset.lineIndex;
      var select = section.querySelector("[data-pricing-item-select]");
      var container = section.querySelector("[data-pricing-related-items]");
      var item = catalogueItem(select.value);
      container.replaceChildren();
      if (!item) return;

      if (!item.related.length) {
        var empty = document.createElement("p");
        empty.className = "hint";
        empty.textContent = "This main item has no optional related items.";
        container.appendChild(empty);
        return;
      }

      var title = document.createElement("p");
      title.className = "section-title";
      title.textContent = "Optional related items";
      container.appendChild(title);

      var optionalRows = [];
      item.related.forEach(function (related) {
        var previous = selected.filter(function (entry) {
          return String(entry.id) === String(related.id);
        })[0];
        var row = document.createElement("div");
        row.className = "pricing-related-choice";

        var choice = document.createElement("label");
        choice.className = "choice";
        var checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.name = "line_" + index + "_related_ids";
        checkbox.value = related.id;
        checkbox.checked = Boolean(previous);
        var labelText = document.createElement("span");
        labelText.textContent = related.name + " — " + related.price + " " + related.currency;
        choice.appendChild(checkbox);
        choice.appendChild(labelText);

        var quantityWrap = document.createElement("div");
        quantityWrap.className = "field pricing-related-quantity";
        quantityWrap.hidden = !checkbox.checked;
        var quantityLabel = document.createElement("label");
        var quantityId = "line-" + index + "-related-" + related.id;
        quantityLabel.htmlFor = quantityId;
        quantityLabel.textContent = "Quantity";
        var quantityInput = document.createElement("input");
        quantityInput.id = quantityId;
        quantityInput.name = "line_" + index + "_related_qty_" + related.id;
        quantityInput.type = "number";
        quantityInput.min = "1";
        quantityInput.step = "1";
        quantityInput.value = previous && previous.quantity ? previous.quantity : "1";
        quantityInput.required = checkbox.checked;
        quantityWrap.appendChild(quantityLabel);
        quantityWrap.appendChild(quantityInput);

        var priceWrap = document.createElement("div");
        priceWrap.className = "field pricing-related-price";
        priceWrap.hidden = !checkbox.checked;
        var priceLabel = document.createElement("label");
        var priceId = quantityId + "-price";
        priceLabel.htmlFor = priceId;
        priceLabel.textContent = "Unit price";
        var priceInput = document.createElement("input");
        priceInput.id = priceId;
        priceInput.name = "line_" + index + "_related_price_" + related.id;
        priceInput.type = "number";
        priceInput.min = "0";
        priceInput.step = "0.01";
        priceInput.className = "catalogue-price-input";
        priceInput.value =
          previous && previous.unit_price ? previous.unit_price : related.price;
        priceInput.required = checkbox.checked;
        priceWrap.appendChild(priceLabel);
        priceWrap.appendChild(priceInput);

        var currencyWrap = document.createElement("div");
        currencyWrap.className = "field pricing-related-currency";
        currencyWrap.hidden = !checkbox.checked;
        var currencyLabel = document.createElement("label");
        var currencyId = quantityId + "-currency";
        currencyLabel.htmlFor = currencyId;
        currencyLabel.textContent = "Currency";
        var currencyInput = document.createElement("select");
        currencyInput.id = currencyId;
        currencyInput.name = "line_" + index + "_related_currency_" + related.id;
        ["SAR", "USD"].forEach(function (code) {
          var option = document.createElement("option");
          option.value = code;
          option.textContent = code;
          currencyInput.appendChild(option);
        });
        currencyInput.value =
          previous && previous.currency ? previous.currency : related.currency;
        currencyInput.required = checkbox.checked;
        currencyWrap.appendChild(currencyLabel);
        currencyWrap.appendChild(currencyInput);

        function setSelected(active) {
          checkbox.checked = active;
          quantityWrap.hidden = !active;
          priceWrap.hidden = !active;
          currencyWrap.hidden = !active;
          quantityInput.required = active;
          priceInput.required = active;
          currencyInput.required = active;
          if (!active) {
            quantityInput.value = "1";
            priceInput.value = related.price;
            currencyInput.value = related.currency;
          }
        }

        checkbox.addEventListener("change", function () {
          setSelected(checkbox.checked);
          if (checkbox.checked && skipCheckbox) {
            skipCheckbox.checked = false;
            section.dataset.skipOptional = "false";
          }
        });

        row.appendChild(choice);
        row.appendChild(quantityWrap);
        row.appendChild(priceWrap);
        row.appendChild(currencyWrap);
        container.appendChild(row);
        optionalRows.push({ checkbox: checkbox, setSelected: setSelected });
      });

      var skipChoice = document.createElement("label");
      skipChoice.className = "choice pricing-skip-optionals";
      var skipCheckbox = document.createElement("input");
      skipCheckbox.type = "checkbox";
      skipCheckbox.name = "line_" + index + "_skip_optional_items";
      skipCheckbox.value = "1";
      skipCheckbox.checked = section.dataset.skipOptional === "true";
      var skipText = document.createElement("span");
      skipText.textContent = "Skip all optional items for this main item";
      skipChoice.appendChild(skipCheckbox);
      skipChoice.appendChild(skipText);
      container.appendChild(skipChoice);

      skipCheckbox.addEventListener("change", function () {
        section.dataset.skipOptional = skipCheckbox.checked ? "true" : "false";
        if (skipCheckbox.checked) {
          optionalRows.forEach(function (entry) {
            entry.setSelected(false);
          });
        }
      });
      if (skipCheckbox.checked) {
        optionalRows.forEach(function (entry) {
          entry.setSelected(false);
        });
      }
    }

    function updateMainItem(section, resetPrice) {
      var select = section.querySelector("[data-pricing-item-select]");
      var item = catalogueItem(select.value);
      var priceInput = section.querySelector("[data-pricing-main-price]");
      var currencyInput = section.querySelector("[data-pricing-main-currency]");
      var image = section.querySelector("[data-pricing-item-image]");
      if (!item) {
        if (resetPrice) {
          priceInput.value = "";
          currencyInput.value = "SAR";
        }
        image.hidden = true;
        image.removeAttribute("src");
        image.alt = "";
        return;
      }
      if (resetPrice || !priceInput.value) priceInput.value = item.price;
      if (resetPrice || !currencyInput.value) currencyInput.value = item.currency;
      if (item.image_url) {
        image.src = item.image_url;
        image.alt = item.label;
        image.hidden = false;
      } else {
        image.hidden = true;
        image.removeAttribute("src");
        image.alt = "";
      }
    }

    function refreshRemoveButtons() {
      var sections = pricingLines.querySelectorAll("[data-pricing-line]");
      sections.forEach(function (section) {
        section.querySelector("[data-remove-pricing-line]").disabled =
          sections.length === 1;
      });
    }

    function initialisePricingLine(section) {
      var index = Number(section.dataset.lineIndex);
      nextPricingIndex = Math.max(nextPricingIndex, index + 1);
      var select = section.querySelector("[data-pricing-item-select]");
      var pickerTrigger = section.querySelector("[data-choose-pricing-item]");
      if (pickerTrigger) {
        select.hidden = true;
        select.required = false;
        pickerTrigger.hidden = false;
        syncPricingItemTrigger(section);
        pickerTrigger.addEventListener("click", function () {
          pricingPickerSection = section;
          openPricingItemPicker();
        });
      }
      updateMainItem(section, false);
      renderRelatedItems(section, relatedSelection(section));
      select.addEventListener("change", function () {
        section.dataset.relatedSelection = "[]";
        section.dataset.skipOptional = "false";
        updateMainItem(section, true);
        renderRelatedItems(section, []);
        syncPricingItemTrigger(section);
        refreshPricingLineNumbersAndAlternatives();
      });
      section.querySelector("[data-remove-pricing-line]").addEventListener(
        "click",
        function () {
          section.remove();
          refreshRemoveButtons();
          refreshPricingLineNumbersAndAlternatives();
        }
      );
    }

    pricingLines.querySelectorAll("[data-pricing-line]").forEach(
      initialisePricingLine
    );
    refreshRemoveButtons();
    refreshPricingLineNumbersAndAlternatives();

    function usePricingItem(itemId) {
      var emptySection = Array.from(
        pricingLines.querySelectorAll("[data-pricing-line]")
      ).filter(function (candidate) {
        return !candidate.querySelector("[data-pricing-item-select]").value;
      })[0];
      if (emptySection) {
        var emptySelect = emptySection.querySelector("[data-pricing-item-select]");
        emptySection.dataset.relatedSelection = "[]";
        emptySection.dataset.skipOptional = "false";
        emptySelect.value = String(itemId);
        updateMainItem(emptySection, true);
        renderRelatedItems(emptySection, []);
        syncPricingItemTrigger(emptySection);
        refreshPricingLineNumbersAndAlternatives();
        emptySection.scrollIntoView({ behavior: "smooth", block: "center" });
        emptySection.querySelector('input[type="number"]').focus();
        return;
      }
      var source = pricingLines.querySelector("[data-pricing-line]");
      if (!source) return;
      var oldIndex = source.dataset.lineIndex;
      var newIndex = String(nextPricingIndex++);
      var section = source.cloneNode(true);
      section.dataset.lineIndex = newIndex;
      section.dataset.relatedSelection = "[]";
      section.dataset.skipOptional = "false";
      section.querySelectorAll("[name]").forEach(function (field) {
        field.name = field.name.replace(
          "line_" + oldIndex + "_",
          "line_" + newIndex + "_"
        );
      });
      section.querySelectorAll("[id]").forEach(function (field) {
        field.id = field.id.replace("-" + oldIndex, "-" + newIndex);
      });
      section.querySelectorAll("label[for]").forEach(function (label) {
        label.htmlFor = label.htmlFor.replace("-" + oldIndex, "-" + newIndex);
      });
      section.querySelectorAll(".field-error").forEach(function (error) {
        error.remove();
      });
      section.querySelector("[data-pricing-item-select]").value = String(itemId);
      section.querySelector(
        'input[name="line_' + newIndex + '_quantity"]'
      ).value = "1";
      section.querySelector("[data-pricing-main-price]").value = "";
      section.querySelector("[data-pricing-main-currency]").value = "SAR";
      section.querySelector("[data-pricing-item-image]").hidden = true;
      section.querySelector("[data-pricing-related-items]").replaceChildren();
      var alternativeSelect = section.querySelector(
        "[data-pricing-alternative-select]"
      );
      if (alternativeSelect) {
        alternativeSelect.value = "";
        alternativeSelect.dataset.currentAlternative = "";
        delete alternativeSelect.dataset.alternativeListener;
      }
      pricingLines.insertBefore(section, pricingLineFooter || null);
      initialisePricingLine(section);
      refreshRemoveButtons();
      refreshPricingLineNumbersAndAlternatives();
      section.scrollIntoView({ behavior: "smooth", block: "center" });
      section.querySelector('input[type="number"]').focus();
    }

    function openPricingItemPicker() {
      if (!pricingItemPicker) return;
      if (pricingItemPickerSearch) {
        pricingItemPickerSearch.value = "";
        pricingItemPickerSearch.dispatchEvent(new Event("input"));
      }
      if (typeof pricingItemPicker.showModal === "function") {
        pricingItemPicker.showModal();
      } else {
        pricingItemPicker.setAttribute("open", "");
      }
      if (pricingItemPickerSearch) pricingItemPickerSearch.focus();
    }

    addPricingLineButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        pricingPickerSection = null;
        openPricingItemPicker();
      });
    });

    if (pricingItemPicker) {
      pricingItemPicker.querySelectorAll("[data-pricing-picker-item]").forEach(function (choice) {
        choice.addEventListener("click", function () {
          pricingItemPicker.close();
          if (pricingPickerSection) {
            var section = pricingPickerSection;
            var select = section.querySelector("[data-pricing-item-select]");
            select.value = String(choice.dataset.itemId);
            select.dispatchEvent(new Event("change", { bubbles: true }));
            section.scrollIntoView({ behavior: "smooth", block: "center" });
          } else {
            usePricingItem(choice.dataset.itemId);
          }
          pricingPickerSection = null;
        });
      });
      var closePicker = pricingItemPicker.querySelector("[data-close-pricing-item-picker]");
      if (closePicker) closePicker.addEventListener("click", function () { pricingItemPicker.close(); });
      if (pricingItemPickerSearch) {
        pricingItemPickerSearch.addEventListener("input", function () {
          var query = pricingItemPickerSearch.value.trim().toLowerCase();
          var visibleCount = 0;
          pricingItemPicker.querySelectorAll("[data-pricing-picker-item]").forEach(function (choice) {
            var matches = !query || choice.dataset.searchText.indexOf(query) !== -1;
            choice.hidden = !matches;
            if (matches) visibleCount += 1;
          });
          pricingItemPicker.querySelectorAll(".pricing-item-picker-category").forEach(function (category) {
            category.hidden = !category.querySelector(
              "[data-pricing-picker-item]:not([hidden])"
            );
          });
          if (pricingItemPickerEmpty) pricingItemPickerEmpty.hidden = visibleCount !== 0;
        });
      }
    }

    var manpowerQuantity = pricingForm.querySelector("[data-manpower-quantity]");
    var manpowerPrice = pricingForm.querySelector("[data-manpower-price]");
    var manpowerCurrency = pricingForm.querySelector("[data-manpower-currency]");
    var installationPrice = pricingForm.querySelector("[data-installation-price]");
    var installationCurrency = pricingForm.querySelector("[data-installation-currency]");
    function updateInstallationPrice() {
      var workers = Number(manpowerQuantity.value);
      var perWorker = Number(manpowerPrice.value);
      installationPrice.value = Number.isFinite(workers) && Number.isFinite(perWorker)
        ? (workers * perWorker).toFixed(2)
        : "";
      installationCurrency.value = manpowerCurrency.value;
    }
    [manpowerQuantity, manpowerPrice, manpowerCurrency].forEach(function (field) {
      field.addEventListener("input", updateInstallationPrice);
      field.addEventListener("change", updateInstallationPrice);
    });
    updateInstallationPrice();

    /* -------------------------------- camera installation plan bridge */
    var plannerFrame = pricingForm.querySelector("[data-planner-frame]");
    var plannerDataNode = document.getElementById("quotation-planner-data");
    var plannerState = pricingForm.querySelector("[data-planner-state]");
    var plannerSubmitError = pricingForm.querySelector("[data-planner-submit-error]");
    var plannerReady = false;
    var plannerRequestId = null;
    var plannerSubmitting = false;
    var plannerInitial = { state: null, background_url: null };
    if (plannerDataNode) {
      try {
        plannerInitial = JSON.parse(plannerDataNode.textContent);
      } catch (error) {
        plannerInitial = { state: null, background_url: null };
      }
    }

    function showPlannerSubmitError(message) {
      if (!plannerSubmitError) return;
      plannerSubmitError.textContent = message;
      plannerSubmitError.hidden = !message;
      if (message) plannerSubmitError.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    function setQuotationSubmitting(active) {
      plannerSubmitting = active;
      pricingForm.querySelectorAll('button[type="submit"]').forEach(function (button) {
        button.disabled = active;
      });
    }

    function dataUrlBlob(dataUrl) {
      if (!dataUrl) return Promise.resolve(null);
      return fetch(dataUrl).then(function (response) { return response.blob(); });
    }

    function renderQuotationErrors(errors) {
      var messages = Object.keys(errors || {}).map(function (key) { return errors[key]; });
      showPlannerSubmitError(messages.join(" ") || "The quotation could not be saved. Review the form and try again.");
    }

    function submitQuotationWithPlan(result) {
      plannerState.value = result.design ? JSON.stringify(result.design) : "";
      Promise.all([
        dataUrlBlob(result.backgroundDataUrl),
        dataUrlBlob(result.outputDataUrl),
      ]).then(function (blobs) {
        var payload = new FormData(pricingForm);
        payload.delete("installation_plan_background");
        payload.delete("installation_plan_output");
        if (blobs[0]) payload.append("installation_plan_background", blobs[0], "floor-plan.png");
        if (blobs[1]) payload.append("installation_plan_output", blobs[1], "camera-installation-plan.png");
        return fetch(pricingForm.action, {
          method: "POST",
          body: payload,
          credentials: "same-origin",
          headers: {
            "Accept": "application/json",
            "X-Requested-With": "camera-planner",
          },
        });
      }).then(function (response) {
        return response.json().then(function (payload) {
          return { response: response, payload: payload };
        });
      }).then(function (result) {
        if (result.response.ok && result.payload.redirect) {
          window.location.assign(result.payload.redirect);
          return;
        }
        if (result.payload.form_token) {
          var token = pricingForm.querySelector('input[name="form_token"]');
          if (token) token.value = result.payload.form_token;
        }
        renderQuotationErrors(result.payload.errors);
        setQuotationSubmitting(false);
      }).catch(function (error) {
        console.error(error);
        showPlannerSubmitError("The quotation could not be sent. Check the application connection and try again.");
        setQuotationSubmitting(false);
      });
    }

    if (plannerFrame) {
      window.addEventListener("message", function (event) {
        if (event.origin !== window.location.origin || event.source !== plannerFrame.contentWindow || !event.data) return;
        if (event.data.type === "quotation-planner:ready") {
          plannerReady = true;
          plannerFrame.contentWindow.postMessage({
            type: "quotation-planner:init",
            design: plannerInitial.state,
            backgroundUrl: plannerInitial.background_url,
          }, window.location.origin);
          return;
        }
        if (event.data.requestId !== plannerRequestId) return;
        if (event.data.type === "quotation-planner:error") {
          showPlannerSubmitError(event.data.message || "The camera plan could not be prepared.");
          setQuotationSubmitting(false);
          return;
        }
        if (event.data.type === "quotation-planner:result") {
          submitQuotationWithPlan(event.data);
        }
      });

      pricingForm.addEventListener("submit", function (event) {
        if (plannerSubmitting) {
          event.preventDefault();
          return;
        }
        event.preventDefault();
        showPlannerSubmitError("");
        if (!plannerReady) {
          showPlannerSubmitError("The camera planner is still loading. Wait a moment and try again.");
          return;
        }
        setQuotationSubmitting(true);
        plannerRequestId = String(Date.now()) + Math.random().toString(36).slice(2);
        plannerFrame.contentWindow.postMessage({
          type: "quotation-planner:export",
          requestId: plannerRequestId,
        }, window.location.origin);
      });
    }
  }

  /* ------------------------------------------------------ dialog toggles */
  document.querySelectorAll("[data-toggle-target]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var target = document.getElementById(btn.dataset.toggleTarget);
      if (!target) return;
      var open = target.hasAttribute("hidden");
      if (open) { target.removeAttribute("hidden"); } else { target.setAttribute("hidden", ""); }
      btn.setAttribute("aria-expanded", String(open));
      if (open) { var f = target.querySelector("input, textarea, select"); if (f) f.focus(); }
    });
  });

  /* --------------------------------------------------- searchable select */
  document.querySelectorAll("[data-combo]").forEach(function (root) {
    var input = root.querySelector(".combo-input");
    var list = root.querySelector(".combo-list");
    var hidden = root.querySelector("input[type=hidden]");
    var options = Array.prototype.slice.call(list.querySelectorAll(".combo-option"));
    var cursor = -1;

    function visible() {
      return options.filter(function (o) { return o.style.display !== "none"; });
    }
    function open() { list.removeAttribute("hidden"); input.setAttribute("aria-expanded", "true"); }
    function close() {
      list.setAttribute("hidden", "");
      input.setAttribute("aria-expanded", "false");
      cursor = -1;
      options.forEach(function (o) { o.setAttribute("aria-selected", "false"); });
      // Snap the text back to the committed choice.
      var chosen = options.filter(function (o) { return o.dataset.value === hidden.value; })[0];
      input.value = chosen ? chosen.dataset.label : "";
    }
    function filter(term) {
      var t = term.trim().toLowerCase();
      var shown = 0;
      options.forEach(function (o) {
        var match = !t || o.dataset.search.indexOf(t) !== -1;
        var customerField = document.querySelector("[data-customer-select]");
        if (o.dataset.customer && customerField && customerField.value) {
          match = match && o.dataset.customer === customerField.value;
        }
        var siteField = document.querySelector("[data-site-combo] input[type=hidden]");
        if (o.dataset.site && siteField && siteField.value) {
          match = match && o.dataset.site === siteField.value;
        }
        o.style.display = match ? "" : "none";
        if (match) shown++;
      });
      var empty = list.querySelector(".combo-empty");
      if (empty) empty.style.display = shown ? "none" : "";
    }
    function choose(option) {
      hidden.value = option.dataset.value;
      input.value = option.dataset.label;
      close();
      hidden.dispatchEvent(new Event("change", { bubbles: true }));
    }
    function move(step) {
      var vis = visible();
      if (!vis.length) return;
      cursor = (cursor + step + vis.length) % vis.length;
      vis.forEach(function (o, i) { o.setAttribute("aria-selected", String(i === cursor)); });
      vis[cursor].scrollIntoView({ block: "nearest" });
    }

    input.addEventListener("focus", function () { filter(""); open(); });
    input.addEventListener("input", function () { hidden.value = ""; filter(input.value); open(); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); open(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); open(); move(-1); }
      else if (e.key === "Enter") {
        var vis = visible();
        if (!list.hasAttribute("hidden") && cursor >= 0 && vis[cursor]) { e.preventDefault(); choose(vis[cursor]); }
      } else if (e.key === "Escape") { close(); }
    });
    options.forEach(function (o) {
      o.addEventListener("mousedown", function (e) { e.preventDefault(); choose(o); });
    });
    document.addEventListener("click", function (e) { if (!root.contains(e.target)) close(); });
  });

  /* ------------------------------------------ selected site information */
  var siteCombo = document.querySelector("[data-site-combo]");
  var siteDetails = document.querySelector("[data-site-details]");
  if (siteCombo && siteDetails) {
    var siteValue = siteCombo.querySelector('input[type="hidden"]');
    var customerSelect = document.querySelector("[data-customer-select]");
    function syncSiteDetails() {
      var option = siteCombo.querySelector(
        '.combo-option[data-value="' + siteValue.value + '"]'
      );
      if (!option) {
        siteDetails.setAttribute("hidden", "");
        return;
      }
      var location = option.dataset.address || "";
      if (option.dataset.city) location += (location ? " · " : "") + option.dataset.city;
      var contact = option.dataset.contact || "";
      if (option.dataset.phone) contact += (contact ? " · " : "") + option.dataset.phone;
      siteDetails.querySelector("[data-site-address]").textContent =
        location || "No address recorded.";
      siteDetails.querySelector("[data-site-contact]").textContent = contact
        ? "Contact: " + contact
        : "No site contact recorded.";
      siteDetails.removeAttribute("hidden");
    }
    siteValue.addEventListener("change", syncSiteDetails);
    if (customerSelect) {
      customerSelect.addEventListener("change", function () {
        var chosen = siteCombo.querySelector(
          '.combo-option[data-value="' + siteValue.value + '"]'
        );
        if (chosen && chosen.dataset.customer !== customerSelect.value) {
          siteValue.value = "";
          siteCombo.querySelector(".combo-input").value = "";
          siteValue.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
    }
    syncSiteDetails();
  }
  if (siteCombo) {
    var dependentSiteValue = siteCombo.querySelector('input[type="hidden"]');
    var dependentCustomer = document.querySelector("[data-customer-select]");
    var installedDeviceField = document.querySelector('input[name="installed_device_id"]');
    function clearDependentDevice() {
      if (!installedDeviceField || !installedDeviceField.value) return;
      var selectedDevice = document.querySelector(
        '.combo-option[data-value="' + installedDeviceField.value + '"][data-site]'
      );
      if (
        selectedDevice &&
        selectedDevice.dataset.site !== dependentSiteValue.value
      ) {
        installedDeviceField.value = "";
        var deviceInput = installedDeviceField.closest(".combo").querySelector(".combo-input");
        if (deviceInput) deviceInput.value = "";
      }
    }
    if (dependentCustomer) {
      dependentCustomer.addEventListener("change", function () {
        var selectedSite = siteCombo.querySelector(
          '.combo-option[data-value="' + dependentSiteValue.value + '"]'
        );
        if (selectedSite && selectedSite.dataset.customer !== dependentCustomer.value) {
          dependentSiteValue.value = "";
          siteCombo.querySelector(".combo-input").value = "";
          dependentSiteValue.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
    }
    dependentSiteValue.addEventListener("change", clearDependentDevice);
    clearDependentDevice();
  }

  /* -------------------------------------------------------- photo input */
  window.initializePhotoPicker = function (photoRoot) {
    if (!photoRoot || photoRoot.dataset.photoReady === "true") return;
    photoRoot.dataset.photoReady = "true";
    var selected = [];
    var fileInput = photoRoot.querySelector("input[type=file]");
    var grid = photoRoot.querySelector(".preview-grid");
    var zone = photoRoot.querySelector(".dropzone");
    var counter = photoRoot.querySelector("[data-photo-count]");
    var maxBytes = parseInt(photoRoot.dataset.maxBytes, 10);
    var maxFiles = parseInt(photoRoot.dataset.maxFiles, 10);
    var allowed = ["image/jpeg", "image/png", "image/webp"];
    var errorBox = photoRoot.querySelector("[data-photo-error]");

    function showError(msg) {
      errorBox.textContent = msg || "";
      errorBox.style.display = msg ? "" : "none";
    }
    function refresh() {
      grid.innerHTML = "";
      selected.forEach(function (file, index) {
        var cell = document.createElement("div");
        cell.className = "preview";
        var img = document.createElement("img");
        img.alt = file.name;
        img.src = URL.createObjectURL(file);
        img.addEventListener("load", function () { URL.revokeObjectURL(img.src); });
        var name = document.createElement("span");
        name.className = "name";
        name.textContent = file.name;
        var kill = document.createElement("button");
        kill.type = "button"; kill.className = "remove"; kill.innerHTML = "&times;";
        kill.setAttribute("aria-label", "Remove " + file.name);
        kill.addEventListener("click", function () {
          selected.splice(index, 1);
          refresh();
        });
        cell.append(img, name, kill);
        grid.appendChild(cell);
      });
      if (counter) {
        counter.textContent = selected.length
          ? selected.length + (selected.length === 1 ? " photo ready" : " photos ready")
          : "No photos yet";
      }
      syncInput();
    }
    function syncInput() {
      var dt = new DataTransfer();
      selected.forEach(function (f) { dt.items.add(f); });
      fileInput.files = dt.files;
    }
    function accept(files) {
      showError("");
      Array.prototype.forEach.call(files, function (file) {
        if (selected.length >= maxFiles) { showError("You can attach up to " + maxFiles + " photos."); return; }
        if (allowed.indexOf(file.type) === -1) { showError("“" + file.name + "” is not a JPEG, PNG or WebP file."); return; }
        if (file.size > maxBytes) {
          showError("“" + file.name + "” is larger than the " + (maxBytes / 1048576).toFixed(0) + " MB limit.");
          return;
        }
        selected.push(file);
      });
      refresh();
    }

    // Two inputs (camera + gallery) feed one list; only the primary one is submitted.
    photoRoot.querySelectorAll("input[type=file]").forEach(function (input) {
      input.addEventListener("change", function (e) {
        if (e.target !== fileInput) {
          accept(e.target.files);
          e.target.value = "";
        } else {
          accept(e.target.files);
        }
      });
    });
    photoRoot.querySelectorAll("[data-pick]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = photoRoot.querySelector("#" + btn.dataset.pick);
        if (target) target.click();
      });
    });
    ["dragenter", "dragover"].forEach(function (evt) {
      zone.addEventListener(evt, function (e) { e.preventDefault(); zone.classList.add("dragging"); });
    });
    ["dragleave", "drop"].forEach(function (evt) {
      zone.addEventListener(evt, function (e) { e.preventDefault(); zone.classList.remove("dragging"); });
    });
    zone.addEventListener("drop", function (e) {
      if (e.dataTransfer && e.dataTransfer.files) accept(e.dataTransfer.files);
    });
  };
  document.querySelectorAll("[data-photos]").forEach(window.initializePhotoPicker);

  /* ------------------------------------ submit with progress + duplicate lock */
  var submitForm = document.querySelector("[data-async-form]");
  if (submitForm && window.XMLHttpRequest && window.FormData) {
    var submitBtn = submitForm.querySelector("[data-submit]");
    var progress = submitForm.querySelector(".progress");
    var bar = progress ? progress.querySelector("span") : null;
    var busy = false;
    var dirtyGuardOff = false;
    var submitLabel = submitBtn.dataset.label || submitBtn.textContent;
    var savingLabel = submitBtn.dataset.savingLabel || "Saving record…";

    submitForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (busy) return;
      busy = true;
      dirtyGuardOff = true;
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="spinner" aria-hidden="true"></span> ' + savingLabel;
      if (progress) { progress.removeAttribute("hidden"); bar.style.width = "0%"; }

      var xhr = new XMLHttpRequest();
      xhr.open("POST", submitForm.action, true);
      xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
      xhr.upload.addEventListener("progress", function (evt) {
        if (evt.lengthComputable && bar) bar.style.width = (evt.loaded / evt.total * 100).toFixed(0) + "%";
      });
      xhr.addEventListener("load", function () {
        var data = {};
        try { data = JSON.parse(xhr.responseText); } catch (err) { data = {}; }
        if (xhr.status >= 200 && xhr.status < 300 && data.redirect) {
          if (bar) bar.style.width = "100%";
          window.location.assign(data.redirect);
          return;
        }
        busy = false;
        dirtyGuardOff = false;
        submitBtn.disabled = false;
        submitBtn.textContent = submitLabel;
        if (progress) progress.setAttribute("hidden", "");
        renderErrors(data.errors || { form: "The record could not be saved. Try again." }, data.form_token);
      });
      xhr.addEventListener("error", function () {
        busy = false; dirtyGuardOff = false;
        submitBtn.disabled = false;
        submitBtn.textContent = submitLabel;
        if (progress) progress.setAttribute("hidden", "");
        renderErrors({ form: "The connection dropped before the record was saved. Try again." });
      });
      xhr.send(new FormData(submitForm));
    });

    function renderErrors(errors, freshToken) {
      if (freshToken) {
        var tokenField = submitForm.querySelector('input[name=form_token]');
        if (tokenField) tokenField.value = freshToken;
      }
      submitForm.querySelectorAll("[data-error-for]").forEach(function (slot) {
        var key = slot.dataset.errorFor;
        slot.textContent = errors[key] || "";
        slot.style.display = errors[key] ? "" : "none";
        var field = submitForm.querySelector('[name="' + key + '"]');
        if (field) field.setAttribute("aria-invalid", errors[key] ? "true" : "false");
      });
      var top = submitForm.querySelector("[data-form-error]") ||
        document.querySelector("[data-form-error]");
      if (top) {
        top.textContent = errors.form || "";
        top.style.display = errors.form ? "" : "none";
      }
      var first = submitForm.querySelector('[data-error-for]:not([style*="display: none"])');
      (first || submitForm).scrollIntoView({ behavior: "smooth", block: "center" });
    }

    /* unsaved-changes guard */
    var touched = false;
    submitForm.addEventListener("input", function () { touched = true; });
    submitForm.addEventListener("change", function () { touched = true; });
    window.addEventListener("beforeunload", function (e) {
      if (touched && !dirtyGuardOff) { e.preventDefault(); e.returnValue = ""; }
    });
  }

  /* ------------------------------------------ quotation invoice uploads */
  document.querySelectorAll("[data-image-upload-queue], [data-invoice-upload-queue]").forEach(function (form) {
    var input = form.querySelector("[data-image-file-input], [data-invoice-file-input]");
    var queue = form.querySelector("[data-image-file-queue], [data-invoice-file-queue]");
    var list = form.querySelector("[data-image-file-list], [data-invoice-file-list]");
    var count = form.querySelector("[data-image-file-count], [data-invoice-file-count]");
    var submit = form.querySelector("[data-image-upload-submit], [data-invoice-upload-submit]");
    var reminder = form.querySelector("[data-image-upload-reminder], [data-invoice-upload-reminder]");
    if (!input || !queue || !list || !count || typeof window.DataTransfer !== "function") return;

    var selectedFiles = [];
    var previewUrls = [];
    if (submit) submit.disabled = true;

    function fileKey(file) {
      return [file.name, file.size, file.lastModified, file.type].join("::");
    }

    function replaceInputFiles() {
      var transfer = new DataTransfer();
      selectedFiles.forEach(function (file) { transfer.items.add(file); });
      input.files = transfer.files;
    }

    function readableSize(bytes) {
      if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + " KB";
      return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    }

    function renderQueue() {
      previewUrls.forEach(function (url) { URL.revokeObjectURL(url); });
      previewUrls = [];
      list.innerHTML = "";
      queue.hidden = selectedFiles.length === 0;
      if (submit) submit.disabled = selectedFiles.length === 0;
      if (reminder) reminder.hidden = selectedFiles.length === 0;
      count.textContent = (form.dataset.selectedTemplate || "__COUNT__ selected").replace("__COUNT__", String(selectedFiles.length));

      selectedFiles.forEach(function (file, index) {
        var row = document.createElement("div");
        row.className = "invoice-upload-selection-item";
        var image = document.createElement("img");
        var previewUrl = URL.createObjectURL(file);
        previewUrls.push(previewUrl);
        image.src = previewUrl;
        image.alt = "";

        var details = document.createElement("div");
        var name = document.createElement("strong");
        name.textContent = file.name;
        var size = document.createElement("span");
        size.className = "hint";
        size.textContent = readableSize(file.size);
        details.appendChild(name);
        details.appendChild(size);

        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "btn btn-quiet btn-sm";
        remove.textContent = form.dataset.removeLabel || "Remove";
        remove.addEventListener("click", function () {
          selectedFiles.splice(index, 1);
          replaceInputFiles();
          renderQueue();
        });
        row.appendChild(image);
        row.appendChild(details);
        row.appendChild(remove);
        list.appendChild(row);
      });
    }

    input.addEventListener("change", function () {
      var known = {};
      selectedFiles.forEach(function (file) { known[fileKey(file)] = true; });
      Array.prototype.slice.call(input.files || []).forEach(function (file) {
        var key = fileKey(file);
        if (!known[key]) { selectedFiles.push(file); known[key] = true; }
      });
      replaceInputFiles();
      renderQueue();
    });

    window.addEventListener("beforeunload", function () {
      previewUrls.forEach(function (url) { URL.revokeObjectURL(url); });
    });
  });

  /* ------------------------------------------------------------ lightbox */
  var lightbox = document.querySelector("[data-lightbox]");
  if (lightbox) {
    var stageImg = lightbox.querySelector("img");
    var caption = lightbox.querySelector("[data-lb-caption]");
    var thumbs = Array.prototype.slice.call(document.querySelectorAll("[data-lb-open]"));
    var at = 0;
    var lastFocus = null;

    function show(i) {
      at = (i + thumbs.length) % thumbs.length;
      var src = thumbs[at].dataset.full;
      stageImg.src = src;
      stageImg.alt = thumbs[at].dataset.caption || "Proof photo";
      caption.textContent = (at + 1) + " of " + thumbs.length + " · " + (thumbs[at].dataset.caption || "");
    }
    function open(i) {
      lastFocus = document.activeElement;
      lightbox.removeAttribute("hidden");
      document.body.style.overflow = "hidden";
      show(i);
      lightbox.querySelector("[data-lb-close]").focus();
    }
    function close() {
      lightbox.setAttribute("hidden", "");
      document.body.style.overflow = "";
      if (lastFocus) lastFocus.focus();
    }
    thumbs.forEach(function (t, i) { t.addEventListener("click", function () { open(i); }); });
    lightbox.querySelector("[data-lb-close]").addEventListener("click", close);
    var prev = lightbox.querySelector("[data-lb-prev]");
    var next = lightbox.querySelector("[data-lb-next]");
    if (prev) prev.addEventListener("click", function () { show(at - 1); });
    if (next) next.addEventListener("click", function () { show(at + 1); });
    document.addEventListener("keydown", function (e) {
      if (lightbox.hasAttribute("hidden")) return;
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight") show(at + 1);
      if (e.key === "ArrowLeft") show(at - 1);
    });
  }
})();
