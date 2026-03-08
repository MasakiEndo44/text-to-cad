#!/usr/bin/env python3
"""
Stage 2: SVG 技術図面生成スクリプト (v4 — JIS B 0001 準拠)

requirements.json または parameters.json から
正面図・平面図（上面/底面）・右側面図の3面図を含む工業図面スタイルの SVG を生成する。

JIS B 0001 / ISO 128 準拠:
  - 第三角法のビュー配置（正面図=左下、平面図=左上、側面図=右下）
  - 寸法値は寸法線の上（水平）/ 左（垂直）に配置
  - 矢印は開き角 30° の塗りつぶし
  - 寸法線の段重ね対応（level 引数）
  - 投影法記号の描画
  - 穴位置寸法を基準面から記入

穴フィーチャーの投影ルール:
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

# JIS B 0001 準拠の矢印定数
ARROW_LEN  = 8         # 矢印の長さ (px)
ARROW_W    = 2.3       # 矢印の半幅 (px) → 開き角 ≈ 30°

# 寸法線の間隔（実寸 mm 単位、スケールで px に変換）
DIM_GAP1_MM = 10.0     # 外形線から第1寸法線までの距離
DIM_GAP2_MM = 7.0      # 寸法線同士の距離
EXT_GAP_MM  = 2.0      # 寸法補助線と外形線の隙間
EXT_OVER_MM = 3.0      # 寸法補助線が寸法線を超える長さ

LABEL_SIZE = 11
VIEW_TITLE = 14
FEAT_LABEL_SIZE = 9
CL_MARGIN  = 4   # 中心線の線端余白 (px)


# ── SVGBuilder ────────────────────────────────────────────────────────────────

class SVGBuilder:
    """SVG 要素を積み上げて最後に文字列化する軽量ビルダー"""

    def __init__(self, width, height, scale=1.0):
        self.w = width
        self.h = height
        self._sc = scale   # mm→px 変換倍率
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
        """JIS B 0001 準拠の塗り矢印（開き角 30°）"""
        a = math.radians(angle_deg)
        tip   = (x, y)
        left  = (x - ARROW_LEN * math.cos(a) + ARROW_W * math.sin(a),
                 y - ARROW_LEN * math.sin(a) - ARROW_W * math.cos(a))
        right = (x - ARROW_LEN * math.cos(a) - ARROW_W * math.sin(a),
                 y - ARROW_LEN * math.sin(a) + ARROW_W * math.cos(a))
        self.polygon([tip, left, right], fill=COLOR_DIM, stroke=COLOR_DIM, sw=0)

    # ── JIS 準拠 寸法線メソッド ──

    def dim_h(self, x1, y_base, x2, label, above=True, level=1):
        """水平寸法線 (JIS B 0001 準拠)

        寸法値は寸法線の上に配置（白地矩形は不使用）。
        level: 段重ね（1=最内側, 2=その外側...）
        """
        sc = max(self._sc, 0.5)  # 最低限のスケール
        sign = -1 if above else 1
        gap1 = DIM_GAP1_MM * sc
        gap2 = DIM_GAP2_MM * sc
        ext_gap = EXT_GAP_MM * sc
        ext_over = EXT_OVER_MM * sc

        y_dim = y_base + sign * (gap1 + gap2 * (level - 1))

        # 寸法補助線（外形線と隙間を空けて延ばす）
        for xp in (x1, x2):
            y0 = y_base + sign * ext_gap       # 外形線との隙間
            y1 = y_dim + sign * ext_over        # 寸法線の少し先まで延ばす
            self.line(xp, min(y0, y1), xp, max(y0, y1),
                      stroke=COLOR_DIM, sw=0.5)

        # 寸法線
        self.line(x1, y_dim, x2, y_dim, stroke=COLOR_DIM, sw=0.7)

        # 矢印（スペースが狭い場合は外向き）
        span = abs(x2 - x1)
        if span > ARROW_LEN * 4:
            self._arrow(x1, y_dim, 180)
            self._arrow(x2, y_dim, 0)
        else:
            # 外向き矢印
            self._arrow(x1, y_dim, 0)
            self._arrow(x2, y_dim, 180)

        # 寸法値: 寸法線の上に配置（above=True の場合はさらに上、above=False ならさらに下）
        mx = (x1 + x2) / 2
        text_offset = 6  # 寸法線から数値までのオフセット (px)
        ty = y_dim - text_offset if above else y_dim + text_offset
        self.text(mx, ty, label, size=LABEL_SIZE, color=COLOR_DIM)

    def dim_v(self, y1, x_base, y2, label, left_side=True, level=1):
        """垂直寸法線 (JIS B 0001 準拠)

        寸法値は寸法線の左に配置（90° 回転、下→上方向に読む）。
        level: 段重ね（1=最内側, 2=その外側...）
        """
        sc = max(self._sc, 0.5)
        sign = -1 if left_side else 1
        gap1 = DIM_GAP1_MM * sc
        gap2 = DIM_GAP2_MM * sc
        ext_gap = EXT_GAP_MM * sc
        ext_over = EXT_OVER_MM * sc

        x_dim = x_base + sign * (gap1 + gap2 * (level - 1))

        # 寸法補助線
        for yp in (y1, y2):
            x0 = x_base + sign * ext_gap
            x1_ = x_dim + sign * ext_over
            self.line(min(x0, x1_), yp, max(x0, x1_), yp,
                      stroke=COLOR_DIM, sw=0.5)

        # 寸法線
        self.line(x_dim, y1, x_dim, y2, stroke=COLOR_DIM, sw=0.7)

        # 矢印（スペースが狭い場合は外向き）
        span = abs(y2 - y1)
        if span > ARROW_LEN * 4:
            self._arrow(x_dim, y1, 270)
            self._arrow(x_dim, y2, 90)
        else:
            self._arrow(x_dim, y1, 90)
            self._arrow(x_dim, y2, 270)

        # 寸法値: 寸法線の左（left_side の場合はさらに左）に 90° 回転配置
        my = (y1 + y2) / 2
        text_offset = 6
        tx = x_dim - text_offset if left_side else x_dim + text_offset
        self.text_rotated(tx, my, label, -90, size=LABEL_SIZE, color=COLOR_DIM)

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
            self.center_cross(cx, cy, max(r + 4, 8))
        else:
            self.circle(cx, cy, r, stroke=COLOR_FEATURE, sw=1.2)
            self.center_cross(cx, cy, max(r + 4, 8))

    def feature_side_h(self, cy, r, x_start, x_end, hidden=True):
        """穴を側面から見た投影（穴軸が水平方向）:
        2本の水平平行破線（穴径間隔）＋ 水平中心線（一点鎖線）
        """
        stroke = COLOR_FEATURE_HIDDEN if hidden else COLOR_FEATURE
        dash   = "4,2"
        self.line(x_start, cy - r, x_end, cy - r, stroke=stroke, sw=0.8, dash=dash)
        self.line(x_start, cy + r, x_end, cy + r, stroke=stroke, sw=0.8, dash=dash)
        self.line(min(x_start, x_end) - CL_MARGIN, cy,
                  max(x_start, x_end) + CL_MARGIN, cy,
                  stroke=COLOR_CENTERLINE, sw=0.5, dash="8,3,2,3")

    def feature_side_v(self, cx, r, y_start, y_end, hidden=True):
        """穴を側面から見た投影（穴軸が垂直方向）:
        2本の垂直平行破線（穴径間隔）＋ 垂直中心線（一点鎖線）
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

def _make_label_placer(svg):
    """ラベル重複を防止するクロージャを返す"""
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
            svg.line(x, y, lx - 10 if ox_off > 0 else lx + 10, ly,
                     stroke=COLOR_HIDDEN, sw=0.5)
        svg.feature_label(lx, ly, label, offset_x=0, offset_y=0)
        drawn_labels.append((lx, ly))

    return place_label


# ── 穴位置寸法の収集と描画 ────────────────────────────────────────────────────

def _draw_hole_position_dims(svg, d, features_in_view, view_face, ox, oy, sc,
                              view_w_mm, view_h_mm, above_h=True, left_v=True):
    """フィーチャーの基準面からの位置寸法を描画する。

    features_in_view: [(face, fx_mm, fy_mm, dia, label), ...] — このビューで円として見える穴
    view_w_mm, view_h_mm: ビューの実寸幅・高さ (mm)
    """
    if not features_in_view:
        return

    # 重複座標を除去して、ユニークな位置を収集
    x_positions = {}  # mm_x -> label
    y_positions = {}  # mm_y -> label

    for face, fx, fy, dia, label in features_in_view:
        # X 方向: 左端面からの距離（端点付近でない場合のみ）
        if 3 < fx < view_w_mm - 3:
            x_key = round(fx, 1)
            if x_key not in x_positions:
                x_positions[x_key] = label
        # Y 方向: 上端面からの距離
        if 3 < fy < view_h_mm - 3:
            y_key = round(fy, 1)
            if y_key not in y_positions:
                y_positions[y_key] = label

    # X 方向の穴位置寸法（左端面を基準）
    dim_level_h = 2  # level 1 は外形寸法に使うことが多い
    for x_mm in sorted(x_positions.keys()):
        px = ox + x_mm * sc
        svg.dim_h(ox, oy if above_h else oy + view_h_mm * sc, px,
                  f"{x_mm:.1f}", above=above_h, level=dim_level_h)
        dim_level_h += 1
        if dim_level_h > 4:  # 最大4段まで
            break

    # Y 方向の穴位置寸法（上端面を基準）
    dim_level_v = 2
    for y_mm in sorted(y_positions.keys()):
        py = oy + y_mm * sc
        svg.dim_v(oy, ox if left_v else ox + view_w_mm * sc, py,
                  f"{y_mm:.1f}", left_side=left_v, level=dim_level_v)
        dim_level_v += 1
        if dim_level_v > 4:
            break


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
    wp = d["wall"]   * sc
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

    place_label = _make_label_placer(svg)
    circle_features = []  # 円として描画されるフィーチャー（位置寸法用）

    for face, fx, fy, dia, label in d["features"]:
        r = (dia / 2) * sc

        if face == "front":
            cx, cy = ox + fx * sc, oy + fy * sc
            svg.feature_circle(cx, cy, r, hidden=False)
            place_label(cx, cy, label, max(r+6, 12), -max(r+4, 10))
            circle_features.append((face, fx, fy, dia, label))

        elif face == "back":
            cx, cy = ox + fx * sc, oy + fy * sc
            svg.feature_circle(cx, cy, r, hidden=True)
            place_label(cx, cy, label, max(r+6, 12), -max(r+4, 10))
            circle_features.append((face, fx, fy, dia, label))

        elif face == "bottom":
            cx = ox + fx * sc
            svg.feature_side_v(cx, r, oy + H - wp, oy + H, hidden=True)
            place_label(cx, oy + H - wp, label, max(r+6, 12), -6)

        elif face == "top":
            cx = ox + fx * sc
            svg.feature_side_v(cx, r, oy, oy + wp, hidden=True)

    # 寸法線 — 高さ (左側, level=1)
    svg.dim_v(oy, ox, oy + H, f"{d['height']:.0f}", left_side=True, level=1)

    # 穴位置寸法
    _draw_hole_position_dims(svg, d, circle_features, "front",
                              ox, oy, sc, d["width"], d["height"],
                              above_h=True, left_v=True)

    # ビュー名（ビューの下に配置）
    svg.view_title(ox + W/2, oy + H + 25, "正面図 FRONT VIEW")


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
        svg.rect(ox + Dp - wp, oy - fl["t"]*sc, wp, H + (fl["t"]+fl["b"])*sc,
                 fill=COLOR_FACE_SIDE, stroke=COLOR_OUTLINE, sw=1.5, rx=0)

    svg.rect(ox, oy, Dp, H, fill=COLOR_FACE_SIDE, stroke=COLOR_OUTLINE, sw=2.0, rx=fr)
    svg.rect(ox + wp, oy + wp, Dp - 2*wp, H - 2*wp,
             fill="none", stroke=COLOR_HIDDEN, sw=0.9, dash="6,3",
             rx=max(0.0, fr - wp))

    place_label = _make_label_placer(svg)

    for face, fx, fy, dia, label in d["features"]:
        r = (dia / 2) * sc

        if face == "front":
            cy = oy + fy * sc
            svg.feature_side_h(cy, r, ox, ox + wp, hidden=True)
            place_label(ox + wp + 4, cy, label, 12, -max(r+3, 8))

        elif face == "back":
            cy = oy + fy * sc
            svg.feature_side_h(cy, r, ox + Dp - wp, ox + Dp, hidden=True)
            place_label(ox + Dp - wp - 4, cy, label, -12, -max(r+3, 8))

        elif face == "bottom":
            cu = ox + fy * sc
            svg.feature_side_v(cu, r, oy + H - wp, oy + H, hidden=True)
            place_label(cu, oy + H - wp, label, max(r+6, 10), -6)

        elif face == "side":
            cx, cy = ox + fx * sc, oy + fy * sc
            svg.feature_circle(cx, cy, r, hidden=False)

    # 寸法線
    svg.dim_h(ox, oy, ox + Dp, f"{d['depth']:.0f}", above=True, level=1)
    svg.dim_v(oy, ox + Dp, oy + H, f"{d['height']:.0f}", left_side=False, level=1)
    svg.view_title(ox + Dp/2, oy + H + 25, "右側面図 RIGHT SIDE VIEW")


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
        svg.rect(ox - fl["l"]*sc, oy + Dp - wp, W + (fl["l"]+fl["r"])*sc, wp,
                 fill=COLOR_FACE_SIDE, stroke=COLOR_OUTLINE, sw=1.5, rx=0)

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

    place_label = _make_label_placer(svg)
    circle_features = []

    for face, fx, fy, dia, label in d["features"]:
        r = (dia / 2) * sc

        if face == "bottom":
            cx, cy = ox + fx * sc, oy + fy * sc
            svg.feature_circle(cx, cy, r, hidden=False)
            place_label(cx, cy, label, max(r+6, 12), -max(r+4, 10))
            circle_features.append((face, fx, fy, dia, label))

        elif face == "top":
            cx, cy = ox + fx * sc, oy + fy * sc
            svg.feature_circle(cx, cy, r, hidden=True)

        elif face == "front":
            cu = ox + fx * sc
            svg.feature_side_v(cu, r, oy, oy + wp, hidden=True)
            place_label(cu, oy + wp, label, max(r+6, 12), 10)

        elif face == "back":
            cu = ox + fx * sc
            svg.feature_side_v(cu, r, oy + Dp - wp, oy + Dp, hidden=True)
            place_label(cu, oy + Dp - wp, label, max(r+6, 12), -6)

    # 底面穴グループ間隔寸法
    bottom_feats = [(fx, fy) for f, fx, fy, dia, lbl in d["features"] if f == "bottom"]
    if len(bottom_feats) >= 2:
        xs = sorted(set(round(fx, 2) for fx, fy in bottom_feats))
        if len(xs) >= 2:
            svg.dim_h(ox + xs[0]*sc, oy + Dp + 5,
                      ox + xs[-1]*sc, f"{xs[-1]-xs[0]:.0f}", above=False, level=2)

    # 背面取付穴ピッチ寸法
    back_feats = [(fx, fy) for f, fx, fy, dia, lbl in d["features"] if f == "back"]
    if len(back_feats) >= 2:
        bxs = sorted(set(round(fx, 2) for fx, fy in back_feats))
        if len(bxs) >= 2:
            svg.dim_h(ox + bxs[0]*sc, oy - 5,
                      ox + bxs[-1]*sc, f"P.C.D {bxs[-1]-bxs[0]:.0f}", above=True, level=2)

    # 外形寸法
    svg.dim_h(ox, oy + Dp, ox + W, f"{d['width']:.0f}", above=False, level=1)
    svg.dim_v(oy, ox + W, oy + Dp, f"{d['depth']:.0f}", left_side=False, level=1)

    # 穴位置寸法（底面ビューの円として見える穴）
    _draw_hole_position_dims(svg, d, circle_features, "bottom",
                              ox, oy, sc, d["width"], d["depth"],
                              above_h=True, left_v=True)

    # ビュー名（ビューの上に配置 — JIS ではビュー名は上が標準）
    svg.view_title(ox + W/2, oy - 30, "底面図 BOTTOM VIEW")


# ── 投影法記号 ────────────────────────────────────────────────────────────────

def draw_projection_symbol(svg, cx, cy, size=20):
    """JIS B 0001 第三角法の投影法記号を描画

    截頭円錐の正面図（台形）と右側面図（同心円2つ）で構成。
    cx, cy: シンボルの中心座標
    size: シンボルの基本サイズ
    """
    s = size
    gap = s * 0.6  # 正面図と側面図の間隔

    # 左側: 正面図（台形 = 截頭円錐を正面から見たもの）
    trap_cx = cx - gap
    # 台形: 上辺が短く下辺が長い
    top_w = s * 0.4
    bot_w = s * 0.8
    h = s * 0.7
    pts = [
        (trap_cx - top_w/2, cy - h/2),
        (trap_cx + top_w/2, cy - h/2),
        (trap_cx + bot_w/2, cy + h/2),
        (trap_cx - bot_w/2, cy + h/2),
    ]
    svg.polygon(pts, fill="none", stroke=COLOR_OUTLINE, sw=1.2)
    # 中心線（水平）
    svg.line(trap_cx - bot_w/2 - 3, cy, trap_cx + bot_w/2 + 3, cy,
             stroke=COLOR_CENTERLINE, sw=0.5, dash="4,2,1,2")

    # 右側: 側面図（同心円2つ = 截頭円錐を横から見たもの）
    circle_cx = cx + gap
    r_outer = s * 0.4
    r_inner = s * 0.2
    svg.circle(circle_cx, cy, r_outer, stroke=COLOR_OUTLINE, sw=1.2)
    svg.circle(circle_cx, cy, r_inner, stroke=COLOR_OUTLINE, sw=1.2)
    # 中心線クロス
    svg.line(circle_cx - r_outer - 3, cy, circle_cx + r_outer + 3, cy,
             stroke=COLOR_CENTERLINE, sw=0.5, dash="4,2,1,2")
    svg.line(circle_cx, cy - r_outer - 3, circle_cx, cy + r_outer + 3,
             stroke=COLOR_CENTERLINE, sw=0.5, dash="4,2,1,2")


# ── タイトルブロック ──────────────────────────────────────────────────────────

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
             f"作成日: {today}  |  text-to-cad skill v5",
             size=11, color=COLOR_SUBTITLE, anchor="end")


# ── メイン ────────────────────────────────────────────────────────────────────

def generate_svg(req_data, param_data, output_path):
    d = extract_dims(req_data, param_data)
    W, D, H = d["width"], d["depth"], d["height"]

    # ── 寸法マージンの推定 ──────────────────────────────────────────────
    # 各ビュー外側に寸法線が何段分必要かを事前推定する。
    # 穴位置寸法は最大 level=4 まで、外形寸法が level=1。
    # 正面図: 左に dim_v (height + 穴位置), 上に dim_h (穴位置)
    # 底面図: 下に dim_h (width), 右に dim_v (depth), 上に穴ピッチ
    # 側面図: 上に dim_h (depth), 右に dim_v (height)

    front_circle_feats = [f for f in d["features"] if f[0] in ("front", "back")]
    bottom_circle_feats = [f for f in d["features"] if f[0] == "bottom"]

    # 最大段数を推定
    front_v_levels = 1 + min(len(set(round(fy, 1) for _, _, fy, _, _ in front_circle_feats)), 3)
    front_h_levels = 1 + min(len(set(round(fx, 1) for _, fx, _, _, _ in front_circle_feats)), 3)
    bottom_h_levels = 1 + min(len(set(round(fx, 1) for _, fx, _, _, _ in bottom_circle_feats)), 3)
    bottom_v_levels = 1 + min(len(set(round(fy, 1) for _, _, fy, _, _ in bottom_circle_feats)), 3)

    # ── スケール計算（寸法マージンを含む） ──────────────────────────────
    da_x, da_y = PADDING, PADDING
    da_w = CANVAS_W - PADDING * 2
    da_h = CANVAS_H - PADDING * 2 - TITLE_H

    # 各方向の寸法マージン（mm単位 → スケール後にpxになる）
    # margin_mm = gap1 + gap2 * (max_level - 1) + テキスト余白
    def dim_margin_mm(max_level):
        return DIM_GAP1_MM + DIM_GAP2_MM * (max_level - 1) + 8  # 8mm = テキスト余白

    # 左マージン: 正面図の左に垂直寸法
    margin_left_mm  = dim_margin_mm(front_v_levels)
    # 上マージン: 底面図の上に水平寸法 + ビュー名
    margin_top_mm   = dim_margin_mm(max(bottom_h_levels, 2)) + 12  # 12mm for view title
    # 右マージン: 側面図の右に垂直寸法
    margin_right_mm = dim_margin_mm(2)
    # 下マージン: 正面図の下にビュー名
    margin_bot_mm   = 12  # ビュー名のみ
    # VIEW_GAP は寸法が両側から重なるため、両ビューの最大段数を考慮
    view_gap_mm     = dim_margin_mm(2) + dim_margin_mm(1) + 5  # 左右のビュー間

    # 利用可能な描画空間をmm単位で逆算してスケールを決定
    # X方向: margin_left + W + view_gap + D + margin_right
    avail_x_mm = W + D + view_gap_mm + margin_left_mm + margin_right_mm
    # Y方向: margin_top + D + view_gap + H + margin_bot
    avail_y_mm = D + H + view_gap_mm + margin_top_mm + margin_bot_mm

    sc_x = da_w / avail_x_mm
    sc_y = da_h / avail_y_mm
    sc = min(sc_x, sc_y, 5.0)

    svg = SVGBuilder(CANVAS_W, CANVAS_H, scale=sc)
    svg.rect(0, 0, CANVAS_W, CANVAS_H, fill=COLOR_BG, stroke="none", sw=0)

    # 描画領域の枠
    svg.rect(da_x, da_y, da_w, da_h, fill="#f9f9fd", stroke="#ccccdd", sw=1.0, rx=4)

    # ── ビュー配置（第三角法、寸法マージン考慮） ──────────────────────
    # 正面図の左上角を基準点として計算
    margin_left_px  = margin_left_mm * sc
    margin_top_px   = margin_top_mm * sc
    view_gap_px     = view_gap_mm * sc

    # 図面全体を描画領域内でセンタリング
    total_w_px = margin_left_px + W * sc + view_gap_px + D * sc + margin_right_mm * sc
    total_h_px = margin_top_px + D * sc + view_gap_px + H * sc + margin_bot_mm * sc
    offset_x = da_x + (da_w - total_w_px) / 2
    offset_y = da_y + (da_h - total_h_px) / 2

    # 正面図 (W × H)
    front_ox = offset_x + margin_left_px
    front_oy = offset_y + margin_top_px + D * sc + view_gap_px

    # 底面図 (W × D) — 正面図の真上
    plan_ox  = front_ox
    plan_oy  = offset_y + margin_top_px

    # 右側面図 (D × H) — 正面図の右
    side_ox  = front_ox + W * sc + view_gap_px
    side_oy  = front_oy

    # ── 描画 ──
    draw_bottom(svg, d, plan_ox, plan_oy, sc)
    draw_front(svg, d, front_ox, front_oy, sc)
    draw_side(svg, d, side_ox, side_oy, sc)

    # 投影法記号（タイトルブロックの左上付近）
    proj_sym_x = CANVAS_W - PADDING - 100
    proj_sym_y = CANVAS_H - TITLE_H - 30
    draw_projection_symbol(svg, proj_sym_x, proj_sym_y, size=18)
    svg.text(proj_sym_x, proj_sym_y + 18, "第三角法",
             size=9, color="#888888", anchor="middle")

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
