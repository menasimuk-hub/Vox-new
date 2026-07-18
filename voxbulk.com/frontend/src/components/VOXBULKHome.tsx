import { useEffect, useState, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import {
  FileText, Sparkles, CalendarCheck, PhoneCall, BarChart3, CheckCircle2, MessageCircle,
  ArrowRight, ArrowUpRight, ShieldCheck, Zap, Layers, Users, Bot, Star,
  Upload, Mail, Inbox, Headphones, Clock, Wallet, Gauge,
  X, Check, Plug, Quote, Play, Calendar, FlaskConical, Building2,
} from "lucide-react";


import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { useTalkModal } from "@/components/TalkModal";
import { useCurrency, FX, SYM } from "@/components/CurrencyContext";
import { usePublicPricing, type PublicPlan } from "@/hooks/usePricing";


/* ---------------- HERO ---------------- */
function Equaliser() {
  return (
    <div className="flex items-end gap-[3px] h-5">
      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
        <span
          key={i}
          className="eq-bar w-[3px] rounded-full bg-gold"
          style={{ height: "100%", animationDelay: `${i * 0.12}s` }}
        />
      ))}
    </div>
  );
}

export function HeroDashboard() {
  const tickerItems = [
    "CV scored · Amelia C. · 92",
    "Interview booked · Joshua R.",
    "WhatsApp survey sent · 240 recipients",
    "AI call completed · 14m 32s",
    "Shortlist updated · Senior Engineer",
    "Final round auto-scheduled · Tue 14:30",
  ];
  return (
    <div className="relative w-full min-w-0">

      <div className="absolute inset-0 -m-6 rounded-[32px] bg-gradient-to-br from-blue-500/15 via-transparent to-teal/15 blur-2xl" />
      <span className="absolute -top-3 left-10 w-2 h-2 rounded-full bg-gold shadow-[0_0_12px_2px_rgba(212,169,58,0.6)] float-a" />
      <span className="absolute top-16 -left-4 w-1.5 h-1.5 rounded-full bg-teal float-b" />
      <span className="absolute -bottom-3 left-1/3 w-2.5 h-2.5 rounded-full bg-blue-400/80 shadow-[0_0_14px_2px_rgba(96,165,250,0.55)] float-a" style={{ animationDelay: "1.2s" }} />
      <span className="absolute -top-2 right-10 w-1.5 h-1.5 rounded-full bg-teal float-a" style={{ animationDelay: "1.6s" }} />
      <span className="absolute top-1/2 -right-3 w-2 h-2 rounded-full bg-white/40 float-b" style={{ animationDelay: "0.4s" }} />
      <div className="hidden md:flex absolute -left-8 top-24 items-center gap-1.5 px-2.5 h-7 rounded-full bg-white/[0.08] border border-white/15 backdrop-blur text-[11px] text-white/85 float-a" style={{ animationDelay: "0.6s" }}>
        <span className="w-1.5 h-1.5 rounded-full bg-gold" /> ATS 92 · Strong fit
      </div>
      <div className="hidden md:flex absolute -right-6 bottom-16 items-center gap-1.5 px-2.5 h-7 rounded-full bg-white/[0.08] border border-white/15 backdrop-blur text-[11px] text-white/85 float-b" style={{ animationDelay: "1.4s" }}>
        <span className="w-1.5 h-1.5 rounded-full bg-teal pulse-dot" /> AI call · live
      </div>
      <div className="relative sm:aspect-[16/10] w-full max-w-[720px] mx-auto rounded-2xl border border-white/10 bg-[#0E1A2E] shadow-elevated overflow-hidden flex flex-col">
        <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-white/10 bg-white/[0.03]">
          <span className="w-2 h-2 rounded-full bg-white/20" />
          <span className="w-2 h-2 rounded-full bg-white/20" />
          <span className="w-2 h-2 rounded-full bg-white/20" />
          <span className="ml-2 text-[11px] text-white/40">voxbulk.com · workspace</span>
          <span className="ml-auto inline-flex items-center gap-1.5 text-[10.5px] text-teal">
            <span className="w-1.5 h-1.5 rounded-full bg-teal pulse-dot" /> LIVE
          </span>
        </div>
        <div className="overflow-hidden border-b border-white/10 bg-white/[0.02]">
          <div className="flex gap-8 py-1.5 whitespace-nowrap animate-ticker text-[11px] text-white/55">
            {[...tickerItems, ...tickerItems].map((t, i) => (
              <span key={i} className="inline-flex items-center gap-2">
                <span className="w-1 h-1 rounded-full bg-gold" /> {t}
              </span>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-white/5">
          {[
            { icon: FileText, label: "CVs scanned", value: "1,248" },
            { icon: Gauge, label: "Avg ATS", value: "76" },
            { icon: PhoneCall, label: "Calls today", value: "312" },
            { icon: CalendarCheck, label: "Booked", value: "87" },
          ].map((s, i) => (
            <div key={i} className="bg-[#0E1A2E] px-3 py-2 text-left">
              <div className="flex items-center gap-1.5 text-white/50 text-[10px] uppercase tracking-wider">
                <s.icon size={11} className="text-gold" /> {s.label}
              </div>
              <div className="mt-0.5 text-[18px] font-bold text-white tracking-tight">{s.value}</div>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-[1.55fr_1fr] gap-px bg-white/5 flex-1 min-h-0">
          <div className="bg-[#0E1A2E] p-3 flex flex-col min-h-0">
            <div className="flex items-center justify-between mb-1.5">
              <div className="text-[10.5px] uppercase tracking-wider text-white/50 font-semibold">Top candidates</div>
              <div className="text-[10px] text-white/40">Senior Engineer · VB-ENG-204</div>
            </div>
            <div className="grid grid-cols-[1.4fr_0.55fr_0.55fr_0.7fr] gap-2 px-1 pb-1 text-[10px] uppercase tracking-wider text-white/40 border-b border-white/10">
              <span>Candidate</span><span className="text-right">ATS</span><span className="text-right">Interview</span><span className="text-right">Status</span>
            </div>
            <div className="flex-1 overflow-hidden divide-y divide-white/5">
              {[
                { name: "Amelia Carter", role: "Product Manager", ats: 92, iv: 89, status: "Booked", tone: "teal" },
                { name: "Joshua Reid", role: "Senior Engineer", ats: 88, iv: 84, status: "Shortlist", tone: "gold" },
                { name: "Priya Shah", role: "Backend Eng", ats: 81, iv: 79, status: "Review", tone: "blue" },
                { name: "Marcus Lee", role: "Full-stack", ats: 76, iv: 72, status: "Review", tone: "blue" },
                { name: "Hannah Wood", role: "Senior Engineer", ats: 68, iv: 65, status: "Hold", tone: "muted" },
              ].map((c) => (
                <div key={c.name} className="grid grid-cols-[1.4fr_0.55fr_0.55fr_0.7fr] gap-2 items-center py-1.5 px-1">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-400 to-teal flex items-center justify-center text-white font-semibold text-[9px] shrink-0">
                      {c.name.split(" ").map(n => n[0]).join("")}
                    </div>
                    <div className="min-w-0">
                      <div className="text-white font-semibold text-[12px] truncate leading-tight">{c.name}</div>
                      <div className="text-[10px] text-white/45 truncate leading-tight">{c.role}</div>
                    </div>
                  </div>
                  <div className="text-right text-[13px] font-bold text-gold tabular-nums">{c.ats}</div>
                  <div className="text-right text-[13px] font-bold text-teal tabular-nums">{c.iv}</div>
                  <div className="text-right">
                    <span className={`inline-block px-1.5 py-0.5 rounded-full text-[9.5px] font-semibold ${
                      c.tone === "teal" ? "bg-teal/15 text-teal" :
                      c.tone === "gold" ? "bg-gold/15 text-gold" :
                      c.tone === "blue" ? "bg-blue-400/15 text-blue-300" :
                      "bg-white/10 text-white/55"
                    }`}>{c.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-[#0B1626] p-3 flex flex-col min-h-0">
            <div className="flex items-center justify-between mb-2">
              <div className="text-[10.5px] uppercase tracking-wider text-white/50 font-semibold">Calling now</div>
              <span className="inline-flex items-center gap-1 text-[10px] text-teal">
                <span className="w-1.5 h-1.5 rounded-full bg-teal pulse-dot" /> Live
              </span>
            </div>
            <div className="rounded-xl bg-white/[0.04] border border-white/10 p-2.5 flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-gold to-blue-400 flex items-center justify-center text-navy font-bold text-[10px]">EM</div>
              <div className="flex-1 min-w-0">
                <div className="text-white text-[12px] font-semibold truncate leading-tight">Elena Martín</div>
                <div className="text-[10px] text-white/50 leading-tight">Q4 · skills · 08:42</div>
              </div>
              <Equaliser />
            </div>
            <div className="mt-2 rounded-lg bg-white/[0.03] border border-white/5 p-2 text-[10.5px] text-white/65 leading-snug">
              <span className="text-teal">AI:</span> "Tell me about a system you scaled past 1M users…"
            </div>
            <div className="mt-2 grid grid-cols-3 gap-1.5">
              {[
                { l: "Skills", v: "9.1" },
                { l: "Comms", v: "8.7" },
                { l: "Fit", v: "9.0" },
              ].map(m => (
                <div key={m.l} className="rounded-md bg-white/[0.04] border border-white/5 px-1.5 py-1 text-center">
                  <div className="text-[9px] uppercase tracking-wider text-white/45">{m.l}</div>
                  <div className="text-[13px] font-bold text-gold tabular-nums">{m.v}</div>
                </div>
              ))}
            </div>
            <div className="mt-auto pt-2 flex items-center justify-between text-[10px] text-white/45">
              <span>Queue · 6 waiting</span>
              <span className="inline-flex items-center gap-1 text-teal"><CheckCircle2 size={10} /> Auto-scoring</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Hero({
  badgeText = "Live now · AI Assistant Platform",
  headline,
  sub,
  primaryHref = "/contact",
  primaryLabel = "Request a demo",
  secondaryLabel = "Talk to us",
  onSecondary,
}: {
  badgeText?: string;
  headline?: React.ReactNode;
  sub?: React.ReactNode;
  primaryHref?: string;
  primaryLabel?: string;
  secondaryLabel?: string;
  onSecondary?: () => void;
} = {}) {
  const talk = useTalkModal();
  const handleSecondary = onSecondary ?? talk.open;
  const heading = headline ?? (
    <>
      <span className="sr-only">VoxBulk — </span>
      Intelligent screening. <span className="serif-italic text-gold">Instant results.</span>
    </>
  );
  const subCopy = sub ?? (
    <>
      VoxBulk automates conversations, workflows and data collection — so your team
      can focus on decisions, not coordination.
    </>
  );
  return (
    <section id="top" className="relative overflow-hidden bg-navy text-white pt-[112px] md:pt-[128px] pb-16 md:pb-20">
      <div className="absolute inset-0 bg-grid opacity-[0.3]" />
      <div className="absolute inset-0 bg-hero-glow" />
      <div className="absolute -top-24 -left-20 w-[380px] h-[380px] rounded-full blur-3xl opacity-30 float-a"
           style={{ background: "radial-gradient(circle, #1E6FD9 0%, transparent 60%)" }} />
      <div className="absolute -bottom-24 -right-20 w-[380px] h-[380px] rounded-full blur-3xl opacity-25 float-b"
           style={{ background: "radial-gradient(circle, #4FB3A9 0%, transparent 60%)" }} />

      <div className="relative max-w-[1320px] mx-auto px-5 md:px-10 grid lg:grid-cols-[0.85fr_1.15fr] gap-10 lg:gap-12 items-center">
        <div className="text-left min-w-0">
          <div className="inline-flex items-center gap-2 px-3.5 h-8 rounded-full border border-white/15 bg-white/[0.06] text-[12.5px] text-white/80 backdrop-blur">
            <span className="w-1.5 h-1.5 rounded-full bg-teal pulse-dot" />
            {badgeText}
          </div>

          <h1 className="mt-5 text-[30px] sm:text-[42px] lg:text-[54px] font-bold tracking-[-0.035em] leading-[1.08] text-white break-words">
            {heading}
          </h1>

          <p className="mt-5 max-w-[520px] text-[15px] sm:text-[16px] md:text-[17px] text-white/70 leading-[1.6]">
            {subCopy}
          </p>


          <div className="mt-7 flex flex-col sm:flex-row items-start sm:items-center gap-3">
            <Link to={primaryHref} className="btn-primary text-[15px] px-6 h-12">
              {primaryLabel} <ArrowRight size={16} />
            </Link>
            <button onClick={handleSecondary} className="btn-ghost-light text-[15px] h-12">
              <Headphones size={15} /> {secondaryLabel}
            </button>
          </div>

          <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12.5px] text-white/55">
            <span className="inline-flex items-center gap-1.5"><ShieldCheck size={14} className="text-teal" /> GDPR compliant</span>
            <span className="text-white/20">·</span>
            <span className="inline-flex items-center gap-1.5"><Zap size={14} className="text-gold" /> Live in days</span>
            <span className="text-white/20">·</span>
            <span className="inline-flex items-center gap-1.5"><Layers size={14} className="text-blue-300" /> Plug into your stack</span>
          </div>
        </div>

        <HeroDashboard />
      </div>
    </section>
  );
}


/* ---------------- TRUST STRIP ---------------- */
export function TrustStrip() {
  const items = ["HR Teams", "Operations", "Talent Acquisition", "People Ops", "Research", "Customer Success"];
  return (
    <section className="py-10 border-y border-border bg-white">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <p className="text-center text-[12.5px] font-semibold uppercase tracking-[0.18em] text-muted-text">
          Built for teams who automate the busywork
        </p>
        <div className="mt-5 flex flex-wrap items-center justify-center gap-x-10 gap-y-3">
          {items.map((i) => (
            <span key={i} className="text-[15px] font-semibold text-navy/70">{i}</span>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- WHAT WE DO ---------------- */
export function WhatWeDo() {
  const pillars = [
    {
      icon: MessageCircle,
      title: "Automated conversations",
      body: "Voice and messaging agents that handle real, two-way conversations — outbound, inbound and follow-up.",
    },
    {
      icon: Zap,
      title: "Workflows on autopilot",
      body: "Multi-step processes — qualify, schedule, follow up, report — completed without manual handoffs.",
    },
    {
      icon: BarChart3,
      title: "Insights you can act on",
      body: "Structured data and clear dashboards from every interaction — anonymous or named, your call.",
    },
  ];
  return (
    <section id="what-we-do" className="py-24 md:py-32 bg-beige">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="max-w-[720px]">
          <span className="eyebrow">What we do</span>
          <h2 className="mt-4 text-[36px] md:text-[52px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
            One platform. Many <span className="serif-italic text-primary">intelligent assistants</span>.
          </h2>
          <p className="mt-5 text-[17px] text-body max-w-[620px]">
            VoxBulk gives businesses voice and messaging agents that work alongside your team — saving
            hours of coordination and surfacing the insights buried in every conversation.
          </p>
        </div>

        <div className="mt-14 grid md:grid-cols-3 gap-5">
          {pillars.map((p) => (
            <div key={p.title} className="card-soft p-7">
              <div className="w-11 h-11 rounded-xl bg-navy text-gold flex items-center justify-center">
                <p.icon size={20} />
              </div>
              <h3 className="mt-5 text-[20px] font-bold text-heading">{p.title}</h3>
              <p className="mt-2 text-[15px] text-body leading-[1.6]">{p.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}


/* ---------------- CAPABILITIES ---------------- */
export function Capabilities() {
  const caps = [
    {
      tag: "AI Interview Screening",
      icon: Sparkles,
      tone: "blue",
      headline: "Screen smarter. Hire faster.",
      body: "VoxBulk's AI interviews every candidate automatically — scoring skills, communication and fit before your team gets involved. No scheduling, no bias, no wasted time.",
    },
    {
      tag: "WhatsApp Survey",
      icon: MessageCircle,
      tone: "teal",
      headline: "Surveys they actually respond to.",
      body: "Send smart surveys straight to WhatsApp. 98% open rates, instant responses, zero chasing — all feeding directly into your dashboard.",
    },
    {
      tag: "AI Calling Survey",
      icon: PhoneCall,
      tone: "gold",
      headline: "Your AI makes the calls.",
      body: "Automated voice calls that hold real conversations, score every answer and surface your strongest candidates — before a human picks up the phone.",
    },
  ];
  return (
    <section id="capabilities" className="py-24 md:py-28 bg-white">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="max-w-[720px]">
          <span className="eyebrow">Capabilities</span>
          <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
            Three engines. <span className="serif-italic text-primary">One platform</span>.
          </h2>
        </div>

        <div className="mt-12 grid md:grid-cols-3 gap-5">
          {caps.map((c) => {
            const toneBg =
              c.tone === "blue" ? "bg-primary/10 text-primary border-primary/20" :
              c.tone === "teal" ? "bg-teal/15 text-teal border-teal/25" :
              "bg-gold/15 text-[#8a6a1a] border-gold/30";
            return (
              <div key={c.tag} className="relative card-soft p-7 overflow-hidden group">
                <div className={`absolute -top-14 -right-14 w-44 h-44 rounded-full blur-2xl opacity-60 ${
                  c.tone === "blue" ? "bg-primary/15" : c.tone === "teal" ? "bg-teal/15" : "bg-gold/20"
                }`} />
                <div className="relative">
                  <div className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-[10.5px] font-bold uppercase tracking-[0.14em] border ${toneBg}`}>
                    <c.icon size={12} /> {c.tag}
                  </div>
                  <h3 className="mt-5 text-[22px] font-bold text-heading leading-[1.2] tracking-[-0.01em]">
                    {c.headline}
                  </h3>
                  <p className="mt-3 text-[14.5px] text-body leading-[1.65]">
                    {c.body}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ---------------- LIVE SERVICES ---------------- */
const services = [
  {
    icon: FileText,
    tag: "Recruitment",
    title: "CV upload & ATS",
    body: "Upload candidate CVs in bulk. AI scans, scores and ranks each one against the job requirements automatically.",
  },
  {
    icon: Sparkles,
    tag: "Recruitment",
    title: "AI interview question generation",
    body: "Tailored interview questions generated for every role and every candidate's CV — no manual scripting.",
  },
  {
    icon: CalendarCheck,
    tag: "Recruitment",
    title: "Automated candidate scheduling",
    body: "The AI contacts shortlisted candidates and books their interviews — zero coordination from your team.",
  },
  {
    icon: PhoneCall,
    tag: "Recruitment",
    title: "AI-run voice interviews",
    body: "Candidates complete a fully automated, natural voice interview at their scheduled time.",
  },
  {
    icon: BarChart3,
    tag: "Recruitment",
    title: "Results dashboard",
    body: "Scores, answers and highlights for every candidate, in one clear breakdown for your hiring team.",
  },
  {
    icon: CheckCircle2,
    tag: "Recruitment",
    title: "One-click final round booking",
    body: "Accept candidates and instantly schedule human interviews via Cronofy or Calendly integration.",
  },
];


export function LiveServices() {
  return (
    <section id="services" className="py-24 md:py-32 bg-white scroll-mt-24">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="flex items-end justify-between flex-wrap gap-6">
          <div className="max-w-[680px]">
            <span className="eyebrow">Live services</span>
            <h2 className="mt-4 text-[36px] md:text-[52px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
              Recruitment, fully <span className="serif-italic text-primary">automated</span> — today.
            </h2>
            <p className="mt-5 text-[17px] text-body">
              Our flagship product. Six connected services that take a role from open req to booked
              final-round interview — without your team lifting a finger.
            </p>

          </div>
          <a href="#demo" className="hidden md:inline-flex items-center gap-1.5 text-[14px] font-semibold text-primary hover:gap-2.5 transition-all">
            See it in action <ArrowUpRight size={16} />
          </a>
        </div>

        <div className="mt-14 grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {services.map((s, i) => (
            <div key={s.title} className="card-soft p-7 group relative overflow-hidden">
              <div className="absolute top-5 right-5 text-[11px] font-semibold uppercase tracking-wider text-muted-text">
                {s.tag}
              </div>
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-50 to-beige-2 border border-border flex items-center justify-center text-primary">
                <s.icon size={22} />
              </div>
              <div className="mt-5 flex items-center gap-2">
                <span className="text-[12px] font-mono text-muted-text">0{i + 1}</span>
                <span className="h-px flex-1 bg-border" />
              </div>
              <h3 className="mt-3 text-[19px] font-bold text-heading leading-tight">{s.title}</h3>
              <p className="mt-2 text-[14.5px] text-body leading-[1.6]">{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- HOW IT WORKS ---------------- */
export function HowItWorks() {
  const steps = [
    {
      n: "01",
      title: "Connect",
      body: "Plug VoxBulk into your ATS, calendar (Cronofy / Calendly) and messaging stack. Setup typically takes a day.",
    },
    {
      n: "02",
      title: "Configure",
      body: "Tell the AI what roles you're hiring for or what survey you need. It builds the questions, scoring and outreach.",
    },
    {
      n: "03",
      title: "Launch",
      body: "Upload CVs or audience lists. VoxBulk runs the conversations, schedules and follow-ups end-to-end.",
    },
    {
      n: "04",
      title: "Decide",
      body: "Review ranked results, listen to interview highlights, and book final rounds with a single click.",
    },
  ];
  return (
    <section id="how-it-works" className="py-24 md:py-32 bg-beige">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="text-center max-w-[720px] mx-auto">
          <span className="eyebrow">How it works</span>
          <h2 className="mt-4 text-[36px] md:text-[52px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
            From open role to booked interview, in <span className="serif-italic text-primary">four steps</span>.
          </h2>
        </div>

        <div className="mt-16 grid md:grid-cols-4 gap-5 relative">
          <div className="hidden md:block absolute top-8 left-[12%] right-[12%] h-px bg-border" />
          {steps.map((s) => (
            <div key={s.n} className="relative bg-white border border-border rounded-2xl p-6">
              <div className="w-16 h-16 -mt-12 mx-auto rounded-full bg-navy text-gold flex items-center justify-center font-bold text-[18px] border-4 border-beige">
                {s.n}
              </div>
              <h3 className="mt-4 text-center text-[18px] font-bold text-heading">{s.title}</h3>
              <p className="mt-2 text-center text-[14.5px] text-body leading-[1.6]">{s.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- METRICS ---------------- */
export function Metrics() {
  const items = [
    { value: "92%", label: "less time spent on screening & scheduling" },
    { value: "4×", label: "more candidates interviewed per week" },
    { value: "<48h", label: "from CV upload to booked interview" },
    { value: "100%", label: "of interviews scored & summarised" },
  ];
  return (
    <section className="py-20 md:py-24 bg-navy text-white">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="grid md:grid-cols-4 gap-8 text-center">
          {items.map((i) => (
            <div key={i.label}>
              <div className="text-[44px] md:text-[56px] font-bold tracking-[-0.03em] text-gold">{i.value}</div>
              <div className="mt-2 text-[14px] text-white/65 max-w-[200px] mx-auto">{i.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- PRICING ---------------- */


type Plan = {
  name: string;
  priceGBP: number | null;     // null = custom, 0 = pay-as-you-go
  ratePerMinGBP: number | null;
  mins: number | null;
  wa: number | "Unlimited" | "Pay/use";
  cv: number | "Unlimited" | "Pay/use";
  badge?: string;
  enterprise?: boolean;
  payg?: boolean;
};

export const PLANS: Plan[] = [
  { name: "Pay as you go", priceGBP: 0,    ratePerMinGBP: 0.40, mins: null, wa: "Pay/use", cv: "Pay/use", badge: "No commitment", payg: true },
  { name: "Starter",    priceGBP: 59,   ratePerMinGBP: 0.35, mins: 400,  wa: 200,         cv: 100 },
  { name: "Pro",        priceGBP: 129,  ratePerMinGBP: 0.30, mins: 1200, wa: 600,         cv: 400,  badge: "Most popular" },
  { name: "Business",   priceGBP: 249,  ratePerMinGBP: 0.25, mins: 3000, wa: 2000,        cv: 1500 },
  { name: "Enterprise", priceGBP: null, ratePerMinGBP: null, mins: null, wa: "Unlimited", cv: "Unlimited", badge: "Custom pricing", enterprise: true },
];

export const WA_GBP = 1.5;
export const CV_GBP = 0.75;

export function fmt(n: number, dp = 2) { return n.toFixed(dp); }

export type Billing = "monthly" | "yearly";

export function BillingToggle({
  value,
  onChange,
  className = "",
}: {
  value: Billing;
  onChange: (b: Billing) => void;
  className?: string;
}) {
  return (
    <div className={`inline-flex items-center gap-1 rounded-full border border-border bg-white p-1 shadow-elegant ${className}`}>
      <button
        type="button"
        onClick={() => onChange("monthly")}
        className={`h-8 px-4 rounded-full text-[12.5px] font-semibold transition-all ${value === "monthly" ? "bg-navy text-white" : "text-muted-text hover:text-heading"}`}
      >
        Monthly
      </button>
      <button
        type="button"
        onClick={() => onChange("yearly")}
        className={`h-8 pl-4 pr-2 rounded-full text-[12.5px] font-semibold inline-flex items-center gap-2 transition-all ${value === "yearly" ? "bg-navy text-white" : "text-muted-text hover:text-heading"}`}
      >
        Yearly
        <span className={`text-[10px] font-bold uppercase tracking-[0.08em] px-1.5 py-0.5 rounded-full ${value === "yearly" ? "bg-gold text-navy" : "bg-gold/15 text-primary"}`}>2 months free</span>
      </button>
    </div>
  );
}

function plansFromApi(apiPlans: PublicPlan[] | undefined): Plan[] | null {
  if (!apiPlans?.length) return null;
  return apiPlans.map((p) => {
    const enterprise = Boolean(p.is_enterprise);
    const payg = Boolean(p.is_payg);
    const monthly = p.monthly_price_minor != null ? p.monthly_price_minor / 100 : null;
    const rate = p.per_min_minor != null ? p.per_min_minor / 100 : null;
    return {
      name: p.name,
      priceGBP: enterprise ? null : payg ? 0 : monthly,
      ratePerMinGBP: enterprise ? null : rate,
      mins: enterprise || payg ? null : p.minutes_included,
      wa: enterprise ? "Unlimited" : payg ? "Pay/use" : p.whatsapp_included,
      cv: enterprise ? "Unlimited" : payg ? "Pay/use" : p.cv_scans_included,
      badge: p.is_featured ? "Most popular" : payg ? "No commitment" : enterprise ? "Custom pricing" : undefined,
      enterprise,
      payg,
    };
  });
}

export function Pricing() {
  const { currency: cur } = useCurrency();
  const corePricing = usePublicPricing();
  const [topup, setTopup] = useState(50);
  const [dur, setDur] = useState(12);
  const [num, setNum] = useState(100);

  const s = SYM[cur];
  const fx = FX[cur];
  const displayPlans = plansFromApi(corePricing.data?.plans) || PLANS;
  // When API returns market-local prices, do not re-apply FX multipliers.
  const priceFx = corePricing.data?.plans?.length ? 1 : fx;


  return (
    <section id="pricing" className="py-24 md:py-32 bg-beige">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="text-center max-w-[680px] mx-auto">
          <span className="eyebrow">Pricing</span>
          <h2 className="mt-4 text-[36px] md:text-[52px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
            Per-minute rates. <span className="serif-italic text-primary">No surprises.</span>
          </h2>
          <p className="mt-5 text-[17px] text-body">
            Monthly subscription with minutes included. Top up any time. Cancel with 30 days' notice.
          </p>
        </div>

        {/* Currency is set in the footer (auto-detected by country, manual override) */}
        <div className="mt-6 text-center text-[12.5px] text-muted-text">
          Prices shown in <span className="font-semibold text-heading">{SYM[cur]} {cur.toUpperCase()}</span> · change country in footer
        </div>


        {/* Plans */}
        <div className="mt-10 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
          {displayPlans.map((p) => {
            const featured = p.badge === "Most popular";
            const waV = typeof p.wa === "number" ? p.wa.toLocaleString() : p.wa;
            const cvV = typeof p.cv === "number" ? p.cv.toLocaleString() : p.cv;
            return (
              <div
                key={p.name}
                className={`relative rounded-2xl p-5 flex flex-col ${
                  featured
                    ? "bg-navy text-white border-2 border-gold shadow-elevated"
                    : p.enterprise
                      ? "bg-white border border-navy/15 shadow-elegant"
                      : p.payg
                        ? "bg-gradient-to-br from-white to-beige-2/40 border border-primary/25 shadow-elegant"
                        : "bg-white border border-border shadow-elegant"
                }`}
              >
                {p.badge && (
                  <span className={`absolute -top-3 left-5 text-[10.5px] font-bold uppercase tracking-[0.14em] px-2.5 py-1 rounded-full ${
                    featured ? "bg-gold text-navy" : p.payg ? "bg-primary text-white" : "bg-navy text-white"
                  }`}>
                    {p.badge}
                  </span>
                )}
                <div className={`text-[14px] font-semibold ${featured ? "text-white/90" : "text-heading"}`}>
                  {p.name}
                </div>

                {p.enterprise ? (
                  <>
                    <div className="mt-3 text-[24px] font-bold tracking-[-0.02em] text-heading">Let's talk</div>
                    <div className="mt-1 text-[12px] text-muted-text">Volume rates · SLA · dedicated support</div>
                  </>
                ) : p.payg ? (
                  <>
                    <div className="mt-3 flex items-baseline gap-1">
                      <span className="text-[30px] font-bold tracking-[-0.02em] text-heading">{s}0</span>
                      <span className="text-[13px] text-muted-text">/mo</span>
                    </div>
                    <div className="mt-1 text-[12px] text-muted-text">
                      Per minute: <strong className="text-heading">{s}{fmt((p.ratePerMinGBP as number) * priceFx)}</strong>
                    </div>
                    <div className="mt-1 text-[11.5px] text-muted-text">
                      Only pay for what you use · no monthly fee
                    </div>
                  </>
                ) : (
                  <>
                    <div className="mt-3 flex items-baseline gap-1">
                      <span className={`text-[30px] font-bold tracking-[-0.02em] ${featured ? "text-gold" : "text-heading"}`}>
                        {s}{Math.round((p.priceGBP as number) * priceFx)}
                      </span>
                      <span className={`text-[13px] ${featured ? "text-white/60" : "text-muted-text"}`}>/mo</span>
                    </div>
                    <div className={`mt-1 text-[12px] ${featured ? "text-white/70" : "text-muted-text"}`}>
                      Per minute: <strong className={featured ? "text-white" : "text-heading"}>{s}{fmt((p.ratePerMinGBP as number) * priceFx)}</strong>
                    </div>
                    <div className={`mt-1 text-[11.5px] ${featured ? "text-white/55" : "text-muted-text"}`}>
                      Typical interview · {s}{fmt((p.ratePerMinGBP as number) * 10 * priceFx)} – {s}{fmt((p.ratePerMinGBP as number) * 15 * priceFx)}
                    </div>
                  </>
                )}

                <div className={`my-4 h-px ${featured ? "bg-white/15" : "bg-border"}`} />
                <ul className="space-y-2.5 text-[13px] flex-1">
                  <li className="flex justify-between gap-2">
                    <span className={`flex items-center gap-1.5 ${featured ? "text-white/70" : "text-body"}`}>
                      <Clock size={13} /> Mins included
                    </span>
                    <span className={`font-semibold ${featured ? "text-white" : "text-heading"}`}>
                      {p.mins === null ? (p.payg ? "0" : "Custom") : p.mins.toLocaleString()}
                    </span>
                  </li>
                  <li className="flex justify-between gap-2">
                    <span className={`flex items-center gap-1.5 ${featured ? "text-white/70" : "text-body"}`}>
                      <MessageCircle size={13} /> WA surveys
                    </span>
                    <span className={`font-semibold ${featured ? "text-white" : "text-heading"}`}>{waV}</span>
                  </li>
                  <li className="flex justify-between gap-2">
                    <span className={`flex items-center gap-1.5 ${featured ? "text-white/70" : "text-body"}`}>
                      <FileText size={13} /> CV scans
                    </span>
                    <span className={`font-semibold ${featured ? "text-white" : "text-heading"}`}>{cvV}</span>
                  </li>
                </ul>
                <a
                  href={p.enterprise ? "/contact" : "#demo"}
                  className={`mt-5 w-full inline-flex items-center justify-center gap-1.5 h-10 rounded-xl font-semibold text-[13.5px] transition-all ${
                    featured
                      ? "bg-gold text-navy hover:brightness-105"
                      : p.payg
                        ? "bg-primary text-white hover:bg-primary-dark"
                        : "bg-navy text-white hover:bg-navy/90"
                  }`}
                >
                  {p.enterprise ? "Contact us" : p.payg ? "Start free" : "Subscribe"} <ArrowRight size={13} />
                </a>
              </div>
            );
          })}
        </div>


        {/* Interview cost estimator */}
        <div className="mt-16">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-text mb-4">
            Interview call cost estimator
          </div>
          <div className="bg-white border border-border rounded-2xl p-6 md:p-8 shadow-elegant">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
                <Clock size={18} />
              </div>
              <div>
                <div className="text-[15px] font-semibold text-heading">How much will my interviews cost?</div>
                <div className="text-[12.5px] text-muted-text">Typical interview: 10–15 minutes. Adjust to match your calls.</div>
              </div>
            </div>

            <div className="space-y-4 mb-5">
              <SliderRow
                label="Call duration"
                value={dur} min={5} max={30} step={1}
                onChange={setDur}
                display={`${dur} min`}
              />
              <SliderRow
                label="Number of interviews"
                value={num} min={10} max={500} step={10}
                onChange={setNum}
                display={`${num}`}
              />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {displayPlans.map((p) => {
                if (p.enterprise || p.ratePerMinGBP === null) {
                  return (
                    <div key={p.name} className="bg-beige rounded-xl px-4 py-3 text-center">
                      <div className="text-[11px] text-muted-text mb-1">{p.name}</div>
                      <div className="text-[14px] font-semibold text-heading">Contact us</div>
                      <div className="text-[10.5px] text-muted-text mt-0.5">volume rates</div>
                    </div>
                  );
                }
                const total = p.ratePerMinGBP * dur * num * priceFx;
                const perCall = p.ratePerMinGBP * dur * priceFx;
                return (
                  <div key={p.name} className="bg-beige rounded-xl px-4 py-3 text-center">
                    <div className="text-[11px] text-muted-text mb-1">{p.name}</div>
                    <div className="text-[16px] font-bold text-heading tabular-nums">{s}{fmt(total)}</div>
                    <div className="text-[10.5px] text-muted-text mt-0.5">{s}{fmt(perCall)}/call</div>
                  </div>
                );
              })}
            </div>
            <div className="text-[11px] text-muted-text mt-3">Enterprise pricing is tailored — contact us for a quote.</div>
          </div>
        </div>

        {/* What each service costs */}
        <div className="mt-12">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-text mb-4">
            What each service costs
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <ServiceCard
              tone="blue"
              icon={<PhoneCall size={16} />}
              title="Interview & survey call"
              price={`${s}${fmt(0.25 * fx)} – ${s}${fmt(0.35 * fx)}/min`}
              unit="per minute · depends on your plan"
              desc={`Starter: ${s}${fmt(0.35 * fx)}/min · Pro: ${s}${fmt(0.30 * fx)}/min · Business: ${s}${fmt(0.25 * fx)}/min · Enterprise: custom. A typical 10–15 min interview costs ${s}${fmt(3.5 * fx)} – ${s}${fmt(5.25 * fx)} on Starter, down to ${s}${fmt(2.5 * fx)} – ${s}${fmt(3.75 * fx)} on Business.`}
            />
            <ServiceCard
              tone="teal"
              icon={<MessageCircle size={16} />}
              title="WhatsApp survey"
              price={`${s}${fmt(WA_GBP * fx)}`}
              unit="per user sent"
              desc="One flat charge every time a survey is sent to a candidate or employee via WhatsApp. No per-reply charge — just the send."
            />
            <ServiceCard
              tone="gold"
              icon={<FileText size={16} />}
              title="ATS CV scan"
              price={`${s}${fmt(CV_GBP * fx)}`}
              unit="per CV scanned"
              desc="Each CV uploaded and processed by the ATS costs a flat fee. Applies to every scan regardless of outcome."
            />
          </div>
        </div>

        {/* Pay-as-you-go top-up */}
        <div className="mt-12">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-text mb-4">
            Pay-as-you-go top-up
          </div>
          <div className="bg-white border border-border rounded-2xl p-6 md:p-8 shadow-elegant">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-success/10 text-success flex items-center justify-center">
                <Wallet size={18} />
              </div>
              <div>
                <div className="text-[15px] font-semibold text-heading">Credit top-up</div>
                <div className="text-[12.5px] text-muted-text">No expiry — use across calls, surveys and CV scans</div>
              </div>
            </div>
            <div className="flex items-center gap-4 mb-5">
              <input
                type="range"
                min={10}
                max={500}
                step={10}
                value={topup}
                onChange={(e) => setTopup(parseInt(e.target.value))}
                className="flex-1 accent-primary"
                aria-label="Top-up amount"
              />
              <div className="text-[15px] font-semibold text-heading min-w-[80px] text-right tabular-nums">
                {s}{fmt(topup * fx)}
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
              <TopupCell label="Minutes of calls" value={`~${Math.floor(topup / 0.35)} mins`} />
              <TopupCell label="WhatsApp surveys" value={`${Math.floor(topup / WA_GBP).toLocaleString()} surveys`} />
              <TopupCell label="CV scans" value={`${Math.floor(topup / CV_GBP).toLocaleString()} scans`} />
            </div>
            <a
              href="#demo"
              className="block w-full text-center h-11 leading-[44px] rounded-xl border border-border text-[14px] font-semibold text-heading hover:bg-beige transition-colors"
            >
              Top up now
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

export function SliderRow({
  label, value, min, max, step, onChange, display,
}: {
  label: string; value: number; min: number; max: number; step: number;
  onChange: (v: number) => void; display: string;
}) {
  return (
    <div className="flex items-center gap-4">
      <label className="text-[13px] text-muted-text min-w-[140px]">{label}</label>
      <input
        type="range"
        min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseInt(e.target.value))}
        className="flex-1 accent-primary"
        aria-label={label}
      />
      <span className="text-[14px] font-semibold text-heading min-w-[60px] text-right tabular-nums">{display}</span>
    </div>
  );
}

export function ServiceCard({
  tone, icon, title, price, unit, desc,
}: {
  tone: "blue" | "teal" | "gold";
  icon: React.ReactNode; title: string; price: string; unit: string; desc: string;
}) {
  const toneClasses =
    tone === "blue" ? "bg-primary/10 text-primary"
    : tone === "teal" ? "bg-teal/15 text-teal"
    : "bg-gold/15 text-[#8a6a1a]";
  return (
    <div className="bg-white border border-border rounded-2xl p-5 shadow-elegant">
      <div className="flex items-center gap-2.5 mb-3">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${toneClasses}`}>{icon}</div>
        <div className="text-[13.5px] font-semibold text-heading">{title}</div>
      </div>
      <div className="text-[22px] font-bold tracking-[-0.01em] text-heading">{price}</div>
      <div className="text-[12.5px] text-muted-text mt-0.5">{unit}</div>
      <div className="mt-3 pt-3 border-t border-border text-[12.5px] text-body leading-[1.6]">{desc}</div>
    </div>
  );
}

export function TopupCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-beige rounded-xl px-4 py-3">
      <div className="text-[11.5px] text-muted-text mb-1">{label}</div>
      <div className="text-[14px] font-semibold text-heading tabular-nums">{value}</div>
    </div>
  );
}


/* ---------------- TESTIMONIAL ---------------- */
export function Testimonial() {
  return (
    <section className="py-24 md:py-28 bg-beige">
      <div className="max-w-[920px] mx-auto px-5 md:px-10 text-center">
        <div className="flex justify-center gap-0.5 text-gold">
          {[...Array(5)].map((_, i) => <Star key={i} size={18} fill="currentColor" />)}
        </div>
        <p className="mt-6 text-[24px] md:text-[32px] font-medium text-heading leading-[1.35] tracking-[-0.015em]">
          "VoxBulk replaced two full days of weekly screening calls. Our hiring managers now spend their time
          on <span className="serif-italic text-primary">final-round interviews</span> — not chasing diaries."
        </p>
        <div className="mt-7 flex items-center justify-center gap-3">
          <div className="w-11 h-11 rounded-full bg-navy text-gold flex items-center justify-center font-semibold">SH</div>
          <div className="text-left">
            <div className="font-semibold text-heading text-[15px]">Sarah Holloway</div>
            <div className="text-[13px] text-muted-text">Head of People, mid-market SaaS</div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------------- FAQ ---------------- */
const faqItems: { q: string; a: ReactNode }[] = [
  { q: "What exactly does VoxBulk do?", a: "VoxBulk is an AI assistant platform that automates conversations, workflows and data collection. Our first live service is end-to-end recruitment automation — CV screening, scheduling, AI voice interviews, scoring and final-round booking. We also offer AI-run WhatsApp surveys." },
  { q: "How long does setup take?", a: "Most teams are live within a few days. We connect to your ATS, calendar (Cronofy or Calendly) and messaging tools, configure your roles, and run test conversations before going live." },
  { q: "How do AI voice interviews actually work?", a: "Candidates receive a scheduled link, dial in at their slot, and complete a natural conversation with our AI. The AI asks tailored questions, listens, follows up, and produces a scored, summarised report — all without human involvement." },
  { q: "Can I use VoxBulk just for surveys?", a: "Yes. WhatsApp surveys are available as a standalone service. The AI builds the questions, sends them, collects responses, and delivers a named or anonymous feedback report — whichever you need." },
  { q: "Which languages and accents are supported?", a: "AI voice interviews and calling surveys support English (GB, Irish, Australian, American, Scottish and Canadian dialects) and Arabic (Egyptian and Saudi dialects). WhatsApp surveys and voice-note transcription work across 50+ languages, with responses translated to English in your dashboard." },
  { q: "How is my data kept secure?", a: "VoxBulk is a multi-tenant platform with strict tenant isolation — each organisation's data is kept separate. Passwords use encrypted storage, integration secrets are encrypted at rest, and role-based access controls ensure only authorised team members see what they need. Production runs on secured infrastructure with controlled deployments, in UK and EU data centres." },
  {
    q: "Is VoxBulk GDPR compliant?",
    a: (
      <>
        Yes. All data stays within UK/EU data centres, calls and messages are encrypted in transit and at rest, and we sign a Data Processing Agreement with every customer.{" "}
        <Link to="/gdpr" className="text-primary font-semibold underline-offset-2 hover:underline">
          Read our GDPR overview
        </Link>
        .
      </>
    ),
  },
  { q: "What integrations are supported?", a: "Cronofy and Calendly for scheduling, WhatsApp for messaging surveys, plus API access to push results into your ATS or HRIS. Custom integrations are available on the Enterprise plan." },
  { q: "Can candidates opt out of speaking to AI?", a: "Yes. The AI announces itself at the start of every interaction, and candidates can request a human follow-up at any time." },
  { q: "Is there a contract or commitment?", a: "No long-term contract. Monthly subscription, cancel anytime with 30 days' notice. Enterprise customers can opt for annual terms with custom pricing." },
];

export function FAQ() {
  const [openIdx, setOpenIdx] = useState<number | null>(0);
  return (
    <section id="faq" className="py-24 md:py-32 bg-white">
      <div className="max-w-[860px] mx-auto px-5 md:px-10">
        <div className="text-center">
          <span className="eyebrow">FAQ</span>
          <h2 className="mt-4 text-[36px] md:text-[52px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
            Questions, <span className="serif-italic text-primary">answered</span>.
          </h2>
        </div>
        <div className="mt-12 divide-y divide-border border-y border-border">
          {faqItems.map((item, i) => {
            const open = openIdx === i;
            return (
              <div key={item.q}>
                <button
                  onClick={() => setOpenIdx(open ? null : i)}
                  className="w-full flex items-center justify-between text-left py-5 gap-6"
                  aria-expanded={open}
                >
                  <span className="text-[16px] md:text-[17px] font-semibold text-heading">{item.q}</span>
                  <span className={`w-8 h-8 rounded-full border border-border flex items-center justify-center transition-transform ${open ? "rotate-45 bg-navy text-gold border-navy" : "text-heading"}`}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                      <line x1="12" y1="5" x2="12" y2="19" />
                      <line x1="5" y1="12" x2="19" y2="12" />
                    </svg>
                  </span>
                </button>
                {open && (
                  <div className="pb-6 pr-12 text-[15.5px] text-body leading-[1.65] animate-fade-in">
                    {item.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>
        <div className="mt-10 text-center">
          <Link to="/contact" className="btn-outline text-[14px]">
            Still have questions? Talk to us <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ---------------- BOTTOM CTA ---------------- */
export function BottomCTA() {
  return (
    <section id="demo" className="py-24 md:py-28 bg-beige">
      <div className="max-w-[1080px] mx-auto px-5 md:px-10">
        <div className="relative overflow-hidden rounded-3xl bg-navy text-white p-10 md:p-16">
          <div className="absolute -top-20 -right-20 w-[360px] h-[360px] rounded-full blur-3xl opacity-30"
               style={{ background: "radial-gradient(circle, #D4A93A 0%, transparent 60%)" }} />
          <div className="absolute -bottom-24 -left-20 w-[360px] h-[360px] rounded-full blur-3xl opacity-25"
               style={{ background: "radial-gradient(circle, #1E6FD9 0%, transparent 60%)" }} />
          <div className="relative max-w-[680px]">
            <span className="eyebrow eyebrow-light">Ready to automate</span>
            <h2 className="mt-4 text-[36px] md:text-[52px] font-bold tracking-[-0.03em] leading-[1.05] text-white">
              See VoxBulk run a full hiring round — <span className="serif-italic text-gold">in 20 minutes</span>.
            </h2>
            <p className="mt-5 text-[17px] text-white/70 max-w-[560px]">
              Book a personalised demo. We'll plug in a sample role, run live AI interviews, and walk you
              through the dashboard with your team.
            </p>
            <div className="mt-8 flex flex-col sm:flex-row gap-3">
              <Link to="/contact" className="btn-primary text-[15px] h-12 px-7">
                Request a demo <ArrowRight size={16} />
              </Link>
              <a href="#services" className="btn-ghost-light text-[15px] h-12">
                Explore services
              </a>
            </div>
            <div className="mt-7 flex flex-wrap gap-x-6 gap-y-2 text-[12.5px] text-white/55">
              <span className="inline-flex items-center gap-1.5"><Users size={13} /> Built for HR & ops teams</span>
              <span className="inline-flex items-center gap-1.5"><ShieldCheck size={13} /> GDPR compliant</span>
              <span className="inline-flex items-center gap-1.5"><Zap size={13} /> Live within days</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------------- CV INTAKE (Two ways) ---------------- */
export function CVIntake() {
  return (
    <section id="cv-intake" className="py-24 md:py-32 bg-white">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="max-w-[760px]">
          <span className="eyebrow">CV intake</span>
          <h2 className="mt-4 text-[36px] md:text-[52px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
            Two ways to receive CVs. <span className="serif-italic text-primary">Zero admin</span> either way.
          </h2>
          <p className="mt-5 text-[17px] text-body max-w-[640px]">
            However candidates apply, VoxBulk handles it automatically.
          </p>

          {/* ATS score chips */}
          <div className="mt-6 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-navy text-white text-[12.5px] font-semibold">
              <Gauge size={14} className="text-gold" /> ATS score · live
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-success/10 text-success text-[12.5px] font-semibold border border-success/20">
              92 · Strong fit
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gold/15 text-[#8a6a1a] text-[12.5px] font-semibold border border-gold/30">
              78 · Worth a call
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-muted text-muted-text text-[12.5px] font-semibold border border-border">
              52 · Lower match
            </span>
          </div>
        </div>

        <div className="mt-14 grid md:grid-cols-2 gap-5">
          {/* Option 1 — Drag & drop */}
          <div className="relative card-soft p-8 overflow-hidden">
            <div className="absolute -top-12 -right-12 w-48 h-48 rounded-full bg-primary/10 blur-2xl" />
            <div className="relative">
              <div className="inline-flex items-center gap-2 text-[11.5px] font-bold uppercase tracking-[0.14em] text-primary">
                <span className="w-6 h-6 rounded-full bg-primary text-white inline-flex items-center justify-center text-[11px]">1</span>
                Option 1
              </div>
              <h3 className="mt-4 text-[24px] font-bold text-heading">Drag &amp; drop</h3>
              <p className="mt-3 text-[15px] text-body leading-[1.65]">
                Upload CVs directly into VoxBulk in bulk. AI scans and scores them instantly.
              </p>

              <div className="mt-6 rounded-2xl border-2 border-dashed border-primary/30 bg-primary/[0.04] p-6 text-center">
                <div className="w-12 h-12 mx-auto rounded-xl bg-primary/10 text-primary flex items-center justify-center">
                  <Upload size={22} />
                </div>
                <div className="mt-3 text-[14px] font-semibold text-heading">Drop CVs here</div>
                <div className="text-[12.5px] text-muted-text mt-0.5">PDF, DOCX · up to 500 files at once</div>
                <div className="mt-4 flex flex-wrap items-center justify-center gap-1.5 text-[11.5px] text-muted-text">
                  <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-white border border-border"><FileText size={11} /> amelia_cv.pdf</span>
                  <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-white border border-border"><FileText size={11} /> j_reid.pdf</span>
                  <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-white border border-border"><FileText size={11} /> +248 more</span>
                </div>
              </div>
            </div>
          </div>

          {/* Option 2 — Email intake */}
          <div className="relative card-soft p-8 overflow-hidden">
            <div className="absolute -top-12 -right-12 w-48 h-48 rounded-full bg-gold/15 blur-2xl" />
            <div className="relative">
              <div className="inline-flex items-center gap-2 text-[11.5px] font-bold uppercase tracking-[0.14em] text-[#8a6a1a]">
                <span className="w-6 h-6 rounded-full bg-gold text-navy inline-flex items-center justify-center text-[11px] font-bold">2</span>
                Option 2
              </div>
              <h3 className="mt-4 text-[24px] font-bold text-heading">Email intake</h3>
              <p className="mt-3 text-[15px] text-body leading-[1.65]">
                Generate a job reference code and share it with candidates. They email their CV to your VoxBulk careers inbox with the reference in the subject line — VoxBulk automatically assigns it to the right job and starts screening. No portals, no manual sorting.
              </p>

              <div className="mt-6 rounded-2xl bg-navy text-white p-5 font-mono text-[12.5px]">
                <div className="flex items-center gap-2 text-white/50 text-[11px] uppercase tracking-wider mb-3">
                  <Inbox size={13} />
                  <span>your_Job_number@voxbulk.com</span>
                </div>
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <span className="text-white/40 w-12">To:</span>
                    <span>VB-ENG-204@voxbulk.com</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="text-white/40 w-12">Subject:</span>
                    <span>[<span className="text-gold">VB-ENG-204</span>] Senior Engineer application</span>
                  </div>
                  <div className="flex gap-2">
                    <span className="text-white/40 w-12">Attach:</span>
                    <span className="inline-flex items-center gap-1.5 text-teal"><FileText size={12} /> cv.pdf</span>
                  </div>
                </div>
                <div className="mt-4 pt-3 border-t border-white/10 flex items-center gap-2 text-teal text-[12px]">
                  <CheckCircle2 size={13} /> Auto-routed to <strong className="text-white">Senior Engineer · VB-ENG-204</strong>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------------- TALK TO US (white, continuous motion) ---------------- */
function SignalField() {
  return (
    <>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-[linear-gradient(180deg,rgba(245,240,232,0.95),rgba(245,240,232,0))]" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-[linear-gradient(0deg,rgba(245,240,232,0.95),rgba(245,240,232,0))]" />
      <div className="pointer-events-none absolute -left-10 top-1/2 hidden h-[420px] w-[420px] -translate-y-1/2 rounded-full bg-primary/[0.08] blur-3xl md:block" />
      <div className="pointer-events-none absolute -right-16 top-1/2 hidden h-[360px] w-[360px] -translate-y-1/2 rounded-full bg-teal/[0.10] blur-3xl md:block" />
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-70">
        <div className="signal-orbit relative h-[460px] w-[460px] rounded-full border border-primary/10">
          <div className="absolute inset-14 rounded-full border border-gold/10" />
          <div className="absolute inset-28 rounded-full border border-teal/10" />
          <span className="absolute left-1/2 top-0 h-2 w-2 -translate-x-1/2 rounded-full bg-primary/35" />
          <span className="absolute bottom-10 right-14 h-2 w-2 rounded-full bg-teal/35" />
          <span className="absolute left-16 top-24 h-1.5 w-1.5 rounded-full bg-gold/40" />
        </div>
      </div>
    </>
  );
}

export function TalkToUs() {
  const talk = useTalkModal();
  return (
    <section id="talk" className="relative overflow-hidden bg-white text-heading py-20 md:py-28 border-y border-border">
      <div className="absolute inset-0 bg-grid opacity-[0.05]" />
      <SignalField />

      <div className="relative max-w-[1080px] mx-auto px-5 md:px-10 grid md:grid-cols-2 gap-12 items-center">
        <div>
          <span className="eyebrow">Talk to us</span>
          <h2 className="mt-4 text-[36px] md:text-[52px] font-bold tracking-[-0.03em] leading-[1.05] text-heading">
            Prefer to <span className="serif-italic text-primary">hear it live</span>?
          </h2>
          <p className="mt-5 text-[17px] text-body max-w-[520px]">
            Hit call and a VoxBulk AI agent will pick up instantly — ask anything about pricing, integrations, or how it would work for your team.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <button
              onClick={talk.open}
              className="inline-flex items-center justify-center gap-2 h-12 px-7 rounded-xl font-semibold text-[15px] bg-navy text-white hover:bg-navy/90 transition-all shadow-[0_10px_30px_-12px_rgba(10,22,40,0.45)]"
            >
              <PhoneCall size={16} /> Talk to us
            </button>
            <span className="inline-flex items-center gap-1.5 text-[12.5px] text-muted-text">
              <span className="w-1.5 h-1.5 rounded-full bg-teal pulse-dot" /> Avg pick-up under 3 seconds
            </span>
          </div>
        </div>

        <div className="relative">
          <div className="relative mx-auto max-w-[420px] rounded-3xl bg-white border border-border p-7 shadow-[0_30px_60px_-30px_rgba(10,22,40,0.25)]">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-gradient-to-br from-primary to-teal flex items-center justify-center">
                <Headphones size={20} className="text-white" />
              </div>
              <div className="flex-1">
                <div className="text-heading font-semibold text-[15px]">VoxBulk AI agent</div>
                <div className="inline-flex items-center gap-1.5 text-[12px] text-teal">
                  <span className="w-1.5 h-1.5 rounded-full bg-teal pulse-dot" /> Online · responds instantly
                </div>
              </div>
            </div>

            <div className="mt-6 flex items-end justify-center gap-[5px] h-20">
              {Array.from({ length: 28 }).map((_, i) => (
                <span
                  key={i}
                  className="eq-bar w-[4px] rounded-full bg-primary/80"
                  style={{ height: "100%", animationDelay: `${(i % 7) * 0.12}s`, animationDuration: `${0.9 + (i % 4) * 0.15}s` }}
                />
              ))}
            </div>

            <div className="mt-6 flex items-center justify-center">
              <button
                onClick={talk.open}
                className="w-16 h-16 rounded-full bg-navy text-white inline-flex items-center justify-center shadow-[0_15px_30px_-10px_rgba(10,22,40,0.45)] hover:scale-105 transition-all"
                aria-label="Talk to us"
              >
                <PhoneCall size={24} />
              </button>
            </div>
            <div className="mt-3 text-center text-[12px] text-muted-text">Tap to start the conversation</div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------------- PAGE ---------------- */
/* ---------------- HOMEPAGE SECTIONS ---------------- */
export function PlatformIntro() {
  return (
    <section id="what-we-do" className="py-24 md:py-28 bg-white scroll-mt-24">

      <div className="max-w-[1080px] mx-auto px-5 md:px-10 text-center">
        <span className="eyebrow">One platform. Three products.</span>
        <h2 className="mt-4 text-[36px] md:text-[52px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
          Intelligent screening. <span className="serif-italic text-primary">Instant results.</span>
        </h2>
        <p className="mt-5 text-[17px] text-body max-w-[720px] mx-auto">
          VoxBulk automates the conversations your team doesn't have time for — from hiring to customer feedback.
        </p>
      </div>
    </section>
  );
}

export function ProductCards() {
  const products = [
    {
      icon: Sparkles,
      tone: "blue",
      title: "Recruitment Automation",
      body: "Post one job — wake up to a shortlist. CV intake, ATS scoring, WhatsApp booking and 10–12 minute AI voice interviews with ranked recommendations.",
      href: "/recruitment",
    },
    {
      icon: MessageCircle,
      tone: "teal",
      title: "WhatsApp Surveys",
      body: "WhatsApp and AI Calling collect far more answers than email. Customers respond in their language; your dashboard translates, charts and recommends what to fix.",
      href: "/surveys",
    },
    {
      icon: Inbox,
      tone: "gold",
      title: "Customer Feedback",
      body: "One QR. Scan → WhatsApp → ~30s. Voice notes in 50+ languages, English dashboard, multi-location compare and red-flag recovery.",
      href: "/feedback",
    },
  ];
  return (
    <section id="products" className="py-20 md:py-24 bg-beige">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="grid md:grid-cols-3 gap-5">
          {products.map((p) => {
            const toneBg =
              p.tone === "blue" ? "bg-primary/10 text-primary border-primary/20" :
              p.tone === "teal" ? "bg-teal/15 text-teal border-teal/25" :
              "bg-gold/15 text-[#8a6a1a] border-gold/30";
            const halo =
              p.tone === "blue" ? "bg-primary/15" :
              p.tone === "teal" ? "bg-teal/15" : "bg-gold/20";
            return (
              <div key={p.title} className="relative card-soft p-7 overflow-hidden flex flex-col">
                <div className={`absolute -top-14 -right-14 w-44 h-44 rounded-full blur-2xl opacity-60 ${halo}`} />
                <div className="relative flex-1">
                  <div className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-[10.5px] font-bold uppercase tracking-[0.14em] border ${toneBg}`}>
                    <p.icon size={12} /> Live
                  </div>
                  <h3 className="mt-5 text-[22px] font-bold text-heading leading-[1.2] tracking-[-0.01em]">{p.title}</h3>
                  <p className="mt-3 text-[14.5px] text-body leading-[1.65]">{p.body}</p>
                </div>
                <Link to={p.href} className="relative mt-6 inline-flex items-center gap-1.5 text-[14px] font-semibold text-primary hover:gap-2.5 transition-all">
                  Explore <ArrowRight size={14} />
                </Link>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export function StatsRow({
  items = [
    { value: "92%", label: "less time spent on screening" },
    { value: "98%", label: "WhatsApp open rate" },
    { value: "4×", label: "more candidates interviewed per week" },
    { value: "<24h", label: "from setup to first result" },
  ],
}: { items?: { value: string; label: string }[] } = {}) {
  return (
    <section className="py-20 md:py-24 bg-navy text-white">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="grid md:grid-cols-4 grid-cols-2 gap-8 text-center">
          {items.map((i) => (
            <div key={i.label}>
              <div className="text-[40px] md:text-[56px] font-bold tracking-[-0.03em] text-gold">{i.value}</div>
              <div className="mt-2 text-[13.5px] md:text-[14px] text-white/65 max-w-[220px] mx-auto">{i.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function PricingTeaser() {
  return (
    <section className="py-24 md:py-28 bg-white">
      <div className="max-w-[860px] mx-auto px-5 md:px-10 text-center">
        <span className="eyebrow">Simple pricing</span>
        <h2 className="mt-4 text-[36px] md:text-[52px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
          Pay for what you use. <span className="serif-italic text-primary">Cancel anytime.</span>
        </h2>
        <p className="mt-5 text-[17px] text-body">
          Each product has its own plan — pick one or combine them.
        </p>
        <div className="mt-8">
          <Link to="/pricing" className="btn-primary text-[15px] h-12 px-7">
            See all pricing <ArrowRight size={16} />
          </Link>
        </div>
      </div>
    </section>
  );
}

export default function VOXBULKHome() {
  return (
    <div className="bg-background text-body antialiased">
      <SiteHeader />
      <main>
        <Hero />
        <TalkToUs />
        <PlatformIntro />
        <ProductCards />
        <Capabilities />
        <HowItWorks />
        <StatsRow />
        <Testimonial />
        <PricingTeaser />
        <FAQ />
        <BottomCTA />
      </main>
      <SiteFooter />
    </div>
  );
}




/* ---------------- WHO IT'S FOR ---------------- */
export function WhoItsFor() {
  const items = [
    { icon: Users, title: "Recruitment agencies", body: "Place more candidates without growing your consultant headcount. Run dozens of roles in parallel." },
    { icon: Building2, title: "In-house TA teams", body: "Replace manual screening calls and back-and-forth scheduling. Keep your ATS, drop the busywork." },
    { icon: Gauge, title: "Volume hirers", body: "Hospitality, retail, care, BPO — interview hundreds of candidates a week without lifting a finger." },
  ];
  return (
    <section className="py-20 md:py-24 bg-white">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="max-w-[720px]">
          <span className="eyebrow">Who it's for</span>
          <h2 className="mt-4 text-[32px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
            Built for teams handling <span className="serif-italic text-primary">20+ roles a month</span>.
          </h2>
          <p className="mt-4 text-[16px] text-body">
            VoxBulk plugs into your existing ATS and calendar. It doesn't replace your team — it removes the manual screening, chasing and scheduling that eats their week.
          </p>
        </div>
        <div className="mt-10 grid md:grid-cols-3 gap-5">
          {items.map((i) => (
            <div key={i.title} className="card-soft p-7">
              <div className="w-11 h-11 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
                <i.icon size={20} />
              </div>
              <h3 className="mt-5 text-[18px] font-bold text-heading">{i.title}</h3>
              <p className="mt-2 text-[14.5px] text-body leading-[1.6]">{i.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- BEFORE / AFTER ---------------- */
export function BeforeAfter() {
  const before = [
    "Recruiters spend 15+ hours/week screening CVs by hand",
    "Phone tag with candidates to book a 20-minute call",
    "Inconsistent notes — every consultant scores differently",
    "Top candidates ghost after 48h of silence",
    "Hiring managers wait days for a shortlist",
  ];
  const after = [
    "AI scores and ranks every CV the moment it lands",
    "Candidates self-book interviews via WhatsApp in seconds",
    "Every interview transcribed, scored and summarised the same way",
    "Auto follow-ups keep candidates warm 24/7",
    "Shortlists ready inside 48 hours — every time",
  ];
  return (
    <section className="py-24 md:py-28 bg-beige">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="text-center max-w-[720px] mx-auto">
          <span className="eyebrow">The shift</span>
          <h2 className="mt-4 text-[34px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
            Your week today vs. your week with <span className="serif-italic text-primary">VoxBulk</span>.
          </h2>
        </div>
        <div className="mt-12 grid md:grid-cols-2 gap-5">
          <div className="rounded-2xl bg-white border border-border p-7">
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-red-50 text-red-700 border border-red-100 text-[11px] font-bold uppercase tracking-[0.14em]">
              <X size={12} /> Without VoxBulk
            </div>
            <ul className="mt-5 space-y-3">
              {before.map((b) => (
                <li key={b} className="flex gap-3 text-[14.5px] text-body leading-[1.55]">
                  <X size={16} className="mt-0.5 text-red-500 shrink-0" />
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-2xl bg-navy text-white p-7 border border-gold/30 shadow-elevated relative overflow-hidden">
            <div className="absolute -top-16 -right-16 w-44 h-44 rounded-full bg-gold/15 blur-2xl" />
            <div className="relative">
              <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-gold/15 text-gold border border-gold/30 text-[11px] font-bold uppercase tracking-[0.14em]">
                <Check size={12} /> With VoxBulk
              </div>
              <ul className="mt-5 space-y-3">
                {after.map((a) => (
                  <li key={a} className="flex gap-3 text-[14.5px] text-white/85 leading-[1.55]">
                    <Check size={16} className="mt-0.5 text-teal shrink-0" />
                    <span>{a}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------------- INTEGRATIONS ---------------- */
export function Integrations() {
  const ats = ["Bullhorn", "Vincere", "JobAdder", "Workable", "Greenhouse", "Lever", "Teamtailor", "Recruitee"];
  const cal = ["Cronofy", "Calendly", "Google Calendar", "Outlook"];
  return (
    <section className="py-20 md:py-24 bg-white border-y border-border">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="text-center max-w-[720px] mx-auto">
          <span className="eyebrow inline-flex items-center gap-2">
            <Plug size={13} /> Integrations
          </span>
          <h2 className="mt-4 text-[28px] md:text-[36px] font-bold tracking-[-0.03em] text-heading leading-[1.15]">
            Plugs into the stack you already use.
          </h2>
          <p className="mt-3 text-[15px] text-body">
            Two-way sync with your ATS. Real-time booking through your calendar. No rip-and-replace.
          </p>
        </div>
        <div className="mt-10 grid md:grid-cols-2 gap-5">
          <div className="rounded-2xl bg-beige border border-border p-6">
            <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted-text">ATS</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {ats.map((a) => (
                <span key={a} className="px-3 py-1.5 rounded-full bg-white border border-border text-[13px] font-semibold text-heading">
                  {a}
                </span>
              ))}
            </div>
          </div>
          <div className="rounded-2xl bg-beige border border-border p-6">
            <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted-text">Calendar & comms</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {cal.map((c) => (
                <span key={c} className="px-3 py-1.5 rounded-full bg-white border border-border text-[13px] font-semibold text-heading">
                  {c}
                </span>
              ))}
              <span className="px-3 py-1.5 rounded-full bg-white border border-border text-[13px] font-semibold text-heading inline-flex items-center gap-1.5">
                <MessageCircle size={13} /> WhatsApp Business
              </span>
            </div>
          </div>
        </div>
        <p className="mt-6 text-center text-[12.5px] text-muted-text">
          Don't see yours? We connect to anything with a REST API or webhook.
        </p>
      </div>
    </section>
  );
}

/* ---------------- PROOF ---------------- */
export function Proof() {
  return (
    <section className="py-24 md:py-28 bg-beige">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10 grid lg:grid-cols-[1.1fr_0.9fr] gap-8 items-stretch">
        <div className="card-soft p-9 relative overflow-hidden">
          <Quote size={48} className="absolute top-6 right-6 text-primary/15" />
          <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-muted-text">Recruitment agency · UK</div>
          <p className="mt-5 text-[20px] md:text-[22px] font-medium text-heading leading-[1.45] tracking-[-0.01em]">
            "We went from interviewing 30 candidates a week to <span className="text-primary">over 200</span> — with the same five consultants. VoxBulk does the screening calls overnight."
          </p>
          <div className="mt-6 flex items-center gap-3">
            <div className="w-11 h-11 rounded-full bg-gradient-to-br from-primary to-teal flex items-center justify-center text-white font-bold text-[15px]">SM</div>
            <div>
              <div className="text-[14.5px] font-bold text-heading">Sarah M.</div>
              <div className="text-[12.5px] text-muted-text">Head of Talent · 40-person agency</div>
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {[
            { v: "12,400+", l: "candidates interviewed by AI" },
            { v: "6.4x", l: "more roles handled per consultant" },
            { v: "38h", l: "saved per recruiter, per week" },
            { v: "94%", l: "candidate satisfaction with the AI call" },
          ].map((m) => (
            <div key={m.l} className="card-soft p-5 flex flex-col justify-center">
              <div className="text-[32px] md:text-[36px] font-bold tracking-[-0.03em] text-primary">{m.v}</div>
              <div className="mt-1 text-[13px] text-body leading-[1.4]">{m.l}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- RISK REVERSAL ---------------- */
export function RiskReversal() {
  const talk = useTalkModal();
  const items = [
    { icon: FlaskConical, t: "Pilot on one role", b: "Run a single live vacancy through VoxBulk. See the shortlist before you commit." },
    { icon: ShieldCheck, t: "Your data stays yours", b: "GDPR compliant. UK & EU data residency. Export or delete anything, anytime." },
    { icon: Calendar, t: "Cancel anytime", b: "Month-to-month. 30 days' notice. No setup fees, no lock-in." },
  ];
  return (
    <section className="py-24 md:py-28 bg-white">
      <div className="max-w-[1180px] mx-auto px-5 md:px-10">
        <div className="text-center max-w-[720px] mx-auto">
          <span className="eyebrow">Low-risk start</span>
          <h2 className="mt-4 text-[32px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
            Try it on one role. <span className="serif-italic text-primary">Decide from there.</span>
          </h2>
        </div>
        <div className="mt-10 grid md:grid-cols-3 gap-5">
          {items.map((i) => (
            <div key={i.t} className="card-soft p-7">
              <div className="w-11 h-11 rounded-xl bg-gold/15 text-[#8a6a1a] flex items-center justify-center">
                <i.icon size={20} />
              </div>
              <h3 className="mt-5 text-[18px] font-bold text-heading">{i.t}</h3>
              <p className="mt-2 text-[14.5px] text-body leading-[1.6]">{i.b}</p>
            </div>
          ))}
        </div>
        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link to="/contact" className="btn-primary text-[15px] px-6 h-12">
            Start a pilot on one role <ArrowRight size={16} />
          </Link>
          <button onClick={talk.open} className="inline-flex items-center gap-2 h-12 px-5 rounded-xl border border-border bg-white font-semibold text-[14.5px] text-heading hover:bg-beige transition-all">
            <Calendar size={15} /> Book a 20-min walkthrough
          </button>
        </div>
      </div>
    </section>
  );
}
