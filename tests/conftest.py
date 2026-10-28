"""Shared test helpers. No test touches the network."""

from __future__ import annotations

import pytest

from iegrid import store


def make_pdf(lines: list[str], *more_pages: list[str]) -> bytes:
    """A PDF with one page per list of text lines, built by hand (no extra dependency)."""
    pages = [lines, *more_pages]
    n = len(pages)
    # objects: 1 catalog, 2 pages, 3 font, then a page + content pair per page
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n)).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % n,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, page_lines in enumerate(pages):
        ops = ["BT", "/F1 10 Tf", "14 TL", "50 780 Td"]
        for line in page_lines:
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({safe}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode()
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                       b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (5 + 2 * i))
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, xref)
    return bytes(out)


@pytest.fixture
def con():
    c = store.connect(":memory:")
    yield c
    c.close()
