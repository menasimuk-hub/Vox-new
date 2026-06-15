import type { AssistantHighlightType, AssistantNextAction, AssistantUiCommand } from "@/lib/types/assistant";

type ExecutorContext = {
  navigate: (route: string) => void;
  setHighlight: (h: { type: AssistantHighlightType; id: string; label?: string | null }) => void;
};

export function executeUiCommands(commands: AssistantUiCommand[] | undefined, ctx: ExecutorContext) {
  if (!commands?.length) return;
  for (const cmd of commands) {
    if (cmd.kind === "navigate" || cmd.kind === "open_panel") {
      if (cmd.route) ctx.navigate(cmd.route);
      continue;
    }
    if ((cmd.kind === "highlight" || cmd.kind === "scroll_to") && cmd.highlight_id && cmd.highlight_type) {
      ctx.setHighlight({
        type: cmd.highlight_type,
        id: cmd.highlight_id,
        label: cmd.highlight_label,
      });
      if (cmd.route) ctx.navigate(cmd.route);
    }
  }
}

export function uiCommandsFromNextActions(actions: AssistantNextAction[]): AssistantUiCommand[] {
  return (actions || []).map((a) => ({
    id: a.id,
    kind: a.kind === "open_panel" ? "open_panel" : "navigate",
    route: a.route,
    label: a.label,
    highlight_type: "",
    highlight_id: null,
    highlight_label: null,
  }));
}
