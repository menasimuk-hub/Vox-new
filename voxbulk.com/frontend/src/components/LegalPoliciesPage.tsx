import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { getApiBaseUrl } from "@/lib/retoverApi";
import {
  LEGAL_TAB_IDS,
  LEGAL_TAB_LABELS,
  type LegalTabId,
} from "@/lib/legalPoliciesConfig";
import defaultBodies from "@/data/legalDefaultBodies.json";
import "./legal-policies.css";

type SidebarSection = { id: string; label: string };

const FALLBACK_PAGES = defaultBodies as Partial<Record<LegalTabId, string>>;

function mergeLegalPages(fromApi: Partial<Record<LegalTabId, string>>) {
  const merged: Partial<Record<LegalTabId, string>> = { ...FALLBACK_PAGES };
  for (const slug of LEGAL_TAB_IDS) {
    const body = fromApi[slug];
    if (body && body.trim()) merged[slug] = body;
  }
  return merged;
}

type LegalPoliciesPageProps = {
  activeTab: LegalTabId;
};

export function LegalPoliciesPage({ activeTab }: LegalPoliciesPageProps) {
  const navigate = useNavigate();
  const contentRef = useRef<HTMLDivElement>(null);
  const [pages, setPages] = useState<Partial<Record<LegalTabId, string>>>({});
  const [loading, setLoading] = useState(true);
  const [sidebarSections, setSidebarSections] = useState<SidebarSection[]>([]);
  const [activeSection, setActiveSection] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        const base = getApiBaseUrl().replace(/\/+$/, "");
        const response = await fetch(`${base}/legal-pages`);
        if (response.ok) {
          const data = (await response.json()) as {
            pages?: Array<{ slug: string; body: string }>;
          };
          const map: Partial<Record<LegalTabId, string>> = {};
          for (const row of data.pages ?? []) {
            if (LEGAL_TAB_IDS.includes(row.slug as LegalTabId) && row.body) {
              map[row.slug as LegalTabId] = row.body;
            }
          }
          if (!cancelled) setPages(mergeLegalPages(map));
          return;
        }
      } catch {
        /* fall through to per-slug fetch */
      }

      const base = getApiBaseUrl().replace(/\/+$/, "");
      const entries = await Promise.all(
        LEGAL_TAB_IDS.map(async (slug) => {
          try {
            const response = await fetch(`${base}/legal-pages/${encodeURIComponent(slug)}`);
            if (!response.ok) return [slug, ""] as const;
            const data = (await response.json()) as { body?: string };
            return [slug, data.body ?? ""] as const;
          } catch {
            return [slug, ""] as const;
          }
        }),
      );
      if (!cancelled) {
        setPages(
          mergeLegalPages(Object.fromEntries(entries) as Partial<Record<LegalTabId, string>>),
        );
      }
    }

    load().finally(() => {
      if (!cancelled) setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const buildSidebar = useCallback(() => {
    const root = contentRef.current;
    if (!root) return;

    const sections: SidebarSection[] = [];
    root.querySelectorAll(".section").forEach((el, idx) => {
      const section = el as HTMLElement;
      if (!section.id) section.id = `section-${idx}`;
      const titleEl = section.querySelector(".section-title");
      const label = titleEl?.textContent?.trim() || `Section ${idx + 1}`;
      sections.push({ id: section.id, label });
    });

    setSidebarSections(sections);
    setActiveSection(sections[0]?.id ?? null);
  }, []);

  useEffect(() => {
    buildSidebar();
  }, [activeTab, pages, loading, buildSidebar]);

  useEffect(() => {
    const root = contentRef.current;
    if (!root) return;

    const onClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      const toggle = target.closest(".toggle:not(.locked)") as HTMLElement | null;
      if (!toggle || !root.contains(toggle)) return;
      event.preventDefault();
      toggle.classList.toggle("on");
      toggle.classList.toggle("off");
    };

    root.addEventListener("click", onClick);
    return () => root.removeEventListener("click", onClick);
  }, [activeTab, pages, loading]);

  const switchTab = (tab: LegalTabId) => {
    navigate({ to: "/legal-policies", search: { tab } });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    const offset = window.innerWidth >= 768 ? 176 : 160;
    const top = el.getBoundingClientRect().top + window.scrollY - offset;
    window.scrollTo({ top, behavior: "smooth" });
    setActiveSection(id);
  };

  const bodyHtml = pages[activeTab] ?? "";
  const tabLabel = LEGAL_TAB_LABELS[activeTab];

  return (
    <div className="legal-policies-hub min-h-screen flex flex-col antialiased">
      <SiteHeader />

      <div className="lp-body flex-1 flex flex-col">
        <nav className="lp-nav" aria-label="Legal documents">
          <div className="lp-nav-tabs">
            {LEGAL_TAB_IDS.map((tab) => (
              <button
                key={tab}
                type="button"
                className={`lp-nav-tab${tab === activeTab ? " active" : ""}`}
                onClick={() => switchTab(tab)}
                aria-current={tab === activeTab ? "page" : undefined}
              >
                {LEGAL_TAB_LABELS[tab]}
              </button>
            ))}
          </div>
        </nav>

        <div className="lp-layout">
          {sidebarSections.length > 0 && (
            <aside className="lp-sidebar" aria-label="On this page">
              <div className="lp-sidebar-title">On this page</div>
              <nav>
                {sidebarSections.map((section) => (
                  <button
                    key={section.id}
                    type="button"
                    className={`lp-sidebar-link${activeSection === section.id ? " active" : ""}`}
                    onClick={() => scrollToSection(section.id)}
                  >
                    {section.label}
                  </button>
                ))}
              </nav>
            </aside>
          )}

          <main className="lp-main">
            {loading ? (
              <p className="lp-loading">Loading {tabLabel}…</p>
            ) : bodyHtml ? (
              <div
                ref={contentRef}
                className="lp-content"
                dangerouslySetInnerHTML={{ __html: bodyHtml }}
              />
            ) : (
              <p className="lp-loading">
                {tabLabel} content is not available yet. Please check back shortly.
              </p>
            )}
          </main>
        </div>
      </div>

      <SiteFooter />
    </div>
  );
}
