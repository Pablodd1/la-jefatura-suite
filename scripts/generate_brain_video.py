"""Generate a High-Definition 3D Spinning Brain Schematic Video (assets/hero-brain-3d.mp4).

Symbolizes 'El Jefe / El Cerebro de la Empresa' — the central executive brain connecting
all business units (MBMB, CEDEXX, DLM, UNITEC USA, BuildingApp.us) with zero hallucinations.
"""
import math
import os
import random
import subprocess
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_MP4 = os.path.join(ROOT, "assets", "hero-brain-3d.mp4")
FFMPEG = r"C:\Users\jasme\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffmpeg.EXE"

W, H = 1280, 720
FPS = 30
FRAMES = 150  # 5-second seamless 360-degree loop


def build_brain_geometry(seed: int = 42):
    rng = random.Random(seed)
    nodes = []
    # Generate anatomically shaped Left & Right Cerebral Hemispheres + Cerebellum + Brainstem
    for i in range(420):
        hemi = -1 if i % 2 == 0 else 1
        u = rng.uniform(0, math.pi)
        v = rng.uniform(0, math.pi)
        # Base ellipsoid for cerebral hemisphere
        rx = 115.0
        ry = 145.0
        rz = 185.0
        # Cortical surface vs deep core nuclei
        shell = 0.88 + 0.12 * rng.random() if i < 340 else 0.38 + 0.35 * rng.random()
        x = hemi * (18.0 + rx * shell * math.sin(u) * math.sin(v))
        y = -15.0 + ry * shell * math.cos(u)
        z = rz * shell * math.sin(u) * math.cos(v)

        # Sculpt frontal/occipital contour & temporal lobe bulge
        if y > 40:
            y *= 0.72
        if z < -30 and y > 10:
            # Temporal lobe lower bulge
            y += 22.0
            x *= 1.08
        # Cortical gyri/sulci folding ripple
        fold = 1.0 + 0.055 * math.sin(x * 0.11) * math.cos(z * 0.09)
        x *= fold
        y *= fold
        z *= fold

        lobe = "FRONTAL" if z > 45 else ("OCCIPITAL" if z < -75 else ("TEMPORAL" if y > 15 else "PARIETAL"))
        nodes.append({"x": x, "y": y, "z": z, "hemi": hemi, "lobe": lobe, "core": i >= 340})

    # Add Cerebellum & Brainstem schematic nodes
    for i in range(70):
        hemi = -1 if i % 2 == 0 else 1
        u = rng.uniform(0, math.pi)
        v = rng.uniform(0, math.pi)
        x = hemi * (10.0 + 68.0 * math.sin(u) * math.sin(v))
        y = 92.0 + 42.0 * math.cos(u)
        z = -95.0 + 55.0 * math.sin(u) * math.cos(v)
        nodes.append({"x": x, "y": y, "z": z, "hemi": hemi, "lobe": "CEREBELLUM", "core": False})

    # Connect nearby nodes into a high-definition 3D schematic mesh + corpus callosum bridges
    edges = []
    n_len = len(nodes)
    for i in range(n_len):
        a = nodes[i]
        dists = []
        for j in range(i + 1, n_len):
            b = nodes[j]
            dx = a["x"] - b["x"]
            dy = a["y"] - b["y"]
            dz = a["z"] - b["z"]
            d2 = dx * dx + dy * dy + dz * dz
            if a["hemi"] == b["hemi"] and d2 < 2100:
                dists.append((d2, j))
            elif a["hemi"] != b["hemi"] and abs(a["x"]) < 42 and abs(b["x"]) < 42 and d2 < 2600:
                # Corpus callosum cross-hemisphere bridge
                dists.append((d2, j))
        dists.sort(key=lambda t: t[0])
        for _, j in dists[:3]:
            edges.append((i, j))

    return nodes, edges


def project(x, y, z, rot_y, rot_x=0.16):
    # Rotate around Y axis
    cy, sy = math.cos(rot_y), math.sin(rot_y)
    x1 = x * cy + z * sy
    z1 = -x * sy + z * cy
    # Slight tilt around X axis
    cx, sx = math.cos(rot_x), math.sin(rot_x)
    y2 = y * cx - z1 * sx
    z2 = y * sx + z1 * cx

    fov = 640.0
    dist = 520.0
    scale = fov / (dist + z2)
    sx_px = W * 0.5 + x1 * scale
    sy_px = H * 0.5 + y2 * scale
    return sx_px, sy_px, z2, scale


def main():
    os.makedirs(os.path.dirname(OUT_MP4), exist_ok=True)
    nodes, edges = build_brain_geometry()

    cmd = [
        FFMPEG,
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{W}x{H}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "-",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "17",
        "-movflags", "+faststart",
        OUT_MP4,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    for f in range(FRAMES):
        t = f / float(FRAMES)
        rot_y = t * 2.0 * math.pi
        rot_x = 0.18 + 0.06 * math.sin(t * 2.0 * math.pi)

        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img, "RGBA")

        # 1. Subtle technical CAD grid & radial glow
        for gx in range(0, W, 64):
            draw.line([(gx, 0), (gx, H)], fill=(255, 212, 0, 11), width=1)
        for gy in range(0, H, 64):
            draw.line([(0, gy), (W, gy)], fill=(255, 212, 0, 11), width=1)

        for r_glow in (310, 250, 190, 130):
            draw.ellipse(
                [W // 2 - r_glow, H // 2 - r_glow, W // 2 + r_glow, H // 2 + r_glow],
                outline=(255, 212, 0, 22),
                width=1,
            )

        # 2. 3D Orbital Enterprise Telemetry Rings around the Brain
        for ring_r, tilt in ((265.0, 0.35), (315.0, -0.28)):
            pts = []
            for seg in range(73):
                ang = (seg / 72.0) * 2.0 * math.pi + rot_y * 0.5
                rx = ring_r * math.cos(ang)
                rz = ring_r * math.sin(ang)
                ry = rx * math.sin(tilt)
                px, py, _, _ = project(rx, ry, rz, 0.0, 0.18)
                pts.append((px, py))
            draw.line(pts, fill=(255, 212, 0, 58), width=1)

        # 3. Project all 3D brain nodes
        proj = [project(n["x"], n["y"], n["z"], rot_y, rot_x) for n in nodes]

        # 4. Sort and draw 3D synaptic edges (back-to-front)
        sorted_edges = sorted(edges, key=lambda e: (proj[e[0]][2] + proj[e[1]][2]) * 0.5, reverse=True)
        for idx_e, (i, j) in enumerate(sorted_edges):
            x1, y1, z1, _ = proj[i]
            x2, y2, z2, _ = proj[j]
            z_avg = (z1 + z2) * 0.5
            depth_norm = max(0.12, min(1.0, (220.0 - z_avg) / 420.0))
            alpha = int(32 + 155 * depth_norm)

            # Synaptic firing pulse traveling along edges
            pulse = math.sin(t * 2.0 * math.pi * 3.0 + idx_e * 0.17)
            if pulse > 0.92:
                draw.line([(x1, y1), (x2, y2)], fill=(255, 248, 190, min(255, alpha + 90)), width=2)
            else:
                col = (255, 212, 0, alpha) if nodes[i]["lobe"] == "FRONTAL" else (245, 185, 15, int(alpha * 0.85))
                draw.line([(x1, y1), (x2, y2)], fill=col, width=1)

        # 5. Draw 3D cortical nodes & glowing executive nuclei
        order = sorted(range(len(nodes)), key=lambda k: proj[k][2], reverse=True)
        for k in order:
            px, py, pz, sc = proj[k]
            depth_norm = max(0.15, min(1.0, (220.0 - pz) / 420.0))
            r = max(1.4, (3.2 if nodes[k]["core"] else 2.2) * sc)
            alpha = int(65 + 190 * depth_norm)
            if nodes[k]["core"]:
                draw.ellipse([px - r * 2.1, py - r * 2.1, px + r * 2.1, py + r * 2.1], fill=(255, 212, 0, int(alpha * 0.28)))
                draw.ellipse([px - r, py - r, px + r, py + r], fill=(255, 250, 210, alpha))
            else:
                draw.ellipse([px - r, py - r, px + r, py + r], fill=(255, 212, 0, alpha))

        proc.stdin.write(img.tobytes())

    proc.stdin.close()
    stderr_out = proc.stderr.read().decode("utf-8", errors="ignore")
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr_out}")
    print(f"Generated HD 3D Brain Video: {OUT_MP4} ({os.path.getsize(OUT_MP4):,} bytes)")


if __name__ == "__main__":
    main()
