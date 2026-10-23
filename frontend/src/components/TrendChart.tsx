import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SEVERITIES, type TrendPoint } from "../api";

export const SEVERITY_COLORS = {
  critical: "var(--sev-critical)",
  high: "var(--sev-high)",
  medium: "var(--sev-medium)",
  low: "var(--sev-low)",
};

export default function TrendChart({ points }: { points: TrendPoint[] }) {
  // Pivot [{day, severity, count}] into one row per day for a stacked bar.
  const rows = useMemo(() => {
    const byDay = new Map<string, Record<string, number | string>>();
    for (const p of points) {
      const row = byDay.get(p.day) ?? { day: p.day };
      row[p.severity] = p.count;
      byDay.set(p.day, row);
    }
    return [...byDay.values()];
  }, [points]);

  if (rows.length === 0) return <p className="muted">No findings in this period.</p>;

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="day" tick={{ fontSize: 12, fill: "var(--muted)" }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "var(--muted)" }} />
        <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }} />
        <Legend />
        {[...SEVERITIES].reverse().map((s) => (
          <Bar key={s} dataKey={s} stackId="sev" fill={SEVERITY_COLORS[s]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
