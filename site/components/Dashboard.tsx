import { BarChart } from "@/components/BarChart";
import { Figure } from "@/components/Figure";
import { GridMap } from "@/components/GridMap";
import { LineChart } from "@/components/LineChart";
import { SplitBars } from "@/components/SplitBars";
import { Stat } from "@/components/Stat";
import { TableScroll } from "@/components/TableScroll";
import { LIST_NAMES, gw, mw, pct, waited } from "@/lib/format";
import type { Pace, Project, Report } from "@/lib/report";

// Rows shown before "show all"; a layout choice, never printed.
const TOP = 10;

const EIRGRID = "EirGrid contracted lists, Supported by EirGrid Group Data";
const ESB = "ESB Networks DSO lists, © ESB Networks, used with their permission";
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

// The shares a batch has: both counts when both exist, never a made-up zero or one
const shares = (b: { share_found: number | null; share_tagged: number | null }) =>
  [b.share_found, b.share_tagged].filter((v): v is number => v !== null);

const DSO_ENERGISED = ["esb.dso_energised_renewable", "esb.dso_energised_nonrenewable"];

// One grid's delivery pace: MW energised each year, the contracted queue in years of that
// pace over the window the back-test supports (or doesn't), and the fastest window beside it.
function PaceFigure({ id, grid, pace, source, note }: {
  id: string;
  grid: string;
  pace: Pace;
  source: string;
  note: string;
}) {
  const recent = pace.cover[0];
  const fastest = pace.fastest[0];
  const last = pace.backtest.methods.find((m) => m.method === "last year");
  const mean = pace.backtest.methods.find((m) => m.method === "mean of 3");
  const averageHelps = !!last && !!mean && mean.mae_mw < last.mae_mw;
  return (
    <Figure
      id={id}
      title={
        recent && recent.years !== null
          ? `At the ${recent.from}-${recent.to} pace the ${grid} queue of ${mw(pace.queue_mw)} is ${recent.years} years of delivery${fastest && fastest.years !== null ? `; at the fastest ${fastest.window} years (${fastest.from}-${fastest.to}), ${fastest.years}` : ""}`
          : `The ${grid} queue of ${mw(pace.queue_mw)} has no recent pace to set against`
      }
      subtitle={`MW energised per year, ${grid}, ${pace.annual[0]?.year ?? ""} to ${pace.through}. Years of cover is the contracted MW over the mean pace of the window, not a forecast of when the queue clears: most contracted MW never energises. ${
        last && mean
          ? `Back-test over ${pace.backtest.years} years (${pace.backtest.first}-${pace.backtest.through}): ${averageHelps ? `a ${mean.method.replace("mean of ", "")}-year mean beat last year's value in ${mean.beats_last_year} of ${pace.backtest.years} years (${mw(mean.mae_mw)} against ${mw(last.mae_mw)} mean error)` : `last year's value was the better guide (${mw(last.mae_mw)} mean error against ${mw(mean.mae_mw)} for a ${mean.method.replace("mean of ", "")}-year mean), so no averaging claim is made`}.`
          : ""
      }`}
      footer={`Source: ${source}`}
      table={{
        headings: ["Window", "Pace (MW a year)", "Years of cover"],
        rows: [...pace.cover, ...pace.fastest].map((c) => [`${c.from}-${c.to}`, mw(c.pace_mw), c.years === null ? "no pace" : String(c.years)]),
      }}
    >
      <BarChart
        title="MW energised each year"
        subtitle={note}
        footer=""
        valueHeading="MW"
        bars={pace.annual.map((a) => ({ label: String(a.year), value: a.mw, text: mw(a.mw) }))}
      />
    </Figure>
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
  const count = (outcome: string) =>
    report.left_outcomes?.by_outcome.find((o) => o.outcome === outcome)?.count ?? 0;

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
        {report.left_outcomes && (
          <Figure
            id="fig-left"
            title={`${report.left_outcomes.total} projects (${gw(report.left_outcomes.total_gw)}) have left the contracted lists for good; ${count("connected") + count("connected on the distribution grid")} are on a connected or energised list by ref, ${count("connected as part of a sibling")} more as phases of one`}
            subtitle={`Each project's final leave from the contracted lists, by what EirGrid's connected lists say (they cover wind only, to ${report.left_outcomes.cover_end}). Leaving the contracted list was within a year of the first connected listing for ${report.left_outcomes.energised_at_leave.within_a_year} of ${report.left_outcomes.energised_at_leave.refs} matched by ref`}
            footer={`Source: ${EIRGRID}, connected lists from the Internet Archive${asOf(report.editions, TSO_IDS)}`}
            table={{
              headings: ["Outcome", "Projects", "GW"],
              rows: report.left_outcomes.by_outcome.map((o) => [o.outcome, String(o.count), gw(o.gw)]),
            }}
          >
            <BarChart
              title="Projects by outcome"
              subtitle="Count of final leavers; 'unknown' is never read as 'not connected'"
              footer={`Unknown: ${report.left_outcomes.why_unknown.map((w) => `${w.count} ${w.why}`).join("; ")}`}
              valueHeading="Projects"
              bars={report.left_outcomes.by_outcome.map((o) => ({
                label: o.outcome,
                value: o.count,
                text: `${o.count} (${gw(o.gw)})`,
              }))}
            />
            {report.left_outcomes.not_listed.length > 0 && (
              <>
                <h3>Wind projects on no connected list</h3>
                <ProjectTable
                  label="Wind projects that left the contracted lists and are on no connected list"
                  rows={report.left_outcomes.not_listed.map((n) => ({ ref: n.ref, name: n.name, mw: n.mw, left: n.left }))}
                  extra={{ heading: "Left", cell: (r) => String(r.left ?? "") }}
                />
              </>
            )}
          </Figure>
        )}
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

      {report.funnel && report.funnel.batches.length > 0 && (
        <section aria-labelledby="funnel">
          <h2 id="funnel">From offer to contract</h2>
          <Figure
            id="fig-funnel"
            title={(() => {
              const all = report.funnel.batches.flatMap((b) => shares(b));
              return all.length === 0
                ? "No ECP batch's offers could be followed to a contracted list"
                : `Of the projects each ECP batch offered, ${pct(Math.min(...all))} to ${pct(Math.max(...all))} have ever appeared on a contracted list`;
            })()}
            subtitle="Share of each batch's distinct offers that appear on a contracted or ESB energised list, counted two independent ways: by matching each offer to a list row by name and MEC (strict, so a lower bound), and from the lists' own batch tags. Where they differ, the recall column says how much the matching missed. ESB's contracted lists in the store begin long after the early batches, so a distribution project that signed and withdrew before then leaves no trace: the early batches are undercounted, and the later ones are the cleaner reading."
            footer={`Source: ECP batch results (joint system-operator publications); ${EIRGRID}; ${ESB}${asOf(report.editions, [...TSO_IDS, ...DSO_CONTRACTED])}`}
            table={{
              headings: ["Batch", "Results", "Age (months)", "Offered", "Found by matching", "Counted by tag", "Match precision", "Match recall", "Where the found ones are now"],
              rows: report.funnel.batches.map((b) => [
                b.batch,
                b.results ?? "",
                String(b.age_months ?? ""),
                `${b.offered} (${mw(b.offered_mw)})`,
                `${b.found} (${mw(b.found_mw)})`,
                String(b.tagged),
                b.validation.precision === null ? "" : pct(b.validation.precision),
                b.validation.recall === null ? "" : pct(b.validation.recall),
                Object.entries(b.status).map(([k, v]) => `${v} ${k}`).join("; "),
              ]),
            }}
          >
            <SplitBars
              mode="paired"
              scaleMax={1}
              names={["found by matching offers to the lists", "counted from the lists' own batch tags"]}
              rows={report.funnel.batches.map((b) => ({
                label: `${b.batch} (${b.results ?? ""})`,
                a: b.share_found ?? 0,
                b: b.share_tagged ?? 0,
                text: shares(b).length === 0 ? "no count" : `${pct(Math.min(...shares(b)))} to ${pct(Math.max(...shares(b)))} of ${b.offered} offers`,
              }))}
            />
          </Figure>
        </section>
      )}

      {report.target_slippage && report.target_slippage.matched > 0 && (
        <section aria-labelledby="slip">
          <h2 id="slip">Promise against delivery</h2>
          <Figure
            id="fig-slippage"
            title={`${report.target_slippage.late_to_completion} of ${report.target_slippage.matched} wind projects with a published target connected after it${
              report.target_slippage.enough && report.target_slippage.median_to_completion !== null && report.target_slippage.median_to_first !== null
                ? `, by a median of ${report.target_slippage.median_to_first} months to first listing and ${report.target_slippage.median_to_completion} to completion`
                : ""
            }`}
            subtitle={`Months between the target connection month EirGrid printed in its earliest lists and the projects' connected-list entries. Wind only, one cohort: ${report.target_slippage.with_target} projects had a target and ${report.target_slippage.matched} can be followed to a connection (${report.target_slippage.unmatched} cannot: still waiting, on the distribution grid, or spelled differently). The lists don't say whether a target meant first energisation or full export, so both are shown. This is a record of what happened to these projects, not a rate to apply to others.`}
            footer={`Source: ${EIRGRID}, connected lists from the Internet Archive${asOf(report.editions, TSO_IDS)}`}
            table={{
              headings: ["Project", "MEC", "Target", "First listed", "Completed", "Months late to first listing", "Months late to completion"],
              rows: report.target_slippage.rows.map((r) => [`${r.name} (${r.ref})`, mw(r.mw), r.target, r.first_listed, r.completed, String(r.to_first), String(r.to_completion)]),
            }}
          >
            <BarChart
              title="Months from the target to completion"
              subtitle="▲ later than the target, ▼ earlier"
              footer=""
              valueHeading="Months"
              bars={report.target_slippage.rows.map((r) => ({
                label: `${r.name} (${r.ref})`,
                value: Math.max(0, r.to_completion),
                text: `${r.to_completion > 0 ? "▲" : r.to_completion < 0 ? "▼" : ""} ${Math.abs(r.to_completion)}`.trim(),
              }))}
            />
          </Figure>
        </section>
      )}

      {report.delivery_pace && (
        <section aria-labelledby="pace">
          <h2 id="pace">Pace of delivery</h2>
          <PaceFigure
            id="fig-pace-dso"
            grid="distribution"
            pace={report.delivery_pace.distribution}
            source={`${ESB}${asOf(report.editions, DSO_ENERGISED)}`}
            note={`ESB revises its energisation history. Across the ${report.delivery_pace.distribution.stability.editions_compared} editions held, a year's total moves by at most ${mw(report.delivery_pace.distribution.stability.window_change_mw)} inside the pace window (${report.delivery_pace.distribution.stability.window_years[0]}-${report.delivery_pace.distribution.stability.window_years[1]}), but by up to ${mw(report.delivery_pace.distribution.stability.largest_change_mw)} in an earlier year (${report.delivery_pace.distribution.stability.year}; the errata below say why).${
              report.delivery_pace.distribution.vintage_check
                ? ` The back-test on the series as first printed in the ${report.delivery_pace.distribution.vintage_check.edition} edition ${report.delivery_pace.distribution.vintage_check.averaging_beats_last_year ? "also finds averaging beats last year's value" : "does not agree that averaging beats last year's value"}.`
                : ""
            }`}
          />
          <PaceFigure
            id="fig-pace-tso"
            grid="transmission wind"
            pace={report.delivery_pace.transmission_wind}
            source={`${EIRGRID}, connected list of ${report.delivery_pace.transmission_wind.as_of}`}
            note={`The connected lists end at ${report.delivery_pace.transmission_wind.as_of}, so this pace is older than the queue it is set against. Transmission non-wind has no pace series (its connected lists carry no dates per project), so it is blank here, not zero. EirGrid restated its own wind history by ${mw(report.delivery_pace.transmission_wind.restatement.largest_mw)} between its ${report.delivery_pace.transmission_wind.restatement.last_edition_before ?? ""} and ${report.delivery_pace.transmission_wind.restatement.first_edition_matching ?? ""} editions.`}
          />
        </section>
      )}

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
              subtitle={`Contracted MW by connection substation (circle area) on OpenStreetMap's lines, all-island; ${gw(grid.placed_gw)}${grid.placed_share === null ? "" : ` (${pct(grid.placed_share)})`} of the queue is on the map. A new station OpenStreetMap doesn't have yet is drawn at the existing station its ECP results name, at a site a cited source gives, or at the townland it is named after (marked so in the table). Distance is from the substation, not the project's site`}
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
                <p className="muted">
                  Mostly new stations. Their MW is counted above, not drawn. A project whose list and ECP results name stations far apart is listed here too, under both names.
                </p>
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

      {report.external && report.external.checks.length > 0 && (
        <section aria-labelledby="external">
          <h2 id="external">Against a published total</h2>
          {report.external.checks.map((c) => (
            <Figure
              key={c.id}
              id="fig-external"
              title={`The two publishers' lists add up to ${mw(c.ours_mw)} of wind; the published national total is ${mw(c.theirs_mw)}: ${mw(Math.abs(c.diff_mw))} (${pct(Math.abs(c.diff_pct))}) ${c.diff_mw < 0 ? "short" : "over"}`}
              subtitle={`${c.label}, ${c.as_of}. Scope: ${c.scope}. This checks our reading of the lists against a figure published elsewhere (${c.source}); the figure comes from SEAI, which draws on EirGrid and ESB data, so agreement was expected and a gap would have meant a list lost or double-counted. ${
                c.decomposition
                  ? `Stepping both totals back a year with the published net addition, the gap was ${mw(Math.abs(c.decomposition.gap_before_mw))} (${pct(Math.abs(c.decomposition.gap_before_pct))}) at the end of ${c.decomposition.year - 1} and grew by ${mw(Math.abs(c.decomposition.added_shortfall_mw))} in ${c.decomposition.year}: our lists see ${mw(c.decomposition.ours_added_mw)} of added wind that year against ${mw(c.decomposition.theirs_net_added_mw)} net, and EirGrid's last list is from ${c.tso_edition}, so wind connecting after it is not in them. The earlier ${mw(Math.abs(c.decomposition.gap_before_mw))} is a level difference we have not explained; ruled out: ${c.ruled_out.join("; ")}.`
                  : `The gap is not explained: ${c.ruled_out.join("; ")}.`
              }`}
              footer={`Source: ${c.source}, checked ${c.checked_on}: "${c.says}"; ${EIRGRID}; ${ESB}`}
              table={{
                headings: ["Part", "Edition", "MW"],
                rows: [
                  ["EirGrid connected wind (installed)", c.tso_edition, mw(c.tso_mw)],
                  ["ESB energised wind (MEC), entries dated to the day", c.dso_edition, mw(c.dso_mw)],
                  ["Our total", "", mw(c.ours_mw)],
                  ["Published total", c.as_of, mw(c.theirs_mw)],
                  ...(c.decomposition
                    ? [
                        [`Gap at the end of ${c.decomposition.year - 1}`, "", mw(c.decomposition.gap_before_mw)],
                        [`Added in ${c.decomposition.year}: ours`, "", mw(c.decomposition.ours_added_mw)],
                        [`Added in ${c.decomposition.year}: published, net`, "", mw(c.decomposition.theirs_net_added_mw)],
                      ]
                    : []),
                ],
              }}
            >
              <BarChart
                title="Wind capacity, MW"
                subtitle={c.notes}
                footer=""
                valueHeading="MW"
                bars={[
                  { label: "EirGrid connected", value: c.tso_mw, text: mw(c.tso_mw) },
                  { label: "ESB energised", value: c.dso_mw, text: mw(c.dso_mw) },
                  { label: "Our total", value: c.ours_mw, text: mw(c.ours_mw) },
                  { label: "Published total", value: c.theirs_mw, text: mw(c.theirs_mw) },
                ]}
                scaleMax={c.theirs_mw}
              />
            </Figure>
          ))}
        </section>
      )}

      {report.firm_capacity && (
        <section aria-labelledby="firm-capacity">
          <h2 id="firm-capacity">How much of the queue counts as capacity</h2>
          {(() => {
            const f = report.firm_capacity;
            const range = (lo: number, hi: number) => (lo === hi ? pct(lo) : `${pct(lo)} to ${pct(hi)}`);
            const gasText =
              f.gas_nameplate_share !== null && f.gas_share_low !== null && f.gas_share_high !== null
                ? `; gas turbines are ${pct(f.gas_nameplate_share)} of that nameplate and ${range(f.gas_share_low, f.gas_share_high)} of what counts`
                : "";
            const mwRange = (lo: number, hi: number) => (lo === hi ? mw(lo) : `${mw(lo)} to ${mw(hi)}`);
            return (
              <Figure
                id="fig-firm"
                title={`Of the ${gw(f.applied_mw / 1000)} of the queue with a published factor, ${gw(f.totals.latest.low_mw / 1000)} to ${gw(f.totals.latest.high_mw / 1000)} counts as capacity in the ${f.latest_year} auction${gasText}`}
                subtitle={`Share of each technology's contracted MW that the capacity auction counts, from the de-rating factors the system operators publish for the ${f.latest_year} auction, applied at each project's size. A battery's duration is not on the lists, so storage is shown for ${f.storage_hours.low} and ${f.storage_hours.high} hours. ${mw(f.left_alone_mw)}${f.left_alone_share === null ? "" : ` (${pct(f.left_alone_share)} of the queue)`} has no factor applied: hybrids such as solar with a battery, interconnectors, combined heat and power, and smaller technologies. This is the auction's rule for what a megawatt is worth, not a forecast that a project connects and not what a megawatt delivers in an hour.`}
                footer={`Source: ${f.sources.map((x) => `${x.name}, read ${x.checked_on}`).join("; ")}; ${EIRGRID}; ${ESB}`}
                table={{
                  headings: ["Technology", "Projects", "Contracted", `Counts, ${f.prior_year}`, `Counts, ${f.latest_year}`, `Share, ${f.latest_year}`],
                  rows: [
                    ...f.classes.map((c) => [
                      c.label, c.projects, mw(c.nameplate_mw),
                      mwRange(c.prior.low_mw, c.prior.high_mw), mwRange(c.latest.low_mw, c.latest.high_mw),
                      range(c.latest.low_share, c.latest.high_share),
                    ]),
                    ["All with a factor", "", mw(f.applied_mw), mwRange(f.totals.prior.low_mw, f.totals.prior.high_mw),
                      mwRange(f.totals.latest.low_mw, f.totals.latest.high_mw), ""],
                    ...f.left_alone.map((l) => [l.technology, "", mw(l.mw), "no factor applied", "no factor applied", ""]),
                  ],
                }}
              >
                <BarChart
                  title="Share of contracted MW that counts"
                  subtitle="Each bar is the share counted; battery storage is drawn at the longer duration"
                  footer=""
                  valueHeading="Share counted"
                  bars={f.classes.map((c) => ({
                    label: c.label,
                    value: c.latest.high_share,
                    text: range(c.latest.low_share, c.latest.high_share),
                  }))}
                  scaleMax={1}
                />
              </Figure>
            );
          })()}
        </section>
      )}

      {report.errata && (
        <section aria-labelledby="errata">
          <h2 id="errata">Where the lists disagree</h2>
          <div className="card" id="fig-errata">
            <h3>
              {report.errata.total === 0
                ? "No disagreement found between the lists"
                : `${report.errata.total} places where a publisher's list disagrees with itself or another publication`}
            </h3>
            <p className="muted">
              A disagreement is not necessarily an error: each row says what disagrees and what would settle it. The list is rebuilt with every report, so a row goes when a publisher fixes its list.
              {report.errata.kinds.length > 0 && ` By kind: ${report.errata.kinds.map((k) => `${k.count} ${k.kind}`).join(", ")}.`}
            </p>
            {report.errata.entries.length > 0 && (
              <TableScroll label="Disagreements between the lists">
                <table className="score-table wrap">
                  <thead>
                    <tr>
                      <th scope="col">Kind</th>
                      <th scope="col">Project</th>
                      <th scope="col">One says</th>
                      <th scope="col">Against</th>
                      <th scope="col">What would settle it</th>
                      <th scope="col">Answer found</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.errata.entries.map((e) => (
                      <tr key={`${e.kind}-${e.ref}-${e.project}`}>
                        <td>{e.kind}</td>
                        <td>
                          {e.ref && <code>{e.ref}</code>} {e.project}
                        </td>
                        <td>{e.says}</td>
                        <td>{e.against}</td>
                        <td>{e.settles}</td>
                        <td>
                          {e.answer ? (
                            <>
                              <strong>{e.answer.status}</strong>: {e.answer.verdict}. {e.answer.detail}{" "}
                              {e.answer.url ? (
                                <a href={e.answer.url}>{e.answer.source}</a>
                              ) : (
                                e.answer.source
                              )}{" "}
                              (read {e.answer.checked_on})
                            </>
                          ) : (
                            "Not looked into"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableScroll>
            )}
          </div>
        </section>
      )}

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
