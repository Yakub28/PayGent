"use client";
import { useEffect, useState } from "react";
import {
  Agent,
  AgentRole,
  fetchAgents,
  registerAgent,
  topupAgent,
  deleteAgent,
} from "@/lib/api";

const DEFAULT_MODEL = "llama3.1";

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    name: "",
    role: "consumer" as AgentRole,
    model: DEFAULT_MODEL,
    system_prompt: "",
    ollama_base_url: "",
    initial_balance_sats: 100000,
    service_price_sats: 20,
    languages: "python, typescript, go",
  });

  async function refresh() {
    try {
      setAgents(await fetchAgents());
    } catch (e) {
      // ignore
    }
  }

  useEffect(() => {
    refresh();
    const i = setInterval(refresh, 3000);
    return () => clearInterval(i);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await registerAgent({
        name: form.name.trim(),
        role: form.role,
        model: form.model.trim() || DEFAULT_MODEL,
        system_prompt: form.system_prompt.trim() || null,
        ollama_base_url: form.ollama_base_url.trim() || null,
        initial_balance_sats: Number(form.initial_balance_sats) || 0,
        service_price_sats: Number(form.service_price_sats) || 20,
        languages: form.languages
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      setForm({ ...form, name: "", system_prompt: "" });
      await refresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function topup(id: string) {
    const amount = Number(prompt("Top up by how many sats?", "10000"));
    if (!amount || amount <= 0) return;
    await topupAgent(id, amount);
    await refresh();
  }

  async function remove(id: string) {
    if (!confirm("Deactivate this agent?")) return;
    await deleteAgent(id);
    await refresh();
  }

  const consumers = agents.filter((a) => a.role === "consumer");
  const providers = agents.filter((a) => a.role === "provider");

  return (
    <main className="max-w-5xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-2">Agents</h1>
      <p className="text-gray-400 mb-6">
        Register consumer and provider agents. Each agent runs against its own
        Ollama model identity. Provider agents auto-publish a Code Writer
        service to the marketplace.
      </p>

      <form
        onSubmit={submit}
        className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-8 grid gap-3 md:grid-cols-2"
      >
        <Field label="Name">
          <input
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g. Codex-Provider-1"
            className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2"
          />
        </Field>

        <Field label="Role">
          <select
            value={form.role}
            onChange={(e) =>
              setForm({ ...form, role: e.target.value as AgentRole })
            }
            className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2"
          >
            <option value="consumer">Consumer (buys code)</option>
            <option value="provider">Provider (writes code)</option>
          </select>
        </Field>

        <Field label="Ollama model">
          <input
            value={form.model}
            onChange={(e) => setForm({ ...form, model: e.target.value })}
            placeholder="llama3.1"
            className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2"
          />
        </Field>

        <Field label="Ollama base URL (optional)">
          <input
            value={form.ollama_base_url}
            onChange={(e) =>
              setForm({ ...form, ollama_base_url: e.target.value })
            }
            placeholder="leave blank to use server default"
            className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2"
          />
        </Field>

        <Field label="System prompt (optional)" full>
          <textarea
            value={form.system_prompt}
            onChange={(e) =>
              setForm({ ...form, system_prompt: e.target.value })
            }
            placeholder={
              form.role === "provider"
                ? "Default: senior-engineer code-only persona"
                : "Default: helper-needing engineer persona"
            }
            className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 h-20"
          />
        </Field>

        {form.role === "consumer" ? (
          <Field label="Initial balance (sats)">
            <input
              type="number"
              value={form.initial_balance_sats}
              onChange={(e) =>
                setForm({
                  ...form,
                  initial_balance_sats: Number(e.target.value),
                })
              }
              className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2"
            />
          </Field>
        ) : (
          <Field label="Service price per call (sats)">
            <input
              type="number"
              value={form.service_price_sats}
              onChange={(e) =>
                setForm({
                  ...form,
                  service_price_sats: Number(e.target.value),
                })
              }
              className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2"
            />
          </Field>
        )}

        {form.role === "provider" && (
          <Field label="Languages (comma separated)">
            <input
              value={form.languages}
              onChange={(e) => setForm({ ...form, languages: e.target.value })}
              className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2"
            />
          </Field>
        )}

        {error && (
          <div className="md:col-span-2 text-red-400 text-sm">{error}</div>
        )}
        <div className="md:col-span-2">
          <button
            type="submit"
            disabled={loading}
            className="bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-medium px-4 py-2 rounded"
          >
            {loading ? "Registering…" : "Register agent"}
          </button>
        </div>
      </form>

      <Group title="Consumer agents" agents={consumers} onTopup={topup} onDelete={remove} />
      <Group title="Provider agents" agents={providers} onTopup={topup} onDelete={remove} />
    </main>
  );
}

function Field({
  label,
  children,
  full,
}: {
  label: string;
  children: React.ReactNode;
  full?: boolean;
}) {
  return (
    <label className={`text-sm ${full ? "md:col-span-2" : ""}`}>
      <span className="block text-gray-400 mb-1">{label}</span>
      {children}
    </label>
  );
}

function Group({
  title,
  agents,
  onTopup,
  onDelete,
}: {
  title: string;
  agents: Agent[];
  onTopup: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <section className="mb-8">
      <h2 className="text-xl font-semibold mb-3">
        {title}{" "}
        <span className="text-gray-500 text-sm">({agents.length})</span>
      </h2>
      {agents.length === 0 ? (
        <div className="text-gray-500 text-sm">none yet</div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {agents.map((a) => (
            <div
              key={a.id}
              className="bg-gray-900 border border-gray-800 rounded-xl p-4"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-semibold">{a.name}</div>
                  <div className="text-xs text-gray-500">
                    {a.id.slice(0, 8)} · {a.model}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-purple-400 font-mono">
                    {a.balance_sats.toLocaleString()} sat
                  </div>
                </div>
              </div>
              {a.service_id && (
                <div className="mt-2 text-xs text-gray-400">
                  service: <span className="font-mono">{a.service_id.slice(0, 8)}</span>
                </div>
              )}
              {a.system_prompt && (
                <div className="mt-2 text-xs text-gray-500 line-clamp-2">
                  “{a.system_prompt}”
                </div>
              )}
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => onTopup(a.id)}
                  className="text-xs bg-gray-800 hover:bg-gray-700 px-2 py-1 rounded"
                >
                  Top up
                </button>
                <button
                  onClick={() => onDelete(a.id)}
                  className="text-xs text-red-400 hover:text-red-300 ml-auto"
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
