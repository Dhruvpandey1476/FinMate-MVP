import type {
  Snapshot, CashflowPoint, Transaction, Goal, Insight, Memory, ChatMessage,
  Forecast, BudgetCategory, DebtPlan, Notification, PlanSummary,
  SimulationResult, RecurringItem, TraceStep, User,
  SafeToSpend, EarlyWarningResponse, TimeMachine, NextBestAction, CoreLoop,
} from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

/**
 * The backend this build talks to.
 *
 * NEXT_PUBLIC_* is inlined at BUILD time, not read at runtime - so changing it
 * in a hosting dashboard has no effect until the app is rebuilt. Exported so
 * the UI can show which backend it is actually calling when a request fails,
 * which is the single most common cause of "my deploy shows no changes".
 */
export const apiBaseUrl = API_BASE;
export const isLocalApi = /localhost|127\.0\.0\.1/.test(API_BASE);
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

/**
 * An API failure that carries its HTTP status.
 *
 * The UI needs to tell these apart: 402 means "upgrade", 429 means "slow down",
 * 409 means "already imported". The old client flattened everything to a bare
 * Error and every caller swallowed it with `.catch(() => {})`.
 */
export class ApiError extends Error {
  status: number;
  requestId?: string;

  constructor(message: string, status: number, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
  }

  get isQuotaExceeded() {
    return this.status === 402;
  }
  get isRateLimited() {
    return this.status === 429;
  }
  get isConflict() {
    return this.status === 409;
  }
}

function redirectToLogin() {
  clearToken();
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...authHeaders() },
      ...options,
    });
  } catch {
    // Network-level failure: the backend is down or unreachable.
    throw new ApiError(
      "Can't reach the FinMate server. Check your connection and try again.",
      0
    );
  }

  if (res.status === 401) {
    redirectToLogin();
    throw new ApiError("Your session has expired. Please sign in again.", 401);
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) detail = body.detail[0].msg;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status, res.headers.get("X-Request-ID") ?? undefined);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function upload<T>(path: string, file: File): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: authHeaders(),
      body: formData,
    });
  } catch {
    throw new ApiError("Can't reach the FinMate server. Check your connection.", 0);
  }

  if (res.status === 401) {
    redirectToLogin();
    throw new ApiError("Your session has expired. Please sign in again.", 401);
  }
  if (!res.ok) {
    let detail = `Upload failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export interface StreamHandlers {
  onTrace?: (step: TraceStep) => void;
  onToken?: (text: string) => void;
  onDone?: (reply: string, trace: TraceStep[]) => void;
  onError?: (error: ApiError) => void;
}

/**
 * Stream a CFO reply over SSE.
 *
 * Reasoning nodes arrive as they complete and the answer arrives token by
 * token, so the user sees progress instead of a 30-second spinner.
 * Returns an abort function.
 */
export function streamChat(message: string, handlers: StreamHandlers): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ message }),
        signal: controller.signal,
      });

      if (res.status === 401) {
        redirectToLogin();
        throw new ApiError("Your session has expired. Please sign in again.", 401);
      }
      if (!res.ok) {
        let detail = `Chat failed (${res.status})`;
        try {
          const body = await res.json();
          if (typeof body.detail === "string") detail = body.detail;
        } catch {
          /* ignore */
        }
        throw new ApiError(detail, res.status);
      }
      if (!res.body) throw new ApiError("Streaming is not supported by this browser.", 0);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      // SSE frames are separated by a blank line; a chunk can split one in half.
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          const line = frame.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          try {
            const evt = JSON.parse(line.slice(5).trim());
            if (evt.type === "trace") handlers.onTrace?.(evt.step);
            else if (evt.type === "token") handlers.onToken?.(evt.text);
            else if (evt.type === "done") handlers.onDone?.(evt.reply, evt.trace ?? []);
            else if (evt.type === "error") {
              handlers.onError?.(new ApiError(evt.detail ?? "The agent hit an error.", 500));
            }
          } catch {
            /* skip a malformed frame rather than killing the stream */
          }
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      handlers.onError?.(
        err instanceof ApiError
          ? err
          : new ApiError("Can't reach the FinMate server.", 0)
      );
    }
  })();

  return () => controller.abort();
}

export const api = {
  // Auth
  signup: (name: string, email: string, password: string) =>
    request<{ token: string; user: Record<string, unknown> }>("/api/auth/signup", {
      method: "POST", body: JSON.stringify({ name, email, password }),
    }),
  login: (email: string, password: string) =>
    request<{ token: string; user: Record<string, unknown> }>("/api/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    }),
  magicRequest: (email: string, name?: string) =>
    request<{ sent: boolean; email: string; dev_link?: string }>("/api/auth/magic/request", {
      method: "POST", body: JSON.stringify({ email, name }),
    }),
  magicVerify: (token: string) =>
    request<{ token: string; user: Record<string, unknown> }>("/api/auth/magic/verify", {
      method: "POST", body: JSON.stringify({ token }),
    }),
  me: () => request<User>("/api/auth/me"),
  logoutAll: () => request<{ ok: boolean; token: string }>("/api/auth/logout-all", { method: "POST" }),
  getPlan: () => request<PlanSummary>("/api/auth/plan"),
  getPlans: () => request<Record<string, unknown>[]>("/api/auth/plans"),
  joinWaitlist: (email: string) =>
    request<{ ok: boolean; message: string }>("/api/waitlist", {
      method: "POST", body: JSON.stringify({ email }),
    }),

  // Financial Twin
  getSnapshot: () => request<Snapshot>("/api/twin/snapshot"),
  getCashflowSeries: (months = 6) =>
    request<CashflowPoint[]>(`/api/twin/cashflow-series?months=${months}`),

  // Profile / Transactions
  getTransactions: (limit = 50, offset = 0) =>
    request<Transaction[]>(`/api/profile/transactions?limit=${limit}&offset=${offset}`),
  countTransactions: () => request<{ total: number }>("/api/profile/transactions/count"),
  addTransaction: (data: Partial<Transaction>, allowDuplicate = false) =>
    request<Transaction>(
      `/api/profile/transactions?allow_duplicate=${allowDuplicate}`,
      { method: "POST", body: JSON.stringify(data) }
    ),
  deleteTransaction: (id: number) =>
    request<{ ok: boolean }>(`/api/profile/transactions/${id}`, { method: "DELETE" }),

  getAssets: () => request<{ id: number; name: string; asset_type: string; value: number }[]>("/api/profile/assets"),
  addAsset: (data: { name: string; asset_type: string; value: number }) =>
    request("/api/profile/assets", { method: "POST", body: JSON.stringify(data) }),
  deleteAsset: (id: number) => request(`/api/profile/assets/${id}`, { method: "DELETE" }),

  getLiabilities: () =>
    request<{ id: number; name: string; liability_type: string; amount: number;
              interest_rate: number; monthly_payment: number }[]>("/api/profile/liabilities"),
  addLiability: (data: {
    name: string; liability_type: string; amount: number;
    interest_rate: number; monthly_payment: number;
  }) => request("/api/profile/liabilities", { method: "POST", body: JSON.stringify(data) }),
  deleteLiability: (id: number) => request(`/api/profile/liabilities/${id}`, { method: "DELETE" }),

  getUser: () => request<User>("/api/profile/user"),
  updateUser: (data: Partial<User>) =>
    request("/api/profile/user", { method: "PATCH", body: JSON.stringify(data) }),
  loadSample: () => request<{ message: string; loaded: boolean }>("/api/profile/load-sample", { method: "POST" }),
  onboard: (data: Record<string, unknown>) =>
    request<{ ok: boolean }>("/api/profile/onboard", { method: "POST", body: JSON.stringify(data) }),
  deleteAccount: () => request<{ ok: boolean }>("/api/profile/account", { method: "DELETE" }),

  // Goals
  getGoals: () => request<Goal[]>("/api/goals/"),
  createGoal: (data: Partial<Goal>) =>
    request<Goal>("/api/goals/", { method: "POST", body: JSON.stringify(data) }),
  updateGoal: (id: number, data: Partial<Goal>) =>
    request<Goal>(`/api/goals/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  getGoalPlan: (goalId: number) => request<Record<string, unknown>>(`/api/goals/${goalId}/plan`),
  deleteGoal: (goalId: number) => request<{ ok: boolean }>(`/api/goals/${goalId}`, { method: "DELETE" }),

  // AI CFO Chat
  sendChat: (message: string) =>
    request<{ reply: string; reasoning_trace: TraceStep[] }>("/api/chat/", {
      method: "POST", body: JSON.stringify({ message }),
    }),
  getChatHistory: (limit = 100) => request<ChatMessage[]>(`/api/chat/history?limit=${limit}`),
  clearChatHistory: () => request<{ ok: boolean }>("/api/chat/history", { method: "DELETE" }),

  // Scenario Simulator
  simulate: (data: Record<string, unknown>) =>
    request<SimulationResult>("/api/simulate/", { method: "POST", body: JSON.stringify(data) }),

  // Insights
  getInsights: (refresh = false) => request<Insight[]>(`/api/insights/?refresh=${refresh}`),

  // Cash-flow forecast
  getForecast: (days = 90) => request<Forecast>(`/api/forecast/?days=${days}`),
  getRecurring: () =>
    request<{ expenses: RecurringItem[]; income: Record<string, unknown>[] }>("/api/forecast/recurring"),
  getBudget: () => request<BudgetCategory[]>("/api/forecast/budget"),

  // Debt optimizer
  getDebtPlan: (extraMonthly = 0, strategy = "avalanche") =>
    request<DebtPlan>(`/api/debt/plan?extra_monthly=${extraMonthly}&strategy=${strategy}`),
  getPrepayVsInvest: (amount: number, annualReturn = 0.1, liabilityId?: number) =>
    request<Record<string, unknown>>(
      `/api/debt/prepay-vs-invest?amount=${amount}&annual_return=${annualReturn}` +
      (liabilityId ? `&liability_id=${liabilityId}` : "")
    ),
  getAmortization: (liabilityId: number, extraMonthly = 0) =>
    request<Record<string, unknown>>(`/api/debt/amortize/${liabilityId}?extra_monthly=${extraMonthly}`),

  // Memory
  getMemoryTimeline: (limit = 200, offset = 0) =>
    request<Memory[]>(`/api/memory/timeline?limit=${limit}&offset=${offset}`),
  getMemoryByType: (type: string) => request<Memory[]>(`/api/memory/by-type/${type}`),
  createMemory: (data: { memory_type: string; content: string; importance?: number }) =>
    request<Memory>("/api/memory/", { method: "POST", body: JSON.stringify(data) }),
  updateMemory: (id: number, data: Partial<Memory>) =>
    request<Memory>(`/api/memory/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteMemory: (id: number) => request<{ ok: boolean }>(`/api/memory/${id}`, { method: "DELETE" }),

  // Notifications
  getNotifications: (unreadOnly = false) =>
    request<Notification[]>(`/api/notifications?unread_only=${unreadOnly}`),
  refreshNotifications: () =>
    request<Notification[]>("/api/notifications/refresh", { method: "POST" }),
  markNotificationsRead: (id?: number) =>
    request<{ updated: number }>(
      `/api/notifications/read${id ? `?notification_id=${id}` : ""}`, { method: "POST" }
    ),

  // Upload
  uploadCSV: (file: File) =>
    upload<{ message: string; total_parsed: number; total_inserted: number;
             duplicates_skipped: number; transactions: Partial<Transaction>[] }>("/api/upload/csv", file),
  uploadPDF: (file: File) =>
    upload<{ message: string; total_parsed: number; total_inserted: number;
             duplicates_skipped: number; transactions: Partial<Transaction>[] }>("/api/upload/pdf", file),
  getDuplicates: () =>
    request<{ duplicate_groups: number; extra_rows: number }>("/api/upload/duplicates"),

  // Tier 1 Core Loop
  getCoreLoop: () => request<CoreLoop>("/api/dashboard/core"),
  getSafeToSpend: (horizonDays = 14) =>
    request<SafeToSpend>(`/api/safe-to-spend?horizon_days=${horizonDays}`),
  getBalanceCheckpoint: () =>
    request<{ exists: boolean; balance?: number; as_of?: string; stale_days?: number }>(
      "/api/balance-checkpoint"
    ),
  addBalanceCheckpoint: (balance: number, note?: string) =>
    request<{ ok: boolean; safe_to_spend: SafeToSpend }>("/api/balance-checkpoint", {
      method: "POST", body: JSON.stringify({ balance, note }),
    }),
  getEarlyWarning: () => request<EarlyWarningResponse>("/api/early-warning"),
  getTimeMachine: (months = 12) => request<TimeMachine>(`/api/time-machine?months=${months}`),
  runTimeMachine: (data: { months: number; what_if_amount?: number; what_if_monthly?: number }) =>
    request<TimeMachine>("/api/time-machine", { method: "POST", body: JSON.stringify(data) }),
  getNextBestAction: (refresh = false) =>
    request<NextBestAction>(`/api/next-best-action?refresh=${refresh}`),

  // Health
  getHealth: () => request<Record<string, unknown>>("/api/health"),
};

export function formatINR(value: number, opts: { compact?: boolean } = {}): string {
  if (!Number.isFinite(value)) return "₹0";
  if (opts.compact && Math.abs(value) >= 10000000) {
    return `₹${(value / 10000000).toFixed(1)}Cr`;
  }
  if (opts.compact && Math.abs(value) >= 100000) {
    return `₹${(value / 100000).toFixed(1)}L`;
  }
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-IN", {
      day: "numeric", month: "short", year: "numeric",
    });
  } catch {
    return iso;
  }
}
