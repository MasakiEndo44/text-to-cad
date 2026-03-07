# text-to-cad 改善ログ

## 2026-03-08: Stage 2 SVG品質問題（重複穴・重複ラベル）の修正
- **きっかけ**: 直後フィードバック — 正面図の四隅に穴が2重に描かれ、「M4取付」等のラベルがかぶって読めない
- **ギャップ**: 素人でも気づく図面ミス（重複穴・重複ラベル・PCBラベル決め打ち）が発生していた
- **根本原因**: 指示不足＋手順の順序問題 — SVG生成後にClaudeが出力を品質確認するよう指示されていなかった。またスクリプトの `_resolve_hole_positions()` が center_dist 未指定時に同一座標の穴を num_holes 個追加するバグがあった
- **変更内容**:
  - SKILL.md: Stage 2 ワークフローに「Claude 自己QC（必須）」ステップを追加。`⚠️ WARN:` 0件確認・フィーチャー数整合・重複チェックを必須化
  - SKILL.md: ユーザー案内文に「おかしいな」と気づくためのNG例リスト（素人向け）を追加
  - stage2_svg_views.py: `_resolve_hole_positions()` の bottom face フォールバック修正 — center_dist 未指定かつ num_holes≥2 の場合、同一座標リピートではなく幅方向均等配置に変更し `⚠️ WARN:` を出力
  - stage2_svg_views.py: `draw_bottom()` の PCB ラベルを "DHT22" 決め打ちから `internal_components[].name` の動的取得に変更

## 2026-03-07: Stage 2 SVG図面にインターフェース（穴・開口）描画要件を追加
- **きっかけ**: 直後フィードバック（DHT22センサーケース設計時）
- **ギャップ**: requirements.json に5種類のインターフェース（PG7穴、LED穴、壁取付穴、ベント穴、M3インサート穴）を定義したが、SVG図面にはただの直方体3面図しか出力されず、穴・開口が一切描画されなかった
- **根本原因**: 指示不足＋参照情報不足 — SKILL.md の Stage 2 セクションに interfaces 配列を描画する設計要件が記載されておらず、スクリプトも interfaces をパースしない構造だった
- **変更内容**:
  - SKILL.md: Stage 2 に「インターフェース描画」サブセクション追加（描画ルール、extract_dims()設計指針、等角図での簡易表現）
  - SKILL.md: ユーザーへの案内文の確認ポイントを4項目に拡充
  - stage2_svg_views.py: extract_dims() を全面リファクタし interfaces 配列をパースする機能を追加
  - stage2_svg_views.py: _classify_face() / _resolve_hole_positions() / _make_label() を新設。position文字列からヒューリスティックに描画面と座標を算出
  - stage2_svg_views.py: _draw_features_on_view() ヘルパーで各ビューにフィーチャー（実線円＋中心線＋ラベル）を描画。隠れ線投影にも対応
  - stage2_svg_views.py: 上面図 → 底面図に変更（底面にフィーチャーがある場合）。背面取付穴も底面図上に投影表示
  - stage2_svg_views.py: 等角図にフィーチャーの中心マーカー＋ラベルを表示（背面は非表示）
  - DHT22 requirements.json で検証: 12フィーチャー（PG7×2, VENT×1, LED×1, M3 ins.×4, M4取付×4）すべて描画成功

## 2026-03-07: Stage 2 正投影図法準拠の穴投影を実装 (v3)
- **きっかけ**: 直後フィードバック — 正面図の円穴が側面図でも円で描かれていた
- **ギャップ**: 図面のルールとして、穴軸⊥視線の場合は「2本の平行破線＋中心線」で描くべきところ、全ビューで円描画していた
- **根本原因**: 指示不足 — 正投影図法のルール（穴軸と視線の関係）がスクリプトに実装されていなかった
- **変更内容**:
  - SKILL.md: 描画ルールを「穴軸∥視線→円、軸⊥視線→2本破線+中心線」に書き直し、ビュー×面の投影対応表を追加
  - stage2_svg_views.py: SVGBuilder に feature_side_h() / feature_side_v() メソッドを追加（2本平行破線＋一点鎖線中心線を描画）
  - stage2_svg_views.py: 汎用の _draw_features_on_view() を廃止し、各 draw_front/draw_side/draw_bottom 内で穴軸と視線の関係に基づいて描画方法を分岐
  - stage2_svg_views.py: 中心線クロスを一点鎖線パターン(8,3,2,3)に変更
  - DHT22 requirements.json で検証: 実線円8個、隠れ円4個、平行破線24組、中心線64本 — 全投影が正しいことを確認
