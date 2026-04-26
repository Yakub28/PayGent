"use client";
import { useEffect, useState } from "react";
import {
  Agent,
  AgentRole,
  ServiceType,
  ServiceTypeInfo,
  fetchAgents,
  fetchServiceTypes,
  registerAgent,
  topupAgent,
  deleteAgent,
} from "@/lib/api";

const DEFAULT_MODEL = "claude-sonnet-4-5";
const FALLBACK_TYPES: ServiceTypeInfo[] = [
  {
    key: "code_writer",
    label: "Code Writer",
    description: "Writes a code snippet from a prompt.",
    default_price_sats: 15,
  },
  {
    key: "code_reviewer",
    label: "Code Reviewer",
    description: "Reviews code for bugs and quality.",
    default_price_sats: 25,
  },
  {
    key: "summarizer",
    label: "Summarizer",
    description: "Summarizes text in 3 sentences.",
    default_price_sats: 10,
  },
  {
    key: "sentiment",
    label: "Sentiment Analyzer",
    description: "Classifies text as positive / negative / neutral.",
    default_price_sats: 8,
  },
];

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [types, setTypes] = useState<ServiceTypeInfo[]>(FALLBACK_TYPES);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    name: "",
    role: "consumer" as AgentRole,
    model: DEFAULT_MODEL,
    system_prompt: "",
    initial_balance_sats: 100000,
    service_type: "code_writer" as ServiceType,
    service_price_sats: 15,
  });

  async function refresh() {
    try {
      setAgents(await fetchAgents());
    } catch {
      // ignore transient errors
    }
  }

  useEffect(() => {
    refresh();
    fetchServiceTypes()
      .then((t) => {
        if (t.length > 0) setTypes(t);
      })
      .catch(() => {});
    const i = setInterval(refresh, 3000);
    return () => clearInterval(i);
  }, []);

  // When the user picks a different service type, default the price to that type's default.
  useEffect(() => {
    const t = types.find((t) => t.key === form.service_type);
    if (t) setForm((f) => ({ ...f, service_price_sats: t.default_price_sats }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.service_type, types]);

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
        initial_balance_sats: Number(form.initial_balance_sats) || 0,
        service_type:
          form.role === "provider" ? form.service_type : null,
        service_price_sats:
          form.role === "provider" ? Number(form.service_price_sats) : null,
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
  const selectedType = types.find((t) => t.key === form.service_type);

  return (
    <main className="max-w-5xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-2">Agents</h1>
      <p className="text-gray-400 mb-6">
        Register consumer and provider agents. Each agent runs against its own
        Claude model identity. Provider agents auto-publish a service of the
        chosen type to the marketplace.
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
            <option value="consumer">Consumer (buys services)</option>
            <option value="provider">Provider (sells a service)</option>
          </select>
        </Field>

        <Field label="Claude model">
          <input
            value={form.model}
            onChange={(e) => setForm({ ...form, model: e.target.value })}
            placeholder="claude-sonnet-4-5"
            className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2"
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
          <Field label="Service type">
            <select
              value={form.service_type}
              onChange={(e) =>
                setForm({
                  ...form,
                  service_type: e.target.value as ServiceType,
                })
              }
              className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2"
            >
              {types.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
          </Field>
        )}

        <Field label="System prompt (optional)" full>
          <textarea
            value={form.system_prompt}
            onChange={(e) =>
              setForm({ ...form, system_prompt: e.target.value })
            }
            placeholder={
              form.role === "provider"
                ? `Default persona for ${
                    selectedType?.label ?? "this service"
                  }`
                : "Default: helper-needing engineer persona"
            }
            className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 h-20"
          />
        </Field>

        {form.role === "provider" && (
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

        {form.role === "provider" && selectedType && (
          <div className="md:col-span-2 text-xs text-gray-500">
            <span className="text-gray-400">{selectedType.label}:</span>{" "}
            {selectedType.description}
          </div>
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

      <Group title="Consumer agents" agents={consumers} types={types} onTopup={topup} onDelete={remove} />
      <Group title="Provider agents" agents={providers} types={types} onTopup={topup} onDelete={remove} />
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
  types,
  onTopup,
  onDelete,
}: {
  title: string;
  agents: Agent[];
  types: ServiceTypeInfo[];
  onTopup: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const labelFor = (key: string | null) =>
    types.find((t) => t.key === key)?.label ?? key ?? "—";

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
                  <div className="font-semibold flex items-center gap-2">
                    {a.name}
                    {a.service_type && (
                      <span className="text-[10px] uppercase tracking-wider bg-purple-900/60 text-purple-200 px-2 py-0.5 rounded">
                        {labelFor(a.service_type)}
                      </span>
                    )}
                  </div>
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
