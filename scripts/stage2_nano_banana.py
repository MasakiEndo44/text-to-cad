#!/usr/bin/env python3
"""
Stage 2: Nano Banana (Gemini 2.5 Flash Image) API 呼び出し

要件 JSON からプロンプトを自動生成し、多角度の 2D レンダリングを生成する。
Google AI Studio API を使用（500 req/日の無料枠）。

環境変数:
  GOOGLE_API_KEY: Google AI Studio の API キー
"""
import os
import sys
import json
import base64
from pathlib import Path

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("❌ google-genai パッケージがありません。インストール:")
    print("   pip install google-genai --break-system-packages")
    sys.exit(1)


# ── 設定 ──
MODEL_ID = "gemini-2.0-flash-exp"  # Nano Banana 対応モデル
VIEWS = [
    {"name": "front_view",     "angle": "front view, straight-on",   "desc": "正面図"},
    {"name": "side_view",      "angle": "side view, 90 degrees",     "desc": "側面図"},
    {"name": "top_view",       "angle": "top-down view, bird's eye", "desc": "上面図"},
    {"name": "isometric_view", "angle": "isometric view, 45 degree angle, slightly above", "desc": "45°俯瞰図"},
    {"name": "exploded_view",  "angle": "exploded view showing all parts separated with assembly lines", "desc": "分解図"},
]


def init_client():
    """Gemini クライアントを初期化"""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("❌ 環境変数 GOOGLE_API_KEY が設定されていません")
        print("   export GOOGLE_API_KEY='your-key-here'")
        sys.exit(1)
    return genai.Client(api_key=api_key)


def build_prompt(requirements: dict, view: dict, sketch_path: str = None) -> str:
    """要件 JSON + ビュー設定からプロンプトを自動生成"""
    dims = requirements.get("dimensions", {}).get("outer", {})
    parts = requirements.get("parts_initial", [])
    mfg = requirements.get("manufacturing", {})

    # 部品リスト
    feature_list = ", ".join(p.get("name", "") for p in parts if p.get("name"))

    # 材質
    materials = set()
    for p in parts:
        if p.get("material"):
            materials.add(p["material"])
    material_str = ", ".join(materials) if materials else "plastic"

    prompt = (
        f"Generate a {view['angle']} of a {requirements.get('product_name', 'product')}. "
        f"Description: {requirements.get('description', '')}. "
        f"Approximate dimensions: {dims.get('width_mm', '?')}mm wide × "
        f"{dims.get('depth_mm', '?')}mm deep × {dims.get('height_mm', '?')}mm tall. "
        f"Style: clean industrial design render, white background, studio lighting, "
        f"no text overlays, no watermarks, professional product photography. "
    )

    if feature_list:
        prompt += f"Key features: {feature_list}. "

    prompt += f"Material appearance: {material_str}. "

    if mfg.get("method"):
        prompt += f"Manufacturing: {mfg['method']}. "

    if sketch_path:
        prompt += "Recreate the proportions and layout shown in the attached sketch. "

    return prompt


def generate_view(client, prompt: str, sketch_path: str = None,
                  output_path: str = "output.png") -> str:
    """1枚の見取り図を生成"""
    contents = []

    # スケッチがある場合は image-to-image
    if sketch_path and os.path.exists(sketch_path):
        with open(sketch_path, "rb") as f:
            sketch_data = f.read()
        contents.append(types.Part.from_bytes(
            data=sketch_data,
            mime_type="image/png"
        ))

    contents.append(prompt)

    response = client.models.generate_content(
        model=MODEL_ID,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        )
    )

    # レスポンスから画像を抽出
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.mime_type.startswith("image/"):
            img_data = part.inline_data.data
            if isinstance(img_data, str):
                img_data = base64.b64decode(img_data)
            with open(output_path, "wb") as f:
                f.write(img_data)
            print(f"  ✅ {output_path} ({len(img_data)} bytes)")
            return output_path

    print(f"  ⚠️ 画像が返されませんでした")
    return None


def generate_all_views(requirements: dict, output_dir: str = "renders",
                       sketch_path: str = None, views: list = None):
    """全角度の見取り図を一括生成"""
    client = init_client()
    os.makedirs(output_dir, exist_ok=True)

    if views is None:
        views = VIEWS

    results = []
    for i, view in enumerate(views):
        print(f"\n🎨 [{i+1}/{len(views)}] {view['desc']} ({view['name']})...")
        prompt = build_prompt(requirements, view, sketch_path)
        out_path = os.path.join(output_dir, f"{view['name']}.png")

        result = generate_view(client, prompt, sketch_path, out_path)
        results.append({
            "view": view["name"],
            "description": view["desc"],
            "path": result,
            "prompt_used": prompt[:200] + "..."
        })

    # メタデータ保存
    meta_path = os.path.join(output_dir, "render_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 全{len(views)}ビュー生成完了 → {output_dir}/")
    return results


if __name__ == "__main__":
    # テスト: 単一ビュー生成
    test_req = {
        "product_name": "センサーケース",
        "description": "防水センサーを収納するABSケース",
        "dimensions": {"outer": {"width_mm": 120, "height_mm": 40, "depth_mm": 80}},
        "parts_initial": [
            {"name": "ボディ", "material": "ABS"},
            {"name": "蓋", "material": "ABS"},
        ],
        "manufacturing": {"method": "3Dプリント(FDM)"}
    }

    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        generate_all_views(test_req)
    else:
        client = init_client()
        prompt = build_prompt(test_req, VIEWS[3])  # isometric
        print(f"プロンプト: {prompt[:200]}...")
        generate_view(client, prompt, output_path="test_isometric.png")
