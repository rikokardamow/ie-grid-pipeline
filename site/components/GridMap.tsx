import type { Grid } from "@/lib/report";

// The island, OpenStreetMap's lines by voltage, and a circle at each substation sized by
// the contracted MW waiting there. An equirectangular projection at Ireland's latitude
// is close enough at this scale. Each circle has a hover title; the numbers are also
// in the tables below the map.

const W = 560;
const LAT0 = 53.4;
const K = Math.cos((LAT0 * Math.PI) / 180);

export function GridMap({ grid, format }: { grid: Grid; format: (node: Grid["nodes"][number]) => string }) {
  const pts = grid.outline.flat();
  const lons = pts.map((p) => p[0]);
  const lats = pts.map((p) => p[1]);
  const [x0, x1] = [Math.min(...lons), Math.max(...lons)];
  const [y0, y1] = [Math.min(...lats), Math.max(...lats)];
  const scale = W / ((x1 - x0) * K || 1);
  const H = Math.round((y1 - y0) * scale) || W;
  const px = (lon: number) => (lon - x0) * K * scale;
  const py = (lat: number) => (y1 - lat) * scale;
  const path = (ring: number[][]) => ring.map((p, i) => `${i ? "L" : "M"}${px(p[0]).toFixed(1)},${py(p[1]).toFixed(1)}`).join("") + "Z";
  const line = (ring: number[][]) => ring.map((p, i) => `${i ? "L" : "M"}${px(p[0]).toFixed(1)},${py(p[1]).toFixed(1)}`).join("");
  const maxMw = Math.max(...grid.nodes.map((n) => n.mw)) || 1;
  const r = (mw: number) => 14 * Math.sqrt(mw / maxMw); // area in proportion to MW
  const byKv = [...grid.lines].sort((a, b) => a.kv - b.kv);
  const kvClass = (kv: number) => (kv >= 400 ? "kv400" : kv >= 220 ? "kv220" : "kv110");

  return (
    <svg className="grid-map" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Map of contracted generation by substation">
      {grid.outline.map((ring, i) => (
        <path key={i} d={path(ring)} className="land" />
      ))}
      {byKv.map((l, i) => (
        <path key={i} d={line(l.path)} className={`power ${kvClass(l.kv)}`} />
      ))}
      {[...grid.nodes].filter((n) => n.mw > 0).reverse().map((n) => (
        <circle key={n.node} cx={px(n.lon)} cy={py(n.lat)} r={r(n.mw)} className="node">
          <title>{format(n)}</title>
        </circle>
      ))}
    </svg>
  );
}
