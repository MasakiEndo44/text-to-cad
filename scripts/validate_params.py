#!/usr/bin/env python3
"""
parameters.json バリデーション & 変更差分レポート

- recommended_range 逸脱の警告
- critical パラメータの変更検知
- 寸法間の整合性チェック
"""
import json
import sys
import os
from copy import deepcopy


def load_params(path: str = "parameters.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_params(params: dict) -> list[dict]:
    """全パラメータをチェックし、警告リストを返す"""
    warnings = []

    for category, items in params.items():
        if category.startswith("_"):
            continue
        if not isinstance(items, dict):
            continue

        for key, spec in items.items():
            if not isinstance(spec, dict) or "value" not in spec:
                continue

            val = spec["value"]
            note = spec.get("note", key)

            # recommended_range チェック
            rng = spec.get("recommended_range")
            if rng and len(rng) == 2:
                lo, hi = rng
                if val < lo or val > hi:
                    warnings.append({
                        "level": "WARNING",
                        "category": category,
                        "key": key,
                        "message": f"{note}: 値 {val} が推奨範囲 [{lo}, {hi}] の外です",
                        "value": val,
                        "range": rng
                    })

            # ゼロ・負の値チェック
            if val <= 0:
                warnings.append({
                    "level": "ERROR",
                    "category": category,
                    "key": key,
                    "message": f"{note}: 値 {val} が 0 以下です",
                    "value": val
                })

    # 寸法整合性チェック
    warnings.extend(_check_dimensional_consistency(params))

    return warnings


def _check_dimensional_consistency(params: dict) -> list[dict]:
    """寸法間の整合性をチェック"""
    warnings = []

    def _get(cat, key):
        try:
            return params[cat][key]["value"]
        except (KeyError, TypeError):
            return None

    # 穴径 < 座ぐり径
    hole_d = _get("mounting_interface", "bolt_hole_diameter")
    cb_d = _get("mounting_interface", "counterbore_diameter")
    if hole_d and cb_d and hole_d >= cb_d:
        warnings.append({
            "level": "ERROR",
            "category": "mounting_interface",
            "key": "bolt_hole_diameter / counterbore_diameter",
            "message": f"穴径 ({hole_d}mm) ≥ 座ぐり径 ({cb_d}mm) です。座ぐり径は穴径より大きくなければなりません"
        })

    # 穴ピッチが外形内に収まるか
    for axis, dim_key in [("x", "width"), ("y", "depth")]:
        pitch = _get("mounting_interface", f"bolt_hole_pitch_{axis}")
        envelope = _get("outer_envelope", dim_key)
        if pitch and envelope and pitch >= envelope:
            warnings.append({
                "level": "ERROR",
                "category": "mounting_interface",
                "key": f"bolt_hole_pitch_{axis}",
                "message": f"穴ピッチ{axis.upper()} ({pitch}mm) が外形{dim_key} ({envelope}mm) を超えています"
            })

    # 基板が内寸に収まるか
    wall = _get("global", "wall_thickness")
    if wall:
        for pcb_key, env_key in [("pcb_width", "width"), ("pcb_depth", "depth")]:
            pcb_dim = _get("internal_cavity", pcb_key)
            env_dim = _get("outer_envelope", env_key)
            if pcb_dim and env_dim:
                inner = env_dim - 2 * wall
                if pcb_dim > inner:
                    warnings.append({
                        "level": "ERROR",
                        "category": "internal_cavity",
                        "key": pcb_key,
                        "message": f"基板{pcb_key} ({pcb_dim}mm) が内寸 ({inner}mm = 外形{env_dim} - 肉厚{wall}×2) を超えています"
                    })

    # フィレットR が辺長の 1/3 を超えていないか
    fillet_r = _get("global", "fillet_radius")
    if fillet_r:
        height = _get("outer_envelope", "height")
        if height and fillet_r > height / 3:
            warnings.append({
                "level": "WARNING",
                "category": "global",
                "key": "fillet_radius",
                "message": f"フィレットR ({fillet_r}mm) が高さ ({height}mm) の1/3を超えています。CadQuery でエラーになる可能性があります"
            })

    return warnings


def diff_report(old_params: dict, new_params: dict) -> str:
    """2つの parameters.json の差分レポートを生成"""
    lines = ["# パラメータ変更レポート", ""]
    changes = []

    for category, items in new_params.items():
        if category.startswith("_") or not isinstance(items, dict):
            continue

        old_items = old_params.get(category, {})
        for key, new_spec in items.items():
            if not isinstance(new_spec, dict) or "value" not in new_spec:
                continue

            old_spec = old_items.get(key, {})
            old_val = old_spec.get("value")
            new_val = new_spec["value"]

            if old_val is not None and old_val != new_val:
                is_critical = new_spec.get("critical", False)
                note = new_spec.get("note", key)
                changes.append({
                    "category": category,
                    "key": key,
                    "note": note,
                    "old": old_val,
                    "new": new_val,
                    "critical": is_critical
                })

    if not changes:
        return "変更なし"

    # critical な変更を先に表示
    critical_changes = [c for c in changes if c["critical"]]
    other_changes = [c for c in changes if not c["critical"]]

    if critical_changes:
        lines.append("## ⚠️ Critical パラメータの変更（相手部品との整合確認が必要）")
        lines.append("")
        for c in critical_changes:
            lines.append(f"- **{c['note']}** (`{c['category']}.{c['key']}`): "
                         f"{c['old']} → {c['new']} {c.get('unit', 'mm')}")
        lines.append("")

    if other_changes:
        lines.append("## その他の変更")
        lines.append("")
        for c in other_changes:
            lines.append(f"- {c['note']} (`{c['category']}.{c['key']}`): "
                         f"{c['old']} → {c['new']}")

    return "\n".join(lines)


def print_validation_result(warnings: list):
    """バリデーション結果を表示"""
    errors = [w for w in warnings if w["level"] == "ERROR"]
    warns = [w for w in warnings if w["level"] == "WARNING"]

    print("\n━━━ パラメータ バリデーション ━━━")
    if not warnings:
        print("  ✅ すべてのパラメータが正常です")
    else:
        for e in errors:
            print(f"  ❌ {e['message']}")
        for w in warns:
            print(f"  ⚠️ {w['message']}")
        print(f"\n  エラー: {len(errors)}, 警告: {len(warns)}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return len(errors) == 0  # エラーがなければ True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用法: python validate_params.py <parameters.json> [old_parameters.json]")
        sys.exit(1)

    params = load_params(sys.argv[1])
    warnings = validate_params(params)
    ok = print_validation_result(warnings)

    if len(sys.argv) >= 3:
        old_params = load_params(sys.argv[2])
        report = diff_report(old_params, params)
        print("\n" + report)

    sys.exit(0 if ok else 1)
