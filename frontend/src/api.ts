export type Alert = {
  type: "sales_drop" | "void_refund_spike" | string;
  severity: "high" | "medium" | string;
  message: string;
  last_hour_sales?: number;
  prior_hour_sales?: number;
  baseline_sales?: number;
  void_refund_count?: number;
  transaction_count?: number;
};

export type VenueRow = {
  venue_id: number;
  code: string;
  name: string;
  city: string;
  venue_type: string;
  sales_today: number;
  sale_count: number;
  void_refund_count: number;
  transaction_count: number;
  alerts: Alert[];
};

export type TopItem = {
  item_id: string;
  name: string;
  qty: number;
  revenue: number;
};

export type DashboardData = {
  as_of: string;
  day_start: string;
  total_sales: number;
  venue_count: number;
  alert_count: number;
  sale_count: number;
  void_refund_count: number;
  venues: VenueRow[];
  top_items: TopItem[];
};

export type VenueDetail = {
  venue_id: number;
  code: string;
  name: string;
  city: string;
  venue_type: string;
  sales_today: number;
  alerts: Alert[];
  hourly_trade: { hour: string; sales: number; count: number; baseline?: number | null }[];
  top_items: TopItem[];
  as_of: string;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export function getToken(): string | null {
  return localStorage.getItem("ops_token");
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem("ops_token", token);
  else localStorage.removeItem("ops_token");
}

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Token ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    setToken(null);
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

/** DRF ObtainAuthToken — returns `{ token }` only. */
export function login(username: string, password: string) {
  return api<{ token: string }>("/api/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function fetchDashboard() {
  return api<DashboardData>("/api/dashboard/");
}

export function fetchVenue(venueId: number) {
  return api<VenueDetail>(`/api/venues/${venueId}/`);
}

export function acknowledgeAlert(venueId: number, alertType: string, note = "") {
  return api<{ venue_id: number; alert_type: string; expires_at: string }>(
    `/api/venues/${venueId}/ack/`,
    {
      method: "POST",
      body: JSON.stringify({ alert_type: alertType, note }),
    }
  );
}

export function streamUrl(): string {
  const token = getToken();
  return `${API_BASE}/api/stream/?token=${encodeURIComponent(token ?? "")}`;
}

export function money(n: number): string {
  return n.toLocaleString("en-AU", { style: "currency", currency: "AUD" });
}
