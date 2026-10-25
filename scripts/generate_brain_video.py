"""Generate the HD 3D Spinning Brain hero video (assets/hero-brain-3d.mp4) - v2.

Upgrades vs v1: 1920x1080, Fibonacci-sampled cortex (~2,200 nodes, even density),
cerebellum + brainstem + deep nuclei, rim-light shading, 2x supersampling (anti-aliasing)
and a bloom pass for the glowing synaptic network. Seamless 360-degree loop.
"""
import math
import os
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_MP4 = os.path.join(ROOT, "assets", "hero-brain-3d.mp4")
FFMPEG = r"C:\Users\jasme\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.EXE"

W, H = 1920, 1080
SS = 2                       # supersampling factor
FPS = 30
FRAMES = 180                 # 6 s seamless loop
ACC = np.array([255, 212, 0], dtype=float)
GOLD = math.pi * (3 - math.sqrt(5))


def build():
    pts, nrm, kind, hemi = [], [], [], []
    N = 1700
    for i in range(N):
        uy = 1 - 2 * (i + 0.5) / N
        rr = math.sqrt(max(0, 1 - uy * uy))
        th = GOLD * i
        ux, uz = math.cos(th) * rr, math.sin(th) * rr
        h = 1 if ux >= 0 else -1
        px, py, pz = abs(ux), uy, uz
        X = px * (82 - 10 * max(0, pz))
        Y = py * 100
        Z = pz * 140
        if Y > 0:
            Y *= 0.56
        tb = math.exp(-((pz + 0.08) ** 2) / 0.12) * math.exp(-((py - 0.38) ** 2) / 0.10) * px
        Y += tb * 24
        X += tb * 9
        g = (1 + 0.050 * math.sin(X * 0.17 + Z * 0.09 + py * 2.2) * math.cos(Z * 0.12 - Y * 0.10)
             + 0.032 * math.sin(Z * 0.26 + X * 0.11) * math.sin(Y * 0.23)
             + 0.018 * math.sin(X * 0.45 + Y * 0.37 + Z * 0.31))
        X, Y, Z = X * g, Y * g, Z * g
        pts.append((h * (7 + X), Y - 12, Z)); nrm.append((ux, uy, uz)); kind.append("c"); hemi.append(h)
    # deep nuclei
    rng = np.random.default_rng(20261025)
    for i in range(150):
        h = -1 if i % 2 == 0 else 1
        a, b, rad = rng.random() * 2 * math.pi, math.acos(2 * rng.random() - 1), 0.25 + 0.38 * rng.random()
        x = h * (6 + abs(math.sin(b) * math.cos(a)) * 62 * rad * 1.5)
        y = -10 + math.cos(b) * 62 * rad * 1.4
        z = math.sin(b) * math.sin(a) * 96 * rad * 1.5
        pts.append((x, y, z)); nrm.append((0, 0, 0)); kind.append("k"); hemi.append(h)
    # cerebellum
    for i in range(300):
        uy = 1 - 2 * (i + 0.5) / 300
        rr = math.sqrt(1 - uy * uy)
        th = GOLD * i
        ux, uz = math.cos(th) * rr, math.sin(th) * rr
        h = 1 if ux >= 0 else -1
        stri = 1 + 0.05 * math.sin(uy * 24)
        pts.append((h * (4 + abs(ux) * 60 * stri), 80 + uy * 30 * stri, -96 + uz * 40 * stri))
        nrm.append((ux, uy, uz)); kind.append("b"); hemi.append(h)
    # brainstem
    for i in range(36):
        t, a = i / 35, i * 1.7
        pts.append((math.cos(a) * 9, 40 + t * 96, -34 - t * 36 + math.sin(a) * 9))
        nrm.append((0, 0, 0)); kind.append("s"); hemi.append(0)

    P = np.array(pts); Nn = np.array(nrm)
    kind = np.array(kind); hemi = np.array(hemi)
    thr = {"c": 20, "k": 46, "b": 16, "s": 22}
    edges = set()
    for kd in ("c", "k", "b", "s"):
        for hm in (-1, 1, 0):
            idx = np.where((kind == kd) & (hemi == hm))[0]
            if len(idx) < 2:
                continue
            sub = P[idx]
            d = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
            np.fill_diagonal(d, 1e9)
            order = np.argsort(d, axis=1)[:, :3]
            for r in range(len(idx)):
                for c in order[r]:
                    if d[r, c] < thr[kd]:
                        a, b = idx[r], idx[c]
                        edges.add((min(a, b), max(a, b)))
    # corpus callosum
    kl = np.where((kind == "k") & (hemi == -1))[0]
    kr = np.where((kind == "k") & (hemi == 1))[0]
    for a in kl:
        d = np.linalg.norm(P[kr] - P[a], axis=1)
        j = int(np.argmin(d))
        if d[j] < 70:
            edges.add((min(a, kr[j]), max(a, kr[j])))
    return P, Nn, kind, np.array(sorted(edges))


def main():
    P, Nn, kind, E = build()
    print(f"nodes={len(P)} edges={len(E)}")
    cmd = [FFMPEG, "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-s", f"{W}x{H}", "-pix_fmt", "rgb24",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
           "-crf", "20", "-movflags", "+faststart", OUT_MP4]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    w2, h2 = W * SS, H * SS
    fov, dist = 1080.0 * SS, 520.0
    is_core = (kind == "k")
    base_r = np.where(is_core, 3.4, np.where(kind == "c", 1.7, 1.5)) * SS

    for f in range(FRAMES):
        t = f / FRAMES
        ry = t * 2 * math.pi
        rx = 0.18 + 0.06 * math.sin(t * 2 * math.pi)
        cy_, sy_ = math.cos(ry), math.sin(ry)
        cx_, sx_ = math.cos(rx), math.sin(rx)

        x1 = P[:, 0] * cy_ + P[:, 2] * sy_
        z1 = -P[:, 0] * sy_ + P[:, 2] * cy_
        y2 = P[:, 1] * cx_ - z1 * sx_
        z2 = P[:, 1] * sx_ + z1 * cx_
        sc = fov / (dist + z2)
        X = w2 * 0.5 + x1 * sc
        Y = h2 * 0.5 + y2 * sc

        nz1 = -Nn[:, 0] * sy_ + Nn[:, 2] * cy_
        nz = Nn[:, 1] * sx_ + nz1 * cx_
        depth = np.clip((215 - z2) / 400, 0.1, 1.0)
        rim = np.where(np.isin(kind, ["c", "b"]),
                       (0.35 + 0.65 * (1 - np.abs(nz))) * np.where(nz > 0.15, 0.55, 1.0), 0.65)
        lum = depth * rim

        img = Image.new("RGB", (w2, h2), (0, 0, 0))
        d = ImageDraw.Draw(img, "RGBA")

        # aura rings
        for rr in (330, 420, 520):
            R = rr * SS * 1.0
            d.ellipse([w2 / 2 - R, h2 / 2 - R, w2 / 2 + R, h2 / 2 + R], outline=(255, 212, 0, 20), width=SS)

        # edges, far to near
        el = (lum[E[:, 0]] + lum[E[:, 1]]) * 0.5
        for k in np.argsort(el):
            a, b = E[k]
            alpha = int(255 * min(1.0, 0.04 + el[k] * 0.62))
            d.line([(X[a], Y[a]), (X[b], Y[b])], fill=(255, 212, 0, alpha), width=SS)
        # nodes, far to near
        for i in np.argsort(-z2):
            r = base_r[i] * sc[i] / (fov / dist)
            a = int(255 * min(1.0, 0.18 + lum[i] * 1.1))
            col = (255, 246, 200, a) if is_core[i] else (255, 218, 40, a)
            d.ellipse([X[i] - r, Y[i] - r, X[i] + r, Y[i] + r], fill=col)

        # downsample (anti-alias), then bloom
        base = img.resize((W, H), Image.LANCZOS)
        glow = base.resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(7)).resize((W, H), Image.BILINEAR)
        glow = glow.point(lambda v: min(255, int(v * 1.6)))
        out = ImageChops.add(base, glow)
        proc.stdin.write(out.tobytes())
        if f % 30 == 0:
            print(f"frame {f}/{FRAMES}", flush=True)

    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", errors="ignore")
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(err)
    print(f"Generated {OUT_MP4} ({os.path.getsize(OUT_MP4):,} bytes)")


if __name__ == "__main__":
    main()
