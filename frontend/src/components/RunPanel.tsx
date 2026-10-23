import { useEffect, useState } from "react";
import { api, SEVERITIES, type RunDetail } from "../api";

const RANK = Object.fromEntries(SEVERITIES.map((s, i) => [s, i]));

export default function RunPanel({ runId, onClose }: { runId: number; onClose: () => void }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRun(null);
    api.run(runId).then(setRun).catch((e) => setError(e.message));
  }, [runId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const pr = run?.pull_request;
  const findings = run ? [...run.findings].sort((a, b) => RANK[a.severity] - RANK[b.severity] || a.line - b.line) : [];

  return (
    <div className="overlay" onClick={onClose}>
      <aside className="panel" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="panel-head">
          <div>
            <div className="muted">
              {pr ? `${pr.repository_name} #${pr.number} · by ${pr.author}` : "Loading…"}
            </div>
            <h2>{pr?.title ?? ""}</h2>
          </div>
          <button className="link" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        {error && <p className="error">{error}</p>}

        {run && pr && (
          <>
            <div className="meta">
              <span className={`status status-${run.status}`}>{run.status}</span>
              <span className="muted">
                commit <code>{run.head_sha.slice(0, 7)}</code>
              </span>
              {pr.html_url ? (
                <a href={pr.html_url} target="_blank" rel="noreferrer">
                  Open on GitHub ↗
                </a>
              ) : (
                <span className="muted">Demo pull request (not on GitHub)</span>
              )}
            </div>

            {run.notes && (
              <ul className="notes">
                {run.notes.split("\n").map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            )}
            {run.error && <p className="error">{run.error}</p>}

            <h3>
              {findings.length} finding{findings.length === 1 ? "" : "s"}
            </h3>
            {findings.map((f) => (
              <div key={f.id} className="finding">
                <div className="finding-head">
                  <span className={`badge sev-${f.severity}`}>{f.severity}</span>
                  <code>
                    {f.file_path}:{f.line}
                  </code>
                  <span className="muted">
                    {f.tool} · {f.rule_id}
                  </span>
                  {f.confidence && <span className={`confidence conf-${f.confidence}`}>{f.confidence} confidence</span>}
                </div>
                <div>{f.message}</div>
                {f.suggestion && <div className="muted">Fix: {f.suggestion}</div>}
              </div>
            ))}
          </>
        )}
      </aside>
    </div>
  );
}
