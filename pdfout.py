# -*- coding: utf-8 -*-
"""A small branded-PDF writer in plain Python - no packages to install.

Enough PDF to produce a clean DHARANI 360 record sheet or register export:
the teal header band, headings, labelled fields, tables, rules, a QR code and
a footer. Text uses the two fonts every PDF reader already has built in
(Helvetica and Helvetica-Bold), so nothing has to be embedded and the file
stays a few kilobytes.

    from pdfout import Document
    doc = Document("Trade Licence Renewal", "COR-002/14")
    doc.field("Licence number", "CN-1042887")
    doc.save("out.pdf")
"""

import zlib

# --------------------------------------------------------------- page setup --

A4_W, A4_H = 595.28, 841.89
MARGIN = 46.0

TEAL = (0.055, 0.455, 0.565)      # #0e7490
DEEP = (0.043, 0.360, 0.451)      # #0b5c73
COPPER = (0.420, 0.259, 0.149)    # #6b4226
INK = (0.090, 0.125, 0.180)
MUTED = (0.404, 0.451, 0.502)
LINE = (0.851, 0.878, 0.898)
WASH = (0.945, 0.965, 0.973)
WHITE = (1, 1, 1)

# Character widths per 1000 em, from the Adobe core-font metrics.
_W_REG = (
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 "
    "1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 "
    "333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 "
    "556 556 333 500 278 556 500 722 500 500 500 334 260 334 584"
).split()
_W_BOLD = (
    "278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 "
    "975 722 722 722 722 667 611 778 722 278 556 722 611 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 333 278 333 584 556 "
    "333 556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 "
    "611 611 389 556 333 611 556 778 556 556 500 389 280 389 584"
).split()
WIDTHS = {False: [int(x) for x in _W_REG], True: [int(x) for x in _W_BOLD]}


def text_width(s, size, bold=False):
    table = WIDTHS[bold]
    total = 0
    for ch in s:
        o = ord(ch)
        total += table[o - 32] if 32 <= o <= 126 else 556
    return total * size / 1000.0


def _clean(s):
    """Fold anything outside WinAnsi down to something a core font can draw."""
    if s is None:
        return ""
    s = str(s)
    swaps = {"‘": "'", "’": "'", "“": '"', "”": '"',
             "–": "-", "—": "-", "…": "...", " ": " ",
             "•": "-", "×": "x", "→": "->", "✓": "v"}
    for a, b in swaps.items():
        s = s.replace(a, b)
    return "".join(ch if 32 <= ord(ch) <= 126 else "?" for ch in s)


def _esc(s):
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def wrap(s, width, size, bold=False):
    """Greedy word wrap; also breaks a single word that is too long on its own."""
    s = _clean(s)
    out = []
    for para in s.split("\n"):
        words, line = para.split(), ""
        if not words:
            out.append("")
            continue
        for w in words:
            trial = (line + " " + w).strip()
            if text_width(trial, size, bold) <= width or not line:
                if text_width(trial, size, bold) > width and not line:
                    chunk = ""
                    for ch in w:
                        if text_width(chunk + ch, size, bold) > width and chunk:
                            out.append(chunk)
                            chunk = ch
                        else:
                            chunk += ch
                    line = chunk
                else:
                    line = trial
            else:
                out.append(line)
                line = w
        out.append(line)
    return out


# ---------------------------------------------------------------- document --

class Document(object):
    def __init__(self, title, subtitle="", org="DHARANI 360",
                 tagline="Realty Operations & Compliance Suite", footer=""):
        self.title = _clean(title)
        self.subtitle = _clean(subtitle)
        self.org = _clean(org)
        self.tagline = _clean(tagline)
        self.footer = _clean(footer)
        self.pages = []
        self._ops = []
        self.y = 0.0
        self._new_page()

    # ------------------------------------------------------------ primitives
    def _op(self, s):
        self._ops.append(s)

    def rect(self, x, y, w, h, color, radius=0):
        r, g, b = color
        self._op("{:.3f} {:.3f} {:.3f} rg".format(r, g, b))
        if radius <= 0:
            self._op("{:.2f} {:.2f} {:.2f} {:.2f} re f".format(x, y, w, h))
        else:
            k = radius * 0.5523
            self._op(
                "{:.2f} {:.2f} m "
                "{:.2f} {:.2f} l {:.2f} {:.2f} {:.2f} {:.2f} {:.2f} {:.2f} c "
                "{:.2f} {:.2f} l {:.2f} {:.2f} {:.2f} {:.2f} {:.2f} {:.2f} c "
                "{:.2f} {:.2f} l {:.2f} {:.2f} {:.2f} {:.2f} {:.2f} {:.2f} c "
                "{:.2f} {:.2f} l {:.2f} {:.2f} {:.2f} {:.2f} {:.2f} {:.2f} c f".format(
                    x + radius, y,
                    x + w - radius, y, x + w - radius + k, y, x + w, y + radius - k, x + w, y + radius,
                    x + w, y + h - radius, x + w, y + h - radius + k, x + w - radius + k, y + h, x + w - radius, y + h,
                    x + radius, y + h, x + radius - k, y + h, x, y + h - radius + k, x, y + h - radius,
                    x, y + radius, x, y + radius - k, x + radius - k, y, x + radius, y))

    def line(self, x1, y1, x2, y2, color=LINE, width=0.7):
        r, g, b = color
        self._op("{:.3f} {:.3f} {:.3f} RG {:.2f} w {:.2f} {:.2f} m {:.2f} {:.2f} l S"
                 .format(r, g, b, width, x1, y1, x2, y2))

    def text(self, x, y, s, size=10, bold=False, color=INK, spacing=0.0):
        s = _esc(_clean(s))
        if not s:
            return
        r, g, b = color
        self._op("BT /{} {:.2f} Tf {:.3f} {:.3f} {:.3f} rg {:.2f} Tc {:.2f} {:.2f} Td ({}) Tj ET"
                 .format("HB" if bold else "HR", size, r, g, b, spacing, x, y, s))

    # --------------------------------------------------------------- layout
    @property
    def content_width(self):
        return A4_W - MARGIN * 2

    def _new_page(self):
        if self._ops:
            self.pages.append(self._ops)
        self._ops = []
        self._banner()

    def _banner(self):
        h = 74
        self.rect(0, A4_H - h, A4_W, h, DEEP)
        self.rect(0, A4_H - h, 5, h, COPPER)
        self.text(MARGIN, A4_H - 32, self.org, 17, True, WHITE, spacing=0.6)
        self.text(MARGIN, A4_H - 49, self.tagline, 8.4, False, (0.78, 0.87, 0.90))
        if self.pages:
            self.text(MARGIN, A4_H - 65, self.title, 9, True, (0.86, 0.93, 0.95))
        self.y = A4_H - h - 26

    def space(self, n=10):
        self.y -= n

    def need(self, h):
        if self.y - h < MARGIN + 34:
            self._new_page()

    # -------------------------------------------------------------- blocks
    def doc_head(self, meta_pairs=()):
        """Big title, reference line, and a row of small meta chips."""
        self.need(70)
        for ln in wrap(self.title, self.content_width, 19, True):
            self.text(MARGIN, self.y, ln, 19, True, INK)
            self.y -= 23
        if self.subtitle:
            self.text(MARGIN, self.y, self.subtitle, 10.5, False, TEAL)
            self.y -= 16
        if meta_pairs:
            self.y -= 4
            x = MARGIN
            for label, value in meta_pairs:
                label, value = _clean(label), _clean(value)
                w = max(text_width(label, 7.4, True), text_width(value, 9.5, True)) + 20
                if x + w > A4_W - MARGIN:
                    x = MARGIN
                    self.y -= 40
                self.rect(x, self.y - 30, w, 38, WASH, 4)
                self.text(x + 10, self.y - 2, label.upper(), 7.4, True, MUTED, spacing=0.5)
                self.text(x + 10, self.y - 18, value or "-", 9.5, True, INK)
                x += w + 8
            self.y -= 44
        self.y -= 6
        self.line(MARGIN, self.y, A4_W - MARGIN, self.y)
        self.y -= 22

    def heading(self, s):
        self.need(40)
        self.text(MARGIN, self.y, _clean(s).upper(), 8.6, True, TEAL, spacing=0.9)
        self.y -= 7
        self.line(MARGIN, self.y, A4_W - MARGIN, self.y, LINE, 0.6)
        self.y -= 17

    def field(self, label, value, columns=2, _state={}):
        """A labelled value. Two per row by default."""
        col_w = (self.content_width - 18) / columns
        idx = _state.get("i", 0) % columns
        if idx == 0:
            self.need(46)
            _state["row_y"] = self.y
        x = MARGIN + idx * (col_w + 18)
        y = _state["row_y"]
        self.text(x, y, _clean(label).upper(), 7.2, True, MUTED, spacing=0.4)
        lines = wrap(value if value not in (None, "") else "-", col_w, 10)
        yy = y - 13
        for ln in lines[:4]:
            self.text(x, yy, ln, 10, False, INK)
            yy -= 12
        used = y - yy + 8
        _state["i"] = _state.get("i", 0) + 1
        if _state["i"] % columns == 0:
            self.y = min(self.y, y - max(used, 30))
        else:
            self.y = min(self.y, y - max(used, 30))
            self.y = _state["row_y"] - max(used, 30) if idx == columns - 1 else self.y

    def fields(self, pairs, columns=2):
        """Lay out label/value pairs in a tidy grid, row by row."""
        col_w = (self.content_width - 18 * (columns - 1)) / columns
        row = []
        for pair in list(pairs) + [None]:
            if pair is not None:
                row.append(pair)
            if len(row) == columns or (pair is None and row):
                heights = []
                for label, value in row:
                    heights.append(len(wrap(value if value not in (None, "") else "-", col_w, 10)[:5]))
                h = 15 + max(heights) * 12 + 8
                self.need(h)
                top = self.y
                for i, (label, value) in enumerate(row):
                    x = MARGIN + i * (col_w + 18)
                    self.text(x, top, _clean(label).upper(), 7.2, True, MUTED, spacing=0.4)
                    yy = top - 13
                    for ln in wrap(value if value not in (None, "") else "-", col_w, 10)[:5]:
                        self.text(x, yy, ln, 10, False, INK)
                        yy -= 12
                self.y = top - h
                row = []

    def paragraph(self, s, size=9.6, color=INK, gap=13):
        for ln in wrap(s, self.content_width, size):
            self.need(gap + 6)
            self.text(MARGIN, self.y, ln, size, False, color)
            self.y -= gap
        self.y -= 4

    def callout(self, label, body, color=TEAL):
        lines = wrap(body, self.content_width - 30, 9.4)
        h = 18 + len(lines) * 12 + 12
        self.need(h + 8)
        self.rect(MARGIN, self.y - h + 14, self.content_width, h, WASH, 5)
        self.rect(MARGIN, self.y - h + 14, 3.2, h, color)
        self.text(MARGIN + 14, self.y, _clean(label).upper(), 7.4, True, color, spacing=0.6)
        yy = self.y - 14
        for ln in lines:
            self.text(MARGIN + 14, yy, ln, 9.4, False, INK)
            yy -= 12
        self.y -= h + 8

    def table(self, headers, rows, widths=None, max_rows=None):
        n = len(headers)
        widths = widths or [1.0 / n] * n
        cols = [self.content_width * w for w in widths]
        if max_rows:
            rows = rows[:max_rows]

        def header_band():
            self.need(30)
            self.rect(MARGIN, self.y - 6, self.content_width, 20, WASH)
            x = MARGIN + 8
            for i, htxt in enumerate(headers):
                self.text(x, self.y, _clean(htxt).upper(), 7.2, True, MUTED, spacing=0.4)
                x += cols[i]
            self.y -= 22

        header_band()
        for r_i, row in enumerate(rows):
            cells = [wrap(str(c if c not in (None, "") else "-"), cols[i] - 12, 9)[:3]
                     for i, c in enumerate(row)]
            h = max(len(c) for c in cells) * 11 + 9
            if self.y - h < MARGIN + 34:
                self._new_page()
                header_band()
            if r_i % 2 == 1:
                self.rect(MARGIN, self.y - h + 11, self.content_width, h, (0.976, 0.984, 0.988))
            x = MARGIN + 8
            for i, cell in enumerate(cells):
                yy = self.y
                for ln in cell:
                    self.text(x, yy, ln, 9, i == 0, INK)
                    yy -= 11
                x += cols[i]
            self.y -= h
            self.line(MARGIN, self.y + 8, A4_W - MARGIN, self.y + 8, LINE, 0.5)
        self.y -= 8

    def qr(self, matrix_rows, caption="", box=104):
        """Draw a QR matrix (list of rows of 0/1) bottom-right of the current row."""
        size = len(matrix_rows)
        self.need(box + 26)
        cell = box / float(size)
        x0 = A4_W - MARGIN - box
        y0 = self.y - box + 10
        self.rect(x0 - 9, y0 - 9, box + 18, box + 18, WHITE, 5)
        self._op("0 0 0 rg")
        for r, row in enumerate(matrix_rows):
            c = 0
            while c < size:
                if row[c]:
                    start = c
                    while c < size and row[c]:
                        c += 1
                    self._op("{:.3f} {:.3f} {:.3f} {:.3f} re f".format(
                        x0 + start * cell, y0 + (size - 1 - r) * cell,
                        (c - start) * cell, cell))
                else:
                    c += 1
        lines = wrap(caption, box + 16, 7.4)[:2] if caption else []
        for i, ln in enumerate(lines):
            self.text(x0 - 8, y0 - 18 - i * 9, ln, 7.4, False, MUTED)
        # Move the cursor past the block, or the next thing drawn lands on top
        # of the code and the phone stops being able to read it.
        self.y = y0 - 18 - len(lines) * 9 - 10
        return x0 - 20            # left edge of the QR block, for text beside it

    # ----------------------------------------------------------------- save
    def _finish(self):
        if self._ops:
            self.pages.append(self._ops)
            self._ops = []

    def _page_stream(self, ops, page_no, total):
        foot = self.footer or "{} - {}".format(self.org, self.tagline)
        tail = [
            "0.851 0.878 0.898 RG 0.7 w {:.2f} {:.2f} m {:.2f} {:.2f} l S".format(
                MARGIN, MARGIN + 22, A4_W - MARGIN, MARGIN + 22),
            "BT /HR 7.6 Tf 0.404 0.451 0.502 rg {:.2f} {:.2f} Td ({}) Tj ET".format(
                MARGIN, MARGIN + 9, _esc(_clean(foot))),
        ]
        label = "Page {} of {}".format(page_no, total)
        tail.append("BT /HR 7.6 Tf 0.404 0.451 0.502 rg {:.2f} {:.2f} Td ({}) Tj ET".format(
            A4_W - MARGIN - text_width(label, 7.6), MARGIN + 9, _esc(label)))
        return "\n".join(ops + tail).encode("latin-1", "replace")

    def bytes(self):
        self._finish()
        total = len(self.pages)
        objs = []

        def add(body):
            objs.append(body)
            return len(objs)

        font_r = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        font_b = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

        pages_obj = len(objs) + 1 + total * 2 + 1     # reserved below
        page_ids, content_ids = [], []
        for i, ops in enumerate(self.pages):
            data = zlib.compress(self._page_stream(ops, i + 1, total), 9)
            cid = add(b"<< /Length " + str(len(data)).encode() + b" /Filter /FlateDecode >>\nstream\n"
                      + data + b"\nendstream")
            content_ids.append(cid)
        for i in range(total):
            pid = add(("<< /Type /Page /Parent {} 0 R /MediaBox [0 0 {:.2f} {:.2f}] "
                       "/Resources << /Font << /HR {} 0 R /HB {} 0 R >> >> /Contents {} 0 R >>"
                       ).format(pages_obj, A4_W, A4_H, font_r, font_b, content_ids[i]).encode())
            page_ids.append(pid)
        real_pages = add(("<< /Type /Pages /Count {} /Kids [{}] >>".format(
            total, " ".join("{} 0 R".format(p) for p in page_ids))).encode())
        # patch the parent reference now that the real number is known
        for i, pid in enumerate(page_ids):
            objs[pid - 1] = objs[pid - 1].replace(
                b"/Parent " + str(pages_obj).encode() + b" 0 R",
                b"/Parent " + str(real_pages).encode() + b" 0 R")
        info = add(("<< /Title ({}) /Producer (DHARANI 360) >>".format(
            _esc(self.title))).encode("latin-1", "replace"))
        catalog = add("<< /Type /Catalog /Pages {} 0 R >>".format(real_pages).encode())

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for i, body in enumerate(objs, start=1):
            offsets.append(len(out))
            out += str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n"
        xref_at = len(out)
        out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n"
        out += b"0000000000 65535 f \n"
        for off in offsets[1:]:
            out += "{:010d} 00000 n \n".format(off).encode()
        out += (b"trailer\n<< /Size " + str(len(objs) + 1).encode()
                + b" /Root " + str(catalog).encode() + b" 0 R /Info "
                + str(info).encode() + b" 0 R >>\nstartxref\n"
                + str(xref_at).encode() + b"\n%%EOF\n")
        return bytes(out)

    def save(self, path):
        with open(path, "wb") as fh:
            fh.write(self.bytes())
