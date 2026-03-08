---
name: text-to-cad
description: >
  テキストによる製品アイデアから段階的にCAD STEPデータを生成するワークフロー。
  要件定義→見取り図→部品表→STEP の4ステージを対話的に進行する。
  ケース、ブラケット、カバー等のプリズマティック（角柱的）な機構部品に最適化。
  以下のトリガーで使用: 「ケースを設計して」「筐体を作りたい」「ブラケットの3Dデータが欲しい」
  「STEPファイルを生成して」「CADデータを作って」「基板ケースを設計」「取付部品を設計」
  「3Dモデルを作りたい」など、機構部品の設計・CADデータ生成に関するリクエスト全般。
  設計の専門知識がないユーザーでも Stage 1〜2 を操作可能。
---

# Text-to-CAD パイプライン

テキストの製品アイデアから、対話を通じて CAD STEP データまでを段階的に生成する。

## 適用スコープ

本 Skill は **直方体ベースの機構部品** に最適化されている。

| 対応度 | 形状タイプ | 例 |
|--------|-----------|-----|
| ✅ 最適 | 箱型ケース・筐体 | 基板ケース、センサーケース |
| ✅ 最適 | ブラケット・マウント | モーターマウント、センサー取付台 |
| ✅ 対応可 | カバー・蓋・パネル | コネクタカバー、操作パネル |
| ⚠️ 制限あり | 板金部品 | 簡易な曲げなら対応可 |
| ❌ 非対応 | 自由曲面・意匠面 | コンシューマー外装、人間工学グリップ |
| ❌ 非対応 | 歯車・カム機構 | インボリュート歯形 |

スコープ外の依頼が来たら「このスキルは箱型ケースやブラケット等の設計に特化しています」と案内する。

## 最重要原則: AI が作る部品を最小限にする

現状の AI は複数部品のアセンブリ整合が極めて弱い。この Skill では:

1. **一体化**: リブ、ボス、スナップフィット爪等はボディのフィーチャーとして統合
2. **標準品化**: ネジ、Oリング、スペーサー等は型番指定のみ。AI はモデリングしない
3. **目標2部品以下**: AI が CadQuery で生成するオリジナル部品は2個以下に抑える

## パイプライン概要

```
Stage 1 → 🎨 Gate → Stage 2 → Stage 3 → Stage 3.5 → Stage 4
要件定義   スケッチ   SVG図面    BOM/構成図  フィーチャー  STEP生成
(対話)     (推奨)     (Python    (AI+人間    マッピング    (テンプレート
                      標準Lib)   レビュー)   (空間配置)    駆動)
```

各 Stage 終了時に **チェックポイント JSON** を出力する。
新しい会話セッションから再開可能。

---

## Stage 1: 要件定義 — 対話型ヒアリング

### 目的
ユーザーとの対話で要件を引き出し、構造化された要件 JSON にまとめる。

### 基本姿勢
- 聞き役に徹し、いきなり要件を埋めに行かない
- 実物写真・図面・データシートを積極的に求める
- mm 単位の具体的数値を引き出す
- **ユーザーの技術レベルを推定**: 非設計者にはインライン注釈を付ける

#### 用語注釈ルール
非設計者と判断した場合、初出の設計用語に括弧書きで説明を添える:
- 座ぐり（＝ネジ頭が飛び出さないように掘った穴）
- クリアランス（＝部品同士の隙間）
- 穴ピッチ（＝穴と穴の中心間距離）
- フィレット（＝角を丸める処理。R3 = 半径3mmの丸み）
- シェル（＝中身をくり抜いて壁だけ残す処理）

### ヒアリングフロー

4ラウンドで段階的に掘り下げる。各ラウンドでユーザーの回答を待ってから次へ進む。
1ラウンドに質問を詰め込みすぎず、3問以内を心がける。

#### Round 1: 全体像
- 何を作りたいか、何に使うか、誰が使うか
- 既存品や類似製品はあるか → **ある場合は実物写真を求める**
- 「イメージに近い既製品や、参考になるモノの写真はありますか？写真があると認識合わせが格段に早くなります。」

#### Round 2: 寸法・インターフェース
- 最外形寸法（W×D×H mm）
- **相手部品の図面・データシートを要求**: 取付先フレーム、接続先コネクタ等
- 取付穴位置・ピッチ・穴径、開口位置・サイズ
- 「この部品が取り付くフレーム側の図面はありますか？穴ピッチ（＝穴と穴の中心間距離）と穴径がわかると精度が上がります。」

#### Round 3: 機能・構造
- 可動部（ヒンジ、スライド、回転）
- 内蔵物（基板、バッテリー）→ **基板外形図・データシートを要求**
- 環境条件（防水、耐熱、耐荷重）
- 製造方法の希望（3Dプリント、射出成形、板金）
- 「中に入る基板の外形図（DXF や PDF）はありますか？取付穴の位置やコネクタ高さがわかるとケース内寸を正確に決められます。」

#### Round 4: 材質・コスト・制約
- 材質（強度、透明、食品接触 等）
- ロット数（試作1個 ↔ 量産1万個で設計が変わる）
- 予算感・納期
- 「この機能は市販品で実現できないか？」を常に意識する（標準品化の種を拾う）

### 収集推奨の参考資料

| 種別 | 重要度 |
|------|--------|
| 実物写真（類似品・現行品の複数角度） | ⭐⭐⭐ |
| 相手部品の図面（取付先フレーム、基板外形図） | ⭐⭐⭐ |
| データシート（内蔵部品のスペック、寸法図） | ⭐⭐⭐ |
| 手書きスケッチ（ポンチ絵） | ⭐⭐ |
| 既存CADデータ（STEP/DXF） | ⭐⭐ |

### 出力: requirements.json

ヒアリング完了後、以下の構造で JSON を生成し、ユーザーに確認を求める。
「これで次に進んでいいですか？」の確認ゲートを必ず設ける。

```json
{
  "product_name": "",
  "description": "",
  "dimensions": {
    "outer": { "width_mm": 0, "height_mm": 0, "depth_mm": 0 },
    "constraints": ""
  },
  "interfaces": [
    { "name": "", "type": "", "spec": "" }
  ],
  "internal_components": [
    { "name": "", "dimensions": "", "datasheet": "" }
  ],
  "parts_initial": [
    { "name": "", "function": "", "material": "" }
  ],
  "functional_requirements": [],
  "manufacturing": { "method": "", "lot_size": 0 },
  "constraints": [],
  "reference_materials": {
    "photos": [], "drawings": [], "datasheets": [], "sketches": []
  }
}
```

### チェックポイント出力

Stage 1 完了時、`checkpoint_stage1.json` を生成:
```json
{
  "stage": 1,
  "status": "completed",
  "requirements": { ... },
  "conversation_summary": "要件定義の要約テキスト",
  "collected_files": ["list of uploaded file paths"],
  "next_action": "スケッチ提出ゲート → Stage 2 へ"
}
```

---

## 🎨 スケッチ提出ゲート（Stage 1→2 間）

Stage 2 に入る前に手書きスケッチの提出を推奨する:

> 「要件が固まりました。次は技術図面の生成に進みます。
> その前に、手書きのスケッチがあると認識合わせが早くなります。
> 紙にボールペンで描いてスマホで撮影するだけでOKです。
> ① 全体の外観スケッチ（斜めから見た絵が1枚あるとベスト）
> ② 気にしているポイントの注記（ここにボタン、ここに穴、など）
> ③ できればおおよその寸法線
> スキップもできます。スケッチがあれば numbers の確認に活用します。」

スケッチがある場合: 画像を確認しながら requirements.json の数値を精査する。
スケッチがない場合: ヒアリングの数値をそのまま使って図面を生成（確認ラリーで調整）。

---

## Stage 2: SVG 技術図面生成

### ⚠️ 重要な位置づけ
技術図面は **外形・穴位置・寸法の合意形成** が主目的。**設計寸法の根拠にはならない。**
Stage 4 の STEP 生成では、寸法は parameters.json が常に優先。図面とJSONが矛盾したら JSON に従う。

### 特徴
- **外部API不要** — Python 標準ライブラリのみで動作。Google APIキーや追加パッケージ不要。
- **Cursor / Claude Code / Cowork すべてで動作**
- 出力は SVG（ベクター形式）— ブラウザで直接開けて拡大縮小しても劣化なし

### 生成される図面
- 正面図（Width × Height）
- 側面図（Depth × Height）
- 底面図（Width × Depth）— 底面穴・取付穴・内蔵部品フットプリントを含む
- 各ビューに寸法線・中心線・隠れ線付き
- タイトルブロック（製品名・寸法サマリ・作成日）

### インターフェース描画（穴・開口・ボス等）

技術図面の主目的は「外形＋穴位置の合意形成」であり、ただの直方体の3面図では不十分。
requirements.json の `interfaces` 配列に定義された全フィーチャーを、各ビューに描画する。

#### 描画ルール — 正投影図法 (JIS B 0001 / ISO 128)

穴の投影方法は「穴軸と視線の関係」で決まる:

- **穴軸 ∥ 視線（穴を正面から見る）**: 実線の円＋中心線クロス。反対面の穴は破線の円（隠れ線）。
- **穴軸 ⊥ 視線（穴を横から見る）**: 2本の平行破線（穴径の間隔）＋ 1本の中心線（一点鎖線 `8,3,2,3`）。線の長さは穴深さ（=壁厚、貫通穴の場合）。

各ビューでの適用例:

| ビュー（視線方向） | front面穴(軸Z) | back面穴(軸Z) | bottom面穴(軸Y) |
|---|---|---|---|
| **正面図** (視線-Z) | 実線の円 | 隠れ線の円 | 2本の垂直破線 |
| **側面図** (視線-X) | 2本の水平破線（左端） | 2本の水平破線（右端） | 2本の垂直破線 |
| **底面図** (視線+Y) | 2本の垂直破線（上端） | 2本の垂直破線（下端） | 実線の円 |

- **position フィールドから描画面を判定**: `front_face` → front面、`bottom_center` → bottom面、`back_face` → back面。
- **寸法線**: 穴位置の主要寸法（端面からの距離、穴間ピッチ）を記入。代表的な穴グループごとに1〜2本。
- **凡例ラベル**: 各穴/開口の横に短いラベル（例: "PG7", "φ5.3 LED", "M4 取付", "φ8 VENT"）を添える。

#### extract_dims() の設計指針
スクリプトの `extract_dims()` は requirements.json から以下を抽出する:
- `interfaces[*].position` → 描画面の判定
- `interfaces[*].hole_diameter_mm` → 穴径
- `interfaces[*].spec` 内の位置情報（"中央", "端から6mm" 等）→ 座標計算
- 位置が曖昧な場合はケース中央や均等配置でフォールバックし、図面上に "位置未確定" と注記する

### 実行方法

```bash
# Stage 1 の要件JSONから生成（ヒアリング直後に使える）
python scripts/stage2_svg_views.py --req requirements.json --out views/

# Stage 4 の parameters.json から生成（より精確な寸法）
python scripts/stage2_svg_views.py --params parameters.json --out views/

# 両方渡すと parameters.json の値が優先される
python scripts/stage2_svg_views.py --req requirements.json --params parameters.json --out views/
```

出力: `views/technical_drawing.svg`（ブラウザで開いてレビュー）

### ワークフロー

1. Stage 1 完了 → `requirements.json` が揃っている
2. スクリプトを実行 → `technical_drawing.svg` を生成
3. **Claude 自己QC（必須）** — stdout を読み、以下を全て確認してからユーザーに渡す:
   - `⚠️ WARN:` が 0 件であること。あれば原因を特定し `requirements.json` を修正 → 再実行
   - `📊 フィーチャー解析結果:` の穴個数が `interfaces` の定義数と概ね一致すること
   - 同一ラベルが同一ビューに不自然な数（例: "M3 ins." が 8 個）出ていないこと
   - 同一座標・同一径のフィーチャーが重複していないこと
4. ユーザーがブラウザで図面を確認
5. 修正がある場合 → `requirements.json` の数値を修正して再実行（ラリー）
6. 合意が取れたら Stage 3 へ

### ユーザーへの案内文

```
SVG技術図面を生成しました。
views/technical_drawing.svg をブラウザで開いて確認してください。

確認ポイント:
① 外形寸法（W/D/H）は意図通りですか？
② 各面の穴・開口の位置は合っていますか？（ケーブルグランド、LED、ベント穴 等）
③ 取付穴のピッチ・端面からの距離はこれで合っていますか？
④ 図面に描かれていない穴や、不要な穴はありませんか？

以下のような「おかしいな」があれば教えてください（設計知識不要）:
- 穴の円が同じ場所に2個重なって見える
- 文字ラベルが重なって読めない
- 存在しないはずの穴が描かれている
- 穴の数が多すぎる / 少なすぎる

修正があれば数値を教えてください。再生成します。
問題なければ Stage 3（部品表・構成図）に進みます。
```

### スクリプト詳細
`scripts/stage2_svg_views.py` を参照。
`requirements.json` / `parameters.json` の両フォーマットを自動判別して読み込む。

### チェックポイント
`checkpoint_stage2.json`: 要件 + 図面パス + レビュー履歴

---

## Stage 3: 部品表・構成図

### 部品削減チェック（必須）
全部品に以下を適用し、オリジナル部品を最小化する:
1. 市販品で代替できるか? → はい: 型番だけ記載
2. 隣接部品と一体化できるか? → はい: フィーチャーとして統合
3. 既製素材の加工で代替できるか? → はい: 加工指示で対応
4. すべて「いいえ」→ オリジナル部品（カテゴリA）として残す

### BOM 3カテゴリ分類
- **A (オリジナル)**: AI が STEP 生成 — ⚠️ 目標2個以下
- **B (標準品)**: 型番+調達先を記載。STEP はメーカーサイトからDL
- **C (加工素材)**: 既製素材+加工指示

カテゴリ A が3個以上なら警告を出す。

### Claude 簡易設計レビューモード（知見者不在時）
専門家がいない場合、Claude が以下を自動チェック:
- 内蔵部品が筐体内寸に収まるか（算術チェック）
- 型番が実在するか（Web検索で確認）
- 材質と製造法の整合性
- 一般的な設計ルール逸脱（肉厚、ボス径等）

⚠️ Claude のレビューは参考情報。最終判断にはリスクが伴う旨を明示する。

### ユーザー向け部品表 (BOM) の Excel 出力
ユーザーがレビューや調達を直感的に行えるよう、構成要素をまとめた Excel (`.xlsx`) ファイルを出力する。
**このとき、単なる一覧ではなく「部品の用途」や「ミスミ・モノタロウ等での推奨型番」も併記し、視認性の高いフォーマット（列幅調整・背景色・罫線）を適用する。**

Stage 3 完了時に以下を実行して生成する:
```bash
python scripts/stage3_export_xlsx.py --json checkpoint_stage3.json --out output/bom.xlsx
```
※ `openpyxl` ライブラリが必要なため、未インストールの場合は `pip install openpyxl` を実行してあげること。

※ AI は `checkpoint_stage3.json` 生成時に、`bom` 配列の中身として `category`, `part_number`, `name`, `quantity`, `purpose` (用途/役割), `material_spec` (材質/仕様), `supplier_pn` (推奨型番), `remarks` (備考/リンク) を含めること。

### チェックポイント
- `checkpoint_stage3.json`: 要件 + BOM + 構成図（システム連携用）
- `output/bom.xlsx`: 視認性を担保したユーザーレビュー・発注用のExcel部品表

---

## Stage 3.5: フィーチャーマッピング（空間配置の明示化）

### 目的
requirements.json の「何を作るか」を、CadQuery が正しく解釈できる「**どの面のどこに何を作るか**」に翻訳する。
LLM が3D空間の面方向を推測でコーディングすることによる形状破綻を防ぐ、Stage 3 と Stage 4 の間の橋渡しステップ。

### なぜ必要か
Stage 1-3 では要件を `position: "bottom_face"` のように記述するが、CadQuery のコードでは `.faces("<Z")` のような面セレクタに変換する必要がある。この変換を LLM に暗黙的に任せると、座標系の誤解や shell/union 後の面構成変化により穴が意図しない面に開く。フィーチャーマッピングで事前に空間配置を確定させることで、Stage 4 のコード生成を決定論的にする。

### 座標系の標準定義

本スキルでは全形状タイプ共通の座標系を使う:

| 軸 | 方向 | 備考 |
|----|------|------|
| X | Width（幅） | +X = 右, -X = 左 |
| Y | Depth（奥行き） | +Y = 背面, -Y = 正面 |
| Z | Height（高さ） | +Z = 上, -Z = 底 |

**面名 → CadQuery セレクタ対応表:**

| 要件上の面名 | 空間方向 | CadQuery セレクタ |
|------------|---------|------------------|
| `front_face` | -Y | `.faces("<Y")` |
| `back_face` | +Y | `.faces(">Y")` |
| `bottom_face` | -Z | `.faces("<Z")` |
| `top_face` | +Z | `.faces(">Z")` |
| `left_face` | -X | `.faces("<X")` |
| `right_face` | +X | `.faces(">X")` |
| `outer_cylinder` | — | `.faces(selectors.RadiusNthSelector(-1))` |
| `end_face_top` | +Z | 円柱端面 `.faces(">Z")` |
| `end_face_bottom` | -Z | 円柱端面 `.faces("<Z")` |

### ベース形状タイプ

本スキルは複数の形状タイプに対応する。Stage 1 の要件からベース形状を選定する:

| タイプ | 形状 | 用途例 | CadQuery 起点 |
|--------|------|--------|---------------|
| `box_shell` | 直方体シェル（箱型） | ケース・筐体 | `box()` → `shell()` |
| `cylinder_shell` | 円柱シェル | 円筒ケース・キャニスター | `cylinder()` → `shell()` |
| `plate` | 平板 | パネル・蓋単体・ブラケットベース | `box()` (薄い) |
| `bracket_L` | L字ブラケット | モーターマウント・棚受け | 2つの `box()` の union |
| `bracket_U` | U字チャネル | レール・ガイド | `box()` → 溝 `cut` |

このタイプ分類により、Stage 4 のコード生成テンプレートが決まる。

### フィーチャーマッピング JSON の構造

`feature_mapping.json` として出力する。詳細スキーマは `references/feature_mapping_schema.md` を参照。

```json
{
  "coordinate_system": {
    "x_axis": "width", "y_axis": "depth", "z_axis": "height",
    "origin": "center_of_base_shape"
  },
  "parts": [
    {
      "part_id": "P001",
      "name": "ボディ",
      "base_shape": {
        "type": "box_shell",
        "dimensions": {"W": 70, "D": 45, "H": 85},
        "wall_thickness": 3,
        "open_face": "+Z",
        "fillet_radius": 2
      },
      "features": [
        {
          "id": "PG7_left",
          "source_req": "interfaces[1]",
          "type": "through_hole",
          "face": "-Z",
          "cq_selector": ".faces('<Z')",
          "diameter": 12.5,
          "position_on_face": {"x": -15, "y": 5},
          "build_order": 4
        }
      ]
    }
  ]
}
```

### フィーチャータイプ一覧

| タイプ | CadQuery 操作 | 必須パラメータ |
|--------|--------------|---------------|
| `through_hole` | `.hole(d)` | diameter, face, position |
| `blind_hole` | `.hole(d, depth)` | diameter, depth, face, position |
| `cbore_hole` | `.cboreHole(d, cboreDia, cboreDepth)` | diameter, cbore_dia, cbore_depth |
| `rect_pocket` | `.rect().cutBlind()` | width, height, depth, face |
| `boss` | `.circle().extrude()` | diameter, height, face, position |
| `rect_pad` | `.rect().extrude()` | width, height, thickness, face |
| `fillet` | `.fillet()` | radius, edge_selector |
| `chamfer` | `.chamfer()` | distance, edge_selector |
| `gasket_groove` | `.rect().cutBlind()` | width, depth, offset_from_edge |

### ワークフロー

1. Claude が requirements.json + parameters.json + checkpoint_stage3.json から `feature_mapping.json` を自動生成
2. Claude 自己QC:
   - 全 `interfaces` が `features` にマッピングされているか
   - `face` の値が座標系定義と整合しているか
   - `build_order` に重複・矛盾がないか
3. ユーザーにレビューを求める: フィーチャー一覧表（部品ごとに穴・ボス・追加形状を箇条書き）を見せ、face 指定と位置が意図通りか確認
4. 確認後 Stage 4 へ進む

### ユーザーへの案内文

```
フィーチャーマッピングを作成しました。
STEP 生成に入る前に、各フィーチャーの配置を確認してください。

■ P001 ボディ (box_shell 70×45×85mm)
  底面 (-Z): PG7穴 φ12.5 ×2, 通気膜穴 φ8 ×1
  背面 (+Y): M4取付穴 φ4.5 ×2（取付耳に配置）
  内部:     M3ボス φ8 ×4（蓋固定用）

■ P002 蓋 (plate 70×85×5mm)
  前面 (-Y): LED穴 φ3.2 ×1
  4隅:      M3座ぐり穴 ×4
  下面:     嵌合スカート (ボディ内寸にフィット)

確認ポイント:
① 穴がどの面に開くか正しいですか？（底面 / 背面 / 前面）
② 穴の個数は合っていますか？
③ 追加形状（取付耳、ボス、スカート）の位置は意図通りですか？
```

### チェックポイント
`checkpoint_stage3_5.json`: 要件 + BOM + フィーチャーマッピング

---

## Stage 4: CAD STEP 生成（フィーチャーマッピング駆動）

### 原則
AI がモデリングするのはカテゴリ A（目標2部品以下）のみ。
全重要寸法を `parameters.json` に集約し、CadQuery コードから分離する。
**コード生成は必ず `feature_mapping.json` を参照**し、各フィーチャーの面指定・座標・ビルド順序に従う。LLM が面セレクタを推測で決めることを禁止する。

### parameters.json の設計
- `recommended_range` で非設計者が極端な値を入れるのを防止
- `critical: true` で相手部品との嵌合寸法を明示
- `constraint` で製造方法依存の制約を注記
- 詳細スキーマは `references/parameters_schema.md` を参照

### コード生成→検証→修正ループ（最大5回転）

1. **feature_mapping.json を読み込む**（Stage 3.5 の成果物）
2. **ベース形状テンプレートを選択**: `base_shape.type` に応じたパターンを `references/cadquery_patterns.md` から選ぶ
3. Claude が CadQuery コードを生成。このとき:
   - 各フィーチャーのコードブロックに `# feature: {id}` コメントを必ず記載
   - 面セレクタは `feature_mapping.json` の `cq_selector` を**そのまま転記**（推測禁止）
   - ビルド順序は `build_order` に従う
   - `references/cadquery_patterns.md` の「統合ビルドテンプレート」に従い、base → fillet → shell → 各面フィーチャー → ボス → 追加形状 の順序を守る
4. 実行（`python generate_step.py`）
5. エラー → エラー解析 → コード修正 → 3に戻る
6. 正常終了 → **セマンティック検証**（`scripts/stage4_validate_shape.py`）:
   - バウンディングボックスが parameters の ±1mm 以内か
   - 穴（円筒面）の数がフィーチャーマッピングの through_hole/blind_hole/cbore_hole 総数と一致
   - 体積が理論値の ±20% 以内か
7. セマンティック検証 NG → 該当フィーチャーを特定しコード修正。OK → プレビュー生成
8. SVG/STL プレビュー画像をユーザーに提示して最終確認

5回転で解決しない場合、形状の簡略化を提案する。

### CadQuery コード生成の注意点
- `references/cadquery_patterns.md` を必ず参照してからコードを書く
- **面セレクタは feature_mapping.json の cq_selector を転記する**（自分で推測しない）
- shell → fillet の順序に注意（fillet → shell が安全）
- shell/union 後に面構成が変わるため、追加フィーチャーは `.workplane(offset=...)` で明示的に位置指定
- 嵌合する2部品は **同一スクリプト内** で生成し、寸法を共有パラメータで連動させる
- 各フィーチャーのコードに `# feature: {id} | face: {face}` コメントを付けてトレーサビリティを確保

### 出力
```
output/
├── parameters.json
├── feature_mapping.json
├── generate_step.py
├── step/
│   ├── P001_body.step
│   ├── P002_lid.step
│   └── (assembly.step)
├── standard_parts/
│   └── download_guide.md
├── preview/
│   ├── P001_body.svg
│   └── P002_lid.svg
└── README.md
```

---

## 再開時の手順

ユーザーが checkpoint JSON を送ってきた場合:
1. JSON を読み込み、完了済み Stage を確認
2. 次の Stage から再開する旨を伝える
3. 前 Stage の成果物を要約して確認を取る

例: 「checkpoint_stage2.json を受け取りました。Stage 2（技術図面）まで完了しています。
次は Stage 3（部品表・構成図）に進みます。要件の概要は: [要約]。この内容で合っていますか？」
