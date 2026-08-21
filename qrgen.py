# -*- coding: utf-8 -*-
"""A complete QR Code encoder in plain Python - no packages to install.

DHARANI 360 runs offline on an office computer, so a QR code cannot be
fetched from an internet service and a pip dependency is one more thing that
can fail on a fresh machine. This module does the whole job in the standard
library: byte-mode encoding, Reed-Solomon error correction, mask selection,
and an SVG or PNG rendering of the finished matrix.

    from qrgen import qr_svg
    svg = qr_svg("http://127.0.0.1:5000/record/COR-002/14")

Supports versions 1-20 at error-correction level M, which covers any link
this system produces with a wide margin.
"""

# --------------------------------------------------------------- constants --

# Total codewords and (ec_per_block, num_blocks_group1, num_blocks_group2)
# for error-correction level M, versions 1..20.
_EC_M = {
    1:  (10, 1, 0, 16, 0),
    2:  (16, 1, 0, 28, 0),
    3:  (26, 1, 0, 44, 0),
    4:  (18, 2, 0, 32, 0),
    5:  (24, 2, 0, 43, 0),
    6:  (16, 4, 0, 27, 0),
    7:  (18, 4, 0, 31, 0),
    8:  (22, 2, 2, 38, 39),
    9:  (22, 3, 2, 36, 37),
    10: (26, 4, 1, 43, 44),
    11: (30, 1, 4, 50, 51),
    12: (22, 6, 2, 36, 37),
    13: (22, 8, 1, 37, 38),
    14: (24, 4, 5, 40, 41),
    15: (24, 5, 5, 41, 42),
    16: (28, 7, 3, 45, 46),
    17: (28, 10, 1, 46, 47),
    18: (26, 9, 4, 43, 44),
    19: (26, 3, 11, 44, 45),
    20: (26, 3, 13, 41, 42),
}

# Row 1 of the alignment-pattern coordinate table, versions 1..20.
_ALIGN = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
    7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
    11: [6, 30, 54], 12: [6, 32, 58], 13: [6, 34, 62],
    14: [6, 26, 46, 66], 15: [6, 26, 48, 70], 16: [6, 26, 50, 74],
    17: [6, 30, 54, 78], 18: [6, 30, 56, 82], 19: [6, 30, 58, 86],
    20: [6, 34, 62, 90],
}


class QRError(ValueError):
    pass


# ------------------------------------------------------------------ GF(256) --

_EXP = [0] * 512
_LOG = [0] * 256


def _init_tables():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_tables()


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(degree):
    poly = [1]
    for i in range(degree):
        nxt = [0] * (len(poly) + 1)
        for j, c in enumerate(poly):
            nxt[j] ^= _gf_mul(c, 1)
            nxt[j + 1] ^= _gf_mul(c, _EXP[i])
        poly = nxt
    return poly


def _rs_encode(data, ec_len):
    gen = _rs_generator(ec_len)
    rem = [0] * ec_len
    for byte in data:
        factor = byte ^ rem[0]
        rem = rem[1:] + [0]
        for i, g in enumerate(gen[1:]):
            rem[i] ^= _gf_mul(g, factor)
    return rem


# --------------------------------------------------------------- bit buffer --

class _Bits(object):
    def __init__(self):
        self.bits = []

    def put(self, value, length):
        for i in range(length - 1, -1, -1):
            self.bits.append((value >> i) & 1)

    def __len__(self):
        return len(self.bits)


# ------------------------------------------------------------------ encoder --

def _capacity_bits(version):
    ec_per_block, g1, g2, dc1, dc2 = _EC_M[version]
    return (g1 * dc1 + g2 * dc2) * 8


def _pick_version(nbytes):
    for v in range(1, 21):
        count_bits = 8 if v < 10 else 16
        needed = 4 + count_bits + nbytes * 8
        if needed <= _capacity_bits(v):
            return v
    raise QRError("Too much data for a version-20 QR code ({} bytes)".format(nbytes))


def _encode_data(text, version):
    raw = text.encode("utf-8")
    count_bits = 8 if version < 10 else 16
    buf = _Bits()
    buf.put(0b0100, 4)                 # byte mode
    buf.put(len(raw), count_bits)
    for b in raw:
        buf.put(b if isinstance(b, int) else ord(b), 8)

    cap = _capacity_bits(version)
    if len(buf) > cap:
        raise QRError("data does not fit the chosen version")

    # terminator, then pad to a byte boundary, then the alternating pad bytes
    buf.put(0, min(4, cap - len(buf)))
    while len(buf) % 8:
        buf.bits.append(0)
    data = bytearray()
    for i in range(0, len(buf), 8):
        byte = 0
        for bit in buf.bits[i:i + 8]:
            byte = (byte << 1) | bit
        data.append(byte)
    pads = (0xEC, 0x11)
    i = 0
    while len(data) * 8 < cap:
        data.append(pads[i % 2])
        i += 1
    return bytes(data)


def _interleave(data, version):
    ec_len, g1, g2, dc1, dc2 = _EC_M[version]
    blocks, ecs = [], []
    pos = 0
    for _ in range(g1):
        blocks.append(data[pos:pos + dc1]); pos += dc1
    for _ in range(g2):
        blocks.append(data[pos:pos + dc2]); pos += dc2
    for b in blocks:
        ecs.append(_rs_encode(b, ec_len))

    out = bytearray()
    for i in range(max(len(b) for b in blocks)):
        for b in blocks:
            if i < len(b):
                out.append(b[i])
    for i in range(ec_len):
        for e in ecs:
            out.append(e[i])
    return bytes(out)


# ------------------------------------------------------------------- matrix --

def _new_matrix(size):
    return [[None] * size for _ in range(size)]


def _place_finder(m, r, c):
    size = len(m)
    for dr in range(-1, 8):
        for dc in range(-1, 8):
            rr, cc = r + dr, c + dc
            if not (0 <= rr < size and 0 <= cc < size):
                continue
            inner = 2 <= dr <= 4 and 2 <= dc <= 4
            ring = dr in (0, 6) or dc in (0, 6)
            border = dr in (-1, 7) or dc in (-1, 7)
            m[rr][cc] = 0 if border else (1 if (ring or inner) else 0)


def _place_alignment(m, version):
    coords = _ALIGN[version]
    size = len(m)
    for r in coords:
        for c in coords:
            if (r < 8 and c < 8) or (r < 8 and c > size - 9) or (r > size - 9 and c < 8):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    ring = max(abs(dr), abs(dc))
                    m[r + dr][c + dc] = 1 if ring != 1 else 0


def _place_timing(m):
    size = len(m)
    for i in range(8, size - 8):
        bit = 1 if i % 2 == 0 else 0
        if m[6][i] is None:
            m[6][i] = bit
        if m[i][6] is None:
            m[i][6] = bit


def _reserve_format(m, version):
    size = len(m)
    for i in range(9):
        if m[8][i] is None:
            m[8][i] = 0
        if m[i][8] is None:
            m[i][8] = 0
    for i in range(8):
        m[8][size - 1 - i] = 0
        m[size - 1 - i][8] = 0
    m[size - 8][8] = 1                      # the always-dark module
    if version >= 7:
        for i in range(6):
            for j in range(3):
                m[size - 11 + j][i] = 0
                m[i][size - 11 + j] = 0


def _place_data(m, stream):
    size = len(m)
    bits = []
    for byte in stream:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    idx = 0
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for c in (col, col - 1):
                if m[row][c] is None:
                    m[row][c] = bits[idx] if idx < len(bits) else 0
                    idx += 1
        upward = not upward
        col -= 2


_MASKS = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]


def _is_function(version, size, r, c):
    if r < 9 and c < 9:
        return True
    if r < 9 and c >= size - 8:
        return True
    if r >= size - 8 and c < 9:
        return True
    if r == 6 or c == 6:
        return True
    if version >= 7 and ((r < 6 and c >= size - 11) or (c < 6 and r >= size - 11)):
        return True
    for ar in _ALIGN[version]:
        for ac in _ALIGN[version]:
            if (ar < 8 and ac < 8) or (ar < 8 and ac > size - 9) or (ar > size - 9 and ac < 8):
                continue
            if abs(r - ar) <= 2 and abs(c - ac) <= 2:
                return True
    return False


def _penalty(m):
    size = len(m)
    score = 0
    # rule 1 - runs of five or more
    for line in list(m) + [list(col) for col in zip(*m)]:
        run, prev = 1, line[0]
        for v in line[1:]:
            if v == prev:
                run += 1
            else:
                if run >= 5:
                    score += 3 + (run - 5)
                run, prev = 1, v
        if run >= 5:
            score += 3 + (run - 5)
    # rule 2 - 2x2 blocks
    for r in range(size - 1):
        for c in range(size - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    # rule 3 - finder-like patterns
    pat1 = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    pat2 = [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]
    for line in list(m) + [list(col) for col in zip(*m)]:
        for i in range(size - 10):
            seg = line[i:i + 11]
            if seg == pat1 or seg == pat2:
                score += 40
    # rule 4 - dark/light balance
    dark = sum(sum(row) for row in m)
    pct = dark * 100 // (size * size)
    score += 10 * (abs(pct - 50) // 5)
    return score


_FORMAT_GEN = 0b10100110111
_FORMAT_MASK = 0b101010000010010


def _format_bits(mask):
    # level M is 0b00
    data = (0b00 << 3) | mask
    rem = data << 10
    for i in range(14, 9, -1):
        if rem & (1 << i):
            rem ^= _FORMAT_GEN << (i - 10)
    return ((data << 10) | rem) ^ _FORMAT_MASK


_VERSION_GEN = 0b1111100100101


def _version_bits(version):
    rem = version << 12
    for i in range(17, 11, -1):
        if rem & (1 << i):
            rem ^= _VERSION_GEN << (i - 12)
    return (version << 12) | rem


def _apply_format(m, version, mask):
    size = len(m)
    fb = _format_bits(mask)
    # bit 14 (most significant) is the first module of the sequence
    bits = [(fb >> i) & 1 for i in range(14, -1, -1)]
    # copy one: along row 8, then up column 8
    for i in range(6):
        m[8][i] = bits[i]
    m[8][7] = bits[6]
    m[8][8] = bits[7]
    m[7][8] = bits[8]
    for i in range(9, 15):
        m[14 - i][8] = bits[i]
    # copy two: up column 8 from the bottom, then along row 8 from the right
    for i in range(7):
        m[size - 1 - i][8] = bits[i]
    for i in range(8):
        m[8][size - 8 + i] = bits[7 + i]
    m[size - 8][8] = 1
    if version >= 7:
        vb = _version_bits(version)
        for i in range(18):
            bit = (vb >> i) & 1
            m[i // 3][size - 11 + i % 3] = bit
            m[size - 11 + i % 3][i // 3] = bit


def matrix(text):
    """Return the finished QR matrix as a list of rows of 0/1."""
    raw_len = len(text.encode("utf-8"))
    version = _pick_version(raw_len)
    size = version * 4 + 17

    data = _encode_data(text, version)
    stream = _interleave(data, version)

    base = _new_matrix(size)
    _place_finder(base, 0, 0)
    _place_finder(base, 0, size - 7)
    _place_finder(base, size - 7, 0)
    _place_alignment(base, version)
    _place_timing(base)
    _reserve_format(base, version)
    _place_data(base, stream)

    best, best_score = None, None
    for mask in range(8):
        cand = [row[:] for row in base]
        fn = _MASKS[mask]
        for r in range(size):
            for c in range(size):
                if not _is_function(version, size, r, c) and fn(r, c):
                    cand[r][c] ^= 1
        _apply_format(cand, version, mask)
        score = _penalty(cand)
        if best_score is None or score < best_score:
            best, best_score = cand, score
    return best


# ----------------------------------------------------------------- renderers --

def qr_svg(text, scale=6, quiet=4, dark="#0b2b33", light="#ffffff", title=None):
    """QR code as a standalone SVG string - crisp at any size, tiny on the wire."""
    m = matrix(text)
    size = len(m)
    total = (size + quiet * 2) * scale
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{0}" '
        'viewBox="0 0 {0} {0}" shape-rendering="crispEdges" role="img">'.format(total)
    ]
    if title:
        parts.append("<title>{}</title>".format(
            title.replace("&", "&amp;").replace("<", "&lt;")))
    parts.append('<rect width="{0}" height="{0}" fill="{1}"/>'.format(total, light))
    path = []
    for r, row in enumerate(m):
        c = 0
        while c < size:
            if row[c]:
                start = c
                while c < size and row[c]:
                    c += 1
                path.append("M{} {}h{}v{}h-{}z".format(
                    (start + quiet) * scale, (r + quiet) * scale,
                    (c - start) * scale, scale, (c - start) * scale))
            else:
                c += 1
    parts.append('<path fill="{}" d="{}"/>'.format(dark, "".join(path)))
    parts.append("</svg>")
    return "".join(parts)


def qr_png(text, scale=6, quiet=4):
    """QR code as PNG bytes, written with zlib and struct only."""
    import struct
    import zlib
    m = matrix(text)
    size = len(m)
    px = (size + quiet * 2) * scale

    rows = []
    for r in range(px):
        line = bytearray([0])                       # filter type 0
        mr = r // scale - quiet
        for c in range(px):
            mc = c // scale - quiet
            on = 0 <= mr < size and 0 <= mc < size and m[mr][mc]
            line.append(0 if on else 255)
        rows.append(bytes(line))
    raw = b"".join(rows)

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", px, px, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))
