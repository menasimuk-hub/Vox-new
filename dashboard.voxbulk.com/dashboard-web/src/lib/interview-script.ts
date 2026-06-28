/** Extract / merge the QUESTIONS block from a full interview script (keeps disclosure + intro server-side). */

export function extractQuestionsBlock(script: string): string {
  const text = String(script || "");
  const match = text.match(/\bQUESTIONS\s*\r?\n([\s\S]*?)(?=\r?\n\s*CLOSING\b|$)/i);
  if (match) return match[1].trim();
  return text.trim();
}

export function mergeQuestionsIntoScript(fullScript: string, questionsBlock: string): string {
  const questions = String(questionsBlock || "").trim();
  const text = String(fullScript || "");
  const match = text.match(/^([\s\S]*?\bQUESTIONS\s*\r?\n)([\s\S]*?)(\r?\n\s*CLOSING[\s\S]*)$/i);
  if (match) {
    const prefix = match[1];
    const closing = match[3].startsWith("\n") ? match[3] : `\n${match[3]}`;
    return `${prefix}${questions}${questions ? "\n" : ""}${closing}`.trimEnd();
  }
  if (!text.trim()) {
    return ["QUESTIONS", questions, "", "CLOSING", "Thank you for your time today."].join("\n");
  }
  return `${text.trim()}\n\nQUESTIONS\n${questions}`;
}

export function questionsMatchApproved(fullScript: string, approvedScript: string): boolean {
  return extractQuestionsBlock(fullScript).trim() === extractQuestionsBlock(approvedScript).trim();
}

const CV_QUESTION_MARKERS = [
  "cv",
  "resume",
  "résumé",
  "curriculum vitae",
  "your experience",
  "your role at",
  "you worked",
  "you mentioned",
  "your background",
  "your previous",
  "tell me about your",
  "on your cv",
  "in your cv",
  "from your cv",
  "achievement",
  "career gap",
  "employment gap",
  "previous employer",
  "last role",
  "most recent role",
  "سيرة",
  "السيرة",
  "الذاتية",
  "خبرة",
  "خبرات",
  "عمل",
  "وظيفة",
  "منصب",
  "إنجاز",
  "انجاز",
  "فجوة",
  "مسار",
  "خلفية",
  "مؤهل",
  "سابق",
  "أخبرني",
  "اخبرني",
  "حدثني",
];

export function looksCvPersonalized(question: string): boolean {
  const q = String(question || "");
  const lower = q.toLowerCase();
  return CV_QUESTION_MARKERS.some((marker) => {
    if (/[\u0600-\u06FF]/.test(marker)) {
      return q.includes(marker);
    }
    return lower.includes(marker);
  });
}

export type ParsedScriptQuestion = {
  index: number;
  text: string;
  cvBased: boolean;
};

/** Parse numbered lines from the QUESTIONS block (or full script). */
export function parseScriptQuestions(scriptOrBlock: string): ParsedScriptQuestion[] {
  const block = extractQuestionsBlock(scriptOrBlock);
  const lines = block.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const items: ParsedScriptQuestion[] = [];
  for (const line of lines) {
    const match = line.match(/^\s*(\d+)\.\s*(.+)$/);
    if (match) {
      const text = match[2].trim();
      items.push({ index: Number(match[1]), text, cvBased: looksCvPersonalized(text) });
      continue;
    }
    if (items.length) {
      items[items.length - 1].text = `${items[items.length - 1].text} ${line}`.trim();
      continue;
    }
    items.push({ index: 1, text: line, cvBased: looksCvPersonalized(line) });
  }
  return items.map((item, i) => ({ ...item, index: i + 1 }));
}

/** Match backend _estimate_interview_duration_minutes (question count only, no AI override). */
export function estimateInterviewDurationMinutes(scriptOrBlock: string): number {
  const parsed = parseScriptQuestions(scriptOrBlock);
  const count = parsed.length || extractQuestionsBlock(scriptOrBlock).split(/\r?\n/).filter((line) => line.trim()).length || 1;
  return Math.max(5, Math.min(30, 2 + Math.round(count * 1.8)));
}

export function resolveScriptFromConfig(config: Record<string, unknown>): string {
  const approved = String(config.approved_script || "").trim();
  const draft = String(config.generated_script_draft || "").trim();
  const isApproved = Boolean(config.script_approved);
  if (isApproved && approved) return approved;
  return draft || approved;
}
