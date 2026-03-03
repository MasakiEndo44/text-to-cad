# parameters.json スキーマ定義

## 概要

parameters.json は STEP 生成時の全重要寸法を集約するファイル。
ユーザーが直接編集して寸法を変更し、`generate_step.py` を再実行するだけで
STEP を更新できるようにする。

## フィールド定義

各寸法パラメータは以下の構造:

```json
{
  "value": 2.0,
  "unit": "mm",
  "note": "日本語の説明（非設計者にもわかるように）",
  "critical": true,
  "recommended_range": [1.0, 5.0],
  "constraint": "3Dプリント(FDM): ≥1.2mm, 射出成形: ≥0.8mm"
}
```

| フィールド | 必須 | 型 | 説明 |
|-----------|------|-----|------|
| `value` | ✅ | number | 現在の寸法値 |
| `unit` | ✅ | string | 単位 ("mm", "deg", "-") |
| `note` | ✅ | string | 日本語の説明 |
| `critical` | ❌ | boolean | 相手部品との嵌合に影響する場合 true |
| `recommended_range` | ❌ | [min, max] | 推奨値の範囲。範囲外で警告 |
| `constraint` | ❌ | string | 製造方法依存の制約の説明 |

## カテゴリ構成

```json
{
  "_meta": {
    "product_name": "製品名",
    "version": "1.0.0",
    "generated_by": "text-to-cad skill",
    "last_modified": "ISO8601 datetime"
  },
  "global": {
    "wall_thickness": {},
    "fillet_radius": {},
    "fit_clearance": {}
  },
  "outer_envelope": {
    "width": {},
    "depth": {},
    "height": {}
  },
  "mounting_interface": {
    "bolt_hole_diameter": {},
    "bolt_hole_pitch_x": {},
    "bolt_hole_pitch_y": {},
    "counterbore_diameter": {},
    "counterbore_depth": {}
  },
  "internal_cavity": {
    "pcb_width": {},
    "pcb_depth": {},
    "pcb_standoff_height": {},
    "pcb_mount_hole_dia": {}
  },
  "openings": {},
  "lid_interface": {}
}
```

## 推奨値ガイド

### 肉厚 (wall_thickness)
| 製造方法 | 推奨範囲 | デフォルト |
|---------|---------|-----------|
| FDM 3Dプリント | 1.2 - 4.0 mm | 2.0 mm |
| SLA 3Dプリント | 0.8 - 3.0 mm | 1.5 mm |
| 射出成形 (ABS) | 0.8 - 3.5 mm | 2.0 mm |
| 板金 | 0.5 - 3.0 mm | 1.0 mm |

### クリアランス (fit_clearance)
| 製造方法 | すきま嵌合 | 中間嵌合 |
|---------|-----------|---------|
| FDM 3Dプリント | 0.2 - 0.4 mm | 0.1 - 0.2 mm |
| SLA 3Dプリント | 0.1 - 0.2 mm | 0.05 - 0.1 mm |
| 射出成形 | 0.05 - 0.15 mm | 0.02 - 0.05 mm |

### ネジ穴径
| ネジサイズ | 通し穴径 | タップ下穴径 |
|-----------|---------|------------|
| M2 | 2.2 mm | 1.6 mm |
| M2.5 | 2.7 mm | 2.05 mm |
| M3 | 3.2 mm | 2.5 mm |
| M4 | 4.3 mm | 3.3 mm |
| M5 | 5.3 mm | 4.2 mm |

### フィレット半径
- 目安: 辺長の 1/4 以下
- 最小: 0.3mm（3Dプリントの最小R）
- CadQuery の安定動作: 肉厚の 1/2 以下を推奨
