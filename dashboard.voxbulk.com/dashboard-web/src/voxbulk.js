
var titles={
  dashboard:['Dashboard','Live · Overview'],
  queue:['Recovery queue','Patients who missed or cancelled'],
  noshow:['No-show follow-up','AI contacts no-shows and offers to rebook'],
  emergency:['Emergency reschedule','Cancel a day or window — AI calls all patients'],
  recall:['Recall campaigns','Proactively fill chairs with overdue dental patients'],
  offers:['Offer campaigns','Fill empty slots with targeted offers'],
  interviews:['Interviews','AI phone or Zoom interview screening'],
  surveys:['Surveys','AI-powered phone and WhatsApp surveys'],
  'survey-detail':['Survey detail','Review, pay, and manage your campaign'],
  'results-i':['Interview results','Candidate scoring, recordings and analysis'],
  'results-s':['Survey results','Anonymous aggregate insights and exports'],
  reports:['Reports','Performance analytics and cost breakdown'],
  reminders:['Reminder sequences','Automated WhatsApp timing and message settings'],
  profile:['Profile settings','Company info, branding and revenue settings'],
  system:['System settings','API connection, WhatsApp messages and AI calling'],
  team:['Team members','Roles and access control'],
  optout:['Opt-out list','Do-not-call management — required under PECR'],
  audit:['Audit log','Full activity and compliance history'],
  packages:['Packages & pricing','Subscription plans, interview and survey bundles'],
  billing:['Billing','Plan, usage and invoice history'],
  support:['Support','Help, documentation and legal']
};

// ── NAVIGATION ──
function toggleSetupChecklist(show){
  var card=document.getElementById('ob-card');
  var btn=document.getElementById('ob-show-btn');
  if(!card) return;
  var open=(show===true)?true:(show===false?false:card.style.display==='none');
  card.style.display=open?'block':'none';
  if(btn) btn.style.display=open?'none':'inline-flex';
}
function syncSetupChecklistForPage(id){
  if(id==='system'){
    toggleSetupChecklist(true);
  }
}
function go(id,el){
  document.querySelectorAll('.pg').forEach(p=>p.classList.remove('on'));
  document.querySelectorAll('.ni').forEach(n=>n.classList.remove('on'));
  var pg=document.getElementById('pg-'+id);
  if(pg) pg.classList.add('on');
  // highlight correct nav item
  document.querySelectorAll('.ni').forEach(function(n){
    if(n.getAttribute('onclick')&&n.getAttribute('onclick').includes("'"+id+"'")) n.classList.add('on');
  });
  var t=titles[id]||[id,''];
  document.getElementById('tb-t').textContent=t[0];
  var s=id==='dashboard'?'<span class="ldot"></span> '+t[1]:t[1];
  document.getElementById('tb-s').innerHTML=s;
  closeNotif();
  syncSetupChecklistForPage(id);
  if(typeof window.onSurveyPageNav==='function') window.onSurveyPageNav(id);
  if(id==='reports'&&typeof window.reloadInterviewReports==='function') window.reloadInterviewReports();
  window.scrollTo(0,0);
}
// Convenience nav — finds and highlights correct sidebar item automatically
function goNav(id){
  go(id,null);
}

// ── SIDEBAR ──
var sbOpen=true;
function toggleSidebar(){
  sbOpen=!sbOpen;
  var sb=document.getElementById('sb');
  var main=document.getElementById('main');
  var ic=document.getElementById('sb-tog-ic');
  sb.classList.toggle('collapsed',!sbOpen);
  main.classList.toggle('expanded',!sbOpen);
  ic.className=sbOpen?'ti ti-layout-sidebar-left-collapse':'ti ti-layout-sidebar-left-expand';
}

// ── DARK MODE (persisted) ──
var dark=localStorage.getItem('vb-dark')==='1';
if(dark){document.body.classList.add('dark');}
function toggleDark(){
  dark=!dark;
  document.body.classList.toggle('dark',dark);
  document.getElementById('mode-i').className=dark?'ti ti-sun':'ti ti-moon';
  localStorage.setItem('vb-dark',dark?'1':'0');
}
// set icon on load
if(document.getElementById('mode-i')) document.getElementById('mode-i').className=dark?'ti ti-sun':'ti ti-moon';

// ── NOTIFICATIONS ──
var notifOpen=false;
function toggleNotif(){
  notifOpen=!notifOpen;
  document.getElementById('npanel').style.display=notifOpen?'block':'none';
}
function closeNotif(){notifOpen=false;var n=document.getElementById('npanel');if(n)n.style.display='none';}
document.addEventListener('click',function(e){if(!e.target.closest('.nbell'))closeNotif();});

// ── ESC KEY closes panels ──
document.addEventListener('keydown',function(e){
  if(e.key==='Escape'){
    closeNotif();
    closeConfirm();
    var rp=document.getElementById('rec-panel'); if(rp) rp.style.display='none';
    var sp=document.getElementById('srec-panel'); if(sp) sp.style.display='none';
    if(chatOpen) toggleChat();
  }
});

// ── SYSTEM SETTINGS TABS ──
function stab(id,el){
  document.querySelectorAll('.tpcont').forEach(p=>p.classList.remove('on'));
  document.querySelectorAll('.tb').forEach(t=>t.classList.remove('on'));
  document.getElementById('stp-'+id).classList.add('on');
  el.classList.add('on');
}

// ── BOOKING SYSTEM SELECTOR ──
var credForms=['apikey','multi','userpass','oauth','standalone'];
function selSys(el,type){
  var nameEl=el.querySelector('.sn');
  var name=nameEl?nameEl.textContent:'';
  if(name.indexOf('Calendly')>=0||name.indexOf('Cronofy')>=0){
    toast('Scheduling integration coming soon — Phase 5','tw');
  }
  document.querySelectorAll('.sysb').forEach(s=>s.classList.remove('sel'));
  el.classList.add('sel');
  credForms.forEach(function(f){var e2=document.getElementById('cred-'+f);if(e2)e2.style.display='none';});
  var target=document.getElementById('cred-'+type);
  if(target) target.style.display='block';
  var ast=document.getElementById('ast');
  if(ast&&type!=='apikey') ast.innerHTML='<span class="sdotl sgr2"></span><span style="color:var(--t3)">Enter credentials for '+el.querySelector('.sn').textContent+'</span>';
}
function vkey(){
  var s=document.getElementById('ast');
  s.innerHTML='<span style="color:var(--t3);font-size:12px">Validating...</span>';
  setTimeout(function(){s.innerHTML='<span class="sdotl sg2"></span><span style="color:var(--grn);font-weight:600">Connected — Dentally syncing live</span>';toast('Dentally connected successfully','tg');},1100);
}

// ── WHATSAPP PREVIEW ──
var smp={'{first_name}':'Sarah','{clinic_name}':'Bright Smiles','{date}':'Mon 19 May','{time}':'2:30pm','{service}':'Check-up'};
function uwp(){
  var m=document.getElementById('msg-r').value;
  Object.entries(smp).forEach(function([k,v]){m=m.replaceAll(k,v);});
  document.getElementById('wap').textContent=m;
  document.getElementById('wb1p').textContent=document.getElementById('wb1').value||'Button 1';
  document.getElementById('wb2p').textContent=document.getElementById('wb2').value||'Button 2';
}
function iv(id,v){
  var ta=document.getElementById(id);
  var s=ta.selectionStart,e=ta.selectionEnd;
  ta.value=ta.value.slice(0,s)+v+ta.value.slice(e);
  ta.selectionStart=ta.selectionEnd=s+v.length;
  ta.focus();uwp();
}

// ── VOICE SELECTORS (fixed) ──
function selVc(el){document.querySelectorAll('.vo').forEach(function(v){v.classList.remove('sel');});el.classList.add('sel');}
function selFmt(el,grpId){
  var grp=document.getElementById(grpId);
  if(grp) grp.querySelectorAll('.vo').forEach(function(v){v.classList.remove('sel');});
  el.classList.add('sel');
}

// ── AI SCRIPT GENERATOR ──
var scrpts=[
  'We noticed you missed your appointment today and we\'d love to help you find a new time. Do you have a moment — it\'ll only take a minute?',
  'We noticed your appointment slot is now free and we\'d love to get you rebooked at a time that works for you.',
  'We\'re reaching out because your appointment wasn\'t completed today. We have some great slots coming up — shall I offer you a few options?'
];
var si=0;
function gsc(){
  var p=document.getElementById('scp');
  p.style.opacity='.3';
  setTimeout(function(){si=(si+1)%scrpts.length;p.textContent='"'+scrpts[si]+'"';p.style.opacity='1';toast('Script regenerated','tg');},700);
}

// ── PRICING TOGGLE ──
var yr=false;var prs=[{m:79,y:63},{m:179,y:143}];
function tb(){
  yr=!yr;
  var t=document.getElementById('tgl');
  if(t){t.classList.toggle('y',yr);}
  var tlm=document.getElementById('tl-m');var tly=document.getElementById('tl-y');
  if(tlm){tlm.classList.toggle('on',!yr);}
  if(tly){tly.classList.toggle('on',yr);}
  var pp1=document.getElementById('pp1');var pp2=document.getElementById('pp2');
  if(pp1) pp1.innerHTML='£'+(yr?prs[0].y:prs[0].m)+'<span>/mo</span>';
  if(pp2) pp2.innerHTML='£'+(yr?prs[1].y:prs[1].m)+'<span>/mo</span>';
}

// ── PROFIT CALCULATOR ──
function rc(){
  var sln=document.getElementById('sln');var slm=document.getElementById('slm');
  if(!sln||!slm) return;
  var n=parseInt(sln.value);var m=parseInt(slm.value);
  document.getElementById('vn').textContent=n;
  document.getElementById('vm').textContent=m+' min';
  var cost=+(n*m*0.15+n*0.20).toFixed(2);
  var buns=[{c:10,p:39},{c:25,p:89},{c:50,p:159},{c:100,p:279}];
  var rec=buns.find(function(b){return b.c>=n;})||buns[buns.length-1];
  var profit=+(rec.p-cost).toFixed(2);
  document.getElementById('rc2').textContent='£'+cost.toFixed(2);
  document.getElementById('rb2').textContent=rec.c+' × £'+rec.p;
  document.getElementById('rp2').textContent=profit>0?'£'+profit.toFixed(2):'£0.00';
  document.getElementById('rp2').style.color=profit>0?'var(--grn)':'var(--red)';
}
function cb(n){var sln=document.getElementById('sln');if(sln){sln.value=Math.min(n,100);rc();}}
function cbS(n,p){}

// ── REMINDER SEQUENCE TOGGLE ──
function togS(el){
  el.classList.toggle('on');el.classList.toggle('off');
  el.closest('.seq').classList.toggle('off',el.classList.contains('off'));
}

// ── PER-TREATMENT TOGGLE ──
function togPerTx(el){
  el.classList.toggle('on');el.classList.toggle('off');
  var on=el.classList.contains('on');
  document.getElementById('per-lbl').textContent=on?'On — using per-treatment values below':'Off — using flat rate £85 for all treatments';
  document.getElementById('per-table').style.display=on?'block':'none';
}

// ── INTERVIEW RECORDING PANEL ──
function showRec(name,dur,task,sent){
  document.getElementById('rec-name').textContent=name;
  document.getElementById('rec-dur').textContent=dur;
  document.getElementById('rec-task').textContent=task;
  document.getElementById('rec-sent').textContent=sent;
  document.getElementById('rec-av').textContent=name.split(' ').map(function(w){return w[0];}).join('').slice(0,2);
  document.getElementById('rec-panel').style.display='block';
  buildWave('wave-track');
  document.getElementById('rec-panel').scrollIntoView({behavior:'smooth',block:'nearest'});
}

// ── SURVEY RECORDING PANEL ──
function showSurveyRec(name,dur){
  document.getElementById('srec-name').textContent=name;
  document.getElementById('srec-dur').textContent=dur;
  document.getElementById('srec-av').textContent=name.split(' ').map(function(w){return w[0];}).join('').slice(0,2);
  document.getElementById('srec-panel').style.display='block';
  buildWave('swave-track');
  document.getElementById('srec-panel').scrollIntoView({behavior:'smooth',block:'nearest'});
}

// ── AUDIO WAVE ──
function buildWave(id){
  var track=document.getElementById(id);
  if(!track) return;
  track.innerHTML='';
  for(var i=0;i<48;i++){
    var b=document.createElement('div');
    b.className='wv'+(i<14?' played':'');
    b.style.height=(Math.random()*60+20)+'%';
    track.appendChild(b);
  }
}
var playing=false;
function togglePlay(){
  playing=!playing;
  var ic=document.getElementById('play-ic');
  if(ic) ic.className=playing?'ti ti-player-pause':'ti ti-player-play';
}

function intFmtSoon(){
  toast('Zoom interviews coming in Phase 5 — phone calls only for now','tw');
}

// ── INTERVIEW WINDOW PREVIEW ──
function updateIntWindow(){
  var sd=document.getElementById('int-start-date');
  var st=document.getElementById('int-start-time');
  var ed=document.getElementById('int-end-date');
  var et=document.getElementById('int-end-time');
  var prev=document.getElementById('int-window-preview');
  var tzHint=document.getElementById('int-window-tz-hint');
  if(!sd||!prev) return;
  var tz='';
  try{tz=Intl.DateTimeFormat().resolvedOptions().timeZone||'';}catch(e){}
  if(tzHint){
    tzHint.textContent=tz?'Times are in your local timezone ('+tz+').':'Times use your browser local timezone.';
  }
  if(sd.value&&ed.value){
    prev.style.display='flex';
    document.getElementById('int-window-text').textContent='Calling window: '+sd.value+' at '+(st&&st.value?st.value:'09:00')+' → '+ed.value+' at '+(et&&et.value?et.value:'17:00')+'. AI stops automatically.';
  } else {
    prev.style.display='none';
  }
}
window.intFmtSoon=intFmtSoon;

// ── SURVEY WINDOW PREVIEW ──
function updateSurWindow(){
  var sd=document.getElementById('sur-start-date');
  var st=document.getElementById('sur-start-time');
  var ed=document.getElementById('sur-end-date');
  var et=document.getElementById('sur-end-time');
  var prev=document.getElementById('sur-window-preview');
  if(!sd||!prev) return;
  if(sd.value&&ed.value){
    prev.style.display='flex';
    document.getElementById('sur-window-text').textContent='Calling window: '+sd.value+' at '+st.value+' → '+ed.value+' at '+et.value+'. AI stops automatically.';
  } else {
    prev.style.display='none';
  }
}

// ── CAMPAIGN LAUNCHERS ──
function launchIntCampaign(){
  var sd=document.getElementById('int-start-date');
  var ed=document.getElementById('int-end-date');
  if(!sd||!sd.value||!ed||!ed.value){toast('Please set a start and end date first','tr');return;}
  document.getElementById('int-live-banner').style.display='flex';
  toast('Interview campaign launched! AI will call from '+sd.value,'tg');
  window.scrollTo(0,0);
}
function launchSurCampaign(){
  var sd=document.getElementById('sur-start-date');
  var ed=document.getElementById('sur-end-date');
  if(!sd||!sd.value||!ed||!ed.value){toast('Please set a start and end date first','tr');return;}
  toast('Survey campaign launched! AI calling begins '+sd.value,'tg');
}

// ── DATE RANGE PICKER ──
function drpSel(el){
  document.querySelectorAll('.drp-opt').forEach(function(o){o.classList.remove('on');});
  el.classList.add('on');
  toast('Period: '+el.textContent,'tg');
}

// ── TOAST ──
function toast(msg,cls){
  var c=document.getElementById('toast-container');
  var t=document.createElement('div');
  t.className='toast '+(cls||'');
  var icon=cls==='tg'?'ti-check':cls==='tr'?'ti-alert-circle':'ti-info-circle';
  t.innerHTML='<i class="ti '+icon+'"></i>'+msg;
  c.appendChild(t);
  requestAnimationFrame(function(){requestAnimationFrame(function(){t.classList.add('show');});});
  setTimeout(function(){t.classList.remove('show');setTimeout(function(){t.remove();},300);},3000);
}
window.toast = toast;

// ── CONFIRM DIALOG ──
var confirmCb=null;
var confirmCancelCb=null;
function showConfirm(title,msg,okLabel,cb,cancelCb,cancelLabel){
  document.getElementById('confirm-title-text').textContent=title;
  document.getElementById('confirm-msg-text').textContent=msg;
  document.getElementById('confirm-ok-btn').textContent=okLabel||'Confirm';
  var cancelBtn=document.getElementById('confirm-cancel-btn');
  if(cancelBtn) cancelBtn.textContent=cancelLabel||'Cancel';
  confirmCb=cb;
  confirmCancelCb=cancelCb||null;
  document.getElementById('confirm-overlay').classList.add('show');
}
window.showConfirm = showConfirm;
function closeConfirm(didConfirm){
  document.getElementById('confirm-overlay').classList.remove('show');
  if(didConfirm && confirmCb) confirmCb();
  else if(!didConfirm && confirmCancelCb) confirmCancelCb();
  confirmCb=null;
  confirmCancelCb=null;
}
document.getElementById('confirm-ok-btn').addEventListener('click',function(){
  closeConfirm(true);
});
document.getElementById('confirm-cancel-btn')?.addEventListener('click',function(){
  closeConfirm(false);
});
document.getElementById('confirm-overlay').addEventListener('click',function(e){
  if(e.target===this) closeConfirm(false);
});

// ── INIT ──
rc();
buildWave('wave-track');
buildWave('swave-track');


// ── CHAT TOGGLE ──
var chatOpen=false;
function toggleChat(){
  chatOpen=!chatOpen;
  document.getElementById('chat-win').classList.toggle('hidden',!chatOpen);
  document.getElementById('chat-fab-ic').className=chatOpen?'ti ti-minus':'ti ti-message-circle';
  if(chatOpen){document.getElementById('chat-badge').style.display='none';document.getElementById('cw-msgs').scrollTop=9999;}
}
function closeChat(){
  chatOpen=false;
  document.getElementById('chat-win').classList.add('hidden');
  document.getElementById('chat-fab-ic').className='ti ti-message-circle';
}

// ── TABS ──
function cwTab(el,pane){
  document.querySelectorAll('.cw-tab').forEach(t=>t.classList.remove('on'));
  el.classList.add('on');
  ['chat-pane','team-pane','history-pane'].forEach(function(id){
    document.getElementById(id).style.display=(id===pane)?'flex':'none';
    if(id===pane&&id!=='chat-pane') document.getElementById(id).style.display='block';
  });
}

// ── SEND MESSAGE ──
var chatHistory=[{role:'support',text:"👋 Hi! I'm Sarah from VoxBulk support. How can I help you today?",time:'Just now'}];
var autoReplies={
  'default':["Thanks for reaching out! Let me look into that for you.","Got it — can you give me a bit more detail?","I'm checking on this now, one moment please ⏳","Sure, I can help with that! Here's what you need to do…","That's a great question. Let me pull up the docs for you."],
  'billing':["I'll pull up your billing details right away. One moment!","I can see your Starter plan is active. Would you like to discuss an upgrade?"],
  'integration':["Let me check your Dentally connection status. Can you confirm your API key is saved in System settings?","Most connection issues are resolved by re-entering the API key. Want me to walk you through it?"],
  'voice':["For ElevenLabs, make sure you're using the Flash (Turbo) model for lowest latency. Which TTS are you currently on?","I'd recommend the Creator plan on ElevenLabs — it gives you API access and the Flash model."],
  'interview':["Interview campaigns are under Other Services → Interviews. You can set a start and end time so the AI stops calling automatically!"]
};

function getAutoReply(text){
  var t=text.toLowerCase();
  if(t.includes('bill')||t.includes('price')||t.includes('plan')) return pick(autoReplies.billing);
  if(t.includes('integrat')||t.includes('connect')||t.includes('dentally')) return pick(autoReplies.integration);
  if(t.includes('voice')||t.includes('eleven')||t.includes('tts')||t.includes('sound')) return pick(autoReplies.voice);
  if(t.includes('interview')||t.includes('survey')||t.includes('campaign')) return pick(autoReplies.interview);
  return pick(autoReplies.default);
}
function pick(arr){return arr[Math.floor(Math.random()*arr.length)];}

function appendMsg(text,who,time){
  var msgs=document.getElementById('cw-msgs');
  var isOut=(who==='user');
  var av=isOut?'<div class="msg-av usr">BS</div>':'<div class="msg-av sup">SC</div>';
  var bub='<div class="msg-bub">'+text+'</div><div class="msg-time">'+(time||'Just now')+'</div>';
  var d=document.createElement('div');
  d.className='msg '+(isOut?'out':'in');
  d.innerHTML=isOut?bub+av:av+'<div>'+bub+'</div>';
  msgs.appendChild(d);
  msgs.scrollTop=9999;
}

function showTyping(){
  var msgs=document.getElementById('cw-msgs');
  var d=document.createElement('div');
  d.className='msg in';d.id='typing-ind';
  d.innerHTML='<div class="msg-av sup">SC</div><div class="typing-bub"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';
  msgs.appendChild(d);msgs.scrollTop=9999;
}
function removeTyping(){var t=document.getElementById('typing-ind');if(t)t.remove();}

function sendMsg(){
  var inp=document.getElementById('cw-input');
  var txt=inp.value.trim();
  if(!txt)return;
  // hide quick replies after first message
  document.getElementById('quick-replies').style.display='none';
  appendMsg(txt,'user','Just now');
  inp.value='';inp.style.height='auto';
  // auto-reply
  showTyping();
  setTimeout(function(){
    removeTyping();
    appendMsg(getAutoReply(txt),'support','Just now');
  },1200+Math.random()*800);
}

function sendQuick(el,text){
  document.getElementById('quick-replies').style.display='none';
  appendMsg(text,'user','Just now');
  showTyping();
  setTimeout(function(){
    removeTyping();
    appendMsg(getAutoReply(text),'support','Just now');
  },1200+Math.random()*800);
}
