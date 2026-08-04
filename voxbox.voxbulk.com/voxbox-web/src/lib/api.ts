import { SESSION_KEY } from "@/lib/mail-store";
import type { MailAccount, MailFolder, MailMessage } from "@/lib/mail-store";

const TOKEN_KEY = "voxbox.token";

export const API_BASE =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "https://api.voxbulk.com");

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

function snakeToCamel(key: string): string {
  return key.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
}

function camelToSnake(key: string): string {
  return key.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`);
}

function mapKeys(obj: unknown, transform: (k: string) => string): unknown {
  if (Array.isArray(obj)) return obj.map((v) => mapKeys(v, transform));
  if (obj && typeof obj === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      out[transform(k)] = mapKeys(v, transform);
    }
    return out;
  }
  return obj;
}

export function fromApi<T>(obj: unknown): T {
  return mapKeys(obj, snakeToCamel) as T;
}

export function toApi(obj: unknown): unknown {
  return mapKeys(obj, camelToSnake);
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const json = (await res.json()) as { detail?: unknown; message?: unknown };
    if (typeof json.detail === "string") return json.detail;
    if (Array.isArray(json.detail)) return json.detail.map(String).join("; ");
    if (typeof json.message === "string") return json.message;
  } catch {
    /* ignore */
  }
  return res.statusText || `Request failed (${res.status})`;
}

function redirectToLogin() {
  clearToken();
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(SESSION_KEY);
    window.location.assign("/");
  }
}

async function request<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    auth?: boolean;
  } = {},
): Promise<T> {
  const { method = "GET", body, auth = true } = options;
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(toApi(body)) : undefined,
  });

  if (res.status === 401 && auth) {
    redirectToLogin();
    throw new ApiError(401, "Unauthorized");
  }

  if (!res.ok) {
    throw new ApiError(res.status, await parseError(res));
  }

  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  return fromApi<T>(JSON.parse(text));
}

function mapAccount(raw: Record<string, unknown>): MailAccount {
  const camel = fromApi<Record<string, unknown>>(raw);
  return {
    id: String(camel.id ?? ""),
    name: String(camel.name ?? ""),
    email: String(camel.email ?? ""),
    color: String(camel.color ?? "var(--accent-1)"),
    imapHost: String(camel.imapHost ?? ""),
    imapPort: Number(camel.imapPort ?? 993),
    smtpHost: String(camel.smtpHost ?? ""),
    smtpPort: Number(camel.smtpPort ?? 465),
    username: String(camel.username ?? ""),
    password: "",
    ssl: Boolean(camel.ssl ?? camel.imapUseSsl ?? true),
    status: (camel.status as MailAccount["status"]) ?? "untested",
    signature: String(camel.signature ?? ""),
    frozen: Boolean(camel.frozen),
    sortOrder: Number(camel.sortOrder ?? 0),
    passwordConfigured: Boolean(camel.passwordConfigured),
  };
}

function mapMessage(raw: Record<string, unknown>): MailMessage {
  const camel = fromApi<Record<string, unknown>>(raw);
  return {
    id: String(camel.id ?? ""),
    accountId: String(camel.accountId ?? ""),
    from: String(camel.from ?? ""),
    fromEmail: String(camel.fromEmail ?? ""),
    to: String(camel.to ?? ""),
    subject: String(camel.subject ?? ""),
    preview: String(camel.preview ?? ""),
    html: String(camel.html ?? ""),
    text: String(camel.text ?? ""),
    date: String(camel.date ?? new Date().toISOString()),
    unread: Boolean(camel.unread),
    important: Boolean(camel.important),
    starred: Boolean(camel.starred),
    hasAttachment: Boolean(camel.hasAttachment),
    folder: (camel.folder as MailFolder) ?? "inbox",
  };
}

export interface AuthUser {
  username: string;
  displayName: string;
}

export interface LoginResponse extends AuthUser {
  accessToken: string;
  tokenType: string;
}

export interface KpiData {
  total: number;
  unread: number;
  important: number;
  starred: number;
}

export interface TestAccountResult {
  ok: boolean;
  message: string;
  status?: string;
}

export interface SyncResult {
  ok: boolean;
  syncedAccounts: number;
  fetched: number;
  message: string;
}

export interface AiReplyResult {
  reply: string;
  error: string | null;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const raw = await request<Record<string, unknown>>("/voxbox/auth/login", {
    method: "POST",
    body: { username, password },
    auth: false,
  });
  const mapped = fromApi<LoginResponse>(raw);
  if (!mapped.accessToken) {
    throw new ApiError(500, "Login response missing access token.");
  }
  setToken(mapped.accessToken);
  return mapped;
}

export async function fetchMe(): Promise<AuthUser> {
  return request<AuthUser>("/voxbox/auth/me");
}

export async function updateCredentials(body: {
  username?: string;
  password?: string;
  displayName?: string;
  currentPassword: string;
}): Promise<void> {
  try {
    await request("/voxbox/auth/credentials", { method: "PUT", body });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return;
    throw e;
  }
}

export async function fetchAccounts(): Promise<MailAccount[]> {
  const rows = await request<Record<string, unknown>[]>("/voxbox/accounts");
  return rows.map(mapAccount);
}

export async function createAccount(account: MailAccount): Promise<MailAccount> {
  const raw = await request<Record<string, unknown>>("/voxbox/accounts", {
    method: "POST",
    body: accountPayload(account, true),
  });
  return mapAccount(raw);
}

export async function updateAccount(account: MailAccount): Promise<MailAccount> {
  const raw = await request<Record<string, unknown>>(`/voxbox/accounts/${account.id}`, {
    method: "PUT",
    body: accountPayload(account, false),
  });
  return mapAccount(raw);
}

export async function deleteAccount(id: string): Promise<void> {
  await request(`/voxbox/accounts/${id}`, { method: "DELETE" });
}

export async function testAccount(id: string): Promise<TestAccountResult> {
  return request<TestAccountResult>(`/voxbox/accounts/${id}/test`, { method: "POST" });
}

export async function reorderAccounts(orderedIds: string[]): Promise<void> {
  await request("/voxbox/accounts/reorder", {
    method: "PUT",
    body: { orderedIds },
  });
}

function accountPayload(account: MailAccount, isCreate: boolean): Record<string, unknown> {
  const body: Record<string, unknown> = {
    name: account.name,
    email: account.email,
    color: account.color,
    imapHost: account.imapHost,
    imapPort: account.imapPort,
    smtpHost: account.smtpHost,
    smtpPort: account.smtpPort,
    username: account.username,
    ssl: account.ssl,
    signature: account.signature,
    frozen: account.frozen,
  };
  if (account.password || isCreate) {
    body.password = account.password;
  }
  return body;
}

export async function fetchMessages(params: {
  accountId?: string;
  folder?: string;
  tab?: string;
  q?: string;
}): Promise<MailMessage[]> {
  const qs = new URLSearchParams();
  if (params.accountId && params.accountId !== "all") qs.set("account_id", params.accountId);
  if (params.folder) qs.set("folder", params.folder);
  if (params.tab) qs.set("tab", params.tab);
  if (params.q) qs.set("q", params.q);
  const suffix = qs.toString() ? `?${qs}` : "";
  const rows = await request<Record<string, unknown>[]>(`/voxbox/messages${suffix}`);
  return rows.map(mapMessage);
}

export async function fetchMessage(id: string): Promise<MailMessage> {
  const raw = await request<Record<string, unknown>>(`/voxbox/messages/${id}`);
  return mapMessage(raw);
}

export async function patchMessage(
  id: string,
  patch: Partial<Pick<MailMessage, "unread" | "starred" | "important" | "folder">>,
): Promise<MailMessage> {
  const raw = await request<Record<string, unknown>>(`/voxbox/messages/${id}`, {
    method: "PATCH",
    body: patch,
  });
  return mapMessage(raw);
}

export async function sendMessage(
  id: string,
  body: { kind: "reply" | "forward"; body: string; to?: string },
): Promise<void> {
  await request(`/voxbox/messages/${id}/send`, { method: "POST", body });
}

export async function syncMail(): Promise<SyncResult> {
  return request<SyncResult>("/voxbox/sync", { method: "POST" });
}

export async function fetchKpi(accountId?: string): Promise<KpiData> {
  const qs =
    accountId && accountId !== "all" ? `?account_id=${encodeURIComponent(accountId)}` : "";
  return request<KpiData>(`/voxbox/kpi${qs}`);
}

export async function generateAiReply(body: {
  subject: string;
  from: string;
  body: string;
  tone: string;
  mode: "write" | "fix";
  draft: string;
}): Promise<AiReplyResult> {
  return request<AiReplyResult>("/voxbox/ai/reply", { method: "POST", body });
}
