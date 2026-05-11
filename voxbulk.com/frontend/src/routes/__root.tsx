import { useEffect } from "react";
import {
  Outlet,
  Link,
  createRootRoute,
  HeadContent,
  Scripts,
  useRouter,
} from "@tanstack/react-router";
import { Toaster } from "@/components/ui/sonner";
import { AuthModalProvider } from "@/components/AuthModal";
import { clearAllRetoverSiteLocalKeys } from "@/lib/retoverApi";

import appCss from "../styles.css?url";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Page not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "VOXBULK.COM" },
      {
        name: "description",
        content:
          "VOXBULK.COM automates appointment recovery and booking for UK dental clinics using AI.",
      },
      { name: "author", content: "VOXBULK.COM" },
      { property: "og:title", content: "VOXBULK.COM" },
      {
        property: "og:description",
        content:
          "VOXBULK.COM automates appointment recovery and booking for UK dental clinics using AI.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
      { name: "twitter:site", content: "@VOXBULK" },
      { name: "twitter:title", content: "VOXBULK.COM" },
      {
        name: "twitter:description",
        content:
          "VOXBULK.COM automates appointment recovery and booking for UK dental clinics using AI.",
      },
      {
        property: "og:image",
        content:
          "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/87551d18-c0da-40a6-8e8a-6ea6f29405bb/id-preview-20c3aaaa--de49a3cc-7504-412a-ba67-d8a82d68ccf5.lovable.app-1777888311232.png",
      },
      {
        name: "twitter:image",
        content:
          "https://pub-bb2e103a32db4e198524a2e9ed8f35b4.r2.dev/87551d18-c0da-40a6-8e8a-6ea6f29405bb/id-preview-20c3aaaa--de49a3cc-7504-412a-ba67-d8a82d68ccf5.lovable.app-1777888311232.png",
      },
    ],
    links: [
      {
        rel: "stylesheet",
        href: appCss,
      },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
});

function RootShell({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const router = useRouter();
  // Dashboard/admin logout lands here with ?retover_logout=1 to clear THIS origin's storage (5173).
  // Must use router.navigate — raw replaceState desyncs TanStack Start after hydration and can white-screen the app.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const sp = new URLSearchParams(window.location.search);
    if (sp.get("retover_logout") !== "1") return;
    try {
      clearAllRetoverSiteLocalKeys();
    } catch {
      /* localStorage blocked / quota */
    }
    sp.delete("retover_logout");
    const rest = sp.toString();
    const nextHref = `${window.location.pathname}${rest ? `?${rest}` : ""}`;
    void router.navigate({ href: nextHref, replace: true, resetScroll: false }).catch(() => {
      try {
        window.history.replaceState(window.history.state ?? {}, "", nextHref);
      } catch {
        /* ignore */
      }
    });
  }, [router]);

  return (
    <AuthModalProvider>
      <Outlet />
      <Toaster />
    </AuthModalProvider>
  );
}
