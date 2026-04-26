"use client";
import { useEffect, useState } from "react";
import { fetchStats, fetchServices, fetchTransactions, Stats, Service, Transaction } from "@/lib/api";
import StatsBar from "@/components/StatsBar";
import ServiceCatalog from "@/components/ServiceCatalog";
import TransactionFeed from "@/components/TransactionFeed";

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);

  async function refresh() {
    try {
      const [s, svc, txns] = await Promise.all([
        fetchStats(),
        fetchServices(),
        fetchTransactions(),
      ]);
      setStats(s);
      setServices(svc);
      setTransactions(txns);
    } catch (_e) {
      // Backend not yet running — silently retry
    }
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <main className="p-8">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-white">PayGent Marketplace</h1>
            <p className="text-gray-400 mt-1">Lightning-powered agent services ⚡</p>
          </div>
          <div className="text-xs text-gray-600">auto-refreshes every 3s</div>
        </div>

        {stats ? (
          <StatsBar stats={stats} />
        ) : (
          <div className="grid grid-cols-4 gap-4 mb-8">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-center animate-pulse h-20" />
            ))}
          </div>
        )}

        <ServiceCatalog services={services} />
        <TransactionFeed transactions={transactions} />
      </div>
    </main>
  );
}
