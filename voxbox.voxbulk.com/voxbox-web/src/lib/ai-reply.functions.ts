import { generateAiReply as apiGenerateAiReply } from "@/lib/api";

export type AiReplyInput = {
  subject: string;
  from: string;
  body: string;
  tone: string;
  mode: "write" | "fix";
  draft: string;
};

export async function generateAiReply(input: AiReplyInput): Promise<{ reply: string; error: string | null }> {
  const res = await apiGenerateAiReply(input);
  return { reply: res.reply ?? "", error: res.error };
}
