#!/usr/bin/env python3
"""
Stage 3.5b: 視覚的契約 (Visual Contract) SVG 生成スクリプト

feature_mapping.json の geometry_tree から簡易3面図を生成し、
Stage 2 のSVGやユーザースケッチと照合するためのプレビューを出力する。

Python 標準ライブラリのみ（CadQuery不要）。

使い方:
    python scripts/stage3_5_preview_svg.py \
        --fmap feature_mapping.json \
        --out preview/geometry_preview.svg
"""

import argparse
import json
import sys
import os

# ── 描画定数 ──────────────────────────────────────────────────────────────────

CANVAS_W = 1200
CANVAS_H = 800
PADDING = 40
VIEW_GAP = 50

COLOR_OUTLINE = "#1a1a2e"
COLOR_FILL = "#e8e8f0"
COLOR_EXTENSION = "#c8d8e8"   # 張り出し部（耳等）の塗りつぶし
COLOR_OPENING = "#ffffff"     # 開口面
COLOR_DIM = "#3355aa"
COLOR_LABEL = "#444444"
COLOR_HOLE = "#ff6666"
COLOR_GRID = "#dddddd"

FONT_FAMILY = "Arial, Helvetica, sans-serif"


# ── SVG ビルダー ──────────────────────────────────────────────────────────────

class MiniSVG:
    """最小限のSVG生成ヘルパー"""

    def __init__(self, width, height):
        self.w = width
        self.h = height
        self._elems = []

    def add(self, s):
        self._elems.append(s)

    def rect(self, x, y, w, h, fill=COLOR_FILL, stroke=COLOR_OUTLINE, sw=1.5,
             dash=None, opacity=1.0):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        o = f' opacity="{opacity}"' if opacity < 1.0 else ""
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                 f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}{o}/>')

    def circle(self, cx, cy, r, fill="none", stroke=COLOR_HOLE, sw=1.0):
        self.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
                 f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def line(self, x1, y1, x2, y2, stroke=COLOR_OUTLINE, sw=1.0, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                 f'stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, content, size=11, color=COLOR_LABEL, anchor="middle",
             bold=False):
        fw = ' font-weight="bold"' if bold else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
                 f'font-size="{size}" font-family="{FONT_FAMILY}" fill="{color}"{fw}>'
                 f'{content}</text>')

    def dim_h(self, x1, x2, y, label):
        """水平寸法線"""
        self.line(x1, y, x2, y, stroke=COLOR_DIM, sw=0.8)
        self.line(x1, y - 4, x1, y + 4, stroke=COLOR_DIM, sw=0.8)
        self.line(x2, y - 4, x2, y + 4, stroke=COLOR_DIM, sw=0.8)
        self.text((x1 + x2) / 2, y - 6, label, size=10, color=COLOR_DIM)

    def dim_v(self, y1, y2, x, label):
        """垂直寸法線"""
        self.line(x, y1, x, y2, stroke=COLOR_DIM, sw=0.8)
        self.line(x - 4, y1, x + 4, y1, stroke=COLOR_DIM, sw=0.8)
        self.line(x - 4, y2, x + 4, y2, stroke=COLOR_DIM, sw=0.8)
        self.text(x - 12, (y1 + y2) / 2 + 4, label, size=10, color=COLOR_DIM,
                  anchor="end")

    def build(self):
        header = (f'<svg xmlns="http://www.w3.org/2000/svg" '
                  f'width="{self.w}" height="{self.h}" '
                  f'viewBox="0 0 {self.w} {self.h}">')
        bg = (f'<rect width="{self.w}" height="{self.h}" fill="white"/>')
        return "\n".join([header, bg] + self._elems + ["</svg>"])


# ── geometry_tree パーサー ────────────────────────────────────────────────────

def collect_primitives(node, parent_transform=None):
    """
    geometry_tree ノードを再帰的に辿り、プリミティブのリストを返す。
    各プリミティブは {type, params, transform, semantic_tag} の辞書。
    """
    if parent_transform is None:
        parent_transform = [0, 0, 0]

    primitives = []

    if "primitive" in node:
        # リーフノード
        t = node.get("transform", {}).get("translate", [0, 0, 0])
        combined_t = [parent_transform[i] + t[i] for i in range(3)]
        primitives.append({
            "type": node["primitive"],
            "params": node["params"],
            "translate": combined_t,
            "semantic_tag": node.get("semantic_tag", "")
        })
    elif "operation" in node:
        # Boolean ノード
        for child in node.get("children", []):
            primitives.extend(collect_primitives(child, parent_transform))

    return primitives


def compute_bounding_box(primitives):
    """全プリミティブの結合バウンディングボックスを計算"""
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")

    for prim in primitives:
        p = prim["params"]
        t = prim["translate"]

        if prim["type"] == "box":
            w, d, h = p["W"], p["D"], p["H"]
            min_x = min(min_x, t[0] - w / 2)
            max_x = max(max_x, t[0] + w / 2)
            min_y = min(min_y, t[1] - d / 2)
            max_y = max(max_y, t[1] + d / 2)
            min_z = min(min_z, t[2] - h / 2)
            max_z = max(max_z, t[2] + h / 2)
        elif prim["type"] == "cylinder":
            r = p["radius"]
            h = p["height"]
            min_x = min(min_x, t[0] - r)
            max_x = max(max_x, t[0] + r)
            min_y = min(min_y, t[1] - r)
            max_y = max(max_y, t[1] + r)
            min_z = min(min_z, t[2] - h / 2)
            max_z = max(max_z, t[2] + h / 2)

    return (min_x, min_y, min_z, max_x, max_y, max_z)


# ── 3面図描画 ─────────────────────────────────────────────────────────────────

def draw_front_view(svg, primitives, finishing, features, ox, oy, scale, bb):
    """正面図 (X-Z平面, -Y方向から見る)"""
    svg.text(ox, oy - 15, "正面図 (Front)", size=13, bold=True)

    for prim in primitives:
        p = prim["params"]
        t = prim["translate"]
        tag = prim["semantic_tag"]

        if prim["type"] == "box":
            w, h = p["W"], p["H"]
            x = ox + (t[0] - w / 2) * scale
            y = oy + (-t[2] - h / 2) * scale  # Z↑ → SVG Y↓
            fill = COLOR_EXTENSION if "main" not in tag else COLOR_FILL
            svg.rect(x, y, w * scale, h * scale, fill=fill)
        elif prim["type"] == "cylinder":
            r = p["radius"]
            cx = ox + t[0] * scale
            cy = oy - t[2] * scale
            svg.circle(cx, cy, r * scale, fill=COLOR_FILL, stroke=COLOR_OUTLINE)

    # 開口面の表示
    shell_info = finishing.get("shell", {})
    open_face = shell_info.get("open_face", "")
    if open_face == "-Y":
        bb_w = (bb[3] - bb[0])
        bb_h = (bb[5] - bb[2])
        wall = shell_info.get("thickness", 3)
        inner_x = ox + (bb[0] + wall) * scale
        inner_y = oy + (-bb[5] + wall) * scale
        inner_w = (bb_w - 2 * wall) * scale
        inner_h = (bb_h - 2 * wall) * scale
        svg.rect(inner_x, inner_y, inner_w, inner_h, fill=COLOR_OPENING,
                 stroke=COLOR_OUTLINE, sw=0.8, dash="4,2")

    # フィーチャー（穴をプロット）
    for feat in features:
        face = feat.get("face", "")
        if face == "-Y" and feat.get("type") in ("through_hole", "blind_hole", "cbore_hole"):
            pos = feat.get("position_on_face", {})
            d = feat.get("diameter", 3)
            cx = ox + pos.get("x", 0) * scale
            cy = oy - pos.get("y", 0) * scale
            svg.circle(cx, cy, d / 2 * scale, stroke=COLOR_HOLE, sw=1.5)

    # 寸法線
    bb_w = bb[3] - bb[0]
    bb_h = bb[5] - bb[2]
    svg.dim_h(ox + bb[0] * scale, ox + bb[3] * scale, oy + (-bb[2]) * scale + 20,
              f"W{bb_w:.0f}")
    svg.dim_v(oy + (-bb[5]) * scale, oy + (-bb[2]) * scale, ox + bb[0] * scale - 15,
              f"H{bb_h:.0f}")


def draw_side_view(svg, primitives, finishing, features, ox, oy, scale, bb):
    """側面図 (Y-Z平面, +X方向から見る)"""
    svg.text(ox, oy - 15, "側面図 (Side)", size=13, bold=True)

    for prim in primitives:
        p = prim["params"]
        t = prim["translate"]
        tag = prim["semantic_tag"]

        if prim["type"] == "box":
            d, h = p["D"], p["H"]
            x = ox + (t[1] - d / 2) * scale
            y = oy + (-t[2] - h / 2) * scale
            fill = COLOR_EXTENSION if "main" not in tag else COLOR_FILL
            svg.rect(x, y, d * scale, h * scale, fill=fill)

    # 寸法線
    bb_d = bb[4] - bb[1]
    bb_h = bb[5] - bb[2]
    svg.dim_h(ox + bb[1] * scale, ox + bb[4] * scale, oy + (-bb[2]) * scale + 20,
              f"D{bb_d:.0f}")


def draw_top_view(svg, primitives, finishing, features, ox, oy, scale, bb):
    """上面図 (X-Y平面, +Z方向から見下ろす)"""
    svg.text(ox, oy - 15, "上面図 (Top)", size=13, bold=True)

    for prim in primitives:
        p = prim["params"]
        t = prim["translate"]
        tag = prim["semantic_tag"]

        if prim["type"] == "box":
            w, d = p["W"], p["D"]
            x = ox + (t[0] - w / 2) * scale
            y = oy + (t[1] - d / 2) * scale  # Y+ → SVG Y↓ (上から見て奥が下)
            fill = COLOR_EXTENSION if "main" not in tag else COLOR_FILL
            svg.rect(x, y, w * scale, d * scale, fill=fill)

    # フィーチャー（底面穴を描画）
    for feat in features:
        face = feat.get("face", "")
        if face in ("-Z", "+Z") and feat.get("type") in ("through_hole", "blind_hole"):
            pos = feat.get("position_on_face", {})
            d = feat.get("diameter", 3)
            cx = ox + pos.get("x", 0) * scale
            cy = oy + pos.get("y", 0) * scale
            svg.circle(cx, cy, d / 2 * scale, stroke=COLOR_HOLE, sw=1.5)


# ── メイン ────────────────────────────────────────────────────────────────────

def generate_preview(fmap_path, output_path):
    with open(fmap_path, encoding="utf-8") as f:
        fmap = json.load(f)

    svg = MiniSVG(CANVAS_W, CANVAS_H)

    # タイトル
    svg.text(CANVAS_W / 2, 30, "Visual Contract — Geometry Preview", size=16, bold=True)

    parts = fmap.get("parts", [])

    for i, part in enumerate(parts):
        part_id = part.get("part_id", f"P{i+1:03d}")
        name = part.get("name", "")
        gt = part.get("geometry_tree", part.get("base_shape", {}))
        finishing = part.get("finishing", {})
        features = part.get("features", [])

        # 旧スキーマ互換: base_shape → 仮の geometry_tree に変換
        if "base_shape" in part and "geometry_tree" not in part:
            bs = part["base_shape"]
            gt = {
                "primitive": "box",
                "params": bs.get("dimensions", {"W": 50, "D": 30, "H": 40}),
                "semantic_tag": "main_body"
            }
            finishing = {
                "fillet": {"edge_selector": "|Z",
                           "radius": bs.get("fillet_radius", 2)},
            }
            if bs.get("wall_thickness"):
                finishing["shell"] = {
                    "open_face": bs.get("open_face", "+Z"),
                    "thickness": bs.get("wall_thickness", 3)
                }

        primitives = collect_primitives(gt)
        if not primitives:
            print(f"⚠️ WARN: {part_id} {name} — geometry_tree にプリミティブが見つかりません",
                  file=sys.stderr)
            continue

        bb = compute_bounding_box(primitives)
        bb_w = bb[3] - bb[0]
        bb_d = bb[4] - bb[1]
        bb_h = bb[5] - bb[2]

        # スケール計算
        view_area_w = (CANVAS_W - PADDING * 3 - VIEW_GAP * 2) / 3
        view_area_h = CANVAS_H - PADDING * 2 - 80  # タイトル分

        scale_front = min(view_area_w / max(bb_w, 1), view_area_h / max(bb_h, 1)) * 0.75
        scale_side = min(view_area_w / max(bb_d, 1), view_area_h / max(bb_h, 1)) * 0.75
        scale_top = min(view_area_w / max(bb_w, 1), view_area_h / max(bb_d, 1)) * 0.75
        scale = min(scale_front, scale_side, scale_top)

        # 部品ラベル
        base_y = 60 + i * (CANVAS_H - 80)
        svg.text(PADDING, base_y, f"■ {part_id} {name}", size=13, bold=True,
                 anchor="start")

        # 各ビューの原点（ビュー中心）
        front_ox = PADDING + view_area_w / 2
        front_oy = base_y + 30 + view_area_h / 2

        side_ox = PADDING + view_area_w + VIEW_GAP + view_area_w / 2
        side_oy = front_oy

        top_ox = PADDING + (view_area_w + VIEW_GAP) * 2 + view_area_w / 2
        top_oy = front_oy

        draw_front_view(svg, primitives, finishing, features, front_ox, front_oy,
                        scale, bb)
        draw_side_view(svg, primitives, finishing, features, side_ox, side_oy,
                       scale, bb)
        draw_top_view(svg, primitives, finishing, features, top_ox, top_oy,
                      scale, bb)

    # 出力
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
                exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg.build())

    print(f"✅ 視覚的契約SVGを生成しました: {output_path}")
    print(f"   ブラウザで開いてスケッチと照合してください。")


def main():
    parser = argparse.ArgumentParser(
        description="Stage 3.5b: geometry_tree から視覚的契約SVGを生成")
    parser.add_argument("--fmap", required=True, help="feature_mapping.json のパス")
    parser.add_argument("--out", default="preview/geometry_preview.svg",
                        help="出力SVGパス")
    args = parser.parse_args()

    if not os.path.exists(args.fmap):
        print(f"❌ エラー: {args.fmap} が見つかりません", file=sys.stderr)
        sys.exit(1)

    generate_preview(args.fmap, args.out)


if __name__ == "__main__":
    main()
