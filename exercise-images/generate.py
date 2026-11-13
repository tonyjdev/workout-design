"""Genera los fotogramas de ejercicios (SVG + PNG) con un estilo único.

Estilo: figura plana de perfil mirando a la derecha, extremidades redondeadas,
lado cercano oscuro y lado lejano claro, material en color de acento, suelo y
sombra suaves. Cada pose se define con puntos clave; codos y rodillas se
calculan por cinemática inversa de dos segmentos.

Uso: python3 generate.py   (salida en ./<CODIGO>/frame-N.svg|png)
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

# ---------- Estilo ----------
W, H = 400, 300  # lienzo (4:3)
FLOOR_Y = 262  # y del suelo en el lienzo
SCALE = 1.25  # unidades de figura -> px
ORIGIN_X = 150  # x del lienzo para x=0 de la figura
PNG_SCALE = 3  # PNG a 1200x900

BG = "#F4F6F8"
FLOOR = "#D9DEE4"
SHADOW = "#E3E7EC"
NEAR = "#26323F"  # lado cercano + tronco
FAR = "#8C99A6"  # lado lejano
ACCENT = "#FF6B3D"  # material (mancuernas...)

# Grosor de segmentos (unidades de figura)
TORSO_W, NECK_W = 24, 9
THIGH_W, SHIN_W, FOOT_W = 16, 13, 9
UPPER_W, FORE_W = 11, 9
HEAD_R, HAND_R = 11.5, 5.5

# Longitudes
THIGH, SHIN = 42, 40
UPPER, FORE = 29, 27


# ---------- Geometría ----------
def to_canvas(p):
    return (ORIGIN_X + p[0] * SCALE, FLOOR_Y - p[1] * SCALE)


def ik(root, target, l1, l2, bend):
    """Articulación media entre root y target. bend=+1 dobla a la izquierda
    del vector root->target (sentido antihorario), -1 a la derecha."""
    dx, dy = target[0] - root[0], target[1] - root[1]
    d = math.hypot(dx, dy)
    d = min(d, l1 + l2 - 1e-6)
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    h = math.sqrt(max(l1 * l1 - a * a, 0))
    ux, uy = dx / math.hypot(dx, dy), dy / math.hypot(dx, dy)
    mx, my = root[0] + ux * a, root[1] + uy * a
    return (mx - uy * h * bend, my + ux * h * bend)


def clamp_reach(root, target, length):
    dx, dy = target[0] - root[0], target[1] - root[1]
    d = math.hypot(dx, dy)
    if d <= length:
        return target
    return (root[0] + dx / d * length, root[1] + dy / d * length)


def add(p, q, k=1.0):
    return (p[0] + q[0] * k, p[1] + q[1] * k)


def unit(angle_deg):
    a = math.radians(angle_deg)
    return (math.cos(a), math.sin(a))


# ---------- Pose ----------
def pose(hip, torso_deg, head_deg=None, legs=(), arms=(), props=()):
    """legs/arms: dicts por lado ('near'|'far') con ankle/toe o wrist y bend.
    props: lista de callables(pose_points) -> shapes."""
    t = unit(torso_deg)
    neck = add(hip, t, 52)
    shoulder = add(neck, t, -6)
    head_dir = unit(head_deg if head_deg is not None else torso_deg)
    head = add(neck, head_dir, 7 + HEAD_R)
    return dict(hip=hip, neck=neck, shoulder=shoulder, head=head,
                legs=legs, arms=arms, props=props, torso=t)


def limb_segments(p, side, kind):
    """Segmentos [(a, b, ancho_a, ancho_b)] y manos de piernas o brazos de un lado."""
    segs, dots = [], []
    if kind == "legs":
        for leg in p["legs"]:
            if leg["side"] != side:
                continue
            ankle = clamp_reach(p["hip"], leg["ankle"], THIGH + SHIN)
            knee = ik(p["hip"], ankle, THIGH, SHIN, leg.get("bend", 1))
            segs += [(p["hip"], knee, THIGH_W, SHIN_W + 1), (knee, ankle, SHIN_W, FOOT_W),
                     (ankle, leg["toe"], FOOT_W, FOOT_W - 2)]
    else:
        for arm in p["arms"]:
            if arm["side"] != side:
                continue
            wrist = clamp_reach(p["shoulder"], arm["wrist"], UPPER + FORE)
            elbow = ik(p["shoulder"], wrist, UPPER, FORE, arm.get("bend", -1))
            segs += [(p["shoulder"], elbow, UPPER_W, FORE_W + 1), (elbow, wrist, FORE_W, FORE_W - 2)]
            dots.append((wrist, HAND_R))
    return segs, dots


HALO = 2.6  # separación (color de fondo) alrededor de piezas cercanas


def part(segs, dots, color, halo=False):
    out = []
    if halo:
        out += [("taper", a, b, wa + 2 * HALO, wb + 2 * HALO, BG) for a, b, wa, wb in segs]
        out += [("circle", c, r + HALO, BG) for c, r in dots]
    out += [("taper", a, b, wa, wb, color) for a, b, wa, wb in segs]
    out += [("circle", c, r, color) for c, r in dots]
    return out


def shapes(p):
    """Figuras ordenadas: ('taper', a, b, wa, wb, color) | ('circle', c, r, color)."""
    out = []
    out += part(*limb_segments(p, "far", "arms"), FAR)
    out += part(*limb_segments(p, "far", "legs"), FAR)
    # Tronco (más ancho en el pecho), cuello y cabeza
    chest = add(p["neck"], p["torso"], -12)
    out.append(("taper", p["hip"], chest, TORSO_W - 3, TORSO_W + 1, NEAR))
    hd = (p["head"][0] - p["neck"][0], p["head"][1] - p["neck"][1])
    n = math.hypot(*hd)
    out.append(("taper", add(p["neck"], p["torso"], -8), add(p["neck"], (hd[0] / n, hd[1] / n), 5), NECK_W, NECK_W, NEAR))
    out += part([], [(p["head"], HEAD_R)], NEAR, halo=True)
    for prop in p["props"]:
        out += prop(p)
    out += part(*limb_segments(p, "near", "legs"), NEAR, halo=True)
    out += part(*limb_segments(p, "near", "arms"), NEAR, halo=True)
    return out


def taper_polygon(a, b, ra, rb):
    """Polígono tangente a dos círculos (a, ra) y (b, rb)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy) or 1e-6
    ux, uy = dx / d, dy / d
    s = max(min((ra - rb) / d, 0.99), -0.99)
    c = math.sqrt(1 - s * s)
    # normales de las tangentes exteriores
    n1 = (ux * s - uy * c, uy * s + ux * c)
    n2 = (ux * s + uy * c, uy * s - ux * c)
    return [add(a, n1, ra), add(b, n1, rb), add(b, n2, rb), add(a, n2, ra)]


def shadow_extent(p):
    xs = [p["hip"][0], p["head"][0]]
    for leg in p["legs"]:
        xs += [leg["ankle"][0], leg["toe"][0]]
    for arm in p["arms"]:
        xs.append(arm["wrist"][0])
    return min(xs) - 14, max(xs) + 14


# ---------- Material ----------
def dumbbell_vertical(center_fn):
    """Mancuerna vertical sujeta con ambas manos (goblet)."""
    def draw(p):
        c = center_fn(p)
        top, bot = add(c, (0, 9)), add(c, (0, -9))
        return [("taper", top, bot, 5, 5, ACCENT),
                ("taper", add(top, (-7, 0)), add(top, (7, 0)), 10, 10, ACCENT),
                ("taper", add(bot, (-7, 0)), add(bot, (7, 0)), 10, 10, ACCENT)]
    return draw


# ---------- Render ----------
def render_svg(p, path):
    def pt(q):
        x, y = to_canvas(q)
        return f"{x:.1f}", f"{y:.1f}"

    x0, x1 = shadow_extent(p)
    sx0, _ = to_canvas((x0, 0))
    sx1, _ = to_canvas((x1, 0))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        f'<line x1="24" y1="{FLOOR_Y}" x2="{W - 24}" y2="{FLOOR_Y}" stroke="{FLOOR}" stroke-width="3" stroke-linecap="round"/>',
        f'<ellipse cx="{(sx0 + sx1) / 2:.1f}" cy="{FLOOR_Y}" rx="{(sx1 - sx0) / 2:.1f}" ry="6" fill="{SHADOW}"/>',
        '<g>',
    ]
    for s in shapes(p):
        if s[0] == "taper":
            _, a, b, wa, wb, color = s
            poly = " ".join(",".join(pt(q)) for q in taper_polygon(a, b, wa / 2, wb / 2))
            parts.append(f'<path fill="{color}" d="M{poly}Z"/>')
            for c, r in ((a, wa / 2), (b, wb / 2)):
                cx, cy = pt(c)
                parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r * SCALE:.1f}" fill="{color}"/>')
        else:
            cx, cy = pt(s[1])
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{s[2] * SCALE:.1f}" fill="{s[3]}"/>')
    parts += ["</g>", "</svg>"]
    path.write_text("\n".join(parts) + "\n")


def render_png(p, path):
    k = PNG_SCALE * 2  # supersampling
    img = Image.new("RGB", (W * k, H * k), BG)
    d = ImageDraw.Draw(img)

    def pt(q):
        x, y = to_canvas(q)
        return x * k, y * k

    def line(a, b, w, color):
        r = w / 2
        d.line([a, b], fill=color, width=int(round(w)))
        for c in (a, b):
            d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=color)

    line((24 * k, FLOOR_Y * k), ((W - 24) * k, FLOOR_Y * k), 3 * k, FLOOR)
    x0, x1 = shadow_extent(p)
    (sx0, sy), (sx1, _) = pt((x0, 0)), pt((x1, 0))
    d.ellipse([sx0, sy - 6 * k, sx1, sy + 6 * k], fill=SHADOW)
    for s in shapes(p):
        if s[0] == "taper":
            _, a, b, wa, wb, color = s
            d.polygon([pt(q) for q in taper_polygon(a, b, wa / 2, wb / 2)], fill=color)
            for c, r in ((a, wa / 2), (b, wb / 2)):
                (cx, cy), rr = pt(c), r * SCALE * k
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=color)
        else:
            (cx, cy), r = pt(s[1]), s[2] * SCALE * k
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=s[3])
    img = img.resize((W * PNG_SCALE, H * PNG_SCALE), Image.LANCZOS)
    img.save(path)


# ---------- Ejercicios ----------
def legs_standing(ankle_x=0.0, spread=4.0, toe=17):
    return (
        dict(side="far", ankle=(ankle_x - spread, 8), toe=(ankle_x - spread + toe, 3)),
        dict(side="near", ankle=(ankle_x + spread, 8), toe=(ankle_x + spread + toe, 3)),
    )


def goblet_squat():
    """Sentadilla goblet: 3 fotogramas (arriba, media, abajo)."""
    def chest(p):
        perp = (-p["torso"][1], p["torso"][0])  # perpendicular
        fwd = perp if perp[0] > 0 else (-perp[0], -perp[1])
        return add(add(p["neck"], p["torso"], -20), fwd, 21)

    def arms_goblet(p):
        c = chest(p)
        return (dict(side="far", wrist=add(c, (-2, 2)), bend=-1),
                dict(side="near", wrist=add(c, (2, -2)), bend=-1))

    frames = []
    for hip, torso in [((-3, 89), 88), ((-20, 64), 70), ((-31, 44), 58)]:
        p = pose(hip, torso, legs=legs_standing(spread=3), props=[dumbbell_vertical(chest)])
        p["arms"] = arms_goblet(p)
        frames.append(p)
    return frames


def inchworms():
    """Gusano: 5 fotogramas (de pie, flexión, manos avanzan, plancha, pies hacia manos)."""
    frames = []

    def arms(wrist_x, bend=-1, spread=4):
        return (dict(side="far", wrist=(wrist_x - spread, 5), bend=bend),
                dict(side="near", wrist=(wrist_x + spread, 5), bend=bend))

    def lean(hip, shoulder_target):
        """Ángulo de tronco para que el hombro quede en shoulder_target."""
        dx, dy = shoulder_target[0] - hip[0], shoulder_target[1] - hip[1]
        return math.degrees(math.atan2(dy, dx))

    # 1. De pie, brazos relajados
    p = pose((-1, 89), 90, legs=legs_standing(spread=3))
    p["arms"] = (dict(side="far", wrist=(-5, 84)), dict(side="near", wrist=(5, 83)))
    frames.append(p)

    # 2. Flexión de cadera, manos al suelo delante de los pies
    hip = (-14, 87)
    p = pose(hip, -58, head_deg=-72, legs=legs_standing(spread=3))
    p["arms"] = arms(30)
    frames.append(p)

    # 3. Manos avanzan
    hip = (-4, 86)
    p = pose(hip, lean(hip, (50, 55)), head_deg=-60, legs=legs_standing(spread=3))
    p["arms"] = arms(64)
    frames.append(p)

    # 4. Plancha: cuerpo recto, hombros sobre las muñecas, sobre puntas de pie
    ankle = (0, 16)
    shoulder = (118, 60)
    d = (shoulder[0] - ankle[0], shoulder[1] - ankle[1])
    n = math.hypot(*d)
    u = (d[0] / n, d[1] / n)
    hip = add(ankle, u, THIGH + SHIN - 1)
    torso = math.degrees(math.atan2(u[1], u[0]))
    plank_legs = (dict(side="far", ankle=(-3, 16), toe=(5, 3), bend=1),
                  dict(side="near", ankle=(3, 16), toe=(11, 3), bend=1))
    p = pose(hip, torso, head_deg=torso - 12, legs=plank_legs)
    p["arms"] = arms(120, bend=-1)
    frames.append(p)

    # 5. Pies caminan hacia las manos (pica)
    hip = (68, 86)
    pike_legs = (dict(side="far", ankle=(38, 10), toe=(52, 3)),
                 dict(side="near", ankle=(44, 10), toe=(58, 3)))
    p = pose(hip, lean(hip, (114, 58)), head_deg=-75, legs=pike_legs)
    p["arms"] = arms(115)
    frames.append(p)
    return frames


EXERCISES = {"GOBLET_SQUAT": goblet_squat, "INCHWORMS": inchworms}


def main():
    root = Path(__file__).parent
    for code, fn in EXERCISES.items():
        out = root / code
        out.mkdir(exist_ok=True)
        for i, p in enumerate(fn(), 1):
            render_svg(p, out / f"frame-{i}.svg")
            render_png(p, out / f"frame-{i}.png")
        print(code, "ok")


if __name__ == "__main__":
    main()
