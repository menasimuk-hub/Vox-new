import { Outlet, Link, createRootRoute, HeadContent, Scripts } from "@tanstack/react-router";
import { Toaster } from "@/components/ui/sonner";
import { AuthModalProvider } from "@/components/AuthModal";
import { TalkModalProvider } from "@/components/TalkModal";
import { CurrencyProvider } from "@/components/CurrencyContext";
import { AuthProvider } from "@/lib/auth";
import { fetchSeoSettings, type PublicSeoSettings, absoluteSeoUrl } from "@/lib/seo";
import { HOME_KEYWORDS, PAGE_SEO } from "@/lib/seo-defaults";

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
  loader: async () => {
    const settings = await fetchSeoSettings();
    return { settings };
  },
  head: ({ loaderData }) => {
    const s: PublicSeoSettings = loaderData?.settings || {};
    const siteName = s.site_name || "VoxBulk";
    const description =
      s.home_description ||
      s.default_meta_description ||
      PAGE_SEO.home.description;
    const title = s.home_title || PAGE_SEO.home.title || siteName;
    const keywords =
      [s.home_focus_keyword, s.home_tags].filter(Boolean).join(", ") || HOME_KEYWORDS;
    const meta: Array<Record<string, string>> = [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title },
      { name: "description", content: description },
      { name: "keywords", content: keywords },
      { name: "author", content: siteName },
      { property: "og:title", content: title },
      { property: "og:description", content: description },
      { property: "og:type", content: "website" },
      { property: "og:site_name", content: siteName },
      { property: "og:url", content: `${SITE_ORIGIN}/` },
      { name: "twitter:card", content: s.default_social_image_url ? "summary_large_image" : "summary" },
      { name: "twitter:title", content: title },
      { name: "twitter:description", content: description },
    ];
    if (s.google_site_verification) {
      meta.push({ name: "google-site-verification", content: s.google_site_verification });
    }
    if (s.default_social_image_url) {
      const ogImage = absoluteSeoUrl(s.default_social_image_url);
      if (ogImage) {
        meta.push({ property: "og:image", content: ogImage });
        meta.push({ name: "twitter:image", content: ogImage });
      }
    }

    const graph: Array<Record<string, unknown>> = [];
    if (s.schema_organization !== false) {
      graph.push({
        "@type": "Organization",
        name: siteName,
        legalName: "VoxBulk LTD",
        url: "https://voxbulk.com",
        logo: `${SITE_ORIGIN}${brandAssets.logoBlack}`,
        description,
      });
    }
    if (s.schema_website !== false) {
      graph.push({ "@type": "WebSite", name: siteName, url: "https://voxbulk.com" });
    }

    return {
      meta,
      links: [
        { rel: "preload", as: "font", type: "font/woff2", href: "/fonts/inter-400.woff2", crossOrigin: "anonymous" },
        { rel: "preload", as: "font", type: "font/woff2", href: "/fonts/inter-600.woff2", crossOrigin: "anonymous" },
        {
          rel: "preload",
          as: "font",
          type: "font/woff2",
          href: "/fonts/instrument-serif-400-italic.woff2",
          crossOrigin: "anonymous",
        },
        { rel: "icon", type: "image/x-icon", href: brandAssets.favicon },
        { rel: "icon", type: "image/png", href: brandAssets.faviconPng },
        { rel: "apple-touch-icon", href: brandAssets.faviconPng },
        { rel: "stylesheet", href: appCss },
      ],
      scripts:
        graph.length > 0
          ? [{ type: "application/ld+json", children: JSON.stringify({ "@context": "https://schema.org", "@graph": graph }) }]
          : [],
    };
  },
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
