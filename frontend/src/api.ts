export type Severity = "low" | "medium" | "high" | "critical";
export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];

export interface User {
  id: number;
  email: string;
  role: "viewer" | "reviewer" | "admin";
}

export interface Repository {
  id: number;
  full_name: string;
  is_active: boolean;
  last_event_at: string | null;
}

export interface RepositoryCheck {
  full_name: string;
  found: boolean;
  private: boolean | null;
  already_registered: boolean;
  message: string;
}

export interface WebhookSetup {
  webhook_url: string | null;
  content_type: string;
  events: string[];
  secret_location: string;
}

export interface Finding {
  id: number;
  run_id: number;
  tool: string;
  rule_id: string;
  severity: Severity;
  file_path: string;
  line: number;
  message: string;
  suggestion: string | null;
  confidence: "low" | "medium" | "high" | null;
  created_at: string;
  repository: string;
  pr_number: number;
  pr_url: string;
}

export interface FindingPage {
  items: Finding[];
  total: number;
}

export interface RunDetail {
  id: number;
  head_sha: string;
  status: "queued" | "running" | "completed" | "failed";
  notes: string | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  pull_request: {
    id: number;
    number: number;
    title: string;
    author: string;
    html_url: string;
    repository_name: string;
  };
  findings: Omit<Finding, "repository" | "pr_number" | "pr_url">[];
}

export interface TrendPoint {
  day: string;
  severity: Severity;
  count: number;
}

const TOKEN_KEY = "prguard.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage unavailable (private mode): the session just won't survive a reload.
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`/api${path}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : response.statusText;
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  async login(email: string, password: string): Promise<void> {
    const form = new URLSearchParams({ username: email, password });
    const { access_token } = await request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: form,
    });
    setToken(access_token);
  },
  register: (email: string, password: string) =>
    request<User>("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>("/auth/me"),
  repos: () => request<Repository[]>("/repos"),
  addRepo: (full_name: string) =>
    request<Repository>("/repos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name }),
    }),
  checkRepo: (full_name: string) =>
    request<RepositoryCheck>("/repos/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name }),
    }),
  webhookSetup: () => request<WebhookSetup>("/repos/setup"),
  findings(params: { repoId?: number; severity: Severity[]; tool?: string; limit: number; offset: number }) {
    const query = new URLSearchParams({ limit: String(params.limit), offset: String(params.offset) });
    if (params.repoId) query.set("repo_id", String(params.repoId));
    if (params.tool) query.set("tool", params.tool);
    params.severity.forEach((s) => query.append("severity", s));
    return request<FindingPage>(`/findings?${query}`);
  },
  run: (id: number) => request<RunDetail>(`/runs/${id}`),
  trends(repoId?: number, days = 30) {
    const query = new URLSearchParams({ days: String(days) });
    if (repoId) query.set("repo_id", String(repoId));
    return request<TrendPoint[]>(`/stats/trends?${query}`);
  },
};
