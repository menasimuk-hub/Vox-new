import { Outlet, Link, createRootRoute, HeadContent, Scripts } from "@tanstack/react-router";
import { Toaster } from "@/components/ui/sonner";
import { AuthModalProvider } from "@/components/AuthModal";
import { TalkModalProvider } from "@/components/TalkModal";
import { CurrencyProvider } from "@/components/CurrencyContext";
import { AuthProvider } from "@/lib/auth";

import { brandAssets, SITE_ORIGIN } from "@/lib/brand";

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
      { title: "VoxBulk" },
      { name: "description", content: "VoxBulk is an AI assistant platform that automates conversations, workflows and data collection for modern businesses." },
      { name: "author", content: "VoxBulk" },
      { property: "og:title", content: "VoxBulk" },
      { property: "og:description", content: "AI assistant platform automating conversations, workflows and data collection." },
      { property: "og:type", content: "website" },
      { property: "og:site_name", content: "VoxBulk" },
      { name: "twitter:card", content: "summary" },
      { name: "twitter:title", content: "VoxBulk" },
      { name: "twitter:description", content: "AI assistant platform automating conversations, workflows and data collection." },
    ],

    links: [
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Instrument+Serif&display=swap",
      },
      { rel: "icon", type: "image/x-icon", href: brandAssets.favicon },
      { rel: "icon", type: "image/png", href: brandAssets.faviconPng },
      { rel: "apple-touch-icon", href: brandAssets.faviconPng },
      {
        rel: "stylesheet",
        href: appCss,
      },
    ],
    scripts: [
      {
        type: "application/ld+json",
        children: JSON.stringify({
          "@context": "https://schema.org",
          "@graph": [
            {
              "@type": "Organization",
              name: "VoxBulk",
              legalName: "VoxBulk LTD",
              url: "https://voxbulk.com",
              logo: `${SITE_ORIGIN}${brandAssets.logoBlack}`,
              description: "AI assistant platform automating conversations, workflows and data collection.",
            },
            {
              "@type": "WebSite",
              name: "VoxBulk",
              url: "https://voxbulk.com",
            },

          ],
        }),
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
  return (
    <AuthProvider>
      <CurrencyProvider>
        <AuthModalProvider>
          <TalkModalProvider>
            <Outlet />
            <Toaster />
          </TalkModalProvider>
        </AuthModalProvider>
      </CurrencyProvider>
    </AuthProvider>
  );
}
