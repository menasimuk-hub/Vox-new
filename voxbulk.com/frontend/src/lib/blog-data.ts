export interface BlogPost {
  slug: string;
  title: string;
  excerpt: string;
  category: string;
  author: string;
  authorRole: string;
  date: string; // ISO
  readMins: number;
  content: Array<
    | { type: "p"; text: string }
    | { type: "h2"; text: string }
    | { type: "quote"; text: string; cite?: string }
    | { type: "list"; items: string[] }
  >;
}

export const posts: BlogPost[] = [
  {
    slug: "the-real-cost-of-slow-hiring",
    title: "The real cost of slow hiring — and how to reclaim two weeks per role",
    excerpt:
      "Every extra day a role sits open is a day of lost output, stretched teams and a shrinking candidate pool. Here's how automation flips the maths.",
    category: "Recruitment",
    author: "Alex Rahman",
    authorRole: "Head of Product, VoxBulk",
    date: "2026-07-14",
    readMins: 6,
    content: [
      { type: "p", text: "Hiring managers rarely talk about time-to-hire in pounds — but they should. A vacant role in a professional services firm costs, on average, £312 per day in unrealised revenue. Multiply that by 42 days (the UK median) and every open seat is quietly draining more than £13,000 before anyone is even offered the job." },
      { type: "h2", text: "Where the days actually disappear" },
      { type: "p", text: "In the hundreds of pipelines we've audited with clients, the pattern is consistent. It's not the interview stage — it's everything around it." },
      { type: "list", items: [
        "3–5 days lost to CV triage after posting",
        "4–7 days waiting for candidates to reply to first outreach",
        "2–4 days per interview slot juggled across three calendars",
        "1–2 days for hiring managers to write and align on feedback",
      ] },
      { type: "quote", text: "We didn't have a candidate problem. We had a coordination problem.", cite: "Head of Talent, mid-market SaaS" },
      { type: "h2", text: "What automation actually replaces" },
      { type: "p", text: "Contrary to how it's often sold, AI in recruitment isn't about replacing recruiters — it's about deleting the parts of their week they don't want anyway. Screening every applicant. Chasing replies. Booking, rebooking, and rebooking again." },
      { type: "p", text: "When our customers switch on VoxBulk for a role, the same pipeline that took 42 days routinely closes in 18. Not because the AI is faster in isolation, but because the queue between each human step evaporates." },
      { type: "h2", text: "The two-week rule" },
      { type: "p", text: "If you can shave two weeks off time-to-hire on your ten most active roles, that's ~£40,000 back into the business per quarter — before you count the retention benefits of candidates who don't ghost you halfway through." },
    ],
  },
  {
    slug: "whatsapp-beats-email-for-surveys",
    title: "Why WhatsApp quietly became the highest-signal survey channel",
    excerpt:
      "98% open rates aren't a marketing line — they're a structural fact of how people use their phones in 2026. Here's what that means for feedback programs.",
    category: "Surveys",
    author: "Priya Menon",
    authorRole: "Research Lead, VoxBulk",
    date: "2026-06-28",
    readMins: 5,
    content: [
      { type: "p", text: "Email surveys have been dying slowly for a decade. WhatsApp didn't kill them — inbox overload did. But WhatsApp is what took their place, and the numbers aren't close." },
      { type: "h2", text: "Open rate isn't a vanity metric" },
      { type: "p", text: "In 2025 benchmarks across 14 industries, WhatsApp surveys hit a median 98% open rate and 62% completion. Email? 21% and 4%. The gap widens further outside English-first markets." },
      { type: "list", items: [
        "Delivered read receipts within 3 minutes on average",
        "Voice-note replies unlock unfiltered qualitative data",
        "Native translation means one survey works in 50+ languages",
      ] },
      { type: "quote", text: "The customers who never emailed us back left us six-minute voice notes." },
      { type: "h2", text: "Designing for the channel, not against it" },
      { type: "p", text: "The mistake most brands make is porting a 20-question web survey straight into WhatsApp. Don't. Keep it to five questions, allow voice, and let the AI do the translation and sentiment work behind the scenes." },
    ],
  },
  {
    slug: "ai-interviews-without-the-bias",
    title: "AI interviews without the bias — what actually works",
    excerpt:
      "Structured scoring, transparent rubrics, and audit trails: three non-negotiables for using AI in candidate assessment responsibly.",
    category: "AI & Ethics",
    author: "Dr. Rania Osei",
    authorRole: "Advisor, VoxBulk",
    date: "2026-06-10",
    readMins: 7,
    content: [
      { type: "p", text: "The concern isn't whether AI can interview candidates. It can, and it does — millions of times a month across the market. The concern is whether it does so more fairly than the human process it replaces. The honest answer is: only if you design for it." },
      { type: "h2", text: "The three-rubric rule" },
      { type: "list", items: [
        "Every question maps to a competency, not a personality trait",
        "Every score is explainable in plain English on the report",
        "Every candidate can request the transcript and rating rationale",
      ] },
      { type: "quote", text: "If your AI can't explain why it scored someone a 6, it shouldn't be scoring." },
    ],
  },
  {
    slug: "multilingual-feedback-global-brands",
    title: "Multilingual feedback: what global brands get right",
    excerpt:
      "When a customer sends a voice note in Arabic and your team reads it in English within seconds, the loop closes. Here's how leading brands set that up.",
    category: "Customer Feedback",
    author: "Marc Lefevre",
    authorRole: "Customer Success, VoxBulk",
    date: "2026-05-22",
    readMins: 4,
    content: [
      { type: "p", text: "There's a persistent myth that global CX programs require regional call centres and localised survey teams. In 2026, that's simply no longer true — and it hasn't been for eighteen months." },
      { type: "h2", text: "One inbox, every language" },
      { type: "p", text: "The pattern that works: single QR code on the receipt or table tent, WhatsApp opens in the customer's default language, voice or text reply accepted, AI translates and tags sentiment before it hits your dashboard. The brand team reads one language. The customer never switched theirs." },
    ],
  },
  {
    slug: "recruitment-automation-regulated-industries",
    title: "Recruitment automation in regulated industries: a practical guide",
    excerpt:
      "Financial services, healthcare, and legal all have hard constraints. That doesn't mean automation is off the table — it means the guardrails matter more.",
    category: "Recruitment",
    author: "Alex Rahman",
    authorRole: "Head of Product, VoxBulk",
    date: "2026-05-03",
    readMins: 8,
    content: [
      { type: "p", text: "Every conversation with a regulated-industry buyer starts the same way: 'We love this, but compliance will kill it.' They don't. Not if you bring compliance in on day one." },
      { type: "h2", text: "What compliance actually wants" },
      { type: "list", items: [
        "Data residency guarantees (UK/EU-only processing)",
        "Full audit trail of every AI decision and prompt",
        "Human-in-the-loop for any reject decision",
        "DPA signed before pilot, not after",
      ] },
    ],
  },
];

export interface NewsItem {
  slug: string;
  date: string;
  title: string;
  body: string;
}

export const newsItems: NewsItem[] = [
  { slug: "multilingual-voice-notes-62-languages", date: "2026-07-15", title: "VoxBulk expands multilingual voice-note support to 62 languages", body: "Customers on the Growth and Scale plans can now receive and translate voice replies in an additional 12 languages, including Amharic, Sinhala and Uzbek." },
  { slug: "bullhorn-ats-integration", date: "2026-07-02", title: "New Bullhorn ATS integration goes live", body: "Recruitment Automation customers can now push AI interview scores and shortlists directly into Bullhorn pipelines without middleware." },
  { slug: "soc2-type-ii-renewed", date: "2026-06-24", title: "SOC 2 Type II attestation renewed for a second consecutive year", body: "VoxBulk's controls across security, availability and confidentiality were re-attested by an independent auditor with zero exceptions." },
  { slug: "ai-calling-survey-exits-beta", date: "2026-06-11", title: "AI Calling Survey exits beta", body: "The fully-automated voice survey product, previously in closed beta with 40 customers, is now available on the Scale and Enterprise plans." },
  { slug: "cronofy-scheduling-coverage", date: "2026-05-30", title: "Partnership with Cronofy deepens scheduling coverage", body: "Round-robin and pooled availability are now supported natively for teams of up to 200 interviewers on the Enterprise plan." },
  { slug: "manchester-office-opens", date: "2026-05-08", title: "New office opens in Manchester", body: "The customer success and implementation team expands to a second UK location to support growing demand across the North of England." },
  { slug: "customer-feedback-benchmarks-report", date: "2026-04-19", title: "Customer feedback benchmarks report published", body: "Our first annual report on WhatsApp feedback benchmarks — covering 14 industries and 3.2M conversations — is now available on request." },
  { slug: "uk-ai-safety-coalition", date: "2026-04-02", title: "VoxBulk joins the UK AI Safety Coalition", body: "We've formally committed to the coalition's guidelines on AI transparency in candidate assessment and consumer research." },
  { slug: "arabic-dialect-support", date: "2026-03-21", title: "Arabic dialect support ships across all products", body: "Gulf, Levantine and Egyptian dialects are now handled natively across screening, surveys and feedback — no configuration required." },
  { slug: "series-a-extension", date: "2026-03-05", title: "Series A extension closed", body: "An extension round brings total funding to £14.2M, led by existing investors and joined by two new strategic partners in the CX space." },
];
