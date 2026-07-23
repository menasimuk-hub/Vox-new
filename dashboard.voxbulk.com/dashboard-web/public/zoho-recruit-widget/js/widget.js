(function () {
  var STORAGE_KEY = "voxbulk_zoho_widget_v1";
  var state = {
    candidateId: "",
    name: "",
    phone: "",
    email: "",
    jobTitle: "AI voice screening",
  };

  function $(id) {
    return document.getElementById(id);
  }

  function loadConfig() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") || {};
    } catch (e) {
      return {};
    }
  }

  function saveConfig(cfg) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg || {}));
  }

  function setStatus(msg, isError) {
    var el = $("status");
    el.textContent = msg || "";
    el.className = "status" + (isError ? " err" : " muted");
  }

  function showSetup(show) {
    $("setup").classList.toggle("hidden", !show);
    $("main").classList.toggle("hidden", show);
  }

  function renderCandidate() {
    var box = $("candBox");
    if (!state.candidateId) {
      box.innerHTML = '<div class="muted">Open a Candidate in Zoho Recruit, then open this widget.</div>';
      return;
    }
    box.innerHTML =
      "<strong>" +
      escapeHtml(state.name || "Candidate") +
      "</strong>" +
      '<div class="muted">ID: ' +
      escapeHtml(state.candidateId) +
      "</div>";
    $("phone").value = state.phone || "";
    $("email").value = state.email || "";
    if (state.jobTitle) $("jobTitle").value = state.jobTitle;
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function pickField(data, keys) {
    for (var i = 0; i < keys.length; i++) {
      var v = data[keys[i]];
      if (v != null && String(v).trim()) return String(v).trim();
    }
    return "";
  }

  function applyRecord(data) {
    var row = data;
    if (data && data.data && data.data[0]) row = data.data[0];
    if (!row || typeof row !== "object") return;
    state.name = pickField(row, ["Full_Name", "Last_Name", "First_Name", "name"]);
    state.phone = pickField(row, ["Mobile", "Phone", "Secondary_Phone", "phone"]);
    state.email = pickField(row, ["Email", "email"]);
    state.jobTitle = pickField(row, ["Current_Job_Title", "Skill_Set"]) || state.jobTitle;
    if (row.id) state.candidateId = String(row.id);
    renderCandidate();
  }

  function fetchCandidate(entity, recordId) {
    state.candidateId = String(recordId || "");
    renderCandidate();
    if (!window.ZOHO || !ZOHO.RECRUIT || !ZOHO.RECRUIT.API) return;
    try {
      ZOHO.RECRUIT.API.getRecord({ Entity: entity || "Candidates", RecordID: recordId })
        .then(function (resp) {
          applyRecord(resp);
        })
        .catch(function () {
          setStatus("Could not load candidate fields from Zoho — enter phone manually.", true);
        });
    } catch (e) {
      setStatus("Could not load candidate fields from Zoho — enter phone manually.", true);
    }
  }

  function onPageLoad(data) {
    var entity = (data && (data.Entity || data.module)) || "Candidates";
    var id = data && (data.EntityId || data.entityId || data.id);
    if (Array.isArray(id)) id = id[0];
    if (id) fetchCandidate(entity, id);
    else renderCandidate();
  }

  async function launch() {
    var cfg = loadConfig();
    var apiKey = String(cfg.api_key || "").trim();
    var apiBase = String(cfg.api_base || "https://api.voxbulk.com").replace(/\/$/, "");
    var phone = $("phone").value.trim();
    var candidateId = state.candidateId;
    if (!apiKey) {
      showSetup(true);
      setStatus("Save your VoxBulk API key first.", true);
      return;
    }
    if (!candidateId) {
      setStatus("Open this widget from a Zoho Candidate record.", true);
      return;
    }
    if (!phone) {
      setStatus("Candidate phone is required.", true);
      return;
    }

    $("launch").disabled = true;
    $("linkOut").classList.add("hidden");
    setStatus("Creating screening…");

    try {
      var res = await fetch(apiBase + "/partner/v1/screenings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey,
          "X-Partner-Name": "zoho",
        },
        body: JSON.stringify({
          partner_reference_id: candidateId,
          job_title: $("jobTitle").value.trim() || "AI voice screening",
          screening_questions: [$("question").value.trim() || "Tell me about your relevant experience for this role."],
          candidate_name: state.name || "Candidate",
          candidate_phone: phone,
          candidate_email: $("email").value.trim() || undefined,
          preferred_language: $("lang").value === "ar" ? "ar" : "en",
        }),
      });
      var body = await res.json().catch(function () {
        return {};
      });
      if (!res.ok) {
        throw new Error(body.detail || body.message || "HTTP " + res.status);
      }
      var link = body.screening_link || "";
      setStatus("Screening created (" + (body.status || "ok") + "). Invite sent when WhatsApp/email is configured.");
      if (link) {
        var a = $("linkOut");
        a.href = link;
        a.textContent = link;
        a.classList.remove("hidden");
      }
    } catch (e) {
      setStatus(e && e.message ? e.message : "Launch failed", true);
    } finally {
      $("launch").disabled = false;
    }
  }

  function bootUi() {
    var cfg = loadConfig();
    $("apiBase").value = cfg.api_base || "https://api.voxbulk.com";
    $("apiKey").value = cfg.api_key || "";
    if (!cfg.api_key) showSetup(true);
    else showSetup(false);

    $("saveSetup").onclick = function () {
      saveConfig({
        api_base: $("apiBase").value.trim() || "https://api.voxbulk.com",
        api_key: $("apiKey").value.trim(),
      });
      showSetup(false);
      setStatus("API key saved on this browser.");
    };
    $("editSetup").onclick = function () {
      showSetup(true);
    };
    $("launch").onclick = function () {
      launch();
    };
    renderCandidate();
  }

  bootUi();

  if (window.ZOHO && ZOHO.embeddedApp) {
    ZOHO.embeddedApp.on("PageLoad", onPageLoad);
    ZOHO.embeddedApp.init();
  } else {
    setStatus("Zoho SDK not detected — open this widget inside Zoho Recruit.", true);
  }
})();
