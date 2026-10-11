#!/usr/bin/env python3
"""Decode a 317 old-format model from models.idx/models.dat and report stats.

Purpose: confirm the exact conventions the client's Model.method460 + private
Model(int) reader expects, by round-tripping an EXISTING known-good model:
- footer flags and section order/offsets
- whether x/y/z deltas live in three separate streams (and their section order)
- colour index ranges (palette indexing sanity)
- face winding: compute world-space normals and see whether they point outward
  (n . (faceCenter - meshCenter) > 0) so new models can match the convention.

Usage: python3 decode_model_probe.py <model_id>
"""
import struct, sys, os

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Client", "Cache")


def load_index():
    raw = open(os.path.join(CACHE, "models.idx"), "rb").read()
    count = struct.unpack(">i", raw[:4])[0]
    idx = []
    off = 4
    for _ in range(count):
        mid, ln = struct.unpack(">ii", raw[off:off+8]); off += 8
        idx.append((mid, ln))
    dat = open(os.path.join(CACHE, "models.dat"), "rb").read()
    return idx, dat


class R:
    def __init__(self, b, o=0):
        self.b = b; self.o = o
    def u8(self):
        v = self.b[self.o]; self.o += 1; return v
    def u16(self):
        v = (self.b[self.o] << 8) | self.b[self.o+1]; self.o += 2; return v
    def smart(self):
        i = self.b[self.o]
        if i < 128:
            return self.u8() - 64
        return self.u16() - 49152


def main():
    mid_want = int(sys.argv[1]) if len(sys.argv) > 1 else None
    idx, dat = load_index()
    # offsets of each entry's data within models.dat
    o = 0; entries = []
    for (mid, ln) in idx:
        entries.append((mid, o, ln)); o += ln
    if mid_want is None:
        # pick the smallest model that parses for the probe
        cand = sorted(entries, key=lambda e: e[2])
        for (mid, off, ln) in cand:
            if 100 < ln < 3000:
                mid_want = mid; break
    (mid, off, ln) = next(e for e in entries if e[0] == mid_want)
    data = dat[off:off+ln]
    print(f"model {mid}: {ln} bytes")

    r = R(data, len(data) - 18)
    nV = r.u16(); nF = r.u16(); nTex = r.u8()
    k = r.u8(); l = r.u8(); i1 = r.u8(); j1 = r.u8(); k1 = r.u8()
    l1 = r.u16(); i2 = r.u16(); j2 = r.u16(); k2 = r.u16()
    print(f"nV={nV} nF={nF} nTex={nTex} flags k,l,i1,j1,k1={k},{l},{i1},{j1},{k1}")
    print(f"section lens l1(x?)={l1} i2(y?)={i2} j2(z?)={j2} k2(uv?)={k2}")

    # replicate reader offsets (private Model(int))
    l2 = 0
    a372 = l2; l2 += nV
    a378 = l2; l2 += nF
    if l == 255: a381 = l2; l2 += nF
    else: a381 = None; 
    if j1 == 1: a383 = l2; l2 += nF
    else: a383 = None
    if k == 1: a380 = l2; l2 += nF
    else: a380 = None
    if k1 == 1: a376 = l2; l2 += nV
    else: a376 = None
    if i1 == 1: a382 = l2; l2 += nF
    else: a382 = None
    a377 = l2; l2 += k2
    a379 = l2; l2 += nF * 2
    a384 = l2; l2 += nTex * 6
    a373 = l2; l2 += l1
    a374 = l2; l2 += i2
    a375 = l2; l2 += j2
    print(f"offsets: pos={a372} faceIntro={a378} alpha={a383} tint={a380} vskin={a376} "
          f"facePrio={a382} uv={a377} colours={a379} texUV={a384} x={a373} y={a374} z={a375} end={l2}")
    print(f"data len check: reader end {l2} + footer 18 == {l2+18} vs file {len(data)}")

    # decode vertices (three delta streams like the reader)
    s0 = R(data, a372)
    sx = R(data, a373); sy = R(data, a374); sz = R(data, a375)
    ssk = R(data, a376) if a376 is not None else None
    verts = []
    cx = cy = cz = 0
    for i in range(nV):
        f = s0.u8()
        dx = sx.smart() if f & 1 else 0
        dy = sy.smart() if f & 2 else 0
        dz = sz.smart() if f & 4 else 0
        cx += dx; cy += dy; cz += dz
        if ssk: ssk.u8()
        verts.append((cx, cy, cz))
    xs = [v[0] for v in verts]; ys = [v[1] for v in verts]; zs = [v[2] for v in verts]
    print(f"verts: x[{min(xs)},{max(xs)}] y[{min(ys)},{max(ys)}] z[{min(zs)},{max(zs)}]")

    # faces
    sC = R(data, a379); sU = R(data, a378); sI = R(data, a377)
    sA = R(data, a383) if a383 is not None else None
    sT = R(data, a380) if a380 is not None else None
    sP = R(data, a382) if a382 is not None else None
    faces = []
    j2a = l2a = j3a = k3 = 0
    cols = []
    for i in range(nF):
        col = sC.u16(); cols.append(col)
        alpha = sA.u8() if sA else None
        tint = sT.u8() if sT else None
        prio = sP.u8() if sP else None
        t = sU.u8()
        if t == 1:
            a = k3 + sI.smart(); k3 = a; j2a = a
            b = k3 + sI.smart(); k3 = b; l2a = b
            c = k3 + sI.smart(); k3 = c; j3a = c
        elif t == 2:
            b = j2a; c = j3a
            a = k3 + sI.smart(); k3 = c
            j2a = c; j3a = a
        elif t == 3:
            a = j3a; b = l2a
            c = k3 + sI.smart(); k3 = c; j3a = c
        elif t == 4:
            a = l2a; b = j2a
            c = k3 + sI.smart(); k3 = c; j3a = c
        else:
            a = b = c = -1
        faces.append((a, b, c, col, prio, tint, alpha))
    print(f"colour index range: {min(cols)}..{max(cols)}  sample: {cols[:8]}")
    prios = {f[4] for f in faces}
    print("face priorities present:", prios)

    # winding analysis on closed triangles
    cxm = sum(xs)/nV; cym = sum(ys)/nV; czm = sum(zs)/nV
    out_in = [0, 0]
    for (a,b,c,col,_p,_t,_al) in faces:
        if a < 0 or b < 0 or c < 0: continue
        ax,ay,az = verts[a]; bx,by,bz = verts[b]; cxx,cyy,czz = verts[c]
        ux,uy,uz = bx-ax, by-ay, bz-az
        vx,vy,vz = cxx-ax, cyy-ay, czz-az
        nx,ny,nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        fx = (ax+bx+cxx)/3 - cxm; fy = (ay+by+cyy)/3 - cym; fz = (az+bz+czz)/3 - czm
        if nx*fx + ny*fy + nz*fz > 0: out_in[0] += 1
        else: out_in[1] += 1
    print(f"face normals outward/inward: {out_in[0]}/{out_in[1]}")


if __name__ == "__main__":
    main()
