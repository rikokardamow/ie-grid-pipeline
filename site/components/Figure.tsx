import { TableScroll } from "@/components/TableScroll";

// The frame every chart on the page shares (CHARTS.md): the finding as the title, the
// units under it, the source line at the foot, and the same numbers as a table.
export function Figure({ id, title, subtitle, footer, table, children }: {
  id?: string;
  title: string;
  subtitle: string;
  footer: string;
  table: { headings: string[]; rows: (string | number)[][] };
  children: React.ReactNode;
}) {
  return (
    <figure className="card chart" id={id}>
      <figcaption>
        <h3>{title}</h3>
        <p className="muted">{subtitle}</p>
      </figcaption>
      {children}
      <details>
        <summary>Table view</summary>
        <TableScroll label={`${title}, as a table`}>
          <table className="score-table">
            <thead>
              <tr>
                {table.headings.map((h) => (
                  <th key={h} scope="col">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((r, i) => (
                <tr key={i}>
                  {r.map((c, j) => (
                    <td key={j}>{c}</td>
                  ))}
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
