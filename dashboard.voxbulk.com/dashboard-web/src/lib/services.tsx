import * as React from "react";
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import { showRecoveryModules } from "@/lib/feature-flags";
import type { ApiEnabledServices, Organisation } from "@/lib/types/api";

export type ServiceKey = "interviews" | "surveys" | "recovery" | "followup";

const DEFAULT: Record<ServiceKey, boolean> = {
  interviews: true,
  surveys: true,
  recovery: false,
  followup: false,
};

function fromApi(raw?: ApiEnabledServices | null): Record<ServiceKey, boolean> {
  if (!raw) return { ...DEFAULT };
  const base = {
    interviews: raw.interview !== false,
    surveys: raw.survey !== false,
    recovery: Boolean(raw.recovery),
    followup: Boolean(raw.follow_up),
  };
  if (!showRecoveryModules) {
    base.recovery = false;
    base.followup = false;
  }
  return base;
}

function toApi(enabled: Record<ServiceKey, boolean>): ApiEnabledServices {
  return {
    interview: enabled.interviews,
    survey: enabled.surveys,
    recovery: showRecoveryModules ? enabled.recovery : false,
    follow_up: showRecoveryModules ? enabled.followup : false,
  };
}

type Ctx = {
  enabled: Record<ServiceKey, boolean>;
  setEnabled: React.Dispatch<React.SetStateAction<Record<ServiceKey, boolean>>>;
  toggle: (k: ServiceKey, v: boolean) => void;
  save: () => Promise<void>;
  saving: boolean;
  loaded: boolean;
};

const ServicesCtx = React.createContext<Ctx>({
  enabled: DEFAULT,
  setEnabled: () => {},
  toggle: () => {},
  save: async () => {},
  saving: false,
  loaded: false,
});

export function ServicesProvider({ children }: { children: React.ReactNode }) {
  const [enabled, setEnabled] = React.useState<Record<ServiceKey, boolean>>(DEFAULT);
  const [saving, setSaving] = React.useState(false);

  const orgQ = useQuery({
    queryKey: ["organisations", "me"],
    queryFn: () => apiFetch<Organisation>("/organisations/me"),
  });

  React.useEffect(() => {
    if (orgQ.data?.enabled_services) {
      setEnabled(fromApi(orgQ.data.enabled_services));
    }
  }, [orgQ.data]);

  const toggle = (k: ServiceKey, v: boolean) => setEnabled((s) => ({ ...s, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      const result = await apiFetch<{ enabled_services: ApiEnabledServices }>(
        "/organisations/me/enabled-services",
        { method: "PATCH", body: JSON.stringify(toApi(enabled)) },
      );
      setEnabled(fromApi(result.enabled_services));
    } finally {
      setSaving(false);
    }
  };

  return (
    <ServicesCtx.Provider
      value={{
        enabled,
        setEnabled,
        toggle,
        save,
        saving,
        loaded: orgQ.isSuccess,
      }}
    >
      {children}
    </ServicesCtx.Provider>
  );
}

export const useServices = () => React.useContext(ServicesCtx);

export { fromApi as enabledServicesFromApi };
