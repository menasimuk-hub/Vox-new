import type { InterviewAgent } from "@/lib/queries";
import {
  ARABIC_REGION_ORDER,
  ENGLISH_REGION_ORDER,
  genderLabel,
  INTERVIEW_REGIONS,
  isArabicRegionCode,
  regionFlagEmoji,
  regionMenuLabel,
} from "@/lib/interview-agent-regions";

export type AgentDialectDisplay = {
  dialect_code: string;
  dialect_label: string;
  dialect_description: string;
  flag_emoji?: string;
};

export function resolveInterviewAgentDialect(agent: InterviewAgent): AgentDialectDisplay {
  const code = agent.accent_region || agent.dialect_code;
  if (code && INTERVIEW_REGIONS[code]) {
    const region = INTERVIEW_REGIONS[code];
    return {
      dialect_code: region.code,
      dialect_label: agent.dialect_label || region.englishLabel,
      dialect_description: agent.dialect_description || `Professional ${region.label} phone screening style`,
      flag_emoji: agent.flag_emoji || region.flagEmoji,
    };
  }
  if (agent.dialect_code && agent.dialect_label) {
    return {
      dialect_code: agent.dialect_code,
      dialect_label: agent.dialect_label,
      dialect_description: agent.dialect_description || "",
      flag_emoji: agent.flag_emoji,
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
    flag_emoji: "🇬🇧",
  };
}

export function interviewAgentDisplayName(agent: InterviewAgent): string {
  const raw = (agent.voice_label || agent.name || "").trim();
  return raw.replace(/\s*-\s*ar\s*$/i, "").replace(/\s*\(male\s+ar\)\s*$/i, "").trim();
}

export function interviewAgentGenderLabel(agent: InterviewAgent): string {
  return genderLabel(agent.gender);
}

export function agentRegionCode(agent: InterviewAgent): string {
  return agent.accent_region || resolveInterviewAgentDialect(agent).dialect_code;
}

export type RegionMenuOption = {
  code: string;
  label: string;
  flagEmoji: string;
  language: "en" | "ar";
};

export function buildRegionMenuOptions(agents: InterviewAgent[]): RegionMenuOption[] {
  const codes = new Set<string>();
  for (const agent of agents) {
    codes.add(agentRegionCode(agent));
  }
  const options: RegionMenuOption[] = [];
  for (const code of ENGLISH_REGION_ORDER) {
    if (!codes.has(code)) continue;
    options.push({
      code,
      label: regionMenuLabel(code),
      flagEmoji: regionFlagEmoji(code),
      language: "en",
    });
  }
  for (const code of ARABIC_REGION_ORDER) {
    if (!codes.has(code)) continue;
    options.push({
      code,
      label: regionMenuLabel(code),
      flagEmoji: regionFlagEmoji(code),
      language: "ar",
    });
  }
  for (const code of codes) {
    if (options.some((o) => o.code === code)) continue;
    options.push({
      code,
      label: regionMenuLabel(code),
      flagEmoji: regionFlagEmoji(code),
      language: isArabicRegionCode(code) ? "ar" : "en",
    });
  }
  return options;
}

export function agentsForRegion(agents: InterviewAgent[], regionCode: string): InterviewAgent[] {
  return agents
    .filter((agent) => agentRegionCode(agent) === regionCode)
    .sort((a, b) => String(a.gender).localeCompare(String(b.gender)));
}

export function groupEnglishInterviewAgents(agents: InterviewAgent[]): { region: string; label: string; agents: InterviewAgent[] }[] {
  const groups: { region: string; label: string; agents: InterviewAgent[] }[] = [];
  const byRegion = new Map<string, InterviewAgent[]>();
  for (const agent of agents) {
    const code = agent.accent_region || resolveInterviewAgentDialect(agent).dialect_code;
    const bucket = byRegion.get(code) || [];
    bucket.push(agent);
    byRegion.set(code, bucket);
  }
  const ordered = [...ENGLISH_REGION_ORDER, ...Array.from(byRegion.keys()).filter((k) => !ENGLISH_REGION_ORDER.includes(k as typeof ENGLISH_REGION_ORDER[number]))];
  for (const code of ordered) {
    const list = byRegion.get(code);
    if (!list?.length) continue;
    const meta = INTERVIEW_REGIONS[code];
    groups.push({
      region: code,
      label: meta?.label || code,
      agents: [...list].sort((a, b) => String(a.gender).localeCompare(String(b.gender))),
    });
  }
  return groups;
}
