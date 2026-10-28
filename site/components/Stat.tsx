// A headline number with what it counts underneath.
export function Stat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="card stat">
      <p className="muted stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      <p className="muted stat-detail">{detail}</p>
    </div>
  );
}
