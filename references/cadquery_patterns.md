# CadQuery パターンライブラリ

Claude が CadQuery コードを生成する際に参照する、検証済みパターン集。
ここに載っているパターンは実際に動作確認されたものなので、優先的に使う。

## 基本原則

### 操作順序（最重要）
CadQuery/OpenCASCADE は操作順序に敏感。以下の順序を守ること:

```
1. box / cylinder 等の基本形状
2. fillet（角R）     ← shell の前に fillet すると失敗しやすい
3. shell（くり抜き） ← fillet 後に shell が安全
4. 穴あけ（hole, cboreHole）
5. 突起・ボス（extrude）
```

**NG パターン**: shell → fillet（薄い壁にフィレットをかけるとカーネルエラー）
**OK パターン**: fillet → shell → 穴あけ → ボス追加

### 面セレクタ早見表

| セレクタ | 意味 | 用例 |
|---------|------|------|
| `">Z"` | Z方向で最も高い面（上面） | 蓋の取付面 |
| `"<Z"` | Z方向で最も低い面（底面） | 取付穴の加工面 |
| `">X"` | X方向で最も遠い面（右側面） | ケーブル穴 |
| `"<X"` | X方向で最も近い面（左側面） | |
| `"\|Z"` | Z軸に平行なエッジ（縦エッジ） | 箱の角にフィレット |
| `">Z[-2]"` | Z方向で上から2番目の面 | shell 後の内底面（注意: 不安定） |

**⚠️ `-2` 等のインデックスセレクタは shell/cut 後に面の数が変わるため不安定。**
可能であれば `.workplane(offset=...)` で明示的に位置指定する方が安全。

## パターン1: 基板ケース（本体）

最も頻出のパターン。箱→フィレット→シェル→穴の順序。

```python
import cadquery as cq
import json

with open("parameters.json") as f:
    params = json.load(f)

def p(cat, key):
    return params[cat][key]["value"]

# 基本形状
body = (
    cq.Workplane("XY")
    .box(p("outer_envelope", "width"),
         p("outer_envelope", "depth"),
         p("outer_envelope", "height"))
)

# 外側フィレット（shell の前に！）
body = body.edges("|Z").fillet(p("global", "fillet_radius"))

# シェル（上面を開放して箱にする）
body = body.faces(">Z").shell(-p("global", "wall_thickness"))

# 底面に取付穴
pitch_x = p("mounting_interface", "bolt_hole_pitch_x")
pitch_y = p("mounting_interface", "bolt_hole_pitch_y")
body = (
    body.faces("<Z").workplane()
    .rect(pitch_x, pitch_y, forConstruction=True)
    .vertices()
    .cboreHole(
        p("mounting_interface", "bolt_hole_diameter"),
        p("mounting_interface", "counterbore_diameter"),
        p("mounting_interface", "counterbore_depth")
    )
)

cq.exporters.export(body, "P001_body.step")
```

## パターン2: 嵌合蓋

ボディの内寸から自動算出して嵌合スカートを作る。

```python
# ボディの内寸を計算（パラメータから自動算出）
wall = p("global", "wall_thickness")
clearance = p("global", "fit_clearance")
lid_thickness = 3.0  # mm

inner_w = p("outer_envelope", "width") - 2 * wall - 2 * clearance
inner_d = p("outer_envelope", "depth") - 2 * wall - 2 * clearance
overlap = p("lid_interface", "lid_overlap")

# 蓋の天板
lid = (
    cq.Workplane("XY")
    .box(p("outer_envelope", "width"),
         p("outer_envelope", "depth"),
         lid_thickness)
)

# フィレット
lid = lid.edges("|Z").fillet(p("global", "fillet_radius"))

# 嵌合スカート（下面から突出）
lid = (
    lid.faces("<Z").workplane()
    .rect(inner_w, inner_d)
    .extrude(overlap)
)

cq.exporters.export(lid, "P002_lid.step")
```

## パターン3: ボス（スタンドオフ）一体成形

基板取付ボスをボディの内底面に一体で生やす。
shell 後の内底面を取得するのがポイント。

```python
# shell 後のボディに対して内底面にボスを追加
# ⚠️ .faces("<Z[-2]") は不安定なので、offset 方式を推奨

standoff_h = p("internal_cavity", "pcb_standoff_height")
mount_d = p("internal_cavity", "pcb_mount_hole_dia")
boss_od = mount_d + 3.0  # ボス外径 = 穴径 + 3mm

# workplane を底面内側に設定（底面 + 壁厚分上にオフセット）
wp = body.faces("<Z").workplane(offset=p("global", "wall_thickness"))

# 基板取付穴パターン
pcb_pitch_x = p("internal_cavity", "pcb_width") - 5
pcb_pitch_y = p("internal_cavity", "pcb_depth") - 5

body = (
    wp.rect(pcb_pitch_x, pcb_pitch_y, forConstruction=True)
    .vertices()
    .circle(boss_od / 2).extrude(standoff_h)
)

# ボス上面にタッピングネジ下穴
body = (
    body.faces(">Z").workplane()
    .rect(pcb_pitch_x, pcb_pitch_y, forConstruction=True)
    .vertices()
    .hole(mount_d, standoff_h)
)
```

## パターン4: 側面の穴（ケーブル穴・LED窓）

```python
# 側面（+X面）にケーブル穴
cable_d = p("openings", "cable_hole_diameter")
cable_z = p("openings", "cable_hole_offset_z")
height = p("outer_envelope", "height")

body = (
    body.faces(">X").workplane()
    .center(0, cable_z - height / 2)
    .hole(cable_d)
)

# 角型の窓（LED等）
window_w = p("openings", "led_window_width")
window_h = p("openings", "led_window_height")
wall = p("global", "wall_thickness")

body = (
    body.faces(">X").workplane()
    .center(0, 5)  # Y方向オフセット
    .rect(window_w, window_h)
    .cutBlind(-wall)  # 壁厚分だけ貫通
)
```

## パターン5: スナップフィット爪

蓋またはボディに一体成形する。爪は単純な突起として表現する。

```python
snap_w = p("lid_interface", "snap_fit_width")
snap_d = p("lid_interface", "snap_fit_depth")  # 爪の掛かり量

# 蓋の嵌合スカートの外面に爪を追加
# 長辺の中央2箇所に配置
depth = p("outer_envelope", "depth")

lid = (
    lid.faces("<X").workplane()  # スカートの面を選択
    .center(0, -overlap / 2)     # 爪の位置
    .rect(snap_w, snap_d)
    .extrude(snap_d)             # 外側に突出
)
```

## パターン6: SVG プレビュー出力

STEP 生成後にプレビュー画像を作る。

```python
import cadquery as cq

# SVG エクスポート（軽量で確実）
cq.exporters.export(body, "preview_body.svg",
                    exportType=cq.exporters.ExportTypes.SVG,
                    opt={"width": 600, "height": 400,
                         "marginLeft": 10, "marginTop": 10,
                         "projectionDir": (1, -1, 0.5)})

# STL エクスポート（3Dビューア用）
cq.exporters.export(body, "preview_body.stl")
```

## よくあるエラーと対処法

| エラー | 原因 | 対処 |
|-------|------|------|
| `StdFail_NotDone` | フィレット半径が大きすぎる | フィレットR を小さくする（目安: 辺長の1/3以下） |
| `BRepAlgoAPI error` | shell と fillet の順序 | fillet → shell の順序にする |
| `wire is not closed` | スケッチが閉じていない | rect/circle を使い、polyline は避ける |
| `face selector returns empty` | shell/cut 後に面構成が変化 | offset workplane 方式に切り替え |
| `Null TopoDS_Shape` | 形状が破綻（ゼロ厚み等） | 肉厚を大きくする、形状を単純化 |

## CadQuery インストール確認

```bash
pip install cadquery --break-system-packages
python -c "import cadquery as cq; print('CadQuery OK:', cq.__version__)"
```
