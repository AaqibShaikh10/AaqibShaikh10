"""
Builds every SVG in ../ (light + dark variants) for the profile README.

Text is converted to outlined paths so the typography renders identically
everywhere (GitHub serves SVGs as images, which cannot load web fonts).

Setup (once):
    npm i @fontsource/inter-tight @fontsource/jetbrains-mono
    pip install fonttools brotli uharfbuzz

Run:
    FONT_DIR=path/to/node_modules/@fontsource python build_assets.py

Edit the CONTENT section below, re-run, commit the regenerated SVGs.
"""

import io
import math
import os
import random
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

OUT = Path(__file__).resolve().parent.parent
FONT_DIR = Path(os.environ.get("FONT_DIR", "node_modules/@fontsource"))

# ----------------------------------------------------------------------------
# Palette — one accent, tuned per theme for contrast against GitHub's
# backgrounds (#0d1117 dark, #ffffff light). Backgrounds stay transparent.
# ----------------------------------------------------------------------------
THEMES = {
    "dark": dict(ink="#E6EDF3", muted="#9198A1", faint="#3D444D",
                 hair="#30363D", accent="#FF7A45", soft="0.16"),
    "light": dict(ink="#1F2328", muted="#59636E", faint="#C8D1DA",
                  hair="#D1D9E0", accent="#C2410C", soft="0.10"),
}


# ----------------------------------------------------------------------------
# Type: shaped with HarfBuzz (kerning), drawn as paths
# ----------------------------------------------------------------------------
def fmt(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


class Font:
    def __init__(self, path):
        tt = TTFont(path)
        tt.flavor = None
        buf = io.BytesIO()
        tt.save(buf)
        data = buf.getvalue()
        self.tt = TTFont(io.BytesIO(data))
        self.upem = self.tt["head"].unitsPerEm
        self.glyphs = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()
        self.hb = hb.Font(hb.Face(data))

    def _shape(self, text, size, tracking):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"kern": True, "liga": True})
        s = size / self.upem
        out, x = [], 0.0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            out.append((self.order[info.codepoint], x + pos.x_offset * s, pos.y_offset * s))
            x += pos.x_advance * s + tracking
        return out, x - tracking

    def width(self, text, size, tracking=0):
        return self._shape(text, size, tracking)[1]

    def outline(self, name):
        """Glyph outline in font units (y up)."""
        pen = SVGPathPen(self.glyphs, ntos=lambda v: str(round(v)))
        self.glyphs[name].draw(pen)
        return pen.getCommands()


F = {
    "display": Font(FONT_DIR / "inter-tight/files/inter-tight-latin-600-normal.woff2"),
    "body": Font(FONT_DIR / "inter-tight/files/inter-tight-latin-400-normal.woff2"),
    "mono": Font(FONT_DIR / "jetbrains-mono/files/jetbrains-mono-latin-400-normal.woff2"),
    "monob": Font(FONT_DIR / "jetbrains-mono/files/jetbrains-mono-latin-500-normal.woff2"),
}


class Canvas:
    def __init__(self, w, h, title, desc, t):
        self.w, self.h, self.title, self.desc, self.t = w, h, title, desc, t
        self.els = []
        self.defs = {}

    def text(self, font, s, x, y, size, color, tracking=0, anchor="start"):
        fo = F[font]
        glyphs, w = fo._shape(s, size, tracking)
        if anchor == "end":
            x -= w
        elif anchor == "middle":
            x -= w / 2
        k = size / fo.upem
        uses = []
        for name, gx, gy in glyphs:
            gid = font + "-" + "".join(ch if ch.isalnum() else "_" for ch in name)
            if gid not in self.defs:
                d = fo.outline(name)
                if not d:          # spaces have no outline
                    continue
                self.defs[gid] = d
            dy = f' y="{round(-gy / k)}"' if gy else ""
            uses.append(f'<use href="#{gid}" x="{round(gx / k)}"{dy}/>')
        self.els.append(f'<g fill="{self.t[color]}" transform="translate({fmt(x)} {fmt(y)}) '
                        f'scale({k:.5g} {-k:.5g})">{"".join(uses)}</g>')
        return w

    def runs(self, font, parts, x, y, size, tracking=0):
        """Inline runs of differently coloured text on one baseline."""
        for s, color in parts:
            x += self.text(font, s, x, y, size, color, tracking)
            x += tracking

    def raw(self, svg):
        self.els.append(svg)

    def line(self, x1, y1, x2, y2, color, sw=1, extra=""):
        self.raw(f'<line x1="{fmt(x1)}" y1="{fmt(y1)}" x2="{fmt(x2)}" y2="{fmt(y2)}" '
                 f'stroke="{self.t[color]}" stroke-width="{sw}"{extra}/>')

    def rect(self, x, y, w, h, rx=0, fill="none", stroke=None, sw=1, fill_op=None, extra=""):
        f = self.t[fill] if fill != "none" else "none"
        s = f' stroke="{self.t[stroke]}" stroke-width="{sw}"' if stroke else ""
        fo = f' fill-opacity="{fill_op}"' if fill_op else ""
        self.raw(f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" '
                 f'rx="{fmt(rx)}" fill="{f}"{fo}{s}{extra}/>')

    def svg(self):
        body = "\n".join(self.els)
        if self.defs:
            body = ("<defs>" + "".join(f'<path id="{i}" d="{d}"/>' for i, d in self.defs.items())
                    + "</defs>\n" + body)
        # Crop 40 units off each side so the artwork's text column lines up with
        # the README's own text edge (content is laid out on x = 48 .. 1152).
        vx, vw = 40, self.w - 80
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{vw}" height="{self.h}" '
                f'viewBox="{vx} 0 {vw} {self.h}" role="img" aria-labelledby="t d">\n'
                f'<title id="t">{self.title}</title>\n<desc id="d">{self.desc}</desc>\n'
                f'{body}\n</svg>\n')


# ----------------------------------------------------------------------------
# Shared motif: a speech-like waveform with an "inspection window"
# ----------------------------------------------------------------------------
def amplitudes(n, seed):
    rnd = random.Random(seed)
    bumps = [(rnd.uniform(0, 1), rnd.uniform(0.35, 1), rnd.uniform(0.03, 0.09)) for _ in range(n // 6)]
    amps = []
    for i in range(n):
        t = i / max(n - 1, 1)
        env = sum(h * math.exp(-((t - c) / w) ** 2) for c, h, w in bumps)
        amps.append(env * (0.55 + 0.45 * rnd.random()))
    peak = max(amps)
    return [max(0.07, min(1.0, a / peak)) for a in amps]


def waveform(c, x0, x1, cy, half, bw, step, seed, window=None, before="muted",
             after="faint", before_op="0.6", auto_width=None):
    """Draws bars; returns the (x_start, x_end) of the accent window.
    auto_width places the window over the loudest stretch of that width."""
    n = int((x1 - x0) // step) + 1
    amps = amplitudes(n, seed)
    if auto_width:
        span = int(auto_width // step)
        best = max(range(n - span), key=lambda i: sum(amps[i:i + span]))
        window = (x0 + best * step, x0 + (best + span) * step)
    for i, a in enumerate(amps):
        x = x0 + i * step
        h = max(bw, 2 * a * half)
        if window and window[0] <= x <= window[1]:
            color, op = "accent", None
        elif window and x > window[1]:
            color, op = after, None
        else:
            color, op = before, before_op
        c.rect(x, cy - h / 2, bw, h, rx=bw / 2, fill=color, fill_op=op)
    return window


def bracket(c, x1, y1, x2, y2, arm=12, sw=2):
    t = c.t["accent"]
    d = (f"M{x1} {y1 + arm}V{y1}H{x1 + arm}M{x2 - arm} {y1}H{x2}V{y1 + arm}"
         f"M{x2} {y2 - arm}V{y2}H{x2 - arm}M{x1 + arm} {y2}H{x1}V{y2 - arm}")
    c.raw(f'<path d="{d}" fill="none" stroke="{t}" stroke-width="{sw}" stroke-linecap="square"/>')


def arrow(c, x1, y, x2, color="accent", sw=1.5):
    """Horizontal connector with a small open arrowhead."""
    t = c.t[color]
    c.raw(f'<path d="M{fmt(x1)} {fmt(y)}H{fmt(x2)}M{fmt(x2 - 6)} {fmt(y - 5)}L{fmt(x2)} {fmt(y)}'
          f'L{fmt(x2 - 6)} {fmt(y + 5)}" fill="none" stroke="{t}" stroke-width="{sw}" '
          f'stroke-linecap="round" stroke-linejoin="round"/>')


def ext_arrow(c, x, y, color="muted"):
    """Small north-east arrow used after a repository path."""
    t = c.t[color]
    c.raw(f'<path d="M{fmt(x)} {fmt(y)}L{fmt(x + 9)} {fmt(y - 9)}M{fmt(x + 2)} {fmt(y - 9)}'
          f'H{fmt(x + 9)}V{fmt(y - 2)}" fill="none" stroke="{t}" stroke-width="1.5" '
          f'stroke-linecap="round" stroke-linejoin="round"/>')


# ----------------------------------------------------------------------------
# CONTENT
# ----------------------------------------------------------------------------
def hero(t):
    c = Canvas(1200, 470, "Aaqib Shaikh — Software Engineer",
               "Software engineer working on machine-learning systems and full-stack "
               "applications. A waveform with an inspection window marks DeepSafe, "
               "the deepfake-detection project in progress.", t)
    c.text("monob", "SOFTWARE ENGINEER", 48, 52, 15, "muted", tracking=1.6)
    c.text("monob", "AI / ML  ·  FULL STACK", 1152, 52, 15, "muted", tracking=1.6, anchor="end")
    c.line(48, 72.5, 1152, 72.5, "hair")
    c.text("display", "Aaqib Shaikh", 42, 200, 116, "ink", tracking=-3.5)
    c.runs("body", [("I build ", "muted"), ("machine-learning systems", "ink"),
                    (" and the", "muted")], 48, 262, 31)
    c.runs("body", [("full-stack applications", "ink"),
                    (" that put them to work.", "muted")], 48, 304, 31)
    waveform(c, 48, 1150, 392, 36, 4, 8, seed=7, window=(816, 968))
    bracket(c, 802, 348, 982, 436)
    c.text("monob", "DEEPSAFE — IN PROGRESS", 802, 334, 13, "accent", tracking=1.4)
    c.text("mono", "video + audio", 802, 462, 13, "muted", tracking=0.6)
    return c


CARD_W, CARD_H, MX = 1200, 336, 648


def card_frame(t, index, category, name_lines, tagline, repo, title, desc):
    c = Canvas(CARD_W, CARD_H, title, desc, t)
    if index != "01":   # the section heading's own rule sits above the first card
        c.line(0, 0.5, CARD_W, 0.5, "hair")
    c.text("monob", index, 48, 48, 15, "accent", tracking=1.2)
    c.text("monob", category, 88, 48, 15, "muted", tracking=1.5)
    y = 124
    for ln in name_lines:
        c.text("display", ln, 45, y, 60, "ink", tracking=-1.6)
        y += 64
    y += -64 + 50
    for ln in tagline:
        c.text("body", ln, 48, y, 25, "muted")
        y += 34
    w = c.text("mono", repo, 48, 306, 15, "muted", tracking=0.2)
    ext_arrow(c, 48 + w + 10, 304)
    return c


def card_deepsafe(t):
    c = card_frame(t, "01", "DEEPFAKE DETECTION", ["DeepSafe"],
                   ["Flags manipulated video and audio", "using two separate detection models."],
                   "AaqibShaikh10/DeepSafe",
                   "01 — DeepSafe",
                   "Deepfake detection for video and audio. Video frames are analysed one by one "
                   "with XceptionNet; audio is analysed with AASIST.")
    c.text("monob", "VIDEO · XCEPTIONNET · PER FRAME", MX, 48, 13, "muted", tracking=1.2)
    flagged = {2, 3, 9, 10, 11, 16}
    cw, ch, gap = 64, 42, 8
    for r in range(3):
        for col in range(7):
            i = r * 7 + col
            x, y = MX + col * (cw + gap), 64 + r * (ch + gap)
            if i in flagged:
                c.rect(x, y, cw, ch, rx=5, fill="accent", fill_op=t["soft"], stroke="accent", sw=1.5)
                c.rect(x + cw / 2 - 10, y + ch / 2 - 10, 20, 20, rx=3, stroke="accent", sw=1.25)
            else:
                c.rect(x + 0.5, y + 0.5, cw - 1, ch - 1, rx=5, stroke="faint", sw=1.25)
                c.rect(x + cw / 2 - 10, y + ch / 2 - 10, 20, 20, rx=3, stroke="faint", sw=1)
    c.text("monob", "AUDIO · AASIST", MX, 236, 13, "muted", tracking=1.2)
    wx0, wx1 = waveform(c, MX, 1142, 286, 22, 3, 6, seed=21, auto_width=96,
                        before="muted", after="muted", before_op="0.55")
    bracket(c, wx0 - 8, 258, wx1 + 2, 314, arm=9, sw=1.75)
    return c


def card_heart(t):
    c = card_frame(t, "02", "HEALTHCARE ML", ["Heart Disease", "Prediction"],
                   ["Predicts heart-disease risk from 11 clinical features."],
                   "AaqibShaikh10/Heart-Disease-Prediction-And-Analysis",
                   "02 — Heart Disease Prediction",
                   "Five classifiers compared by 5-fold cross-validated ROC-AUC: Random Forest 0.925, "
                   "Logistic Regression 0.922, Naive Bayes 0.909, KNN 0.898, Decision Tree 0.785. "
                   "Random Forest test set: accuracy 0.89, ROC-AUC 0.93.")
    c.text("monob", "5-FOLD CV · ROC-AUC", MX, 48, 13, "muted", tracking=1.2)
    models = [("Random Forest", .925), ("Logistic Reg.", .922), ("Naive Bayes", .909),
              ("KNN", .898), ("Decision Tree", .785)]
    bx, bmax = MX + 160, 260
    c.line(bx + 0.5, 66, bx + 0.5, 270, "hair")
    for i, (name, v) in enumerate(models):
        y = 86 + i * 42
        best = i == 0
        c.text("mono", name, MX, y + 5, 14, "ink" if best else "muted")
        c.rect(bx, y - 7, bmax * v, 14, rx=2, fill="accent" if best else "muted",
               fill_op=None if best else "0.35")
        c.text("monob" if best else "mono", f"{v:.3f}", bx + bmax * v + 14, y + 5, 14,
               "accent" if best else "muted")
    c.text("monob", "TEST SET · ACCURACY 0.89 · ROC-AUC 0.93", MX, 306, 13, "muted", tracking=1.0)
    return c


def card_news(t):
    c = card_frame(t, "03", "NLP", ["Multilingual", "News Platform"],
                   ["Summaries and sentiment across 10 languages."],
                   "AaqibShaikh10/multilingual-news-platform",
                   "03 — Multilingual News Platform",
                   "Ten supported languages (EN, ES, FR, DE, IT, PT, AR, HI, UR, ZH); input from text, "
                   "URL, PDF or RSS; pipeline of language detection, summarization and sentiment.")
    c.text("monob", "LANGUAGES", MX, 48, 13, "muted", tracking=1.2)
    codes = ["EN", "ES", "FR", "DE", "IT", "PT", "AR", "HI", "UR", "ZH"]
    cw, chh, gap = 52, 34, 8
    for i, code in enumerate(codes):
        x, y = MX + (i % 5) * (cw + gap), 64 + (i // 5) * (chh + gap)
        c.rect(x + 0.5, y + 0.5, cw - 1, chh - 1, rx=5, stroke="faint", sw=1.25)
        c.text("monob", code, x + cw / 2, y + 22, 14, "ink", anchor="middle", tracking=0.6)
    ix = 990
    c.text("monob", "INPUT", ix, 48, 13, "muted", tracking=1.2)
    for i, s in enumerate(["text", "url", "pdf", "rss"]):
        c.text("mono", s, ix, 86 + i * 22, 14, "muted", tracking=0.4)
    stages = ["DETECT", "SUMMARIZE", "SENTIMENT"]
    sw_, sg, sy, sh = 150, 23, 206, 52
    c.raw(f'<path d="M{MX + 146} 148V178H{MX + sw_ / 2}V{sy - 8}" fill="none" '
          f'stroke="{t["accent"]}" stroke-width="1.5" stroke-linejoin="round"/>')
    c.raw(f'<path d="M{MX + sw_ / 2 - 5} {sy - 13}L{MX + sw_ / 2} {sy - 7}L{MX + sw_ / 2 + 5} {sy - 13}" '
          f'fill="none" stroke="{t["accent"]}" stroke-width="1.5" stroke-linecap="round" '
          f'stroke-linejoin="round"/>')
    for i, s in enumerate(stages):
        x = MX + i * (sw_ + sg)
        c.rect(x + 0.5, sy + 0.5, sw_ - 1, sh - 1, rx=6, stroke="faint", sw=1.25)
        c.text("monob", s, x + sw_ / 2, sy + 31, 14, "ink", anchor="middle", tracking=1.2)
        if i < 2:
            arrow(c, x + sw_ + 3, sy + sh / 2, x + sw_ + sg - 3)
    c.text("monob", "FLASK · HUGGING FACE TRANSFORMERS", MX, 306, 13, "muted", tracking=1.0)
    return c


def card_rag(t):
    c = card_frame(t, "04", "LLM · RAG", ["RAG Chatbot"],
                   ["Answers questions about a PDF", "using retrieval and Llama 3."],
                   "AaqibShaikh10/rag-chatbot",
                   "04 — RAG Chatbot",
                   "Retrieval pipeline: PDF, split into 500-character chunks with 50 overlap, embedded "
                   "with all-MiniLM-L6-v2, top 3 chunks retrieved, answered by Llama 3 via Groq.")
    c.text("monob", "RETRIEVAL PIPELINE", MX, 48, 13, "muted", tracking=1.2)
    cx = [MX + 40 + i * 113 for i in range(5)]
    cy = 142
    acc, fnt, mut = t["accent"], t["faint"], t["muted"]
    # 1 document
    x = cx[0]
    c.raw(f'<path d="M{x - 20} {cy - 28}H{x + 8}L{x + 20} {cy - 16}V{cy + 28}H{x - 20}Z'
          f'M{x + 8} {cy - 28}V{cy - 16}H{x + 20}" fill="none" stroke="{mut}" stroke-width="1.5" '
          f'stroke-linejoin="round"/>')
    for k in range(4):
        c.line(x - 12, cy - 6 + k * 9, x + (12 if k < 3 else 2), cy - 6 + k * 9, "faint", 1.5)
    # 2 chunks
    x = cx[1]
    for k in range(4):
        c.rect(x - 24, cy - 26 + k * 14, 48, 10, rx=2, stroke="muted", sw=1.25)
    # 3 embed: scatter
    x = cx[2]
    rnd = random.Random(4)
    pts = [(x + rnd.uniform(-28, 28), cy + rnd.uniform(-26, 26)) for _ in range(16)]
    for px, py in pts:
        c.raw(f'<circle cx="{fmt(px)}" cy="{fmt(py)}" r="3" fill="{mut}" fill-opacity="0.75"/>')
    # 4 top-k: same cloud, three nearest highlighted around a query point
    x = cx[3]
    qx, qy = x + 6, cy - 4
    pts2 = [(x + (px - cx[2]), py) for px, py in pts]
    near = sorted(pts2, key=lambda p: (p[0] - qx) ** 2 + (p[1] - qy) ** 2)[:3]
    for px, py in pts2:
        if (px, py) in near:
            c.raw(f'<line x1="{fmt(qx)}" y1="{fmt(qy)}" x2="{fmt(px)}" y2="{fmt(py)}" '
                  f'stroke="{acc}" stroke-width="1"/>')
    for px, py in pts2:
        hit = (px, py) in near
        c.raw(f'<circle cx="{fmt(px)}" cy="{fmt(py)}" r="{3.6 if hit else 3}" '
              f'fill="{acc if hit else fnt}"/>')
    c.raw(f'<circle cx="{fmt(qx)}" cy="{fmt(qy)}" r="5" fill="none" stroke="{acc}" stroke-width="1.5"/>')
    # 5 answer bubble
    x = cx[4]
    c.raw(f'<path d="M{x - 24} {cy - 22}H{x + 24}a4 4 0 0 1 4 4V{cy + 12}a4 4 0 0 1-4 4'
          f'H{x - 6}L{x - 16} {cy + 26}V{cy + 16}H{x - 24}a4 4 0 0 1-4-4V{cy - 18}a4 4 0 0 1 4-4Z" '
          f'fill="{acc}" fill-opacity="{t["soft"]}" stroke="{acc}" stroke-width="1.5" '
          f'stroke-linejoin="round"/>')
    for k, ww in enumerate([30, 22]):
        c.line(x - 15, cy - 9 + k * 11, x - 15 + ww, cy - 9 + k * 11, "accent", 1.75,
               ' stroke-linecap="round"')
    for i in range(4):
        arrow(c, cx[i] + 34, cy, cx[i + 1] - 34, color="faint")
    labels = [("PDF", "source"), ("CHUNK", "500 / 50"), ("EMBED", "MiniLM-L6"),
              ("TOP-K", "k = 3"), ("ANSWER", "Llama 3")]
    for (a, b), x in zip(labels, cx):
        c.text("monob", a, x, 214, 13, "ink", anchor="middle", tracking=1.2)
        c.text("mono", b, x, 236, 13, "muted", anchor="middle", tracking=0.2)
    c.text("monob", "LANGCHAIN · STREAMLIT · GROQ", MX, 306, 13, "muted", tracking=1.0)
    return c


def footer(t):
    c = Canvas(1200, 64, "", "Decorative closing rule.", t)
    c.line(48, 32.5, 548, 32.5, "hair")
    c.line(652, 32.5, 1152, 32.5, "hair")
    waveform(c, 560, 640, 32, 14, 3, 6, seed=3, window=(584, 616),
             before="muted", after="muted", before_op="0.6")
    return c


ASSETS = {
    "hero": hero,
    "project-deepsafe": card_deepsafe,
    "project-heart-disease": card_heart,
    "project-multilingual-news": card_news,
    "project-rag-chatbot": card_rag,
    "footer": footer,
}

if __name__ == "__main__":
    for name, fn in ASSETS.items():
        for theme, pal in THEMES.items():
            path = OUT / f"{name}-{theme}.svg"
            path.write_text(fn(pal).svg(), encoding="utf-8")
            print(f"{path.name:40s} {path.stat().st_size / 1024:6.1f} KB")
