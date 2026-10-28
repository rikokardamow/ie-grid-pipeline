import { BarChart } from "@/components/BarChart";
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

// "As of" for a chart: the editions its data comes from, never the report date
function asOf(editions: Record<string, string>, ids: string[]) {
  const dates = [...new Set(ids.map((id) => editions[id]).filter(Boolean))].sort();
  return dates.length > 0 ? ` · As of ${dates.join(" and ")}` : "";
}

function ProjectTable({ label, rows, extra }: {
  label: string;
  rows: (Project & Record<string, unknown>)[];
  extra?: { heading: string; cell: (r: Project & Record<string, unknown>) => string };
}) {
  const table = (part: typeof rows) => (
    <TableScroll label={label}>
      <table className="score-table wrap">
        <thead>
          <tr>
            <th scope="col">Ref</th>
            <th scope="col">Project</th>
            <th scope="col" className="num">MEC</th>
            {extra && <th scope="col">{extra.heading}</th>}
          </tr>
        </thead>
        <tbody>
          {part.map((r) => (
            <tr key={`${r.ref}-${r.name}`}>
              <td>
                <code>{r.ref}</code>
              </td>
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
      </section>

      <section aria-labelledby="moved">
        <h2 id="moved">What moved</h2>
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
