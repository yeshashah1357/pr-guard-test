import type { Finding } from "../api";

export default function FindingsTable({
  findings,
  onOpenRun,
}: {
  findings: Finding[];
  onOpenRun: (runId: number) => void;
}) {
  if (findings.length === 0) return <p className="muted">No findings match these filters.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Severity</th>
            <th>Finding</th>
            <th>Location</th>
            <th>Pull request</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f) => (
            <tr key={f.id}>
              <td>
                <span className={`badge sev-${f.severity}`}>{f.severity}</span>
              </td>
              <td>
                <div className="rule">
                  {f.tool} · <code>{f.rule_id}</code>
                  {f.confidence && <span className={`confidence conf-${f.confidence}`}>{f.confidence} confidence</span>}
                </div>
                <div>{f.message}</div>
                {f.suggestion && <div className="muted">Fix: {f.suggestion}</div>}
              </td>
              <td>
                <code>
                  {f.file_path}:{f.line}
                </code>
              </td>
              <td>
                <button className="link" onClick={() => onOpenRun(f.run_id)}>
                  {f.repository}#{f.pr_number}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
