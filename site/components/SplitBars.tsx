// Horizontal bars of two parts, one dark and one pale, with a 2 px surface gap between
// them and the total written at the end. "stacked" puts the parts end to end (one
// total, two shares); "paired" gives each part its own thin bar (two measures per row).
// Names of the two parts are in the key above the bars, so colour is never alone.

export type SplitRow = { label: string; a: number; b: number; text: string };

export function SplitBars({ rows, names, mode }: {
  rows: SplitRow[];
  names: [string, string];
  mode: "stacked" | "paired";
}) {
  const max =
    Math.max(...rows.map((r) => (mode === "stacked" ? r.a + r.b : Math.max(r.a, r.b)))) || 1;
  const w = (v: number) => `${(v / max) * 100}%`;
  return (
    <>
      <p className="key">
        <span className="swatch main" aria-hidden="true" /> {names[0]}
        <span className="swatch second" aria-hidden="true" /> {names[1]}
      </p>
      <ul className={`bars split ${mode}`}>
        {rows.map((r) => (
          <li key={r.label} title={`${r.label}: ${r.text}`}>
            <span className="bar-label">{r.label}</span>
            <span className="bar-track">
              {mode === "stacked" ? (
                <span className="bar-stack">
                  <span className="bar main" style={{ width: w(r.a) }} />
                  <span className="bar second" style={{ width: w(r.b) }} />
                </span>
              ) : (
                <span className="bar-pair">
                  <span className="bar main" style={{ width: w(r.a) }} />
                  <span className="bar second" style={{ width: w(r.b) }} />
                </span>
              )}
              <span className="bar-value">{r.text}</span>
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}
