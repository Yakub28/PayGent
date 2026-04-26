// frontend/lib/api.ts
const getBaseUrl = () => {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined") return ""; // Relative path for browser
  return "http://localhost:8000"; // Fallback for SSR
};

const BASE = getBaseUrl();

export interface Service {
  id: string;
  name: string;
  description: string;
  price_sats: number;
  tier: string;
  avg_quality_score: number | null;
  success_rate: number;
  call_count: number;
  price_adjusted: boolean;
  provider_agent_id: string | null;
  service_type: string | null;
  company_name: string | null;
  is_verified: boolean;
}

export interface Transaction {
  id: string;
  service_id: string;
  service_name: string | null;
  payment_hash: string;
  amount_sats: number;
  fee_sats: number | null;
  provider_sats: number | null;
  status: string;
  created_at: string;
  quality_score: number | null;
  score_reason: string | null;
  consumer_agent_id: string | null;
}

export interface Stats {
  total_volume_sats: number;
  total_fees_sats: number;
  total_calls: number;
  marketplace_balance_sats: number;
  top_rated_name: string | null;
  top_rated_tier: string | null;
}

export type AgentRole = "consumer" | "provider";
export type ServiceType =
  | "code_writer"
  | "code_reviewer"
  | "summarizer"
  | "sentiment";

export interface Agent {
  id: string;
  name: string;
  role: AgentRole;
  model: string;
  system_prompt: string | null;
  service_type: ServiceType | null;
  balance_sats: number;
  created_at: string;
  is_active: boolean;
  service_id: string | null;
}

export interface ServiceTypeInfo {
  key: ServiceType;
  label: string;
  description: string;
  default_price_sats: number;
}

export interface RegisterAgentPayload {
  name: string;
  role: AgentRole;
  model?: string;
  system_prompt?: string | null;
  initial_balance_sats?: number;
  service_type?: ServiceType | null;
  service_price_sats?: number | null;
}

export interface SimulationConfig {
  rate_per_sec: number;
  use_llm: boolean;
  max_iterations?: number | null;
}

export interface SimulationStatus {
  running: boolean;
  rate_per_sec: number;
  iterations: number;
  successes: number;
  failures: number;
  started_at: string | null;
  last_event: string | null;
  use_llm: boolean;
}

export interface SimulationEvent {
  timestamp: string;
  consumer_agent_id: string;
  consumer_name: string;
  provider_agent_id: string;
  provider_name: string;
  service_type: string;
  prompt: string;
  result_text: string | null;
  sats_paid: number;
  duration_ms: number;
  success: boolean;
  error: string | null;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  return res.json();
}

export const fetchStats = () => getJson<Stats>("/api/stats");
export const fetchServices = () => getJson<Service[]>("/api/services");
export const fetchTransactions = () => getJson<Transaction[]>("/api/transactions");

export const fetchAgents = () => getJson<Agent[]>("/api/agents");
export const fetchServiceTypes = () =>
  getJson<ServiceTypeInfo[]>("/api/service-types");
export const registerAgent = (payload: RegisterAgentPayload) =>
  postJson<Agent>("/api/agents", payload);
export const topupAgent = (id: string, amount_sats: number) =>
  postJson<Agent>(`/api/agents/${id}/topup`, { amount_sats });
export async function deleteAgent(id: string): Promise<void> {
  await fetch(`${BASE}/api/agents/${id}`, { method: "DELETE" });
}

export const fetchSimulationStatus = () =>
  getJson<SimulationStatus>("/api/simulation/status");
export const fetchSimulationEvents = (limit = 50) =>
  getJson<SimulationEvent[]>(`/api/simulation/events?limit=${limit}`);
export const startSimulation = (cfg: SimulationConfig) =>
  postJson<SimulationStatus>("/api/simulation/start", cfg);
export const stopSimulation = () =>
  postJson<SimulationStatus>("/api/simulation/stop", {});
