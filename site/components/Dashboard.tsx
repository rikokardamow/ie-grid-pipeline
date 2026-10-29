import { BarChart } from "@/components/BarChart";
import { Figure } from "@/components/Figure";
import { GridMap } from "@/components/GridMap";
import { LineChart } from "@/components/LineChart";
import { SplitBars } from "@/components/SplitBars";
import { Stat } from "@/components/Stat";
import { TableScroll } from "@/components/TableScroll";
import { LIST_NAMES, gw, mw, pct, waited } from "@/lib/format";
import type { Project, Report } from "@/lib/report";

// Rows shown before "show all"; a layout choice, never printed.
const TOP = 10;

const EIRGRID = "EirGrid contracted lists, Supported by EirGrid Group Data";
const ESB = "ESB Networks DSO lists, © ESB Networks, not for republication";
const OSM = "substations © OpenStreetMap contributors, ODbL";

const span = (editions: string[]) => (editions.length > 0 ? `, ${editions.join("; ")}` : "");

// "5" or "31-36": the range of a few numbers, as the g1 exhibit writes it
const range = (xs: number[]) => {
  if (xs.length === 0) return "";
  const lo = Math.min(...xs);
  const hi = Math.max(...xs);
  return lo === hi ? `${lo}` : `${lo}–${hi}`;
};

const TSO_IDS = ["eirgrid.tso_contracted_wind", "eirgrid.tso_contracted_nonwind"];
const DSO_CONTRACTED = ["esb.dso_contracted_renewable", "esb.dso_contracted_nonrenewable"];

// "As of" for a chart: the editions its data comes from, never the report date
function asOf(editions: Record<string, string>, ids: string[]) {
  const dates = [...new Set(ids.map((id) => editions[id]).filter(Boolean))].sort();
  return dates.length > 0 ? ` · As of ${dates.join(" and ")}` : "";
}

function ProjectTable({ label, rows, extra, noRef }: {
  label: string;
  noRef?: boolean;
  rows: (Project & Record<string, unknown>)[];
  extra?: { heading: string; cell: (r: Project & Record<string, unknown>) => string };
}) {
  const table = (part: typeof rows) => (
    <TableScroll label={label}>
      <table className="score-table wrap">
        <thead>
          <tr>
            {!noRef && <th scope="col">Ref</th>}
            <th scope="col">{noRef ? "Substation" : "Project"}</th>
            <th scope="col" className="num">MEC</th>
            {extra && <th scope="col">{extra.heading}</th>}
          </tr>
        </thead>
        <tbody>
          {part.map((r) => (
            <tr key={`${r.ref}-${r.name}`}>
              {!noRef && (
                <td>
                  <code>{r.ref}</code>
                </td>
              )}
              <td>{r.name}</td>
              <td className="num">{mw(r.mw)}</td>
              {extra && <td>{extra.cell(r)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </TableScroll>
  );
  if (rows.length <= TOP) return table(rows);
  return (
    <>
      {table(rows.slice(0, TOP))}
      <details>
        <summary>All rows</summary>
        {table(rows)}
      </details>
    </>
  );
}

// The finding, from the report's own comparison at equal age (report._stuck)
function burndownTitle({ stuck }: Report) {
  const first = stuck.burndown_first_at;
  const later = stuck.burndown_later_max_at;
  if (first === null) return `No ECP batch is ${stuck.at_years} years past its results yet`;
  const head = `At ${stuck.at_years} years, ${stuck.burndown_first} had ${pct(first)} of its MW energised`;
  return later === null ? head : `${head}; no later batch passed ${pct(later)}`;
}

function New({ report }: { report: Report }) {
  const n = report.new;
  if (n.first_report) {
    return <p>First report: there is no earlier report to compare with yet.</p>;
  }
  if (n.lists.length === 0) {
    return <p>No new publication since the report of {n.since}. The lists below are unchanged.</p>;
  }
  return (
    <ul className="plain">
      {n.lists.map((l) => (
        <li key={l.list}>
          New edition: {l.list}, as of {l.as_of}
        </li>
      ))}
    </ul>
  );
}

export function Dashboard({ report }: { report: Report }) {
  const { queue, moved, stuck, where } = report;
  const tso = moved.transmission;
  const dso = moved.distribution;
  const top = where.counties[0];
  const tech = queue.by_technology;
  const hist = queue.history;
  const lastTso = [...TSO_IDS.map((id) => report.editions[id] ?? "")].sort().pop() ?? "";
  const years = moved.by_year;
  const full = years.filter((y) => String(y.year) < lastTso.slice(0, 4));
  const shown = full[full.length - 1] ?? years[years.length - 1];
  const fresh = report.freshness;
  const grid = report.grid;

  return (
    <>
      <header>
        <h1>Ireland&apos;s grid connection queue</h1>
        <p className="muted">Weekly report of {report.report_date}</p>
        <p className="lede">
          {gw(queue.transmission_gw)} is contracted to connect to the transmission grid and{" "}
          {gw(queue.distribution_gw)} to the distribution grid, not yet energised.
        </p>
      </header>

      <section aria-labelledby="new">
        <h2 id="new">This week</h2>
        <New report={report} />
        {report.warnings.length > 0 && (
          <div className="card notice" role="note">
            <p>A newer edition could not be read, so the one before it is shown:</p>
            <ul className="plain">
              {report.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="stats">
          <Stat
            label="Transmission (EirGrid)"
            value={gw(queue.transmission_gw)}
            detail={`${queue.transmission_projects} projects, ${gw(queue.interconnector_gw)} of it interconnectors`}
          />
          <Stat
            label="Distribution (ESB Networks)"
            value={gw(queue.distribution_gw)}
            detail={`${queue.distribution_projects} projects`}
          />
        </div>
        {fresh.length > 0 && (
          <BarChart
            id="fig-freshness"
            title={`EirGrid's lists go up ${range(fresh.filter((f) => f.list.startsWith("EirGrid")).map((f) => f.days))} days after their as-of date; ESB's take ${range(fresh.filter((f) => f.list.startsWith("ESB")).map((f) => f.days))}`}
            subtitle="Days from each list's as-of date to its publication (the server's Last-Modified time), so the distribution side of this page runs about a month behind"
            footer={`Source: ${EIRGRID}; ${ESB}`}
            valueHeading="Days to publication"
            bars={fresh.map((f) => ({ label: f.list, value: f.days, text: `${f.days} days · as of ${f.as_of}, up ${f.published}` }))}
          />
        )}
      </section>

      <section aria-labelledby="waiting">
        <h2 id="waiting">What is waiting</h2>
        {tech.groups.length > 0 && (
          <Figure
            id="fig-technology"
            title={`${gw(tech.total_gw)} has signed to connect${tech.top_share === null ? "" : `; ${tech.groups[0].group.toLowerCase()} is ${pct(tech.top_share)} of it`}`}
            subtitle="Contracted GW not yet energised, by technology: transmission (EirGrid) and distribution (ESB Networks)"
            footer={`Source: ${EIRGRID}; ${ESB}${asOf(report.editions, [...TSO_IDS, ...DSO_CONTRACTED])}`}
            table={{
              headings: ["Technology", "Transmission", "Distribution"],
              rows: tech.groups.map((g) => [g.group, gw(g.transmission_gw), gw(g.distribution_gw)]),
            }}
          >
            <SplitBars
              mode="stacked"
              names={["transmission", "distribution"]}
              rows={tech.groups.map((g) => ({
                label: g.group,
                a: g.transmission_gw,
                b: g.distribution_gw,
                text: `${gw(g.transmission_gw + g.distribution_gw)} (${g.transmission_gw.toFixed(2)} + ${g.distribution_gw.toFixed(2)})`,
              }))}
            />
          </Figure>
        )}
        {hist.nonwind.length > 0 && (
          <Figure
            id="fig-history"
            title={`Non-wind waiting on transmission: ${gw(hist.nonwind[0].gw)} in ${hist.nonwind[0].as_of.slice(0, 4)}, ${gw(hist.nonwind[hist.nonwind.length - 1].gw)} now`}
            subtitle="GW printed on every EirGrid contracted list since the first one read; dashed rules mark each connection batch's results"
            footer={`Source: ${EIRGRID}, from the Internet Archive and eirgrid.ie${asOf(report.editions, TSO_IDS)}`}
            table={{
              headings: ["Edition", "Non-wind", "Wind"],
              rows: hist.nonwind.map((p) => [
                p.as_of,
                gw(p.gw),
                (() => {
                  const w = hist.wind.find((q) => q.as_of === p.as_of);
                  return w ? gw(w.gw) : "";
                })(),
              ]),
            }}
          >
            <LineChart
              unit="GW contracted on transmission"
              format={(v) => v.toFixed(1)}
              rules={hist.batches.map((b) => ({ date: b.results, label: b.batch }))}
              series={[
                { name: "non-wind", tone: "main", points: hist.nonwind.map((p) => ({ date: p.as_of, value: p.gw })) },
                { name: "wind", tone: "second", points: hist.wind.map((p) => ({ date: p.as_of, value: p.gw })) },
              ]}
            />
          </Figure>
        )}
      </section>

      <section aria-labelledby="moved">
        <h2 id="moved">What moved</h2>
        {shown && (
          <Figure
            id="fig-flows"
            title={`${shown.year}: ${gw(shown.joined_gw)} joined the transmission lists, ${gw(shown.left_gw)} left`}
            subtitle="GW joining and leaving the EirGrid contracted lists each year, edition by edition; relabelled refs are not counted as either"
            footer={`Source: ${EIRGRID}${asOf(report.editions, TSO_IDS)}`}
            table={{
              headings: ["Year", "Joined", "Left"],
              rows: years.map((y) => [String(y.year), gw(y.joined_gw), gw(y.left_gw)]),
            }}
          >
            <SplitBars
              mode="paired"
              names={["joined", "left (connected, withdrawn or moved)"]}
              rows={years.map((y) => ({
                label: String(y.year),
                a: y.joined_gw,
                b: y.left_gw,
                text: `▲ ${y.joined_gw.toFixed(2)} · ▼ ${y.left_gw.toFixed(2)} GW`,
              }))}
            />
          </Figure>
        )}
        <div className="card">
          <h3>Transmission{span(tso.editions)}</h3>
          {tso.joined.length + tso.left.length === 0 ? (
            <p>No project joined or left the transmission lists.</p>
          ) : (
            <p>
              {tso.joined_count} projects joined ({gw(tso.joined_gw)}) and {tso.left_count} left (
              {gw(tso.left_gw)}).{" "}
              {tso.all_confirmed
                ? "Every one is confirmed by name as well as ref."
                : "Some are not confirmed by name: check them in the lists."}
            </p>
          )}
          {tso.joined.length > 0 && (
            <ProjectTable label="Projects that joined the transmission lists" rows={tso.joined} />
          )}
          {tso.left.length > 0 && (
            <>
              <h3>Left (connected, withdrawn or moved)</h3>
              <ProjectTable label="Projects that left the transmission lists" rows={tso.left} />
            </>
          )}
        </div>
        <div className="card">
          <h3>Distribution{span(dso.editions)}</h3>
          <p>
            {dso.count} projects newly energised ({mw(dso.mw)}).
            {dso.newly_listed_count > 0 &&
              ` ${dso.newly_listed_count} more appeared on the energised lists with an older or no date.`}
          </p>
          {dso.projects.length > 0 && (
            <ProjectTable
              label="Projects newly energised on the distribution grid"
              rows={dso.projects}
              extra={{ heading: "Energised", cell: (r) => String(r.energised_on ?? r.note ?? "") }}
            />
          )}
        </div>
      </section>

      <section aria-labelledby="stuck">
        <h2 id="stuck">What&apos;s stuck</h2>
        <BarChart
          id="fig-burndown"
          title={burndownTitle(report)}
          subtitle={`Share of each ECP batch's distribution projects energised ${stuck.at_years} years after its results, by MW`}
          footer={`Source: ${ESB}; ECP batch results${asOf(report.editions, ["esb.dso_energised_renewable", "esb.dso_energised_nonrenewable"])}`}
          valueHeading={`Energised at ${stuck.at_years} years`}
          scaleMax={1}
          bars={stuck.burndown.map((b) => ({
            label: b.batch,
            value: b.share_at,
            text: pct(b.share_at ?? 0),
            note: `${b.age_months} months old, ${pct(b.share_now)} so far`,
          }))}
        />
        <div className="card">
          <h3>Longest waiting, {mw(stuck.large_mw)} and over</h3>
          <p className="muted">Transmission lists as of {stuck.as_of}, from the first signed month.</p>
          <ProjectTable
            label="Longest-waiting transmission projects"
            rows={stuck.longest_waiting}
            extra={{
              heading: "Waiting",
              cell: (r) => `${waited(r.years_part as number, r.months_part as number)} (${r.route})`,
            }}
          />
        </div>
      </section>

      <section aria-labelledby="where">
        <h2 id="where">Where</h2>
        <BarChart
          id="fig-counties"
          title={top ? `${top.county} has the most contracted generation waiting: ${gw(top.gw)}` : "No project placed in a county yet"}
          subtitle={`Contracted GW by county, transmission and distribution, interconnectors left out${
            where.generation_placed_share === null ? "" : `; ${pct(where.generation_placed_share)} of generation MW placed`
          }`}
          footer={`Source: ${EIRGRID}; ${ESB}; ECP batch results; ${OSM}${asOf(report.editions, [
            "eirgrid.tso_contracted_wind",
            "eirgrid.tso_contracted_nonwind",
            "esb.dso_contracted_renewable",
            "esb.dso_contracted_nonrenewable",
          ])}`}
          valueHeading="Contracted GW"
          bars={where.counties.map((c) => ({ label: c.county, value: c.gw, text: gw(c.gw) }))}
        />
        {grid === null ? (
          <p className="muted">No grid map yet: run <code>uv run python -m iegrid.grid</code>, then the report.</p>
        ) : (
          <>
            <Figure
              id="fig-map"
              title={`${gw(grid.far_gw)} waits at ${grid.far_nodes} substations ${grid.far_km} km or more from the ${grid.backbone_kv.join("/")} kV network`}
              subtitle={`Contracted MW by connection substation (circle area) on OpenStreetMap's lines, all-island; ${gw(grid.placed_gw)}${grid.placed_share === null ? "" : ` (${pct(grid.placed_share)})`} of the queue is at a substation on the map. Distance is from the substation, not the project's site`}
              footer={`Source: ${EIRGRID}; ${ESB}; lines and ${OSM}, fetched ${grid.osm_fetched_at.slice(0, 10)}; coast Natural Earth${asOf(report.editions, [...TSO_IDS, ...DSO_CONTRACTED])}`}
              table={{
                headings: ["Substation", "kV", "Contracted", "Projects", `To ${grid.backbone_kv.join("/")} kV`],
                rows: grid.nodes.map((n) => [n.node, String(n.kv), mw(n.mw), String(n.projects), n.km_backbone === null ? "" : `${n.km_backbone} km`]),
              }}
            >
              <div className="map-layout">
                <div>
                  <p className="key map-key">
                    <span className="line-swatch kv400" aria-hidden="true" /> {grid.backbone_kv[grid.backbone_kv.length - 1]} kV
                    <span className="line-swatch kv220" aria-hidden="true" /> {grid.backbone_kv.slice(0, -1).join("/")} kV
                    <span className="line-swatch" aria-hidden="true" /> lower
                    <span className="dot-swatch" aria-hidden="true" /> contracted MW
                  </p>
                  <GridMap
                    grid={grid}
                    format={(n) => `${n.node}: ${mw(n.mw)}, ${n.projects} projects${n.km_backbone === null ? "" : `, ${n.km_backbone} km to ${grid.backbone_kv.join("/")} kV`}`}
                  />
                </div>
                <BarChart
                  title={grid.bands[0] ? `${gw(grid.bands[0].gw)} is at substations ${grid.bands[0].label} from the backbone` : "No substation on the map yet"}
                  subtitle={`Contracted GW at mapped substations, by distance to the nearest ${grid.backbone_kv.join("/")} kV line`}
                  footer={`Source: as the map`}
                  valueHeading="Contracted GW"
                  bars={grid.bands.map((b) => ({ label: b.label, value: b.gw, text: `${gw(b.gw)} at ${b.nodes} substations` }))}
                />
              </div>
            </Figure>
            {grid.unplaced.length > 0 && (
              <div className="card">
                <h3>Not on the map: substations OpenStreetMap doesn&apos;t name yet</h3>
                <p className="muted">Mostly new stations. Their MW is counted above, not drawn.</p>
                <ProjectTable
                  label="Substations not on the map"
                  noRef
                  rows={grid.unplaced.map((u) => ({ ref: "", name: u.node, mw: u.mw }))}
                />
              </div>
            )}
          </>
        )}
      </section>

      <section aria-labelledby="runs">
        <h2 id="runs">Run log</h2>
        <div className="card" id="fig-runs">
          <h3>
            {report.runs.count === 0
              ? "No weekly run logged before this report"
              : `Before this report: ${report.runs.count} weekly ${report.runs.count === 1 ? "run" : "runs"} since ${report.runs.first?.slice(0, 10) ?? ""}; ${report.runs.with_new_files} brought a new file${report.runs.failed > 0 ? `, ${report.runs.failed} failed` : ""}`}
          </h3>
          <p className="muted">
            The weekly job checks both pages for new lists. Most weeks nothing lands: ESB posts quarterly, EirGrid irregularly. The run that wrote this page is logged after it, so a list it found is under This week, not here.
          </p>
          {report.runs.latest.length > 0 && (
            <TableScroll label="Weekly runs">
              <table className="score-table wrap">
                <thead>
                  <tr>
                    <th scope="col">Run</th>
                    <th scope="col">Started (UTC)</th>
                    <th scope="col">Status</th>
                    <th scope="col">New files</th>
                    <th scope="col">Parsed</th>
                  </tr>
                </thead>
                <tbody>
                  {report.runs.latest.map((r) => (
                    <tr key={r.run}>
                      <td>{r.run}</td>
                      <td>{r.started.replace("T", " ").slice(0, 16)}</td>
                      <td>{r.status}</td>
                      <td>{r.stored.length > 0 ? r.stored.join("; ") : String(r.new_files)}</td>
                      <td>{r.parsed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
          )}
        </div>
      </section>

      <section aria-labelledby="editions">
        <h2 id="editions">Editions used</h2>
        <TableScroll label="Editions used">
          <table className="score-table">
            <thead>
              <tr>
                <th scope="col">List</th>
                <th scope="col">As of</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(report.editions).map(([id, asOf]) => (
                <tr key={id}>
                  <td>{LIST_NAMES[id] ?? id}</td>
                  <td>{asOf}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      </section>

      <section aria-labelledby="caveats">
        <h2 id="caveats">Read with care</h2>
        <ul className="plain">
          {report.caveats.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </section>
    </>
  );
}
