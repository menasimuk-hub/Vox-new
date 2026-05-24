const bodyHtml = `<div class="app" id="app">

  <!-- ═══ SIDEBAR ═══ -->
  <div class="sb" id="sb">
    <div class="sb-logo">
  <!-- Full logos (shown when sidebar is open) -->
  <img src="/logo-dark.svg" class="logo-light sb-logo-full" style="height:26px;width:auto;object-fit:contain;" />
  <img src="/logo-light.svg"  class="logo-dark  sb-logo-full" style="height:26px;width:auto;object-fit:contain;" />
  <div class="sb-ic sb-logo-icon" style="background:#1a73e8;padding:0;">
    <img src="/favicon.png" style="width:100%;height:100%;object-fit:contain;" />
</div>
  <div class="sb-toggle" onclick="toggleSidebar()" title="Toggle sidebar">
    <i class="ti ti-layout-sidebar-left-collapse" id="sb-tog-ic"></i>
  </div>
</div>

    <div class="sb-nav">
      <div class="ni on" onclick="go('dashboard',this)" data-tip="Dashboard"><i class="ti ti-layout-dashboard nav-ic"></i><span class="ni-label">Dashboard</span><span class="ni-tip">Dashboard</span></div>

      <div class="nav-sec">Recovery</div>
      <div class="ni" onclick="go('queue',this)" data-tip="Recovery queue"><i class="ti ti-phone-incoming nav-ic"></i><span class="ni-label">Recovery queue</span><span class="ni-badge" id="qbadge" style="display:none">0</span><span class="ni-tip">Recovery queue</span></div>
      <div class="ni" onclick="go('noshow',this)" data-tip="No-show follow-up"><i class="ti ti-user-x nav-ic"></i><span class="ni-label">No-show follow-up</span><span class="ni-tip">No-show follow-up</span></div>
      <div class="ni" onclick="go('emergency',this)" data-tip="Emergency reschedule"><i class="ti ti-alert-triangle nav-ic"></i><span class="ni-label">Emergency reschedule</span><span class="ni-tip">Emergency reschedule</span></div>

      <div class="nav-sec">Fill &amp; Grow</div>
      <div class="ni" onclick="go('recall',this)" data-tip="Recall campaigns"><i class="ti ti-refresh nav-ic"></i><span class="ni-label">Recall campaigns</span><span class="ni-tip">Recall campaigns</span></div>
      <div class="ni" onclick="go('offers',this)" data-tip="Offer campaigns"><i class="ti ti-speakerphone nav-ic"></i><span class="ni-label">Offer campaigns</span><span class="ni-tip">Offer campaigns</span></div>

      <div class="nav-sec">Other services</div>
      <div class="ni" onclick="go('interviews',this)" data-tip="Interviews"><i class="ti ti-briefcase nav-ic"></i><span class="ni-label">Interviews</span><span class="ni-tip">Interviews</span></div>
      <div class="ni" onclick="go('surveys',this)" data-tip="Surveys"><i class="ti ti-clipboard-list nav-ic"></i><span class="ni-label">Surveys</span><span class="ni-tip">Surveys</span></div>

      <div class="nav-sec">Data</div>
      <div class="ni" onclick="go('reports',this)" data-tip="Reports"><i class="ti ti-chart-bar nav-ic"></i><span class="ni-label">Reports</span><span class="ni-tip">Reports</span></div>
      <div class="ni" onclick="go('results-i',this)" data-tip="Interview results"><i class="ti ti-chart-dots nav-ic"></i><span class="ni-label">Interview results</span><span class="ni-tip">Interview results</span></div>
      <div class="ni" onclick="go('results-s',this)" data-tip="Survey results"><i class="ti ti-chart-pie nav-ic"></i><span class="ni-label">Survey results</span><span class="ni-tip">Survey results</span></div>

      <div class="nav-sec">Settings</div>
      <div class="ni" onclick="go('reminders',this)" data-tip="Reminder sequences"><i class="ti ti-clock nav-ic"></i><span class="ni-label">Reminder sequences</span><span class="ni-tip">Reminder sequences</span></div>
      <div class="ni" onclick="go('profile',this)" data-tip="Profile settings"><i class="ti ti-building nav-ic"></i><span class="ni-label">Profile settings</span><span class="ni-tip">Profile settings</span></div>
      <div class="ni" onclick="go('system',this)" data-tip="System settings"><i class="ti ti-plug nav-ic"></i><span class="ni-label">System settings</span><span class="ni-dot"></span><span class="ni-tip">System settings</span></div>
      <div class="ni" onclick="go('team',this)" data-tip="Team members"><i class="ti ti-users nav-ic"></i><span class="ni-label">Team members</span><span class="ni-tip">Team members</span></div>
      <div class="ni" onclick="go('optout',this)" data-tip="Opt-out list"><i class="ti ti-ban nav-ic"></i><span class="ni-label">Opt-out list</span><span class="ni-tip">Opt-out list</span></div>
      <div class="ni" onclick="go('audit',this)" data-tip="Audit log"><i class="ti ti-history nav-ic"></i><span class="ni-label">Audit log</span><span class="ni-tip">Audit log</span></div>

      <div class="nav-sec">Account</div>
      <div class="ni" onclick="go('packages',this)" data-tip="Packages &amp; pricing"><i class="ti ti-package nav-ic"></i><span class="ni-label">Packages &amp; pricing</span><span class="ni-tip">Packages</span></div>
      <div class="ni" onclick="go('billing',this)" data-tip="Billing"><i class="ti ti-credit-card nav-ic"></i><span class="ni-label">Billing</span><span class="ni-tip">Billing</span></div>
      <div class="ni" onclick="go('support',this)" data-tip="Support"><i class="ti ti-help-circle nav-ic"></i><span class="ni-label">Support</span><span class="ni-tip">Support</span></div>
    </div>
    <div class="sb-bot">
      <div class="user-row" onclick="go('profile',document.querySelector('.ni'))">
        <div class="uav">BS</div>
        <div class="u-info"><div class="unm">Bright Smiles</div><div class="uplan">Starter plan · Profile area</div></div>
      </div>
      <div class="logout" id="dashboard-logout" role="button" tabindex="0" aria-label="Log out"><i class="ti ti-logout"></i><span class="logout-label">Log out</span></div>
    </div>
  </div>

  <!-- ═══ MAIN ═══ -->
  <div class="main" id="main">
    <div class="topbar">
      <div class="tb-info">
        <div class="tb-title" id="tb-t">Dashboard</div>
        <div class="tb-sub" id="tb-s"><span class="ldot"></span> Live · <span id="tb-s-plain">Overview</span></div>
      </div>
      <div class="tb-r">
        <div class="api-pill"><span class="api-dot"></span>Dentally connected</div>
        <div class="tbbtn" onclick="toggleDark()" title="Toggle dark mode"><i class="ti ti-moon" id="mode-i"></i></div>
        <div class="nbell" style="position:relative">
          <div class="tbbtn" onclick="toggleNotif()"><i class="ti ti-bell"></i></div>
          <div class="npanel" id="npanel" style="display:none">
            <div class="np-hd"><span class="np-t">Notifications</span><span class="bdg br">0 new</span></div>
            <div class="nitem" style="cursor:default"><div class="nic af-b"><i class="ti ti-bell-off"></i></div><div><div class="nt">No notifications yet</div><div class="ns">Alerts will appear here</div></div></div>
          </div>
        </div>
      </div>
    </div>

    <div class="content">

      <!-- ══ DASHBOARD ══ -->
      <div class="pg on" id="pg-dashboard">
        <!-- ROI HERO -->
        <div class="roi-card">
          <div class="roi-ic"><i class="ti ti-trending-up"></i></div>
          <div class="roi-main">
            <div class="roi-val" id="dash-roi-val">£0.00</div>
            <div class="roi-lbl">returned for every £1 spent on VoxBulk this month</div>
            <div class="roi-sub" id="dash-roi-sub">£0 recovered · £0 total cost · 0% call success rate</div>
          </div>
          <div class="roi-actions">
            <button class="roi-btn" onclick="goNav('queue')"><i class="ti ti-phone-incoming"></i>Run AI now</button>
            <button class="roi-btn" onclick="goNav('reports')"><i class="ti ti-download"></i>Export report</button>
          </div>
        </div>
        <!-- QUICK ACTIONS -->
        <div class="qa-row">
          <button class="qa-btn primary" onclick="goNav('queue')"><i class="ti ti-phone-incoming"></i>Recovery queue<span class="qa-sub" id="dash-qa-queue">0 patients waiting</span></button>
          <button class="qa-btn" onclick="goNav('emergency')"><i class="ti ti-alert-triangle" style="color:var(--red)"></i>Emergency reschedule<span class="qa-sub">Cancel a day instantly</span></button>
          <button class="qa-btn" onclick="goNav('recall')"><i class="ti ti-refresh" style="color:var(--pur)"></i>Recall campaign<span class="qa-sub" id="dash-qa-recall">0 overdue patients</span></button>
          <button class="qa-btn" onclick="goNav('reports')"><i class="ti ti-chart-bar" style="color:var(--blu)"></i>View reports<span class="qa-sub">Full analytics</span></button>
        </div>
        <div class="kg4">
          <div class="kpi gt"><div class="kl">Est. recovered today</div><div class="kv" id="dash-kpi-recovered-today">£0</div><div class="kd ne">0% vs yesterday</div></div>
          <div class="kpi"><div class="kl">Calls made</div><div class="kv" id="dash-kpi-calls-made">0</div><div class="kd ne">0% recovery rate</div></div>
          <div class="kpi"><div class="kl">No-shows contacted</div><div class="kv" id="dash-kpi-noshows">0</div><div class="kd ne">0 unreachable</div></div>
          <div class="kpi"><div class="kl">WhatsApp open rate</div><div class="kv" id="dash-kpi-wa-rate">0%</div><div class="kd ne" id="dash-kpi-wa-sent">0 sent today</div></div>
        </div>
        <div class="kg4">
          <div class="kpi"><div class="kl">Queue pending</div><div class="kv" style="color:var(--amb)" id="dash-kpi-queue">0</div><div class="kd ne">No pending items</div></div>
          <div class="kpi"><div class="kl">Avg call length</div><div class="kv" id="dash-kpi-avg-call">0m 00s</div><div class="kd ne">Per outbound call</div></div>
          <div class="kpi"><div class="kl">Monthly cost</div><div class="kv" id="dash-kpi-cost">£0</div><div class="kd ne">All channels</div></div>
          <div class="kpi"><div class="kl">Monthly target</div><div class="kv" style="color:var(--grn)" id="dash-kpi-target-pct">0%</div><div class="kd ne" id="dash-kpi-target-amt">£0 / £0</div></div>
        </div>
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><span style="font-size:13px;font-weight:600;color:var(--t1)">Est. revenue recovered this month</span><span style="font-size:13px;color:var(--grn);font-weight:700" id="dash-rv-label">£0 / £0</span></div>
          <div class="rvbar"><div class="rvfill" id="dash-rv-fill" style="width:0%"></div></div>
          <div style="font-size:11px;color:var(--t3)">Based on £85 avg appointment value · <span style="color:var(--blu);cursor:pointer;text-decoration:underline" onclick="go('profile',document.querySelector('.ni'))">Update in profile settings</span></div>
        </div>
        <div class="g2">
          <div class="card" style="margin:0">
            <div class="ch"><i class="ti ti-activity grn"></i>Live activity feed</div>
            <div class="af" id="dash-activity-empty"><div class="af-ic af-b"><i class="ti ti-clock"></i></div><div><div class="at">No activity yet</div><div class="as">Activity will appear here when you start using VoxBulk</div></div></div>
          </div>
          <div class="card" style="margin:0">
            <div class="ch"><i class="ti ti-calendar grn"></i>Today's schedule</div>
            <div style="display:flex;flex-direction:column;gap:6px" id="dash-schedule">
              <div class="sl"><div class="sl-t">—</div><div class="sl-c mt"><span class="sdot sr"></span><div class="qi"><div class="qn">No appointments scheduled</div><div class="qd">Connect your booking API to sync today's schedule</div></div></div></div>
            </div>
          </div>
        </div>
        <div class="card" style="margin-top:12px">
          <div class="ch"><i class="ti ti-chart-line grn"></i>Calls this week</div>
          <div class="brs"><div class="br-b" style="height:4%"></div><div class="br-b dm" style="height:4%"></div><div class="br-b dm" style="height:4%"></div><div class="br-b dm" style="height:4%"></div><div class="br-b dm" style="height:4%"></div><div class="br-b on" style="height:4%"></div><div class="br-b" style="height:4%;opacity:.3"></div></div>
          <div class="brl"><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span style="color:var(--grn);font-weight:700">Sat</span><span>Sun</span></div>
        </div>
      </div>

      <!-- ══ QUEUE ══ -->
      <div class="pg" id="pg-queue">
        <div class="kg2" style="margin-bottom:12px">
          <div class="kpi"><div class="kl">Pending today</div><div class="kv" style="color:var(--amb)">12</div><div class="kd am">Needs action</div></div>
          <div class="kpi"><div class="kl">Rebooked today</div><div class="kv" style="color:var(--grn)">31</div><div class="kd up">37% success rate</div></div>
        </div>
        <div class="card">
          <div style="display:flex;gap:8px;margin-bottom:13px;flex-wrap:wrap;align-items:center">
            <select style="font-size:12px;padding:6px 9px;border-radius:8px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1)"><option>All statuses</option><option>Calling now</option><option>No answer</option><option>Rebooked</option></select>
            <select style="font-size:12px;padding:6px 9px;border-radius:8px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1)"><option>Today</option><option>Last 7 days</option></select>
            <button class="btn btng bsm" style="margin-left:auto"><i class="ti ti-player-play"></i>Run AI calling now</button>
          </div>
          <div class="qr"><div class="av av-a">SJ</div><div class="qi"><div class="qn">Sarah Johnson · +44 7700 900123</div><div class="qd">Missed 2:30pm · Check-up · Est. £90</div></div><span class="bdg ba"><i class="ti ti-phone" style="font-size:11px"></i>Calling</span></div>
          <div class="qr"><div class="av av-p">MR</div><div class="qi"><div class="qn">Marco Rossi · +44 7700 900456</div><div class="qd">Missed 11:00am · Hygiene · Est. £55</div></div><span class="bdg br">No answer ×2</span></div>
          <div class="qr"><div class="av av-g">AL</div><div class="qi"><div class="qn">Aisha Lee · +44 7700 900789</div><div class="qd">Missed 9:15am · Check-up · Rebooked Mon</div></div><span class="bdg bg"><i class="ti ti-check" style="font-size:11px"></i>Rebooked</span></div>
          <div class="qr"><div class="av av-b">PT</div><div class="qi"><div class="qn">Paul Torres · +44 7700 900321</div><div class="qd">Missed yesterday 4pm · Consultation</div></div><span class="bdg bb">WhatsApp sent</span></div>
          <div class="qr"><div class="av av-p">KN</div><div class="qi"><div class="qn">Kim Nguyen · +44 7700 900654</div><div class="qd">Missed yesterday 1:30pm · Check-up</div></div><span class="bdg br">Declined</span></div>
        </div>
      </div>

      <!-- ══ NOSHOW ══ -->
      <div class="pg" id="pg-noshow">
        <div class="kg2" style="margin-bottom:12px">
          <div class="kpi"><div class="kl">No-shows today</div><div class="kv">7</div></div>
          <div class="kpi"><div class="kl">Rebooked</div><div class="kv" style="color:var(--grn)">4</div><div class="kd up">57% success</div></div>
        </div>
        <div class="card">
          <div class="ch"><i class="ti ti-settings grn"></i>Follow-up settings</div>
          <div class="fg"><label>Opening message (AI will say this)</label><textarea rows="2" style="resize:none">Hi, I'm Aria, an AI assistant from {clinic_name}. This call may be recorded. We noticed you missed your appointment — can we help you rebook?</textarea></div>
          <div class="fg2"><div class="fg"><label>Max call attempts</label><select><option>1</option><option selected>2</option><option>3</option></select></div><div class="fg"><label>WhatsApp fallback</label><select><option selected>Yes — after 2nd attempt</option><option>No</option></select></div></div>
          <button class="btn btng bsm">Save settings</button>
        </div>
      </div>

      <!-- ══ EMERGENCY ══ -->
      <div class="pg" id="pg-emergency">
        <div class="inf r"><i class="ti ti-alert-triangle"></i>This triggers AI calls to all affected patients. Review the cost estimate below before confirming.</div>
        <div class="card">
          <div class="ch"><i class="ti ti-alert-triangle red"></i>Emergency reschedule</div>
          <div class="fg2"><div class="fg"><label>Date to cancel</label><input type="date" value="2026-05-16"/></div><div class="fg"><label>Scope</label><select><option>Entire day</option><option selected>From a time onwards</option><option>Time window only</option></select></div></div>
          <div class="fg2"><div class="fg"><label>From time</label><input type="time" value="09:00"/></div><div class="fg"><label>To time</label><input type="time" value="13:00"/></div></div>
          <div class="fg"><label>Reason (AI will mention this)</label><input value="Unexpected staff emergency"/></div>
          <div class="fg"><label>Alternative slots to offer</label><input placeholder="e.g. tomorrow 9am–12pm, next Monday all day"/></div>
          <div class="inf a"><i class="ti ti-calculator"></i>12 appointments affected · £4.80 calls + £1.20 WhatsApp = <strong>£6.00 total estimated cost</strong></div>
          <button class="btn btng"><i class="ti ti-phone"></i>Start AI calling — 12 patients</button>
        </div>
      </div>

      <!-- ══ RECALL ══ -->
      <div class="pg" id="pg-recall">
        <div class="inf g"><i class="ti ti-info-circle"></i>Dental recall only — AI contacts patients overdue for check-ups or hygiene. Visible to Dental accounts only.</div>
        <div class="kg4">
          <div class="kpi"><div class="kl">Overdue patients</div><div class="kv">143</div><div class="kd am">12+ months</div></div>
          <div class="kpi"><div class="kl">Contacted this month</div><div class="kv">38</div></div>
          <div class="kpi"><div class="kl">Booked from recall</div><div class="kv">10</div><div class="kd up">26% success</div></div>
          <div class="kpi"><div class="kl">Recall revenue (est.)</div><div class="kv" style="color:var(--grn)">£940</div><div class="kd up">This month</div></div>
        </div>
        <div class="card">
          <div class="ch"><i class="ti ti-settings grn"></i>Recall settings</div>
          <div class="fg2"><div class="fg"><label>Recall interval</label><select><option>6 months</option><option selected>12 months</option><option>18 months</option></select></div><div class="fg"><label>Appointment types</label><select><option selected>Check-up + Hygiene</option><option>Hygiene only</option><option>Check-up only</option></select></div></div>
          <div class="fg2"><div class="fg"><label>Contact method</label><select><option selected>Call first, WhatsApp fallback</option><option>WhatsApp only</option><option>Call only</option></select></div><div class="fg"><label>Max bookings / week</label><input type="number" value="20"/></div></div>
          <div class="fg"><label>AI message</label><textarea rows="2" style="resize:none">Hi {first_name}, it's been a while since your last visit at {clinic_name}. We'd love to book you in for a check-up — do you have a moment?</textarea></div>
          <button class="btn btng bsm"><i class="ti ti-player-play"></i>Launch recall campaign</button>
        </div>
      </div>

      <!-- ══ OFFERS ══ -->
      <div class="pg" id="pg-offers">
        <div class="camp"><div class="camp-ic ci-g"><i class="ti ti-sun"></i></div><div class="camp-info"><div class="camp-nm">Summer skin offer <span class="bdg bg" style="margin-left:8px">Live</span></div><div class="camp-sub">20% off chemical peels · Beauty clinic</div><div class="prog-b"><div class="prog-f" style="width:76%"></div></div><div style="font-size:10.5px;color:var(--t3)">38 booked of 50 cap</div></div></div>
        <div class="camp"><div class="camp-ic ci-b"><i class="ti ti-eye"></i></div><div class="camp-info"><div class="camp-nm">Back-to-school eye tests <span class="bdg bb" style="margin-left:8px">Aug 1</span></div><div class="camp-sub">Free eye test for under-16s · Optician</div><div class="prog-b"><div class="prog-f" style="width:0%"></div></div><div style="font-size:10.5px;color:var(--t3)">Not yet started</div></div></div>
        <div class="card">
          <div class="ch"><i class="ti ti-plus grn"></i>New offer campaign</div>
          <div class="fg"><label>Campaign name</label><input placeholder="e.g. January skin offer"/></div>
          <div class="fg"><label>Offer description</label><input placeholder="e.g. 20% off all chemical peels this January"/></div>
          <div class="fg2"><div class="fg"><label>Booking method</label><select><option selected>AI calls to book</option><option>WhatsApp + booking link</option><option>Both</option></select></div><div class="fg"><label>Max bookings cap</label><input type="number" value="30"/></div></div>
          <div style="display:flex;gap:8px"><button class="btn btng bsm"><i class="ti ti-sparkles"></i>AI write message</button><button class="btn bsm">Next — choose audience</button></div>
        </div>
      </div>

      <!-- ══ INTERVIEWS ══ -->
      <div class="pg" id="pg-interviews">
        <!-- LIVE BANNER -->
        <div class="live-banner" id="int-live-banner" style="display:none">
          <div class="live-pulse"></div>
          <div class="lb-info">
            <div class="lb-title">Campaign live — Senior Engineer · May 2026</div>
            <div class="lb-sub">AI calling now · Window: 19 May 09:00 → 23 May 17:00 · 5 of 8 called</div>
          </div>
          <button class="btn bsm btnr" onclick="showConfirm('Stop this campaign?','This will immediately halt all outbound AI calls. Calls already connected will finish naturally.','Stop campaign',function(){toast('Campaign stopped','ta');document.getElementById(\\'int-live-banner\\').style.display=\\'none\\';})"><i class="ti ti-player-stop"></i>Stop</button>
        </div>
        <div class="kg2" style="margin-bottom:12px">
          <div class="kpi"><div class="kl">Credits remaining</div><div class="kv">0</div><div class="kd ne">of 0 bundle</div></div>
          <div class="kpi"><div class="kl">Completed this month</div><div class="kv">0</div><div class="kd ne">0% reached</div></div>
        </div>
        <!-- ACTIVE PROJECTS -->
        <div class="card">
          <div class="ch"><i class="ti ti-briefcase grn"></i>Projects</div>
          <div id="int-live-orders"></div>
          <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--b1)" id="int-projects-empty">
            <div class="empty-state" style="padding:16px 0">
              <i class="ti ti-plus-circle"></i>
              <div class="es-title">Start a new interview campaign</div>
              <div class="es-sub">Upload your candidate list and the AI will screen them automatically within your defined calling window.</div>
            </div>
          </div>
        </div>
        <!-- NEW CAMPAIGN FORM -->
        <div class="card">
          <div class="ch"><i class="ti ti-upload grn"></i>New interview campaign</div>
          <div class="standalone-upload" id="int-upload-zone" style="margin-bottom:12px;cursor:pointer"><i class="ti ti-file-spreadsheet" style="font-size:24px;display:block;margin-bottom:6px;color:var(--t3)"></i>Drop Excel / CSV · Required: name, phone · Optional: email<br/><a href="#" id="int-template-dl" style="font-size:11px;color:var(--grn);margin-top:6px;display:inline-block">Download sample template</a><input type="file" id="int-file-input" accept=".csv,.xlsx,.xls" style="display:none"/></div>
          <div class="fg"><label>Role / position</label><input id="int-role" placeholder="e.g. Senior Software Engineer · London"/></div>
          <div class="fg"><label>Interview format</label>
            <div style="display:flex;gap:7px" id="int-fmt-grp">
              <div class="vo sel" onclick="selFmt(this,'int-fmt-grp')" style="padding:9px">Phone call<small>AI calls candidate</small></div>
              <div class="vo" onclick="selFmt(this,'int-fmt-grp')" style="padding:9px">Zoom<small>AI sends link + books</small></div>
            </div>
          </div>
          <div class="fg"><label>Screening criteria (AI generates questions from this)</label><textarea id="int-criteria" rows="2" style="resize:none" placeholder="e.g. Check 2+ years React, comfortable remote, available in 2 weeks, salary expectation"></textarea></div>
          <div id="int-ai-panel" style="display:none;margin-bottom:10px;background:var(--s2);border-radius:11px;padding:13px;border:1.5px solid var(--b2)">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
              <span style="font-size:12px;font-weight:700;color:var(--t1)"><i class="ti ti-sparkles" style="color:var(--grn)"></i> AI-generated interview script</span>
              <span class="bdg ba" id="int-ai-status">Draft</span>
            </div>
            <div class="fg" style="margin-bottom:8px"><label>Review and edit before approving</label><textarea id="int-ai-script" rows="10" style="resize:vertical;font-size:12px;line-height:1.6" placeholder="Click Generate AI questions to create a script you can read here…"></textarea></div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <button class="btn btng bsm" type="button" id="int-ai-approve"><i class="ti ti-check"></i>Approve script</button>
              <button class="btn bsm" type="button" id="int-ai-regen"><i class="ti ti-refresh"></i>Regenerate</button>
            </div>
          </div>
          <!-- CALLING WINDOW -->
          <div style="background:var(--s2);border-radius:11px;padding:13px;margin-bottom:10px">
            <div style="font-size:11px;font-weight:700;color:var(--t3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px;display:flex;align-items:center;gap:6px"><i class="ti ti-clock" style="color:var(--grn);font-size:14px"></i>AI calling window — system stops automatically at end time</div>
            <div class="fg2">
              <div class="fg" style="margin-bottom:0"><label><i class="ti ti-player-play" style="color:var(--grn);font-size:12px;margin-right:3px"></i>Start date</label><input type="date" id="int-start-date" oninput="updateIntWindow()"/></div>
              <div class="fg" style="margin-bottom:0"><label>Start time</label><input type="time" id="int-start-time" value="09:00" oninput="updateIntWindow()"/></div>
            </div>
            <div class="fg2" style="margin-top:8px">
              <div class="fg" style="margin-bottom:0"><label><i class="ti ti-player-stop" style="color:var(--red);font-size:12px;margin-right:3px"></i>End date</label><input type="date" id="int-end-date" oninput="updateIntWindow()"/></div>
              <div class="fg" style="margin-bottom:0"><label>End time</label><input type="time" id="int-end-time" value="17:00" oninput="updateIntWindow()"/></div>
            </div>
            <div id="int-window-preview" style="display:none;margin-top:10px;background:var(--gd);border-radius:8px;padding:8px 11px;font-size:11.5px;color:var(--grn);font-weight:500;align-items:center;gap:7px">
              <i class="ti ti-check"></i><span id="int-window-text"></span>
            </div>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn btng bsm" type="button" id="int-ai-generate"><i class="ti ti-sparkles"></i>Generate AI questions</button>
            <button class="btn bsm" onclick="launchIntCampaign()"><i class="ti ti-player-play"></i>Launch interviews</button>
          </div>
        </div>
      </div>

      <!-- ══ SURVEYS ══ -->
      <div class="pg" id="pg-surveys">
        <!-- LIVE BANNER -->
        <div class="live-banner" id="sur-live-banner" style="display:none">
          <div class="live-pulse"></div>
          <div class="lb-info">
            <div class="lb-title">No live survey</div>
            <div class="lb-sub">0 of 0 responded · No active window</div>
          </div>
          <button class="btn bsm btnr" onclick="showConfirm('Stop this survey?','This will halt all outbound survey calls. Results collected so far will be saved.','Stop survey',function(){toast('Survey stopped','ta');})"><i class="ti ti-player-stop"></i>Stop</button>
        </div>
        <!-- ACTIVE PROJECTS -->
        <div class="card">
          <div class="ch"><i class="ti ti-clipboard-list grn"></i>Survey projects</div>
          <div id="sur-live-orders"></div>
          <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--b1)" id="sur-projects-empty">
            <div class="empty-state" style="padding:16px 0">
              <i class="ti ti-plus-circle"></i>
              <div class="es-title">No survey projects yet</div>
              <div class="es-sub">Create a new survey campaign below — upload your contact list and launch when ready.</div>
            </div>
          </div>
        </div>
        <!-- NEW CAMPAIGN FORM -->
        <div class="card">
          <div class="ch"><i class="ti ti-plus grn"></i>New survey campaign</div>
          <div class="sur-launch-note"><i class="ti ti-phone"></i> AI phone call surveys · Phase 1</div>
          <div class="fg"><label>What do you want to learn?</label><textarea id="sur-goal" rows="2" style="resize:none" placeholder="e.g. Patient satisfaction — experience, wait times, likelihood to recommend"></textarea></div>
          <div class="fg"><label>Max call length</label><select id="sur-max-length"><option selected>3 minutes</option><option>5 minutes</option><option>10 minutes</option></select></div>
          <div class="fg" id="sur-agent-field" style="margin-bottom:10px"><label>AI voice agent</label><select id="sur-agent-select"><option value="">Loading agents…</option></select><div class="muted" style="font-size:11px;margin-top:4px">Friendly voice shown on your survey calls — no technical IDs.</div></div>
          <input type="file" id="sur-file-input" accept=".csv,.xlsx,.xls" hidden/>
          <div class="standalone-upload" id="sur-upload-zone" style="margin-bottom:6px"><label for="sur-file-input" class="sur-upload-trigger"><i class="ti ti-upload" style="font-size:24px;display:block;margin-bottom:6px;color:var(--t3)"></i>Upload contact list · CSV/Excel: name, phone, email</label><a href="#" id="sur-template-dl" style="font-size:11px;color:var(--grn);margin-top:6px;display:inline-block">Download sample template</a></div>
          <div id="sur-upload-filename" class="muted" style="font-size:11px;margin-bottom:12px;display:none"></div>
          <div id="sur-ai-panel" style="display:none;margin-bottom:10px;background:var(--s2);border-radius:11px;padding:13px;border:1.5px solid var(--b2)">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
              <span style="font-size:12px;font-weight:700;color:var(--t1)"><i class="ti ti-sparkles" style="color:var(--grn)"></i> AI-generated survey script</span>
              <span class="bdg ba" id="sur-ai-status">Draft</span>
            </div>
            <div class="fg" style="margin-bottom:8px"><label>Review and edit before approving</label><textarea id="sur-ai-script" rows="10" style="resize:vertical;font-size:12px;line-height:1.6" placeholder="Click AI write survey script to generate questions you can read here…"></textarea></div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <button class="btn btng bsm" type="button" id="sur-ai-approve"><i class="ti ti-check"></i>Approve script</button>
              <button class="btn bsm" type="button" id="sur-ai-regen"><i class="ti ti-refresh"></i>Regenerate</button>
            </div>
          </div>
          <!-- CALLING WINDOW -->
          <div style="background:var(--s2);border-radius:11px;padding:13px;margin-bottom:10px">
            <div style="font-size:11px;font-weight:700;color:var(--t3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px;display:flex;align-items:center;gap:6px"><i class="ti ti-clock" style="color:var(--grn);font-size:14px"></i>AI calling window — system stops automatically at end time</div>
            <div class="fg2">
              <div class="fg" style="margin-bottom:0"><label><i class="ti ti-player-play" style="color:var(--grn);font-size:12px;margin-right:3px"></i>Start date</label><input type="date" id="sur-start-date" oninput="updateSurWindow()"/></div>
              <div class="fg" style="margin-bottom:0"><label>Start time</label><input type="time" id="sur-start-time" value="09:00" oninput="updateSurWindow()"/></div>
            </div>
            <div class="fg2" style="margin-top:8px">
              <div class="fg" style="margin-bottom:0"><label><i class="ti ti-player-stop" style="color:var(--red);font-size:12px;margin-right:3px"></i>End date</label><input type="date" id="sur-end-date" oninput="updateSurWindow()"/></div>
              <div class="fg" style="margin-bottom:0"><label>End time</label><input type="time" id="sur-end-time" value="17:00" oninput="updateSurWindow()"/></div>
            </div>
            <div id="sur-window-preview" style="display:none;margin-top:10px;background:var(--gd);border-radius:8px;padding:8px 11px;font-size:11.5px;color:var(--grn);font-weight:500;align-items:center;gap:7px">
              <i class="ti ti-check"></i><span id="sur-window-text"></span>
            </div>
          </div>
          <!-- PACKAGE + QUOTE -->
          <div id="sur-launch-pricing" class="sur-launch-pricing" hidden>
            <div class="sur-launch-pricing-head"><i class="ti ti-receipt"></i> Package &amp; pricing</div>
            <div id="sur-contact-count" class="sur-launch-meta muted"></div>
            <div class="fg" style="margin-bottom:8px"><label>AI call package</label><select id="sur-package-select"></select></div>
            <div id="sur-quote-breakdown" class="sur-quote-breakdown"></div>
            <div id="sur-quote-total" class="sur-quote-total"></div>
            <div id="sur-quote-status" class="sur-quote-status muted"></div>
          </div>
          <div id="sur-validation-errors" class="validation-error" style="display:none;margin-bottom:10px"></div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px">
            <button class="btn btng bsm" type="button" id="sur-ai-generate"><i class="ti ti-sparkles"></i>AI write survey script</button>
            <button class="btn btng bsm" type="button" id="sur-pay-schedule"><i class="ti ti-credit-card"></i>Pay and schedule survey</button>
          </div>
        </div>
      </div>

      <!-- ══ REPORTS ══ -->
      <div class="pg" id="pg-reports">
        <!-- Date range picker -->
        <div class="drp">
          <span style="font-size:11.5px;color:var(--t2);font-weight:600;margin-right:4px">Period:</span>
          <button class="drp-opt" onclick="drpSel(this)">Today</button>
          <button class="drp-opt" onclick="drpSel(this)">This week</button>
          <button class="drp-opt on" onclick="drpSel(this)">This month</button>
          <button class="drp-opt" onclick="drpSel(this)">Last month</button>
          <button class="drp-opt" onclick="drpSel(this)">Custom</button>
          <button class="btn btng bsm" style="margin-left:auto"><i class="ti ti-download"></i>Export CSV</button>
          <button class="btn bsm"><i class="ti ti-file-type-pdf"></i>PDF report</button>
        </div>
        <!-- ROI summary -->
        <div class="roi-card" style="margin-bottom:12px">
          <div class="roi-ic"><i class="ti ti-coin"></i></div>
          <div class="roi-main">
            <div class="roi-val">£25.50</div>
            <div class="roi-lbl">returned per £1 spent — May 2026</div>
            <div class="roi-sub">Best month on record · +22% vs April</div>
          </div>
        </div>
        <div class="kg4">
          <div class="kpi gt"><div class="kl">Est. recovered (month)</div><div class="kv">£4,650</div><div class="kd up">+22% vs last month</div></div>
          <div class="kpi"><div class="kl">Total calls</div><div class="kv">421</div><div class="kd up">37% recovery rate</div></div>
          <div class="kpi"><div class="kl">WhatsApp sent</div><div class="kv">310</div><div class="kd up">89% open rate</div></div>
          <div class="kpi"><div class="kl">Total cost</div><div class="kv">£182</div><div class="kd ne">This month</div></div>
        </div>
        <div class="g2">
          <div class="card" style="margin:0">
            <div class="ch"><i class="ti ti-chart-bar grn"></i>Recovery by source</div>
            <div class="crit-row"><div class="crit-lbl">Dentally</div><div class="crit-bar"><div class="crit-fill" style="width:72%"></div></div><div class="crit-val">72%</div></div>
            <div class="crit-row"><div class="crit-lbl">Phorest</div><div class="crit-bar"><div class="crit-fill" style="width:55%;background:var(--pur)"></div></div><div class="crit-val">55%</div></div>
            <div class="crit-row"><div class="crit-lbl">Manual upload</div><div class="crit-bar"><div class="crit-fill" style="width:38%;background:var(--amb)"></div></div><div class="crit-val">38%</div></div>
          </div>
          <div class="card" style="margin:0">
            <div class="ch"><i class="ti ti-receipt grn"></i>Cost breakdown (this month)</div>
            <div class="qr"><i class="ti ti-phone" style="font-size:14px;color:var(--t3)"></i><span style="font-size:12px;color:var(--t1);flex:1">Call minutes (940 min)</span><span style="font-size:13px;font-weight:700;color:var(--t1)">£94</span></div>
            <div class="qr"><i class="ti ti-message" style="font-size:14px;color:var(--t3)"></i><span style="font-size:12px;color:var(--t1);flex:1">WhatsApp (310 msgs)</span><span style="font-size:13px;font-weight:700;color:var(--t1)">£62</span></div>
            <div class="qr"><i class="ti ti-cpu" style="font-size:14px;color:var(--t3)"></i><span style="font-size:12px;color:var(--t1);flex:1">AI processing</span><span style="font-size:13px;font-weight:700;color:var(--t1)">£26</span></div>
            <div class="qr" style="border:none"><span style="font-size:13px;font-weight:700;color:var(--t1);flex:1">Total</span><span style="font-size:15px;font-weight:700;color:var(--grn)">£182</span></div>
          </div>
        </div>
        <div class="card">
          <div class="ch"><i class="ti ti-chart-line grn"></i>Calls this month — daily</div>
          <div class="brs" style="height:70px">
            <div class="br-b dm" style="height:40%"></div><div class="br-b dm" style="height:55%"></div><div class="br-b dm" style="height:35%"></div><div class="br-b dm" style="height:70%"></div>
            <div class="br-b dm" style="height:60%"></div><div class="br-b dm" style="height:80%"></div><div class="br-b dm" style="height:45%"></div><div class="br-b dm" style="height:90%"></div>
            <div class="br-b dm" style="height:65%"></div><div class="br-b dm" style="height:75%"></div><div class="br-b dm" style="height:50%"></div><div class="br-b dm" style="height:85%"></div>
            <div class="br-b dm" style="height:55%"></div><div class="br-b dm" style="height:70%"></div><div class="br-b dm" style="height:40%"></div><div class="br-b dm" style="height:95%"></div>
            <div class="br-b dm" style="height:60%"></div><div class="br-b on" style="height:100%"></div><div class="br-b" style="height:10%;opacity:.3"></div>
          </div>
          <div class="brl"><span>1 May</span><span>5</span><span>9</span><span>13</span><span>17</span><span style="color:var(--grn);font-weight:700">Today</span></div>
        </div>
      </div>

      <!-- ══ INTERVIEW RESULTS ══ -->
      <div class="pg" id="pg-results-i">
        <div class="breadcrumb">
          <span class="bc-link" onclick="goNav('interviews')"><i class="ti ti-briefcase" style="font-size:11px"></i> Interviews</span>
          <span class="bc-sep">›</span>
          <span class="bc-cur">Senior Engineer · May 2026</span>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px">
          <button class="btn bsm" onclick="goNav('interviews')"><i class="ti ti-arrow-left"></i>Back to interviews</button>
          <div style="display:flex;gap:8px"><button class="btn btng bsm"><i class="ti ti-download"></i>Export PDF</button><button class="btn bsm"><i class="ti ti-table"></i>Export CSV</button></div>
        </div>
        <div class="kg4">
          <div class="kpi"><div class="kl">Called</div><div class="kv">8</div></div>
          <div class="kpi"><div class="kl">Reached</div><div class="kv">8</div><div class="kd up">100%</div></div>
          <div class="kpi"><div class="kl">Recommended</div><div class="kv" style="color:var(--grn)">5</div><div class="kd up">Advance</div></div>
          <div class="kpi"><div class="kl">Avg duration</div><div class="kv">7m 20s</div></div>
        </div>
        <div class="card">
          <div class="ch"><i class="ti ti-users grn"></i>Candidates — click to view recording &amp; transcript</div>
          <table class="res-table">
            <thead>
              <tr><th>Candidate</th><th>Duration</th><th>Task</th><th>Score</th><th>Recommendation</th><th>Sentiment</th><th></th></tr>
            </thead>
            <tbody>
              <tr onclick="showRec('James Davies','7m 14s','Senior Engineer screening','Enthusiastic')">
                <td><div style="display:flex;align-items:center;gap:9px"><div class="av av-g" style="width:28px;height:28px;font-size:10px">JD</div>James Davies</div></td>
                <td><i class="ti ti-clock" style="color:var(--t3);font-size:12px"></i> 7m 14s</td>
                <td>Interview screening</td>
                <td><div class="stars"><i class="ti ti-star star"></i><i class="ti ti-star star"></i><i class="ti ti-star star"></i><i class="ti ti-star star"></i><i class="ti ti-star star e"></i></div></td>
                <td><span class="bdg bg">Advance</span></td>
                <td><span class="bdg bp">Enthusiastic</span></td>
                <td><button class="btn bsm bxsm"><i class="ti ti-player-play"></i>Play</button></td>
              </tr>
              <tr onclick="showRec('Aisha Mohammed','8m 02s','Senior Engineer screening','Enthusiastic')">
                <td><div style="display:flex;align-items:center;gap:9px"><div class="av av-b" style="width:28px;height:28px;font-size:10px">AM</div>Aisha Mohammed</div></td>
                <td><i class="ti ti-clock" style="color:var(--t3);font-size:12px"></i> 8m 02s</td>
                <td>Interview screening</td>
                <td><div class="stars"><i class="ti ti-star star"></i><i class="ti ti-star star"></i><i class="ti ti-star star"></i><i class="ti ti-star star"></i><i class="ti ti-star star"></i></div></td>
                <td><span class="bdg bg">Advance</span></td>
                <td><span class="bdg bp">Enthusiastic</span></td>
                <td><button class="btn bsm bxsm"><i class="ti ti-player-play"></i>Play</button></td>
              </tr>
              <tr onclick="showRec('Raj Kumar','6m 44s','Senior Engineer screening','Neutral')">
                <td><div style="display:flex;align-items:center;gap:9px"><div class="av av-a" style="width:28px;height:28px;font-size:10px">RK</div>Raj Kumar</div></td>
                <td><i class="ti ti-clock" style="color:var(--t3);font-size:12px"></i> 6m 44s</td>
                <td>Interview screening</td>
                <td><div class="stars"><i class="ti ti-star star"></i><i class="ti ti-star star"></i><i class="ti ti-star star"></i><i class="ti ti-star star e"></i><i class="ti ti-star star e"></i></div></td>
                <td><span class="bdg ba">Hold</span></td>
                <td><span class="bdg bb">Neutral</span></td>
                <td><button class="btn bsm bxsm"><i class="ti ti-player-play"></i>Play</button></td>
              </tr>
              <tr onclick="showRec('Lisa Wong','5m 30s','Senior Engineer screening','Hesitant')">
                <td><div style="display:flex;align-items:center;gap:9px"><div class="av av-r" style="width:28px;height:28px;font-size:10px">LW</div>Lisa Wong</div></td>
                <td><i class="ti ti-clock" style="color:var(--t3);font-size:12px"></i> 5m 30s</td>
                <td>Interview screening</td>
                <td><div class="stars"><i class="ti ti-star star"></i><i class="ti ti-star star"></i><i class="ti ti-star star e"></i><i class="ti ti-star star e"></i><i class="ti ti-star star e"></i></div></td>
                <td><span class="bdg br">Decline</span></td>
                <td><span class="bdg br">Hesitant</span></td>
                <td><button class="btn bsm bxsm"><i class="ti ti-player-play"></i>Play</button></td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- Recording detail panel -->
        <div class="rec-card" id="rec-panel" style="display:none">
          <div class="rec-head">
            <div class="av av-g" style="width:40px;height:40px;font-size:13px" id="rec-av">JD</div>
            <div class="rec-meta">
              <div class="rec-name" id="rec-name">James Davies</div>
              <div class="rec-info">
                <div class="rec-info-item"><i class="ti ti-clock"></i><span id="rec-dur">7m 14s</span></div>
                <div class="rec-info-item"><i class="ti ti-tag"></i><span id="rec-task">Interview screening</span></div>
                <div class="rec-info-item"><i class="ti ti-mood-happy"></i><span id="rec-sent">Enthusiastic</span></div>
              </div>
            </div>
            <button class="btn bsm" onclick="document.getElementById('rec-panel').style.display='none'"><i class="ti ti-x"></i>Close</button>
          </div>
          <div class="audio-player">
            <div class="play-btn" onclick="togglePlay()"><i class="ti ti-player-play" id="play-ic"></i></div>
            <div class="wave-track" id="wave-track"></div>
            <span class="wave-time">7:14</span>
          </div>
          <div style="font-size:12px;font-weight:700;color:var(--t2);margin-bottom:8px;text-transform:uppercase;letter-spacing:.05em">Transcript</div>
          <div class="transcript-box">
            <div class="trans-line"><span class="trans-ai">Aria (AI):</span> <span class="trans-pt">Hello, may I speak with James Davies? … Hi James, I'm Aria, an AI assistant calling on behalf of TechCorp. This call may be recorded for quality purposes. Is now a good time for a quick 5-minute screening call?</span></div>
            <div class="trans-line"><span class="trans-ai">James:</span> <span class="trans-pt">Yes, absolutely, I've been expecting your call.</span></div>
            <div class="trans-line"><span class="trans-ai">Aria:</span> <span class="trans-pt">Great. Can you tell me briefly about your React experience? We're looking for someone with at least 2 years of hands-on work.</span></div>
            <div class="trans-line"><span class="trans-ai">James:</span> <span class="trans-pt">Sure — I've been working with React for about 4 years now, building large-scale applications at my current role. I'm comfortable with hooks, context, Redux, and TypeScript.</span></div>
            <div class="trans-line"><span class="trans-ai">Aria:</span> <span class="trans-pt">That's great. Are you comfortable working remotely?</span></div>
            <div class="trans-line"><span class="trans-ai">James:</span> <span class="trans-pt">Yes, I've been fully remote for 3 years. I actually prefer it — I have a dedicated home office.</span></div>
          </div>
          <div class="g2" style="margin-top:12px;margin-bottom:0">
            <div>
              <div style="font-size:12px;font-weight:700;color:var(--t2);margin-bottom:8px;text-transform:uppercase;letter-spacing:.05em">Score breakdown</div>
              <div class="crit-row"><div class="crit-lbl">React experience</div><div class="crit-bar"><div class="crit-fill" style="width:90%"></div></div><div class="crit-val">4.5/5</div></div>
              <div class="crit-row"><div class="crit-lbl">Availability</div><div class="crit-bar"><div class="crit-fill" style="width:100%"></div></div><div class="crit-val">5.0/5</div></div>
              <div class="crit-row"><div class="crit-lbl">Remote comfort</div><div class="crit-bar"><div class="crit-fill" style="width:100%"></div></div><div class="crit-val">5.0/5</div></div>
              <div class="crit-row"><div class="crit-lbl">Communication</div><div class="crit-bar"><div class="crit-fill" style="width:86%"></div></div><div class="crit-val">4.3/5</div></div>
            </div>
            <div>
              <div style="font-size:12px;font-weight:700;color:var(--t2);margin-bottom:8px;text-transform:uppercase;letter-spacing:.05em">Best answer highlight</div>
              <div style="background:var(--gd);border-radius:9px;padding:11px;font-size:11.5px;color:var(--t1);line-height:1.6;font-style:italic">"I've been working with React for about 4 years now, building large-scale applications... I'm comfortable with hooks, context, Redux, and TypeScript."</div>
            </div>
          </div>
          <div class="retention-notice"><i class="ti ti-clock" style="font-size:15px"></i>This recording and transcript will be automatically deleted on <strong>14 Aug 2026</strong> (90 days). Access restricted to Managers and Owners. All access is logged in the Audit log.</div>
        </div>
        <div class="g2" style="margin-top:12px">
          <div class="card" style="margin:0">
            <div class="ch"><i class="ti ti-chart-dots grn"></i>Avg scores across all candidates</div>
            <div class="crit-row"><div class="crit-lbl">React experience</div><div class="crit-bar"><div class="crit-fill" style="width:82%"></div></div><div class="crit-val">4.1/5</div></div>
            <div class="crit-row"><div class="crit-lbl">Availability</div><div class="crit-bar"><div class="crit-fill" style="width:90%"></div></div><div class="crit-val">4.5/5</div></div>
            <div class="crit-row"><div class="crit-lbl">Remote comfort</div><div class="crit-bar"><div class="crit-fill" style="width:74%"></div></div><div class="crit-val">3.7/5</div></div>
          </div>
          <div class="card" style="margin:0">
            <div class="ch"><i class="ti ti-alert-circle red"></i>Red flags</div>
            <div style="background:var(--rd);border-radius:9px;padding:11px;font-size:11.5px;color:var(--red);line-height:1.7">Raj Kumar — salary expectation above stated budget<br>Lisa Wong — unavailable for 6 weeks from start date</div>
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:12px"><button class="btn btng bsm"><i class="ti ti-download"></i>Export PDF report</button><button class="btn bsm"><i class="ti ti-table"></i>Export CSV</button></div>
      </div>

      <!-- ══ SURVEY RESULTS ══ -->
      <div class="pg" id="pg-results-s">
        <div class="breadcrumb">
          <span class="bc-link" onclick="goNav('surveys')"><i class="ti ti-clipboard-list" style="font-size:11px"></i> Surveys</span>
          <span class="bc-sep">›</span>
          <span class="bc-cur" id="sur-results-breadcrumb">Survey results</span>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px">
          <button class="btn bsm" onclick="goNav('surveys')"><i class="ti ti-arrow-left"></i>Back to surveys</button>
          <div style="display:flex;gap:8px"><button class="btn btng bsm" disabled title="Coming soon"><i class="ti ti-download"></i>Export PDF</button><button class="btn bsm" disabled title="Coming soon"><i class="ti ti-table"></i>Export CSV</button></div>
        </div>
        <div id="sur-results-loading" class="inf g" style="display:none"><i class="ti ti-loader"></i>Loading survey results…</div>
        <div id="sur-results-error" class="inf r" style="display:none"></div>
        <div id="sur-results-empty" class="inf b" style="display:none"><i class="ti ti-info-circle"></i>Select a survey from the Surveys page to view results.</div>
        <div id="sur-results-content" style="display:none">
        <div class="kg4">
          <div class="kpi gt"><div class="kl">Overall satisfaction</div><div class="kv" id="sur-kpi-satisfaction" style="color:var(--grn)">—</div><div class="kd" id="sur-kpi-satisfaction-sub">—</div></div>
          <div class="kpi"><div class="kl">Would recommend</div><div class="kv" id="sur-kpi-recommend">—</div><div class="kd" id="sur-kpi-nps">—</div></div>
          <div class="kpi"><div class="kl">Responded</div><div class="kv" id="sur-kpi-responded">—</div><div class="kd" id="sur-kpi-response-rate">—</div></div>
          <div class="kpi"><div class="kl">Avg call length</div><div class="kv" id="sur-kpi-duration">—</div></div>
        </div>
        <div class="card">
          <div class="ch"><i class="ti ti-users grn"></i>Respondents — click to view transcript</div>
          <table class="res-table">
            <thead><tr><th>Name</th><th>Duration</th><th>Task</th><th>Satisfaction</th><th>Status</th><th></th></tr></thead>
            <tbody id="sur-results-respondents"></tbody>
          </table>
        </div>
        <div class="rec-card" id="srec-panel" style="display:none">
          <div class="rec-head">
            <div class="av av-g" style="width:40px;height:40px;font-size:13px" id="srec-av">—</div>
            <div class="rec-meta">
              <div class="rec-name" id="srec-name">—</div>
              <div class="rec-info">
                <div class="rec-info-item"><i class="ti ti-clock"></i><span id="srec-dur">—</span></div>
                <div class="rec-info-item"><i class="ti ti-tag"></i><span id="srec-goal">—</span></div>
                <div class="rec-info-item"><i class="ti ti-mood-happy"></i><span id="srec-sentiment">—</span></div>
              </div>
            </div>
            <button class="btn bsm" onclick="document.getElementById('srec-panel').style.display='none'"><i class="ti ti-x"></i>Close</button>
          </div>
          <div id="srec-summary" style="font-size:12px;color:var(--t2);margin:0 0 10px;line-height:1.6"></div>
          <div class="transcript-box" id="srec-transcript"></div>
          <div id="srec-answers" style="margin-top:10px"></div>
          <div class="retention-notice"><i class="ti ti-clock" style="font-size:15px"></i>Call transcripts are retained per your organisation policy. Access is logged in the Audit log.</div>
        </div>
        <div class="card" style="margin-top:12px">
          <div class="ch"><i class="ti ti-alert-circle red"></i>Problem list — AI ranked by frequency</div>
          <div id="sur-results-problems"></div>
        </div>
        <div class="card">
          <div class="ch"><i class="ti ti-bulb amb"></i>AI action suggestions</div>
          <div id="sur-results-recommendations" style="font-size:12px;color:var(--t1);line-height:1.8"></div>
        </div>
        <div style="display:flex;gap:8px"><button class="btn btng bsm" disabled title="Coming soon"><i class="ti ti-download"></i>Export PDF report</button><button class="btn bsm" disabled title="Coming soon"><i class="ti ti-table"></i>Export CSV</button></div>
        </div>
      </div>

      <!-- ══ REMINDERS ══ -->
      <div class="pg" id="pg-reminders">
        <div class="inf b"><i class="ti ti-info-circle"></i>Reminders send automatically based on appointment time. Toggle steps on/off. Changes apply to future appointments only.</div>
        <div class="card">
          <div class="ch"><i class="ti ti-clock grn"></i>Reminder sequence</div>
          <div class="seq"><div class="seqn">1</div><div class="seqi"><div class="seqt">72 hours before — soft reminder</div><div class="seqs">WhatsApp · "Just a heads-up about your upcoming appointment..."</div></div><select style="font-size:11px;padding:5px 8px;border-radius:7px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1);margin-right:8px"><option selected>72 hrs</option><option>96 hrs</option></select><div class="tog on" onclick="togS(this)"><div class="togth"></div></div></div>
          <div class="seq"><div class="seqn">2</div><div class="seqi"><div class="seqt">48 hours before — confirmation request</div><div class="seqs">WhatsApp with Confirm / Reschedule buttons</div></div><select style="font-size:11px;padding:5px 8px;border-radius:7px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1);margin-right:8px"><option selected>48 hrs</option><option>36 hrs</option></select><div class="tog on" onclick="togS(this)"><div class="togth"></div></div></div>
          <div class="seq"><div class="seqn">3</div><div class="seqi"><div class="seqt">24 hours before — final reminder</div><div class="seqs">WhatsApp · "Your appointment is tomorrow at {time}..."</div></div><select style="font-size:11px;padding:5px 8px;border-radius:7px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1);margin-right:8px"><option selected>24 hrs</option><option>12 hrs</option></select><div class="tog on" onclick="togS(this)"><div class="togth"></div></div></div>
          <div class="seq off"><div class="seqn">4</div><div class="seqi"><div class="seqt">2 hours before — day-of reminder</div><div class="seqs">WhatsApp · "We look forward to seeing you today..."</div></div><select style="font-size:11px;padding:5px 8px;border-radius:7px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1);margin-right:8px"><option selected>2 hrs</option><option>1 hr</option></select><div class="tog off" onclick="togS(this)"><div class="togth"></div></div></div>
          <div class="seq"><div class="seqn">5</div><div class="seqi"><div class="seqt">After no-show — rebook offer</div><div class="seqs">WhatsApp + AI call · "We missed you today — shall we rebook?"</div></div><select style="font-size:11px;padding:5px 8px;border-radius:7px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1);margin-right:8px"><option selected>30 min after</option><option>1 hr after</option></select><div class="tog on" onclick="togS(this)"><div class="togth"></div></div></div>
          <button class="btn btng bsm" style="margin-top:8px"><i class="ti ti-device-floppy"></i>Save sequence</button>
        </div>
      </div>

      <!-- ══ PROFILE ══ -->
      <div class="pg" id="pg-profile">
        <div class="g2">
          <div class="card" style="margin:0">
            <div class="ch"><i class="ti ti-building grn"></i>Company info</div>
            <div class="fg"><label>Company name</label><input id="prof-company-name" placeholder="Your clinic or business name"/></div>
            <div class="fg"><label>Survey organiser</label><input id="prof-organiser-name" placeholder="Name read on calls — e.g. Sarah Mitchell"/></div>
            <div class="fg"><label>Industry</label><select id="prof-industry"><option selected>Dental</option><option>Beauty / Salon / Spa</option><option>Aesthetics / Anti-aging</option><option>Eye Optician</option><option>Recruitment / HR</option><option>Automotive</option><option>Other</option></select></div>
            <div class="fg2"><div class="fg"><label>Phone</label><input id="prof-phone" placeholder="+44 …"/></div><div class="fg"><label>Website</label><input id="prof-website" placeholder="yoursite.co.uk"/></div></div>
            <div class="fg"><label>Caller ID shown to patients</label><input id="prof-caller-id" placeholder="Short name on caller ID"/></div>
            <div class="fg"><label>Logo</label><div class="standalone-upload"><i class="ti ti-upload" style="font-size:22px;display:block;margin-bottom:5px;color:var(--t3)"></i>Drop PNG or SVG · max 2MB</div></div>
            <button class="btn btng bsm" type="button" id="prof-save-btn"><i class="ti ti-device-floppy"></i>Save profile</button>
          </div>
          <div class="card" style="margin:0">
            <div class="ch"><i class="ti ti-currency-pound grn"></i>Revenue settings</div>
            <div class="fg"><label>Average appointment value (£)</label><input type="number" value="85" id="apv"/></div>
            <div class="fg"><label>Use per-treatment type values?</label>
              <div style="display:flex;align-items:center;gap:10px;margin-top:4px">
                <div class="tog off" id="per-tog" onclick="togPerTx(this)"><div class="togth"></div></div>
                <span style="font-size:12px;color:var(--t2)" id="per-lbl">Off — using flat rate £85 for all treatments</span>
              </div>
            </div>
            <div id="per-table" style="display:none;margin-top:2px">
              <div class="inf g" style="margin-bottom:10px"><i class="ti ti-api"></i>Dentally supports treatment fees — <button class="btn btng bsm" style="margin-left:6px"><i class="ti ti-refresh"></i>Sync from Dentally</button></div>
              <div class="qr"><div class="qi"><div class="qn">Check-up</div></div><input type="number" value="85" style="width:85px;font-size:12px;padding:5px 9px;border-radius:7px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1)"/></div>
              <div class="qr"><div class="qi"><div class="qn">Hygiene</div></div><input type="number" value="55" style="width:85px;font-size:12px;padding:5px 9px;border-radius:7px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1)"/></div>
              <div class="qr"><div class="qi"><div class="qn">Implant consult</div></div><input type="number" value="350" style="width:85px;font-size:12px;padding:5px 9px;border-radius:7px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1)"/></div>
              <div class="qr" style="border:none"><div class="qi"><div class="qn">Whitening</div></div><input type="number" value="290" style="width:85px;font-size:12px;padding:5px 9px;border-radius:7px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1)"/></div>
              <button class="btn bsm" style="margin-top:7px;width:100%;justify-content:center"><i class="ti ti-plus"></i>Add treatment type</button>
            </div>
          </div>
        </div>
      </div>

      <!-- ══ SYSTEM SETTINGS ══ -->
      <div class="pg" id="pg-system">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px">
          <button type="button" class="btn bsm btng" id="ob-show-btn" onclick="toggleSetupChecklist()"><i class="ti ti-list-check"></i> Show setup checklist</button>
        </div>
        <div class="ob-card" id="ob-card" style="display:none">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
            <div style="font-size:14px;font-weight:700;color:var(--t1);display:flex;align-items:center;gap:8px"><i class="ti ti-rocket" style="color:var(--grn);font-size:16px"></i>Getting started — 3 of 6 complete</div>
            <div style="display:flex;align-items:center;gap:8px">
              <span class="bdg bg">50%</span>
              <button type="button" class="btn bsm" onclick="toggleSetupChecklist(false)" title="Hide checklist"><i class="ti ti-x"></i></button>
            </div>
          </div>
          <div class="ob-prog"><div class="ob-fill" style="width:50%"></div></div>
          <div class="ob-step"><div class="ob-ic ob-done"><i class="ti ti-check"></i></div><div class="ob-lbl">Connect booking system API <span style="color:var(--t3)">— Dentally connected</span></div></div>
          <div class="ob-step"><div class="ob-ic ob-done"><i class="ti ti-check"></i></div><div class="ob-lbl">Set average appointment value <span style="color:var(--t3)">— £85</span></div></div>
          <div class="ob-step"><div class="ob-ic ob-done"><i class="ti ti-check"></i></div><div class="ob-lbl">Configure WhatsApp number <span style="color:var(--t3)">— Connected</span></div></div>
          <div class="ob-step"><div class="ob-ic ob-act"><i class="ti ti-arrow-right"></i></div><div class="ob-lbl" style="color:var(--grn);font-weight:600">Set up reminder sequence <button class="btn btng bsm" style="margin-left:auto" onclick="go('reminders',document.querySelector('.ni'))">Set up →</button></div></div>
          <div class="ob-step"><div class="ob-ic ob-pend">5</div><div class="ob-lbl">Approve AI script</div></div>
          <div class="ob-step"><div class="ob-ic ob-pend">6</div><div class="ob-lbl">Make a test call to hear AI voice</div></div>
        </div>
        <div class="tbrow">
          <div class="tb on" onclick="stab('api',this)"><i class="ti ti-plug"></i>API connection</div>
          <div class="tb" onclick="stab('wa',this)"><i class="ti ti-brand-whatsapp"></i>WhatsApp</div>
          <div class="tb" onclick="stab('call',this)"><i class="ti ti-phone"></i>AI calling</div>
        </div>

        <div class="tpcont on" id="stp-api">
          <div class="secl">Step 1 — Select your booking system</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px">
            <div class="sysb sel" onclick="selSys(this,'apikey')"><span class="sdotl sg2"></span><div><div class="sn">Dentally</div><div class="sc2">Dental · API key</div></div><span class="bdg bg" style="margin-left:auto">Connected</span></div>
            <div class="sysb" onclick="selSys(this,'apikey')"><span class="sdotl sgr2"></span><div><div class="sn">CareStack</div><div class="sc2">Dental · OAuth 2.0</div></div></div>
            <div class="sysb" onclick="selSys(this,'multi')"><span class="sdotl sgr2"></span><div><div class="sn">Phorest</div><div class="sc2">Beauty / Salon · API key + Location ID</div></div></div>
            <div class="sysb" onclick="selSys(this,'multi')"><span class="sdotl sgr2"></span><div><div class="sn">Zenoti</div><div class="sc2">Beauty / Salon · API key + Client ID</div></div></div>
            <div class="sysb" onclick="selSys(this,'apikey')"><span class="sdotl sgr2"></span><div><div class="sn">Boulevard (Joinblvd)</div><div class="sc2">Beauty / Salon · API key</div></div></div>
            <div class="sysb" onclick="selSys(this,'apikey')"><span class="sdotl sgr2"></span><div><div class="sn">Pabau</div><div class="sc2">Aesthetics · API key</div></div></div>
            <div class="sysb" onclick="selSys(this,'userpass')"><span class="sdotl sgr2"></span><div><div class="sn">ODoptik / Optosys / Optomate</div><div class="sc2">Eye Optician · Username + Password</div></div></div>
            <div class="sysb" onclick="selSys(this,'oauth')"><span class="sdotl sgr2"></span><div><div class="sn">Calendly / Cronofy</div><div class="sc2">Recruitment · OAuth 2.0</div></div></div>
            <div class="sysb" onclick="selSys(this,'standalone')"><span class="sdotl" style="background:var(--pur)"></span><div><div class="sn">No booking system</div><div class="sc2">Standalone mode — manual upload</div></div></div>
          </div>
          <div id="cred-area">
            <div class="secl">Step 2 — Connected credentials</div>
            <div class="cred-form" id="cred-apikey">
              <div class="cred-title"><i class="ti ti-key" style="font-size:14px"></i>API key</div>
              <div style="display:flex;gap:8px;margin-bottom:10px">
                <input id="akey" type="password" value="sk-dent-••••••••••••••••" style="flex:1;font-size:12px;padding:8px 10px;border-radius:9px;border:1.5px solid var(--b2);background:var(--s1);color:var(--t1)"/>
                <button class="btn bsm" onclick="document.getElementById('akey').type=document.getElementById('akey').type==='password'?'text':'password'"><i class="ti ti-eye"></i></button>
                <button class="btn btng bsm" onclick="vkey()"><i class="ti ti-plug"></i>Validate</button>
              </div>
              <div id="ast" style="font-size:12px;display:flex;align-items:center;gap:7px"><span class="sdotl sg2"></span><span style="color:var(--grn);font-weight:600">Connected — Dentally syncing live</span></div>
            </div>
            <div class="cred-form" id="cred-multi" style="display:none">
              <div class="cred-title"><i class="ti ti-key" style="font-size:14px"></i>API key + additional field</div>
              <div class="fg2"><div class="fg"><label>API key</label><input type="password" placeholder="Enter API key"/></div><div class="fg"><label>Location / Client ID</label><input placeholder="Enter ID"/></div></div>
              <button class="btn btng bsm"><i class="ti ti-plug"></i>Validate connection</button>
            </div>
            <div class="cred-form" id="cred-userpass" style="display:none">
              <div class="cred-title"><i class="ti ti-user" style="font-size:14px"></i>Username &amp; password login</div>
              <div class="fg3"><div class="fg"><label>Username</label><input placeholder="practice@email.com"/></div><div class="fg"><label>Password</label><input type="password" placeholder="••••••••"/></div><div class="fg"><label>Practice ID</label><input placeholder="e.g. 12345"/></div></div>
              <button class="btn btng bsm"><i class="ti ti-plug"></i>Connect</button>
            </div>
            <div class="cred-form" id="cred-oauth" style="display:none">
              <div class="cred-title"><i class="ti ti-shield-check" style="font-size:14px"></i>OAuth 2.0 — authorise via browser</div>
              <p style="font-size:12px;color:var(--t2);margin-bottom:12px;line-height:1.6">Click below to open the authorisation page. You'll be redirected back automatically after granting access. No password is stored.</p>
              <button class="btn btng"><i class="ti ti-external-link"></i>Connect with OAuth →</button>
            </div>
            <div class="cred-form" id="cred-standalone" style="display:none">
              <div class="cred-title"><i class="ti ti-upload" style="font-size:14px"></i>Standalone mode — no booking system needed</div>
              <p style="font-size:12px;color:var(--t2);margin-bottom:12px;line-height:1.6">Upload your appointment list each time. VoxBulk runs recovery, reminders, and campaigns from your uploaded data.</p>
              <div class="standalone-upload" style="margin-bottom:12px"><i class="ti ti-file-spreadsheet" style="font-size:22px;display:block;margin-bottom:5px"></i>Upload Excel / CSV · Required: Name · Phone · Date · Time · Treatment</div>
              <div class="fg"><label>Recurring upload schedule</label><select><option selected>Manual — I'll upload when needed</option><option>Every Monday morning</option><option>Every day at 8am</option></select></div>
            </div>
          </div>
          <div style="margin-top:12px">
            <div class="secl">Connection health</div>
            <div class="conn-row"><div class="conn-dot conn-ok"></div><div class="conn-info"><div class="conn-name">Dentally</div><div class="conn-sync">Last synced 4 min ago · 47 appointments imported today</div></div><span class="bdg bg">Live</span></div>
            <div class="conn-row"><div class="conn-dot conn-off"></div><div class="conn-info"><div class="conn-name">Phorest</div><div class="conn-sync">Not connected</div></div><button class="btn bsm">Connect</button></div>
            <div class="conn-row"><div class="conn-dot conn-warn"></div><div class="conn-info"><div class="conn-name">Calendly</div><div class="conn-sync">OAuth expires in 3 days — reconnect recommended</div></div><button class="btn bsm ba">Refresh token</button></div>
          </div>
          <div style="margin-top:12px;display:flex;gap:8px;align-items:center">
            <input placeholder="Your phone number e.g. +44 7700 900123" style="flex:1;font-size:12px;padding:8px 10px;border-radius:9px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1)" id="test-call-num"/>
            <button class="btn btng bsm" onclick="toast('Test call initiated to '+document.getElementById('test-call-num').value,'tg')"><i class="ti ti-phone"></i>Call me now — test AI voice</button>
          </div>
        </div>

        <div class="tpcont" id="stp-wa">
          <div class="inf g"><i class="ti ti-info-circle"></i>Use {variables} to personalise messages. The preview on the right updates as you type.</div>
          <div style="display:grid;grid-template-columns:1fr 196px;gap:14px;align-items:start">
            <div>
              <div class="card" style="margin-bottom:10px">
                <div class="ch"><i class="ti ti-bell grn"></i>Appointment reminder</div>
                <div class="fg"><label>Message</label><textarea rows="3" id="msg-r" oninput="uwp()" style="resize:none">Hi {first_name}, reminder from {clinic_name} 😊

Your appointment is on {date} at {time}.

Please confirm below:</textarea></div>
                <div class="fg"><label>Variables — click to insert</label><div class="vp"><span class="vpl" onclick="iv('msg-r','{first_name}')">{first_name}</span><span class="vpl" onclick="iv('msg-r','{clinic_name}')">{clinic_name}</span><span class="vpl" onclick="iv('msg-r','{date}')">{date}</span><span class="vpl" onclick="iv('msg-r','{time}')">{time}</span><span class="vpl" onclick="iv('msg-r','{service}')">{service}</span></div></div>
                <div class="fg2"><div class="fg"><label>Confirm button label</label><input id="wb1" value="Confirm ✓" oninput="uwp()"/></div><div class="fg"><label>Reschedule button label</label><input id="wb2" value="Reschedule" oninput="uwp()"/></div></div>
              </div>
              <button class="btn btng bsm"><i class="ti ti-device-floppy"></i>Save all templates</button>
            </div>
            <div>
              <div style="font-size:10px;color:var(--t3);text-align:center;margin-bottom:8px;text-transform:uppercase;letter-spacing:.07em;font-weight:700">Live preview</div>
              <div class="pf"><div class="ps"><div class="pb"><div class="pba">VB</div><div><div class="pbn">Voxbulk</div><div class="pbs">Business account</div></div></div><div class="pca"><div class="bub"><div class="bt" id="wap">Hi Sarah, reminder from Bright Smiles 😊

Your appointment is on Mon 19 May at 2:30pm.

Please confirm below:</div><div class="wab" id="wb1p">Confirm ✓</div><div class="wab" id="wb2p">Reschedule</div><div class="btm">14:02 ✓✓</div></div></div></div></div>
              <div style="font-size:9.5px;color:var(--t3);text-align:center;margin-top:6px">Showing sample data</div>
            </div>
          </div>
        </div>

        <div class="tpcont" id="stp-call">
          <div class="inf g"><i class="ti ti-shield-check"></i>The AI always discloses it is an AI and that the call may be recorded. These lines are locked and cannot be removed or edited.</div>
          <div class="g2">
            <div>
              <div class="card" style="margin-bottom:10px">
                <div class="ch"><i class="ti ti-microphone grn"></i>AI voice selection</div>
                <div style="display:flex;gap:7px;margin-bottom:10px">
                  <div class="vo sel" onclick="selVc(this)">Aria<small>British female</small></div>
                  <div class="vo" onclick="selVc(this)">James<small>British male</small></div>
                  <div class="vo" onclick="selVc(this)">Sophie<small>Neutral female</small></div>
                </div>
                <div style="display:flex;align-items:center;gap:9px;background:var(--s2);border-radius:9px;padding:8px 10px">
                  <div style="width:28px;height:28px;border-radius:50%;background:var(--grn);display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0"><i class="ti ti-player-play" style="font-size:13px;color:#fff"></i></div>
                  <div style="flex:1;display:flex;align-items:center;gap:2px;height:18px"><div style="width:2.5px;border-radius:2px;background:var(--gd2);height:40%"></div><div style="width:2.5px;border-radius:2px;background:var(--grn);height:72%"></div><div style="width:2.5px;border-radius:2px;background:var(--gd2);height:55%"></div><div style="width:2.5px;border-radius:2px;background:var(--grn);height:90%"></div><div style="width:2.5px;border-radius:2px;background:var(--gd2);height:44%"></div><div style="width:2.5px;border-radius:2px;background:var(--grn);height:66%"></div><div style="width:2.5px;border-radius:2px;background:var(--gd2);height:33%"></div><div style="width:2.5px;border-radius:2px;background:var(--grn);height:80%"></div><div style="width:2.5px;border-radius:2px;background:var(--gd2);height:58%"></div></div>
                  <span style="font-size:10.5px;color:var(--t3)">Preview voice</span>
                </div>
              </div>
              <div class="card">
                <div class="ch"><i class="ti ti-adjustments grn"></i>Call behaviour</div>
                <div class="fg2"><div class="fg"><label>Max attempts</label><select><option>1</option><option selected>2</option><option>3</option></select></div><div class="fg"><label>Gap between attempts</label><select><option selected>1 hour</option><option>2 hours</option><option>4 hours</option></select></div></div>
                <div class="fg2"><div class="fg"><label>Call from</label><input type="time" value="09:00"/></div><div class="fg"><label>Call until</label><input type="time" value="18:30"/></div></div>
                <div class="fg"><label>If no answer after all attempts</label><select><option selected>Send WhatsApp message</option><option>Flag for manual follow-up</option><option>Do nothing</option></select></div>
              </div>
            </div>
            <div class="card">
              <div class="ch"><i class="ti ti-file-text grn"></i>Script builder <span class="aib">AI-generated</span></div>
              <div class="fg2" style="margin-bottom:8px"><div class="fg"><label>Call purpose</label><select><option selected>Appointment recovery</option><option>No-show follow-up</option><option>Emergency reschedule</option><option>Interview screening</option><option>Survey</option></select></div><div class="fg"><label>Tone</label><select><option selected>Friendly and professional</option><option>Warm and empathetic</option><option>Concise and direct</option></select></div></div>
              <button class="btn btng bsm" style="width:100%;justify-content:center;margin-bottom:11px" onclick="gsc()"><i class="ti ti-sparkles"></i>Generate AI script</button>
              <div class="scb"><div class="scl"><span class="sdotl sg2"></span>Opening — required disclosure <span class="lkb">Locked</span></div><div class="sct">"Hello, may I speak with {first_name}? … Hi {first_name}, I'm Aria, an AI assistant calling on behalf of {clinic_name}. This call may be recorded for quality and training purposes."</div></div>
              <div class="scb"><div class="scl"><i class="ti ti-sparkles" style="font-size:12px;color:var(--pur)"></i>Purpose <span class="aib">AI-generated</span></div><div class="sct" id="scp">"We noticed you missed your appointment today and we'd love to help you find a new time. Do you have a moment — it'll only take a minute?"</div></div>
              <div class="scb"><div class="scl"><i class="ti ti-sparkles" style="font-size:12px;color:var(--pur)"></i>Rebooking offer <span class="aib">AI-generated</span></div><div class="sct" id="sco">"We have availability on {available_slots}. Would any of those work for you? … Perfect, I'll go ahead and book that in."</div></div>
              <div class="scb"><div class="scl"><span class="sdotl sg2"></span>Closing <span class="lkb">Locked</span></div><div class="sct">"Is there anything else I can help you with? … Great, thank you {first_name}. Have a lovely day. Goodbye."</div></div>
              <button class="btn bsm" style="width:100%;justify-content:center;margin-top:7px"><i class="ti ti-edit"></i>Edit script manually</button>
            </div>
          </div>
        </div>
      </div>

      <!-- ══ TEAM ══ -->
      <div class="pg" id="pg-team">
        <div class="card">
          <div class="ch"><i class="ti ti-user-plus grn"></i>Invite team member</div>
          <div class="fg2"><div class="fg"><label>Email address</label><input placeholder="colleague@practice.co.uk" type="email"/></div><div class="fg"><label>Role</label><select><option>Owner</option><option selected>Manager</option><option>Staff</option></select></div></div>
          <div class="inf b" style="margin-bottom:10px"><i class="ti ti-info-circle"></i>Owner: full access including billing · Manager: everything except billing · Staff: view queue and results only</div>
          <button class="btn btng bsm"><i class="ti ti-send"></i>Send invite</button>
        </div>
        <div class="card">
          <div class="ch"><i class="ti ti-users grn"></i>Current team</div>
          <div class="team-row"><div class="av av-g">JA</div><div class="qi"><div class="qn">Jane Anderson</div><div class="qd">jane@brightsmiles.co.uk · Last active now</div></div><span class="bdg bg">Owner</span></div>
          <div class="team-row"><div class="av av-b">MP</div><div class="qi"><div class="qn">Mark Peters</div><div class="qd">mark@brightsmiles.co.uk · Last active today</div></div><span class="bdg bb">Manager</span></div>
          <div class="team-row"><div class="av av-p">SR</div><div class="qi"><div class="qn">Sophie Ryan</div><div class="qd">sophie@brightsmiles.co.uk · Last active yesterday</div></div><span class="bdg bp">Staff</span></div>
        </div>
      </div>

      <!-- ══ OPT-OUT ══ -->
      <div class="pg" id="pg-optout">
        <div class="inf r"><i class="ti ti-ban"></i>Patients on this list will never be called or messaged through VoxBulk. This list is required under PECR (UK privacy regulations).</div>

        <!-- ADD FORM FIRST -->
        <div class="card">
          <div class="ch"><i class="ti ti-plus red"></i>Add to opt-out list</div>
          <div class="fg3">
            <div class="fg"><label>Phone number</label><input placeholder="+44 7700 000000" type="tel"/></div>
            <div class="fg"><label>Name (optional)</label><input placeholder="Patient name"/></div>
            <div class="fg"><label>Reason</label><select><option selected>Patient request — call</option><option>Patient request — WhatsApp</option><option>Moved practice</option><option>Deceased</option><option>Manual staff entry</option></select></div>
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <button class="btn btng bsm"><i class="ti ti-shield-check"></i>Add to opt-out list</button>
            <span style="font-size:11px;color:var(--t3)">This person will never be contacted through VoxBulk</span>
          </div>
        </div>

        <!-- API SYNC -->
        <div class="card">
          <div class="ch"><i class="ti ti-refresh grn"></i>API sync</div>
          <div style="display:flex;align-items:center;justify-content:space-between">
            <div>
              <div style="font-size:12.5px;font-weight:600;color:var(--t1);margin-bottom:3px">Sync do-not-contact flags from Dentally</div>
              <div style="font-size:11px;color:var(--t3)">Patients marked do-not-contact in Dentally are automatically added here. Opt-outs here are also pushed back to Dentally.</div>
            </div>
            <div class="tog on" onclick="this.classList.toggle('on');this.classList.toggle('off')"><div class="togth"></div></div>
          </div>
          <div style="margin-top:10px;font-size:11px;color:var(--t3);display:flex;align-items:center;gap:6px"><span class="sdotl sg2"></span>Last synced 5 min ago · 2 patients imported from Dentally this week</div>
        </div>

        <!-- LIST BELOW -->
        <div class="card">
          <div class="ch"><i class="ti ti-ban red"></i>Opt-out list <span style="font-size:12px;font-weight:400;color:var(--t3);margin-left:4px">2 patients</span></div>
          <div style="display:flex;gap:8px;margin-bottom:12px">
            <input placeholder="Search by name or phone..." style="flex:1;font-size:12px;padding:7px 10px;border-radius:8px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1)"/>
            <button class="btn bsm"><i class="ti ti-download"></i>Export CSV</button>
          </div>
          <div class="opt-row"><div class="av av-r">KN</div><div class="qi"><div class="qn">Kim Nguyen · +44 7700 900654</div><div class="qd">Opted out 14 May 2026 · Said "don't call me" during AI call</div></div><button class="btn bsm btnr bxsm" onclick="showConfirm('Remove from opt-out list?','Kim Nguyen will be able to receive AI calls and messages again. Only remove if they have explicitly requested this.','Remove',function(){toast('Removed from opt-out list','ta');})"><i class="ti ti-trash"></i>Remove</button></div>
          <div class="opt-row"><div class="av av-r">PT</div><div class="qi"><div class="qn">Paul Torres · +44 7700 900321</div><div class="qd">Opted out 2 May 2026 · WhatsApp reply "STOP"</div></div><button class="btn bsm btnr bxsm" onclick="showConfirm('Remove from opt-out list?','Paul Torres will be able to receive AI calls and messages again. Only remove if they have explicitly requested this.','Remove',function(){toast('Removed from opt-out list','ta');})"><i class="ti ti-trash"></i>Remove</button></div>
        </div>
      </div>

      <!-- ══ AUDIT LOG ══ -->
      <div class="pg" id="pg-audit">
        <div class="card">
          <div class="ch"><i class="ti ti-history grn"></i>Audit log</div>
          <div style="display:flex;gap:8px;margin-bottom:13px;flex-wrap:wrap">
            <select style="font-size:12px;padding:6px 9px;border-radius:8px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1)"><option>All actions</option><option>Script changes</option><option>Campaign launches</option><option>Opt-out changes</option><option>API changes</option></select>
            <input type="date" style="font-size:12px;padding:6px 9px;border-radius:8px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1)"/>
            <button class="btn bsm" style="margin-left:auto"><i class="ti ti-download"></i>Export CSV</button>
          </div>
          <div class="audit-row"><div class="audit-time">Today 14:02</div><div class="audit-user">Jane Anderson</div><div class="audit-act">Recall campaign launched — 143 overdue patients targeted</div></div>
          <div class="audit-row"><div class="audit-time">Today 11:30</div><div class="audit-user">Mark Peters</div><div class="audit-act">AI call script updated — purpose block modified</div></div>
          <div class="audit-row"><div class="audit-time">Today 09:15</div><div class="audit-user">System</div><div class="audit-act">Kim Nguyen +44 7700 900654 added to opt-out list — opted out during AI call</div></div>
          <div class="audit-row"><div class="audit-time">Yesterday 16:44</div><div class="audit-user">Jane Anderson</div><div class="audit-act">Reminder sequence modified — step 4 (2hr reminder) disabled</div></div>
          <div class="audit-row"><div class="audit-time">14 May 09:01</div><div class="audit-user">Sophie Ryan</div><div class="audit-act">Recovery queue — manual review of 31 call records</div></div>
          <div class="audit-row"><div class="audit-time">13 May 15:20</div><div class="audit-user">System</div><div class="audit-act">Dentally API sync completed — 47 new appointments imported</div></div>
        </div>
      </div>

      <!-- ══ PACKAGES ══ -->
      <div class="pg" id="pg-packages">
        <div class="card" style="margin-bottom:14px;background:var(--s1)">
          <div style="font-size:18px;font-weight:700;color:var(--t1);margin-bottom:6px">Simple, transparent pricing</div>
          <div style="font-size:13px;color:var(--t2);line-height:1.6;margin-bottom:13px">Pay for what you use. Overage is always invoiced separately and shown in your dashboard before billing — never a surprise.</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <div style="background:var(--s2);border:1.5px solid var(--b2);border-radius:20px;padding:5px 13px;font-size:11.5px;color:var(--t2);display:flex;align-items:center;gap:5px;font-weight:500"><i class="ti ti-check" style="color:var(--grn);font-size:13px"></i>No setup fee</div>
            <div style="background:var(--s2);border:1.5px solid var(--b2);border-radius:20px;padding:5px 13px;font-size:11.5px;color:var(--t2);display:flex;align-items:center;gap:5px;font-weight:500"><i class="ti ti-check" style="color:var(--grn);font-size:13px"></i>Cancel anytime</div>
            <div style="background:var(--s2);border:1.5px solid var(--b2);border-radius:20px;padding:5px 13px;font-size:11.5px;color:var(--t2);display:flex;align-items:center;gap:5px;font-weight:500"><i class="ti ti-check" style="color:var(--grn);font-size:13px"></i>14-day free trial</div>
            <div style="background:var(--s2);border:1.5px solid var(--b2);border-radius:20px;padding:5px 13px;font-size:11.5px;color:var(--t2);display:flex;align-items:center;gap:5px;font-weight:500"><i class="ti ti-check" style="color:var(--grn);font-size:13px"></i>Overage shown before billing</div>
          </div>
        </div>
        <div id="packages-checkout-status" class="billing-checkout-status" hidden aria-live="polite"></div>
        <div class="plan-g" id="packages-plan-grid">
          <div style="grid-column:1/-1;padding:24px;text-align:center;color:var(--t3);font-size:13px">Loading subscription plans…</div>
        </div>

        <div style="font-size:15px;font-weight:700;color:var(--t1);margin-bottom:4px;margin-top:20px">Survey packages — pay as you go</div>
        <div id="survey-packages-section">
          <div class="survey-pkg-loading muted">Loading survey packages…</div>
        </div>

        <div style="font-size:15px;font-weight:700;color:var(--t1);margin-bottom:4px;margin-top:20px">Interview bundles — pay as you go</div>
        <div style="font-size:12px;color:var(--t3);margin-bottom:11px">No subscription needed. Buy credits, upload your list, we call. Credits valid 90 days. Calls over 10 minutes are billed separately.</div>
        <div class="iw" style="margin-bottom:16px">
          <div class="iwh"><div class="iwic" style="background:var(--pd)"><i class="ti ti-briefcase" style="color:var(--pur);font-size:17px"></i></div><div><div style="font-size:13.5px;font-weight:700;color:var(--t1)">Interview call bundles</div><div style="font-size:11.5px;color:var(--t3)">Each bundle covers calls up to 10 min · Extra minutes invoiced separately at month end at £0.15/min</div></div></div>
          <div class="bun-g bun-g-4">
            <div class="bun" onclick="cb(10,39)"><div class="bcnt">10</div><div class="bunt">interviews</div><div class="bprc">£39</div><div class="bper">£3.90 each</div><div class="bmrg">64% margin</div><button class="bunbtn">Buy bundle</button></div>
            <div class="bun bst" onclick="cb(25,89)"><div class="bbst">Best value</div><div class="bcnt">25</div><div class="bunt">interviews</div><div class="bprc">£89</div><div class="bper">£3.56 each</div><div class="bmrg">61% margin</div><button class="bunbtn">Buy bundle</button></div>
            <div class="bun" onclick="cb(50,159)"><div class="bcnt">50</div><div class="bunt">interviews</div><div class="bprc">£159</div><div class="bper">£3.18 each</div><div class="bmrg">56% margin</div><button class="bunbtn">Buy bundle</button></div>
            <div class="bun" onclick="cb(100,279)"><div class="bcnt">100</div><div class="bunt">interviews</div><div class="bprc">£279</div><div class="bper">£2.79 each</div><div class="bmrg">50% margin</div><button class="bunbtn">Buy bundle</button></div>
          </div>
          <div class="iwf"><div class="ri"><i class="ti ti-phone"></i>Call: <strong>£0.10/min</strong></div><div class="ri"><i class="ti ti-cpu"></i>AI: <strong>£0.05/min</strong></div><div class="ri"><i class="ti ti-brand-whatsapp" style="color:#25D366"></i>WhatsApp: <strong>£0.20/msg</strong></div><div class="ri"><i class="ti ti-alert-circle" style="color:var(--amb)"></i>Extra mins over 10: <strong>£0.15/min — separate invoice</strong></div></div>
        </div>

        <div class="ovg">
          <div style="display:flex;align-items:flex-start;gap:12px"><div style="width:36px;height:36px;border-radius:9px;background:var(--ad);display:flex;align-items:center;justify-content:center;flex-shrink:0"><i class="ti ti-receipt" style="font-size:17px;color:var(--amb)"></i></div><div><div style="font-size:14px;font-weight:700;color:var(--t1);margin-bottom:4px">Overage billing — always transparent</div><div style="font-size:12px;color:var(--t2);line-height:1.6">Overage is calculated at month end, shown in your dashboard with a 3-day review window, then issued as a separate invoice. You will always receive an email alert when overage exceeds £10.</div></div></div>
          <div class="ovgi">
            <div class="ovi"><div class="ovl">Starter overage rate</div><div class="ovr">£0.15<span style="font-size:11px;font-weight:400;color:var(--t3)">/min</span></div><div class="ovn">After £50 included credit is used</div></div>
            <div class="ovi"><div class="ovl">Growth overage rate</div><div class="ovr">£0.13<span style="font-size:11px;font-weight:400;color:var(--t3)">/min</span></div><div class="ovn">After £120 included credit is used</div></div>
            <div class="ovi"><div class="ovl">Interview extra minutes</div><div class="ovr">£0.15<span style="font-size:11px;font-weight:400;color:var(--t3)">/min</span></div><div class="ovn">Per minute over 10 min · separate invoice</div></div>
          </div>
        </div>

        <div class="calc">
          <div class="ch" style="margin-bottom:14px"><i class="ti ti-calculator grn"></i>Interview profit calculator</div>
          <div class="cr2"><label>Number of interviews</label><input type="range" min="1" max="100" value="20" step="1" id="sln" oninput="rc()"/><span class="v" id="vn">20</span></div>
          <div class="cr2"><label>Avg call length (minutes)</label><input type="range" min="3" max="15" value="7" step="1" id="slm" oninput="rc()"/><span class="v" id="vm">7 min</span></div>
          <div class="cres"><div class="cri"><div class="crl">Your cost</div><div class="crv r" id="rc2">£24.50</div></div><div class="cri"><div class="crl">Best bundle</div><div class="crv" id="rb2">25 × £89</div></div><div class="cri"><div class="crl">Your profit</div><div class="crv g" id="rp2">£54.00</div></div></div>
        </div>
      </div>

      <!-- ══ BILLING ══ -->
      <div class="pg" id="pg-billing">
        <div id="billing-checkout-status" class="billing-checkout-status" hidden aria-live="polite"></div>
        <div class="kg2" style="margin-bottom:12px">
          <div class="kpi"><div class="kl">Current plan</div><div class="kv" style="font-size:17px" id="billing-plan-name">—</div><div class="kd ne" id="billing-plan-renew">—</div></div>
          <div class="kpi"><div class="kl">Call usage</div><div class="kv" style="color:var(--grn)" id="billing-calls-used">—</div><div class="kd ne" id="billing-calls-label">—</div></div>
        </div>
        <div class="card" id="billing-usage-card" style="margin-bottom:12px;display:none">
          <div class="ch"><i class="ti ti-chart-bar grn"></i>Usage this period</div>
          <div id="billing-usage-body" style="font-size:13px;color:var(--t2);line-height:1.7"></div>
        </div>
        <div class="card" id="billing-change-card" style="margin-bottom:12px">
          <div class="ch"><i class="ti ti-switch-horizontal grn"></i>Change plan</div>
          <p id="billing-change-plan-hint" style="font-size:12.5px;color:var(--t2);margin:0 0 12px">Upgrade or downgrade your subscription. Usage limits update immediately; overage is calculated at period end.</p>
          <div class="plan-g plan-g-compact plan-g-inline" id="billing-plan-grid">
            <div style="grid-column:1/-1;padding:12px;text-align:center;color:var(--t3);font-size:13px">Loading plans…</div>
          </div>
        </div>
        <div class="card" id="billing-payment-method-card" hidden style="display:none"><div class="ch"><i class="ti ti-credit-card grn"></i>Payment method</div><div style="display:flex;align-items:center;gap:10px;font-size:13px;color:var(--t1)"><i class="ti ti-credit-card" style="font-size:18px;color:var(--t3)"></i>Visa ending 4242 <span class="bdg bg">Default</span><button class="btn bsm" style="margin-left:auto">Change card</button></div></div>
        <div class="card"><div class="ch"><i class="ti ti-file-invoice grn"></i>Invoices</div>
          <div id="billing-invoices-list">
            <div style="padding:12px;font-size:13px;color:var(--t3);">Loading invoices…</div>
          </div>
        </div>
      </div>

      <!-- ══ SUPPORT ══ -->
      <div class="pg" id="pg-support">
        <div class="g2">
          <div class="card" style="margin:0;cursor:pointer"><div class="ch"><i class="ti ti-book grn"></i>Documentation</div><div style="font-size:12px;color:var(--t3)">Setup guides, API docs, integration walkthroughs and FAQs</div></div>
          <div class="card" style="margin:0;cursor:pointer" onclick="toggleChat();toast('Chat opened — avg reply 2 min','tg')"><div class="ch"><i class="ti ti-message-circle grn"></i>Live chat</div><div style="font-size:12px;color:var(--t3)">Mon–Fri 9am–6pm GMT · Avg reply under 5 minutes</div></div>
        </div>
        <div class="g2" style="margin-top:12px">
          <div class="card" style="margin:0;cursor:pointer"><div class="ch"><i class="ti ti-video grn"></i>Book onboarding call</div><div style="font-size:12px;color:var(--t3)">Free 30-min setup call with our team — available for all plans</div></div>
          <div class="card" style="margin:0;cursor:pointer"><div class="ch"><i class="ti ti-mail grn"></i>Email support</div><div style="font-size:12px;color:var(--t3)">support@voxbulk.com · 24-hour response guarantee</div></div>
        </div>
        <div class="g2" style="margin-top:12px">
          <div class="card" style="margin:0;cursor:pointer"><div class="ch"><i class="ti ti-activity grn"></i>Status page</div><div style="font-size:12px;color:var(--t3)">status.voxbulk.com — real-time system health and uptime</div></div>
          <div class="card" style="margin:0;cursor:pointer"><div class="ch"><i class="ti ti-shield grn"></i>Legal &amp; compliance</div><div style="font-size:12px;color:var(--t3)">Privacy policy · Terms of service · Download DPA (GDPR)</div></div>
        </div>
      </div>

    </div>
  </div>
</div>



<!-- ═══ SURVEY WHATSAPP PREVIEW ═══ -->
<div id="sur-wa-preview-overlay">
  <div class="wa-preview-box">
    <div class="wa-preview-hd">
      <div>
        <div class="wa-preview-title"><i class="ti ti-brand-whatsapp"></i> WhatsApp survey preview</div>
        <div class="wa-preview-sub" id="sur-wa-preview-sub">Your business identity · iPhone preview</div>
      </div>
      <button class="btn bsm" type="button" onclick="closeSurveyWaPreview()"><i class="ti ti-x"></i></button>
    </div>
    <div class="wa-preview-stage">
      <div class="wa-device-shell">
        <div class="wa-device-btn wa-device-btn-action" aria-hidden="true"></div>
        <div class="wa-device-btn wa-device-btn-vol-up" aria-hidden="true"></div>
        <div class="wa-device-btn wa-device-btn-vol-down" aria-hidden="true"></div>
        <div class="wa-device-btn wa-device-btn-power" aria-hidden="true"></div>
        <div class="wa-device wa-device-iphone17">
          <div class="wa-device-bezel">
            <div class="wa-device-island" aria-hidden="true"><span class="wa-island-cam"></span></div>
            <div class="wa-device-screen wa-survey-screen">
              <div class="wa-status-bar wa-survey-status"><span class="wa-status-time">9:41</span><span class="wa-status-icons"><i class="ti ti-antenna-bars-5"></i><i class="ti ti-wifi"></i><i class="ti ti-battery-3"></i></span></div>
              <div class="wa-survey-header">
                <div class="wa-survey-avatar wa-survey-avatar-initials" id="sur-wa-org-avatar">—</div>
                <div>
                  <div class="wa-survey-title" id="sur-wa-org-title">Your business</div>
                  <div class="wa-survey-sub"><i class="ti ti-circle-filled"></i>Online now</div>
                </div>
                <i class="ti ti-dots-vertical wa-survey-menu"></i>
              </div>
              <div class="wa-survey-progress"><div class="wa-survey-progress-fill" id="sur-wa-progress"></div></div>
              <div class="wa-survey-step" id="sur-wa-step-ind">Getting started</div>
              <div class="wa-chat-body">
                <div class="wa-preview-chat wa-survey-body" id="sur-wa-chat"></div>
              </div>
              <div class="wa-survey-send-bar">
                <input class="wa-survey-send-input" type="text" placeholder="Type a message..." readonly />
                <button class="wa-survey-send-btn" type="button" tabindex="-1" aria-label="Send"><i class="ti ti-send"></i></button>
              </div>
              <div class="wa-home-indicator" aria-hidden="true"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="wa-preview-foot">
      <button class="btn bsm" type="button" onclick="resetSurveyWaPreview()"><i class="ti ti-refresh"></i>Restart preview</button>
      <button class="btn btng bsm" type="button" onclick="closeSurveyWaPreview()">Done</button>
    </div>
  </div>
</div>

<!-- ═══ CONFIRM DIALOG ═══ -->
<div id="confirm-overlay">
  <div class="confirm-box">
    <div class="confirm-title"><i class="ti ti-alert-triangle" style="color:var(--amb);font-size:18px"></i><span id="confirm-title-text">Are you sure?</span></div>
    <div class="confirm-msg" id="confirm-msg-text">This action cannot be undone.</div>
    <div class="confirm-btns">
      <button class="btn bsm" onclick="closeConfirm()">Cancel</button>
      <button class="btn bsm btnr" id="confirm-ok-btn">Confirm</button>
    </div>
  </div>
</div>

<!-- ═══ TOAST CONTAINER ═══ -->
<div id="toast-container"></div>

<!-- ═══ LIVE CHAT WINDOW ═══ -->
<style>
/* ── Chat fab ── */
.chat-fab{position:fixed;bottom:24px;right:24px;z-index:9000;width:52px;height:52px;border-radius:50%;background:var(--grn);box-shadow:0 4px 18px rgba(0,158,118,.45);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:transform .2s,box-shadow .2s;border:none}
.chat-fab:hover{transform:scale(1.08);box-shadow:0 6px 24px rgba(0,158,118,.55)}
.chat-fab i{font-size:22px;color:#fff}
.chat-fab-badge{position:absolute;top:3px;right:3px;width:16px;height:16px;border-radius:50%;background:var(--red);border:2px solid var(--bg);font-size:9px;color:#fff;font-weight:700;display:flex;align-items:center;justify-content:center}

/* ── Chat window ── */
.chat-win{position:fixed;bottom:88px;right:24px;z-index:9000;width:340px;height:480px;background:var(--s1);border:1px solid var(--b2);border-radius:18px;box-shadow:0 12px 48px rgba(0,0,0,.18);display:flex;flex-direction:column;overflow:hidden;transition:opacity .2s,transform .2s;transform-origin:bottom right}
.chat-win.hidden{opacity:0;pointer-events:none;transform:scale(.92) translateY(10px)}

/* Header */
.cw-head{padding:13px 15px;background:var(--grn);display:flex;align-items:center;gap:10px;flex-shrink:0}
.cw-av{width:34px;height:34px;border-radius:50%;background:rgba(255,255,255,.25);display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:15px;font-weight:700;color:#fff}
.cw-info{flex:1;min-width:0}
.cw-name{font-size:13px;font-weight:700;color:#fff}
.cw-status{font-size:10.5px;color:rgba(255,255,255,.8);display:flex;align-items:center;gap:4px;margin-top:1px}
.cw-sdot{width:6px;height:6px;border-radius:50%;background:#7fff7f;animation:pu 1.5s infinite}
.cw-actions{display:flex;gap:6px}
.cw-act{width:28px;height:28px;border-radius:8px;background:rgba(255,255,255,.15);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:background .15s;border:none}
.cw-act:hover{background:rgba(255,255,255,.28)}
.cw-act i{font-size:15px;color:#fff}

/* Tabs */
.cw-tabs{display:flex;border-bottom:1px solid var(--b1);background:var(--s1);flex-shrink:0}
.cw-tab{flex:1;padding:9px 6px;font-size:11.5px;font-weight:500;color:var(--t3);cursor:pointer;text-align:center;transition:color .15s;border:none;background:transparent;border-bottom:2px solid transparent;font-family:inherit}
.cw-tab:hover{color:var(--t1)}
.cw-tab.on{color:var(--grn);border-bottom-color:var(--grn);font-weight:700}

/* Messages area */
.cw-msgs{flex:1;overflow-y:auto;padding:13px;display:flex;flex-direction:column;gap:10px;scrollbar-width:thin}
.cw-msgs::-webkit-scrollbar{width:4px}
.cw-msgs::-webkit-scrollbar-thumb{background:var(--b2);border-radius:2px}

/* Bubbles */
.msg{display:flex;gap:7px;align-items:flex-end}
.msg.out{flex-direction:row-reverse}
.msg-av{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;flex-shrink:0}
.msg-av.sup{background:var(--gd);color:var(--grn)}
.msg-av.usr{background:var(--pd);color:var(--pur)}
.msg-bub{max-width:76%;padding:9px 12px;border-radius:14px;font-size:12px;line-height:1.5;color:var(--t1)}
.msg.in .msg-bub{background:var(--s2);border-radius:4px 14px 14px 14px}
.msg.out .msg-bub{background:var(--grn);color:#fff;border-radius:14px 14px 4px 14px}
.msg-time{font-size:9.5px;color:var(--t3);text-align:right;margin-top:3px}
.msg.out .msg-time{color:rgba(255,255,255,.7)}

/* Typing indicator */
.typing-bub{display:flex;align-items:center;gap:3px;padding:10px 13px;background:var(--s2);border-radius:4px 14px 14px 14px;width:fit-content}
.typing-dot{width:6px;height:6px;border-radius:50%;background:var(--t3);animation:tdot 1.2s infinite}
.typing-dot:nth-child(2){animation-delay:.2s}
.typing-dot:nth-child(3){animation-delay:.4s}
@keyframes tdot{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-5px)}}

/* Quick replies */
.quick-replies{padding:0 13px 10px;display:flex;gap:6px;flex-wrap:wrap;flex-shrink:0}
.qr-chip{font-size:11px;padding:5px 11px;border-radius:20px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t2);cursor:pointer;transition:var(--transition);white-space:nowrap;font-family:inherit}
.qr-chip:hover{border-color:var(--grn);color:var(--grn);background:var(--gd)}

/* Input row */
.cw-input{padding:10px 12px;border-top:1px solid var(--b1);display:flex;gap:8px;align-items:center;flex-shrink:0;background:var(--s1)}
.cw-textarea{flex:1;font-size:12.5px;padding:8px 11px;border-radius:10px;border:1.5px solid var(--b2);background:var(--s2);color:var(--t1);font-family:inherit;resize:none;line-height:1.4;max-height:80px;outline:none;transition:border-color .15s}
.cw-textarea:focus{border-color:var(--grn);background:var(--s1)}
.cw-send{width:34px;height:34px;border-radius:10px;background:var(--grn);border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:background .15s}
.cw-send:hover{background:var(--grn2)}
.cw-send i{font-size:16px;color:#fff}
.cw-attach{width:34px;height:34px;border-radius:10px;background:transparent;border:1.5px solid var(--b2);cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:background .15s;color:var(--t3)}
.cw-attach:hover{background:var(--s2);color:var(--t1)}
.cw-attach i{font-size:16px}

/* Team tab */
.agent-row{display:flex;align-items:center;gap:10px;padding:9px 13px;border-bottom:1px solid var(--b1);cursor:pointer;transition:background .12s}
.agent-row:hover{background:var(--s2)}
.agent-row:last-child{border-bottom:none}
.ag-av{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0}
.ag-dot{width:8px;height:8px;border-radius:50%;border:2px solid var(--s1);position:absolute;bottom:0;right:0}
.ag-wrap{position:relative;flex-shrink:0}
.ag-info{flex:1;min-width:0}
.ag-name{font-size:12.5px;font-weight:600;color:var(--t1)}
.ag-role{font-size:10.5px;color:var(--t3)}
.ag-stat{font-size:10px;padding:2px 8px;border-radius:10px;font-weight:600}
</style>

<!-- FAB button -->
<button class="chat-fab" onclick="toggleChat()" id="chat-fab" title="Live support chat">
  <i class="ti ti-message-circle" id="chat-fab-ic"></i>
  <div class="chat-fab-badge" id="chat-badge">1</div>
</button>

<!-- Chat window -->
<div class="chat-win hidden" id="chat-win">
  <!-- Header -->
  <div class="cw-head">
    <div class="cw-av">VS</div>
    <div class="cw-info">
      <div class="cw-name">VoxBulk Support</div>
      <div class="cw-status"><span class="cw-sdot"></span>Online — avg reply 2 min</div>
    </div>
    <div class="cw-actions">
      <button class="cw-act" title="Minimise" onclick="toggleChat()"><i class="ti ti-minus"></i></button>
      <button class="cw-act" title="Close" onclick="closeChat()"><i class="ti ti-x"></i></button>
    </div>
  </div>

  <!-- Tabs -->
  <div class="cw-tabs">
    <button class="cw-tab on" onclick="cwTab(this,'chat-pane')" id="tab-chat">💬 Chat</button>
    <button class="cw-tab" onclick="cwTab(this,'team-pane')" id="tab-team">👥 Team</button>
    <button class="cw-tab" onclick="cwTab(this,'history-pane')" id="tab-history">📋 History</button>
  </div>

  <!-- ── CHAT PANE ── -->
  <div id="chat-pane" style="display:flex;flex-direction:column;flex:1;overflow:hidden">
    <div class="cw-msgs" id="cw-msgs">
      <!-- Welcome message -->
      <div class="msg in">
        <div class="msg-av sup">VS</div>
        <div>
          <div class="msg-bub">👋 Hi! I'm Sarah from VoxBulk support. How can I help you today?</div>
          <div class="msg-time">Just now</div>
        </div>
      </div>
    </div>

    <!-- Quick reply chips -->
    <div class="quick-replies" id="quick-replies">
      <button class="qr-chip" onclick="sendQuick(this,'I need help setting up my AI voice')">🎙️ AI voice setup</button>
      <button class="qr-chip" onclick="sendQuick(this,'Billing question')">💳 Billing</button>
      <button class="qr-chip" onclick="sendQuick(this,'Integration not connecting')">🔌 Integration issue</button>
      <button class="qr-chip" onclick="sendQuick(this,'How do I start an interview campaign?')">📋 Interviews</button>
    </div>

    <!-- Input -->
    <div class="cw-input">
      <button class="cw-attach" title="Attach file"><i class="ti ti-paperclip"></i></button>
      <textarea class="cw-textarea" id="cw-input" placeholder="Type a message…" rows="1"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMsg()}"
        oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,80)+'px'"></textarea>
      <button class="cw-send" onclick="sendMsg()" title="Send"><i class="ti ti-send"></i></button>
    </div>
  </div>

  <!-- ── TEAM PANE ── -->
  <div id="team-pane" style="display:none;flex:1;overflow-y:auto">
    <div style="padding:12px 13px 8px;font-size:11px;color:var(--t3);font-weight:700;text-transform:uppercase;letter-spacing:.06em">Online now</div>
    <div class="agent-row">
      <div class="ag-wrap"><div class="ag-av av-g">SC</div><div class="ag-dot" style="background:#22c55e"></div></div>
      <div class="ag-info"><div class="ag-name">Sarah Chen</div><div class="ag-role">Customer success · Tier 1</div></div>
      <span class="ag-stat bg">Online</span>
    </div>
    <div class="agent-row">
      <div class="ag-wrap"><div class="ag-av av-b">MK</div><div class="ag-dot" style="background:#22c55e"></div></div>
      <div class="ag-info"><div class="ag-name">Mike Kowalski</div><div class="ag-role">Technical support</div></div>
      <span class="ag-stat bg">Online</span>
    </div>
    <div style="padding:12px 13px 8px;font-size:11px;color:var(--t3);font-weight:700;text-transform:uppercase;letter-spacing:.06em;border-top:1px solid var(--b1);margin-top:4px">Away</div>
    <div class="agent-row">
      <div class="ag-wrap"><div class="ag-av av-p">JP</div><div class="ag-dot" style="background:var(--amb)"></div></div>
      <div class="ag-info"><div class="ag-name">Jenny Park</div><div class="ag-role">Onboarding specialist</div></div>
      <span class="ag-stat ba">Away</span>
    </div>
    <div class="agent-row" style="border-bottom:none">
      <div class="ag-wrap"><div class="ag-av av-r">DL</div><div class="ag-dot" style="background:var(--t3)"></div></div>
      <div class="ag-info"><div class="ag-name">David Liu</div><div class="ag-role">Senior engineer</div></div>
      <span class="ag-stat" style="background:var(--s2);color:var(--t3)">Offline</span>
    </div>
  </div>

  <!-- ── HISTORY PANE ── -->
  <div id="history-pane" style="display:none;flex:1;overflow-y:auto">
    <div style="padding:12px 13px 8px;font-size:11px;color:var(--t3);font-weight:700;text-transform:uppercase;letter-spacing:.06em">Previous conversations</div>
    <div class="agent-row" style="flex-direction:column;align-items:flex-start;gap:4px;padding:11px 13px">
      <div style="display:flex;align-items:center;gap:8px;width:100%">
        <span class="bdg bg" style="font-size:9.5px">Resolved</span>
        <span style="font-size:10px;color:var(--t3);margin-left:auto">14 May 2026</span>
      </div>
      <div style="font-size:12.5px;font-weight:600;color:var(--t1)">ElevenLabs TTS not connecting</div>
      <div style="font-size:11px;color:var(--t3)">Resolved by Sarah Chen · 8 min</div>
    </div>
    <div class="agent-row" style="flex-direction:column;align-items:flex-start;gap:4px;padding:11px 13px">
      <div style="display:flex;align-items:center;gap:8px;width:100%">
        <span class="bdg bg" style="font-size:9.5px">Resolved</span>
        <span style="font-size:10px;color:var(--t3);margin-left:auto">2 May 2026</span>
      </div>
      <div style="font-size:12.5px;font-weight:600;color:var(--t1)">Dentally sync stopped working</div>
      <div style="font-size:11px;color:var(--t3)">Resolved by Mike Kowalski · 22 min</div>
    </div>
    <div class="agent-row" style="flex-direction:column;align-items:flex-start;gap:4px;padding:11px 13px;border-bottom:none">
      <div style="display:flex;align-items:center;gap:8px;width:100%">
        <span class="bdg bg" style="font-size:9.5px">Resolved</span>
        <span style="font-size:10px;color:var(--t3);margin-left:auto">18 Apr 2026</span>
      </div>
      <div style="font-size:12.5px;font-weight:600;color:var(--t1)">Billing plan upgrade question</div>
      <div style="font-size:11px;color:var(--t3)">Resolved by Jenny Park · 5 min</div>
    </div>
  </div>
</div>`;
export default bodyHtml;
