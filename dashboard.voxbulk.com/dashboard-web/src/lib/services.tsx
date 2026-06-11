import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import { showRecoveryModules } from "@/lib/feature-flags";
import type { ApiEnabledServices, Organisation } from "@/lib/types/api";

export type ServiceKey = "interviews" | "surveys" | "feedback" | "recovery" | "followup";

const DEFAULT: Record<ServiceKey, boolean> = {
  interviews: true,
  surveys: true,
  feedback: false,
  recovery: false,
  followup: false,
};

/** Admin-granted modules — missing/null means available (interview + survey on). */
function fromAllowedApi(raw?: ApiEnabledServices | null): Record<ServiceKey, boolean> {
  if (!raw) return { ...DEFAULT };
  const out = {
    interviews: raw.interview !== false,
    surveys: raw.survey !== false,
    feedback: Boolean(raw.customer_feedback),
    recovery: Boolean(raw.recovery),
    followup: Boolean(raw.follow_up),
  };
  if (!showRecoveryModules) {
    out.recovery = false;
    out.followup = false;
  }
  return out;
}

/** User visibility prefs — explicit false stays off; user can turn back on later. */
function fromEnabledApi(raw?: ApiEnabledServices | null): Record<ServiceKey, boolean> {
  if (!raw) return { ...DEFAULT };
  const out = {
    interviews: "interview" in raw ? Boolean(raw.interview) : true,
    surveys: "survey" in raw ? Boolean(raw.survey) : true,
    feedback: Boolean(raw.customer_feedback),
    recovery: Boolean(raw.recovery),
    followup: Boolean(raw.follow_up),
  };
  if (!showRecoveryModules) {
    out.recovery = false;
    out.followup = false;
  }
  return out;
}

function toApi(state: Record<ServiceKey, boolean>): ApiEnabledServices {
  return {
    interview: state.interviews,
    survey: state.surveys,
    customer_feedback: state.feedback,
    recovery: showRecoveryModules ? state.recovery : false,
    follow_up: showRecoveryModules ? state.followup : false,
  };
}

function visibleFrom(allowed: Record<ServiceKey, boolean>, enabled: Record<ServiceKey, boolean>) {
  return {
    interviews: allowed.interviews && enabled.interviews,
    surveys: allowed.surveys && enabled.surveys,
    feedback: allowed.feedback && enabled.feedback,
    recovery: allowed.recovery && enabled.recovery,
    followup: allowed.followup && enabled.followup,
  } satisfies Record<ServiceKey, boolean>;
}

type Ctx = {
  allowed: Record<ServiceKey, boolean>;
  enabled: Record<ServiceKey, boolean>;
  visible: Record<ServiceKey, boolean>;
  toggle: (k: ServiceKey, v: boolean) => Promise<void>;
  save: () => Promise<void>;
  saving: boolean;
  loaded: boolean;
  error: string | null;
};

const ServicesCtx = React.createContext<Ctx>({
  allowed: DEFAULT,
  enabled: DEFAULT,
  visible: DEFAULT,
  toggle: async () => {},
  save: async () => {},
  saving: false,
  loaded: false,
  error: null,
});

export function ServicesProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [allowed, setAllowed] = React.useState<Record<ServiceKey, boolean>>(DEFAULT);
  const [enabled, setEnabled] = React.useState<Record<ServiceKey, boolean>>(DEFAULT);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const orgQ = useQuery({
    queryKey: ["organisations", "me"],
    queryFn: () => apiFetch<Organisation>("/organisations/me"),
  });

  React.useEffect(() => {
    if (!orgQ.isSuccess || !orgQ.data) return;
    setAllowed(fromAllowedApi(orgQ.data.allowed_services));
    setEnabled(fromEnabledApi(orgQ.data.enabled_services));
  }, [orgQ.data, orgQ.isSuccess]);

  const visible = React.useMemo(() => visibleFrom(allowed, enabled), [allowed, enabled]);

  const saveEnabled = async (next: Record<ServiceKey, boolean>) => {
    setSaving(true);
    setError(null);
    try {
      const result = await apiFetch<{
        enabled_services: ApiEnabledServices;
        allowed_services?: ApiEnabledServices;
      }>("/organisations/me/enabled-services", {
        method: "PATCH",
        body: JSON.stringify(toApi(next)),
      });
      setAllowed(fromAllowedApi(result.allowed_services ?? orgQ.data?.allowed_services));
      setEnabled(fromEnabledApi(result.enabled_services));
      await queryClient.invalidateQueries({ queryKey: ["organisations", "me"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard", "home-summary"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save service settings");
      throw e;
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (k: ServiceKey, v: boolean) => {
    if (!allowed[k]) {
      const msg = "This module is not available on your account. Contact VoxBulk support.";
      setError(msg);
      throw new Error(msg);
    }
    setError(null);
    const next = { ...enabled, [k]: v };
    const nextVisible = visibleFrom(allowed, next);
    if (!Object.values(nextVisible).some(Boolean)) {
      const msg = "Keep at least one service visible in the sidebar.";
      setError(msg);
      throw new Error(msg);
    }
    setEnabled(next);
    await saveEnabled(next);
  };

  const save = async () => saveEnabled(enabled);

  return (
    <ServicesCtx.Provider
      value={{
        allowed,
        enabled,
        visible,
        toggle,
        save,
        saving,
        loaded: orgQ.isSuccess,
        error,
      }}
    >
      {children}
    </ServicesCtx.Provider>
  );
}

export const useServices = () => React.useContext(ServicesCtx);

export { fromAllowedApi, fromEnabledApi, fromEnabledApi as enabledServicesFromApi, visibleFrom, toApi as servicesToApi };
