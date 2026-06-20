const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request(path: string, options: RequestInit = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
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
  uploadCSV: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/api/upload/csv`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Upload error ${res.status}: ${text}`);
    }
    return res.json();
  },
  uploadPDF: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/api/upload/pdf`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Upload error ${res.status}: ${text}`);
    }
    return res.json();
  },

  // Health
  getHealth: () => request("/api/health"),
};

export function formatINR(value: number, opts: { compact?: boolean } = {}): string {
  if (opts.compact && Math.abs(value) >= 100000) {
    return `₹${(value / 100000).toFixed(1)}L`;
  }
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}
