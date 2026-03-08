# フィーチャーマッピング JSON スキーマ

Stage 3.5 で生成する `feature_mapping.json` の詳細仕様。

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
  "base_shape": { ... },
  "features": [ ... ]
}
```

## base_shape — ベース形状定義

### 共通フィールド

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `type` | string | ✅ | 形状タイプ（下表参照） |
| `fillet_radius` | number | | 外周フィレット半径 (mm) |

### タイプ別フィールド

#### `box_shell` — 箱型ケース

```json
{
  "type": "box_shell",
  "dimensions": {"W": 70, "D": 45, "H": 85},
  "wall_thickness": 3,
  "open_face": "+Z",
  "fillet_radius": 2
}
```

| フィールド | 説明 |
|-----------|------|
| `dimensions.W/D/H` | 外形寸法 (mm) |
| `wall_thickness` | 壁厚 (mm) |
| `open_face` | shell で開放する面 ("+Z", "-Z", etc.) |

CadQuery: `box(W, D, H)` → `edges("|Z").fillet(r)` → `faces(open_face).shell(-wall)`

#### `cylinder_shell` — 円柱ケース

```json
{
  "type": "cylinder_shell",
  "outer_diameter": 60,
  "height": 100,
  "wall_thickness": 2,
  "open_face": "+Z",
  "fillet_radius": 1
}
```

| フィールド | 説明 |
|-----------|------|
| `outer_diameter` | 外径 (mm) |
| `height` | 高さ (mm) |
| `wall_thickness` | 壁厚 (mm) |
| `open_face` | shell で開放する端面 |

CadQuery: `cylinder(height=H, radius=OD/2)` → `faces(open_face).shell(-wall)`

#### `plate` — 平板

```json
{
  "type": "plate",
  "dimensions": {"W": 70, "H": 85, "T": 5},
  "fillet_radius": 2
}
```

| フィールド | 説明 |
|-----------|------|
| `dimensions.W/H` | 幅・高さ (mm) |
| `dimensions.T` | 板厚 (mm) |

CadQuery: `box(W, H, T)` → `edges("|Z").fillet(r)`

#### `bracket_L` — L字ブラケット

```json
{
  "type": "bracket_L",
  "base": {"W": 50, "D": 30, "T": 3},
  "wall": {"W": 50, "H": 40, "T": 3},
  "fillet_radius": 2,
  "inner_fillet": 3
}
```

| フィールド | 説明 |
|-----------|------|
| `base` | 取付面（底板） |
| `wall` | 立ち上がり面 |
| `inner_fillet` | L字内側のフィレット |

CadQuery: 底板 `box()` + 立壁 `box()` → `union()` → 内側 `fillet()`

#### `bracket_U` — U字チャネル

```json
{
  "type": "bracket_U",
  "outer": {"W": 40, "H": 30, "L": 100},
  "wall_thickness": 3,
  "open_face": "+Z"
}
```

| フィールド | 説明 |
|-----------|------|
| `outer` | 外形 W×H×L |
| `wall_thickness` | 壁厚 |
| `open_face` | 溝が開いている面 |

CadQuery: `box(W, H, L)` → 内部を `cut()`

---

## features 配列 — フィーチャー定義

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
{"diameter": 8.0, "height": 15.0, "inner_hole_dia": 4.2, "inner_hole_depth": 8.0}
```
inner_hole_* はタッピング下穴やインサート穴のオプション。

#### `rect_pad`
```json
{"width": 70, "height": 15, "thickness": 3}
```
取付耳やリブなどの突起。

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
| 1 | ベース形状生成 | `box()` / `cylinder()` |
| 2 | 外周フィレット | shell の前にフィレット（逆順はカーネルエラー） |
| 3 | シェル化 | `shell()` で箱にする |
| 4-N | 面ごとのフィーチャー | `-Z` 面 → `+Y` 面 → … の順序は任意だが、一面ずつ完了させる |
| N+1 | ボス・スタンドオフ | shell 後の内面を `offset` で指定して追加 |
| N+2 | 追加形状 (耳等) | union 後に穴を加工 |
| 最後 | ガスケット溝等 | 合わせ面のフィーチャーは最後 |

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
  "build_order": 4
}
```

`pattern` が `"linear"` の場合 `positions` 配列で各穴位置を明示。
`pattern` が `"rectangular"` の場合は `pitch_x`, `pitch_y`, `count_x`, `count_y` で指定可能。
