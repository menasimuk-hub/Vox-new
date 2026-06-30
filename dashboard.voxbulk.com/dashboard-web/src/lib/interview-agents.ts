import type { InterviewAgent } from "@/lib/queries";

export type AgentDialectDisplay = {
  dialect_code: string;
  dialect_label: string;
  dialect_description: string;
};

export function resolveInterviewAgentDialect(agent: InterviewAgent): AgentDialectDisplay {
  if (agent.dialect_code && agent.dialect_label) {
    return {
      dialect_code: agent.dialect_code,
      dialect_label: agent.dialect_label,
      dialect_description: agent.dialect_description || "",
    };
  }

  const blob = [agent.name, agent.voice_label, agent.voice_type_label, agent.dialect_description]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  if (blob.includes("sultan") || blob.includes("saudi") || blob.includes("gulf") || blob.includes("khaleeji")) {
    return {
      dialect_code: "SA",
      dialect_label: "Saudi Gulf",
      dialect_description: "Colloquial Khaleeji phone style — natural, not formal Arabic",
    };
  }
  if (
    blob.includes("jammal") ||
    blob.includes("jamal") ||
    blob.includes("jamel") ||
    blob.includes("egypt") ||
    blob.includes("egyptian") ||
    blob.includes("masri")
  ) {
    return {
      dialect_code: "EG",
      dialect_label: "Egyptian Arabic",
      dialect_description: "Natural Egyptian phone style — understands Gulf & Levant replies",
    };
  }
  if (agent.language === "ar") {
    return {
      dialect_code: "AR",
      dialect_label: "Arabic",
      dialect_description: "Colloquial Arabic for phone interviews",
    };
  }
  return {
    dialect_code: "GB",
    dialect_label: "British English",
    dialect_description: "Professional UK phone screening style",
  };
}

export function interviewAgentDisplayName(agent: InterviewAgent): string {
  const raw = (agent.voice_label || agent.name || "").trim();
  return raw.replace(/\s*-\s*ar\s*$/i, "").replace(/\s*\(male\s+ar\)\s*$/i, "").trim();
}
