import { TableScroll } from "@/components/TableScroll";

export type Bar = { label: string; value: number | null; text: string; note?: string };

// Horizontal bars, one colour, the value written at the end of each bar (CHARTS.md:
// direct labels, title states the finding, footer names the source). A bar with no
// value prints its note instead. The same rows are underneath as a table.
export function BarChart({ id, title, subtitle, footer, bars, valueHeading, scaleMax }: {
  id?: string;
  title: string;
  subtitle: string;
  footer: string;
  bars: Bar[];
  valueHeading: string;
  scaleMax?: number; // shares are drawn against 1 (100%), not against the largest bar
}) {
  const max = scaleMax ?? (Math.max(...bars.map((b) => b.value ?? 0)) || 1);
  return (
    <figure className="card chart bar-chart" id={id}>
      <figcaption>
        <h3>{title}</h3>
        <p className="muted">{subtitle}</p>
      </figcaption>
      <ul className="bars">
        {bars.map((b) => (
          <li key={b.label} title={`${b.label}: ${b.note ?? b.text}`}>
            <span className="bar-label">{b.label}</span>
            <span className="bar-track">
              {b.value !== null && (
                <span className="bar" style={{ width: `${(b.value / max) * 100}%` }} />
              )}
              <span className="bar-value">{b.value === null ? b.note : b.text}</span>
            </span>
          </li>
        ))}
      </ul>
      <details>
        <summary>Table view</summary>
        <TableScroll label={`${title}, as a table`}>
          <table className="score-table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">{valueHeading}</th>
              </tr>
            </thead>
            <tbody>
              {bars.map((b) => (
                <tr key={b.label}>
                  <td>{b.label}</td>
                  <td>{b.value === null ? b.note : b.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      </details>
      <p className="chart-footer muted">{footer}</p>
    </figure>
  );
}
