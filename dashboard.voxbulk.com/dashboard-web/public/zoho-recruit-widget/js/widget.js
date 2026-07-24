(function () {
  var DASH_BASE = "https://dashboard.voxbulk.com/interviews/new";
  var state = {
    candidateId: "",
    name: "",
  };

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setStatus(msg, isError) {
    var el = $("status");
    if (!el) return;
    el.textContent = msg || "";
    el.className = "status" + (isError ? " err" : " muted");
  }

  function renderCandidate() {
    var box = $("candBox");
    var link = $("openDash");
    if (!state.candidateId) {
      box.innerHTML = '<div class="muted">Open a Candidate in Zoho Recruit to deep-link into VoxBulk.</div>';
      if (link) link.href = DASH_BASE;
      return;
    }
    box.innerHTML =
      "<strong>" +
      escapeHtml(state.name || "Candidate") +
      "</strong>" +
      '<div class="muted">ID: ' +
      escapeHtml(state.candidateId) +
      "</div>";
    if (link) {
      link.href =
        DASH_BASE +
        "?zoho_candidate_id=" +
        encodeURIComponent(state.candidateId) +
        (state.name ? "&zoho_candidate_name=" + encodeURIComponent(state.name) : "");
    }
    setStatus("Open VoxBulk to import this candidate into an interview campaign.");
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
          setStatus("Could not load candidate fields — open VoxBulk and search by Candidate ID.", true);
        });
    } catch (e) {
      setStatus("Could not load candidate fields — open VoxBulk and search by Candidate ID.", true);
    }
  }

  function onPageLoad(data) {
    var entity = (data && (data.Entity || data.module)) || "Candidates";
    var id = data && (data.EntityId || data.entityId || data.id);
    if (Array.isArray(id)) id = id[0];
    if (id) fetchCandidate(entity, id);
    else renderCandidate();
  }

  renderCandidate();

  if (window.ZOHO && ZOHO.embeddedApp) {
    ZOHO.embeddedApp.on("PageLoad", onPageLoad);
    ZOHO.embeddedApp.init().catch(function () {});
  } else {
    setStatus("Zoho SDK not detected — open this widget inside Zoho Recruit after Marketplace install.", true);
  }
})();
