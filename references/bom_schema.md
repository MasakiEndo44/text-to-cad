# BOM (Bill of Materials) スキーマ定義

## 3カテゴリ分類

### カテゴリ A: オリジナル部品（AI が STEP を生成）
目標 2個以下。AI が CadQuery コードを生成する部品。

### カテゴリ B: 標準品（型番指定のみ）
STEP はメーカーサイトからダウンロード。

### カテゴリ C: 加工素材（既製素材 + 加工指示）
必要に応じて簡易 STEP を生成。

## JSON スキーマ

```json
{
  "product_name": "製品名",
  "version": "1.0.0",
  "total_parts": 7,
  "category_summary": {
    "A_original": 2,
    "B_standard": 4,
    "C_material": 1
  },
  "parts": [
    {
      "part_number": "P001",
      "name": "ボディ",
      "category": "A",
      "quantity": 1,
      "material": "ABS",
      "dimensions_mm": "120x80x40",
      "manufacturing_method": "3Dプリント(FDM)",
      "connection_method": "-",
      "source": "AI生成STEP",
      "notes": "基板スタンドオフ、ケーブルガイド一体成形"
    },
    {
      "part_number": "P003",
      "name": "なべ小ネジ M3x8",
      "category": "B",
      "quantity": 4,
      "material": "SUS304",
      "dimensions_mm": "M3x8",
      "manufacturing_method": "-",
      "connection_method": "ネジ止め",
      "source": "MISUMI B08-0308",
      "supplier": "MISUMI",
      "cad_download_url": "https://meviy.misumi-ec.com/...",
      "notes": ""
    },
    {
      "part_number": "P007",
      "name": "銘板",
      "category": "C",
      "quantity": 1,
      "material": "SUS304",
      "dimensions_mm": "40x20x0.5",
      "manufacturing_method": "エッチング",
      "connection_method": "接着",
      "source": "別途手配",
      "notes": "加工図別途"
    }
  ],
  "assembly": {
    "sequence": [
      "1. ボディ(P001)に基板をM2ネジで固定",
      "2. ケーブルをグランド(P005)経由で引き出し",
      "3. Oリング(P006)を蓋の溝に嵌め",
      "4. 蓋(P002)をスナップフィットで閉じ",
      "5. M3ネジ(P003)+ワッシャ(P004)で固定"
    ],
    "interference_notes": [
      "P001 ボス高さ + 基板厚 + コネクタ高さ < 内寸高さ を確認",
      "ケーブルグランドのネジ込み代 ≥ ボディ壁厚 を確認"
    ]
  }
}
```

## CSV 出力フォーマット

```csv
カテゴリ,部品番号,名称,数量,材質,寸法(mm),製造方法,接続方式,調達先/型番
A(オリジナル),P001,ボディ,1,ABS,120x80x40,3Dプリント(FDM),-,AI生成STEP
A(オリジナル),P002,蓋,1,ABS,122x82x5,3Dプリント(FDM),スナップフィット,AI生成STEP
B(標準品),P003,なべ小ネジ M3x8,4,SUS304,M3x8,-,ネジ止め,MISUMI B08-0308
B(標準品),P004,SW M3,4,SUS304,M3,-,-,MISUMI FSWM3
B(標準品),P005,ケーブルグランド PG7,1,PA66,PG7,-,ネジ込み,Lapp SKINTOP
B(標準品),P006,Oリング P-12,1,NBR,φ11.8xφ2.4,-,溝嵌め,NOK P-12
C(加工素材),P007,銘板,1,SUS304,40x20x0.5,エッチング,接着,別途手配
```

## 部品削減チェックリスト（Stage 3 で必ず適用）

各部品に対して上から順にチェック。「はい」に該当したら AI モデリング対象外:

1. ✅ 市販品で代替可能か？ → カテゴリ B（型番指定のみ）
2. ✅ 隣接部品と一体化可能か？ → フィーチャー統合
3. ✅ 既製素材の加工で可能か？ → カテゴリ C
4. ❌ すべて「いいえ」→ カテゴリ A（オリジナル部品）
