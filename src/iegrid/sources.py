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


# g3: lists that are only in the archive. EirGrid named its files a dozen ways
# since 2009 ("Connected Wind Report 12Jan10", "contractedtso(non wind)generators
# 18july2013", "TSO-Wind-Contracted-31.03.2022"), and both publishers changed
# what the lists cover:
#   EirGrid to 2017: wind / non-wind ("other types" before 2012).
#   EirGrid connected from Sep 2017: renewables / non-renewables.
#   ESB to 2023: wind / non-wind. From Q1 2024: renewable / non-renewable.
# A list that covers something different keeps its own source_id.
ARCHIVE_ONLY = (
    "eirgrid.tso_connected_wind",
    "eirgrid.tso_connected_nonwind",
    "eirgrid.tso_connected_renewable",
    "eirgrid.tso_connected_nonrenewable",
    "esb.dso_contracted_wind",
    "esb.dso_contracted_nonwind",
    "esb.dso_energised_wind",
    "esb.dso_energised_nonwind",
)

# Where the archive is searched (Wayback CDX url prefixes).
ARCHIVE_PREFIXES = (
    "cms.eirgrid.ie/sites/default/files/publications/*",
    "www.eirgridgroup.com/site-files/library/EirGrid/*",
    "esbnetworks.ie/docs/default-source/publications/*",
    "media.esbnetworks.ie/media/docs/default-source/publications/*",
)

NOT_A_LIST = re.compile(
    r"appendix|cp\d|guidelines|mpid|forum|outage|tuos|standard|general-conditions|"
    r"becoming-operational|ds3|form-|trips|generators-view|emt-model|getting-connected|"
    r"rocof|north-south|curtailment|non-firm|innovation|modification|complaints|nc5a",
)


def normalised_name(url: str) -> str:
    """'Connected%20TSO%20(Non-Wind)%20Generators' -> 'connected-tso-non-wind-generators'."""
    from urllib.parse import unquote

    name = unquote(file_name(url)).lower()
    return re.sub(r"[^a-z0-9.]+", "-", name).strip("-")


def classify_archived(url: str) -> str | None:
    """source_id for an archived file, or None when it isn't one of the lists."""
    if (live := classify(url)) is not None:
        return live.source_id
    name = normalised_name(url)
    if not name.endswith(".pdf") or NOT_A_LIST.search(name):
        return None
    if "esbnetworks" in url or name.startswith(("dso-", "renewable-distribution")):
        if "summary-report" in name and name.startswith("renewable-distribution"):
            return "esb.renewable_summary"
        nonwind = "non-wind" in name
        if name.startswith("dso-contracted-") and "wind" in name:
            return "esb.dso_contracted_nonwind" if nonwind else "esb.dso_contracted_wind"
        if name.startswith("dso-connected-energised-") and "wind" in name:
            return "esb.dso_energised_nonwind" if nonwind else "esb.dso_energised_wind"
        return None
    contracted = "contracted" in name
    connected = "connected" in name and not contracted
    if not (contracted or connected):
        return None
    if connected and "non-renewable" in name:
        return "eirgrid.tso_connected_nonrenewable"
    if connected and "renewable" in name:
        return "eirgrid.tso_connected_renewable"
    nonwind = bool(re.search(r"non-?wind|other-types", name))
    if not (nonwind or "wind" in name):
        return None
    kind = "contracted" if contracted else "connected"
    return f"eirgrid.tso_{kind}_{'nonwind' if nonwind else 'wind'}"
