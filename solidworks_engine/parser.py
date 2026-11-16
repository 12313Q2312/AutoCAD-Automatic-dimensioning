"""Predictable Chinese size extraction, explicitly NOT an arbitrary NLP model."""
import re
from .model import ModelPlanError, PART_FIELDS, FIELD_LABELS, plan_from_parameters

NUMBER = r"(-?(?:\d+(?:\.\d+)?|\.\d+))\s*(毫米|mm|厘米|cm)"
FLAGS = re.IGNORECASE
PATTERNS = {
    "length_mm": [r"(?:长度|长)"],
    "width_mm": [r"(?:宽度|宽)"],
    "thickness_mm": [r"(?:厚度|厚)"],
    "hole_diameter_mm": [r"(?:孔直径|孔径|直径)"],
    "pitch_x_mm": [
        r"(?:X方向孔距|X方向间距|横向孔距|横向间距|长边方向(?:两两)?间隔|长边方向孔距)",
    ],
    "pitch_y_mm": [
        r"(?:Y方向孔距|Y方向间距|纵向孔距|纵向间距|宽边方向(?:两两)?间隔|宽边方向孔距)",
    ],
    "diameter_mm": [r"(?:直径|径向尺寸)"],
    "height_mm": [r"(?:高度|高|长度|长)"],
    "outer_diameter_mm": [r"(?:外径|外直径)"],
    "inner_diameter_mm": [r"(?:内径|内直径)"],
}


def _kind(text: str) -> str:
    if any(word in text for word in ("轴套", "套筒", "衬套")):
        return "bushing"
    if any(word in text for word in ("圆柱", "圆柱体", "实心圆棒")):
        return "cylinder"
    if ("孔" in text and any(w in text for w in ("板", "支架"))) or "四孔" in text:
        if not ("四" in text or "4" in text) or "孔" not in text:
            raise ModelPlanError("首版只支持明确指定四个贯穿孔的矩形板", "part_type")
        return "mounting_plate"
    if any(w in text for w in ("板", "平板", "矩形")):
        return "rectangular_plate"
    raise ModelPlanError("暂只支持矩形板、四孔安装板、圆柱和轴套", "part_type")


def _find_dimension(text: str, key: str):
    for label in PATTERNS[key]:
        pattern = rf"{label}\s*(?:为|是|等于|[:：=])?\s*{NUMBER}"
        matched = re.search(pattern, text, FLAGS)
        if matched:
            number, unit = matched.groups()
            value = float(number)
            return value * (10 if unit.lower() in ("厘米", "cm") else 1)
    return None


def parse_description(text: str) -> dict:
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise ModelPlanError("请输入1至1000字的明确中文建模描述", "description")
    part_type = _kind(text.strip())
    missing = []
    params = {}
    for field in PART_FIELDS[part_type]:
        value = _find_dimension(text, field)
        if value is None:
            missing.append(FIELD_LABELS[field])
        else:
            params[field] = value
    if missing:
        raise ModelPlanError("请补充必要尺寸及单位：" + "、".join(missing), "description")
    return plan_from_parameters(part_type, params)
