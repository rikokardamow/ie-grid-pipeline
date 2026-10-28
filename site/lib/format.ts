// Numbers as the weekly page writes them. Dates stay as the report gives them
// (2026-08-05), so a date on the page is always the report's own string.

export const gw = (x: number) => `${x.toFixed(2)} GW`;

export const mw = (x: number) => `${x.toFixed(x >= 10 ? 0 : 1)} MW`;

export const pct = (share: number) => `${Math.round(share * 100)}%`;

export const waited = (years: number, months: number) => `${years} y ${months} m`;

// The list names the report uses, for the editions table
export const LIST_NAMES: Record<string, string> = {
  "eirgrid.tso_contracted_wind": "EirGrid contracted wind",
  "eirgrid.tso_contracted_nonwind": "EirGrid contracted non-wind",
  "esb.dso_contracted_renewable": "ESB contracted renewable",
  "esb.dso_contracted_nonrenewable": "ESB contracted non-renewable",
  "esb.dso_energised_renewable": "ESB energised renewable",
  "esb.dso_energised_nonrenewable": "ESB energised non-renewable",
};
