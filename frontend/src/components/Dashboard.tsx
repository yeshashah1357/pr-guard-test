import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { api, SEVERITIES, type FindingPage, type Repository, type Severity, type TrendPoint, type User } from "../api";
import FindingsTable from "./FindingsTable";
import RunPanel from "./RunPanel";
import TrendChart from "./TrendChart";

const PAGE_SIZE = 25;

export default function Dashboard({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [repoId, setRepoId] = useState<number | undefined>();
  const [severity, setSeverity] = useState<Severity[]>([]);
  const [tool, setTool] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<FindingPage>({ items: [], total: 0 });
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [newRepo, setNewRepo] = useState("");
  const [openRun, setOpenRun] = useState<number | null>(null);
  const closeRun = useCallback(() => setOpenRun(null), []);

  useEffect(() => {
    api.repos().then(setRepos).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    api.trends(repoId).then(setTrend).catch((e) => setError(e.message));
  }, [repoId]);

  useEffect(() => {
    api
      .findings({ repoId, severity, tool: tool || undefined, limit: PAGE_SIZE, offset })
      .then(setPage)
      .catch((e) => setError(e.message));
  }, [repoId, severity, tool, offset]);

  const totals = useMemo(() => {
    const t: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0 };
    trend.forEach((p) => (t[p.severity] += p.count));
    return t;
  }, [trend]);

  function toggleSeverity(s: Severity) {
    setOffset(0);
    setSeverity((current) => (current.includes(s) ? current.filter((x) => x !== s) : [...current, s]));
  }

  async function addRepo(event: FormEvent) {
    event.preventDefault();
    try {
      const repo = await api.addRepo(newRepo.trim());
      setRepos((r) => [...r, repo].sort((a, b) => a.full_name.localeCompare(b.full_name)));
      setNewRepo("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add repository");
    }
  }

  return (
    <div className="shell">
      <header>
        <strong>PR Guard</strong>
        <span className="muted">
          {user.email} · {user.role}
        </span>
        <button className="link" onClick={onLogout}>
          Sign out
        </button>
      </header>

      {error && (
        <p className="error" onClick={() => setError(null)}>
          {error}
        </p>
      )}

      <section className="toolbar">
        <select
          value={repoId ?? ""}
          onChange={(e) => {
            setOffset(0);
            setRepoId(e.target.value ? Number(e.target.value) : undefined);
          }}
        >
          <option value="">All repositories</option>
          {repos.map((r) => (
            <option key={r.id} value={r.id}>
              {r.full_name}
            </option>
          ))}
        </select>
        {user.role === "admin" && (
          <form onSubmit={addRepo} className="inline">
            <input placeholder="owner/repo" value={newRepo} onChange={(e) => setNewRepo(e.target.value)} required />
            <button type="submit">Add repository</button>
          </form>
        )}
      </section>

      <section className="stats">
        {SEVERITIES.map((s) => (
          <div key={s} className="card stat">
            <span className={`badge sev-${s}`}>{s}</span>
            <span className="stat-value">{totals[s]}</span>
            <span className="muted">last 30 days</span>
          </div>
        ))}
      </section>

      <section className="card">
        <h2>Findings per day</h2>
        <TrendChart points={trend} />
      </section>

      <section className="card">
        <div className="filters">
          <h2>Findings</h2>
          {SEVERITIES.map((s) => (
            <label key={s} className="chip">
              <input type="checkbox" checked={severity.includes(s)} onChange={() => toggleSeverity(s)} />
              {s}
            </label>
          ))}
          <select
            value={tool}
            onChange={(e) => {
              setOffset(0);
              setTool(e.target.value);
            }}
          >
            <option value="">All tools</option>
            <option value="bandit">Bandit</option>
            <option value="ruff">Ruff</option>
            <option value="llm">LLM review</option>
          </select>
        </div>
        <FindingsTable findings={page.items} onOpenRun={setOpenRun} />
        <div className="pager">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
            Previous
          </button>
          <span className="muted">
            {page.total === 0 ? 0 : offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} of {page.total}
          </span>
          <button disabled={offset + PAGE_SIZE >= page.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
            Next
          </button>
        </div>
      </section>

      {openRun !== null && <RunPanel runId={openRun} onClose={closeRun} />}
    </div>
  );
}
