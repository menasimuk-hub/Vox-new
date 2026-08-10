export type Option = { label: string; value: string; low?: boolean };
export type Question = { id: string; text: string; followUpPrompt: string; options: Option[] };

export type SurveyTheme = {
  bgClass: string;
  ink: string;
  sub: string;
  card: string;
  border: string;
  accent: string;
  accent2: string;
  cool: string;
  gradientButton: string;
  gradientProgress: string;
  selectedShadow: string;
  ringA: string;
  ringB: string;
};

export type SurveyTemplateDef = {
  id: string;
  name: string;
  category: "industry" | "seasonal";
  blurb: string;
  motifs: string[];
  theme: SurveyTheme;
  questions: Question[];
  thankYouTitle: string;
  thankYouSubtitle: string;
};

export const DEFAULT_QUESTIONS: Question[] = [
  {
    id: "experience",
    text: "How was your overall experience?",
    followUpPrompt: "Sorry to hear that. What went wrong?",
    options: [
      { label: "Loved it", value: "great" },
      { label: "It was okay", value: "okay" },
      { label: "Not great", value: "poor", low: true },
    ],
  },
  {
    id: "recommend",
    text: "Would you recommend us to a friend?",
    followUpPrompt: "Got it — what's holding you back?",
    options: [
      { label: "Absolutely", value: "yes" },
      { label: "Maybe", value: "maybe", low: true },
      { label: "Not really", value: "no", low: true },
    ],
  },
  {
    id: "speed",
    text: "How did our speed feel?",
    followUpPrompt: "Thanks — where did we lose time?",
    options: [
      { label: "Quick", value: "fast" },
      { label: "Fine", value: "avg" },
      { label: "Too slow", value: "slow", low: true },
    ],
  },
];

export const SURVEY_TEMPLATES: SurveyTemplateDef[] = [
  {
    id: "restaurants-cafes",
    name: "Restaurants & Cafés",
    category: "industry",
    blurb: "Food, service and ambience in three taps — table QR ready.",
    motifs: ["☕", "🥐", "🍽️", "🍷"],
    theme: {
      bgClass: "bg-restaurant-gradient",
      ink: "#3a1f0f",
      sub: "rgba(58,31,15,0.65)",
      card: "rgba(255,251,244,0.85)",
      border: "rgba(58,31,15,0.12)",
      accent: "#c2410c",
      accent2: "#f59e0b",
      cool: "#65a30d",
      gradientButton: "linear-gradient(135deg,#c2410c,#f59e0b)",
      gradientProgress: "linear-gradient(90deg,#c2410c,#f59e0b,#65a30d)",
      selectedShadow: "0 8px 24px -8px rgba(194,65,12,0.55)",
      ringA: "rgba(245,158,11,0.55)",
      ringB: "rgba(194,65,12,0.4)",
    },
    questions: [
      {
        id: "food",
        text: "How was the food & drink?",
        followUpPrompt: "Sorry! What didn't hit the spot?",
        options: [
          { label: "🤤 Delicious", value: "great" },
          { label: "🙂 Decent", value: "okay" },
          { label: "😕 Underwhelming", value: "poor", low: true },
        ],
      },
      {
        id: "service",
        text: "How was the service?",
        followUpPrompt: "Tell us what happened.",
        options: [
          { label: "✨ Attentive", value: "great" },
          { label: "🍽️ Fine", value: "okay" },
          { label: "🙉 Missed us", value: "poor", low: true },
        ],
      },
      {
        id: "vibe",
        text: "How was the ambience?",
        followUpPrompt: "What put you off?",
        options: [
          { label: "🕯️ Cozy", value: "great" },
          { label: "🪑 Okay", value: "okay" },
          { label: "🔊 Not great", value: "poor", low: true },
        ],
      },
    ],
    thankYouTitle: "Bon appétit",
    thankYouSubtitle: "Thanks for the honest bite of feedback — we'll savor it. 🍽️",
  },
  {
    id: "retail-shops",
    name: "Retail Shops",
    category: "industry",
    blurb: "Findability, staff help and checkout speed at the till.",
    motifs: ["🛍️", "🏷️", "🧾", "✨"],
    theme: {
      bgClass: "bg-retail-gradient",
      ink: "#3b0764",
      sub: "rgba(59,7,100,0.65)",
      card: "rgba(255,255,255,0.82)",
      border: "rgba(59,7,100,0.12)",
      accent: "#d946ef",
      accent2: "#22d3ee",
      cool: "#7c3aed",
      gradientButton: "linear-gradient(135deg,#d946ef,#7c3aed)",
      gradientProgress: "linear-gradient(90deg,#d946ef,#7c3aed,#22d3ee)",
      selectedShadow: "0 8px 24px -8px rgba(217,70,239,0.55)",
      ringA: "rgba(217,70,239,0.5)",
      ringB: "rgba(124,58,237,0.4)",
    },
    questions: [
      {
        id: "find",
        text: "Did you find what you wanted?",
        followUpPrompt: "What were you looking for?",
        options: [
          { label: "🛍️ Yes, easily", value: "great" },
          { label: "🧐 Kind of", value: "okay" },
          { label: "🙅 Not really", value: "poor", low: true },
        ],
      },
      {
        id: "staff",
        text: "How helpful was our staff?",
        followUpPrompt: "What could they do better?",
        options: [
          { label: "🌟 Super helpful", value: "great" },
          { label: "🙂 Okay", value: "okay" },
          { label: "😕 Not helpful", value: "poor", low: true },
        ],
      },
      {
        id: "checkout",
        text: "How was checkout?",
        followUpPrompt: "Where did it slow down?",
        options: [
          { label: "⚡ Breezy", value: "fast" },
          { label: "🧾 Fine", value: "avg" },
          { label: "🐢 Too slow", value: "slow", low: true },
        ],
      },
    ],
    thankYouTitle: "You're a gem",
    thankYouSubtitle: "Thanks for shopping with us — your feedback keeps the shelves fresh. ✨",
  },
  {
    id: "salons-spas",
    name: "Salons & Spas",
    category: "industry",
    blurb: "Result, therapist and calm — soft rose-gold styling.",
    motifs: ["🌸", "💖", "🕊️", "❀"],
    theme: {
      bgClass: "bg-salon-gradient",
      ink: "#5b1a2b",
      sub: "rgba(91,26,43,0.62)",
      card: "rgba(255,251,250,0.82)",
      border: "rgba(91,26,43,0.10)",
      accent: "#e11d74",
      accent2: "#f7c6cf",
      cool: "#b76e79",
      gradientButton: "linear-gradient(135deg,#e11d74,#b76e79)",
      gradientProgress: "linear-gradient(90deg,#f7c6cf,#e11d74,#b76e79)",
      selectedShadow: "0 8px 24px -8px rgba(225,29,116,0.45)",
      ringA: "rgba(247,198,207,0.7)",
      ringB: "rgba(225,29,116,0.35)",
    },
    questions: [
      {
        id: "result",
        text: "How do you feel about the result?",
        followUpPrompt: "What would make it perfect?",
        options: [
          { label: "💖 Glowing", value: "great" },
          { label: "🙂 It's fine", value: "okay" },
          { label: "😞 Not what I wanted", value: "poor", low: true },
        ],
      },
      {
        id: "therapist",
        text: "How was your therapist?",
        followUpPrompt: "Tell us more.",
        options: [
          { label: "🌸 Wonderful", value: "great" },
          { label: "🙂 Okay", value: "okay" },
          { label: "😕 Could improve", value: "poor", low: true },
        ],
      },
      {
        id: "ambience",
        text: "How relaxing was the space?",
        followUpPrompt: "What broke the calm?",
        options: [
          { label: "🕊️ Serene", value: "great" },
          { label: "🌿 Alright", value: "okay" },
          { label: "🔊 Distracting", value: "poor", low: true },
        ],
      },
    ],
    thankYouTitle: "Radiant, thank you",
    thankYouSubtitle: "Your feedback keeps our little sanctuary blooming. 🌸",
  },
  {
    id: "hotels-hospitality",
    name: "Hotels & Hospitality",
    category: "industry",
    blurb: "Stay, check-in and team — gold-on-navy luxury finish.",
    motifs: ["🗝️", "🎩", "🛏️", "✦"],
    theme: {
      bgClass: "bg-hotel-gradient",
      ink: "#f5efe0",
      sub: "rgba(245,239,224,0.62)",
      card: "rgba(255,255,255,0.08)",
      border: "rgba(245,239,224,0.18)",
      accent: "#d4af37",
      accent2: "#e9d38a",
      cool: "#0e3a4c",
      gradientButton: "linear-gradient(135deg,#d4af37,#e9d38a)",
      gradientProgress: "linear-gradient(90deg,#d4af37,#e9d38a,#f5efe0)",
      selectedShadow: "0 8px 24px -8px rgba(212,175,55,0.55)",
      ringA: "rgba(212,175,55,0.5)",
      ringB: "rgba(233,211,138,0.4)",
    },
    questions: [
      {
        id: "stay",
        text: "How was your stay overall?",
        followUpPrompt: "We're sorry — what fell short?",
        options: [
          { label: "🌟 Exceptional", value: "great" },
          { label: "🛏️ Pleasant", value: "okay" },
          { label: "🚪 Disappointing", value: "poor", low: true },
        ],
      },
      {
        id: "checkin",
        text: "How was check-in?",
        followUpPrompt: "Where can we smoothen it?",
        options: [
          { label: "🗝️ Effortless", value: "great" },
          { label: "🙂 Fine", value: "okay" },
          { label: "😕 Frustrating", value: "poor", low: true },
        ],
      },
      {
        id: "team",
        text: "How was our team?",
        followUpPrompt: "Any moment we could improve?",
        options: [
          { label: "🎩 Attentive", value: "great" },
          { label: "🙂 Okay", value: "okay" },
          { label: "🔕 Unhelpful", value: "poor", low: true },
        ],
      },
    ],
    thankYouTitle: "Until next time",
    thankYouSubtitle: "Thank you for staying with us — every note helps us welcome you better. 🗝️",
  },
  {
    id: "fitness-gyms",
    name: "Fitness & Gyms",
    category: "industry",
    blurb: "Workout, kit and coaching — high-energy lime and orange.",
    motifs: ["💪", "🏋️", "⚡", "🔥"],
    theme: {
      bgClass: "bg-fitness-gradient",
      ink: "#ecfccb",
      sub: "rgba(236,252,203,0.60)",
      card: "rgba(255,255,255,0.06)",
      border: "rgba(236,252,203,0.15)",
      accent: "#a3e635",
      accent2: "#fb923c",
      cool: "#111827",
      gradientButton: "linear-gradient(135deg,#a3e635,#fb923c)",
      gradientProgress: "linear-gradient(90deg,#a3e635,#fb923c)",
      selectedShadow: "0 8px 24px -6px rgba(163,230,53,0.55)",
      ringA: "rgba(163,230,53,0.55)",
      ringB: "rgba(251,146,60,0.4)",
    },
    questions: [
      {
        id: "workout",
        text: "How was your workout today?",
        followUpPrompt: "What made it tough?",
        options: [
          { label: "💪 Crushed it", value: "great" },
          { label: "🙂 Solid", value: "okay" },
          { label: "😩 Struggled", value: "poor", low: true },
        ],
      },
      {
        id: "equipment",
        text: "How was the equipment?",
        followUpPrompt: "What needs attention?",
        options: [
          { label: "🏋️ Top shape", value: "great" },
          { label: "🔧 Fine", value: "okay" },
          { label: "⚠️ Needs work", value: "poor", low: true },
        ],
      },
      {
        id: "trainer",
        text: "How was our team?",
        followUpPrompt: "Where can we push harder?",
        options: [
          { label: "🔥 On point", value: "great" },
          { label: "🙂 Okay", value: "okay" },
          { label: "😕 Absent", value: "poor", low: true },
        ],
      },
    ],
    thankYouTitle: "Reps logged",
    thankYouSubtitle: "Thanks for the rep of real feedback — see you next session. 💪",
  },
  {
    id: "events-entertainment",
    name: "Events & Entertainment",
    category: "industry",
    blurb: "Vibe, sound and entry flow — neon nightlife palette.",
    motifs: ["🎶", "🎧", "🎉", "🔥"],
    theme: {
      bgClass: "bg-events-gradient",
      ink: "#f5f3ff",
      sub: "rgba(245,243,255,0.60)",
      card: "rgba(255,255,255,0.06)",
      border: "rgba(245,243,255,0.15)",
      accent: "#ec4899",
      accent2: "#22d3ee",
      cool: "#7c3aed",
      gradientButton: "linear-gradient(135deg,#ec4899,#7c3aed,#22d3ee)",
      gradientProgress: "linear-gradient(90deg,#22d3ee,#7c3aed,#ec4899)",
      selectedShadow: "0 8px 24px -6px rgba(236,72,153,0.6)",
      ringA: "rgba(236,72,153,0.5)",
      ringB: "rgba(34,211,238,0.4)",
    },
    questions: [
      {
        id: "hype",
        text: "How was the vibe tonight?",
        followUpPrompt: "What killed the mood?",
        options: [
          { label: "🔥 Electric", value: "great" },
          { label: "🎶 Good", value: "okay" },
          { label: "🥱 Flat", value: "poor", low: true },
        ],
      },
      {
        id: "sound",
        text: "How was the sound & lights?",
        followUpPrompt: "What went off?",
        options: [
          { label: "🎧 Perfect mix", value: "great" },
          { label: "🎚️ Alright", value: "okay" },
          { label: "🔊 Off", value: "poor", low: true },
        ],
      },
      {
        id: "entry",
        text: "How was entry & flow?",
        followUpPrompt: "Where did it jam up?",
        options: [
          { label: "🚪 Smooth", value: "fast" },
          { label: "⏳ Okay", value: "avg" },
          { label: "🐢 Chaotic", value: "slow", low: true },
        ],
      },
    ],
    thankYouTitle: "Encore",
    thankYouSubtitle: "Thanks for turning up — your take fuels the next show. 🎉",
  },
  {
    id: "christmas",
    name: "Christmas",
    category: "seasonal",
    blurb: "Festive red, green and gold for the holiday trading peak.",
    motifs: ["🎄", "❄", "🎁", "✦"],
    theme: {
      bgClass: "bg-christmas-gradient",
      ink: "#fff8ee",
      sub: "rgba(255,248,238,0.65)",
      card: "rgba(255,255,255,0.07)",
      border: "rgba(255,248,238,0.16)",
      accent: "#ef4444",
      accent2: "#22c55e",
      cool: "#fbbf24",
      gradientButton: "linear-gradient(135deg,#ef4444,#22c55e)",
      gradientProgress: "linear-gradient(90deg,#22c55e,#fbbf24,#ef4444)",
      selectedShadow: "0 8px 24px -6px rgba(239,68,68,0.55)",
      ringA: "rgba(239,68,68,0.5)",
      ringB: "rgba(34,197,94,0.4)",
    },
    questions: DEFAULT_QUESTIONS,
    thankYouTitle: "Merry & bright",
    thankYouSubtitle: "Thanks for sharing — happy holidays. 🎄",
  },
  {
    id: "halloween",
    name: "Halloween",
    category: "seasonal",
    blurb: "Pumpkin orange and violet for October campaigns.",
    motifs: ["🎃", "👻", "🦇", "🌙"],
    theme: {
      bgClass: "bg-halloween-gradient",
      ink: "#fff1e0",
      sub: "rgba(255,241,224,0.62)",
      card: "rgba(255,255,255,0.06)",
      border: "rgba(255,241,224,0.16)",
      accent: "#f97316",
      accent2: "#a855f7",
      cool: "#22c55e",
      gradientButton: "linear-gradient(135deg,#f97316,#a855f7)",
      gradientProgress: "linear-gradient(90deg,#a855f7,#f97316)",
      selectedShadow: "0 8px 24px -6px rgba(249,115,22,0.6)",
      ringA: "rgba(249,115,22,0.55)",
      ringB: "rgba(168,85,247,0.4)",
    },
    questions: DEFAULT_QUESTIONS,
    thankYouTitle: "Spooktacular",
    thankYouSubtitle: "Thanks — no tricks, just gratitude for your treat. 🎃",
  },
  {
    id: "ramadan-eid",
    name: "Ramadan & Eid",
    category: "seasonal",
    blurb: "Lantern gold and midnight indigo for Ramadan and Eid.",
    motifs: ["🌙", "✦", "🕌", "🪔"],
    theme: {
      bgClass: "bg-ramadan-gradient",
      ink: "#f5f3ff",
      sub: "rgba(245,243,255,0.62)",
      card: "rgba(255,255,255,0.06)",
      border: "rgba(245,243,255,0.15)",
      accent: "#fbbf24",
      accent2: "#10b981",
      cool: "#6366f1",
      gradientButton: "linear-gradient(135deg,#fbbf24,#10b981)",
      gradientProgress: "linear-gradient(90deg,#10b981,#fbbf24)",
      selectedShadow: "0 8px 24px -6px rgba(251,191,36,0.5)",
      ringA: "rgba(251,191,36,0.5)",
      ringB: "rgba(16,185,129,0.4)",
    },
    questions: DEFAULT_QUESTIONS,
    thankYouTitle: "Eid Mubarak",
    thankYouSubtitle: "Thank you — may your days be blessed. 🌙",
  },
  {
    id: "valentines-day",
    name: "Valentine's Day",
    category: "seasonal",
    blurb: "Blush and crimson for February bookings and gifting.",
    motifs: ["♥", "💌", "❀", "✦"],
    theme: {
      bgClass: "bg-valentines-gradient",
      ink: "#5b0f26",
      sub: "rgba(91,15,38,0.62)",
      card: "rgba(255,251,252,0.82)",
      border: "rgba(91,15,38,0.10)",
      accent: "#e11d48",
      accent2: "#f472b6",
      cool: "#be185d",
      gradientButton: "linear-gradient(135deg,#e11d48,#f472b6)",
      gradientProgress: "linear-gradient(90deg,#f472b6,#e11d48)",
      selectedShadow: "0 8px 24px -6px rgba(225,29,72,0.5)",
      ringA: "rgba(244,114,182,0.55)",
      ringB: "rgba(225,29,72,0.4)",
    },
    questions: DEFAULT_QUESTIONS,
    thankYouTitle: "With love",
    thankYouSubtitle: "Thanks for sharing — you made our day. 💌",
  },
];
