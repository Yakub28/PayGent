// frontend/lib/api.ts
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
}

export interface Stats {
  total_volume_sats: number;
  total_fees_sats: number;
  total_calls: number;
  marketplace_balance_sats: number;
  top_rated_name: string | null;
  top_rated_tier: string | null;
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${BASE}/api/stats`, { cache: "no-store" });
  return res.json();
}

export async function fetchServices(): Promise<Service[]> {
  const res = await fetch(`${BASE}/api/services`, { cache: "no-store" });
  return res.json();
}

export async function fetchTransactions(): Promise<Transaction[]> {
  const res = await fetch(`${BASE}/api/transactions`, { cache: "no-store" });
  return res.json();
}
