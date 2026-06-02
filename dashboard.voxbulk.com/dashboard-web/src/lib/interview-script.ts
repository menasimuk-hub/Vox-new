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
