/* Progressive enhancement only — every form still works without this file,
   except the upload progress bar. */
(function () {
  "use strict";

  /* --------------------------------------- Main Project / Sub Project / Site */
  document.querySelectorAll("[data-project-hierarchy]").forEach(function (form) {
    var dataNode = form.querySelector("[data-project-hierarchy-data]");
    if (!dataNode) return;
    var hierarchy;
    try { hierarchy = JSON.parse(dataNode.textContent); } catch (_) { return; }
    function initializeScope(scope) {
      if (scope.dataset.hierarchyInitialized === "true") return;
      var projectSelect = scope.querySelector("select[name=project_id]");
      var subSelect = scope.querySelector("select[name=sub_project_id]");
      var siteSelect = scope.querySelector("select[name=work_site_id]");
      if (!projectSelect || !subSelect || !siteSelect) return;
      scope.dataset.hierarchyInitialized = "true";
      var subOptions = Array.prototype.slice.call(subSelect.options, 1);
      var siteOptions = Array.prototype.slice.call(siteSelect.options, 1);
      function selectedProject() {
        return hierarchy.find(function (entry) { return String(entry.project_id) === projectSelect.value; });
      }
      function refreshSites(clearInvalid) {
        var project = selectedProject();
        var subProject = project && project.sub_projects.find(function (item) { return String(item.id) === subSelect.value; });
        var allowed = (subProject ? subProject.site_ids : []).map(String);
        siteOptions.forEach(function (option) { option.hidden = allowed.indexOf(option.value) === -1; option.disabled = option.hidden; });
        if (clearInvalid && allowed.indexOf(siteSelect.value) === -1) siteSelect.value = "";
        scope.dispatchEvent(new CustomEvent("scopechange", { bubbles: true }));
      }
      function refreshSubProjects(clearInvalid) {
        var project = selectedProject();
        var allowed = (project ? project.sub_projects : []).map(function (item) { return String(item.id); });
        subOptions.forEach(function (option) { option.hidden = allowed.indexOf(option.value) === -1; option.disabled = option.hidden; });
        if (clearInvalid && allowed.indexOf(subSelect.value) === -1) subSelect.value = "";
        refreshSites(clearInvalid);
      }
      projectSelect.addEventListener("change", function () { refreshSubProjects(true); });
      subSelect.addEventListener("change", function () { refreshSites(true); });
      siteSelect.addEventListener("change", function () { scope.dispatchEvent(new CustomEvent("scopechange", { bubbles: true })); });
      refreshSubProjects(false);
    }
    window.initializeProjectScope = initializeScope;
    var initialScopes = form.querySelectorAll("[data-site-scope]");
    (initialScopes.length ? initialScopes : [form]).forEach(initializeScope);

    var scopesRoot = form.querySelector("[data-site-scopes]");
    var addSite = form.querySelector("[data-add-site]");
    var siteTemplate = form.querySelector("[data-site-template]");
    if (!scopesRoot || !addSite) return;
    function optionLabel(scope, index) {
      var names = ["project_id", "sub_project_id", "work_site_id"].map(function (name) {
        var select = scope.querySelector('[name="' + name + '"]');
        return select && select.selectedIndex > 0 ? select.options[select.selectedIndex].text : "";
      }).filter(Boolean);
      return names.length ? names.join(" › ") : "Site " + (index + 1);
    }
    function refreshScopes() {
      var scopes = Array.from(scopesRoot.querySelectorAll("[data-site-scope]"));
      scopes.forEach(function (scope, index) {
        var number = scope.querySelector("[data-site-number]");
        var remove = scope.querySelector("[data-remove-site]");
        if (number) number.textContent = index + 1;
        if (remove) remove.hidden = scopes.length === 1;
      });
      form.querySelectorAll("[data-item-scope-select]").forEach(function (select) {
        var previous = select.value;
        select.replaceChildren();
        scopes.forEach(function (scope, index) {
          var option = document.createElement("option");
          option.value = String(index);
          option.textContent = optionLabel(scope, index);
          select.appendChild(option);
        });
        select.value = previous && Number(previous) < scopes.length ? previous : "0";
      });
    }
    addSite.addEventListener("click", function () {
      var sourceScope = scopesRoot.querySelector("[data-site-scope]");
      var clone = siteTemplate && siteTemplate.content.firstElementChild
        ? siteTemplate.content.firstElementChild.cloneNode(true)
        : sourceScope.cloneNode(true);
      var deviceTemplate = form.querySelector("[data-device-template]");
      var clonedItems = clone.querySelector("[data-device-items]");
      if (deviceTemplate && clonedItems) clonedItems.replaceChildren(deviceTemplate.content.cloneNode(true));
      clone.querySelectorAll("[data-entry-data-table]").forEach(function (table) {
        var body = table.querySelector("[data-entry-data-rows]");
        var rows = Array.from(body.querySelectorAll("[data-entry-data-row]"));
        rows.slice(1).forEach(function (row) { row.remove(); });
        if (rows[0]) clearEntryDataRow(rows[0], table.dataset.tableKind === "maintenance");
      });
      delete clone.dataset.hierarchyInitialized;
      clone.querySelectorAll("[data-entry-device-import]").forEach(function (panel) { delete panel.dataset.importInitialized; });
      clone.removeAttribute("id");
      clone.querySelectorAll("[id]").forEach(function (node) { node.removeAttribute("id"); });
      clone.querySelectorAll("select, input").forEach(function (field) {
        if (field.type === "checkbox" || field.type === "radio") field.checked = false;
        else field.value = "";
      });
      clone.querySelectorAll(".error-text").forEach(function (error) { error.textContent = ""; error.style.display = "none"; });
      clone.querySelectorAll("[data-device-import-body], .preview-grid").forEach(function (node) { node.replaceChildren(); });
      clone.querySelectorAll("[data-device-import-results]").forEach(function (node) { node.hidden = true; });
      scopesRoot.appendChild(clone);
      initializeScope(clone);
      clone.querySelectorAll("[data-entry-device-import]").forEach(window.initializeEntryDeviceImport || function () {});
      if (window.refreshNestedEntryDevices) window.refreshNestedEntryDevices(form);
      refreshScopes();
    });
    scopesRoot.addEventListener("click", function (event) {
      var remove = event.target.closest("[data-remove-site]");
      if (remove && scopesRoot.querySelectorAll("[data-site-scope]").length > 1) {
        if (remove.dataset.confirm && !window.confirm(remove.dataset.confirm)) return;
        remove.closest("[data-site-scope]").remove();
        refreshScopes();
      }
    });
    scopesRoot.addEventListener("scopechange", refreshScopes);
    form.addEventListener("deviceitemschange", refreshScopes);
    scopesRoot.querySelectorAll("[data-device-items]").forEach(function (itemRoot) {
      new MutationObserver(refreshScopes).observe(itemRoot, { childList: true });
    });
    refreshScopes();
  });

  /* ------------------------------------------------ Excel device entry import */
  function initializeEntryDeviceImport(panel) {
    if (panel.dataset.importInitialized === "true") return;
    panel.dataset.importInitialized = "true";
    var form = panel.closest("form");
    var scope = panel.closest("[data-site-scope]") || form;
    var kind = panel.dataset.entryKind;
    var fileInput = panel.querySelector("[data-device-import-file]");
    var previewButton = panel.querySelector("[data-device-import-preview]");
    var tokenInput = panel.querySelector("[data-device-import-token]");
    var errorsBox = panel.querySelector("[data-device-import-errors]");
    var results = panel.querySelector("[data-device-import-results]");
    var body = panel.querySelector("[data-device-import-body]");
    var count = panel.querySelector("[data-device-import-count]");
    var conflicts = panel.querySelector("[data-device-import-conflicts]");
    var overwrite = conflicts.querySelector("input[name=confirm_asset_overwrites]");

    function clearPreview() {
      tokenInput.value = "";
      body.replaceChildren();
      results.hidden = true;
      conflicts.hidden = true;
      overwrite.checked = false;
    }
    function showErrors(messages) {
      errorsBox.replaceChildren();
      (messages || []).forEach(function (message) {
        var line = document.createElement("div");
        line.textContent = message;
        errorsBox.appendChild(line);
      });
      errorsBox.hidden = !messages || messages.length === 0;
    }
    function addCell(row, value, className) {
      var cell = document.createElement("td");
      cell.textContent = value || "—";
      if (className) cell.className = className;
      row.appendChild(cell);
    }
    function applyRows(rows) {
      var itemsRoot = scope.querySelector("[data-device-items]");
      var addButton = scope.querySelector("[data-add-device]");
      if (!itemsRoot || !addButton) return;
      function assigned() {
        return Array.from(itemsRoot.querySelectorAll("[data-device-row]"));
      }
      while (assigned().length < rows.length) {
        addButton.click();
      }
      while (assigned().length > rows.length) {
        var scopedRows = assigned();
        scopedRows[scopedRows.length - 1].querySelector("[data-remove-device]").click();
      }
      assigned().forEach(function (itemRow, index) {
        var imported = rows[index];
        if (!imported) return;
        var itemSelect = itemRow.querySelector('[name="device_id"], [name="installed_device_id"]');
        if (itemSelect) {
          var value = kind === "installation" ? String(imported.pricing_item_id) : "catalog:" + imported.pricing_item_id;
          itemSelect.value = value;
          itemSelect.dispatchEvent(new Event("change", { bubbles: true }));
        }
        var serial = itemRow.querySelector('[name="serial_number"]');
        if (serial) serial.value = imported.serial_number || "";
      });
    }
    function renderRows(rows) {
      body.replaceChildren();
      rows.forEach(function (item) {
        var row = document.createElement("tr");
        addCell(row, item.item_name);
        addCell(row, item.model);
        addCell(row, item.serial_number, "mono");
        addCell(row, item.imei, "mono");
        addCell(row, item.iccid, "mono");
        addCell(row, item.sim_type ? item.sim_type.toUpperCase() : "");
        addCell(row, item.main_project);
        addCell(row, item.sub_project);
        addCell(row, item.site);
        addCell(row, item.remarks);
        addCell(row, item.status, item.status === "Valid" ? "status-valid" : "status-invalid");
        body.appendChild(row);
      });
      count.textContent = rows.length;
      results.hidden = false;
    }

    previewButton.addEventListener("click", async function () {
      clearPreview();
      showErrors([]);
      if (!fileInput.files.length) { showErrors([panel.dataset.fileRequired]); return; }
      var data = new FormData();
      ["csrf_token", "project_id", "sub_project_id", "work_site_id"].forEach(function (name) {
        var field = name === "csrf_token" ? form.querySelector('[name="csrf_token"]') : scope.querySelector('[name="' + name + '"]');
        data.append(name, field ? field.value : "");
      });
      data.append("device_file", fileInput.files[0]);
      previewButton.disabled = true;
      try {
        var response = await fetch("/data-entry/" + kind + "/device-import-preview", {
          method: "POST",
          body: data,
          headers: { "X-Requested-With": "XMLHttpRequest" }
        });
        var payload = await response.json();
        renderRows(payload.rows || []);
        showErrors(payload.errors || []);
        if (payload.ok) {
          tokenInput.value = payload.token;
          conflicts.hidden = !payload.has_asset_conflicts;
          applyRows(payload.rows || []);
        }
      } catch (_) {
        showErrors([panel.dataset.previewFailed]);
      } finally {
        previewButton.disabled = false;
      }
    });
    fileInput.addEventListener("change", clearPreview);
    ["project_id", "sub_project_id", "work_site_id"].forEach(function (name) {
      var field = scope.querySelector('[name="' + name + '"]');
      if (field) field.addEventListener("change", function () { if (tokenInput.value) clearPreview(); });
    });
  }
  window.initializeEntryDeviceImport = initializeEntryDeviceImport;
  document.querySelectorAll("[data-entry-device-import]").forEach(initializeEntryDeviceImport);

  document.querySelectorAll("[data-price-chart]").forEach(function (chart) {
    var markers = Array.from(chart.querySelectorAll("[data-price-point]"));
    var values = markers.length
      ? markers.map(function (marker) { return Number(marker.dataset.value); })
      : String(chart.dataset.values || "").split(",").map(Number).filter(Number.isFinite);
    var line = chart.querySelector("polyline");
    if (!line || !values.length) return;
    var minimum = Math.min.apply(Math, values), maximum = Math.max.apply(Math, values);
    var span = maximum - minimum || 1;
    var points = values.map(function (value, index) {
      var x = values.length === 1 ? 160 : 10 + index * 300 / (values.length - 1);
      var y = 78 - (value - minimum) * 66 / span;
      return x.toFixed(1) + "," + y.toFixed(1);
    });
    if (values.length === 1) points = ["10," + points[0].split(",")[1], "310," + points[0].split(",")[1]];
    line.setAttribute("points", points.join(" "));
    if (!markers.length) return;

    var svg = chart.querySelector("svg");
    var tooltip = document.createElement("div");
    tooltip.className = "price-chart-tooltip";
    tooltip.hidden = true;
    chart.appendChild(tooltip);
    markers.forEach(function (marker, index) {
      var coordinates = (values.length === 1 ? "160," + points[0].split(",")[1] : points[index]).split(",");
      var x = Number(coordinates[0]), y = Number(coordinates[1]);
      var point = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      point.setAttribute("cx", x);
      point.setAttribute("cy", y);
      point.setAttribute("r", "7");
      point.setAttribute("class", "price-chart-point");
      point.setAttribute("tabindex", "0");
      point.setAttribute("role", "button");
      var detail = [marker.dataset.price, marker.dataset.date, marker.dataset.context].filter(Boolean);
      point.setAttribute("aria-label", detail.join(" · "));
      svg.appendChild(point);

      function showTooltip() {
        tooltip.replaceChildren();
        var price = document.createElement("strong");
        price.textContent = marker.dataset.price || marker.dataset.value;
        tooltip.appendChild(price);
        [marker.dataset.date, marker.dataset.context].filter(Boolean).forEach(function (text) {
          var row = document.createElement("span");
          row.textContent = text;
          tooltip.appendChild(row);
        });
        tooltip.style.left = (x / 320 * 100) + "%";
        tooltip.style.top = (y / 90 * 100) + "%";
        tooltip.hidden = false;
        point.classList.add("is-active");
      }
      function hideTooltip() {
        tooltip.hidden = true;
        point.classList.remove("is-active");
      }
      point.addEventListener("mouseenter", showTooltip);
      point.addEventListener("mouseleave", hideTooltip);
      point.addEventListener("focus", showTooltip);
      point.addEventListener("blur", hideTooltip);
      point.addEventListener("click", showTooltip);
    });
  });

  document.querySelectorAll("[data-pricing-quotation-form]").forEach(function (form) {
    var project = form.querySelector('[name="project_id"]');
    var addressee = form.querySelector("[data-quotation-addressee]");
    var custom = form.querySelector("[data-custom-addressee]");
    if (!project || !addressee || !custom) return;
    function refreshAddressees(clearInvalid) {
      Array.from(addressee.options).forEach(function (option) {
        if (!option.dataset.projectId) return;
        option.hidden = option.dataset.projectId !== project.value;
        option.disabled = option.hidden;
      });
      if (clearInvalid && addressee.selectedOptions[0] && addressee.selectedOptions[0].disabled) addressee.value = "none";
      custom.hidden = addressee.value !== "custom";
    }
    project.addEventListener("change", function () { refreshAddressees(true); });
    addressee.addEventListener("change", function () { refreshAddressees(false); });
    refreshAddressees(false);
  });

  /* ------------------------------------------ Nested site/device entry forms */
  function clearEntryDataRow(row, maintenance) {
    row.dataset.autofilled = "";
    row.querySelectorAll("input, select").forEach(function (field) {
      // Creation rows are re-numbered by refreshEntryDataTables. Existing edit
      // rows must retain their immutable saved Site position when cloned.
      if (field.hasAttribute("data-entry-data-scope") || field.hasAttribute("data-existing-data-scope")) return;
      if (maintenance && (field.name === "data_quantity" || field.name === "existing_data_quantity")) field.value = "1";
      else field.value = "";
    });
  }
  function addEntryDataRow(table) {
    var body = table.querySelector("[data-entry-data-rows]");
    var source = body && body.querySelector("[data-entry-data-row]");
    if (!body || !source) return null;
    var clone = source.cloneNode(true);
    clearEntryDataRow(clone, table.dataset.tableKind === "maintenance");
    body.appendChild(clone);
    return clone;
  }
  function refreshEntryDataTables(form) {
    form.querySelectorAll("[data-site-scope]").forEach(function (scope, scopeIndex) {
      var project = scope.querySelector('[name="project_id"]');
      var subProject = scope.querySelector('[name="sub_project_id"]');
      var site = scope.querySelector('[name="work_site_id"]');
      var selectedText = function (select) {
        var option = select && select.selectedOptions && select.selectedOptions[0];
        return option && option.value ? option.textContent.trim() : "-";
      };
      scope.querySelectorAll("[data-entry-data-table]").forEach(function (table) {
        var rows = Array.from(table.querySelectorAll("[data-entry-data-row]"));
        rows.forEach(function (row, rowIndex) {
          var number = row.querySelector("[data-entry-data-number]");
          var scopeInput = row.querySelector("[data-entry-data-scope]");
          var remove = row.querySelector("[data-remove-data-row]");
          if (number) number.textContent = rowIndex + 1;
          if (scopeInput) scopeInput.value = String(scopeIndex);
          if (remove) remove.hidden = rows.length === 1;
          var mainLabel = row.querySelector("[data-entry-main-project]");
          var subLabel = row.querySelector("[data-entry-sub-project]");
          var siteLabel = row.querySelector("[data-entry-site]");
          if (mainLabel) mainLabel.textContent = selectedText(project);
          if (subLabel) subLabel.textContent = selectedText(subProject);
          if (siteLabel) siteLabel.textContent = selectedText(site);
        });
      });
    });
  }
  function syncInstallationDataRow(select) {
    var scope = select.closest("[data-site-scope]");
    var table = scope && scope.querySelector('[data-entry-data-table][data-table-kind="installation"]');
    if (!table) return;
    var deviceRows = Array.from(scope.querySelectorAll("[data-device-row]"));
    var deviceIndex = deviceRows.indexOf(select.closest("[data-device-row]"));
    var dataRows = Array.from(table.querySelectorAll("[data-entry-data-row]"));
    while (dataRows.length <= deviceIndex) {
      addEntryDataRow(table);
      dataRows = Array.from(table.querySelectorAll("[data-entry-data-row]"));
    }
    var row = dataRows[deviceIndex];
    var itemInput = row.querySelector('[name="data_item_name"], [name="existing_data_item_name"]');
    var modelInput = row.querySelector('[name="data_model"], [name="existing_data_model"]');
    var option = select.selectedOptions[0];
    if (!option || !option.value) return;
    if (!itemInput.value || row.dataset.autofilled === "true") itemInput.value = option.dataset.itemName || option.textContent.trim();
    if (!modelInput.value || row.dataset.autofilled === "true") modelInput.value = option.dataset.itemModel || "";
    row.dataset.autofilled = "true";
    refreshEntryDataTables(form);
  }
  function refreshNestedEntryDevices(form) {
    var prefix = form.dataset.photoPrefix || "entry";
    var globalIndex = 0;
    form.querySelectorAll("[data-site-scope]").forEach(function (scope, scopeIndex) {
      var rows = Array.from(scope.querySelectorAll("[data-device-row]"));
      rows.forEach(function (row, localIndex) {
        var number = row.querySelector("[data-item-number]");
        var remove = row.querySelector("[data-remove-device]");
        var scopeInput = row.querySelector("[data-item-scope-index]");
        if (number) number.textContent = localIndex + 1;
        if (remove) remove.hidden = rows.length === 1 && !scope.matches("[data-existing-site]");
        if (scopeInput) scopeInput.value = String(scopeIndex);
        row.querySelectorAll("[data-name-kind]").forEach(function (field) {
          field.name = field.dataset.nameKind + "_" + globalIndex;
        });
        row.querySelectorAll("[data-description-kind]").forEach(function (root) {
          root.dataset.descriptionName = root.dataset.descriptionKind + "_" + globalIndex;
        });
        row.querySelectorAll("[data-issue-kind]").forEach(function (root) {
          root.dataset.issueName = root.dataset.issueKind + "_" + globalIndex;
        });
        row.querySelectorAll("[data-photo-kind]").forEach(function (input) {
          input.id = prefix + "-" + input.dataset.photoKind + "-" + globalIndex;
        });
        row.querySelectorAll("[data-pick-kind]").forEach(function (button) {
          button.dataset.pick = prefix + "-" + button.dataset.pickKind + "-" + globalIndex;
        });
        row.querySelectorAll("[data-error-kind]").forEach(function (error) {
          error.dataset.errorFor = error.dataset.errorKind + "_" + globalIndex;
        });
        row.querySelectorAll("[data-photos]").forEach(window.initializePhotoPicker);
        window.initializeServiceItemPickers(row);
        globalIndex += 1;
      });
      var project = scope.querySelector('[name="project_id"]');
      var site = scope.querySelector('[name="work_site_id"]');
      scope.querySelectorAll("[data-installed-device-select]").forEach(function (select) {
        Array.from(select.options).slice(1).forEach(function (option) {
          option.hidden = option.dataset.catalog !== "true" && Boolean(
            (project && project.value && option.dataset.project !== project.value) ||
            (site && site.value && option.dataset.site !== site.value)
          );
        });
        if (select.selectedOptions[0] && select.selectedOptions[0].hidden) select.value = "";
      });
    });
    refreshEntryDataTables(form);
    if (window.refreshPhotoGuidance) window.refreshPhotoGuidance(form);
    form.dispatchEvent(new CustomEvent("deviceitemschange"));
  }
  function prepareNestedEditSubmission(form) {
    if (!form.matches("[data-record-nested-edit]")) return;
    var activeScopes = Array.from(form.querySelectorAll("[data-site-scope]")).filter(function (scope) {
      return scope.matches("[data-new-site]") || scope.querySelector("[data-device-row]");
    });
    form.querySelectorAll("[data-site-scope]").forEach(function (scope) {
      var activeIndex = activeScopes.indexOf(scope);
      scope.querySelectorAll("[data-addition-scope-field]").forEach(function (field) {
        field.disabled = activeIndex < 0;
      });
      scope.querySelectorAll("[data-device-row] [data-item-scope-index]").forEach(function (field) {
        field.value = String(Math.max(activeIndex, 0));
      });
      scope.querySelectorAll("[data-entry-data-scope]").forEach(function (field) {
        field.value = String(Math.max(activeIndex, 0));
      });
    });
  }
  window.refreshNestedEntryDevices = refreshNestedEntryDevices;
  function initializeNestedEntryForms() {
    document.querySelectorAll("[data-nested-entry-devices]").forEach(function (form) {
      if (form.dataset.nestedEntryInitialized === "true") return;
      form.dataset.nestedEntryInitialized = "true";
      var template = form.querySelector("[data-device-template]");
      form.addEventListener("click", function (event) {
        var removeExisting = event.target.closest("[data-remove-existing-item]");
        if (removeExisting) {
          if (removeExisting.dataset.confirm && !window.confirm(removeExisting.dataset.confirm)) return;
          removeExisting.closest("[data-existing-item]").remove();
          return;
        }
        var addDataRow = event.target.closest("[data-add-data-row]");
        if (addDataRow) {
          addEntryDataRow(addDataRow.closest("[data-entry-data-table]"));
          refreshEntryDataTables(form);
          return;
        }
        var removeDataRow = event.target.closest("[data-remove-data-row]");
        if (removeDataRow) {
          var dataBody = removeDataRow.closest("[data-entry-data-rows]");
          if (dataBody.querySelectorAll("[data-entry-data-row]").length > 1) {
            removeDataRow.closest("[data-entry-data-row]").remove();
          } else {
            clearEntryDataRow(
              removeDataRow.closest("[data-entry-data-row]"),
              removeDataRow.closest("[data-entry-data-table]").dataset.tableKind === "maintenance"
            );
          }
          refreshEntryDataTables(form);
          return;
        }
        var add = event.target.closest("[data-add-device]");
        if (add && template) {
          add.closest("[data-site-scope]").querySelectorAll("[data-addition-scope-field]").forEach(function (field) {
            field.disabled = false;
          });
          add.closest("[data-site-scope]").querySelector("[data-device-items]").appendChild(template.content.cloneNode(true));
          refreshNestedEntryDevices(form);
          return;
        }
        var remove = event.target.closest("[data-remove-device]");
        if (remove) {
          var root = remove.closest("[data-device-items]");
          var scope = remove.closest("[data-site-scope]");
          if (root.querySelectorAll("[data-device-row]").length > 1 || scope.matches("[data-existing-site]")) {
            remove.closest("[data-device-row]").remove();
          }
          refreshNestedEntryDevices(form);
        }
      });
      form.addEventListener("change", function (event) {
        if (event.target.matches('[name="device_id"]')) syncInstallationDataRow(event.target);
      });
      form.addEventListener("scopechange", function () { refreshNestedEntryDevices(form); });
      form.addEventListener("submit", function () {
        prepareNestedEditSubmission(form);
      });
      refreshNestedEntryDevices(form);
    });
  }

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
    var isActive = section.dataset.active === "true";
    var isOpen = isActive;

    function setGroupOpen(open, remember) {
      if (open) {
        document.querySelectorAll("[data-nav-section]").forEach(function (other) {
          if (other === section) return;
          var otherToggle = other.querySelector("[data-nav-group-toggle]");
          var otherPanel = otherToggle && document.getElementById(otherToggle.getAttribute("aria-controls"));
          if (otherToggle && otherPanel) {
            otherToggle.setAttribute("aria-expanded", "false");
            otherPanel.hidden = true;
          }
        });
      }
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

  /* -------------------------------------- Pricing Category folder picker */
  var pricingCategoryPicker = document.querySelector(
    "[data-pricing-category-assignment-picker]"
  );
  if (pricingCategoryPicker) {
    var activePricingCategorySelector = null;
    var pricingCategoryRoot = pricingCategoryPicker.querySelector(
      "[data-pricing-category-root]"
    );
    var pricingCategoryBack = pricingCategoryPicker.querySelector(
      "[data-pricing-category-back]"
    );
    var pricingCategoryTitle = pricingCategoryPicker.querySelector(
      "[data-pricing-category-picker-title]"
    );

    function closePricingCategoryPicker() {
      if (typeof pricingCategoryPicker.close === "function") {
        pricingCategoryPicker.close();
      } else {
        pricingCategoryPicker.removeAttribute("open");
      }
    }

    function showPricingCategoryRoot() {
      if (pricingCategoryRoot) pricingCategoryRoot.hidden = false;
      if (pricingCategoryBack) pricingCategoryBack.hidden = true;
      if (pricingCategoryTitle) {
        pricingCategoryTitle.textContent = pricingCategoryTitle.dataset.rootTitle;
      }
      pricingCategoryPicker.querySelectorAll("[data-pricing-category-panel]").forEach(
        function (panel) { panel.hidden = true; }
      );
    }

    document.querySelectorAll("[data-open-pricing-category-picker]").forEach(
      function (button) {
        button.addEventListener("click", function () {
          activePricingCategorySelector = button.closest(
            "[data-pricing-category-selector]"
          );
          if (!activePricingCategorySelector) return;
          showPricingCategoryRoot();
          if (typeof pricingCategoryPicker.showModal === "function") {
            pricingCategoryPicker.showModal();
          } else {
            pricingCategoryPicker.setAttribute("open", "");
          }
        });
      }
    );

    pricingCategoryPicker.querySelectorAll("[data-open-pricing-category]").forEach(
      function (folder) {
        folder.addEventListener("click", function () {
          var panel = document.getElementById(folder.dataset.openPricingCategory);
          if (!panel) return;
          if (pricingCategoryRoot) pricingCategoryRoot.hidden = true;
          pricingCategoryPicker.querySelectorAll("[data-pricing-category-panel]").forEach(
            function (candidate) { candidate.hidden = candidate !== panel; }
          );
          if (pricingCategoryBack) pricingCategoryBack.hidden = false;
          if (pricingCategoryTitle) {
            pricingCategoryTitle.textContent = folder.dataset.categoryLabel;
          }
        });
      }
    );

    pricingCategoryPicker.querySelectorAll("[data-select-pricing-category]").forEach(
      function (choice) {
        choice.addEventListener("click", function () {
          if (!activePricingCategorySelector) return;
          var input = activePricingCategorySelector.querySelector(
            "[data-pricing-category-value]"
          );
          var label = activePricingCategorySelector.querySelector(
            "[data-pricing-category-label]"
          );
          if (input) {
            input.value = choice.dataset.categoryId || "";
            input.dispatchEvent(new Event("change", { bubbles: true }));
          }
          if (label) label.textContent = choice.dataset.categoryLabel;
          closePricingCategoryPicker();
          var trigger = activePricingCategorySelector.querySelector(
            "[data-open-pricing-category-picker]"
          );
          if (trigger) trigger.focus();
        });
      }
    );

    if (pricingCategoryBack) {
      pricingCategoryBack.addEventListener("click", showPricingCategoryRoot);
    }
    var closePricingCategory = pricingCategoryPicker.querySelector(
      "[data-close-pricing-category-picker]"
    );
    if (closePricingCategory) {
      closePricingCategory.addEventListener("click", closePricingCategoryPicker);
    }
  }

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
    var pricingPickerCategoryList = pricingForm.querySelector("[data-pricing-picker-category-list]");
    var pricingPickerBack = pricingForm.querySelector("[data-pricing-picker-back]");
    var pricingPickerTitle = pricingForm.querySelector("[data-pricing-picker-view-title]");
    var pricingPickerSection = null;
    var pricingPickerParentPanel = null;
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
      }
      showPricingPickerCategories();
      if (typeof pricingItemPicker.showModal === "function") {
        pricingItemPicker.showModal();
      } else {
        pricingItemPicker.setAttribute("open", "");
      }
      if (pricingItemPickerSearch) pricingItemPickerSearch.focus();
    }

    function showPricingPickerCategories() {
      if (pricingPickerCategoryList) pricingPickerCategoryList.hidden = false;
      if (pricingPickerBack) pricingPickerBack.hidden = true;
      if (pricingPickerTitle) pricingPickerTitle.textContent = pricingPickerTitle.dataset.defaultTitle;
      pricingPickerParentPanel = null;
      pricingItemPicker.querySelectorAll("[data-pricing-picker-category-panel]").forEach(function (panel) {
        panel.hidden = true;
      });
      pricingItemPicker.querySelectorAll("[data-pricing-picker-subcategory-panel]").forEach(function (panel) {
        panel.hidden = true;
      });
      pricingItemPicker.querySelectorAll("[data-pricing-picker-subcategory]").forEach(function (folder) {
        folder.hidden = false;
      });
      pricingItemPicker.querySelectorAll("[data-pricing-picker-item]").forEach(function (choice) {
        choice.hidden = false;
      });
      if (pricingItemPickerEmpty) pricingItemPickerEmpty.hidden = true;
    }

    function showPricingPickerCategory(panelId, label) {
      if (pricingPickerCategoryList) pricingPickerCategoryList.hidden = true;
      if (pricingPickerBack) pricingPickerBack.hidden = false;
      if (pricingPickerTitle) pricingPickerTitle.textContent = label;
      pricingPickerParentPanel = null;
      pricingItemPicker.querySelectorAll("[data-pricing-picker-category-panel]").forEach(function (panel) {
        panel.hidden = panel.id !== panelId;
      });
      pricingItemPicker.querySelectorAll("[data-pricing-picker-subcategory-panel]").forEach(function (panel) {
        panel.hidden = true;
      });
      if (pricingItemPickerEmpty) pricingItemPickerEmpty.hidden = true;
    }

    function showPricingPickerSubcategory(panelId, parentPanelId, label) {
      if (pricingPickerCategoryList) pricingPickerCategoryList.hidden = true;
      if (pricingPickerBack) pricingPickerBack.hidden = false;
      if (pricingPickerTitle) pricingPickerTitle.textContent = label;
      pricingPickerParentPanel = parentPanelId;
      pricingItemPicker.querySelectorAll("[data-pricing-picker-category-panel]").forEach(function (panel) {
        panel.hidden = true;
      });
      pricingItemPicker.querySelectorAll("[data-pricing-picker-subcategory-panel]").forEach(function (panel) {
        panel.hidden = panel.id !== panelId;
      });
      if (pricingItemPickerEmpty) pricingItemPickerEmpty.hidden = true;
    }

    addPricingLineButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        pricingPickerSection = null;
        openPricingItemPicker();
      });
    });

    if (pricingItemPicker) {
      pricingItemPicker.querySelectorAll("[data-pricing-picker-category]").forEach(function (folder) {
        folder.addEventListener("click", function () {
          showPricingPickerCategory(folder.dataset.pricingPickerCategory, folder.dataset.categoryLabel);
        });
      });
      pricingItemPicker.querySelectorAll("[data-pricing-picker-subcategory]").forEach(function (folder) {
        folder.addEventListener("click", function () {
          showPricingPickerSubcategory(
            folder.dataset.pricingPickerSubcategory,
            folder.dataset.parentPanel,
            folder.dataset.categoryLabel
          );
        });
      });
      if (pricingPickerBack) {
        pricingPickerBack.addEventListener("click", function () {
          if (pricingItemPickerSearch) pricingItemPickerSearch.value = "";
          if (pricingPickerParentPanel) {
            var parentPanel = pricingItemPicker.querySelector("#" + pricingPickerParentPanel);
            showPricingPickerCategory(
              pricingPickerParentPanel,
              parentPanel ? parentPanel.dataset.categoryLabel : ""
            );
          } else {
            showPricingPickerCategories();
          }
        });
      }
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
          if (!query) {
            showPricingPickerCategories();
            return;
          }
          if (pricingPickerCategoryList) pricingPickerCategoryList.hidden = true;
          if (pricingPickerBack) pricingPickerBack.hidden = false;
          if (pricingPickerTitle) pricingPickerTitle.textContent = pricingPickerTitle.dataset.searchTitle;
          pricingPickerParentPanel = null;
          pricingItemPicker.querySelectorAll("[data-pricing-picker-subcategory]").forEach(function (folder) {
            folder.hidden = true;
          });
          var visibleCount = 0;
          pricingItemPicker.querySelectorAll("[data-pricing-picker-item]").forEach(function (choice) {
            var matches = !query || choice.dataset.searchText.indexOf(query) !== -1;
            choice.hidden = !matches;
            if (matches) visibleCount += 1;
          });
          pricingItemPicker.querySelectorAll("[data-pricing-picker-category-panel]").forEach(function (category) {
            category.hidden = !category.querySelector(
              "[data-pricing-picker-item]:not([hidden])"
            );
          });
          pricingItemPicker.querySelectorAll("[data-pricing-picker-subcategory-panel]").forEach(function (category) {
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
      selected.forEach(function (entry, index) {
        var file = entry.file;
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
        if (photoRoot.dataset.descriptionName) {
          cell.classList.add("preview-with-description");
          var description = document.createElement("textarea");
          description.name = photoRoot.dataset.descriptionName;
          description.maxLength = 5000;
          description.rows = 2;
          description.placeholder = photoRoot.dataset.descriptionPlaceholder || "Photo description";
          description.setAttribute("aria-label", (photoRoot.dataset.descriptionLabel || "Description for") + " " + file.name);
          description.value = entry.description || "";
          description.addEventListener("input", function () { entry.description = description.value; });
          var guidanceOptions = photoRoot.photoGuidanceOptions || [];
          if (guidanceOptions.length) {
            var guidanceSelect = document.createElement("select");
            guidanceSelect.className = "photo-guidance-description-select";
            var guidancePlaceholder = document.createElement("option");
            guidancePlaceholder.value = "";
            guidancePlaceholder.textContent = photoRoot.photoGuidanceSelectLabel || "Select a standard description";
            guidanceSelect.appendChild(guidancePlaceholder);
            guidanceOptions.forEach(function (value) {
              var option = document.createElement("option");
              option.value = value;
              option.textContent = value;
              if (entry.description === value) option.selected = true;
              guidanceSelect.appendChild(option);
            });
            guidanceSelect.addEventListener("change", function () {
              if (!guidanceSelect.value) return;
              entry.description = guidanceSelect.value;
              description.value = guidanceSelect.value;
              description.dispatchEvent(new Event("input", { bubbles: true }));
            });
            cell.appendChild(guidanceSelect);
          }
          var ordering = document.createElement("div");
          ordering.className = "preview-order-actions";
          var up = document.createElement("button");
          up.type = "button"; up.className = "btn btn-quiet btn-sm"; up.textContent = "↑";
          up.setAttribute("aria-label", "Move " + file.name + " earlier");
          up.disabled = index === 0;
          up.addEventListener("click", function () {
            if (index > 0) { var previous = selected[index - 1]; selected[index - 1] = selected[index]; selected[index] = previous; refresh(); }
          });
          var down = document.createElement("button");
          down.type = "button"; down.className = "btn btn-quiet btn-sm"; down.textContent = "↓";
          down.setAttribute("aria-label", "Move " + file.name + " later");
          down.disabled = index === selected.length - 1;
          down.addEventListener("click", function () {
            if (index < selected.length - 1) { var next = selected[index + 1]; selected[index + 1] = selected[index]; selected[index] = next; refresh(); }
          });
          ordering.append(up, down);
          cell.append(description);
          if (photoRoot.dataset.issueName) {
            var issueLabel = document.createElement("label");
            issueLabel.className = "photo-issue-toggle";
            var issueCheckbox = document.createElement("input");
            issueCheckbox.type = "checkbox";
            issueCheckbox.name = photoRoot.dataset.issueName + "_" + index;
            issueCheckbox.value = "1";
            issueCheckbox.checked = Boolean(entry.issueFound);
            issueCheckbox.addEventListener("change", function () {
              entry.issueFound = issueCheckbox.checked;
            });
            var issueText = document.createElement("span");
            issueText.textContent = photoRoot.dataset.issueLabel || "Issue Found";
            issueLabel.append(issueCheckbox, issueText);
            cell.append(issueLabel);
          }
          cell.append(ordering);
        }
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
      selected.forEach(function (entry) { dt.items.add(entry.file); });
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
        selected.push({ file: file, description: "", issueFound: false });
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
    photoRoot.refreshPhotoGuidance = refresh;
  };
  document.querySelectorAll("[data-photos]").forEach(window.initializePhotoPicker);

  /* ------------------------------------------ shared page navigation */
  document.querySelectorAll("[data-page-back]").forEach(function (button) {
    button.addEventListener("click", function () {
      var fallback = button.dataset.fallbackUrl || "/dashboard";
      var referrer = null;
      try { referrer = document.referrer ? new URL(document.referrer) : null; } catch (error) { referrer = null; }
      var canReturn = referrer && referrer.origin === window.location.origin &&
        referrer.pathname !== "/login" && referrer.pathname !== "/logout" &&
        window.history.length > 1;
      if (canReturn) window.history.back();
      else window.location.assign(fallback);
    });
  });

  /* ------------------------------------------ Sub Project Site assignment */
  document.querySelectorAll("[data-site-assignment-form]").forEach(function (form) {
    var button = form.querySelector("[data-deselect-sites]");
    var sites = Array.prototype.slice.call(form.querySelectorAll('input[name="site_ids"]'));
    if (!button) return;
    function refresh() {
      button.disabled = !sites.some(function (site) { return site.checked; });
    }
    button.addEventListener("click", function () {
      sites.forEach(function (site) {
        if (!site.checked) return;
        site.checked = false;
        site.dispatchEvent(new Event("change", { bubbles: true }));
      });
      refresh();
    });
    sites.forEach(function (site) { site.addEventListener("change", refresh); });
    refresh();
  });

  /* ---------------- Optional project photo guidance profiles */
  function initializePhotoGuidance(config) {
    var form = config.matches("form") ? config : config.closest("form");
    if (!form || form.dataset.photoGuidanceInitialized === "true") return;
    form.dataset.photoGuidanceInitialized = "true";
    var url = config.dataset.guidanceUrl;
    var selectLabel = config.dataset.guidanceSelectLabel || "Select a standard description";
    var alertLabel = config.dataset.guidanceAlertLabel || "Photo guidance";
    var cache = new Map();

    function stageOf(root) {
      if (root.dataset.photoStage) return root.dataset.photoStage;
      var name = root.dataset.descriptionName || root.dataset.descriptionKind || "";
      return name.indexOf("before") !== -1 ? "before" : "after";
    }
    function showAlert(root, message) {
      var zone = root.querySelector(".dropzone");
      if (!zone) return;
      var existing = zone.querySelector(".photo-guidance-alert");
      if (existing) existing.remove();
      if (!message) return;
      var alert = document.createElement("span");
      alert.className = "photo-guidance-alert";
      var button = document.createElement("button");
      button.type = "button";
      button.className = "photo-guidance-alert-icon";
      button.textContent = "i";
      button.title = message;
      button.setAttribute("aria-label", alertLabel + ": " + message);
      button.setAttribute("aria-expanded", "false");
      var popover = document.createElement("span");
      popover.className = "photo-guidance-alert-text";
      popover.textContent = message;
      popover.hidden = true;
      button.addEventListener("click", function () {
        popover.hidden = !popover.hidden;
        button.setAttribute("aria-expanded", popover.hidden ? "false" : "true");
      });
      button.addEventListener("blur", function () { popover.hidden = true; button.setAttribute("aria-expanded", "false"); });
      alert.append(button, popover);
      zone.insertBefore(alert, zone.firstChild);
    }
    function clearRow(row) {
      row.querySelectorAll("[data-photos]").forEach(function (root) {
        root.photoGuidanceOptions = [];
        root.photoGuidanceSelectLabel = selectLabel;
        showAlert(root, "");
        if (root.refreshPhotoGuidance) root.refreshPhotoGuidance();
      });
      row.querySelectorAll("[data-guidance-photo-stage] .photo-guidance-description-select").forEach(function (select) { select.remove(); });
    }
    function applyExistingDescriptions(row, payload) {
      row.querySelectorAll("[data-guidance-photo-stage]").forEach(function (card) {
        var oldSelect = card.querySelector(".photo-guidance-description-select");
        if (oldSelect) oldSelect.remove();
        var guidance = payload.enabled ? payload[card.dataset.guidancePhotoStage] : null;
        var options = guidance && guidance.descriptions ? guidance.descriptions : [];
        var textarea = card.querySelector('textarea[name^="photo_description_"]');
        if (!textarea || !options.length) return;
        var select = document.createElement("select");
        select.className = "photo-guidance-description-select";
        var placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = selectLabel;
        select.appendChild(placeholder);
        options.forEach(function (value) {
          var option = document.createElement("option");
          option.value = value;
          option.textContent = value;
          if (textarea.value === value) option.selected = true;
          select.appendChild(option);
        });
        select.addEventListener("change", function () {
          if (!select.value) return;
          textarea.value = select.value;
          textarea.dispatchEvent(new Event("input", { bubbles: true }));
        });
        textarea.parentNode.insertBefore(select, textarea);
      });
    }
    function apply(row, payload) {
      row.querySelectorAll("[data-photos]").forEach(function (root) {
        var stage = stageOf(root);
        var guidance = payload.enabled && payload[stage] ? payload[stage] : { alert: "", descriptions: [] };
        root.photoGuidanceOptions = guidance.descriptions || [];
        root.photoGuidanceSelectLabel = selectLabel;
        showAlert(root, guidance.alert || "");
        if (root.refreshPhotoGuidance) root.refreshPhotoGuidance();
      });
      applyExistingDescriptions(row, payload);
    }
    function loadRow(row) {
      var scope = row.closest("[data-site-scope]");
      var project = scope && scope.querySelector('[name="project_id"]');
      var site = scope && scope.querySelector('[name="work_site_id"]');
      var profile = row.querySelector('[data-photo-guidance-profile-select], [data-guidance-profile-id]');
      var values = [project && project.value, profile && profile.value, site && site.value];
      row.photoGuidanceRequest = (row.photoGuidanceRequest || 0) + 1;
      var requestNumber = row.photoGuidanceRequest;
      if (values.some(function (value) { return !value; })) { clearRow(row); return; }
      var key = values.join(":");
      var pending = cache.get(key);
      if (!pending) {
        var params = new URLSearchParams({ project_id: values[0], profile_id: values[1], work_site_id: values[2] });
        pending = fetch(url + "?" + params.toString(), { headers: { "Accept": "application/json" } })
          .then(function (response) { return response.ok ? response.json() : { enabled: false }; })
          .catch(function () { return { enabled: false }; });
        cache.set(key, pending);
      }
      pending.then(function (payload) {
        if (requestNumber === row.photoGuidanceRequest) apply(row, payload);
      });
    }
    function refresh() {
      form.querySelectorAll("[data-device-row], [data-existing-item]").forEach(function (row) {
        var scope = row.closest("[data-site-scope]");
        var project = scope && scope.querySelector('[name="project_id"]');
        var profile = row.querySelector('[data-photo-guidance-profile-select]');
        if (profile) {
          Array.from(profile.options).forEach(function (option) {
            if (!option.value) return;
            var available = Boolean(project && project.value && option.dataset.projectId === project.value);
            option.hidden = !available;
            option.disabled = !available;
          });
          var selected = profile.options[profile.selectedIndex];
          if (profile.value && (!selected || selected.disabled)) profile.value = "";
        }
        loadRow(row);
      });
    }
    form.addEventListener("change", function (event) {
      if (event.target.matches('[name="project_id"], [name="work_site_id"], [data-photo-guidance-profile-select]')) refresh();
    });
    form.addEventListener("scopechange", refresh);
    form.refreshPhotoGuidance = refresh;
    refresh();
  }
  window.refreshPhotoGuidance = function (form) {
    if (form && form.refreshPhotoGuidance) form.refreshPhotoGuidance();
  };
  document.querySelectorAll("[data-photo-guidance]").forEach(initializePhotoGuidance);

  /* --------------------------------- Project photo guidance description rows */
  function initializePhotoGuidanceRuleForm(form) {
    function refreshPreview(stage) {
      var editor = form.querySelector('[data-description-stage="' + stage + '"]');
      var preview = form.querySelector('[data-guidance-preview="' + stage + '"]');
      if (!editor || !preview) return;
      var select = preview.querySelector("[data-preview-select]");
      var alertIcon = preview.querySelector("[data-preview-alert]");
      var alertField = form.querySelector('[name="' + stage + '_alert"]');
      var placeholder = select.options[0] ? select.options[0].textContent : "";
      select.replaceChildren();
      var first = document.createElement("option");
      first.textContent = placeholder;
      select.appendChild(first);
      editor.querySelectorAll('input[type="text"]').forEach(function (input) {
        var value = input.value.trim();
        if (!value) return;
        var option = document.createElement("option");
        option.textContent = value;
        select.appendChild(option);
      });
      select.disabled = select.options.length === 1;
      var alertText = alertField ? alertField.value.trim() : "";
      alertIcon.hidden = !alertText;
      alertIcon.title = alertText;
    }

    function refreshEditor(editor) {
      var rows = Array.from(editor.querySelectorAll("[data-description-row]"));
      var populated = 0;
      rows.forEach(function (row, index) {
        var number = row.querySelector("[data-description-number]");
        var input = row.querySelector('input[type="text"]');
        if (number) number.textContent = index + 1;
        if (input) {
          input.setAttribute("aria-label", editor.dataset.descriptionLabel + " " + (index + 1));
          if (input.value.trim()) populated += 1;
        }
      });
      var count = editor.querySelector("[data-description-count]");
      if (count) count.textContent = populated;
      var add = editor.querySelector("[data-add-description]");
      if (add) add.disabled = rows.length >= Number(editor.dataset.maxDescriptions || 30);
      refreshPreview(editor.dataset.descriptionStage);
    }

    form.querySelectorAll("[data-description-editor]").forEach(function (editor) {
      var list = editor.querySelector("[data-description-list]");
      var add = editor.querySelector("[data-add-description]");
      if (!list || !add) return;
      add.addEventListener("click", function () {
        if (list.querySelectorAll("[data-description-row]").length >= Number(editor.dataset.maxDescriptions || 30)) return;
        var row = document.createElement("div");
        row.className = "photo-guidance-description-row";
        row.dataset.descriptionRow = "";
        var number = document.createElement("span");
        number.className = "photo-guidance-description-number";
        number.dataset.descriptionNumber = "";
        var input = document.createElement("input");
        input.type = "text";
        input.name = editor.dataset.descriptionName;
        input.maxLength = 1000;
        input.dir = "auto";
        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "btn btn-quiet btn-sm";
        remove.dataset.removeDescription = "";
        remove.textContent = editor.querySelector("[data-remove-description]").textContent;
        row.append(number, input, remove);
        list.appendChild(row);
        refreshEditor(editor);
        input.focus();
      });
      list.addEventListener("click", function (event) {
        var remove = event.target.closest("[data-remove-description]");
        if (!remove) return;
        var rows = list.querySelectorAll("[data-description-row]");
        if (rows.length === 1) {
          rows[0].querySelector('input[type="text"]').value = "";
        } else {
          remove.closest("[data-description-row]").remove();
        }
        refreshEditor(editor);
      });
      list.addEventListener("input", function () { refreshEditor(editor); });
      refreshEditor(editor);
    });
    form.querySelectorAll('[name="before_alert"], [name="after_alert"]').forEach(function (field) {
      field.addEventListener("input", function () { refreshPreview(field.name.replace("_alert", "")); });
    });
  }
  document.querySelectorAll(".photo-guidance-rule-form").forEach(initializePhotoGuidanceRuleForm);

  /* -------------------------- long-running record entry autosave + keepalive */
  function initializeRecordAutosave(form) {
    var csrfField = form.querySelector('input[name="csrf_token"]');
    if (!csrfField || !window.fetch) return;

    // Returning to the same form means the final submission was rejected and
    // rendered again. Keep its draft instead of treating a later navigation as
    // a successful save.
    if (sessionStorage.getItem("sms-finalizing-edit-path") === window.location.pathname) {
      sessionStorage.removeItem("sms-finalizing-draft");
      sessionStorage.removeItem("sms-finalizing-edit-path");
      sessionStorage.removeItem("sms-finalizing-draft-csrf");
      sessionStorage.removeItem("sms-finalizing-file-prefix");
    }

    var appendField = form.querySelector('input[name="append_record_id"]');
    var draftKey = (window.location.pathname + (appendField && appendField.value ? ":append:" + appendField.value : "")).toLowerCase();
    var userStorageKey = draftKey;
    var ready = false;
    var restoring = false;
    var dirty = false;
    var saveTimer = null;
    var lastSavedPayload = "";
    var arabic = (document.documentElement.lang || "").toLowerCase().indexOf("ar") === 0;
    function local(english, arabicText) { return arabic ? arabicText : english; }

    var bar = document.createElement("div");
    bar.className = "record-autosave-bar no-print";
    bar.setAttribute("role", "status");
    bar.innerHTML = '<span class="record-autosave-dot" aria-hidden="true"></span><span data-autosave-status></span><span class="record-autosave-actions"><button type="button" class="btn btn-secondary btn-sm" data-autosave-now></button><button type="button" class="btn btn-secondary btn-sm" data-autosave-restore hidden></button><button type="button" class="btn btn-quiet btn-sm" data-autosave-discard hidden></button></span>';
    form.insertBefore(bar, form.firstChild);
    var statusText = bar.querySelector("[data-autosave-status]");
    var saveButton = bar.querySelector("[data-autosave-now]");
    var restoreButton = bar.querySelector("[data-autosave-restore]");
    var discardButton = bar.querySelector("[data-autosave-discard]");
    statusText.textContent = local("Preparing autosave…", "جارٍ تجهيز الحفظ التلقائي…");
    saveButton.textContent = local("Save draft", "حفظ المسودة");
    restoreButton.textContent = local("Restore draft", "استعادة المسودة");
    discardButton.textContent = local("Discard draft", "حذف المسودة");

    function setStatus(message, tone) {
      statusText.textContent = message;
      bar.dataset.tone = tone || "";
    }

    function draftFields() {
      var occurrences = {};
      return Array.from(form.elements).filter(function (field) {
        return field.name && field.type !== "file" && field.type !== "submit" && field.type !== "button" &&
          field.name !== "csrf_token" && field.name !== "form_token" &&
          field.name.indexOf("existing_remove_photo_") !== 0;
      }).map(function (field) {
        var ordinal = occurrences[field.name] || 0;
        occurrences[field.name] = ordinal + 1;
        return {
          name: field.name,
          ordinal: ordinal,
          type: field.type || field.tagName.toLowerCase(),
          value: field.value,
          checked: Boolean(field.checked)
        };
      });
    }

    function draftStructure() {
      return Array.from(form.querySelectorAll("[data-site-scopes] > [data-site-scope]")).map(function (scope) {
        var table = scope.querySelector("[data-entry-data-table]");
        return {
          savedScope: scope.dataset.savedScope || null,
          isNew: scope.hasAttribute("data-new-site") || !scope.hasAttribute("data-existing-site"),
          existingItems: Array.from(scope.querySelectorAll("[data-existing-item-id]")).map(function (item) { return item.dataset.existingItemId; }),
          newDeviceCount: scope.querySelectorAll("[data-device-items] [data-device-row]").length,
          rowCount: table ? table.querySelectorAll("[data-entry-data-row]").length : 0
        };
      });
    }

    function snapshot() {
      return {
        version: 1,
        savedAt: new Date().toISOString(),
        structure: draftStructure(),
        fields: draftFields(),
        hasSelectedPhotos: Array.from(form.querySelectorAll('input[type="file"]')).some(function (field) { return field.files && field.files.length; })
      };
    }

    function fieldGroups() {
      var groups = {};
      Array.from(form.elements).forEach(function (field) {
        if (!field.name) return;
        (groups[field.name] = groups[field.name] || []).push(field);
      });
      return groups;
    }

    function restoreStructure(structure) {
      if (!Array.isArray(structure)) return;
      var scopesRoot = form.querySelector("[data-site-scopes]");
      var addSite = form.querySelector("[data-add-site]");
      if (!scopesRoot || !addSite) return;
      // A draft restores additions and field work, never an old destructive
      // action. Saved Sites/items are authoritative and remain visible until an
      // Administrator explicitly removes them again in the current page.
      var wantedNewCount = structure.filter(function (item) { return item.savedScope === null; }).length;
      while (scopesRoot.querySelectorAll("[data-new-site]").length < wantedNewCount) addSite.click();
      while (scopesRoot.querySelectorAll("[data-new-site]").length > wantedNewCount) {
        var extras = scopesRoot.querySelectorAll("[data-new-site]");
        extras[extras.length - 1].remove();
      }
      var newScopes = Array.from(scopesRoot.querySelectorAll("[data-new-site]"));
      var newIndex = 0;
      structure.forEach(function (wanted) {
        var scope = wanted.savedScope !== null
          ? Array.from(scopesRoot.querySelectorAll("[data-existing-site]")).find(function (candidate) { return String(candidate.dataset.savedScope) === String(wanted.savedScope); })
          : newScopes[newIndex++];
        if (!scope) return;
        var itemsRoot = scope.querySelector("[data-device-items]");
        var addDevice = scope.querySelector("[data-add-device]");
        if (itemsRoot && addDevice) {
          while (itemsRoot.querySelectorAll("[data-device-row]").length < wanted.newDeviceCount) addDevice.click();
          while (itemsRoot.querySelectorAll("[data-device-row]").length > wanted.newDeviceCount) {
            var devices = itemsRoot.querySelectorAll("[data-device-row]");
            devices[devices.length - 1].remove();
          }
        }
        var table = scope.querySelector("[data-entry-data-table]");
        var addRow = table && table.querySelector("[data-add-data-row]");
        if (table && addRow) {
          while (table.querySelectorAll("[data-entry-data-row]").length < Math.max(1, wanted.rowCount)) addRow.click();
          while (table.querySelectorAll("[data-entry-data-row]").length > Math.max(1, wanted.rowCount)) {
            var rows = table.querySelectorAll("[data-entry-data-row]");
            rows[rows.length - 1].remove();
          }
        }
      });
      if (window.refreshNestedEntryDevices) window.refreshNestedEntryDevices(form);
    }

    function applyNamedFields(savedFields, names, dispatchChange) {
      var groups = fieldGroups();
      savedFields.forEach(function (saved) {
        if (names && names.indexOf(saved.name) === -1) return;
        if (!names && ["project_id", "sub_project_id", "work_site_id"].indexOf(saved.name) !== -1) return;
        var field = groups[saved.name] && groups[saved.name][saved.ordinal];
        if (!field || field.type === "file") return;
        if (field.type === "checkbox" || field.type === "radio") field.checked = Boolean(saved.checked);
        else field.value = saved.value;
        if (dispatchChange) field.dispatchEvent(new Event("change", { bubbles: true }));
      });
    }

    function restoreFields(savedFields) {
      if (!Array.isArray(savedFields)) return;
      applyNamedFields(savedFields, ["project_id"], true);
      applyNamedFields(savedFields, ["sub_project_id"], true);
      applyNamedFields(savedFields, ["work_site_id"], true);
      applyNamedFields(savedFields, null, false);
      form.querySelectorAll('input[type="checkbox"][name^="existing_remove_photo_"]').forEach(function (field) {
        field.checked = false;
      });
      if (window.refreshNestedEntryDevices) window.refreshNestedEntryDevices(form);
    }

    function openFileDatabase() {
      return new Promise(function (resolve, reject) {
        if (!window.indexedDB) { reject(new Error("IndexedDB unavailable")); return; }
        var request = indexedDB.open("sms-record-drafts", 1);
        request.onupgradeneeded = function () {
          if (!request.result.objectStoreNames.contains("files")) request.result.createObjectStore("files", { keyPath: "key" });
        };
        request.onsuccess = function () { resolve(request.result); };
        request.onerror = function () { reject(request.error); };
      });
    }

    function fileInputKey(input) {
      var peers = Array.from(form.querySelectorAll('input[type="file"]')).filter(function (candidate) { return candidate.name === input.name; });
      return userStorageKey + "|" + input.name + "|" + Math.max(0, peers.indexOf(input));
    }

    function rememberFiles(input) {
      if (!ready || !input.files) return;
      openFileDatabase().then(function (db) {
        var tx = db.transaction("files", "readwrite");
        var store = tx.objectStore("files");
        var key = fileInputKey(input);
        if (!input.files.length) store.delete(key);
        else store.put({ key: key, files: Array.from(input.files), savedAt: Date.now() });
      }).catch(function () { setStatus(local("Text saved; keep this page open to retain selected photos.", "تم حفظ النصوص؛ اترك الصفحة مفتوحة للاحتفاظ بالصور المختارة."), "warning"); });
    }

    function restoreFiles() {
      if (!window.DataTransfer) return Promise.resolve();
      return openFileDatabase().then(function (db) {
        var inputs = Array.from(form.querySelectorAll('input[type="file"]'));
        return Promise.all(inputs.map(function (input) {
          return new Promise(function (resolve) {
            var request = db.transaction("files", "readonly").objectStore("files").get(fileInputKey(input));
            request.onsuccess = function () {
              if (request.result && request.result.files) {
                try {
                  var transfer = new DataTransfer();
                  request.result.files.forEach(function (file) { transfer.items.add(file); });
                  input.files = transfer.files;
                  input.dispatchEvent(new Event("change", { bubbles: true }));
                } catch (error) { /* Browser keeps the text draft even if files cannot be restored. */ }
              }
              resolve();
            };
            request.onerror = function () { resolve(); };
          });
        }));
      }).catch(function () {});
    }

    function deleteLocalFiles() {
      return openFileDatabase().then(function (db) {
        return new Promise(function (resolve) {
          var tx = db.transaction("files", "readwrite");
          var request = tx.objectStore("files").openCursor();
          request.onsuccess = function () {
            var cursor = request.result;
            if (!cursor) return;
            if (String(cursor.key).indexOf(userStorageKey + "|") === 0) cursor.delete();
            cursor.continue();
          };
          tx.oncomplete = resolve;
          tx.onerror = resolve;
        });
      }).catch(function () {});
    }

    function pruneExpiredLocalFiles() {
      var cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
      return openFileDatabase().then(function (db) {
        var tx = db.transaction("files", "readwrite");
        var request = tx.objectStore("files").openCursor();
        request.onsuccess = function () {
          var cursor = request.result;
          if (!cursor) return;
          if (!cursor.value.savedAt || cursor.value.savedAt < cutoff) cursor.delete();
          cursor.continue();
        };
      }).catch(function () {});
    }
    pruneExpiredLocalFiles();

    function discardDraft() {
      return Promise.all([
        fetch("/drafts/current?draft_key=" + encodeURIComponent(draftKey) + "&csrf_token=" + encodeURIComponent(csrfField.value), {
          method: "DELETE", credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" }
        }).catch(function () {}),
        deleteLocalFiles()
      ]).then(function () {
        lastSavedPayload = "";
        dirty = false;
        setStatus(local("Draft discarded. Autosave is ready.", "تم حذف المسودة، والحفظ التلقائي جاهز."), "ready");
      });
    }

    function saveNow() {
      if (!ready || restoring) return Promise.resolve(false);
      var payload = snapshot();
      var encoded = JSON.stringify(payload);
      if (!dirty && encoded === lastSavedPayload) return Promise.resolve(true);
      setStatus(local("Saving draft…", "جارٍ حفظ المسودة…"), "saving");
      return fetch("/drafts/autosave", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({ csrf_token: csrfField.value, draft_key: draftKey, page_url: window.location.pathname + window.location.search, payload: payload })
      }).then(function (response) {
        if (response.status === 401 || response.status === 403) throw new Error("session");
        if (!response.ok) throw new Error("save");
        return response.json();
      }).then(function (data) {
        dirty = false;
        lastSavedPayload = encoded;
        var time = data.updated_at ? new Date(data.updated_at + (data.updated_at.endsWith("Z") ? "" : "Z")) : new Date();
        setStatus(local("Draft saved at ", "تم حفظ المسودة الساعة ") + time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), "saved");
        return true;
      }).catch(function (error) {
        setStatus(error.message === "session"
          ? local("Session expired. Sign in again; your last draft is safe.", "انتهت الجلسة. سجل الدخول مجددًا؛ آخر مسودة محفوظة بأمان.")
          : local("Draft not saved. Check the connection; retrying automatically.", "لم تُحفظ المسودة. تحقق من الاتصال؛ ستتم إعادة المحاولة تلقائيًا."), "error");
        return false;
      });
    }

    function scheduleSave() {
      if (!ready || restoring) return;
      dirty = true;
      window.clearTimeout(saveTimer);
      saveTimer = window.setTimeout(saveNow, 5000);
    }

    form.addEventListener("input", scheduleSave);
    form.addEventListener("change", function (event) {
      if (event.target && event.target.type === "file") rememberFiles(event.target);
      scheduleSave();
    });
    form.addEventListener("click", function (event) {
      if (event.target.closest("[data-add-site], [data-add-device], [data-add-data-row], [data-remove-site], [data-remove-device], [data-remove-existing-item], [data-remove-data-row]")) {
        window.setTimeout(scheduleSave, 0);
      }
    });
    saveButton.addEventListener("click", function () { dirty = true; saveNow(); });

    fetch("/drafts/current?draft_key=" + encodeURIComponent(draftKey), {
      credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" }
    }).then(function (response) {
      if (!response.ok) throw new Error("load");
      return response.json();
    }).then(function (data) {
      userStorageKey = String(data.user_id || "user") + "|" + draftKey;
      var saved = data.draft && data.draft.payload;
      if (!saved) {
        ready = true;
        setStatus(local("Autosave is ready. Changes are protected for 7 days.", "الحفظ التلقائي جاهز. التغييرات محفوظة لمدة 7 أيام."), "ready");
        return;
      }
      setStatus(local("A saved draft is available from ", "توجد مسودة محفوظة منذ ") + new Date(data.draft.updated_at + (data.draft.updated_at.endsWith("Z") ? "" : "Z")).toLocaleString() + ".", "warning");
      restoreButton.hidden = false;
      discardButton.hidden = false;
      saveButton.hidden = true;
      restoreButton.addEventListener("click", function () {
        restoring = true;
        restoreStructure(saved.structure);
        restoreFields(saved.fields);
        restoreFiles().then(function () {
          // File restoration recreates each dynamic photo description and
          // Issue Found checkbox. Reapply the saved values after those fields
          // exist so long-entry drafts keep both pieces of photo evidence.
          restoreFields(saved.fields);
        }).finally(function () {
          restoring = false;
          ready = true;
          dirty = false;
          lastSavedPayload = JSON.stringify(snapshot());
          restoreButton.hidden = true;
          discardButton.hidden = true;
          saveButton.hidden = false;
          setStatus(local("Draft restored. Autosave is active.", "تمت استعادة المسودة والحفظ التلقائي يعمل."), "saved");
        });
      }, { once: true });
      discardButton.addEventListener("click", function () {
        discardDraft().then(function () {
          ready = true;
          restoreButton.hidden = true;
          discardButton.hidden = true;
          saveButton.hidden = false;
        });
      }, { once: true });
    }).catch(function () {
      ready = true;
      setStatus(local("Autosave is temporarily unavailable; keep this page open.", "الحفظ التلقائي غير متاح مؤقتًا؛ اترك هذه الصفحة مفتوحة."), "error");
    });

    window.setInterval(function () {
      if (dirty) saveNow();
      else fetch("/drafts/keepalive", { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } }).catch(function () {
        setStatus(local("Connection lost. Your last saved draft remains available.", "انقطع الاتصال. آخر مسودة محفوظة ما زالت متاحة."), "error");
      });
    }, 4 * 60 * 1000);

    form.addEventListener("submit", function () {
      window.clearTimeout(saveTimer);
      sessionStorage.setItem("sms-finalizing-draft", draftKey);
      sessionStorage.setItem("sms-finalizing-edit-path", window.location.pathname);
      sessionStorage.setItem("sms-finalizing-draft-csrf", csrfField.value);
      sessionStorage.setItem("sms-finalizing-file-prefix", userStorageKey + "|");
    });

    form._discardAutosaveDraft = discardDraft;
  }
  document.querySelectorAll("[data-record-autosave]").forEach(initializeRecordAutosave);

  var finalizedDraft = sessionStorage.getItem("sms-finalizing-draft");
  var finalizedEditPath = sessionStorage.getItem("sms-finalizing-edit-path");
  var finalizedCsrf = sessionStorage.getItem("sms-finalizing-draft-csrf");
  var finalizedFilePrefix = sessionStorage.getItem("sms-finalizing-file-prefix");
  if (finalizedDraft && finalizedEditPath && window.location.pathname !== finalizedEditPath && !document.querySelector("[data-record-autosave]")) {
    sessionStorage.removeItem("sms-finalizing-draft");
    sessionStorage.removeItem("sms-finalizing-edit-path");
    sessionStorage.removeItem("sms-finalizing-draft-csrf");
    sessionStorage.removeItem("sms-finalizing-file-prefix");
    // The server accepted and redirected away from the entry/edit form.
    // The draft endpoint remains user-scoped; stale local files are cleaned
    // the next time this draft is explicitly discarded.
    fetch("/drafts/current?draft_key=" + encodeURIComponent(finalizedDraft) + "&csrf_token=" + encodeURIComponent(finalizedCsrf || ""), { method: "DELETE", credentials: "same-origin" }).catch(function () {});
    if (finalizedFilePrefix && window.indexedDB) {
      var cleanupRequest = indexedDB.open("sms-record-drafts", 1);
      cleanupRequest.onupgradeneeded = function () {
        if (!cleanupRequest.result.objectStoreNames.contains("files")) cleanupRequest.result.createObjectStore("files", { keyPath: "key" });
      };
      cleanupRequest.onsuccess = function () {
        var tx = cleanupRequest.result.transaction("files", "readwrite");
        var cursorRequest = tx.objectStore("files").openCursor();
        cursorRequest.onsuccess = function () {
          var cursor = cursorRequest.result;
          if (!cursor) return;
          if (String(cursor.key).indexOf(finalizedFilePrefix) === 0) cursor.delete();
          cursor.continue();
        };
      };
    }
  }

  /* ------------------------------------ submit with progress + duplicate lock */
  var submitForm = document.querySelector("[data-async-form]");
  if (submitForm && window.XMLHttpRequest && window.FormData) {
    var submitBtn = submitForm.querySelector("[data-submit]");
    var progress = submitForm.querySelector(".progress");
    var bar = progress ? progress.querySelector("span") : null;
    var busy = false;
    var dirtyGuardOff = false;
    var submitLabel = submitBtn.dataset.label || submitBtn.textContent;

    function entryValidationCopy() {
      var arabic = (document.documentElement.lang || "").toLowerCase().indexOf("ar") === 0;
      return arabic ? {
        summary: "تعذر الحفظ. أكمل الحقول المحددة باللون الأحمر ثم حاول مرة أخرى. لم يتم فقد أي بيانات.",
        site: "الموقع", service: "الخدمة",
        project: "اختر المشروع الرئيسي.", subProject: "اختر المشروع الفرعي.",
        workSite: "اختر الموقع.", quotation: "اختر عرض سعر صالحًا لهذا المشروع.",
        serviceType: "اختر الخدمة المنفذة.", device: "اختر الصنف أو الجهاز.",
        result: "اختر نتيجة العمل.", photos: "أضف صورة واحدة على الأقل قبل الحفظ.",
        badge: "بيانات مطلوبة"
      } : {
        summary: "The record was not saved. Complete the fields highlighted in red and try again. No entered data was lost.",
        site: "Site", service: "service",
        project: "Select the Main Project.", subProject: "Select the Sub Project.",
        workSite: "Select the Site.", quotation: "Select a valid quotation for this Project.",
        serviceType: "Select the service performed.", device: "Select the Item or device.",
        result: "Select the work result.", photos: "Add at least one photo before saving.",
        badge: "Required information"
      };
    }

    function validateEntryBeforeSubmit() {
      var copy = entryValidationCopy();
      var errors = {};
      var details = [];
      var scopes = Array.from(submitForm.querySelectorAll("[data-site-scope]"));
      var rows = Array.from(submitForm.querySelectorAll("[data-device-row]"));
      var isNestedEdit = submitForm.matches("[data-record-nested-edit]");

      function add(key, message, context) {
        if (errors[key]) return;
        errors[key] = message;
        details.push(context + ": " + message);
      }

      scopes.forEach(function (scope, scopeIndex) {
        var active = !isNestedEdit || scope.matches("[data-new-site]") || Boolean(scope.querySelector("[data-device-row]"));
        if (!active) return;
        var suffix = scopeIndex === 0 ? "" : "_scope_" + scopeIndex;
        var scopeLabel = copy.site + " " + (scopeIndex + 1);
        [
          ["project_id", copy.project], ["sub_project_id", copy.subProject],
          ["work_site_id", copy.workSite], ["quotation_number", copy.quotation]
        ].forEach(function (definition) {
          var field = scope.querySelector('[name="' + definition[0] + '"]:not([disabled])');
          if (field && !String(field.value || "").trim()) add(definition[0] + suffix, definition[1], scopeLabel);
        });
      });

      rows.forEach(function (row, rowIndex) {
        var scope = row.closest("[data-site-scope]");
        var scopeIndex = Math.max(scopes.indexOf(scope), 0);
        var rowIndexInScope = Array.from(scope.querySelectorAll("[data-device-row]")).indexOf(row);
        var context = copy.site + " " + (scopeIndex + 1) + "، " + copy.service + " " + (rowIndexInScope + 1);
        var service = row.querySelector('select[name="service_type_id"]');
        var device = row.querySelector('select[name="device_id"]');
        var result = row.querySelector('input[data-name-kind="result"]:checked');
        var photoCount = Array.from(row.querySelectorAll('input[type="file"][name]')).reduce(function (total, input) {
          return total + (input.files ? input.files.length : 0);
        }, 0);
        if (!service || !service.value) add("service_type_id_" + rowIndex, copy.serviceType, context);
        if (device && !device.value) add("device_id_" + rowIndex, copy.device, context);
        if (!result) add("result_" + rowIndex, copy.result, context);
        if (!photoCount) add("photos_" + rowIndex, copy.photos, context);
      });

      if (!details.length) return null;
      errors.form = copy.summary + " " + details.join(" ");
      return errors;
    }
    var savingLabel = submitBtn.dataset.savingLabel || "Saving record…";

    submitForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (busy) return;
      // The async handler is registered before the nested-entry handler on a
      // deferred page. Rebase additions before FormData captures the fields.
      prepareNestedEditSubmission(submitForm);
      var clientErrors = validateEntryBeforeSubmit();
      if (clientErrors) {
        renderErrors(clientErrors);
        return;
      }
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
        if (!data.errors && xhr.responseText) {
          try {
            var responsePage = new DOMParser().parseFromString(xhr.responseText, "text/html");
            var responseError = responsePage.querySelector("[data-form-error], .alert.error");
            var responseToken = responsePage.querySelector('input[name="form_token"]');
            if (responseError && responseError.textContent.trim()) {
              data.errors = { form: responseError.textContent.trim() };
            }
            if (responseToken) data.form_token = responseToken.value;
          } catch (parseError) { /* fall through to the safe generic message */ }
        }
        if (xhr.status >= 200 && xhr.status < 300 && data.redirect) {
          if (bar) bar.style.width = "100%";
          window.location.assign(data.redirect);
          return;
        }
        busy = false;
        dirtyGuardOff = false;
        sessionStorage.removeItem("sms-finalizing-draft");
        sessionStorage.removeItem("sms-finalizing-edit-path");
        sessionStorage.removeItem("sms-finalizing-draft-csrf");
        sessionStorage.removeItem("sms-finalizing-file-prefix");
        submitBtn.disabled = false;
        submitBtn.textContent = submitLabel;
        if (progress) progress.setAttribute("hidden", "");
        renderErrors(data.errors || { form: "The record could not be saved. Try again." }, data.form_token);
      });
      xhr.addEventListener("error", function () {
        busy = false; dirtyGuardOff = false;
        sessionStorage.removeItem("sms-finalizing-draft");
        sessionStorage.removeItem("sms-finalizing-edit-path");
        sessionStorage.removeItem("sms-finalizing-draft-csrf");
        sessionStorage.removeItem("sms-finalizing-file-prefix");
        submitBtn.disabled = false;
        submitBtn.textContent = submitLabel;
        if (progress) progress.setAttribute("hidden", "");
        renderErrors({ form: "The connection dropped before the record was saved. Try again." });
      });
      xhr.send(new FormData(submitForm));
    });

    function renderErrors(errors, freshToken) {
      var copy = entryValidationCopy();
      if (freshToken) {
        var tokenField = submitForm.querySelector('input[name=form_token]');
        if (tokenField) tokenField.value = freshToken;
      }
      submitForm.querySelectorAll('[aria-invalid="true"]').forEach(function (field) { field.removeAttribute("aria-invalid"); });
      submitForm.querySelectorAll('[data-validation-error="true"]').forEach(function (section) { section.removeAttribute("data-validation-error"); });
      submitForm.querySelectorAll("[data-validation-badge], [data-client-validation-error]").forEach(function (node) { node.remove(); });
      submitForm.querySelectorAll("[data-error-for], [data-error-kind], [data-photo-error]").forEach(function (slot) {
        slot.textContent = "";
        slot.style.display = "none";
      });

      function markSection(section) {
        if (!section) return;
        section.dataset.validationError = "true";
        var head = section.querySelector(":scope > .card-head");
        if (head && !head.querySelector("[data-validation-badge]")) {
          var badge = document.createElement("span");
          badge.className = "validation-error-badge";
          badge.dataset.validationBadge = "true";
          badge.textContent = copy.badge;
          head.appendChild(badge);
        }
      }

      function showFieldError(field, message, preferredSlot) {
        if (!field) return;
        var visualField = field;
        if (field.matches('select[name="device_id"]')) {
          var pickerButton = field.closest(".field") && field.closest(".field").querySelector("[data-service-item-trigger]");
          if (pickerButton && !pickerButton.hidden) visualField = pickerButton;
        }
        if (field.matches('input[type="file"]')) {
          var photoPanel = field.closest("[data-photos]");
          if (photoPanel) {
            photoPanel.dataset.validationError = "true";
            visualField = photoPanel.querySelector("[data-pick]") || field;
          }
        }
        visualField.setAttribute("aria-invalid", "true");
        if (field.matches('input[type="radio"]')) {
          var choices = field.closest(".choice-list");
          if (choices) choices.dataset.validationError = "true";
        }
        var slot = preferredSlot;
        if (!slot) {
          var fieldWrap = field.closest(".field");
          slot = fieldWrap && fieldWrap.querySelector(".error-text");
        }
        if (!slot) {
          slot = document.createElement("p");
          slot.className = "error-text";
          slot.dataset.clientValidationError = "true";
          (field.closest(".field") || field.parentElement).appendChild(slot);
        }
        slot.textContent = message;
        slot.style.display = "";
        markSection(field.closest("[data-device-row]"));
        markSection(field.closest("[data-site-scope]"));
      }

      submitForm.querySelectorAll("[data-error-for]").forEach(function (slot) {
        var key = slot.dataset.errorFor;
        if (!errors[key]) return;
        var field = submitForm.querySelector('[name="' + key + '"]');
        if (field) showFieldError(field, errors[key], slot);
      });

      Object.keys(errors).forEach(function (key) {
        if (key === "form") return;
        var scopeMatch = key.match(/^(project_id|sub_project_id|work_site_id|quotation_number)(?:_scope_(\d+))?$/);
        if (scopeMatch) {
          var scopeIndex = scopeMatch[2] ? parseInt(scopeMatch[2], 10) : 0;
          var scope = submitForm.querySelectorAll("[data-site-scope]")[scopeIndex];
          var scopeField = scope && scope.querySelector('[name="' + scopeMatch[1] + '"]:not([disabled])');
          if (scopeField) showFieldError(scopeField, errors[key]);
          else markSection(scope);
          return;
        }
        var siteMatch = key.match(/^site_scope_(\d+)$/);
        if (siteMatch) {
          markSection(submitForm.querySelectorAll("[data-site-scope]")[parseInt(siteMatch[1], 10)]);
          return;
        }
        var match = key.match(/^(service_type_id|device_id|result|serial_number|warranty_start|notes|handover_notes|issue_description|photo_guidance_profile_id|photos|before_photos|after_photos)_(\d+)$/);
        if (!match) return;
        var kind = match[1];
        var itemIndex = parseInt(match[2], 10);
        var item = submitForm.querySelectorAll("[data-device-row]")[itemIndex];
        if (!item) return;
        var slot = item.querySelector('[data-error-kind="' + kind + '"]');
        if (!slot && (kind === "before_photos" || kind === "after_photos")) {
          var stage = kind === "before_photos" ? "before" : "after";
          slot = item.querySelector('[data-photo-stage="' + stage + '"] [data-photo-error]');
        }
        if (!slot && kind === "photos") slot = item.querySelector('[data-error-kind="photos"]');
        var field = kind === "result" ? item.querySelector('input[data-name-kind="result"]') : item.querySelector('[name="' + kind + '"]');
        if (kind === "photos" || kind === "before_photos" || kind === "after_photos") {
          var stageName = kind === "before_photos" ? "before" : (kind === "after_photos" ? "after" : "");
          field = stageName ? item.querySelector('[data-photo-stage="' + stageName + '"] input[type="file"][name]') : item.querySelector('input[type="file"][name]');
        }
        showFieldError(field, errors[key], slot);
      });
      var top = submitForm.querySelector("[data-form-error]") || document.querySelector("[data-form-error]");
      if (top) {
        top.textContent = errors.form || "";
        top.style.display = errors.form ? "" : "none";
      }
      var first = submitForm.querySelector('[aria-invalid="true"], [data-error-for]:not([style*="display: none"]), [data-error-kind]:not([style*="display: none"]), [data-photo-error]:not([style*="display: none"])');
      (first || top || submitForm).scrollIntoView({ behavior: "smooth", block: "center" });
      if (first && typeof first.focus === "function") first.focus({ preventScroll: true });
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

  /* -------------------------------------------- quotation bulk selection */
  document.querySelectorAll("[data-quotation-bulk-form]").forEach(function (form) {
    var selectAll = form.querySelector("[data-quotation-select-all]");
    var selections = Array.prototype.slice.call(form.querySelectorAll("[data-quotation-select]"));
    var deleteButton = form.querySelector("[data-quotation-bulk-delete]");
    var countLabel = form.querySelector("[data-quotation-selection-count]");
    if (!selectAll || !deleteButton) return;

    function updateSelection() {
      var selectedCount = selections.filter(function (checkbox) { return checkbox.checked; }).length;
      deleteButton.disabled = selectedCount === 0;
      selectAll.checked = selectedCount > 0 && selectedCount === selections.length;
      selectAll.indeterminate = selectedCount > 0 && selectedCount < selections.length;
      if (countLabel) countLabel.textContent = selectedCount ? selectedCount + " " + (countLabel.dataset.selectionLabel || "selected") : "";
    }
    selectAll.addEventListener("change", function () {
      selections.forEach(function (checkbox) { checkbox.checked = selectAll.checked; });
      updateSelection();
    });
    selections.forEach(function (checkbox) { checkbox.addEventListener("change", updateSelection); });
    form.addEventListener("submit", function (event) {
      if (event.submitter && event.submitter.hasAttribute("formaction")) return;
      if (!window.confirm(form.dataset.bulkConfirm || "Delete the selected quotations?")) {
        event.preventDefault();
      }
    });
    updateSelection();
  });

  /* ------------------------------------------------ purchase documents */
  document.querySelectorAll("[data-purchase-document-form]").forEach(function (form) {
    var catalogueNode = document.getElementById("purchase-catalogue-data");
    var categoryNode = document.getElementById("purchase-category-data");
    var jsonInput = form.querySelector("[data-purchase-selected-json]");
    var selectedHost = form.querySelector("[data-purchase-selected-items]");
    var picker = document.querySelector("[data-purchase-picker]");
    if (!catalogueNode || !categoryNode || !jsonInput || !selectedHost || !picker) return;

    var catalogue = JSON.parse(catalogueNode.textContent || "[]");
    var categories = JSON.parse(categoryNode.textContent || "[]");
    var catalogueByKey = new Map(catalogue.map(function (item) { return [item.key, item]; }));
    var selectedValues = [];
    try { selectedValues = JSON.parse(jsonInput.value || "[]"); } catch (_error) { selectedValues = []; }
    var selected = new Map();
    selectedValues.forEach(function (value) {
      var key = String(value.kind) + ":" + String(value.id);
      if (catalogueByKey.has(key)) selected.set(key, {
        kind: String(value.kind), id: Number(value.id),
        unit_price: String(value.unit_price || ""),
        currency: String(value.currency || catalogueByKey.get(key).currency || "SAR")
      });
    });
    var pickerContent = picker.querySelector("[data-purchase-picker-content]");
    var pickerBack = picker.querySelector("[data-purchase-picker-back]");
    var pickerSearch = picker.querySelector("[data-purchase-picker-search]");
    var countNode = picker.querySelector("[data-purchase-selected-count]");
    var emptyLabel = selectedHost.querySelector("[data-purchase-empty]") ? selectedHost.querySelector("[data-purchase-empty]").textContent : "No items selected yet.";
    var view = { root: null, category: null };

    function sync() {
      jsonInput.value = JSON.stringify(Array.from(selected.values()));
      if (countNode) countNode.textContent = String(selected.size);
    }
    function field(labelText, input) {
      var holder = document.createElement("label");
      holder.className = "field";
      var label = document.createElement("span"); label.textContent = labelText;
      holder.append(label, input);
      return holder;
    }
    function identity(item) {
      var holder = document.createElement("div"); holder.className = "purchase-selected-identity";
      if (item.image_url) {
        var image = document.createElement("img"); image.src = item.image_url; image.alt = item.name; holder.appendChild(image);
      } else {
        var placeholder = document.createElement("span"); placeholder.className = "purchase-selected-placeholder"; placeholder.textContent = item.name.charAt(0).toUpperCase(); holder.appendChild(placeholder);
      }
      var copy = document.createElement("span");
      var name = document.createElement("strong"); name.textContent = item.name; copy.appendChild(name);
      if (item.model || item.is_related) {
        var detail = document.createElement("small");
        detail.textContent = item.is_related ? form.dataset.relatedLabel + " · " + item.parent_name : item.model;
        copy.appendChild(detail);
      }
      holder.appendChild(copy); return holder;
    }
    function renderSelected() {
      selectedHost.replaceChildren();
      if (!selected.size) {
        var empty = document.createElement("p"); empty.className = "empty-state";
        empty.textContent = emptyLabel;
        selectedHost.appendChild(empty); sync(); return;
      }
      selected.forEach(function (value, key) {
        var item = catalogueByKey.get(key); if (!item) return;
        var row = document.createElement("div"); row.className = "purchase-selected-row"; row.appendChild(identity(item));
        var price = document.createElement("input"); price.type = "number"; price.min = "0"; price.step = "0.01"; price.value = value.unit_price;
        price.addEventListener("input", function () { value.unit_price = price.value; sync(); });
        row.appendChild(field(form.dataset.unitPriceLabel, price));
        var currency = document.createElement("select");
        ["SAR", "USD"].forEach(function (code) { var option = document.createElement("option"); option.value = code; option.textContent = code; option.selected = value.currency === code; currency.appendChild(option); });
        currency.addEventListener("change", function () { value.currency = currency.value; sync(); });
        row.appendChild(field(form.dataset.currencyLabel, currency));
        var remove = document.createElement("button"); remove.type = "button"; remove.className = "btn btn-danger btn-sm"; remove.textContent = form.dataset.removeLabel;
        remove.addEventListener("click", function () { selected.delete(key); renderSelected(); renderPicker(); });
        row.appendChild(remove); selectedHost.appendChild(row);
      });
      sync();
    }
    function folder(name, small, onClick) {
      var button = document.createElement("button"); button.type = "button";
      button.className = "pricing-category-folder pricing-picker-folder" + (small ? " pricing-subcategory-folder" : "");
      var icon = document.createElement("span"); icon.className = "pricing-category-folder-icon";
      var copy = document.createElement("span"); copy.className = "pricing-category-folder-copy";
      var strong = document.createElement("strong"); strong.textContent = name; copy.appendChild(strong);
      var arrow = document.createElement("span"); arrow.className = "pricing-category-folder-arrow"; arrow.textContent = "›";
      button.append(icon, copy, arrow); button.addEventListener("click", onClick); return button;
    }
    function itemButton(item) {
      var button = document.createElement("button"); button.type = "button"; button.className = "purchase-item-card purchase-picker-item";
      if (selected.has(item.key)) button.classList.add("is-selected");
      button.appendChild(identity(item));
      var mark = document.createElement("span"); mark.className = "purchase-selected-check"; mark.textContent = selected.has(item.key) ? "✓" : "+"; button.appendChild(mark);
      button.addEventListener("click", function () {
        if (selected.has(item.key)) selected.delete(item.key);
        else selected.set(item.key, { kind: item.kind, id: item.id, unit_price: "", currency: item.currency || "SAR" });
        renderSelected(); renderPicker();
      }); return button;
    }
    function renderPicker() {
      pickerContent.replaceChildren();
      var search = String(pickerSearch.value || "").trim().toLowerCase();
      if (search) {
        var resultGrid = document.createElement("div"); resultGrid.className = "purchase-item-grid";
        catalogue.filter(function (item) { return (item.name + " " + item.model + " " + item.parent_name).toLowerCase().includes(search); }).forEach(function (item) { resultGrid.appendChild(itemButton(item)); });
        pickerContent.appendChild(resultGrid); pickerBack.hidden = true; sync(); return;
      }
      if (!view.root) {
        var roots = document.createElement("div"); roots.className = "pricing-category-folder-grid";
        categories.forEach(function (root) { roots.appendChild(folder(root.name, false, function () { view.root = root; view.category = root.id; renderPicker(); })); });
        if (catalogue.some(function (item) { return item.category_id === null; })) roots.appendChild(folder(form.dataset.uncategorizedLabel, false, function () { view.root = { id: null, name: form.dataset.uncategorizedLabel, children: [] }; view.category = null; renderPicker(); }));
        pickerContent.appendChild(roots); pickerBack.hidden = true; sync(); return;
      }
      pickerBack.hidden = false;
      if (view.category === view.root.id && view.root.children && view.root.children.length) {
        var subfolders = document.createElement("div"); subfolders.className = "pricing-category-folder-grid pricing-subcategory-folder-grid";
        view.root.children.forEach(function (child) { subfolders.appendChild(folder(child.name, true, function () { view.category = child.id; renderPicker(); })); });
        pickerContent.appendChild(subfolders);
      }
      var items = catalogue.filter(function (item) { return item.category_id === view.category; });
      var itemGrid = document.createElement("div"); itemGrid.className = "purchase-item-grid";
      items.forEach(function (item) { itemGrid.appendChild(itemButton(item)); }); pickerContent.appendChild(itemGrid); sync();
    }
    pickerBack.addEventListener("click", function () {
      if (view.root && view.category !== view.root.id) { view.category = view.root.id; }
      else { view.root = null; view.category = null; }
      renderPicker();
    });
    pickerSearch.addEventListener("input", renderPicker);
    form.querySelector("[data-open-purchase-picker]").addEventListener("click", function () { picker.hidden = false; document.body.style.overflow = "hidden"; renderPicker(); });
    picker.querySelectorAll("[data-close-purchase-picker]").forEach(function (button) { button.addEventListener("click", function () { picker.hidden = true; document.body.style.overflow = ""; }); });
    form.addEventListener("submit", sync);
    renderSelected();
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

  // This script is normally deferred, but initialize safely if it is loaded
  // after DOMContentLoaded as well (for example from a restored browser tab).
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeNestedEntryForms, { once: true });
  } else {
    initializeNestedEntryForms();
  }
})();
