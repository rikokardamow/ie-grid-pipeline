"""The pages we scan and the lists we expect to find on them.

Each list is recognised by its file name. A PDF link that matches no pattern is
reported, not stored, so a new kind of list shows up in the run summary instead
of slipping in unnamed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EIRGRID_PAGE = "https://eirgrid.ie/industry/customer-information/connected-and-contracted-generators"
ESB_PAGE = "https://www.esbnetworks.ie/services/get-connected/renewable-connection/generator-statistics"

PAGES = (EIRGRID_PAGE, ESB_PAGE)


@dataclass(frozen=True)
class Source:
    source_id: str
    page: str
    pattern: re.Pattern[str]


SOURCES = (
    Source("eirgrid.tso_contracted_wind", EIRGRID_PAGE,
           re.compile(r"TSO-Contracted-Wind-Report", re.IGNORECASE)),
    Source("eirgrid.tso_contracted_nonwind", EIRGRID_PAGE,
           re.compile(r"TSO-Contracted-Non-Wind-Report", re.IGNORECASE)),
    Source("esb.dso_contracted_renewable", ESB_PAGE,
           re.compile(r"dso-contracted-renewable-generators", re.IGNORECASE)),
    Source("esb.dso_energised_renewable", ESB_PAGE,
           re.compile(r"dso-energised-renewable-generators", re.IGNORECASE)),
    Source("esb.dso_contracted_nonrenewable", ESB_PAGE,
           re.compile(r"dso-contracted-non-renewable-generators", re.IGNORECASE)),
    Source("esb.dso_energised_nonrenewable", ESB_PAGE,
           re.compile(r"dso-energised-non-renewable-generators", re.IGNORECASE)),
    Source("esb.dso_live_assessments", ESB_PAGE,
           re.compile(r"dso-live-connection-assessments", re.IGNORECASE)),
    Source("esb.renewable_summary", ESB_PAGE,
           re.compile(r"renewable-distribution-connected-generation_summary-report", re.IGNORECASE)),
)


def file_name(url: str) -> str:
    return url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]


def classify(url: str) -> Source | None:
    name = file_name(url)
    for source in SOURCES:
        if source.pattern.search(name):
            return source
    return None
