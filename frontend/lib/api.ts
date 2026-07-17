const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const TOKEN_KEY = "finmate_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string) {
  if (typeof window !== "undefined") localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  if (typeof window !== "undefined") localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function request(path: string, options: RequestInit = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders() },
    ...options,
  });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined" && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new Error("Not authenticated");
  }
  if (!res.ok) {
    let detail = `API error ${res.status}`;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

async function upload(path: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Not authenticated");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload error ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  // Auth
  signup: (name: string, email: string, password: string) =>
    request("/api/auth/signup", { method: "POST", body: JSON.stringify({ name, email, password }) }),
  login: (email: string, password: string) =>
    request("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  magicRequest: (email: string, name?: string) =>
    request("/api/auth/magic/request", { method: "POST", body: JSON.stringify({ email, name }) }),
  magicVerify: (token: string) =>
    request("/api/auth/magic/verify", { method: "POST", body: JSON.stringify({ token }) }),
  me: () => request("/api/auth/me"),
  joinWaitlist: (email: string) =>
    request("/api/waitlist", { method: "POST", body: JSON.stringify({ email }) }),

  // Financial Twin
  getSnapshot: () => request("/api/twin/snapshot"),
  getCashflowSeries: (months = 6) => request(`/api/twin/cashflow-series?months=${months}`),

  // Profile / Transactions
  getTransactions: (limit = 50) => request(`/api/profile/transactions?limit=${limit}`),
  addTransaction: (data: any) =>
    request("/api/profile/transactions", { method: "POST", body: JSON.stringify(data) }),
  getAssets: () => request("/api/profile/assets"),
  getLiabilities: () => request("/api/profile/liabilities"),
  getUser: () => request("/api/profile/user"),
  loadSample: () => request("/api/profile/load-sample", { method: "POST" }),

  // Goals
  getGoals: () => request("/api/goals/"),
  createGoal: (data: any) => request("/api/goals/", { method: "POST", body: JSON.stringify(data) }),
  getGoalPlan: (goalId: number) => request(`/api/goals/${goalId}/plan`),
  deleteGoal: (goalId: number) => request(`/api/goals/${goalId}`, { method: "DELETE" }),

  // AI CFO Chat
  sendChat: (message: string) =>
    request("/api/chat/", { method: "POST", body: JSON.stringify({ message }) }),
  getChatHistory: () => request("/api/chat/history"),

  // Scenario Simulator
  simulate: (data: any) => request("/api/simulate/", { method: "POST", body: JSON.stringify(data) }),

  // Insights
  getInsights: () => request("/api/insights/"),

  // Memory
  getMemoryTimeline: () => request("/api/memory/timeline"),
  getMemoryByType: (type: string) => request(`/api/memory/by-type/${type}`),

  // Upload
  uploadCSV: (file: File) => upload("/api/upload/csv", file),
  uploadPDF: (file: File) => upload("/api/upload/pdf", file),

  // Health
  getHealth: () => request("/api/health"),
};

export function formatINR(value: number, opts: { compact?: boolean } = {}): string {
  if (opts.compact && Math.abs(value) >= 100000) {
    return `₹${(value / 100000).toFixed(1)}L`;
  }
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}
