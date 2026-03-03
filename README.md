# Text-to-CAD Skill セットアップガイド

テキストの製品アイデアから CAD STEP データを段階的に生成する Agent Skill です。

## API キーは不要です ✅

| サービス | 用途 | 状態 |
|---------|------|------|
| Google AI Studio | 見取り図生成 (Stage 2) | ⛔ 廃止 → Python SVG に置き換え済み |
| Tripo API | 3Dメッシュ変換 (Stage 4a) | ⚠️ 未実装（将来対応予定）|
| CadQuery | STEP 生成 (Stage 4b) | ✅ ローカル実行・API キー不要 |

**現在のワークフローで必要な外部サービスはありません。**
唯一のセットアップは `pip install cadquery`（Stage 4 のみ）です。

---

## セットアップ方法

### A. Cowork（Claude デスクトップアプリ）

1. `.skill` ファイルをダブルクリックしてインストール
2. チャットで「基板ケースを設計して」等と話しかけると Stage 1 開始
3. Stage 4 を使う前に一度だけ実行:
   ```bash
   pip install cadquery
   ```

---

### B. Claude Code CLI

```bash
# Skill ディレクトリを配置
cp -r text-to-cad/ ~/.claude/skills/

# CadQuery をインストール（Stage 4 のみ必要）
pip install cadquery
```

チャットで `text-to-cad` スキルが自動認識されます。

---

### C. Cursor / Windsurf / Zed などの AI 統合エディター

Cursor 等は Skill ファイルをネイティブにサポートしていませんが、
以下の方法でほぼ同等の動作を再現できます。

#### 方法 C-1: `.cursor/rules/` に SKILL.md を配置（推奨）

`.cursor/rules/` は Cursor AI への**指示書**、`scripts/` は**実行ツール**です。
この 2 つは役割が異なるため、両方をプロジェクトに配置します。

**① ディレクトリ構成**

```
my-project/
├── .cursor/
│   └── rules/
│       └── text-to-cad.mdc    ← AI 指示書（SKILL.md の内容）
│
├── text-to-cad/               ← スキルのファイル一式をここにコピー
│   └── scripts/
│       ├── stage2_svg_views.py
│       ├── stage4b_generate_step.py
│       └── validate_params.py
│
└── （自分のプロジェクトファイル）
```

**② セットアップコマンド**

```bash
# プロジェクトルートで実行
mkdir -p .cursor/rules

# AI 指示書を配置
cp /path/to/text-to-cad/SKILL.md .cursor/rules/text-to-cad.mdc

# スクリプト一式をプロジェクト内にコピー
cp -r /path/to/text-to-cad ./text-to-cad
```

**③ 各ファイルの使い方**

| ファイル | 誰が使うか | 方法 |
|---------|-----------|------|
| `.mdc` (SKILL.md) | Cursor AI | 自動読み込み・チャットに反映 |
| `stage2_svg_views.py` | ユーザー（ターミナル） | `python text-to-cad/scripts/stage2_svg_views.py --req requirements.json --out renders/` |
| `stage4b_generate_step.py` | ユーザー（ターミナル） | `python text-to-cad/scripts/stage4b_generate_step.py --params parameters.json --out step/` |
| `validate_params.py` | Cursor AI または ユーザー | `@text-to-cad/scripts/validate_params.py` で AI に参照させる、またはターミナルから実行 |

Stage 1〜3 はチャットだけで完結します。Stage 2（SVG）と Stage 4（STEP）はターミナルでスクリプトを実行します。

> **他エディターの場合:**
> - Windsurf: `.windsurf/rules/text-to-cad.md` に配置
> - Zed: `.zed/rules/text-to-cad.md` に配置
> - GitHub Copilot: `.github/copilot-instructions.md` に追記
>
> スクリプトは同様にプロジェクト内の `text-to-cad/scripts/` に置いてください。

#### 方法 C-2: スクリプトを直接実行（チャット不要な場合）

JSON ファイルが手元にある場合、スクリプトを単体で実行できます。

```bash
# Stage 2: 3面図（SVG）生成
python text-to-cad/scripts/stage2_svg_views.py --req requirements.json --out renders/

# Stage 4: STEP ファイル生成
python text-to-cad/scripts/stage4b_generate_step.py --params parameters.json --out step/ --validate --preview
```

AI チャットで Stage 1〜3 の対話を進め、生成された JSON を上記スクリプトに渡します。

#### 方法 C-3: claude CLI をターミナルで使う（最もシンプル）

Cursor の組み込みターミナルから Claude Code CLI を呼び出す方法です。

```bash
# インストール（未インストールの場合）
npm install -g @anthropic-ai/claude-code

# Skill を登録
cp -r text-to-cad/ ~/.claude/skills/

# Cursor のターミナルで実行
claude "基板ケースを設計して"
```

Cursor の AI と claude CLI を併用することで、コード補完と CAD 生成を同時に活用できます。

---

### D. claude.ai Web（Claude プロジェクト）

1. claude.ai でプロジェクトを新規作成
2. **プロジェクト指示** に `SKILL.md` の内容を貼り付け
3. **ナレッジベース** に以下をアップロード:
   - `references/cadquery_patterns.md`
   - `references/parameters_schema.md`
   - `references/bom_schema.md`
   - `scripts/` 内の全 `.py` ファイル
4. チャットで「基板ケースを設計して」等と話しかけると Stage 1 開始

> Stage 4 の STEP 生成はローカル実行が必要なため、Web のみの環境では Stage 3（BOM）まで対応となります。

---

## Python 環境について

| ステージ | 依存パッケージ | Python バージョン |
|---------|--------------|----------------|
| Stage 1, 2, 3 | **なし**（標準ライブラリのみ） | 3.8 以上 |
| Stage 4 (STEP 生成) | `cadquery` | 3.8 〜 3.11 推奨 |

```bash
# CadQuery インストール（Windows / macOS / Linux 共通）
pip install cadquery

# 確認
python -c "import cadquery; print('OK')"
```

> ⚠️ CadQuery は約 400MB と大容量です。初回インストールに数分かかります。
> ⚠️ Python 3.12 は一部の CadQuery バージョンで非対応の場合があります。3.11 を推奨します。

---

## ファイル構成

```
text-to-cad/
├── SKILL.md                     # Skill 本体（プロジェクト指示に使用）
├── README.md                    # このファイル
├── scripts/
│   ├── stage1_requirements.py   # 要件構造化ヘルパー
│   ├── stage2_svg_views.py      # ✅ 3面図 SVG 生成（API 不要）
│   ├── stage2_nano_banana.py    # （旧）Gemini Image API クライアント（非推奨）
│   ├── stage3_bom_generator.py  # BOM 生成・カテゴリ分類
│   ├── stage4b_generate_step.py # CadQuery STEP 生成テンプレート
│   └── validate_params.py       # パラメータ整合性チェック
├── references/
│   ├── cadquery_patterns.md     # CadQuery 検証済みパターン集
│   ├── parameters_schema.md     # parameters.json スキーマ
│   └── bom_schema.md            # BOM スキーマ
├── assets/prompt_templates/     # 見取り図生成プロンプト
├── examples/sample_box_enclosure/  # サンプル（パラメータ + STEP + プレビュー）
└── evals/evals.json             # テストケース
```

---

## 対応する設計物

✅ 箱型ケース・筐体（基板ケース、センサーケース）
✅ ブラケット・マウント（モーターマウント、取付台）
✅ カバー・蓋・パネル
⚠️ 板金部品（簡易な曲げのみ）
❌ 自由曲面・意匠面、歯車・カム機構
