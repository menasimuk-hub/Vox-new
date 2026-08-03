import { frontpageApiFetch } from "@/lib/api";
import { newsItems, posts, type BlogPost } from "@/lib/blog-data";

export type BodyMode = "text" | "html";

export interface PublicBlogPost {
  slug: string;
  title: string;
  excerpt: string;
  category: string;
  author: string;
  author_role: string;
  published_at: string;
  read_mins: number;
  image_url: string | null;
  body_mode: BodyMode;
  body: string;
}

export type PublicNewsItem = PublicBlogPost;

/** Absolute API origin for blog/news media — never bake 127.0.0.1 into HTML. */
function publicMediaApiOrigin(): string {
  if (typeof window !== "undefined") {
    const h = window.location.hostname.toLowerCase();
    if (h === "voxbulk.com" || h === "www.voxbulk.com") return "https://api.voxbulk.com";
    if (h === "localhost" || h === "127.0.0.1" || h === "::1") {
      // Local Vite: same-origin /frontpage proxy
      return "";
    }
  }
  const configured = (
    import.meta.env.VITE_PUBLIC_API_ORIGIN ||
    import.meta.env.VITE_SSR_API_BASE_URL ||
    import.meta.env.VITE_API_BASE_URL ||
    ""
  )
    .trim()
    .replace(/\/+$/, "");
  if (configured) {
    try {
      const u = new URL(configured.includes("://") ? configured : `https://${configured}`);
      if (u.hostname === "127.0.0.1" || u.hostname === "localhost") {
        return "https://api.voxbulk.com";
      }
      if (u.hostname === "voxbulk.com" || u.hostname === "www.voxbulk.com") {
        return "https://api.voxbulk.com";
      }
      return u.origin;
    } catch {
      /* fall through */
    }
  }
  // SSR / production default — public visitors must hit the API host, not loopback.
  return "https://api.voxbulk.com";
}

function resolveMediaUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  let pathOrUrl = String(url).trim();
  if (!pathOrUrl) return null;

  if (pathOrUrl.startsWith("data:")) return pathOrUrl;

  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    try {
      const u = new URL(pathOrUrl);
      // Rewrite SSR/dev absolute loopback media URLs to a browser-reachable origin.
      if (
        (u.hostname === "127.0.0.1" || u.hostname === "localhost") &&
        u.pathname.includes("/frontpage/blog-news/media/")
      ) {
        pathOrUrl = u.pathname;
      } else {
        return pathOrUrl;
      }
    } catch {
      return pathOrUrl;
    }
  }

  const base = publicMediaApiOrigin().replace(/\/+$/, "");
  // Local Vite: relative /frontpage/... is proxied. Production: always absolute API URL.
  if (!base) {
    return pathOrUrl.startsWith("/") ? pathOrUrl : `/${pathOrUrl}`;
  }
  return `${base}${pathOrUrl.startsWith("/") ? pathOrUrl : `/${pathOrUrl}`}`;
}

function mapItem(raw: Record<string, unknown>): PublicBlogPost {
  return {
    slug: String(raw.slug || ""),
    title: String(raw.title || ""),
    excerpt: String(raw.excerpt || ""),
    category: String(raw.category || "General"),
    author: String(raw.author || "VoxBulk"),
    author_role: String(raw.author_role || ""),
    published_at: String(raw.published_at || raw.date || new Date().toISOString().slice(0, 10)),
    read_mins: Number(raw.read_mins || 3) || 3,
    image_url: resolveMediaUrl((raw.image_url as string | null) || null),
    body_mode: raw.body_mode === "html" ? "html" : "text",
    body: String(raw.body || ""),
  };
}

function escapeHtml(s: string) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function blocksToHtml(content: BlogPost["content"]): string {
  return content
    .map((block) => {
      if (block.type === "h2") return `<h2>${escapeHtml(block.text)}</h2>`;
      if (block.type === "quote") {
        const cite = block.cite ? `<cite>— ${escapeHtml(block.cite)}</cite>` : "";
        return `<blockquote><p>${escapeHtml(block.text)}</p>${cite}</blockquote>`;
      }
      if (block.type === "list") {
        return `<ul>${block.items.map((it) => `<li>${escapeHtml(it)}</li>`).join("")}</ul>`;
      }
      return `<p>${escapeHtml(block.text)}</p>`;
    })
    .join("\n");
}

function staticBlog(slug: string): PublicBlogPost | null {
  const fb = posts.find((p) => p.slug === slug);
  if (!fb) return null;
  return {
    slug: fb.slug,
    title: fb.title,
    excerpt: fb.excerpt,
    category: fb.category,
    author: fb.author,
    author_role: fb.authorRole,
    published_at: fb.date,
    read_mins: fb.readMins,
    image_url: null,
    body_mode: "html",
    body: blocksToHtml(fb.content),
  };
}

function staticNews(slug: string): PublicNewsItem | null {
  const fb = newsItems.find((n) => n.slug === slug);
  if (!fb) return null;
  return {
    slug: fb.slug,
    title: fb.title,
    excerpt: fb.body,
    category: "Announcement",
    author: "VoxBulk",
    author_role: "",
    published_at: fb.date,
    read_mins: 1,
    image_url: null,
    body_mode: "text",
    body: fb.body,
  };
}

export function staticBlogList(): PublicBlogPost[] {
  return posts.map((p) => ({
    slug: p.slug,
    title: p.title,
    excerpt: p.excerpt,
    category: p.category,
    author: p.author,
    author_role: p.authorRole,
    published_at: p.date,
    read_mins: p.readMins,
    image_url: null,
    body_mode: "html" as const,
    body: blocksToHtml(p.content),
  }));
}

export function staticNewsList(): PublicNewsItem[] {
  return newsItems.map((n) => ({
    slug: n.slug,
    title: n.title,
    excerpt: n.body,
    category: "Announcement",
    author: "VoxBulk",
    author_role: "",
    published_at: n.date,
    read_mins: 1,
    image_url: null,
    body_mode: "text" as const,
    body: n.body,
  }));
}

export async function fetchBlogList(): Promise<PublicBlogPost[]> {
  try {
    const data = await frontpageApiFetch<{ items: Record<string, unknown>[] }>("/frontpage/blog");
    const items = (data.items || []).map(mapItem);
    return items.length ? items : staticBlogList();
  } catch {
    return staticBlogList();
  }
}

export async function fetchBlogBySlug(slug: string): Promise<PublicBlogPost | null> {
  try {
    const data = await frontpageApiFetch<Record<string, unknown>>(
      `/frontpage/blog/${encodeURIComponent(slug)}`,
    );
    return mapItem(data);
  } catch (e: unknown) {
    const status = e && typeof e === "object" && "status" in e ? Number((e as { status: number }).status) : 0;
    if (status === 404 || status === 0) return staticBlog(slug);
    return staticBlog(slug);
  }
}

export async function fetchNewsList(): Promise<PublicNewsItem[]> {
  try {
    const data = await frontpageApiFetch<{ items: Record<string, unknown>[] }>("/frontpage/news");
    const items = (data.items || []).map(mapItem);
    return items.length ? items : staticNewsList();
  } catch {
    return staticNewsList();
  }
}

export async function fetchNewsBySlug(slug: string): Promise<PublicNewsItem | null> {
  try {
    const data = await frontpageApiFetch<Record<string, unknown>>(
      `/frontpage/news/${encodeURIComponent(slug)}`,
    );
    return mapItem(data);
  } catch {
    return staticNews(slug);
  }
}
