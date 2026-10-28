// Lines over time, drawn as SVG on the server. Each line ends in a dot and its name and
// latest value (direct labels, no legend box); thin rules mark events. Every point has
// a hover title. The only number the chart writes itself is the zero of its y axis,
// marked data-layout so the numbers check knows it.

export type Series = { name: string; points: { date: string; value: number }[]; tone: "main" | "second" };
export type Rule = { date: string; label: string };

const W = 720;
const H = 300;
const PAD = { left: 40, right: 140, top: 28, bottom: 28 };

const time = (d: string) => {
  const [y, m, day] = d.split("-").map(Number);
  return Date.UTC(y, (m || 1) - 1, day || 1);
};

function niceStep(max: number) {
  const raw = max / 4;
  const p = 10 ** Math.floor(Math.log10(raw || 1));
  return [1, 2, 5, 10].map((s) => s * p).find((s) => s >= raw) ?? raw;
}

export function LineChart({ series, rules, unit, format }: {
  series: Series[];
  rules: Rule[];
  unit: string;
  format: (v: number) => string;
}) {
  const all = series.flatMap((s) => s.points);
  if (all.length === 0) return <p className="muted">No editions yet.</p>;
  const t0 = Math.min(...all.map((p) => time(p.date)));
  const t1 = Math.max(...all.map((p) => time(p.date)));
  const vmax = Math.max(...all.map((p) => p.value)) * 1.1 || 1;
  const x = (d: string) => PAD.left + ((time(d) - t0) / (t1 - t0 || 1)) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - v / vmax) * (H - PAD.top - PAD.bottom);
  const step = niceStep(vmax);
  const ticks = Array.from({ length: Math.floor(vmax / step) + 1 }, (_, i) => i * step);
  // a year is labelled at its 1 January, so only years that start inside the chart
  const years = [...new Set(all.map((p) => p.date.slice(0, 4)))]
    .filter((yr) => time(`${yr}-01-01`) >= t0)
    .filter((_, i) => i % 2 === 0);

  return (
    <svg className="line-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${unit} over time`}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} className="grid" />
          {t === 0 ? (
            <text x={PAD.left - 6} y={y(t)} className="tick" textAnchor="end" dominantBaseline="middle" data-layout="">
              0
            </text>
          ) : (
            <text x={PAD.left - 6} y={y(t)} className="tick" textAnchor="end" dominantBaseline="middle">
              {format(t)}
            </text>
          )}
        </g>
      ))}
      {years.map((yr) => (
        <text key={yr} x={x(`${yr}-01-01`)} y={H - 8} className="tick" textAnchor="middle">
          {yr}
        </text>
      ))}
      {rules
        .filter((r) => time(r.date) >= t0 && time(r.date) <= t1)
        .map((r) => (
          <g key={r.label}>
            <line x1={x(r.date)} x2={x(r.date)} y1={PAD.top} y2={H - PAD.bottom} className="rule" />
            <text x={x(r.date)} y={PAD.top - 8} className="tick" textAnchor="middle">
              {r.label}
            </text>
          </g>
        ))}
      {series.map((s) => {
        const last = s.points[s.points.length - 1];
        if (!last) return null;
        return (
          <g key={s.name} className={`series ${s.tone}`}>
            <polyline points={s.points.map((p) => `${x(p.date)},${y(p.value)}`).join(" ")} />
            {s.points.map((p) => (
              <circle key={p.date} cx={x(p.date)} cy={y(p.value)} r={2.5}>
                <title>{`${s.name}, ${p.date}: ${format(p.value)}`}</title>
              </circle>
            ))}
            <circle cx={x(last.date)} cy={y(last.value)} r={5} className="end" />
            <text x={x(last.date) + 10} y={y(last.value)} dominantBaseline="middle" className="label">
              {`${s.name} ${format(last.value)}`}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
