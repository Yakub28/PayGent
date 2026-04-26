"use client";
import { useEffect, useRef, useState } from "react";
import {
  fetchSimulationStatus,
  fetchSimulationEvents,
  startSimulation,
  stopSimulation,
  SimulationStatus,
  SimulationEvent,
} from "@/lib/api";

export default function SimulationPage() {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [events, setEvents] = useState<SimulationEvent[]>([]);
  const [rate, setRate] = useState(2);
  const [useLLM, setUseLLM] = useState(true);
  const [languages, setLanguages] = useState("python, typescript, go");
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function refresh() {
    try {
      const [s, e] = await Promise.all([
        fetchSimulationStatus(),
        fetchSimulationEvents(50),
      ]);
      setStatus(s);
      setEvents(e);
    } catch {
      // ignore transient errors
    }
  }

  useEffect(() => {
    refresh();
    intervalRef.current = setInterval(refresh, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  async function start() {
    setError(null);
    try {
      await startSimulation({
        rate_per_sec: rate,
        use_llm: useLLM,
        languages: languages
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function stop() {
    await stopSimulation();
    await refresh();
  }

  const successRate =
    status && status.iterations > 0
      ? Math.round((status.successes / status.iterations) * 100)
      : null;

  return (
    <main className="max-w-5xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-2">High-Frequency Simulation</h1>
      <p className="text-gray-400 mb-6">
        Drives consumer agents to repeatedly buy code-writing services from
        provider agents. Each call: 402 → mock invoice → instant payment →
        retry → fee split. Pure plumbing stress-test for the Lightning flow.
      </p>

      <div className="grid md:grid-cols-2 gap-4 mb-6">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-sm text-gray-400 mb-3">Configuration</div>
          <label className="block text-sm mb-3">
            <span className="text-gray-400">Rate (calls per second)</span>
            <input
              type="number"
              min={0.1}
              step={0.1}
              value={rate}
              onChange={(e) => setRate(Number(e.target.value))}
              className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 mt-1"
            />
          </label>
          <label className="block text-sm mb-3">
            <span className="text-gray-400">Languages (comma separated)</span>
            <input
              value={languages}
              onChange={(e) => setLanguages(e.target.value)}
              className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 mt-1"
            />
          </label>
          <label className="flex items-center gap-2 text-sm mb-4">
            <input
              type="checkbox"
              checked={useLLM}
              onChange={(e) => setUseLLM(e.target.checked)}
            />
            <span>Use consumer LLM to invent prompts (slower, more realistic)</span>
          </label>
          <div className="flex gap-2">
            {!status?.running ? (
              <button
                onClick={start}
                className="bg-purple-600 hover:bg-purple-500 px-4 py-2 rounded font-medium"
              >
                Start
              </button>
            ) : (
              <button
                onClick={stop}
                className="bg-red-600 hover:bg-red-500 px-4 py-2 rounded font-medium"
              >
                Stop
              </button>
            )}
          </div>
          {error && <div className="text-red-400 text-sm mt-3">{error}</div>}
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="text-sm text-gray-400 mb-3">Live status</div>
          <Stat label="Running" value={status?.running ? "yes" : "no"} highlight={status?.running} />
          <Stat label="Iterations" value={status?.iterations.toString() ?? "0"} />
          <Stat label="Successes" value={status?.successes.toString() ?? "0"} />
          <Stat label="Failures" value={status?.failures.toString() ?? "0"} />
          <Stat
            label="Success rate"
            value={successRate === null ? "—" : `${successRate}%`}
          />
          <Stat label="Last event" value={status?.last_event ?? "—"} mono />
        </div>
      </div>

      <h2 className="text-xl font-semibold mb-3">Recent transactions</h2>
      <div className="space-y-2">
        {events.length === 0 ? (
          <div className="text-gray-500 text-sm">no events yet</div>
        ) : (
          events.map((e, i) => (
            <div
              key={`${e.timestamp}-${i}`}
              className={`bg-gray-900 border rounded-xl p-4 ${
                e.success ? "border-gray-800" : "border-red-900"
              }`}
            >
              <div className="flex items-center justify-between text-sm">
                <div>
                  <span className="text-gray-400">{e.consumer_name}</span>
                  <span className="text-gray-600 mx-2">→</span>
                  <span className="text-gray-400">{e.provider_name}</span>
                  <span className="ml-3 text-purple-400 text-xs">
                    {e.language}
                  </span>
                </div>
                <div className="text-xs text-gray-500">
                  {e.duration_ms} ms · {e.sats_paid} sat
                </div>
              </div>
              <div className="mt-2 text-sm text-gray-300">{e.prompt}</div>
              {e.code && (
                <pre className="mt-2 bg-black/40 border border-gray-800 rounded p-2 text-xs overflow-x-auto text-green-300 max-h-40">
                  {e.code}
                </pre>
              )}
              {e.error && (
                <div className="mt-2 text-xs text-red-400 font-mono">
                  {e.error}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </main>
  );
}

function Stat({
  label,
  value,
  highlight,
  mono,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between text-sm py-1">
      <span className="text-gray-500">{label}</span>
      <span
        className={`${mono ? "font-mono text-xs" : ""} ${
          highlight ? "text-green-400" : "text-white"
        }`}
      >
        {value}
      </span>
    </div>
  );
}
