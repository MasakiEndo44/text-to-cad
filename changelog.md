# text-to-cad 改善ログ

## 2026-03-08: パイプライン構造改善 — geometry_tree・視覚的契約・段階的検証の導入
- **きっかけ**: 振り返り改善 — DHT22_CASE_ver2 で Stage 2 SVG は正しかったが STEP 出力が大きく乖離。専門家議論でアーキテクチャレベルの問題を特定
- **ギャップ**: 取付耳が `rect_pad` で記述され外形と乖離、ボスの押し出し方向が逆、feature_mapping が「フラットな操作リスト」で設計意図の構造を表現できなかった
- **根本原因**: 指示不足＋参照情報不足＋スコープ曖昧 — フィーチャータイプの列挙型アプローチの限界。外形輪郭の拡張を表現する手段がなく、LLM の 3D 空間認識の弱さを補う構造的安全ネットが不足
- **変更内容**:
  - `references/feature_mapping_schema.md` を全面改訂: `geometry_tree`（プリミティブ + Boolean 木）で外形を記述する 2 レイヤー構造を導入。`finishing` ブロック追加。`extrude_direction` 追加
  - `SKILL.md` の Stage 3.5 を **3.5a（ジオメトリ分解）/ 3.5b（視覚的契約）/ 3.5c（フィーチャーアプリケーション）** に分割。Stage 4 に段階的フィードバック（高リスク操作後の中間検証）指示を追加
  - `references/cadquery_patterns.md` の統合ビルドテンプレートを geometry_tree 駆動の 3 フェーズ構成に改訂
  - `scripts/stage3_5_preview_svg.py` を新規作成: geometry_tree から簡易 3 面図 SVG を生成（Python 標準ライブラリのみ）

## 2026-03-08: Stage 4 STEP生成品質の抜本的改善（フィーチャーマッピング導入）
- **きっかけ**: 振り返り改善 — DHT22センサーケース設計で Stage 1-2 の要件・図面と Stage 4 の STEP 出力が大きく乖離
- **ギャップ**: 穴が意図しない面に開く、取付耳の位置が異常、ボスが外側に突出、蓋に嵌合構造なし等、形状が全面的に破綻
- **根本原因**: 指示不足＋参照情報不足＋手順の順序問題 — requirements.json の `position` と CadQuery 面セレクタの対応ルールがなく、LLM が3D空間を推測でコーディングしていた。CADAM比較から「LLMの自由度を制約で狭める」原則を学んだ
- **変更内容**:
  - `SKILL.md` に **Stage 3.5「フィーチャーマッピング」を新設**。面指定・座標・ビルド順序を明示するJSON中間表現を導入。複数形状タイプ（box_shell / cylinder_shell / plate / bracket_L / bracket_U）に汎用的に対応
  - `SKILL.md` の Stage 4 を**フィーチャーマッピング駆動**に改訂。面セレクタはマッピングから転記（推測禁止）、セマンティック検証を追加
  - `references/feature_mapping_schema.md` を新規作成。5種のベース形状タイプとフィーチャータイプの詳細スキーマを定義
  - `references/cadquery_patterns.md` に**統合ビルドテンプレート**、円柱シェル・L字ブラケットのパターンを追加
  - `scripts/stage4_validate_shape.py` を新規作成。BB寸法・穴数・体積のセマンティック検証

## 2026-03-08: Stage 2 SVG品質問題（重複穴・重複ラベル）の修正
- **きっかけ**: 直後フィードバック — 正面図の四隅に穴が2重に描かれ、「M4取付」等のラベルがかぶって読めない
- **ギャップ**: 素人でも気づく図面ミス（重複穴・重複ラベル・PCBラベル決め打ち）が発生していた
- **根本原因**: 指示不足＋手順の順序問題 — SVG生成後にClaudeが出力を品質確認するよう指示されていなかった。またスクリプトの `_resolve_hole_positions()` が center_dist 未指定時に同一座標の穴を num_holes 個追加するバグがあった
- **変更内容**:
  - `skills/text-to-cad/scripts/stage3_export_xlsx.py` を新規作成。`openpyxl` を用いて、色分け・列幅調整・枠固定を施した見やすいエクセル（.xlsx）を生成できるようにした。
  - `SKILL.md` の Stage 3 のチェックポイントに、エクセル生成の指示および JSON の `bom` 構造（用途、ミスミ/モノタロウ推奨品番等）の要件を明記した。
