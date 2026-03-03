#!/usr/bin/env python3
"""
Stage 4b: パラメトリック STEP 生成テンプレート

このファイルは各プロジェクトごとに Claude がカスタマイズして生成する。
parameters.json から全寸法を読み込み、CadQuery でモデリングする。

使用法:
  python generate_step.py [--params parameters.json] [--output ./step/] [--validate] [--preview]
"""
import json
import sys
import os
import argparse

try:
    import cadquery as cq
except ImportError:
    print("❌ CadQuery がインストールされていません:")
    print("   pip install cadquery --break-system-packages")
    sys.exit(1)


# ── パラメータ読み込み ──

def load_params(path: str = "parameters.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def p(params: dict, category: str, key: str):
    """パラメータ値を取得するヘルパー"""
    return params[category][key]["value"]


# ── バリデーション ──

def validate_step(shape, params: dict, part_name: str = "") -> dict:
    """生成された STEP の自動バリデーション"""
    results = {"part_name": part_name}

    try:
        # OpenCASCADE の BRepCheck
        from OCP.BRepCheck import BRepCheck_Analyzer
        analyzer = BRepCheck_Analyzer(shape.val().wrapped)
        results["solid_valid"] = analyzer.IsValid()
    except Exception as e:
        results["solid_valid"] = f"検証不可: {e}"

    # バウンディングボックス
    try:
        bb = shape.val().BoundingBox()
        results["bb_width"] = round(bb.xlen, 2)
        results["bb_depth"] = round(bb.ylen, 2)
        results["bb_height"] = round(bb.zlen, 2)

        # outer_envelope との比較（カテゴリがある場合）
        if "outer_envelope" in params:
            exp_w = p(params, "outer_envelope", "width")
            exp_d = p(params, "outer_envelope", "depth")
            exp_h = p(params, "outer_envelope", "height")
            tol = 2.0  # mm 許容誤差
            results["bb_width_ok"] = abs(bb.xlen - exp_w) < tol
            results["bb_depth_ok"] = abs(bb.ylen - exp_d) < tol
            results["bb_height_ok"] = abs(bb.zlen - exp_h) < tol
    except Exception as e:
        results["bb_error"] = str(e)

    # 体積チェック
    try:
        vol = shape.val().Volume()
        results["volume_mm3"] = round(vol, 1)
        results["volume_ok"] = vol > 0
    except Exception as e:
        results["volume_error"] = str(e)

    return results


def print_validation(results: dict):
    """バリデーション結果を表示"""
    name = results.get("part_name", "")
    print(f"\n━━━ STEP バリデーション: {name} ━━━")
    print(f"  ソリッド有効性:     {'✅' if results.get('solid_valid') == True else '❌'} {results.get('solid_valid', '?')}")

    if "bb_width" in results:
        for dim, label in [("width", "W"), ("depth", "D"), ("height", "H")]:
            val = results.get(f"bb_{dim}", "?")
            ok = results.get(f"bb_{dim}_ok")
            icon = "✅" if ok else ("❌" if ok is False else "ℹ️")
            print(f"  外形寸法 ({label}):       {icon} {val}mm")

    if "volume_mm3" in results:
        vol = results["volume_mm3"]
        ok = results.get("volume_ok", False)
        print(f"  体積:               {'✅' if ok else '❌'} {vol:,.1f} mm³")

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return results.get("solid_valid") == True and results.get("volume_ok", False)


def export_preview(shape, output_path: str, projection=(1, -1, 0.5)):
    """SVG プレビュー画像を出力"""
    try:
        cq.exporters.export(
            shape, output_path,
            exportType=cq.exporters.ExportTypes.SVG,
            opt={
                "width": 800, "height": 600,
                "marginLeft": 20, "marginTop": 20,
                "projectionDir": projection
            }
        )
        print(f"  📸 プレビュー: {output_path}")
    except Exception as e:
        print(f"  ⚠️ プレビュー生成失敗: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 以下は Claude がプロジェクトごとにカスタマイズする部分
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_body(params: dict):
    """カテゴリ A-1: ボディを生成（プロジェクトごとにカスタマイズ）"""

    # 基本形状
    body = (
        cq.Workplane("XY")
        .box(
            p(params, "outer_envelope", "width"),
            p(params, "outer_envelope", "depth"),
            p(params, "outer_envelope", "height")
        )
    )

    # 外側フィレット（shell の前に実行）
    body = body.edges("|Z").fillet(p(params, "global", "fillet_radius"))

    # シェル（上面開放）
    body = body.faces(">Z").shell(-p(params, "global", "wall_thickness"))

    # 取付穴
    pitch_x = p(params, "mounting_interface", "bolt_hole_pitch_x")
    pitch_y = p(params, "mounting_interface", "bolt_hole_pitch_y")
    hole_d = p(params, "mounting_interface", "bolt_hole_diameter")
    cb_d = p(params, "mounting_interface", "counterbore_diameter")
    cb_depth = p(params, "mounting_interface", "counterbore_depth")

    body = (
        body.faces("<Z").workplane()
        .rect(pitch_x, pitch_y, forConstruction=True)
        .vertices()
        .cboreHole(hole_d, cb_d, cb_depth)
    )

    return body


def generate_lid(params: dict):
    """カテゴリ A-2: 蓋を生成（プロジェクトごとにカスタマイズ）"""

    wall = p(params, "global", "wall_thickness")
    clearance = p(params, "global", "fit_clearance")
    lid_thickness = 3.0

    # 蓋の天板
    lid = (
        cq.Workplane("XY")
        .box(
            p(params, "outer_envelope", "width"),
            p(params, "outer_envelope", "depth"),
            lid_thickness
        )
    )

    # フィレット
    lid = lid.edges("|Z").fillet(p(params, "global", "fillet_radius"))

    # 嵌合スカート
    inner_w = p(params, "outer_envelope", "width") - 2 * wall - 2 * clearance
    inner_d = p(params, "outer_envelope", "depth") - 2 * wall - 2 * clearance
    overlap = p(params, "lid_interface", "lid_overlap")

    lid = (
        lid.faces("<Z").workplane()
        .rect(inner_w, inner_d)
        .extrude(overlap)
    )

    return lid


# ── メイン ──

def main():
    parser = argparse.ArgumentParser(description="パラメトリック STEP 生成")
    parser.add_argument("--params", default="parameters.json", help="パラメータ JSON")
    parser.add_argument("--output", default="./step/", help="出力ディレクトリ")
    parser.add_argument("--validate", action="store_true", help="バリデーション実行")
    parser.add_argument("--preview", action="store_true", help="SVG プレビュー出力")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    params = load_params(args.params)

    product = params.get("_meta", {}).get("product_name", "project")
    print(f"🔧 STEP 生成開始: {product}")
    print(f"   パラメータ: {args.params}")
    print(f"   出力先: {args.output}")

    all_valid = True

    # ── P001: ボディ ──
    print("\n📦 P001: ボディ...")
    try:
        body = generate_body(params)
        body_path = os.path.join(args.output, "P001_body.step")
        cq.exporters.export(body, body_path)
        print(f"  ✅ {body_path}")

        if args.validate:
            result = validate_step(body, params, "P001_body")
            valid = print_validation(result)
            all_valid = all_valid and valid

        if args.preview:
            preview_dir = os.path.join(os.path.dirname(args.output.rstrip("/")), "preview")
            os.makedirs(preview_dir, exist_ok=True)
            export_preview(body, os.path.join(preview_dir, "P001_body.svg"))

    except Exception as e:
        print(f"  ❌ エラー: {e}")
        all_valid = False

    # ── P002: 蓋 ──
    print("\n📦 P002: 蓋...")
    try:
        lid = generate_lid(params)
        lid_path = os.path.join(args.output, "P002_lid.step")
        cq.exporters.export(lid, lid_path)
        print(f"  ✅ {lid_path}")

        if args.validate:
            result = validate_step(lid, params, "P002_lid")
            # 蓋のBBは外形と異なるのでBBチェックはスキップ
            print_validation(result)

        if args.preview:
            export_preview(lid, os.path.join(preview_dir, "P002_lid.svg"))

    except Exception as e:
        print(f"  ❌ エラー: {e}")
        all_valid = False

    # ── 結果サマリ ──
    print("\n" + "=" * 50)
    if all_valid:
        print("✅ 全部品の生成・バリデーション成功")
    else:
        print("⚠️ 一部の部品でエラーまたはバリデーション失敗")
    print("=" * 50)

    return 0 if all_valid else 1


if __name__ == "__main__":
    sys.exit(main())
