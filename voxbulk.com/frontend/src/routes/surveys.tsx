import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, Users, Briefcase, Layers, BarChart3, Mic, Languages, FileText, Sparkles, Stethoscope, UserSearch, UtensilsCrossed, Hotel, Home, ShoppingBag, Car, GraduationCap, Scale, Dumbbell, HeartHandshake, Phone, MessageCircle, TrendingUp, Clock, CheckCircle2, Wand2, Wrench, Settings2 } from "lucide-react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { Hero, StatsRow, BottomCTA } from "@/components/VOXBULKHome";

export const Route = createFileRoute("/surveys")({
  head: () => ({
    meta: [
      { title: "WhatsApp Surveys — VoxBulk" },
      { name: "description", content: "Smart AI-built surveys straight to WhatsApp. 98% open rates, instant results, zero chasing." },
      { property: "og:title", content: "WhatsApp Surveys — VoxBulk" },
      { property: "og:description", content: "Surveys your audience actually responds to." },
    ],
    links: [{ rel: "canonical", href: "https://voxbulk.com/surveys" }],
  }),
  component: SurveysPage,
});

const steps = [
  { n: "01", title: "Build your survey", body: "VoxBulk generates smart questions based on your goal. Customise or use as is." },
  { n: "02", title: "Send to your list", body: "Upload your contacts. VoxBulk sends each person a personalised WhatsApp message and guides them through in a natural conversation." },
  { n: "03", title: "Review your results", body: "Every response scored, summarised and added to your dashboard in real time." },
];

const audiences = [
  { icon: Users, title: "HR Teams", body: "Employee feedback and pulse surveys" },
  { icon: Briefcase, title: "Talent Acquisition", body: "Candidate screening and follow-up" },
  { icon: Layers, title: "Operations", body: "Process and workflow feedback" },
  { icon: BarChart3, title: "Research", body: "Structured data collection at scale" },
];

const templates: { icon: any; title: string; questions: string[] }[] = [
  { icon: Stethoscope, title: "Healthcare & dental", questions: ["Post-visit satisfaction","Wait time rating","Staff attitude","Cleanliness","Treatment outcome","Pricing fairness","Would recommend","Return intent","Booking experience","Communication clarity","Appointment availability","Pain management satisfaction","Explanation of treatment","Waiting area comfort","Reception staff rating","Follow-up care quality","Hygienist satisfaction","Parking & accessibility","Online/app experience","Overall care rating"] },
  { icon: UserSearch, title: "Recruitment & staffing", questions: ["Candidate experience","Interview process rating","Consultant rating","Placement satisfaction","Communication quality","Employer satisfaction","Speed of placement","Professionalism","Would recommend","Job match quality","CV support quality","Onboarding support","Candidate quality (employer)","Time-to-hire satisfaction","Post-placement check-in","Salary negotiation support","Interview preparation quality","Transparency of process","Long-term fit rating","Overall service rating"] },
  { icon: UtensilsCrossed, title: "Hospitality & food", questions: ["Food quality","Service speed","Staff friendliness","Cleanliness","Value for money","Ambience","Booking experience","Return intent","Would recommend","Portion size","Dietary/allergy handling","Drink quality","Menu variety","Wait for table","Bill accuracy","Noise level","Outdoor seating experience","Takeaway packaging","Delivery experience","Overall dining rating"] },
  { icon: Hotel, title: "Hotel & accommodation", questions: ["Check-in experience","Room cleanliness","Breakfast quality","Staff friendliness","Value for money","Noise & comfort","Facilities rating","Return intent","Would recommend","Check-out experience","Room temperature control","Wi-Fi quality","Bed comfort","Bathroom cleanliness","Parking experience","Concierge/help desk rating","Pool/gym facilities","In-room dining","Evening turndown service","Overall stay rating"] },
  { icon: Home, title: "Property & lettings", questions: ["Viewing experience","Move-in condition","Maintenance response","Communication","Value for money","Property management","Would recommend","Renewal intent","Agent professionalism","Issue resolution","Safety & security perception","Deposit handling","Inventory accuracy","Move-out process","Tenant communication quality","Emergency response speed","Online portal experience","Referencing process","Rent review fairness","Overall tenancy rating"] },
  { icon: ShoppingBag, title: "Retail & e-commerce", questions: ["Product quality","Delivery experience","Packaging quality","Returns process","Value for money","Staff helpfulness","Stock availability","Would recommend","Repeat purchase intent","Website experience","Order accuracy","Delivery speed","Checkout experience","Product description accuracy","Customer service rating","Loyalty programme value","In-store experience","Click & collect experience","Refund speed","Overall shopping rating"] },
  { icon: Car, title: "Automotive", questions: ["Work quality","Explanation of work","Punctuality","Pricing transparency","Vehicle cleanliness","Booking experience","Staff attitude","Value for money","Would recommend","Turnaround time","MOT experience","Courtesy car availability","Parts quality","Diagnostic accuracy","Invoice clarity","Warranty handling","Collection/drop-off experience","Upsell pressure rating","Post-service follow-up","Overall garage rating"] },
  { icon: GraduationCap, title: "Education & training", questions: ["Course quality","Trainer rating","Learning outcome","Facilities","Value for money","Course material quality","Would recommend","Booking experience","Support quality","Return intent","Post-course resources","Group size satisfaction","Pace of delivery","Online learning experience","Assessment fairness","Certificate/accreditation value","Pre-course communication","Trainer knowledge depth","Practical vs theory balance","Overall course rating"] },
  { icon: Scale, title: "Legal & accountancy", questions: ["Communication clarity","Matter handling","Value for money","Case/matter outcome","Staff professionalism","Response time","Would recommend","Onboarding experience","Billing transparency","Referral likelihood","Expectation vs outcome","Document handling","Jargon avoidance","Deadline adherence","Partner/senior access","Digital tools experience","Tax return satisfaction","Court/hearing preparation","Confidentiality confidence","Overall service rating"] },
  { icon: Dumbbell, title: "Fitness & wellness", questions: ["Session quality","Trainer attitude","Facilities rating","Cleanliness","Value for money","Class variety","Booking experience","Staff friendliness","Would recommend","Membership value","Equipment availability","Changing room quality","App/online portal rating","Personal training value","Class size satisfaction","Parking & access","Nutrition/supplement advice","Injury support handling","Peak time crowding","Overall experience rating"] },
  { icon: Briefcase, title: "Financial services", questions: ["Advice clarity","Product suitability","Adviser professionalism","Response time","Value for money","Onboarding experience","Would recommend","Communication quality","Trust & confidence","Compliance & transparency","Digital platform rating","Application process","Mortgage/loan handling","Claims experience","Renewal process","Documentation clarity","Fee transparency","Switch/transfer experience","Complaint handling","Overall service rating"] },
  { icon: TrendingUp, title: "Logistics & delivery", questions: ["Delivery speed","Packaging condition","Driver attitude","Delivery accuracy","Communication/tracking","Would recommend","Collection experience","Returns process","Value for money","Repeat use intent","Safe place delivery rating","Missed delivery handling","Customer service quality","App/portal experience","Proof of delivery satisfaction","Fragile item handling","Same-day service rating","International delivery rating","Business account experience","Overall delivery rating"] },
  { icon: Sparkles, title: "Events & entertainment", questions: ["Event organisation","Venue quality","Staff friendliness","Value for money","Would recommend","Return intent","Ticketing/booking experience","Queue management","Food & drink quality","Parking & transport","Safety & security feel","Speaker/performer rating","Sound & AV quality","Networking opportunity","Programme/schedule quality","Signage & navigation","Accessibility provision","Merchandise experience","Post-event communication","Overall event rating"] },
  { icon: HeartHandshake, title: "Employee survey", questions: ["Morale","Work-life balance","Feeling valued","Workload","Motivation","Manager communication","Manager fairness","Recognition","Team collaboration","Inclusion & belonging","Career progression","Training quality","Goal clarity","Role clarity","Job satisfaction","Internal communication","Pay & benefits fairness","Remote/hybrid flexibility","Psychological safety","Overall employee experience"] },
];

const channelCompare = [
  { channel: "Email surveys", open: "20%", response: "5–10%", time: "3–7 days", tone: "muted" },
  { channel: "Web pop-ups", open: "8%", response: "1–3%", time: "instant abandon", tone: "muted" },
  { channel: "SMS surveys", open: "82%", response: "15–20%", time: "hours", tone: "muted" },
  { channel: "WhatsApp (VoxBulk)", open: "98%", response: "40–60%", time: "<60 sec", tone: "hero" },
];

function SurveysPage() {
  return (
    <div className="bg-background text-body antialiased">
      <SiteHeader />
      <main>
        <Hero
          badgeText="Live now · WhatsApp Surveys"
          headline={<>Surveys your audience actually <span className="serif-italic text-gold">responds to</span>.</>}
          sub={<>Send smart AI-built surveys straight to WhatsApp. 98% open rates, instant results, zero chasing.</>}
          primaryHref="/contact"
          primaryLabel="Request a demo"
        />

        {/* How it works */}
        <section className="py-24 md:py-28 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="text-center max-w-[680px] mx-auto">
              <span className="eyebrow">How it works</span>
              <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">Three steps. <span className="serif-italic text-primary">Zero friction.</span></h2>
            </div>
            <div className="mt-14 grid md:grid-cols-3 gap-5">
              {steps.map((st) => (
                <div key={st.n} className="bg-white border border-border rounded-2xl p-7">
                  <div className="w-14 h-14 rounded-full bg-navy text-gold flex items-center justify-center font-bold">{st.n}</div>
                  <h3 className="mt-4 text-[19px] font-bold text-heading">{st.title}</h3>
                  <p className="mt-2 text-[14.5px] text-body leading-[1.65]">{st.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Who it's for */}
        <section className="py-24 md:py-28 bg-white">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="max-w-[680px]">
              <span className="eyebrow">Who it's for</span>
              <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">Built for teams who need <span className="serif-italic text-primary">real answers</span>.</h2>
            </div>
            <div className="mt-12 grid md:grid-cols-4 sm:grid-cols-2 gap-5">
              {audiences.map((a) => (
                <div key={a.title} className="card-soft p-6">
                  <div className="w-11 h-11 rounded-xl bg-primary/10 text-primary flex items-center justify-center"><a.icon size={20} /></div>
                  <h3 className="mt-4 text-[16px] font-bold text-heading">{a.title}</h3>
                  <p className="mt-1.5 text-[13.5px] text-body leading-[1.6]">{a.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Voice notes in any language */}
        <section className="relative py-24 md:py-28 bg-navy text-white overflow-hidden">
          {/* Animated background blobs */}
          <div aria-hidden className="absolute inset-0 pointer-events-none">
            <div className="absolute -top-24 -left-20 w-[420px] h-[420px] rounded-full blur-3xl opacity-30" style={{ background: "radial-gradient(circle, #D4A93A 0%, transparent 60%)", animation: "float-y 14s ease-in-out infinite" }} />
            <div className="absolute -bottom-32 -right-16 w-[460px] h-[460px] rounded-full blur-3xl opacity-25" style={{ background: "radial-gradient(circle, #2A82EB 0%, transparent 60%)", animation: "float-y-2 18s ease-in-out infinite" }} />
            <div className="absolute top-1/3 left-1/2 w-[280px] h-[280px] rounded-full blur-3xl opacity-20" style={{ background: "radial-gradient(circle, #14b8a6 0%, transparent 60%)", animation: "float-y 22s ease-in-out infinite" }} />
          </div>

          <div className="relative max-w-[1180px] mx-auto px-5 md:px-10 grid lg:grid-cols-2 gap-14 items-center">
            <div>
              <span className="inline-flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-gold">
                <Languages size={14} /> Any language · Any accent
              </span>
              <h2 className="mt-4 text-[34px] md:text-[46px] font-bold tracking-[-0.03em] leading-[1.05] text-white">
                Your customers speak freely. <span className="serif-italic text-gold">You read everything in English.</span>
              </h2>
              <p className="mt-5 text-[16.5px] text-white/75 leading-[1.7] max-w-[520px]">
                Send a voice note in any language — it lands in your dashboard translated, clear, and ready to act on.
                <span className="text-white"> 50+ languages, any accent, zero effort.</span>
              </p>
              <div className="mt-7 flex flex-wrap gap-2">
                {["English","العربية","中文","Español","Français","Português","हिन्दी","Deutsch","日本語","Türkçe","Русский","Bahasa"].map((l) => (
                  <span key={l} className="px-3 h-8 inline-flex items-center rounded-full border border-white/15 bg-white/[0.04] text-[12.5px] text-white/80">{l}</span>
                ))}
              </div>
              <div className="mt-8 grid sm:grid-cols-3 gap-3">
                {[
                  { Icon: Mic, label: "Voice in" },
                  { Icon: Sparkles, label: "AI translates" },
                  { Icon: FileText, label: "English insights out" },
                ].map((s) => (
                  <div key={s.label} className="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 flex items-center gap-3">
                    <span className="w-9 h-9 rounded-lg bg-gold/20 text-gold flex items-center justify-center"><s.Icon size={16} /></span>
                    <span className="text-[13.5px] font-semibold text-white">{s.label}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Animated voice → translation mock */}
            <div className="relative">
              <div className="relative mx-auto max-w-[440px] rounded-3xl border border-white/10 bg-white/[0.04] backdrop-blur-md p-5 shadow-[0_30px_80px_-30px_rgba(0,0,0,0.6)]">
                {/* Incoming voice note */}
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-full bg-teal/30 text-teal flex items-center justify-center"><Mic size={16} /></div>
                  <div className="flex-1 rounded-2xl rounded-tl-sm bg-white/[0.06] border border-white/10 px-4 py-3">
                    <div className="flex items-center gap-2 text-[11px] text-white/50 font-semibold uppercase tracking-wider">
                      <span className="w-1.5 h-1.5 rounded-full bg-gold animate-pulse" /> Voice · العربية · 0:18
                    </div>
                    <div className="mt-2 flex items-end gap-[3px] h-8">
                      {Array.from({ length: 28 }).map((_, i) => (
                        <span key={i} className="w-[3px] rounded-full bg-gold/70" style={{ height: `${20 + Math.sin(i * 0.7) * 18 + (i % 5) * 4}%`, animation: `pulse 1.6s ease-in-out ${i * 0.05}s infinite` }} />
                      ))}
                    </div>
                  </div>
                </div>

                {/* Translation arrow */}
                <div className="my-4 flex items-center gap-3 text-white/40 text-[11px] uppercase tracking-[0.18em] font-semibold">
                  <span className="flex-1 h-px bg-white/10" />
                  <span className="flex items-center gap-1.5 text-gold"><Languages size={12} /> Auto-translated</span>
                  <span className="flex-1 h-px bg-white/10" />
                </div>

                {/* English transcript card */}
                <div className="rounded-2xl bg-white text-heading p-4 border border-white/10 shadow-lg">
                  <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted-text">
                    <span className="flex items-center gap-1.5 text-primary"><FileText size={12} /> English transcript</span>
                    <span className="px-2 py-0.5 rounded-full bg-teal/15 text-teal">Positive</span>
                  </div>
                  <p className="mt-2 text-[14px] leading-[1.55] text-body">
                    "The onboarding was smooth, but I'd love a faster way to invite my whole team. Overall — really happy with how easy it is."
                  </p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {["Onboarding","Team invites","Ease of use"].map((t) => (
                      <span key={t} className="text-[11px] px-2 py-0.5 rounded-md bg-primary/10 text-primary font-semibold">{t}</span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Prebuilt templates library */}
        <section className="py-24 md:py-28 bg-beige">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="text-center max-w-[720px] mx-auto">
              <span className="eyebrow">Prebuilt templates</span>
              <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                Launch in minutes with <span className="serif-italic text-primary">battle-tested surveys</span>.
              </h2>
              <p className="mt-5 text-[16px] text-body leading-[1.7]">
                11 industries. 100+ proven questions. Pick a template, edit anything, send. Or let our AI build one from a single sentence about your goal.
              </p>
            </div>

            <div className="mt-12 grid lg:grid-cols-3 md:grid-cols-2 gap-5">
              {templates.map((t) => (
                <div key={t.title} className="card-soft p-6 bg-white">
                  <div className="flex items-center gap-3">
                    <span className="w-11 h-11 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
                      <t.icon size={20} />
                    </span>
                    <h3 className="text-[16px] font-bold text-heading">{t.title}</h3>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-1.5">
                    {t.questions.map((q) => (
                      <span key={q} className="text-[12px] px-2.5 py-1 rounded-full bg-beige border border-border text-body">
                        {q}
                      </span>
                    ))}
                  </div>
                  <div className="mt-5 text-[12.5px] font-semibold uppercase tracking-wider text-muted-text flex items-center gap-1.5">
                    <CheckCircle2 size={14} className="text-teal" /> {t.questions.length} ready questions
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Why WhatsApp beats web surveys */}
        <section className="py-24 md:py-28 bg-white">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="max-w-[720px]">
              <span className="eyebrow">The numbers</span>
              <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                Why WhatsApp surveys <span className="serif-italic text-primary">outperform</span> email and web.
              </h2>
              <p className="mt-5 text-[16px] text-body leading-[1.7] max-w-[620px]">
                The average email survey is opened by 1 in 5 people and answered by fewer. WhatsApp lives in the same thread as messages from family and friends — so it gets opened, and it gets answered.
              </p>
            </div>

            <div className="mt-12 grid lg:grid-cols-2 gap-10 items-start">
              {/* Comparison table */}
              <div className="rounded-2xl border border-border overflow-hidden bg-white">
                <div className="grid grid-cols-4 px-5 py-3 bg-beige text-[11.5px] font-bold uppercase tracking-wider text-muted-text">
                  <span>Channel</span>
                  <span className="text-center">Open rate</span>
                  <span className="text-center">Response</span>
                  <span className="text-right">Time to reply</span>
                </div>
                {channelCompare.map((row) => (
                  <div
                    key={row.channel}
                    className={`grid grid-cols-4 px-5 py-4 items-center text-[13.5px] border-t border-border ${row.tone === "hero" ? "bg-primary/5" : ""}`}
                  >
                    <span className={`font-semibold ${row.tone === "hero" ? "text-primary" : "text-heading"}`}>{row.channel}</span>
                    <span className={`text-center font-bold ${row.tone === "hero" ? "text-primary text-[16px]" : "text-body"}`}>{row.open}</span>
                    <span className={`text-center font-bold ${row.tone === "hero" ? "text-primary text-[16px]" : "text-body"}`}>{row.response}</span>
                    <span className={`text-right ${row.tone === "hero" ? "text-primary font-semibold" : "text-body"}`}>{row.time}</span>
                  </div>
                ))}
              </div>

              {/* Fact cards */}
              <div className="grid sm:grid-cols-2 gap-4">
                {[
                  { Icon: MessageCircle, stat: "98%", label: "of WhatsApp messages get read", sub: "vs. 20% for email." },
                  { Icon: TrendingUp, stat: "3–6×", label: "more responses than web or email surveys", sub: "across HR, retail and healthcare." },
                  { Icon: Clock, stat: "<60 sec", label: "median time to first reply", sub: "email takes days. Web pop-ups get dismissed." },
                  { Icon: CheckCircle2, stat: "0", label: "logins, links or apps to install", sub: "the conversation happens where they already are." },
                ].map((f) => (
                  <div key={f.label} className="card-soft p-5">
                    <span className="w-10 h-10 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
                      <f.Icon size={18} />
                    </span>
                    <div className="mt-3 text-[26px] font-bold text-heading tracking-tight">{f.stat}</div>
                    <div className="mt-1 text-[13.5px] font-semibold text-heading">{f.label}</div>
                    <div className="mt-1 text-[12.5px] text-body leading-[1.55]">{f.sub}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* AI calling survey — go deeper */}
        <section className="relative py-24 md:py-28 bg-navy text-white overflow-hidden">
          <div aria-hidden className="absolute inset-0 pointer-events-none">
            <div className="absolute -top-20 right-0 w-[420px] h-[420px] rounded-full blur-3xl opacity-25" style={{ background: "radial-gradient(circle, #D4A93A 0%, transparent 60%)" }} />
            <div className="absolute -bottom-24 -left-10 w-[380px] h-[380px] rounded-full blur-3xl opacity-20" style={{ background: "radial-gradient(circle, #14b8a6 0%, transparent 60%)" }} />
          </div>
          <div className="relative max-w-[1180px] mx-auto px-5 md:px-10 grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <span className="inline-flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-gold">
                <Phone size={14} /> When you need more than text
              </span>
              <h2 className="mt-4 text-[34px] md:text-[46px] font-bold tracking-[-0.03em] leading-[1.05] text-white">
                Go deeper with an <span className="serif-italic text-gold">AI calling survey</span>.
              </h2>
              <p className="mt-5 text-[16.5px] text-white/75 leading-[1.7] max-w-[540px]">
                For the moments where a tick-box won't do — exit interviews, churn investigations, post-incident reviews — VoxBulk picks up the phone. A natural AI voice runs a real conversation, follows up on every "it depends", and hands you a scored, summarised transcript.
              </p>
              <ul className="mt-7 space-y-3 text-[14.5px] text-white/85">
                {[
                  "Adaptive follow-ups — the AI probes when an answer is vague",
                  "Multilingual voice in and out, transcribed in English",
                  "Sentiment, topics and risk flags scored automatically",
                  "Recorded, transcribed and synced to your dashboard",
                ].map((b) => (
                  <li key={b} className="flex items-start gap-3">
                    <CheckCircle2 size={18} className="text-gold mt-0.5 shrink-0" />
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/contact" className="btn-primary text-[15px] h-12 px-7">Book a live demo <ArrowRight size={16} /></Link>
                <Link to="/recruitment" className="btn-outline text-[15px] h-12 px-7 border-white/30 text-white hover:bg-white/10">See AI Interview Screening</Link>
              </div>
            </div>

            <div className="relative mx-auto max-w-[440px] w-full rounded-3xl border border-white/10 bg-white/[0.04] backdrop-blur-md p-5 shadow-[0_30px_80px_-30px_rgba(0,0,0,0.6)]">
              <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-white/50">
                <span className="flex items-center gap-1.5 text-gold"><Phone size={12} /> AI call · live</span>
                <span>02:14</span>
              </div>
              <div className="mt-4 space-y-3 text-[13.5px]">
                <div className="rounded-2xl rounded-tl-sm bg-white/[0.06] border border-white/10 px-4 py-2.5 text-white/85">
                  <span className="text-[10.5px] uppercase tracking-wider text-gold font-semibold">VoxBulk AI</span>
                  <p className="mt-1">"You mentioned the onboarding felt rushed — what specifically would have helped?"</p>
                </div>
                <div className="rounded-2xl rounded-tr-sm bg-teal/15 border border-teal/30 px-4 py-2.5 text-white ml-8">
                  <span className="text-[10.5px] uppercase tracking-wider text-teal font-semibold">Customer</span>
                  <p className="mt-1">"More hand-holding in the first week. A single contact, not five emails."</p>
                </div>
                <div className="rounded-2xl rounded-tl-sm bg-white/[0.06] border border-white/10 px-4 py-2.5 text-white/85">
                  <span className="text-[10.5px] uppercase tracking-wider text-gold font-semibold">VoxBulk AI</span>
                  <p className="mt-1">"Got it. Would a dedicated onboarding manager have changed your decision to renew?"</p>
                </div>
              </div>
              <div className="mt-5 pt-4 border-t border-white/10 grid grid-cols-3 gap-3 text-center">
                <div><div className="text-gold font-bold text-[16px]">7 min</div><div className="text-[11px] text-white/55">avg call</div></div>
                <div><div className="text-gold font-bold text-[16px]">12</div><div className="text-[11px] text-white/55">follow-ups</div></div>
                <div><div className="text-gold font-bold text-[16px]">100%</div><div className="text-[11px] text-white/55">transcribed</div></div>
              </div>
            </div>
          </div>
        </section>



        {/* Custom-built surveys */}
        <section className="py-24 md:py-28 bg-white">
          <div className="max-w-[1180px] mx-auto px-5 md:px-10">
            <div className="grid lg:grid-cols-2 gap-14 items-center">
              <div>
                <span className="eyebrow">Custom-built for you</span>
                <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
                  Not on the list? We'll <span className="serif-italic text-primary">build it for you</span>.
                </h2>
                <p className="mt-5 text-[16px] text-body leading-[1.7] max-w-[560px]">
                  Every business is different. If our 14 templates don't fit exactly, we design a survey — WhatsApp <em>or</em> AI calling — around your questions, your tone, your logic and your branding. Skip logic, branching, follow-ups, scoring rules — all yours.
                </p>

                <ul className="mt-7 space-y-3 text-[14.5px] text-body">
                  {[
                    { Icon: Wand2, t: "Your questions, your wording", d: "We workshop the flow with you, then our AI polishes it for WhatsApp or voice." },
                    { Icon: Settings2, t: "Custom logic & branching", d: "Skip-logic, follow-ups, conditional paths, weighted scoring — however deep you want to go." },
                    { Icon: Wrench, t: "Built once, sent forever", d: "One-time setup. After that it runs on your normal per-survey or per-minute rate." },
                  ].map((b) => (
                    <li key={b.t} className="flex items-start gap-3">
                      <span className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0"><b.Icon size={16} /></span>
                      <div>
                        <div className="font-semibold text-heading">{b.t}</div>
                        <div className="text-[13.5px] text-body leading-[1.6]">{b.d}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Pricing panel */}
              <div className="rounded-3xl border border-border bg-beige p-7 md:p-9 shadow-elegant">
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-text">How custom pricing works</div>
                <h3 className="mt-3 text-[24px] font-bold text-heading tracking-[-0.02em] leading-[1.2]">
                  Standard rates + a small one-off setup fee.
                </h3>
                <p className="mt-3 text-[14px] text-body leading-[1.65]">
                  No hidden retainers. You pay the normal per-survey or per-minute rate you'd pay for a template — plus a one-time build fee based on complexity.
                </p>

                <div className="mt-6 space-y-3">
                  <div className="rounded-2xl bg-white border border-border px-5 py-4 flex items-center justify-between">
                    <div>
                      <div className="text-[13px] font-semibold text-heading">WhatsApp survey — custom</div>
                      <div className="text-[12.5px] text-muted-text">Same per-send rate as templates</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[12px] text-muted-text">+ setup from</div>
                      <div className="text-[18px] font-bold text-heading tabular-nums">£99</div>
                    </div>
                  </div>
                  <div className="rounded-2xl bg-white border border-border px-5 py-4 flex items-center justify-between">
                    <div>
                      <div className="text-[13px] font-semibold text-heading">AI calling survey — custom</div>
                      <div className="text-[12.5px] text-muted-text">Same per-minute rate as templates</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[12px] text-muted-text">+ setup from</div>
                      <div className="text-[18px] font-bold text-heading tabular-nums">£249</div>
                    </div>
                  </div>
                </div>

                <div className="mt-5 flex items-start gap-2 text-[12.5px] text-muted-text leading-[1.55]">
                  <CheckCircle2 size={14} className="text-teal mt-0.5 shrink-0" />
                  <span>Setup covers design workshop, scripting, logic build, review round and go-live. Typical turnaround 3–5 working days.</span>
                </div>

                <Link to="/contact" className="mt-6 w-full inline-flex items-center justify-center gap-2 h-12 rounded-xl bg-navy text-white font-semibold text-[14px] hover:bg-navy/90 transition-colors">
                  Design my custom survey <ArrowRight size={14} />
                </Link>
              </div>
            </div>
          </div>
        </section>

        <StatsRow items={[
          { value: "98%", label: "WhatsApp open rate" },
          { value: "3×", label: "more responses than email surveys" },
          { value: "<60s", label: "average time to complete" },
          { value: "100%", label: "responses scored automatically" },
        ]} />

        {/* Pricing */}
        <section className="py-24 md:py-28 bg-beige">
          <div className="max-w-[1080px] mx-auto px-5 md:px-10 text-center">
            <span className="eyebrow">Pricing</span>
            <h2 className="mt-4 text-[36px] md:text-[48px] font-bold tracking-[-0.03em] text-heading leading-[1.05]">
              One shared plan with <span className="serif-italic text-primary">AI Interview Screening</span>.
            </h2>
            <p className="mt-5 text-[16px] text-body max-w-[620px] mx-auto">
              WhatsApp Surveys and AI Interview Screening run on the same package. Subscribe monthly or pay as you go — use your minutes and surveys however suits you.
            </p>
            <div className="mt-8 flex justify-center gap-3 flex-wrap">
              <Link to="/pricing" className="btn-primary text-[15px] h-12 px-7">
                See pricing <ArrowRight size={16} />
              </Link>
              <Link to="/contact" className="btn-outline text-[15px] h-12 px-7">Talk to us</Link>
            </div>
          </div>
        </section>


        <BottomCTA />
      </main>
      <SiteFooter />
    </div>
  );
}
