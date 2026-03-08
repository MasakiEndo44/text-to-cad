#!/usr/bin/env python3
"""
Stage 2: SVG 技術図面生成スクリプト (v3 — 正投影図法準拠)

requirements.json または parameters.json から
正面図・側面図・底面図の3面図を含む工業図面スタイルの SVG を生成する。

穴フィーチャーの投影ルール (JIS B 0001 / ISO 128 準拠):
  - 穴軸が視線と平行 → 円 (実線 or 隠れ線) ＋ 中心線クロス
  - 穴軸が視線と直交 → 2本の平行破線 (穴径間隔) ＋ 1本の中心線 (一点鎖線)
    線の長さは穴深さ (= 壁厚、貫通穴の場合)

外部 API・ライブラリは不要。Python 標準ライブラリのみ使用。

使用方法:
  python stage2_svg_views.py --req requirements.json --out views/
  python stage2_svg_views.py --params parameters.json --out views/
  python stage2_svg_views.py --req requirements.json --params parameters.json --out views/

出力:
  views/technical_drawing.svg  ← ブラウザで直接開ける
"""

import json
import math
import re
import sys
import os
import argparse
from datetime import date
from pathlib import Path

# ── 定数 ──────────────────────────────────────────────────────────────────────
CANVAS_W = 1400
CANVAS_H = 950
PADDING  = 50
TITLE_H  = 80
VIEW_GAP = 65          # ビュー間の余白 (px)

# 色
COLOR_OUTLINE    = "#1a1a2e"   # 外形線（濃い紺）
COLOR_HIDDEN     = "#888888"   # 隠れ線（破線）
COLOR_CENTERLINE = "#cc3333"   # 中心線（一点鎖線）
COLOR_DIM        = "#1a5fb4"   # 寸法線・テキスト
COLOR_LABEL      = "#222222"   # ビュー名
COLOR_BG         = "#ffffff"
COLOR_FACE_FRONT = "#eef1f8"   # 正面の面色
COLOR_FACE_TOP   = "#f4f6fb"   # 上面の面色（底面図でも使用）
COLOR_FACE_SIDE  = "#dde2f0"   # 側面の面色
COLOR_TITLE_BG   = "#1a1a2e"
COLOR_TITLE_TEXT = "#ffffff"
COLOR_SUBTITLE   = "#9999cc"
COLOR_FEATURE    = "#2d6a4f"   # フィーチャー穴（緑系、実線）
COLOR_FEATURE_HIDDEN = "#888888"  # フィーチャー穴（隠れ線）
COLOR_FEAT_LABEL = "#2d6a4f"   # フィーチャーラベル

FONT = "Noto Sans JP, Meiryo, Yu Gothic, Arial, sans-serif"

ARROW_LEN  = 9
ARROW_W    = 3.5
DIM_OFFSET = 22
EXT_MARGIN = 6
LABEL_SIZE = 12
VIEW_TITLE = 14
FEAT_LABEL_SIZE = 9
CL_MARGIN  = 4   # 中心線の線端余白 (px)


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
        """中心線クロス（穴を正面から見たとき）"""
        self.line(cx - size, cy, cx + size, cy,
                  stroke=COLOR_CENTERLINE, sw=0.7, dash="8,3,2,3")
        self.line(cx, cy - size, cx, cy + size,
                  stroke=COLOR_CENTERLINE, sw=0.7, dash="8,3,2,3")

    def view_title(self, cx, y, label):
        self.text(cx, y, label, size=VIEW_TITLE, color=COLOR_LABEL, bold=True)

    # ── フィーチャー描画プリミティブ ──

    def feature_circle(self, cx, cy, r, hidden=False):
        """穴を軸方向から見た投影: 円＋中心線クロス"""
        if hidden:
            self.circle(cx, cy, r, stroke=COLOR_FEATURE_HIDDEN, sw=0.8, dash="4,2")
            # 隠れ穴でも中心線は描く（やや薄く）
            self.center_cross(cx, cy, max(r + 4, 8))
        else:
            self.circle(cx, cy, r, stroke=COLOR_FEATURE, sw=1.2)
            self.center_cross(cx, cy, max(r + 4, 8))

    def feature_side_h(self, cy, r, x_start, x_end, hidden=True):
        """穴を側面から見た投影（穴軸が水平方向）:
        2本の水平平行破線（穴径間隔）＋ 水平中心線（一点鎖線）

        cy:      穴中心の Y 座標 (px)
        r:       穴半径 (px)
        x_start: 穴始端の X 座標 (px) — 面の外縁
        x_end:   穴終端の X 座標 (px) — 壁厚だけ内側
        """
        stroke = COLOR_FEATURE_HIDDEN if hidden else COLOR_FEATURE
        dash   = "4,2"
        # 2本の平行破線
        self.line(x_start, cy - r, x_end, cy - r, stroke=stroke, sw=0.8, dash=dash)
        self.line(x_start, cy + r, x_end, cy + r, stroke=stroke, sw=0.8, dash=dash)
        # 中心線（一点鎖線）— 両端を少しはみ出す
        self.line(min(x_start, x_end) - CL_MARGIN, cy,
                  max(x_start, x_end) + CL_MARGIN, cy,
                  stroke=COLOR_CENTERLINE, sw=0.5, dash="8,3,2,3")

    def feature_side_v(self, cx, r, y_start, y_end, hidden=True):
        """穴を側面から見た投影（穴軸が垂直方向）:
        2本の垂直平行破線（穴径間隔）＋ 垂直中心線（一点鎖線）

        cx:      穴中心の X 座標 (px)
        r:       穴半径 (px)
        y_start: 穴始端の Y 座標 (px) — 面の外縁
        y_end:   穴終端の Y 座標 (px) — 壁厚だけ内側
        """
        stroke = COLOR_FEATURE_HIDDEN if hidden else COLOR_FEATURE
        dash   = "4,2"
        self.line(cx - r, y_start, cx - r, y_end, stroke=stroke, sw=0.8, dash=dash)
        self.line(cx + r, y_start, cx + r, y_end, stroke=stroke, sw=0.8, dash=dash)
        self.line(cx, min(y_start, y_end) - CL_MARGIN,
                  cx, max(y_start, y_end) + CL_MARGIN,
                  stroke=COLOR_CENTERLINE, sw=0.5, dash="8,3,2,3")

    def feature_label(self, x, y, label, offset_x=0, offset_y=-12):
        """フィーチャーラベルを描画"""
        self.text(x + offset_x, y + offset_y, label,
                  size=FEAT_LABEL_SIZE, color=COLOR_FEAT_LABEL, anchor="middle")

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


# ── インターフェース解析 ─────────────────────────────────────────────────────
# (v2 から変更なし)

def _parse_number(text, pattern):
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def _classify_face(iface):
    pos = iface.get("position", "").lower()
    itype = iface.get("type", "").lower()
    spec = iface.get("spec", "").lower()
    if "front" in pos:
        return "front"
    if "back" in pos or "背面" in pos:
        if "bottom" in pos:
            return "bottom"
        return "back"
    if "bottom" in pos or "底面" in pos:
        return "bottom"
    if "top" in pos or "上面" in pos:
        return "top"
    if "left" in pos or "right" in pos or "側面" in pos:
        return "side"
    if itype == "mounting_hole" and ("背面" in spec or "壁" in spec):
        return "back"
    if itype == "screw_boss":
        return "front"
    return "front"


def _resolve_hole_positions(iface, face, W, H, D, wall):
    dia = float(iface.get("hole_diameter_mm", 5.0))
    spec = iface.get("spec", "")
    name = iface.get("name", "")
    pos  = iface.get("position", "")
    itype = iface.get("type", "")
    label = _make_label(name, dia, itype)
    results = []
    spacing_str = iface.get("spacing", "")

    if face == "back" and (spacing_str or itype == "mounting_hole" or "耳" in name):
        sw = sh = None
        if spacing_str:
            nums = re.findall(r'(\d+\.?\d*)mm', spacing_str)
            if len(nums) >= 2:
                sw, sh = float(nums[0]), float(nums[1])
            elif len(nums) == 1:
                if "上下" in spacing_str or "縦" in spacing_str:
                    sh = float(nums[0])
                    sw = W + 12
                else:
                    sw = float(nums[0])
                    sh = H + 12
        else:
            if "耳" in name or "取付" in name:
                sw = W + 12
                sh = H - 20

        edge = _parse_number(spec, r'端から(\d+\.?\d*)mm') or 6.0
        if sw is not None and sh is not None:
            cx, cy = W / 2, H / 2
            dxs = [-sw/2, sw/2] if sw > 0.001 else [0]
            dys = [-sh/2, sh/2] if sh > 0.001 else [0]
            for dx in dxs:
                for dy in dys:
                    results.append((face, cx + dx, cy + dy, dia, label))
            return results
        for x in (edge, W - edge):
            for y in (edge, H - edge):
                results.append((face, x, y, dia, label))
        return results

    if face == "front" and itype == "screw_boss":
        offset = _parse_number(spec, r'(\d+\.?\d*)mm.*内側') or 10.0
        for x in (offset, W - offset):
            for y in (offset, H - offset):
                results.append((face, x, y, dia, label))
        return results

    if face == "bottom":
        num_m = re.search(r'[×x]\s*(\d+)', name)
        num_holes = int(num_m.group(1)) if num_m else None
        if num_holes is None:
            num_m2 = re.search(r'(\d+)\s*個', spec)
            num_holes = int(num_m2.group(1)) if num_m2 else 1
        center_dist = _parse_number(spec, r'中心間距離\s*(\d+\.?\d*)mm')
        cx = W / 2
        if "rear" in pos.lower() or "奥" in spec or "背面寄り" in spec:
            cy = D * 0.75
        elif "front" in pos.lower() or "前" in spec:
            cy = D * 0.25
        else:
            cy = D / 2
        if center_dist and num_holes >= 2:
            for i in range(num_holes):
                off = center_dist * (i - (num_holes - 1) / 2)
                results.append((face, cx + off, cy, dia, label))
        else:
            if num_holes >= 2:
                # center_dist 未指定: 同一座標への重複追加を防ぎ、幅方向に均等配置
                print(f"⚠️ WARN: '{name}' の中心間距離が未指定。"
                      f"幅方向に均等配置します（要確認: requirements.json に spacing を追加推奨）")
                spacing_fallback = W * 0.5
                for i in range(num_holes):
                    off = spacing_fallback * (i - (num_holes - 1) / 2)
                    results.append((face, cx + off, cy, dia, label))
            else:
                results.append((face, cx, cy, dia, label))
        return results

    if face == "front" and itype in ("through_hole", "led"):
        combined = pos + " " + spec
        x = _parse_number(combined, r'[wW][=＝]?\s*(\d+\.?\d*)mm')
        if x is None or "中央" in combined:
            x = W / 2
        y = _parse_number(combined, r'[hH上].*?(\d+\.?\d*)mm')
        if y is None:
            y = H / 2
        results.append((face, x, y, dia, label))
        return results

    if face in ("front", "back"):
        results.append((face, W / 2, H / 2, dia, label))
    elif face in ("bottom", "top"):
        results.append((face, W / 2, D / 2, dia, label))
    elif face == "side":
        results.append((face, D / 2, H / 2, dia, label))
    else:
        results.append((face, W / 2, H / 2, dia, label))
    return results


def _make_label(name, dia, itype):
    n = name.lower()
    if "pg7" in n or "ケーブルグランド" in n:
        return "PG7"
    if "led" in n:
        return f"φ{dia:.1f} LED"
    if "ベント" in n or "vent" in n:
        return f"φ{dia:.0f} VENT"
    if "壁面" in n or "wall" in n or ("mounting" in itype):
        return "M4 取付"
    if "ヒートセット" in n or "インサート" in n or "screw_boss" in itype:
        return "M3 ins."
    return f"φ{dia:.1f}"


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
        "features": [],
        "pcb": None,
    }

    if req:
        d["product_name"] = req.get("product_name", d["product_name"])
        outer = req.get("dimensions", {}).get("outer", {})
        d["width"]  = float(outer.get("width_mm",  d["width"]))
        d["height"] = float(outer.get("height_mm", d["height"]))
        d["depth"]  = float(outer.get("depth_mm",  d["depth"]))
        d["wall"]   = float(req.get("dimensions", {}).get("wall_thickness_mm", d["wall"]))
        d["mfg_method"] = req.get("manufacturing", {}).get("method", "")

        W, H, D, wall = d["width"], d["height"], d["depth"], d["wall"]
        for iface in req.get("interfaces", []):
            face = _classify_face(iface)
            holes = _resolve_hole_positions(iface, face, W, H, D, wall)
            d["features"].extend(holes)

        for comp in req.get("internal_components", []):
            dims_str = comp.get("dimensions", "")
            nums = re.findall(r'(\d+\.?\d*)mm', dims_str)
            if len(nums) >= 2:
                d["pcb"] = {"w": float(nums[0]), "d": float(nums[1]),
                            "h_standoff": float(nums[2]) if len(nums) >= 3 else 5.0,
                            "label": comp.get("name", "PCB")}
                break

        fl = {"l": 0, "r": 0, "t": 0, "b": 0}
        for f, fx, fy, dia, lbl in d["features"]:
            if f == "back":
                r = dia/2 + 5
                if fx - r < 0: fl["l"] = max(fl["l"], -(fx - r))
                if fx + r > d["width"]: fl["r"] = max(fl["r"], (fx + r) - d["width"])
                if fy - r < 0: fl["t"] = max(fl["t"], -(fy - r))
                if fy + r > d["height"]: fl["b"] = max(fl["b"], (fy + r) - d["height"])
        d["flange"] = fl

    if params:
        def vp(section, key):
            s = params.get(section, {})
            return float(s[key]["value"]) if key in s else None
        d["width"]  = vp("outer_envelope", "width")  or d["width"]
        d["depth"]  = vp("outer_envelope", "depth")  or d["depth"]
        d["height"] = vp("outer_envelope", "height") or d["height"]
        d["wall"]   = vp("global", "wall_thickness") or d["wall"]
        d["fillet"] = vp("global", "fillet_radius")  or d["fillet"]
        pw = vp("internal_cavity", "pcb_width")
        pd = vp("internal_cavity", "pcb_depth")
        ph = vp("internal_cavity", "pcb_standoff_height")
        if pw and pd:
            d["pcb"] = {"w": pw, "d": pd, "h_standoff": ph or 5.0}

    return d


# ── ラベル重複防止ヘルパー ────────────────────────────────────────────────────

def _label_key(label, px, py, grid=20):
    return f"{label}_{round(px/grid)}_{round(py/grid)}"


# ── 各ビューの描画 ────────────────────────────────────────────────────────────
#
#  3D 座標系:  X = 左→右 (0..W)
#              Y = 上→下 (0..H)   ← 図面の上が上
#              Z = 手前→奥 (0..D)
#
#  穴の軸方向:
#    front 面 (z=0) → 軸 +Z     back 面 (z=D) → 軸 -Z
#    bottom面 (y=H) → 軸 -Y     top 面 (y=0)  → 軸 +Y
#    side 面        → 軸 ±X
#
#  投影ルール:
#    軸 ∥ 視線 → 円 (実線 or 隠れ線)
#    軸 ⊥ 視線 → 2本平行破線 + 中心線 (深さ=壁厚)
# ─────────────────────────────────────────────────────────────────────────────

def draw_front(svg, d, ox, oy, sc):
    """正面図 — 視線 -Z方向、XY 平面を見る (W × H)"""
    W  = d["width"]  * sc
    H  = d["height"] * sc
    wp = d["wall"]   * sc   # wall in px
    fr = d["fillet"]  * sc

    fl = d.get("flange", {"l":0, "r":0, "t":0, "b":0})
    if any(fl.values()):
        svg.rect(ox - fl["l"]*sc, oy - fl["t"]*sc, W + (fl["l"]+fl["r"])*sc, H + (fl["t"]+fl["b"])*sc,
                 fill=COLOR_FACE_SIDE, stroke=COLOR_OUTLINE, sw=1.5, rx=fr)

    # 外形 + 内壁隠れ線
    svg.rect(ox, oy, W, H, fill=COLOR_FACE_FRONT, stroke=COLOR_OUTLINE, sw=2.0, rx=fr)

    svg.rect(ox + wp, oy + wp, W - 2*wp, H - 2*wp,
             fill="none", stroke=COLOR_HIDDEN, sw=0.9, dash="6,3",
             rx=max(0.0, fr - wp))
    drawn_labels = []
    drawn_keys = set()
    def place_label(x, y, label, ox_off, oy_off):
        if label in drawn_keys:
            return
        drawn_keys.add(label)
        
        lx, ly = x + ox_off, y + oy_off
        for _ in range(15):
            if not any(abs(lx - ex) < 35 and abs(ly - ey) < 14 for ex, ey in drawn_labels):
                break
            ly += 14
        if abs(ly - (y + oy_off)) > 1:
            svg.line(x, y, lx - 10 if ox_off > 0 else lx + 10, ly, stroke=COLOR_HIDDEN, sw=0.5)
        svg.feature_label(lx, ly, label, offset_x=0, offset_y=0)
        drawn_labels.append((lx, ly))



    for face, fx, fy, dia, label in d["features"]:
        r = (dia / 2) * sc

        if face == "front":
            # 軸 +Z ∥ 視線 → 実線の円
            cx, cy = ox + fx * sc, oy + fy * sc
            svg.feature_circle(cx, cy, r, hidden=False)
            place_label(cx, cy, label, max(r+6, 12), -max(r+4, 10))

        elif face == "back":
            # 軸 -Z ∥ 視線 (裏側) → 隠れ線の円
            cx, cy = ox + fx * sc, oy + fy * sc

            svg.feature_circle(cx, cy, r, hidden=True)
            place_label(cx, cy, label, max(r+6, 12), -max(r+4, 10))

        elif face == "bottom":
            # 軸 -Y ⊥ 視線 → 2本の垂直破線 (底辺から壁厚分)
            cx = ox + fx * sc
            svg.feature_side_v(cx, r, oy + H - wp, oy + H, hidden=True)
            place_label(cx, oy + H - wp, label, max(r+6, 12), -6)

        elif face == "top":
            # 軸 +Y ⊥ 視線 → 2本の垂直破線 (上辺から壁厚分)
            cx = ox + fx * sc
            svg.feature_side_v(cx, r, oy, oy + wp, hidden=True)

    # 寸法線
    # svg.dim_h(ox, oy, ox + W, f"{d['width']:.0f}", above=True) # 底面図とダブるため省略
    svg.dim_v(oy, ox, oy + H, f"{d['height']:.0f}", left_side=True)
    svg.view_title(ox + W/2, oy + H + 30, "正面図 FRONT VIEW")


def draw_side(svg, d, ox, oy, sc):
    """側面図（右側面）— 視線 -X方向、ZY 平面を見る (D × H)
       u 軸 = Z (手前→奥 = 左→右)、v 軸 = Y (上→下)
    """
    Dp = d["depth"]  * sc
    H  = d["height"] * sc
    wp = d["wall"]   * sc
    fr = d["fillet"]  * sc

    fl = d.get("flange", {"l":0, "r":0, "t":0, "b":0})
    if any(fl.values()):
        svg.rect(ox + Dp - wp, oy - fl["t"]*sc, wp, H + (fl["t"]+fl["b"])*sc, fill=COLOR_FACE_SIDE, stroke=COLOR_OUTLINE, sw=1.5, rx=0)

    svg.rect(ox, oy, Dp, H, fill=COLOR_FACE_SIDE, stroke=COLOR_OUTLINE, sw=2.0, rx=fr)
    svg.rect(ox + wp, oy + wp, Dp - 2*wp, H - 2*wp,
             fill="none", stroke=COLOR_HIDDEN, sw=0.9, dash="6,3",
             rx=max(0.0, fr - wp))
    drawn_labels = []
    drawn_keys = set()
    def place_label(x, y, label, ox_off, oy_off):
        if label in drawn_keys:
            return
        drawn_keys.add(label)
        
        lx, ly = x + ox_off, y + oy_off
        for _ in range(15):
            if not any(abs(lx - ex) < 35 and abs(ly - ey) < 14 for ex, ey in drawn_labels):
                break
            ly += 14
        if abs(ly - (y + oy_off)) > 1:
            svg.line(x, y, lx - 10 if ox_off > 0 else lx + 10, ly, stroke=COLOR_HIDDEN, sw=0.5)
        svg.feature_label(lx, ly, label, offset_x=0, offset_y=0)
        drawn_labels.append((lx, ly))



    for face, fx, fy, dia, label in d["features"]:
        r = (dia / 2) * sc

        if face == "front":
            # 軸 +Z ⊥ 視線 → 2本の水平破線（前面=左端から壁厚分）
            cy = oy + fy * sc
            svg.feature_side_h(cy, r, ox, ox + wp, hidden=True)
            place_label(ox + wp + 4, cy, label, 12, -max(r+3, 8))

        elif face == "back":
            # 軸 -Z ⊥ 視線 → 2本の水平破線（背面=右端から壁厚分）
            cy = oy + fy * sc
            
            svg.feature_side_h(cy, r, ox + Dp - wp, ox + Dp, hidden=True)
            place_label(ox + Dp - wp - 4, cy, label, -12, -max(r+3, 8))

        elif face == "bottom":
            # 軸 -Y ⊥ 視線 → 2本の垂直破線（底辺から壁厚分）
            # fy は底面上の depth 方向座標 → 側面図の u 座標
            cu = ox + fy * sc
            svg.feature_side_v(cu, r, oy + H - wp, oy + H, hidden=True)
            place_label(cu, oy + H - wp, label, max(r+6, 10), -6)

        elif face == "side":
            # 軸 ±X ∥ 視線 → 円
            cx, cy = ox + fx * sc, oy + fy * sc
            svg.feature_circle(cx, cy, r, hidden=False)

    svg.dim_h(ox, oy, ox + Dp, f"{d['depth']:.0f}", above=True)
    svg.dim_v(oy, ox + Dp, oy + H, f"{d['height']:.0f}", left_side=False)
    svg.view_title(ox + Dp/2, oy + H + 30, "側面図 SIDE VIEW")


def draw_bottom(svg, d, ox, oy, sc):
    """底面図 — 視線 +Y方向、XZ 平面を見る (W × D)
       u 軸 = X (左→右)、v 軸 = Z (手前→奥 = 上→下)
    """
    W  = d["width"] * sc
    Dp = d["depth"] * sc
    wp = d["wall"]  * sc
    fr = d["fillet"] * sc

    fl = d.get("flange", {"l":0, "r":0, "t":0, "b":0})
    if any(fl.values()):
        svg.rect(ox - fl["l"]*sc, oy + Dp - wp, W + (fl["l"]+fl["r"])*sc, wp, fill=COLOR_FACE_SIDE, stroke=COLOR_OUTLINE, sw=1.5, rx=0)

    svg.rect(ox, oy, W, Dp, fill=COLOR_FACE_TOP, stroke=COLOR_OUTLINE, sw=2.0, rx=fr)
    svg.rect(ox + wp, oy + wp, W - 2*wp, Dp - 2*wp,
             fill="none", stroke=COLOR_HIDDEN, sw=0.9, dash="6,3",
             rx=max(0.0, fr - wp))

    # 内蔵部品フットプリント
    if d["pcb"]:
        pw = d["pcb"]["w"] * sc
        pd = d["pcb"]["d"] * sc
        svg.rect(ox + (W - pw)/2, oy + (Dp - pd)/2, pw, pd,
                 fill="none", stroke="#4477aa", sw=0.8, dash="3,3")
        pcb_label = d["pcb"].get("label", "PCB")
        svg.text(ox + W/2, oy + Dp/2, pcb_label, size=8, color="#4477aa")
    drawn_labels = []
    drawn_keys = set()
    def place_label(x, y, label, ox_off, oy_off):
        if label in drawn_keys:
            return
        drawn_keys.add(label)
        
        lx, ly = x + ox_off, y + oy_off
        for _ in range(15):
            if not any(abs(lx - ex) < 35 and abs(ly - ey) < 14 for ex, ey in drawn_labels):
                break
            ly += 14
        if abs(ly - (y + oy_off)) > 1:
            svg.line(x, y, lx - 10 if ox_off > 0 else lx + 10, ly, stroke=COLOR_HIDDEN, sw=0.5)
        svg.feature_label(lx, ly, label, offset_x=0, offset_y=0)
        drawn_labels.append((lx, ly))



    for face, fx, fy, dia, label in d["features"]:
        r = (dia / 2) * sc

        if face == "bottom":
            # 軸 -Y ∥ 視線 → 実線の円
            cx, cy = ox + fx * sc, oy + fy * sc
            svg.feature_circle(cx, cy, r, hidden=False)
            place_label(cx, cy, label, max(r+6, 12), -max(r+4, 10))

        elif face == "top":
            # 軸 +Y ∥ 視線 (裏側) → 隠れ線の円
            cx, cy = ox + fx * sc, oy + fy * sc
            svg.feature_circle(cx, cy, r, hidden=True)

        elif face == "front":
            # 軸 +Z ⊥ 視線 → 2本の水平破線（前端=上端から壁厚分）
            # front 穴は (fx, fy) = (X座標, Y/高さ座標)。底面図では X が u。
            cu = ox + fx * sc
            svg.feature_side_v(cu, r, oy, oy + wp, hidden=True)
            place_label(cu, oy + wp, label, max(r+6, 12), 10)

        elif face == "back":
            # 軸 -Z ⊥ 視線 → 2本の垂直破線（背面端=下端から壁厚分）
            cu = ox + fx * sc
            
            svg.feature_side_v(cu, r, oy + Dp - wp, oy + Dp, hidden=True)
            place_label(cu, oy + Dp - wp, label, max(r+6, 12), -6)

    # 底面穴グループ間隔寸法
    bottom_feats = [(fx, fy) for f, fx, fy, dia, lbl in d["features"] if f == "bottom"]
    if len(bottom_feats) >= 2:
        xs = sorted(set(round(fx, 2) for fx, fy in bottom_feats))
        if len(xs) >= 2:
            svg.dim_h(ox + xs[0]*sc, oy + Dp + 5,
                      ox + xs[-1]*sc, f"{xs[-1]-xs[0]:.0f}", above=False)

    # 背面取付穴ピッチ寸法
    back_feats = [(fx, fy) for f, fx, fy, dia, lbl in d["features"] if f == "back"]
    if len(back_feats) >= 2:
        bxs = sorted(set(round(fx, 2) for fx, fy in back_feats))
        if len(bxs) >= 2:
            svg.dim_h(ox + bxs[0]*sc, oy - 5,
                      ox + bxs[-1]*sc, f"P.C.D {bxs[-1]-bxs[0]:.0f}", above=True)

    # 外形寸法
    svg.dim_h(ox, oy + Dp + 28, ox + W, f"{d['width']:.0f}", above=False)
    svg.dim_v(oy, ox + W, oy + Dp, f"{d['depth']:.0f}", left_side=False)
    svg.view_title(ox + W/2, oy - 45, "底面図 BOTTOM VIEW")




def draw_title_block(svg, d, cw, ch, pad, th):
    ty = ch - th
    tw = cw - pad * 2
    svg.rect(pad, ty, tw, th, fill=COLOR_TITLE_BG, stroke=COLOR_TITLE_BG, sw=0)
    svg.text(pad + 24, ty + th * 0.35, d["product_name"],
             size=22, color=COLOR_TITLE_TEXT, anchor="start", bold=True)
    info = f"W{d['width']:.0f} x D{d['depth']:.0f} x H{d['height']:.0f} mm"
    if d["mfg_method"]:
        info += f"  |  {d['mfg_method']}"
    n_feat = len(d["features"])
    if n_feat > 0:
        info += f"  |  interfaces: {n_feat} holes"
    svg.text(pad + 24, ty + th * 0.72, info,
             size=13, color=COLOR_SUBTITLE, anchor="start")
    today = date.today().strftime("%Y-%m-%d")
    svg.text(pad + tw - 24, ty + th * 0.35,
             "技術図面 / TECHNICAL DRAWING",
             size=14, color=COLOR_SUBTITLE, anchor="end")
    svg.text(pad + tw - 24, ty + th * 0.72,
             f"作成日: {today}  |  text-to-cad skill v4",
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

    left_w    = da_w       # 3面図で全幅を使う
    inner_pad = PADDING * 1.2
    max_sc_x  = (da_w - VIEW_GAP - inner_pad * 2) / (W + D)
    max_sc_y  = (da_h - VIEW_GAP - inner_pad * 3) / (D + H)
    sc = min(max_sc_x, max_sc_y, 5.0)

    v_ox, v_oy = da_x + inner_pad, da_y + inner_pad
    plan_ox,  plan_oy  = v_ox,                   v_oy
    front_ox, front_oy = v_ox,                   v_oy + D*sc + VIEW_GAP
    side_ox,  side_oy  = v_ox + W*sc + VIEW_GAP, front_oy

    draw_bottom(svg, d, plan_ox, plan_oy, sc)
    draw_front(svg, d, front_ox, front_oy, sc)
    draw_side(svg, d, side_ox, side_oy, sc)

    svg.text(da_x + 10, da_y + da_h - 12,
             "第三角法 / Third-angle projection",
             size=10, color="#aaaaaa", anchor="start", italic=True)
    draw_title_block(svg, d, CANVAS_W, CANVAS_H, PADDING, TITLE_H)

    # フィーチャーサマリ
    faces = {}
    for face, fx, fy, dia, label in d["features"]:
        faces.setdefault(face, []).append(label)
    print("📊 フィーチャー解析結果:")
    for face, labels in faces.items():
        print(f"   {face}: {', '.join(labels)} ({len(labels)}個)")

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
