import * as React from "react";
import { useNavigate } from "@tanstack/react-router";

import type { AssistantHighlight, AssistantNextAction } from "@/lib/types/assistant";

type AssistantHighlightContextValue = {
  highlight: AssistantHighlight;
  setHighlight: (h: AssistantHighlight) => void;
  clearHighlight: () => void;
  applyNextAction: (action: AssistantNextAction) => void;
};

const AssistantHighlightCtx = React.createContext<AssistantHighlightContextValue>({
  highlight: null,
  setHighlight: () => {},
  clearHighlight: () => {},
  applyNextAction: () => {},
});

export function AssistantHighlightProvider({ children }: { children: React.ReactNode }) {
  const [highlight, setHighlightState] = React.useState<AssistantHighlight>(null);
  const navigate = useNavigate();

  const setHighlight = React.useCallback((h: AssistantHighlight) => {
    setHighlightState(h);
    if (h?.id) {
      window.setTimeout(() => {
        const el = document.querySelector(`[data-assistant-highlight="${h.id}"]`);
        el?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 300);
    }
  }, []);

  const clearHighlight = React.useCallback(() => setHighlightState(null), []);

  const applyNextAction = React.useCallback(
    (action: AssistantNextAction) => {
      if (action.kind === "navigate" && action.route) {
        void navigate({ to: action.route });
        return;
      }
      if (action.kind === "open_panel" && action.route) {
        void navigate({ to: action.route });
      }
    },
    [navigate],
  );

  return (
    <AssistantHighlightCtx.Provider value={{ highlight, setHighlight, clearHighlight, applyNextAction }}>
      {children}
    </AssistantHighlightCtx.Provider>
  );
}

export function useAssistantHighlight() {
  return React.useContext(AssistantHighlightCtx);
}

export function assistantHighlightClass(id: string | null | undefined, highlight: AssistantHighlight) {
  if (!id || !highlight?.id || highlight.id !== id) return "";
  return "ring-2 ring-primary ring-offset-2 ring-offset-background bg-primary/5 transition-shadow duration-500";
}
