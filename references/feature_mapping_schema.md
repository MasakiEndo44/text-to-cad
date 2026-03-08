# フィーチャーマッピング JSON スキーマ

Stage 3.5 で生成する `feature_mapping.json` の詳細仕様。

## 設計思想: 2レイヤー構造

feature_mapping.json は**2つのレイヤー**で部品を記述する:

| レイヤー | 目的 | 記述対象 |
|---------|------|---------|
| **構造レイヤー** (`geometry_tree` + `finishing`) | 部品の外形を確定する | プリミティブの Boolean 木、fillet/shell |
| **加工レイヤー** (`features`) | 確定した外形にフィーチャーを適用する | 穴、ボス、溝 等 |

**なぜ分けるのか**: 取付耳やフランジなど「外形輪郭の拡張」は、穴あけやボス追加とは本質的に異なる。外形はプリミティブの Boolean 合成で表現し、穴・ボスは後加工として適用する。これにより:
- `mounting_ear` や `rib` のような個別タイプを列挙する必要がなくなる
- 外形が確定してから加工するため、面セレクタが安定する
- 構造レイヤーだけでプレビューSVGを生成し、事前に外形を検証できる

---

## トップレベル構造

```json
{
  "coordinate_system": { ... },
  "parts": [ ... ]
}
```

## coordinate_system

全部品共通の座標系定義。

```json
{
  "x_axis": "width",
  "y_axis": "depth",
  "z_axis": "height",
  "origin": "center_of_base_shape"
}
```

`origin` は CadQuery の `box()`/`cylinder()` が原点中心で生成されることに対応。

## parts 配列

カテゴリA（AIが生成する）部品ごとに1要素。

```json
{
  "part_id": "P001",
  "name": "ボディ",
  "geometry_tree": { ... },
  "finishing": { ... },
  "features": [ ... ]
}
```

---

## geometry_tree — 構造レイヤー（外形定義）

部品の外形を**プリミティブの Boolean 木**として記述する。
ツリーのノードはプリミティブ（リーフ）か Boolean 操作（ブランチ）のいずれか。

### ノードタイプ

#### プリミティブノード（リーフ）

```json
{
  "primitive": "box",
  "params": {"W": 70, "D": 45, "H": 85},
  "transform": {"translate": [0, 0, 0]},
  "semantic_tag": "main_body"
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `primitive` | string | ✅ | `"box"`, `"cylinder"`, `"polygon_extrude"` |
| `params` | object | ✅ | プリミティブ固有のパラメータ（下表） |
| `transform` | object | | 位置変換。`translate: [x,y,z]`, `rotate: [ax,ay,az]` |
| `semantic_tag` | string | | 意味ラベル（自由文字列。列挙型でない） |

**プリミティブの params:**

| primitive | params | 説明 |
|-----------|--------|------|
| `box` | `{"W": 幅, "D": 奥行, "H": 高さ}` | 原点中心の直方体 |
| `cylinder` | `{"radius": 半径, "height": 高さ}` | 原点中心の円柱（Z軸方向） |
| `polygon_extrude` | `{"points": [[x,y],...], "height": 高さ}` | 多角形の押し出し |

**semantic_tag の例:**
`"main_body"`, `"mounting_ear"`, `"stiffener_rib"`, `"cable_channel"`, `"flange"` 等。
これは人間の理解とコードコメント用であり、CadQuery の操作選択には影響しない。

#### Boolean 操作ノード（ブランチ）

```json
{
  "operation": "union",
  "children": [
    { "primitive": "box", "params": {"W": 70, "D": 45, "H": 85}, "semantic_tag": "main_body" },
    { "primitive": "box", "params": {"W": 14, "D": 3, "H": 14},
      "transform": {"translate": [-41, 24, 32.5]},
      "semantic_tag": "mounting_ear" }
  ]
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `operation` | string | ✅ | `"union"`, `"subtract"`, `"intersect"` |
| `children` | array | ✅ | 子ノード（プリミティブまたは別の Boolean ノード） |

**子ノードは再帰的にネストできる。** ただし実用上、深さ3以上は稀。

### 完全な geometry_tree 例（耳付きケース）

```json
{
  "geometry_tree": {
    "operation": "union",
    "children": [
      {
        "primitive": "box",
        "params": {"W": 70, "D": 45, "H": 85},
        "semantic_tag": "main_body"
      },
      {
        "primitive": "box",
        "params": {"W": 14, "D": 3, "H": 14},
        "transform": {"translate": [-41, 24, 32.5]},
        "semantic_tag": "mounting_ear_TL"
      },
      {
        "primitive": "box",
        "params": {"W": 14, "D": 3, "H": 14},
        "transform": {"translate": [41, 24, 32.5]},
        "semantic_tag": "mounting_ear_TR"
      },
      {
        "primitive": "box",
        "params": {"W": 14, "D": 3, "H": 14},
        "transform": {"translate": [-41, 24, -32.5]},
        "semantic_tag": "mounting_ear_BL"
      },
      {
        "primitive": "box",
        "params": {"W": 14, "D": 3, "H": 14},
        "transform": {"translate": [41, 24, -32.5]},
        "semantic_tag": "mounting_ear_BR"
      }
    ]
  }
}
```

### 単純な部品の geometry_tree（プリミティブのみ）

耳や張り出しがない単純な箱型ケースは、Boolean ノードなしでプリミティブだけ:

```json
{
  "geometry_tree": {
    "primitive": "box",
    "params": {"W": 100, "D": 60, "H": 40},
    "semantic_tag": "main_body"
  }
}
```

---

## finishing — ベース形状の仕上げ

`geometry_tree` で構成された外形に適用する仕上げ操作。
fillet → shell の順序が CadQuery では必須（逆順はカーネルエラー）。

```json
{
  "finishing": {
    "fillet": {
      "edge_selector": "|Y",
      "radius": 2
    },
    "shell": {
      "open_face": "-Y",
      "thickness": 3,
      "cq_selector": ".faces('<Y')"
    }
  }
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `fillet.edge_selector` | string | | フィレット対象エッジ（例: `"\|Z"`, `"\|Y"`） |
| `fillet.radius` | number | | フィレット半径 (mm) |
| `shell.open_face` | string | | shell で開放する面 (`"+Z"`, `"-Y"` 等) |
| `shell.thickness` | number | | 壁厚 (mm) |
| `shell.cq_selector` | string | | CadQuery 面セレクタ |

`finishing` が不要な部品（蓋など）は省略またはフィールドを個別に省略可能:

```json
{
  "finishing": {
    "fillet": { "edge_selector": "|Y", "radius": 2 }
  }
}
```

---

## features 配列 — 加工レイヤー（穴・ボス・溝等）

`geometry_tree` + `finishing` で確定した外形に対して適用する加工フィーチャー。
**構造レイヤー完了後に適用されるため、面セレクタが安定している。**

### 共通フィールド

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `id` | string | ✅ | 一意な識別子（コードコメントに使用） |
| `source_req` | string | ✅ | 元の要件への参照 (例: `"interfaces[1]"`) |
| `type` | string | ✅ | フィーチャータイプ（下表） |
| `face` | string | ✅ | 加工する面 (例: `"-Z"`, `"+Y"`) |
| `cq_selector` | string | ✅ | CadQuery 面セレクタ (例: `".faces('<Z')"`) |
| `position_on_face` | object | | 面上の位置 `{"x": 0, "y": 0}` (面の中心からのオフセット mm) |
| `build_order` | integer | ✅ | ビルド順序（小さい順に実行） |
| `extrude_direction` | string | | `"inward"` / `"outward"`。boss・rect_pad 等の押出し方向を明示 |

### extrude_direction について

`boss` や `rect_pad` など押し出しを伴うフィーチャーでは、shell 後の workplane 法線方向が予測困難なため、意図する方向を明示する:

- `"inward"`: ケース内側に向かって押し出す（ボス、リブ等）
- `"outward"`: ケース外側に向かって押し出す（外部突起等）

CadQuery コード生成時に、workplane の法線方向と `extrude_direction` を照合して `extrude()` の符号を決定する。

### フィーチャータイプ別の追加フィールド

#### `through_hole`
```json
{"diameter": 12.5}
```

#### `blind_hole`
```json
{"diameter": 5.0, "depth": 8.0}
```

#### `cbore_hole`
```json
{"diameter": 3.4, "cbore_dia": 6.0, "cbore_depth": 2.0}
```

#### `boss`
```json
{"diameter": 8.0, "height": 15.0, "inner_hole_dia": 4.2, "inner_hole_depth": 8.0,
 "extrude_direction": "inward"}
```
inner_hole_* はタッピング下穴やインサート穴のオプション。

#### `rect_pad`
```json
{"width": 70, "height": 15, "thickness": 3,
 "extrude_direction": "outward"}
```

> ⚠️ **rect_pad の使用前チェック**: `position_on_face` がベース形状の外側にある場合、それは外形の拡張（耳・フランジ）であり `rect_pad` ではなく `geometry_tree` の `union` で対応すべき。

#### `rect_pocket`
```json
{"width": 10, "depth_cut": 5, "height": 20}
```

#### `gasket_groove`
```json
{"groove_width": 2, "groove_depth": 1.5, "offset_from_edge": 5}
```

---

## build_order のガイドライン

ビルド順序は形状の安定性に直結する。以下の順序を推奨:

| 順序 | 対象 | 理由 |
|------|------|------|
| (自動) | geometry_tree の構築 | プリミティブ → union/subtract |
| (自動) | finishing (fillet → shell) | shell の前に fillet（逆順はカーネルエラー） |
| 1-N | 面ごとのフィーチャー | 一面ずつ完了させる |
| N+1 | ボス・スタンドオフ | shell 後の内面を `offset` で指定して追加 |
| 最後 | ガスケット溝等 | 合わせ面のフィーチャーは最後 |

geometry_tree の構築と finishing は build_order 以前に自動的に実行される。
`features` 配列内の `build_order` は加工レイヤー内の相対順序。

## 複数穴の位置指定パターン

```json
{
  "id": "PG7_pair",
  "type": "through_hole",
  "face": "-Z",
  "cq_selector": ".faces('<Z')",
  "diameter": 12.5,
  "pattern": "linear",
  "positions": [
    {"x": -15, "y": 5},
    {"x": 15, "y": 5}
  ],
  "build_order": 1
}
```

`pattern` が `"linear"` の場合 `positions` 配列で各穴位置を明示。
`pattern` が `"rectangular"` の場合は `pitch_x`, `pitch_y`, `count_x`, `count_y` で指定可能。

---

## 旧スキーマとの互換性

旧スキーマ（`base_shape` ベース）から新スキーマ（`geometry_tree` ベース）への移行:

| 旧フィールド | 新フィールド | 移行方法 |
|-------------|-------------|---------|
| `base_shape.type: "box_shell"` | `geometry_tree.primitive: "box"` + `finishing.shell` | box のパラメータを `geometry_tree` に、shell/fillet を `finishing` に |
| `base_shape.type: "cylinder_shell"` | `geometry_tree.primitive: "cylinder"` + `finishing.shell` | 同上 |
| `base_shape.type: "plate"` | `geometry_tree.primitive: "box"` (薄い) | finishing は fillet のみ |
| `base_shape.type: "bracket_L"` | `geometry_tree.operation: "union"` + 2つの box | 2つの box プリミティブの union |
| 取付耳の `rect_pad` | `geometry_tree` 内の union 子ノード | 外形の一部としてツリーに含める |
