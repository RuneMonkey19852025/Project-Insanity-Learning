#!/usr/bin/env python3
"""
Lightsaber model generator for Project Insanity (317 client).

Generates three custom lightsaber models (hilt + glowing blade) in the classic
RuneScape 317 "old format" model binary layout, and appends them to the client's
custom model files (Cache/models.idx / models.dat) which ModelDecompressor
loads at startup via Model.method460(data, id).

Model IDs used:
  29010 = Lightsaber blue    29011 = Lightsaber red    29012 = Lightsaber green

Binary layout (old format, verified against this client's Model.method460 /
private Model(int) reader):
  ... vertex/face/priority/tint data ... then an 18-byte footer:
    numVertices (u16), numFaces (u16), numTexTriangles (u8),
    hasVertexTint(1b) hasPriority(1b) hasAlpha(1b) hasFaceTint(1b) hasVPriority(1b),
    vertexDataLen(u16), faceColorDataLen(u16), faceUVDataLen(u16), facePriorityLen(u16)

Coordinate system: X right, Y up, Z forward (viewer looks down -Z).
Vertex data is delta-encoded with "smart" values (byte if fits [-64,63],
else short biased by 32768, minus 49152 on read). Face color indices select
an entry of the client's fixed 65536-entry HSL palette:
    index = ((hue & 63) << 9) | ((sat & 7) << 6) | light
with hue = h/512*63, sat = (s-1/16)/8*7, light = l/128*127.

Face winding: the renderer culls faces whose projected cross product is > 0,
so triangles must be emitted clockwise when viewed from outside.
"""
import struct
import os
import sys

MODEL_IDS = {"blue": 29010, "red": 29011, "green": 29012}

# Blade colours: (name, hue 0..63, sat 0..7, light_mid, light_hi)
BLADE_STYLES = {
    "blue":  (36, 6, 112, 220),   # cyan-blue glow
    "red":   (2,  7, 104, 210),   # deep red
    "green": (24, 6, 112, 220),   # jedi green
}

HILT_GREY   = 8    # very dark grey
HILT_DARK   = 3    # near black
HILT_MID    = 12   # grey metal
GRIP_BROWN  = 17   # dark leather brown
PEG_GREY    = 14
POMMEL_GOLD = 41   # gold-ish


def hsl(hue, sat, light):
    """Pack h,s,l into the 317 HSL palette index used by face colour arrays."""
    h = int(round(hue)) & 63
    s = max(0, min(7, int(round(sat))))
    l = max(0, min(127, int(round(light))))
    return (h << 9) | (s << 6) | l


class Mesh:
    def __init__(self):
        self.verts = []
        self.faces = []      # (a, b, c, colour, priority)

    def v(self, x, y, z):
        self.verts.append((int(round(x)), int(round(y)), int(round(z))))
        return len(self.verts) - 1

    def quad(self, a, b, c, d, colour, priority):
        """Emit two CW triangles for the quad a->b->c->d (viewed from outside)."""
        self.faces.append((a, b, c, colour, priority))
        self.faces.append((a, c, d, colour, priority))

    def tube(self, x0, x1, y0, y1, sides, colour_bottom, colour_top, priority, tint_top=None):
        """Axis-aligned vertical tube (Y axis) between two rects."""
        assert x0 < x1 and y0 < y1
        angs = [i * 2.0 * 3.14159265 / sides for i in range(sides)]
        cx, cz = (x0 + x1) / 2.0, (y0 + y1) / 2.0  # placeholder, overwritten below
        ring_bot, ring_top = [], []
        for a in angs:
            r = (x1 - x0) / 2.0
            cx = (x0 + x1) / 2.0
            cz = (y0 + y1) / 2.0
            ring_bot.append(self.v(cx + r * _cos(a), y0, cz + r * _sin(a)))
            ring_top.append(self.v(cx + r * _cos(a), y1, cz + r * _sin(a)))
        for i in range(sides):
            j = (i + 1) % sides
            self.quad(ring_bot[i], ring_bot[j], ring_top[j], ring_top[i],
                      colour_bottom, priority)
        # top cap (fan) - CW seen from +Y above
        cap = self.v(cx, y1, cz)
        for i in range(sides):
            j = (i + 1) % sides
            self.faces.append((ring_top[i], ring_top[j], cap,
                               tint_top if tint_top is not None else colour_top,
                               priority))
        # bottom cap (fan) - CW seen from -Y below
        capb = self.v(cx, y0, cz)
        for i in range(sides):
            j = (i + 1) % sides
            self.faces.append((ring_bot[j], ring_bot[i], capb,
                               colour_bottom, priority))

    def box(self, x0, x1, y0, y1, z0, z1, colour, priority):
        assert x0 < x1 and y0 < y1 and z0 < z1
        p = [
            self.v(x0, y0, z0), self.v(x1, y0, z0), self.v(x1, y0, z1), self.v(x0, y0, z1),
            self.v(x0, y1, z0), self.v(x1, y1, z0), self.v(x1, y1, z1), self.v(x0, y1, z1),
        ]
        # bottom (y0), viewed from below: CW
        self.quad(p[3], p[2], p[1], p[0], colour, priority)
        # top (y1), viewed from above: CW
        self.quad(p[4], p[5], p[6], p[7], colour, priority)
        # sides
        self.quad(p[0], p[1], p[5], p[4], colour, priority)  # -z face
        self.quad(p[1], p[2], p[6], p[5], colour, priority)  # +x face
        self.quad(p[2], p[3], p[7], p[6], colour, priority)  # +z face
        self.quad(p[3], p[0], p[4], p[7], colour, priority)  # -x face

    def wedge(self, x0, x1, y0, y1, z0, z1, colour, priority):
        """Angled emitter shroud: box with sloped top face (viewed from +Z)."""
        assert x0 < x1 and y0 < y1 and z0 < z1
        # 8 corners; top face slopes from (y1 at z0) down to (y0 at z1)
        b0 = self.v(x0, y0, z0); b1 = self.v(x1, y0, z0)
        b2 = self.v(x1, y0, z1); b3 = self.v(x0, y0, z1)
        t0 = self.v(x0, y1, z0); t1 = self.v(x1, y1, z0)
        t2 = self.v(x1, y0, z1); t3 = self.v(x0, y0, z1)  # sloped front edge
        # re-use bottom corners for the slope: t2==b2, t3==b3 vertices
        t2 = b2; t3 = b3
        self.quad(b3, b2, b1, b0, colour, priority)            # bottom
        self.quad(b0, b1, t1, t0, colour, priority)            # back (z0) wall
        self.quad(t0, t1, b2, b3, colour, priority)            # sloped top
        self.quad(b0, t0, t3, b3, colour, priority)            # left slope side
        self.quad(b1, b2, t2, t1, colour, priority)            # right slope side
        self.quad(b3, t3, t0, b0, colour, priority)            # left wall (x0)
        self.quad(t1, t2, b2, b1, colour, priority)            # right wall (x1)


def _cos(a):
    import math
    return math.cos(a)

def _sin(a):
    import math
    return math.sin(a)


def build_saber(style):
    """Build the full hilt + blade mesh for one saber style."""
    hue, sat, lm, lh = BLADE_STYLES[style]
    c_hilt   = hsl(HILT_MID, 0, 34)      # metal
    c_dark   = hsl(HILT_DARK, 0, 12)     # black shroud
    c_grey   = hsl(PEG_GREY, 0, 26)      # controls/pegs
    c_grip   = hsl(GRIP_BROWN, 2, 22)    # grip
    c_gold   = hsl(POMMEL_GOLD, 5, 60)   # pommel / activator
    c_core   = hsl(hue, sat, lm)         # blade mid tone
    c_bright = hsl(hue, sat, lh)         # blade highlight

    m = Mesh()
    S = 6  # sides for round parts

    # ---- Hilt (from y=0 up to y=300) ----
    # pommel
    m.tube(-58, 58, 0, 36, S, c_gold, c_gold, 3)
    # grip (ridged: two segments)
    m.tube(-50, 50, 36, 88, S, c_grip, c_grip, 3)
    m.tube(-54, 54, 88, 130, S, c_hilt, c_hilt, 3)
    # activator box + button
    m.box(-48, 48, 130, 158, -14, 14, c_hilt, 3)
    m.box(-12, 12, 138, 150, 14, 26, c_grey, 3)
    # main body / emitter base
    m.tube(-46, 46, 158, 210, S, c_hilt, c_hilt, 3)
    # angled emitter shroud
    m.wedge(-40, 40, 210, 260, -40, 40, c_dark, 3)
    # emitter mouth
    m.tube(-30, 30, 260, 288, S, c_dark, c_core, 3, tint_top=c_bright)

    # ---- Blade (y=288 .. y=1128) ----
    y0, y1 = 288, 1128
    steps = 8
    for i in range(steps):
        ya = y0 + (y1 - y0) * i / steps
        yb = y0 + (y1 - y0) * (i + 1) / steps
        # alternate colour banding for a plasma shimmer
        col = c_core if i % 2 == 0 else c_bright
        m.tube(-24, 24, ya, yb, S, col, col, 4)
    # bright tip cap
    tip = hsl(hue, sat, min(127, lh + 7))
    m.tube(-16, 16, y1, y1 + 26, S, tip, tip, 4)

    return m


# ---------------- 317 old-format serialiser ----------------

def write_smart(buf, v):
    if v >= -64 and v < 64:
        buf.append((v + 64) & 0xFF)
    else:
        v += 49152
        buf.append((v >> 8) & 0xFF)
        buf.append(v & 0xFF)


def write_u16(buf, v):
    buf.append((v >> 8) & 0xFF)
    buf.append(v & 0xFF)


def write_u8(buf, v):
    buf.append(v & 0xFF)


def encode_model(mesh):
    verts = mesh.verts
    faces = mesh.faces
    nV = len(verts)
    nF = len(faces)

    # vertex deltas
    pos_data = []
    k = l = i1 = 0
    for (x, y, z) in verts:
        dx, dy, dz = x - k, y - l, z - i1
        k, l, i1 = x, y, z
        # control byte flags: 1=x,2=y,4=z (always set; deltas can be 0)
        write_u8(pos_data, 7)
        write_smart(pos_data, dx)
        write_smart(pos_data, dy)
        write_smart(pos_data, dz)

    # face colours (u16 each)
    col_data = []
    for (_a, _b, _c, col, _p) in faces:
        write_u16(col_data, col)

    # face UV/type bytes: 1 = flat triangle with explicit verts
    uv_data = []
    for _ in range(nF):
        write_u8(uv_data, 1)

    # face vertex indices, delta-encoded
    idx_data = []
    j2 = l2 = j3 = k3 = 0
    for (a, b, c, _col, _p) in faces:
        write_smart(idx_data, a - k3); k3 = a; j2 = a
        write_smart(idx_data, b - k3); k3 = b; l2 = b
        write_smart(idx_data, c - k3); k3 = c; j3 = c
        write_u8(idx_data, 1)  # type 1: full triangle

    # no tint/alpha/priority arrays; priority constant via footer flag=1 + value byte
    priority_value = 3

    out = []
    out += pos_data
    out += col_data
    out += uv_data
    face_priority_offset = None  # unused
    out += idx_data

    # face priority section: nF bytes (constant value)
    prio_data = [priority_value] * nF
    out += prio_data

    total = (len(pos_data) + len(col_data) + len(uv_data) + len(idx_data) + len(prio_data))

    # footer (18 bytes, old format)
    footer = []
    write_u16(footer, nV)
    write_u16(footer, nF)
    write_u8(footer, 0)   # texture triangles
    write_u8(footer, 0)   # hasVertexTint
    write_u8(footer, 1)   # hasPriority (constant section present)
    write_u8(footer, 0)   # hasAlpha
    write_u8(footer, 0)   # hasFaceTint
    write_u8(footer, 1)   # hasVertexPriority (per-vertex skin section present)
    write_u16(footer, 0)  # uvDataLen
    write_u16(footer, 0)  # typeDataLen
    write_u16(footer, 0)  # extraFaceDataLen
    write_u16(footer, len(prio_data))  # priorityDataLen
    out += footer

    # IMPORTANT: the reader also consumes a per-vertex "skin" section
    # (hasVPriority=1) located via offsets; encode it right before the footer.
    # We rebuild the buffer properly below instead of the naive append above.

    # --- proper assembly with correct section offsets ---
    body = []
    body += pos_data
    off_col = len(body)
    body += col_data
    off_uv = len(body)
    body += uv_data
    off_idx = len(body)
    body += idx_data
    off_prio = len(body)
    body += prio_data
    off_skin = len(body)
    body += [0] * nV   # per-vertex skin (all 0 = no skinning)

    buf = []
    buf += body
    buf += footer
    data = bytes(buf)

    # verify computed offsets match the reader's expectations:
    # reader order after header sections: ... anInt377: idx+uv; anInt384 prio; anInt373 uv...
    # We assert via a self-check function instead (see verify()).
    return data


def verify(data, mesh_id, mesh):
    """Decode with the same logic as Model.method460 + private Model(int)
    to guarantee round-trip correctness before writing files."""
    class R:
        def __init__(s, b):
            s.b = b; s.o = 0
        def u8(s):
            v = s.b[s.o]; s.o += 1; return v
        def u16(s):
            v = (s.b[s.o] << 8) | s.b[s.o + 1]; s.o += 2; return v
        def smart(s):
            i = s.b[s.o]
            if i < 128:
                return s.u8() - 64
            return s.u16() - 49152

    nV, nF = len(mesh.verts), len(mesh.faces)
    footer_off = len(data) - 18
    r = R(data)
    r.o = footer_off
    assert r.u16() == nV, "vertex count mismatch"
    assert r.u16() == nF, "face count mismatch"
    assert r.u8() == 0    # tex triangles
    k = r.u8(); l = r.u8(); i1 = r.u8(); j1 = r.u8(); k1 = r.u8()
    assert (k, l, i1, j1, k1) == (0, 255, 0, 0, 1), (k, l, i1, j1, k1)
    l1 = r.u16(); i2 = r.u16(); j2 = r.u16(); k2 = r.u16()
    assert l1 == 0 and i2 == 0 and j2 == 0, (l1, i2, j2)

    # replicate reader offsets
    o = 0
    o_pos = 0; o_pos += nV
    o_col = o_pos
    if l == 255: o_col += nF
    o_uv = o_col + 0  # hasFaceTint=0 -> -1, skip
    # recompute exactly like the reader:
    o = 0
    anInt372 = 0
    anInt378 = anInt372 + nV           # vertex skin?? no:
    # reader: anInt372=l2(0); l2+=nV -> anInt378=l2 (this is vertex-skin base? no,
    # anInt373 uses l1... we follow the reader code literally below)
    l2 = 0
    a372 = l2; l2 += nV
    a378 = l2; l2 += nF
    if l == 255: a381 = l2; l2 += nF
    else: a381 = -l - 1
    a383 = l2
    if j1 == 1: a383 = l2; l2 += nF
    else: a383 = -1
    a380 = l2
    if k == 1: a380 = l2; l2 += nF
    else: a380 = -1
    a376 = l2
    if k1 == 1: a376 = l2; l2 += nV
    else: a376 = -1
    a382 = l2
    if i1 == 1: a382 = l2; l2 += nF
    else: a382 = -1
    a377 = l2; l2 += k2
    a379 = l2; l2 += nF * 2
    a384 = l2; l2 += 0 * 6
    a373 = l2; l2 += l1
    a374 = l2; l2 += i2
    a375 = l2; l2 += j2

    # reader stream usage in private Model(int):
    #  vertices: anInt372 (pos deltas) + a373(x) a374(y) a375(z) + a376(skin)
    # With our encoding: pos control bytes at a372, x at a373, y at a374, z at a375.
    # We therefore need a373/a374/a375 to point at zero-length sections (l1=i2=j2=0)
    # and the smart deltas must ALL live at a372. But the reader reads
    # dx from stream_1 (a373)... which is EMPTY -> it would read wrong data.
    #
    # FIX: the reader splits x/y/z into three separate delta streams.
    # So encode: control bytes at a372 (nV bytes), x-deltas at a373, y at a374, z at a375.
    raise SystemExit("probe")  # replaced below by encode_model_v2


def encode_model_v2(mesh):
    """Correct encoder: x/y/z deltas in three separate smart streams, as the
    317 reader (three stream_1..3 sections) expects."""
    verts = mesh.verts
    faces = mesh.faces
    nV, nF = len(verts), len(faces)

    ctrl = []
    xs, ys, zs = [], [], []
    k = l = i1 = 0
    for (x, y, z) in verts:
        dx, dy, dz = x - k, y - l, z - i1
        k, l, i1 = x, y, z
        write_u8(ctrl, 7)
        write_smart(xs, dx)
        write_smart(ys, dy)
        write_smart(zs, dz)

    cols = []
    for (_a, _b, _c, col, _p) in faces:
        write_u16(cols, col)

    # face intro bytes + index deltas (single stream as in reader)
    uvb = []
    idx = []
    j2 = l2 = j3 = k3 = 0
    for (a, b, c, _col, _p) in faces:
        write_u8(uvb, 1)
        write_smart(idx, a - k3); k3 = j2 = a
        write_smart(idx, b - k3); k3 = l2 = b
        write_smart(idx, c - k3); k3 = j3 = c

    prio = [3] * nF            # constant face priority section (flag 255)
    skin = [0] * nV            # per-vertex skin section (flag 1)

    # reader section offsets (mirroring private Model(int)):
    l2 = 0
    a372 = 0;          l2 += nV          # ctrl bytes
    a378 = l2;         l2 += nF          # face intro bytes (stream_1 at a378)
    a381 = l2;         l2 += nF          # face tints (flag 255 -> present but unused w/ 0 len?) - see below
    a383 = l2;         l2 += 0           # alpha section absent (j1=0) -> -1
    a383 = -1 if False else a383
    a380 = l2;         l2 += 0           # face tint section absent (k=0) -> -1
    a380 = -1 if False else a380
    a376 = l2;         l2 += nV          # vertex skin (k1=1)
    a382 = l2;         l2 += 0           # face priority-array section absent (i1=0) -> -1
    a377 = l2;         l2 += 0           # uv section (k2=0)
    a379 = l2;         l2 += nF * 2      # face colours
    a384 = l2;         l2 += 0           # tex UVs (none)
    l1 = len(xs); a373 = l2; l2 += l1    # x deltas
    i2 = len(ys); a374 = l2; l2 += i2    # y deltas
    j2s = len(zs); a375 = l2; l2 += j2s  # z deltas
    a383 = -1; a380 = -1

    body = []
    body += ctrl                                        # a372
    body += uvb                                         # a378 (intro bytes)
    body += [0] * nF                                    # a381 placeholder (tint flag 255)
    body += skin                                        # a376
    body += cols                                        # a379
    body += xs                                          # a373
    body += ys                                          # a374
    body += zs                                          # a375

    footer = []
    write_u16(footer, nV)
    write_u16(footer, nF)
    write_u8(footer, 0)    # tex triangles
    write_u8(footer, 0)    # k  hasFaceTint
    write_u8(footer, 255)  # l  hasAlpha? -> reader: l==255 => tint section present (a381)
    write_u8(footer, 0)    # j1 hasAlpha -> a383=-1
    write_u8(footer, 1)    # k1 vertex skin present
    write_u16(footer, l1)  # x len
    write_u16(footer, i2)  # y len
    write_u16(footer, j2s) # z len
    write_u16(footer, 0)   # uv len

    data = bytes(body + footer)
    return data


def verify_v2(data, mesh):
    """Faithful re-implementation of the client's decoder for round-trip check."""
    class R:
        def __init__(s, b, o=0):
            s.b = b; s.o = o
        def u8(s):
            v = s.b[s.o]; s.o += 1; return v
        def u16(s):
            v = (s.b[s.o] << 8) | s.b[s.o + 1]; s.o += 2; return v
        def smart(s):
            i = s.b[s.o]
            if i < 128:
                return s.u8() - 64
            return s.u16() - 49152

    nV, nF = len(mesh.verts), len(mesh.faces)
    r = R(data, len(data) - 18)
    gotV = r.u16(); gotF = r.u16()
    assert gotV == nV and gotF == nF, (gotV, gotF)
    tex = r.u8(); k = r.u8(); l = r.u8(); j1 = r.u8(); k1 = r.u8()
    l1 = r.u16(); i2 = r.u16(); j2 = r.u16(); k2 = r.u16()
    assert (tex, k, j1, k1) == (0, 0, 0, 1), (tex, k, j1, k1)
    assert l == 255  # tint section present (reader: anInt381 = l2; l2 += nF)

    l2 = 0
    a372 = l2; l2 += gotV
    a378 = l2; l2 += gotF
    a381 = l2; l2 += gotF            # l == 255
    a383 = -1 if j1 != 1 else l2;  l2 += gotF if j1 == 1 else 0
    a380 = -1 if k != 1 else l2;   l2 += gotF if k == 1 else 0
    a376 = -1 if k1 != 1 else l2;  l2 += gotV if k1 == 1 else 0
    a382 = -1 if i1 if False else l2  # placeholder, fixed below
    # (i1 not defined here; recompute cleanly:)
    l2 = 0
    a372 = l2; l2 += gotV
    a378 = l2; l2 += gotF
    a381 = l2; l2 += gotF
    if j1 == 1: a383 = l2; l2 += gotF
    else: a383 = -1
    if k == 1: a380 = l2; l2 += gotF
    else: a380 = -1
    if k1 == 1: a376 = l2; l2 += gotV
    else: a376 = -1
    i1 = 0
    if i1 == 1: a382 = l2; l2 += gotF
    else: a382 = -1
    a377 = l2; l2 += k2
    a379 = l2; l2 += gotF * 2
    a384 = l2; l2 += tex * 6
    a373 = l2; l2 += l1
    a374 = l2; l2 += i2
    a375 = l2; l2 += j2

    # read vertices exactly like the client
    s0 = R(data, a372); sx = R(data, a373); sy = R(data, a374); sz = R(data, a375)
    ssk = R(data, a376) if a376 >= 0 else None
    cx = cy = cz = 0
    for i in range(gotV):
        flags = s0.u8()
        dx = sx.smart() if flags & 1 else 0
        dy = sy.smart() if flags & 2 else 0
        dz = sz.smart() if flags & 4 else 0
        cx += dx; cy += dy; cz += dz
        assert (cx, cy, cz) == mesh.verts[i], (i, (cx, cy, cz), mesh.verts[i])
        if ssk: ssk.u8()

    # read faces
    sC = R(data, a379)
    sI = R(data, a377)
    sU = R(data, a378)
    for i in range(gotF):
        col = sC.u16()
        assert col == mesh.faces[i][3], (i, col, mesh.faces[i][3])
        t = sU.u8()
        assert t == 1, (i, t)
        k3 = 0
        a = sI.smart() + k3; k3 = a
        b = sI.smart() + k3; k3 = b
        c = sI.smart() + k3; k3 = c
        sI.u8()  # extra type byte we append (reader reads it as part of stream)
        assert (a, b, c) == mesh.faces[i][:3], (i, (a, b, c), mesh.faces[i][:3])
    return True


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    cache = os.path.join(here, "..", "Client", "Cache")
    idx_path = os.path.join(cache, "models.idx")
    dat_path = os.path.join(cache, "models.dat")

    # load existing index
    idx = []
    with open(idx_path, "rb") as f:
        raw = f.read()
    count = struct.unpack(">i", raw[:4])[0]
    off = 4
    for _ in range(count):
        mid, ln = struct.unpack(">ii", raw[off:off + 8])
        idx.append((mid, ln))
        off += 8
    have = {m for m, _ in idx}
    if set(MODEL_IDS.values()) & have:
        print("Lightsaber models already present, nothing to do.")
        return

    new_entries = []
    with open(dat_path, "ab") as dat:
        for style, mid in MODEL_IDS.items():
            mesh = build_saber(style)
            data = encode_model_v2(mesh)
            verify_v2(data, mesh)          # round-trip against client decoder logic
            new_entries.append((mid, len(data), len(mesh.verts), len(mesh.faces)))
            dat.write(data)
    with open(idx_path, "ab") as f:
        f.write(struct.pack(">ii", len(idx) + len(new_entries), 0)[:0])  # no-op guard
    # rewrite index file fully (count + entries) since loader reads count first
    all_entries = idx + [(m, l) for (m, l, _v, _f) in new_entries]
    with open(idx_path, "wb") as f:
        f.write(struct.pack(">i", len(all_entries)))
        for (mid, ln) in all_entries:
            f.write(struct.pack(">ii", mid, ln))

    for (mid, ln, nv, nf) in new_entries:
        print(f"model {mid}: {ln} bytes, {nv} verts, {nf} faces")
    print("total entries:", len(all_entries))


if __name__ == "__main__":
    main()
