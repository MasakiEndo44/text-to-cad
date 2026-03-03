#!/usr/bin/env python3
"""
Stage 3: BOM / 構成図生成ヘルパー

BOM の3カテゴリ分類、部品削減チェック、サマリー出力を行う。
"""
import json
import csv
import os
from datetime import datetime


def create_bom_entry(part_number: str, name: str, category: str, quantity: int = 1,
                     material: str = "", dimensions: str = "", mfg_method: str = "",
                     connection: str = "", source: str = "", notes: str = "",
                     supplier: str = "", cad_url: str = "") -> dict:
    """BOM エントリを1件作成"""
    return {
        "part_number": part_number,
        "name": name,
        "category": category,  # "A", "B", "C"
        "quantity": quantity,
        "material": material,
        "dimensions_mm": dimensions,
        "manufacturing_method": mfg_method,
        "connection_method": connection,
        "source": source,
        "supplier": supplier,
        "cad_download_url": cad_url,
        "notes": notes
    }


def category_summary(bom_parts: list) -> dict:
    """カテゴリ別の集計"""
    summary = {"A_original": 0, "B_standard": 0, "C_material": 0}
    for p in bom_parts:
        cat = p.get("category", "?")
        if cat == "A":
            summary["A_original"] += 1
        elif cat == "B":
            summary["B_standard"] += 1
        elif cat == "C":
            summary["C_material"] += 1
    return summary


def print_bom_summary(bom_parts: list):
    """BOM のカテゴリ別サマリーを表示"""
    summary = category_summary(bom_parts)
    total = sum(summary.values())
    a_count = summary["A_original"]

    print("\n━━━ 部品数サマリ ━━━")
    print(f"  カテゴリ A (オリジナル):  {a_count} 部品  ", end="")
    if a_count <= 2:
        print("✅ 目標以内")
    elif a_count == 3:
        print("⚠️ 上限ギリギリ")
    else:
        print("❌ 多すぎ！削減を検討")
    print(f"  カテゴリ B (標準品):      {summary['B_standard']} 部品")
    print(f"  カテゴリ C (加工素材):    {summary['C_material']} 部品")
    print(f"  ─────────────────────")
    print(f"  合計:                     {total} 部品")
    if total > 0:
        print(f"  AI モデリング対象:        {a_count} / {total} ({a_count*100//total}%)")
    print("━━━━━━━━━━━━━━━━━━")

    if a_count > 2:
        a_parts = [p["name"] for p in bom_parts if p["category"] == "A"]
        print(f"\n⚠️ オリジナル部品が {a_count}個あります。")
        print(f"  AI の能力では部品間の嵌合精度が保証できません。")
        print(f"  以下を統合または標準品化できないか検討してください:")
        for name in a_parts:
            print(f"    - {name}")


def export_bom_csv(bom_parts: list, output_path: str = "bom.csv"):
    """BOM を CSV に出力"""
    cat_labels = {"A": "A(オリジナル)", "B": "B(標準品)", "C": "C(加工素材)"}
    fieldnames = ["カテゴリ", "部品番号", "名称", "数量", "材質",
                  "寸法(mm)", "製造方法", "接続方式", "調達先/型番"]

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in sorted(bom_parts, key=lambda x: x["category"]):
            writer.writerow({
                "カテゴリ": cat_labels.get(p["category"], "?"),
                "部品番号": p["part_number"],
                "名称": p["name"],
                "数量": p["quantity"],
                "材質": p["material"],
                "寸法(mm)": p["dimensions_mm"],
                "製造方法": p["manufacturing_method"],
                "接続方式": p["connection_method"],
                "調達先/型番": p.get("source", "")
            })

    print(f"✅ BOM CSV 出力: {output_path}")


def export_bom_json(product_name: str, bom_parts: list,
                    assembly_sequence: list = None,
                    interference_notes: list = None,
                    output_path: str = "bom.json"):
    """BOM を JSON に出力"""
    bom = {
        "product_name": product_name,
        "version": "1.0.0",
        "generated_at": datetime.now().isoformat(),
        "total_parts": len(bom_parts),
        "category_summary": category_summary(bom_parts),
        "parts": bom_parts,
        "assembly": {
            "sequence": assembly_sequence or [],
            "interference_notes": interference_notes or []
        }
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(bom, f, ensure_ascii=False, indent=2)

    print(f"✅ BOM JSON 出力: {output_path}")
    return bom


def generate_download_guide(bom_parts: list, output_path: str = "standard_parts/download_guide.md"):
    """カテゴリ B 標準品の CAD データダウンロードガイドを生成"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    b_parts = [p for p in bom_parts if p["category"] == "B"]

    if not b_parts:
        return

    lines = [
        "# 標準品 CAD データ ダウンロードガイド",
        "",
        "以下の標準品の STEP データをダウンロードし、`standard_parts/` フォルダに配置してください。",
        "",
        "| 部品番号 | 名称 | 型番/調達先 | DL先 |",
        "|---------|------|-----------|------|",
    ]
    for p in b_parts:
        url = p.get("cad_download_url", "メーカーサイトで型番検索")
        lines.append(f"| {p['part_number']} | {p['name']} | {p.get('source', '')} | {url} |")

    lines.extend([
        "",
        "## 主要 CAD データ入手先",
        "- **MISUMI**: https://www.misumi-ec.com/ (MISUMI-VONA で型番検索→CADダウンロード)",
        "- **MonotaRO**: https://www.monotaro.com/",
        "- **McMaster-Carr**: https://www.mcmaster.com/",
        "- **Traceparts**: https://www.traceparts.com/",
        "- **3DContentCentral**: https://www.3dcontentcentral.com/",
    ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ ダウンロードガイド: {output_path}")


if __name__ == "__main__":
    # テスト
    parts = [
        create_bom_entry("P001", "ボディ", "A", 1, "ABS", "120x80x40",
                         "3Dプリント(FDM)", "-", "AI生成STEP",
                         notes="スタンドオフ・ケーブルガイド一体"),
        create_bom_entry("P002", "蓋", "A", 1, "ABS", "122x82x5",
                         "3Dプリント(FDM)", "スナップフィット", "AI生成STEP"),
        create_bom_entry("P003", "なべ小ネジ M3x8", "B", 4, "SUS304", "M3x8",
                         "-", "ネジ止め", "MISUMI B08-0308", supplier="MISUMI"),
        create_bom_entry("P004", "SW M3", "B", 4, "SUS304", "M3",
                         "-", "-", "MISUMI FSWM3"),
        create_bom_entry("P005", "ケーブルグランド PG7", "B", 1, "PA66", "PG7",
                         "-", "ネジ込み", "Lapp SKINTOP ST-M"),
        create_bom_entry("P006", "Oリング P-12", "B", 1, "NBR", "φ11.8xφ2.4",
                         "-", "溝嵌め", "NOK P-12"),
        create_bom_entry("P007", "銘板", "C", 1, "SUS304", "40x20x0.5",
                         "エッチング", "接着", "別途手配"),
    ]

    print_bom_summary(parts)
    export_bom_csv(parts)
    export_bom_json("センサーケース", parts)
    generate_download_guide(parts)
