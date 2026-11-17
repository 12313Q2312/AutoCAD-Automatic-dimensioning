"""Canonical, CAD-independent four-hole geometry for DraftPilot v2."""
from itertools import combinations
from math import hypot, isfinite

from .model import FIELD_LABELS, ModelPlanError, PART_FIELDS, plan_from_parameters

FIELDS = PART_FIELDS["mounting_plate"]
BASE_FIELDS = FIELDS[:3]
HOLES = ("top_left", "top_right", "bottom_left", "bottom_right")
HOLE_LABELS = dict(zip(HOLES, ("左上孔", "右上孔", "左下孔", "右下孔")))
HOLE_GROUPS = {
    **{hole: (hole,) for hole in HOLES},
    "left": ("top_left", "bottom_left"),
    "right": ("top_right", "bottom_right"),
    "top": ("top_left", "top_right"),
    "bottom": ("bottom_left", "bottom_right"),
}
HOLE_LABELS.update(left="左边两个孔", right="右边两个孔", top="上排两个孔", bottom="下排两个孔")
PITCH_FIELDS = FIELDS[4:]
GAP_MM = 1.0


def number(value, field, minimum, maximum):
    if type(value) not in (float, int) or not minimum <= value <= maximum or not isfinite(value):
        raise ModelPlanError(f"{FIELD_LABELS.get(field, field)}超出允许范围或不是有限数字", field)
    return round(float(value), 6)


def build_plate(parameters, holes):
    """Build the entire plan from an editable rectangle and four identified holes."""
    if not isinstance(parameters, dict) or set(parameters) != set(BASE_FIELDS):
        raise ModelPlanError("请提供长、宽、厚三个板尺寸", "parameters")
    normalized = {field: number(parameters[field], field, 0.1, 2000) for field in BASE_FIELDS}
    base = plan_from_parameters("rectangular_plate", normalized)
    length, width, thickness = base["bounding_box_mm"]
    if not isinstance(holes, list) or len(holes) != 4:
        raise ModelPlanError("安装板必须有四个通孔", "holes")

    by_id = {}
    for hole in holes:
        if not isinstance(hole, dict) or set(hole) != {"id", "x_mm", "y_mm", "diameter_mm"}:
            raise ModelPlanError("通孔数据无效", "holes")
        ident = hole["id"]
        if not isinstance(ident, str) or ident not in HOLES or ident in by_id:
            raise ModelPlanError("通孔标识缺失、无效或重复", "holes")
        x, y = (number(hole[k], k, -2000, 2000) for k in ("x_mm", "y_mm"))
        diameter = number(hole["diameter_mm"], "hole_diameter_mm", 0.1, 2000)
        if length / 2 - abs(x) < diameter / 2 + GAP_MM or width / 2 - abs(y) < diameter / 2 + GAP_MM:
            raise ModelPlanError(f"{HOLE_LABELS[ident]}的孔边距板边须至少 1 mm", "holes")
        # A hole keeps its corner identity throughout an editing session.
        side, horizontal = ident.split("_")
        if (x >= 0 if horizontal == "left" else x <= 0) or (y <= 0 if side == "top" else y >= 0):
            raise ModelPlanError(f"{HOLE_LABELS[ident]}必须留在对应的板面象限", "holes")
        by_id[ident] = {"id": ident, "x_mm": x, "y_mm": y, "diameter_mm": diameter}

    ordered = [by_id[ident] for ident in HOLES]
    for first, second in combinations(ordered, 2):
        separation = hypot(first["x_mm"] - second["x_mm"], first["y_mm"] - second["y_mm"])
        if separation - (first["diameter_mm"] + second["diameter_mm"]) / 2 <= GAP_MM:
            raise ModelPlanError("通孔重叠或孔边间隙不超过 1 mm", "holes")

    return {
        **base,
        "schema_version": "2.0",
        "part_type": "mounting_plate",
        "part_label": "四孔安装板",
        "features": [
            base["features"][0],
            {"id": "through_holes", "operation": "cut_through", "through_all": True,
             "sketch": {"type": "individual_circles", "holes": ordered}},
        ],
        "bounding_box_mm": [length, width, thickness],
    }


def from_symmetric_parameters(parameters):
    # Reuse the first version's units, range checks and symmetric geometry.
    plan = plan_from_parameters("mounting_plate", parameters)
    dims = plan["parameters"]
    px, py = (dims[field] / 2 for field in PITCH_FIELDS)
    centers = ((-px, py), (px, py), (-px, -py), (px, -py))
    holes = [{"id": ident, "x_mm": x, "y_mm": y, "diameter_mm": dims["hole_diameter_mm"]}
             for ident, (x, y) in zip(HOLES, centers)]
    return build_plate({key: dims[key] for key in BASE_FIELDS}, holes)


def validate_plate(plan):
    if not isinstance(plan, dict):
        raise ModelPlanError("安装板计划无效", "plan")
    try:
        rebuilt = build_plate(plan["parameters"], plan["features"][1]["sketch"]["holes"])
    except (KeyError, TypeError, IndexError) as exc:
        raise ModelPlanError("安装板计划结构无效", "plan") from exc
    if plan != rebuilt:
        raise ModelPlanError("安装板计划与校验结果不一致", "plan")
    return rebuilt
