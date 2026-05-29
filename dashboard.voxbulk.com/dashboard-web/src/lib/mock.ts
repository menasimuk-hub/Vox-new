export type CampaignType = "interview" | "survey" | "recovery" | "followup";
export type CampaignTone =
  | "live" | "scheduled" | "finished" | "archived"
  | "quoted" | "awaiting-payment" | "payment-failed" | "paused";

export type Campaign = {
  id: string;
  name: string;
  type: CampaignType;
  status: CampaignTone;
  responses: number;
  target: number;
  completion: number;
  updatedAt: string;
};

export const campaigns: Campaign[] = [
  { id: "iv1", name: "Senior dental hygienist — London", type: "interview", status: "live", responses: 47, target: 80, completion: 59, updatedAt: "2m ago" },
  { id: "iv2", name: "Practice manager — Manchester", type: "interview", status: "finished", responses: 62, target: 62, completion: 100, updatedAt: "yesterday" },
  { id: "iv3", name: "Receptionist screening — Q4", type: "interview", status: "scheduled", responses: 0, target: 120, completion: 0, updatedAt: "starts Fri" },
  { id: "iv4", name: "Associate dentist callouts", type: "interview", status: "awaiting-payment", responses: 0, target: 40, completion: 0, updatedAt: "draft" },
  { id: "sv1", name: "Annual patient experience (NPS)", type: "survey", status: "live", responses: 2104, target: 3000, completion: 70, updatedAt: "12m ago" },
  { id: "sv2", name: "Hygienist visit pulse", type: "survey", status: "paused", responses: 412, target: 1200, completion: 34, updatedAt: "1h ago" },
  { id: "sv3", name: "Whitening promo feedback", type: "survey", status: "quoted", responses: 0, target: 600, completion: 0, updatedAt: "—" },
  { id: "sv4", name: "ER wait-time pulse", type: "survey", status: "payment-failed", responses: 12, target: 500, completion: 2, updatedAt: "1h ago" },
  { id: "rv1", name: "No-show recovery — this week", type: "recovery", status: "live", responses: 188, target: 240, completion: 78, updatedAt: "8m ago" },
  { id: "rv2", name: "Hygiene recall — overdue 6m+", type: "recovery", status: "live", responses: 96, target: 200, completion: 48, updatedAt: "just now" },
  { id: "fu1", name: "Implant 72h check-in", type: "followup", status: "scheduled", responses: 0, target: 85, completion: 0, updatedAt: "tomorrow" },
];

export const kpis = {
  recovery: [
    { label: "Recovered today", value: "£3,420", delta: "+£820", trend: "up" },
    { label: "Calls made", value: "184", delta: "+34", trend: "up" },
    { label: "No-shows contacted", value: "97%", delta: "+4 pts", trend: "up" },
    { label: "WhatsApp open rate", value: "82%", delta: "+1 pt", trend: "up" },
    { label: "Queue pending", value: "26", delta: "-12", trend: "down" },
    { label: "Avg. call length", value: "1m 42s", delta: "-6s", trend: "down" },
    { label: "Monthly cost", value: "£412", delta: "of £600", trend: "flat" },
    { label: "Monthly target", value: "68%", delta: "+5 pts", trend: "up" },
  ],
  interviews: [
    { label: "Live campaigns", value: "3" },
    { label: "Running calls", value: "47" },
    { label: "Finished this month", value: "12" },
    { label: "Candidates screened", value: "418" },
  ],
  surveys: [
    { label: "Live surveys", value: "5" },
    { label: "Responses (30d)", value: "8,412" },
    { label: "Completion rate", value: "71%" },
    { label: "Paused", value: "2" },
  ],
};

export const callsThisWeek = [
  { day: "Mon", calls: 42 },
  { day: "Tue", calls: 61 },
  { day: "Wed", calls: 73 },
  { day: "Thu", calls: 58 },
  { day: "Fri", calls: 91 },
  { day: "Sat", calls: 22 },
  { day: "Sun", calls: 8 },
];

export const todaySchedule = [
  { time: "09:30", patient: "S. Patel", treatment: "Hygiene", status: "Confirmed" },
  { time: "10:15", patient: "J. Okafor", treatment: "Filling", status: "Rebooked" },
  { time: "11:00", patient: "M. Larsen", treatment: "Whitening consult", status: "AI calling" },
  { time: "14:00", patient: "A. Nguyen", treatment: "Implant review", status: "Confirmed" },
];

export const candidates = [
  { name: "Alex Morgan", duration: "4m 12s", score: 88, recommendation: "Strong yes", sentiment: "Positive" },
  { name: "Priya Shah", duration: "3m 47s", score: 81, recommendation: "Yes", sentiment: "Positive" },
  { name: "Tom Becker", duration: "5m 02s", score: 64, recommendation: "Maybe", sentiment: "Neutral" },
  { name: "Lina Castro", duration: "2m 18s", score: 41, recommendation: "No", sentiment: "Negative" },
  { name: "Yusuf Adeyemi", duration: "4m 55s", score: 92, recommendation: "Strong yes", sentiment: "Positive" },
];

export const recoveryQueue = [
  { time: "08:50", patient: "C. Reyes", phone: "+44 7700 900111", status: "Calling", tone: "calling" as const },
  { time: "08:42", patient: "F. Yamamoto", phone: "+44 7700 900222", status: "Rebooked", tone: "rebooked" as const },
  { time: "08:30", patient: "D. Schmidt", phone: "+44 7700 900333", status: "No answer", tone: "no-answer" as const },
  { time: "08:18", patient: "E. Rossi", phone: "+44 7700 900444", status: "WhatsApp sent", tone: "wa-sent" as const },
  { time: "08:05", patient: "K. Andersson", phone: "+44 7700 900555", status: "Completed", tone: "completed" as const },
];

export const optOuts = [
  { phone: "+44 7700 900012", name: "J. Walker", reason: "Requested removal", added: "12 Mar" },
  { phone: "+44 7700 900034", name: "—", reason: "Wrong number", added: "04 Mar" },
];

export const auditLog = [
  { who: "Amelia M.", action: "Launched survey 'NPS Q4'", when: "2m ago" },
  { who: "Sam T.", action: "Updated AI script for Recall campaign", when: "1h ago" },
  { who: "Owner", action: "Added Tom B. to team (Manager)", when: "yesterday" },
  { who: "System", action: "Dentally sync completed (412 records)", when: "yesterday" },
];

export const invoices = [
  { id: "INV-10293", date: "01 Mar 2026", amount: "£420.00", status: "Paid" },
  { id: "INV-10241", date: "01 Feb 2026", amount: "£420.00", status: "Paid" },
  { id: "INV-10198", date: "01 Jan 2026", amount: "£380.00", status: "Paid" },
];
