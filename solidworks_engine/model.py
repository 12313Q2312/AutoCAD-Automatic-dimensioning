"""Strict, deterministic ModelPlan v1 for four limited mechanical part families.

No AI inference, CAD COM invocation, macro generation, network, or filesystem writes.
All model dimensions are in millimetres. The future SolidWorks adapter must
convert lengths to metres at its own boundary.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

SCHEMA_VERSION = "1.0"
PART_LABELS = {
    "rectangular_plate": "矩形板",
    "mounting_plate": "四孔安装板",
    "cylinder": "圆柱",
    "bushing": "轴套",
}
FIELD_LABELS = {
    "length_mm": "长度", "width_mm": "宽度", "thickness_mm": "厚度",
    "hole_diameter_mm": "孔径", "pitch_x_mm": "X方向孔距",
    "pitch_y_mm": "Y方向孔距", "diameter_mm": "直径",
    "height_mm": "高度", "outer_diameter_mm": "外径",
    "inner_diameter_mm": "内径",
}
PART_FIELDS = {
    "rectangular_plate": ("length_mm", "width_mm", "thickness_mm"),
    "mounting_plate": (
        "length_mm", "width_mm", "thickness_mm",
        "hole_diameter_mm", "pitch_x_mm", "pitch_y_mm",
    ),
    "cylinder": ("diameter_mm", "height_mm"),
    "bushing": ("outer_diameter_mm", "inner_diameter_mm", "height_mm"),
}
MIN_MM = 0.1
MAX_MM = 2000.0


class ModelPlanError(ValueError):
    def __init__(self, message: str, field: str = ""):
        super().__init__(message)
        self.field = field


def _dimension(params: dict, key: str) -> float:
    if key not in params:
        raise ModelPlanError(f"缺少必要尺寸：{FIELD_LABELS[key]}（mm）", key)
    raw = params[key]
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ModelPlanError(f"{FIELD_LABELS[key]}必须是数字", key)
    number = float(raw)
    if not isfinite(number) or number < MIN_MM or number > MAX_MM:
        raise ModelPlanError(
            f"{FIELD_LABELS[key]}必须在 {MIN_MM:g} 至 {MAX_MM:g} mm 之间", key
        )
    return round(number, 6)


def plan_from_parameters(part_type: str, parameters: dict[str, Any]) -> dict:
    """Build a strictly bounded CAD-independent feature plan."""
    if part_type not in PART_FIELDS:
        raise ModelPlanError("暂不支持该零件类型", "part_type")
    if not isinstance(parameters, dict):
        raise ModelPlanError("参数必须是对象", "parameters")
    required = PART_FIELDS[part_type]
    extra = sorted(set(parameters) - set(required))
    if extra:
        raise ModelPlanError("包含不支持的参数：" + ", ".join(extra), "parameters")
    p = {name: _dimension(parameters, name) for name in required}
    ops = []
    if part_type in ("rectangular_plate", "mounting_plate"):
        length, width, thickness = p["length_mm"], p["width_mm"], p["thickness_mm"]
        ops.append({
            "id": "base", "operation": "extrude", "sketch": {
                "type": "rectangle", "center_mm": [0, 0],
                "length_mm": length, "width_mm": width,
            }, "depth_mm": thickness,
        })
        if part_type == "mounting_plate":
            diameter, px, py = (
                p["hole_diameter_mm"], p["pitch_x_mm"], p["pitch_y_mm"]
            )
            if px <= diameter + 1:
                raise ModelPlanError("X方向孔距过小，通孔重叠或间隙不足", "pitch_x_mm")
            if py <= diameter + 1:
                raise ModelPlanError("Y方向孔距过小，通孔重叠或间隙不足", "pitch_y_mm")
            if (length - px) / 2 < diameter / 2 + 1:
                raise ModelPlanError("X方向孔边距离板边不足1 mm", "pitch_x_mm")
            if (width - py) / 2 < diameter / 2 + 1:
                raise ModelPlanError("Y方向孔边距离板边不足1 mm", "pitch_y_mm")
            centers = [[x, y] for y in (-py / 2, py / 2) for x in (-px / 2, px / 2)]
            ops.append({
                "id": "through_holes", "operation": "cut_through",
                "sketch": {"type": "circles", "diameter_mm": diameter,
                           "centers_mm": centers},
                "through_all": True,
            })
        bounds = [length, width, thickness]
    elif part_type == "cylinder":
        ops.append({
            "id": "base", "operation": "extrude",
            "sketch": {"type": "circle", "diameter_mm": p["diameter_mm"],
                       "center_mm": [0, 0]},
            "depth_mm": p["height_mm"],
        })
        bounds = [p["diameter_mm"], p["diameter_mm"], p["height_mm"]]
    else:
        wall = (p["outer_diameter_mm"] - p["inner_diameter_mm"]) / 2
        if wall < 1:
            raise ModelPlanError("轴套单侧壁厚不能小于1 mm", "inner_diameter_mm")
        ops.append({
            "id": "base", "operation": "extrude",
            "sketch": {
                "type": "annulus", "center_mm": [0, 0],
                "outer_diameter_mm": p["outer_diameter_mm"],
                "inner_diameter_mm": p["inner_diameter_mm"],
            },
            "depth_mm": p["height_mm"],
        })
        bounds = [p["outer_diameter_mm"], p["outer_diameter_mm"], p["height_mm"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "part_type": part_type,
        "part_label": PART_LABELS[part_type],
        "units": "mm",
        "parameters": p,
        "coordinate_system": "XY平面居中，Z正向拉伸",
        "features": ops,
        "bounding_box_mm": bounds,
    }


def validate_plan(plan: dict) -> dict:
    """Rebuild plan from parameters to reject untrusted feature injection."""
    if not isinstance(plan, dict) or plan.get("schema_version") != SCHEMA_VERSION:
        raise ModelPlanError("ModelPlan schema版本不支持", "schema_version")
    rebuilt = plan_from_parameters(plan.get("part_type"), plan.get("parameters"))
    if plan != rebuilt:
        raise ModelPlanError("ModelPlan内容与参数生成的特征不一致", "features")
    return {
        "valid": True, "schema_version": SCHEMA_VERSION, "units": "mm",
        "part_type": plan["part_type"], "feature_count": len(plan["features"]),
        "checks": ["尺寸范围", "零件参数完整", "特征顺序", "几何约束"],
        "boundary": "离线计划检查通过；SolidWorks真实建模未执行",
    }


def simulate(plan: dict) -> dict:
    """Dry-run feature sequence, never create a native CAD file."""
    report = validate_plan(plan)
    return {
        "status": "simulated", "backend": "mock_no_cad",
        "features": [f["id"] for f in plan["features"]],
        "feature_count": report["feature_count"],
        "native_cad_generated": False,
        "message": "已验证特征序列；未连接SolidWorks，未生成SLDPRT或STEP。",
    }
