"""Checks the g1 notebook runs on the store. Read only.

The as-of date stored comes from the text inside the PDF. The file name carries
a date too, written by a different hand, so it is an independent check:
    TSO-Contracted-Wind-Report-05-08-2026.pdf        -> 2026-08-05
    ..._summary-report_01jul26.pdf                     -> 2026-07-01
    dso-..._q2_2026.pdf / q2-2026                      -> 2026-07-01 (day after the quarter)
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from iegrid.sources import file_name

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def as_of_from_name(url: str) -> date | None:
    name = file_name(url).lower()
    if m := re.search(r"(\d{2})-(\d{2})-(\d{4})\.pdf$", name):
        d, mo, y = map(int, m.groups())
        return date(y, mo, d)
    if m := re.search(r"_(\d{2})([a-z]{3})(\d{2})\.pdf$", name):
        d, mon, yy = m.groups()
        return date(2000 + int(yy), MONTHS[mon], int(d))
    if m := re.search(r"q([1-4])[_-](\d{4})\.pdf$", name):
        q, y = int(m.group(1)), int(m.group(2))
        return date(y + 1, 1, 1) if q == 4 else date(y, 3 * q + 1, 1)
    return None


@dataclass(frozen=True)
class Check:
    source_id: str
    as_of: date
    as_of_from_name: date | None
    hash_ok: bool
    published_at: datetime
    basis: str

    @property
    def as_of_ok(self) -> bool:
        return self.as_of == self.as_of_from_name


def check_publications(con) -> list[Check]:
    rows = con.execute(
        "select source_id, url, sha256, raw_path, as_of, published_at, published_at_basis "
        "from publication order by source_id, as_of"
    ).fetchall()
    out = []
    for source_id, url, sha, raw_path, as_of, published_at, basis in rows:
        path = Path(raw_path)
        hash_ok = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == sha
        out.append(Check(source_id, as_of, as_of_from_name(url), hash_ok, published_at, basis))
    return out


def table(con, sql: str) -> str:
    """A query as fixed-width text, fully fetched so the connection is free afterwards."""
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = [[("" if v is None else str(v)) for v in r] for r in cur.fetchall()]
    widths = [max(len(c), *(len(r[i]) for r in rows)) if rows else len(c)
              for i, c in enumerate(cols)]
    line = lambda vals: "  ".join(v.ljust(w) for v, w in zip(vals, widths))  # noqa: E731
    return "\n".join([line(cols), line(["-" * w for w in widths]), *map(line, rows)])
