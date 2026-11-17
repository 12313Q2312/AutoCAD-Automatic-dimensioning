"""Validate a provider's proposals and apply one turn to a four-hole plate."""
from .model import FIELD_LABELS, ModelPlanError
from .plate_v2 import (
    BASE_FIELDS, FIELDS, HOLE_GROUPS, HOLE_LABELS, PITCH_FIELDS, build_plate,
    from_symmetric_parameters, number, validate_plate,
)
from .preview import render_svg

CHANGE_FIELDS = ("delta_x_mm", "delta_y_mm", "new_diameter_mm")
NUMBER_FIELDS = (*FIELDS, *CHANGE_FIELDS)
ACTIONS = ("dimensions", "hole_edit", "clarify", "unsupported")
SKETCH_VALUES = ("none", "four_corners", "unclear", "unsupported")
TURN_FIELDS = ("action", "hole", "sketch", *NUMBER_FIELDS)
QUESTIONS = {
    "length_mm": "板有多长？",
    "width_mm": "板有多宽？",
    "thickness_mm": "板有多厚？",
    "hole_diameter_mm": "四个孔的直径是多少？",
    "pitch_x_mm": "同一排两个孔的中心相距多少？",
    "pitch_y_mm": "上排和下排的孔中心相距多少？",
}


def validate_state(state):
    if state is None:
        return {}, None, None
    if not isinstance(state, dict) or set(state) != {"draft", "plan", "pending_hole"}:
        raise ModelPlanError("对话状态无效，请重新开始", "state")
    draft = state["draft"]
    if not isinstance(draft, dict) or not draft.keys() <= set(FIELDS):
        raise ModelPlanError("对话尺寸无效，请重新开始", "state")
    draft = {field: number(value, field, 0.1, 2000) for field, value in draft.items()}
    plan = validate_plate(state["plan"]) if state["plan"] is not None else None
    if plan is not None and draft:
        raise ModelPlanError("已生成的计划不能同时包含未完成尺寸", "state")
    if plan is None and len(draft) == len(FIELDS):
        raise ModelPlanError("对话状态已有完整尺寸，请重新开始", "state")
    pending_hole = state["pending_hole"]
    if pending_hole not in (*HOLE_GROUPS, None) or (pending_hole is not None and plan is None):
        raise ModelPlanError("待修改孔位无效，请重新开始", "state")
    return draft, plan, pending_hole


def _proposal(value, has_sketch):
    if not isinstance(value, dict) or set(value) != set(TURN_FIELDS):
        raise ModelPlanError("云端返回的指令结构无效，请重试", "proposal")
    action, hole, sketch = (value[key] for key in ("action", "hole", "sketch"))
    if (action not in ACTIONS or hole not in (*HOLE_GROUPS, None) or sketch not in SKETCH_VALUES
            or (sketch != "none") != has_sketch):
        raise ModelPlanError("云端返回的操作或草图状态无效，请重试", "proposal")
    dimensions = {field: number(value[field], field, 0.1, 2000)
                  for field in FIELDS if value[field] is not None}
    edit = {field: number(value[field], field, -2000, 2000)
            for field in CHANGE_FIELDS if value[field] is not None}
    if "new_diameter_mm" in edit:
        edit["new_diameter_mm"] = number(edit["new_diameter_mm"], "hole_diameter_mm", 0.1, 2000)
    if action == "dimensions" and dimensions and not edit and hole is None:
        return action, hole, sketch, dimensions
    if action == "hole_edit" and hole and not dimensions:
        return action, hole, sketch, edit
    if action in ("clarify", "unsupported") and not dimensions and not edit and hole is None:
        return action, hole, sketch, {}
    raise ModelPlanError("云端返回了不完整或冲突的操作，请重试", "proposal")


def _edit(plan, action, hole_id, changes):
    base = plan["parameters"].copy()
    holes = [hole.copy() for hole in plan["features"][1]["sketch"]["holes"]]
    if action == "hole_edit":
        for target in holes:
            if target["id"] not in HOLE_GROUPS[hole_id]:
                continue
            target["x_mm"] += changes.get("delta_x_mm", 0)
            target["y_mm"] += changes.get("delta_y_mm", 0)
            if "new_diameter_mm" in changes:
                target["diameter_mm"] = changes["new_diameter_mm"]
        return build_plate(base, holes), f"已更新{HOLE_LABELS[hole_id]}。"

    for key in BASE_FIELDS:
        if key in changes:
            base[key] = changes[key]
    if "hole_diameter_mm" in changes:
        for hole in holes:
            hole["diameter_mm"] = changes["hole_diameter_mm"]
    for pitch_field, coordinate in zip(PITCH_FIELDS, ("x_mm", "y_mm")):
        if pitch_field not in changes:
            continue
        values = {hole[coordinate] for hole in holes}
        if len(values) != 2 or min(values) != -max(values):
            raise ModelPlanError(
                f"{FIELD_LABELS[pitch_field]}涉及已单独调整的孔。请指定要移动哪个孔。", pitch_field,
            )
        half_pitch = changes[pitch_field] / 2
        for hole in holes:
            hole[coordinate] = half_pitch if hole[coordinate] > 0 else -half_pitch
    return build_plate(base, holes), "已更新指定尺寸。"


def apply_turn(draft, plan, proposal, has_sketch=False, pending_hole=None):
    action, hole, sketch, values = _proposal(proposal, has_sketch)
    if sketch in ("unclear", "unsupported"):
        return _result(draft, plan, "clarify", "请提供正对矩形板面、能看清四个角孔的草图。")
    if action == "unsupported":
        return _result(draft, plan, "clarify", "当前支持矩形四角通孔板。请描述这类板或指定一个角孔进行修改。")
    if action == "clarify":
        missing = next((key for key in FIELDS if key not in draft), None) if plan is None else None
        question = QUESTIONS[missing] if missing else "请说清要改哪个尺寸或哪个孔，以及具体数值和单位。"
        return _result(draft, plan, "clarify", question, pending_hole)
    if plan is not None:
        if action == "hole_edit" and not values:
            return _result(draft, plan, "clarify",
                           f"{HOLE_LABELS[hole]}要改为多大孔径，或者向哪个方向移动多少？", hole)
        updated, message = _edit(plan, action, hole, values)
        return _result({}, updated, "ready", message)
    if action == "hole_edit":
        return _result(draft, None, "clarify", "请先完成基础安装板，再指定要修改的孔。")
    draft = {**draft, **values}
    missing = next((key for key in FIELDS if key not in draft), None)
    if missing:
        return _result(draft, None, "clarify", QUESTIONS[missing])
    return _result({}, from_symmetric_parameters(draft), "ready", "已生成安装板预览，请核对尺寸。")


def _result(draft, plan, status, message, pending_hole=None):
    state = {"draft": draft, "plan": plan, "pending_hole": pending_hole}
    return {"status": status, "message": message, "state": state,
            "preview_svg": render_svg(plan) if plan is not None else None}
