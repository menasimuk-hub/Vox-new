import * as React from "react";

import { fetchAuthenticatedBlob } from "@/lib/api";

/** Loads org logo from authenticated API path into a blob object URL for <img src>. */
export function useOrgLogoPreview(logoUrl?: string | null) {
  const [preview, setPreview] = React.useState<string | null>(null);

  React.useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;

    if (!logoUrl) {
      setPreview(null);
      return;
    }

    void fetchAuthenticatedBlob(logoUrl)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setPreview(objectUrl);
      })
      .catch(() => {
        if (active) setPreview(null);
      });

    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [logoUrl]);

  return preview;
}
