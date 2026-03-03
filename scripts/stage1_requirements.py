#!/usr/bin/env python3
"""
Stage 1: 要件定義 構造化ヘルパー

ヒアリング結果を requirements.json に構造化する。
チェックポイント JSON の生成・読み込みも行う。
"""
import json
import os
from datetime import datetime


def create_empty_requirements():
    """空の requirements テンプレートを生成"""
    return {
        "product_name": "",
        "description": "",
        "dimensions": {
            "outer": {"width_mm": 0, "height_mm": 0, "depth_mm": 0},
            "constraints": ""
        },
        "interfaces": [],
        "internal_components": [],
        "parts_initial": [],
        "functional_requirements": [],
        "manufacturing": {"method": "", "lot_size": 0},
        "constraints": [],
        "reference_materials": {
            "photos": [],
            "drawings": [],
            "datasheets": [],
            "sketches": []
        }
    }


def validate_requirements(req: dict) -> list[str]:
    """要件 JSON のバリデーション。不足項目を返す"""
    warnings = []

    if not req.get("product_name"):
        warnings.append("製品名が未入力です")

    dims = req.get("dimensions", {}).get("outer", {})
    for dim_key in ["width_mm", "height_mm", "depth_mm"]:
        if not dims.get(dim_key) or dims[dim_key] <= 0:
            warnings.append(f"外形寸法 {dim_key} が未設定です")

    if not req.get("manufacturing", {}).get("method"):
        warnings.append("製造方法が未設定です（3Dプリント / 射出成形 / 板金 等）")

    if not req.get("interfaces") and not req.get("constraints"):
        warnings.append("インターフェース情報がありません。単体部品ですか？")

    ref = req.get("reference_materials", {})
    total_refs = sum(len(ref.get(k, [])) for k in ["photos", "drawings", "datasheets", "sketches"])
    if total_refs == 0:
        warnings.append("参考資料がゼロです。実物写真・図面があると精度が上がります")

    return warnings


def save_checkpoint(stage: int, data: dict, output_dir: str = "."):
    """チェックポイント JSON を保存"""
    checkpoint = {
        "stage": stage,
        "status": "completed",
        "timestamp": datetime.now().isoformat(),
        "data": data,
        "next_action": _next_action(stage)
    }
    path = os.path.join(output_dir, f"checkpoint_stage{stage}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    print(f"✅ チェックポイント保存: {path}")
    return path


def load_checkpoint(path: str) -> dict:
    """チェックポイント JSON を読み込み"""
    with open(path, "r", encoding="utf-8") as f:
        cp = json.load(f)
    print(f"📂 チェックポイント読込: Stage {cp['stage']} ({cp['timestamp']})")
    return cp


def _next_action(stage: int) -> str:
    actions = {
        1: "スケッチ提出ゲート → Stage 2（見取り図生成）",
        2: "Stage 3（部品表・構成図）",
        3: "Stage 4（STEP 生成）",
        4: "完了。parameters.json の微調整 → 再生成"
    }
    return actions.get(stage, "不明")


def requirements_summary(req: dict) -> str:
    """要件の日本語サマリーを生成"""
    dims = req.get("dimensions", {}).get("outer", {})
    parts = req.get("parts_initial", [])
    mfg = req.get("manufacturing", {})

    lines = [
        f"📦 **{req.get('product_name', '(未命名)')}**",
        f"   {req.get('description', '')}",
        f"   外形: {dims.get('width_mm', '?')} × {dims.get('depth_mm', '?')} × {dims.get('height_mm', '?')} mm",
        f"   製造: {mfg.get('method', '未定')} ({mfg.get('lot_size', '?')}個)",
        f"   初期部品数: {len(parts)}",
    ]

    interfaces = req.get("interfaces", [])
    if interfaces:
        lines.append(f"   インターフェース: {', '.join(i.get('name', '') for i in interfaces)}")

    internals = req.get("internal_components", [])
    if internals:
        lines.append(f"   内蔵部品: {', '.join(c.get('name', '') for c in internals)}")

    return "\n".join(lines)


if __name__ == "__main__":
    # テスト用
    req = create_empty_requirements()
    req["product_name"] = "センサーケース"
    req["dimensions"]["outer"] = {"width_mm": 120, "height_mm": 40, "depth_mm": 80}
    req["manufacturing"] = {"method": "3Dプリント(FDM)", "lot_size": 5}

    warnings = validate_requirements(req)
    print("=== バリデーション ===")
    for w in warnings:
        print(f"  ⚠️ {w}")

    print("\n=== サマリー ===")
    print(requirements_summary(req))

    save_checkpoint(1, {"requirements": req}, ".")
