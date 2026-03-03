#!/usr/bin/env python3
"""
Stage 2: SVG 技術図面生成スクリプト

requirements.json または parameters.json から
正面図・側面図・上面図・等角図を含む工業図面スタイルの SVG を生成する。

外部 API・ライブラリは不要。Python 標準ライブラリのみ使用。

使用方法:
  python stage2_svg_views.py --req requirements.json --out views/
  python stage2_svg_views.py --params parameters.json --out views/
  python stage2_svg_views.py --req requirements.json --params parameters.json --out views/

  ※ --req と --params を両方渡すと parameters.json の値が優先される（より精確）

出力:
  views/technical_drawing.svg  ← ブラウザで直接開ける
"""

import json
import math
import sys
import os
import argparse
from datetime import date
from pathlib import Path

# ── 定数 ──────────────────────────────────────────────────────────────────────
CANVAS_W = 1400
CANVAS_H = 1000
PADDING  = 50
TITLE_H  = 80
VIEW_GAP = 65          # ビュー間の余白 (px)

# 色
COLOR_OUTLINE    = "#1a1a2e"   # 外形線（濃い紺）
COLOR_HIDDEN     = "#888888"   # 隠れ線（破線）
COLOR_CENTERLINE = "#cc3333"   # 中心線
COLOR_DIM        = "#1a5fb4"   # 寸法線・テキスト
COLOR_LABEL      = "#222222"   # ビュー名
COLOR_BG         = "#ffffff"
COLOR_FACE_FRONT = "#eef1f8"   # 正面の面色
COLOR_FACE_TOP   = "#f4f6fb"   # 上面の面色
COLOR_FACE_SIDE  = "#dde2f0"   # 側面の面色
COLOR_TITLE_BG   = "#1a1a2e"
COLOR_TITLE_TEXT = "#ffffff"
COLOR_SUBTITLE   = "#9999cc"

FONT = "Noto Sans JP, Meiryo, Yu Gothic, Arial, sans-serif"

ARROW_LEN  = 9    # 矢印の長さ (px)
ARROW_W    = 3.5  # 矢印の幅 (px)
DIM_OFFSET = 22   # 外形線から寸法線までのオフセット (px)
EXT_MARGIN = 6    # 延長線の余白 (px)
LABEL_SIZE = 12   # 寸法値テキストサイズ
VIEW_TITLE = 14   # ビュー名テキストサイズ


# ── SVGBuilder ────────────────────────────────────────────────────────────────

class SVGBuilder:
    """SVG 要素を積み上げて最後に文字列化する軽量ビルダー"""

    def __init__(self, width, height):
        self.w = width
        self.h = height
        self._elems = []

    def add(self, s):
        self._elems.append(s)

    def rect(self, x, y, w, h, fill=COLOR_BG, stroke=COLOR_OUTLINE,
             sw=1.5, rx=0, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d} rx="{rx:.2f}"/>'
        )

    def line(self, x1, y1, x2, y2, stroke=COLOR_OUTLINE, sw=1.5, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{stroke}" stroke-width="{sw}"{d}/>'
        )

    def circle(self, cx, cy, r, fill="none", stroke=COLOR_OUTLINE, sw=1.0, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>'
        )

    def polygon(self, pts, fill="none", stroke=COLOR_OUTLINE, sw=1.5):
        s = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        self.add(
            f'<polygon points="{s}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
        )

    def text(self, x, y, content, size=12, color=COLOR_LABEL,
             anchor="middle", bold=False, italic=False):
        fw = "bold" if bold else "normal"
        fs = "italic" if italic else "normal"
        self.add(
            f'<text x="{x:.2f}" y="{y:.2f}" font-family="{FONT}" font-size="{size}" '
            f'fill="{color}" text-anchor="{anchor}" dominant-baseline="central" '
            f'font-weight="{fw}" font-style="{fs}">{content}</text>'
        )

    def text_rotated(self, x, y, content, angle, size=12, color=COLOR_DIM, anchor="middle"):
        self.add(
            f'<text x="{x:.2f}" y="{y:.2f}" font-family="{FONT}" font-size="{size}" '
            f'fill="{color}" text-anchor="{anchor}" dominant-baseline="central" '
            f'transform="rotate({angle},{x:.2f},{y:.2f})">{content}</text>'
        )

    def _arrow(self, x, y, angle_deg):
        a = math.radians(angle_deg)
        tip   = (x, y)
        left  = (x - ARROW_LEN * math.cos(a) + ARROW_W * math.sin(a),
                 y - ARROW_LEN * math.sin(a) - ARROW_W * math.cos(a))
        right = (x - ARROW_LEN * math.cos(a) - ARROW_W * math.sin(a),
                 y - ARROW_LEN * math.sin(a) + ARROW_W * math.cos(a))
        self.polygon([tip, left, right], fill=COLOR_DIM, stroke=COLOR_DIM, sw=0)

    def dim_h(self, x1, y_base, x2, label, above=True):
        sign  = -1 if above else 1
        y_dim = y_base + sign * DIM_OFFSET
        for xp in (x1, x2):
            y0 = y_base - sign * EXT_MARGIN
            y1 = y_dim + sign * 6
            self.line(xp, min(y0, y1), xp, max(y0, y1), stroke=COLOR_DIM, sw=0.8)
        self.line(x1, y_dim, x2, y_dim, stroke=COLOR_DIM, sw=0.9)
        self._arrow(x1, y_dim, 180)
        self._arrow(x2, y_dim, 0)
        mx = (x1 + x2) / 2
        self.rect(mx - 22, y_dim - 7, 44, 13, fill="white", stroke="none", sw=0)
        self.text(mx, y_dim, label, size=LABEL_SIZE, color=COLOR_DIM)

    def dim_v(self, y1, x_base, y2, label, left_side=True):
        sign  = -1 if left_side else 1
        x_dim = x_base + sign * DIM_OFFSET
        for yp in (y1, y2):
            x0 = x_base - sign * EXT_MARGIN
            x1_ = x_dim + sign * 6
            self.line(min(x0, x1_), yp, max(x0, x1_), yp, stroke=COLOR_DIM, sw=0.8)
        self.line(x_dim, y1, x_dim, y2, stroke=COLOR_DIM, sw=0.9)
        self._arrow(x_dim, y1, 270)
        self._arrow(x_dim, y2, 90)
        my = (y1 + y2) / 2
        self.rect(x_dim - 7, my - 22, 13, 44, fill="white", stroke="none", sw=0)
        self.text_rotated(x_dim, my, label, -90, size=LABEL_SIZE, color=COLOR_DIM)

    def center_cross(self, cx, cy, size=10):
        self.line(cx - size, cy, cx + size, cy,
                  stroke=COLOR_CENTERLINE, sw=0.7, dash="5,3")
        self.line(cx, cy - size, cx, cy + size,
                  stroke=COLOR_CENTERLINE, sw=0.7, dash="5,3")

    def view_title(self, cx, y, label):
        self.text(cx, y, label, size=VIEW_TITLE, color=COLOR_LABEL, bold=True)

    def build(self):
        body = "\n".join(self._elems)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}">\n'
            f'{body}\n'
            f'</svg>'
        )


# ── 等角投影 ──────────────────────────────────────────────────────────────────

def iso_pt(x, y, z, scale, ox, oy):
    cos30 = math.cos(math.radians(30))
    sin30 = math.sin(math.radians(30))
    sx =  (x - z) * cos30 * scale + ox
    sy = -(y - (x + z) * sin30) * scale + oy
    return sx, sy


# ── 寸法データ抽出 ────────────────────────────────────────────────────────────

def extract_dims(req: dict, params: dict) -> dict:
    d = {
        "product_name": "部品",
        "width":  100.0,
        "depth":   80.0,
        "height":  40.0,
        "wall":     2.0,
        "fillet":   1.5,
        "mfg_method": "",
        "mounting_holes": [],
        "cable_holes":    [],
        "pcb": None,
    }

    if req:
        d["product_name"] = req.get("product_name", d["product_name"])
        outer = req.get("dimensions", {}).get("outer", {})
        d["width"]  = float(outer.get("width_mm",  d["width"]))
        d["height"] = float(outer.get("height_mm", d["height"]))
        d["depth"]  = float(outer.get("depth_mm",  d["depth"]))
        d["mfg_method"] = req.get("manufacturing", {}).get("method", "")

    if params:
        def vp(section, key):
            s = params.get(section, {})
            return float(s[key]["value"]) if key in s else None

        d["width"]  = vp("outer_envelope", "width")  or d["width"]
        d["depth"]  = vp("outer_envelope", "depth")  or d["depth"]
        d["height"] = vp("outer_envelope", "height") or d["height"]
        d["wall"]   = vp("global", "wall_thickness") or d["wall"]
        d["fillet"] = vp("global", "fillet_radius")  or d["fillet"]

        px = vp("mounting_interface", "bolt_hole_pitch_x")
        py = vp("mounting_interface", "bolt_hole_pitch_y")
        bd = vp("mounting_interface", "bolt_hole_diameter")
        if px and py and bd:
            cx, cy = d["width"] / 2, d["depth"] / 2
            r = bd / 2
            d["mounting_holes"] = [
                (cx - px/2, cy - py/2, r),
                (cx + px/2, cy - py/2, r),
                (cx - px/2, cy + py/2, r),
                (cx + px/2, cy + py/2, r),
            ]

        cd = vp("openings", "cable_hole_diameter")
        cz = vp("openings", "cable_hole_offset_z") or d["height"] / 2
        if cd:
            d["cable_holes"] = [("left", cz, cd / 2)]

        pw = vp("internal_cavity", "pcb_width")
        pd = vp("internal_cavity", "pcb_depth")
        ph = vp("internal_cavity", "pcb_standoff_height")
        if pw and pd:
            d["pcb"] = {"w": pw, "d": pd, "h_standoff": ph or 5.0}

    return d


# ── 各ビューの描画 ────────────────────────────────────────────────────────────

def draw_front(svg, d, ox, oy, sc):
    W, H = d["width"] * sc, d["height"] * sc
    wall = d["wall"] * sc
    fr   = d["fillet"] * sc
    svg.rect(ox, oy, W, H, fill=COLOR_FACE_FRONT, stroke=COLOR_OUTLINE, sw=2.0, rx=fr)
    svg.rect(ox + wall, oy + wall, W - 2*wall, H - 2*wall,
             fill="none", stroke=COLOR_HIDDEN, sw=0.9, dash="6,3",
             rx=max(0.0, fr - wall))
    for side, fz, fr_hole in d["cable_holes"]:
        r = fr_hole * sc
        hy = oy + H - fz * sc
        hx = ox + (wall / 2 if side == "left" else W / 2)
        svg.circle(hx, hy, r, stroke=COLOR_HIDDEN, sw=1.0, dash="4,2")
        svg.center_cross(hx, hy, r + 6)
    svg.dim_h(ox, oy, ox + W, f"{d['width']:.0f}", above=True)
    svg.dim_v(oy, ox, oy + H, f"{d['height']:.0f}", left_side=True)
    svg.view_title(ox + W/2, oy + H + 30, "正面図 FRONT VIEW")


def draw_side(svg, d, ox, oy, sc):
    D, H = d["depth"] * sc, d["height"] * sc
    wall = d["wall"] * sc
    fr   = d["fillet"] * sc
    svg.rect(ox, oy, D, H, fill=COLOR_FACE_SIDE, stroke=COLOR_OUTLINE, sw=2.0, rx=fr)
    svg.rect(ox + wall, oy + wall, D - 2*wall, H - 2*wall,
             fill="none", stroke=COLOR_HIDDEN, sw=0.9, dash="6,3",
             rx=max(0.0, fr - wall))
    for side, fz, fr_hole in d["cable_holes"]:
        if side == "left":
            r = fr_hole * sc
            hy = oy + H - fz * sc
            hx = ox + wall / 2
            svg.circle(hx, hy, r, stroke=COLOR_OUTLINE, sw=1.0)
            svg.center_cross(hx, hy, r + 6)
    svg.dim_h(ox, oy, ox + D, f"{d['depth']:.0f}", above=True)
    svg.dim_v(oy, ox + D, oy + H, f"{d['height']:.0f}", left_side=False)
    svg.view_title(ox + D/2, oy + H + 30, "側面図 SIDE VIEW")


def draw_top(svg, d, ox, oy, sc):
    W, Dp = d["width"] * sc, d["depth"] * sc
    wall  = d["wall"] * sc
    fr    = d["fillet"] * sc
    svg.rect(ox, oy, W, Dp, fill=COLOR_FACE_TOP, stroke=COLOR_OUTLINE, sw=2.0, rx=fr)
    svg.rect(ox + wall, oy + wall, W - 2*wall, Dp - 2*wall,
             fill="none", stroke=COLOR_HIDDEN, sw=0.9, dash="6,3",
             rx=max(0.0, fr - wall))
    if d["pcb"]:
        pcb_w = d["pcb"]["w"] * sc
        pcb_d = d["pcb"]["d"] * sc
        pcb_ox = ox + (W - pcb_w) / 2
        pcb_oy = oy + (Dp - pcb_d) / 2
        svg.rect(pcb_ox, pcb_oy, pcb_w, pcb_d,
                 fill="none", stroke="#4477aa", sw=0.8, dash="3,3")
    for hx, hy, hr in d["mounting_holes"]:
        sx, sy, sr = ox + hx * sc, oy + hy * sc, hr * sc
        svg.circle(sx, sy, sr, fill="none", stroke=COLOR_OUTLINE, sw=1.2)
        svg.center_cross(sx, sy, sr + 6)
    mh = d["mounting_holes"]
    if len(mh) >= 2:
        px_mm = abs(mh[1][0] - mh[0][0])
        svg.dim_h(ox + mh[0][0]*sc, oy - 5,
                  ox + mh[1][0]*sc, f"P.C.D {px_mm:.0f}", above=True)
    if len(mh) >= 3:
        py_mm = abs(mh[2][1] - mh[0][1])
        svg.dim_v(oy + mh[0][1]*sc, ox - 5,
                  oy + mh[2][1]*sc, f"P.C.D {py_mm:.0f}", left_side=True)
    svg.dim_h(ox, oy + Dp, ox + W, f"{d['width']:.0f}", above=False)
    svg.dim_v(oy, ox + W, oy + Dp, f"{d['depth']:.0f}", left_side=False)
    svg.view_title(ox + W/2, oy - 22, "上面図 TOP VIEW")


def draw_isometric(svg, d, cx, cy, sc):
    W, D, H = d["width"], d["depth"], d["height"]
    iso_sc = sc * 0.65

    def pt(x, y, z):
        return iso_pt(x, y, z, iso_sc, cx, cy)

    c = {
        "fbl": pt(0, 0, 0), "fbr": pt(W, 0, 0),
        "ftr": pt(W, H, 0), "ftl": pt(0, H, 0),
        "bbl": pt(0, 0, D), "bbr": pt(W, 0, D),
        "btr": pt(W, H, D), "btl": pt(0, H, D),
    }
    svg.polygon([c["ftl"], c["ftr"], c["btr"], c["btl"]],
                fill=COLOR_FACE_TOP,  stroke=COLOR_OUTLINE, sw=1.5)
    svg.polygon([c["fbl"], c["fbr"], c["ftr"], c["ftl"]],
                fill=COLOR_FACE_FRONT, stroke=COLOR_OUTLINE, sw=1.5)
    svg.polygon([c["fbr"], c["bbr"], c["btr"], c["ftr"]],
                fill=COLOR_FACE_SIDE,  stroke=COLOR_OUTLINE, sw=1.5)
    for p, q in [
        (c["fbl"], c["fbr"]), (c["fbr"], c["ftr"]),
        (c["ftr"], c["ftl"]), (c["ftl"], c["fbl"]),
        (c["fbl"], c["bbl"]), (c["fbr"], c["bbr"]),
        (c["bbl"], c["bbr"]), (c["bbr"], c["btr"]),
        (c["btr"], c["btl"]), (c["btl"], c["ftl"]),
        (c["ftr"], c["btr"]),
    ]:
        svg.line(*p, *q, stroke=COLOR_OUTLINE, sw=2.0)
    for hx, hy, hr in d["mounting_holes"]:
        hp = pt(hx, H, hy)
        svg.circle(*hp, hr * iso_sc * 0.85, fill="#ccccdd", stroke=COLOR_OUTLINE, sw=0.8)
        svg.center_cross(*hp, hr * iso_sc * 1.6)
    dc = COLOR_DIM
    wb, we = pt(0, -6, 0), pt(W, -6, 0)
    svg.line(*wb, *we, stroke=dc, sw=0.8)
    svg.text((wb[0]+we[0])/2, (wb[1]+we[1])/2 - 9, f"W {W:.0f}", size=11, color=dc)
    hl, ht = pt(-5, 0, 0), pt(-5, H, 0)
    svg.line(*hl, *ht, stroke=dc, sw=0.8)
    svg.text((hl[0]+ht[0])/2 - 14, (hl[1]+ht[1])/2, f"H {H:.0f}", size=11, color=dc)
    df_, db = pt(W+5, 0, 0), pt(W+5, 0, D)
    svg.line(*df_, *db, stroke=dc, sw=0.8)
    svg.text((df_[0]+db[0])/2 + 15, (df_[1]+db[1])/2, f"D {D:.0f}", size=11, color=dc)
    bottom_pt = pt(W/2, 0, D)
    svg.view_title(cx, bottom_pt[1] + 28, "等角図 ISOMETRIC VIEW")


def draw_title_block(svg, d, cw, ch, pad, th):
    ty = ch - th
    tw = cw - pad * 2
    svg.rect(pad, ty, tw, th, fill=COLOR_TITLE_BG, stroke=COLOR_TITLE_BG, sw=0)
    svg.text(pad + 24, ty + th * 0.35, d["product_name"],
             size=22, color=COLOR_TITLE_TEXT, anchor="start", bold=True)
    info = f"W{d['width']:.0f} x D{d['depth']:.0f} x H{d['height']:.0f} mm"
    if d["mfg_method"]:
        info += f"  |  {d['mfg_method']}"
    svg.text(pad + 24, ty + th * 0.72, info,
             size=13, color=COLOR_SUBTITLE, anchor="start")
    today = date.today().strftime("%Y-%m-%d")
    svg.text(pad + tw - 24, ty + th * 0.35,
             "技術図面 / TECHNICAL DRAWING",
             size=14, color=COLOR_SUBTITLE, anchor="end")
    svg.text(pad + tw - 24, ty + th * 0.72,
             f"作成日: {today}  |  text-to-cad skill",
             size=11, color=COLOR_SUBTITLE, anchor="end")


# ── メイン ────────────────────────────────────────────────────────────────────

def generate_svg(req_data, param_data, output_path):
    d = extract_dims(req_data, param_data)
    W, D, H = d["width"], d["depth"], d["height"]

    svg = SVGBuilder(CANVAS_W, CANVAS_H)
    svg.rect(0, 0, CANVAS_W, CANVAS_H, fill=COLOR_BG, stroke="none", sw=0)

    da_x, da_y = PADDING, PADDING
    da_w = CANVAS_W - PADDING * 2
    da_h = CANVAS_H - PADDING * 2 - TITLE_H
    svg.rect(da_x, da_y, da_w, da_h, fill="#f9f9fd", stroke="#ccccdd", sw=1.0, rx=4)

    left_w    = da_w * 0.60
    inner_pad = PADDING * 1.2
    max_sc_x  = (left_w - VIEW_GAP - inner_pad * 2) / (W + D)
    max_sc_y  = (da_h   - VIEW_GAP - inner_pad * 3) / (D + H)
    sc = min(max_sc_x, max_sc_y, 5.0)

    v_ox, v_oy = da_x + inner_pad, da_y + inner_pad

    top_ox,   top_oy   = v_ox,                   v_oy
    front_ox, front_oy = v_ox,                   v_oy + D*sc + VIEW_GAP
    side_ox,  side_oy  = v_ox + W*sc + VIEW_GAP, front_oy

    iso_cx = da_x + left_w + (da_w - left_w) * 0.5
    iso_cy = da_y + da_h * 0.42

    draw_top(svg, d, top_ox, top_oy, sc)
    draw_front(svg, d, front_ox, front_oy, sc)
    draw_side(svg, d, side_ox, side_oy, sc)
    draw_isometric(svg, d, iso_cx, iso_cy, sc)

    svg.text(da_x + 10, da_y + da_h - 12,
             "第三角法 / Third-angle projection",
             size=10, color="#aaaaaa", anchor="start", italic=True)
    draw_title_block(svg, d, CANVAS_W, CANVAS_H, PADDING, TITLE_H)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg.build(), encoding="utf-8")
    print(f"✅ SVG 技術図面を生成しました: {output_path}")
    return str(out)


def main():
    parser = argparse.ArgumentParser(
        description="requirements.json / parameters.json から SVG 技術図面を生成"
    )
    parser.add_argument("--req",    help="requirements.json のパス (Stage 1 出力)")
    parser.add_argument("--params", help="parameters.json のパス (Stage 4 入力)")
    parser.add_argument("--out",    default="views/technical_drawing.svg",
                        help="出力 SVG パス (デフォルト: views/technical_drawing.svg)")
    args = parser.parse_args()

    if not args.req and not args.params:
        print("❌ --req または --params のいずれかを指定してください")
        parser.print_help()
        sys.exit(1)

    req_data = param_data = None
    if args.req:
        with open(args.req, encoding="utf-8") as f:
            req_data = json.load(f)
        print(f"📄 requirements.json 読み込み: {args.req}")
    if args.params:
        with open(args.params, encoding="utf-8") as f:
            param_data = json.load(f)
        print(f"📄 parameters.json 読み込み: {args.params}")

    generate_svg(req_data, param_data, args.out)


if __name__ == "__main__":
    main()
