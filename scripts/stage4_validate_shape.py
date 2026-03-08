#!/usr/bin/env python3
"""
Stage 4 セマンティック検証スクリプト

生成された STEP ファイルが feature_mapping.json の仕様を満たしているか検証する。
CadQuery のインポートが必要。

使い方:
    python scripts/stage4_validate_shape.py \
        --step step/P001_body.step \
        --params parameters.json \
        --fmap feature_mapping.json \
        --part-id P001
"""

import argparse
import json
import sys
import math

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_param(params, section, key):
    """parameters.json からネストされた値を取得"""
    entry = params.get(section, {}).get(key, {})
    if isinstance(entry, dict) and "value" in entry:
        return float(entry["value"])
    return None


def validate_bounding_box(shape, params, tolerance_mm=1.0):
    """バウンディングボックスが parameters の外形寸法に一致するか検証"""
    bb = shape.BoundingBox()
    actual = {
        "W": bb.xlen,
        "D": bb.ylen,
        "H": bb.zlen,
    }

    # parameters.json から期待値を取得
    expected = {}
    oe = params.get("outer_envelope", {})
    for key, dim_key in [("width", "W"), ("depth", "D"), ("height", "H"),
                         ("outer_diameter", "OD")]:
        if key in oe:
            val = oe[key]
            expected[dim_key] = float(val["value"]) if isinstance(val, dict) else float(val)

    results = []

    if "OD" in expected:
        # 円柱形: W と D は直径に近いはず
        for dim_key in ["W", "D"]:
            diff = abs(actual[dim_key] - expected["OD"])
            ok = diff <= tolerance_mm
            results.append({
                "check": f"BB {dim_key} ≈ OD",
                "expected": expected["OD"],
                "actual": round(actual[dim_key], 2),
                "diff": round(diff, 2),
                "pass": ok,
            })
        if "H" in expected:
            diff = abs(actual["H"] - expected["H"])
            ok = diff <= tolerance_mm
            results.append({
                "check": "BB H",
                "expected": expected["H"],
                "actual": round(actual["H"], 2),
                "diff": round(diff, 2),
                "pass": ok,
            })
    else:
        for dim_key in ["W", "D", "H"]:
            if dim_key not in expected:
                continue
            diff = abs(actual[dim_key] - expected[dim_key])
            ok = diff <= tolerance_mm
            results.append({
                "check": f"BB {dim_key}",
                "expected": expected[dim_key],
                "actual": round(actual[dim_key], 2),
                "diff": round(diff, 2),
                "pass": ok,
            })

    return results


def count_cylindrical_faces(shape):
    """形状に含まれる円筒面の数をカウント（≈穴の数の近似）"""
    try:
        from OCP.BRep import BRep_Tool
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.GeomAbs import GeomAbs_Cylinder

        count = 0
        explorer = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
        while explorer.More():
            face = explorer.Current()
            surface = BRep_Tool.Surface_s(face)
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            adaptor = BRepAdaptor_Surface(face)
            if adaptor.GetType() == GeomAbs_Cylinder:
                count += 1
            explorer.Next()
        return count
    except ImportError:
        return -1  # OCP が使えない環境


def validate_hole_count(shape, fmap, part_id):
    """穴の数がフィーチャーマッピングの仕様と一致するか検証"""
    hole_types = {"through_hole", "blind_hole", "cbore_hole"}

    # フィーチャーマッピングから期待穴数を計算
    expected_holes = 0
    part_data = None
    for part in fmap.get("parts", []):
        if part.get("part_id") == part_id:
            part_data = part
            break

    if not part_data:
        return [{"check": "hole_count", "pass": False,
                 "message": f"Part {part_id} not found in feature_mapping.json"}]

    for feat in part_data.get("features", []):
        if feat.get("type") in hole_types:
            positions = feat.get("positions", [])
            if positions:
                expected_holes += len(positions)
            else:
                expected_holes += 1

    # cbore_hole は CadQuery 内部で2つの円筒面を作る（穴 + 座ぐり）
    expected_cylindrical = 0
    for feat in part_data.get("features", []):
        if feat.get("type") == "cbore_hole":
            n = len(feat.get("positions", [None]))
            expected_cylindrical += n * 2
        elif feat.get("type") in {"through_hole", "blind_hole"}:
            n = len(feat.get("positions", [None]))
            expected_cylindrical += n

    # ボスも円筒面を持つ
    for feat in part_data.get("features", []):
        if feat.get("type") == "boss":
            n = len(feat.get("positions", [None]))
            expected_cylindrical += n  # 外周
            if feat.get("inner_hole_dia"):
                expected_cylindrical += n  # 内穴

    actual_cyl = count_cylindrical_faces(shape)

    if actual_cyl < 0:
        return [{"check": "hole_count",
                 "pass": None,
                 "message": "OCP not available, skipping cylindrical face count",
                 "expected_holes": expected_holes}]

    return [{
        "check": "cylindrical_faces",
        "expected_approx": expected_cylindrical,
        "actual": actual_cyl,
        "pass": actual_cyl >= expected_holes,  # 最低限、穴の数以上の円筒面があること
        "note": "cbore_hole は2面、boss は外周+内穴で複数面を生成するため近似値",
    }]


def validate_volume(shape, fmap, params, part_id, tolerance_pct=20):
    """体積が理論値の許容範囲内か検証"""
    actual_vol = shape.Volume()

    part_data = None
    for part in fmap.get("parts", []):
        if part.get("part_id") == part_id:
            part_data = part
            break

    if not part_data:
        return [{"check": "volume", "pass": False,
                 "message": f"Part {part_id} not found"}]

    bs = part_data.get("base_shape", {})
    shape_type = bs.get("type", "unknown")

    theoretical_vol = None

    if shape_type == "box_shell":
        dims = bs.get("dimensions", {})
        W = dims.get("W", 0)
        D = dims.get("D", 0)
        H = dims.get("H", 0)
        wall = bs.get("wall_thickness", 0)
        outer_vol = W * D * H
        inner_vol = (W - 2*wall) * (D - 2*wall) * (H - wall)  # 片面開放
        theoretical_vol = outer_vol - inner_vol

    elif shape_type == "cylinder_shell":
        OD = bs.get("outer_diameter", 0)
        H = bs.get("height", 0)
        wall = bs.get("wall_thickness", 0)
        r_out = OD / 2
        r_in = r_out - wall
        outer_vol = math.pi * r_out**2 * H
        inner_vol = math.pi * r_in**2 * (H - wall)
        theoretical_vol = outer_vol - inner_vol

    elif shape_type == "plate":
        dims = bs.get("dimensions", {})
        W = dims.get("W", 0)
        H = dims.get("H", 0)
        T = dims.get("T", 0)
        theoretical_vol = W * H * T

    elif shape_type in ("bracket_L", "bracket_U"):
        # 簡易推定のみ
        theoretical_vol = None

    if theoretical_vol is None:
        return [{"check": "volume", "pass": None,
                 "message": f"Theoretical volume not calculated for {shape_type}"}]

    diff_pct = abs(actual_vol - theoretical_vol) / theoretical_vol * 100

    return [{
        "check": "volume",
        "expected_mm3": round(theoretical_vol, 1),
        "actual_mm3": round(actual_vol, 1),
        "diff_pct": round(diff_pct, 1),
        "pass": diff_pct <= tolerance_pct,
    }]


def main():
    parser = argparse.ArgumentParser(description="Stage 4 セマンティック検証")
    parser.add_argument("--step", required=True, help="STEP ファイルパス")
    parser.add_argument("--params", required=True, help="parameters.json パス")
    parser.add_argument("--fmap", required=True, help="feature_mapping.json パス")
    parser.add_argument("--part-id", required=True, help="検証する part_id (例: P001)")
    args = parser.parse_args()

    # CadQuery で STEP を読み込み
    try:
        import cadquery as cq
    except ImportError:
        print("❌ CadQuery がインストールされていません: pip install cadquery")
        sys.exit(1)

    print(f"📂 Loading STEP: {args.step}")
    shape = cq.importers.importStep(args.step)

    params = load_json(args.params)
    fmap = load_json(args.fmap)

    print(f"🔍 Validating part: {args.part_id}\n")

    all_results = []

    # 1. バウンディングボックス
    print("── Bounding Box ──")
    bb_results = validate_bounding_box(shape, params)
    all_results.extend(bb_results)
    for r in bb_results:
        icon = "✅" if r["pass"] else "❌"
        print(f"  {icon} {r['check']}: expected={r['expected']}, actual={r['actual']}, diff={r['diff']}mm")

    # 2. 穴の数
    print("\n── Hole Count ──")
    hole_results = validate_hole_count(shape, fmap, args.part_id)
    all_results.extend(hole_results)
    for r in hole_results:
        if r.get("pass") is None:
            print(f"  ⚠️ {r.get('message', 'skipped')}")
        else:
            icon = "✅" if r["pass"] else "❌"
            print(f"  {icon} {r['check']}: expected≈{r.get('expected_approx', '?')}, actual={r.get('actual', '?')}")

    # 3. 体積
    print("\n── Volume ──")
    vol_results = validate_volume(shape, fmap, params, args.part_id)
    all_results.extend(vol_results)
    for r in vol_results:
        if r.get("pass") is None:
            print(f"  ⚠️ {r.get('message', 'skipped')}")
        else:
            icon = "✅" if r["pass"] else "❌"
            print(f"  {icon} volume: expected≈{r.get('expected_mm3')}mm³, actual={r.get('actual_mm3')}mm³, diff={r.get('diff_pct')}%")

    # サマリ
    passed = sum(1 for r in all_results if r.get("pass") is True)
    failed = sum(1 for r in all_results if r.get("pass") is False)
    skipped = sum(1 for r in all_results if r.get("pass") is None)

    print(f"\n{'='*40}")
    print(f"📊 Results: {passed} passed, {failed} failed, {skipped} skipped")

    if failed > 0:
        print("❌ VALIDATION FAILED — 形状を確認してください")
        sys.exit(1)
    else:
        print("✅ VALIDATION PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
