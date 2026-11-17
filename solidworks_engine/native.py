"""Generate a native SolidWorks package in one isolated work directory."""
from io import BytesIO
from math import isclose
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile
import json
import logging
import os
import sys

from .plate_v2 import validate_plate

LOGGER = logging.getLogger(__name__)
NATIVE_LOCK = Lock()
DRAWING_EXTENSION = ".SLDDRW"
PART_EXTENSION = ".SLDPRT"
SOLID_BODY = 0
END_BLIND = 0
END_THROUGH_ALL = 1
START_SKETCH_PLANE = 0
SAVE_SILENT = 1
PDF_EXPORT = 1
PART_TEMPLATE = 8
DRAWING_TEMPLATE = 10
MM_PER_METRE = 1000
GEOMETRY_TOLERANCE_MM = 0.01
MAX_FILE_SIZE = 16 * 1024 * 1024
VIEW_SCALES = (10, 5, 2, 1, 0.5, 0.25, 0.2, 0.1, 0.05, 0.02, 0.01)
CORNER_NAMES = ("Upper left", "Upper right", "Lower left", "Lower right")


class NativeError(RuntimeError):
    """A message safe to surface after a CAD operation fails."""


def _require(condition, message):
    if not condition:
        raise NativeError(message)


def _near(first, second):
    return isclose(first, second, rel_tol=0, abs_tol=GEOMETRY_TOLERANCE_MM)


def _verify_geometry(part, plan):
    # For our planar body this is a screening check. Cylinder coordinates are
    # independently read from the actual solid faces rather than from the plan.
    box = part.GetPartBox(True)
    _require(box is not None and len(box) == 6, "SolidWorks 未返回有效的零件外形")
    expected_box = plan["bounding_box_mm"]
    dimensions = [(box[i + 3] - box[i]) * MM_PER_METRE for i in range(3)]
    _require(all(_near(actual, expected) for actual, expected in zip(dimensions, expected_box)),
             "SolidWorks 零件外形与已确认尺寸不一致")
    bodies = part.GetBodies2(SOLID_BODY, False)
    _require(bodies and len(bodies) == 1, "SolidWorks 结果应只包含一个实体")
    measured_holes = []
    for face in bodies[0].GetFaces():
        surface = face.GetSurface()
        if not surface.IsCylinder():
            continue
        x, y, _, axis_x, axis_y, axis_z, radius = surface.CylinderParams
        _require(abs(axis_x) < 1e-7 and abs(axis_y) < 1e-7 and abs(abs(axis_z) - 1) < 1e-7,
                 "SolidWorks 返回了方向不符的孔")
        measured_holes.append([x * MM_PER_METRE, y * MM_PER_METRE, radius * 2 * MM_PER_METRE])
    holes = plan["features"][1]["sketch"]["holes"]
    _require(len(measured_holes) == len(holes), "SolidWorks 实际孔数与计划不一致")
    ordered_measurements = []
    remaining = measured_holes.copy()
    for hole in holes:
        expected = [hole["x_mm"], hole["y_mm"], hole["diameter_mm"]]
        match = next((row for row in remaining if all(_near(a, b) for a, b in zip(row, expected))), None)
        _require(match is not None, "SolidWorks 实际孔位或孔径与计划不一致")
        remaining.remove(match)
        ordered_measurements.append(dict(zip(("x_mm", "y_mm", "diameter_mm"), match)))
    return {
        "approximate_bounds_mm": dimensions,
        "holes": ordered_measurements,
        "tolerance_mm": GEOMETRY_TOLERANCE_MM,
    }


def _template(sw, env, preference, suffix):
    value = os.getenv(env) or sw.GetUserPreferenceStringValue(preference)
    template = Path(value) if value else None
    _require(template and template.is_absolute() and template.is_file() and template.suffix.lower() == suffix,
             f"请在 SolidWorks 设置可用的 {suffix} 默认模板，或配置 {env}")
    return str(template)


def _save(doc, destination, com, pdf_data=None):
    # PDF export uses the current single drawing sheet. File/result existence is
    # checked after the document closes before packaging.
    errors = com.int_ref()
    warnings = com.int_ref()
    saved = doc.Extension.SaveAs3(str(destination), 0, SAVE_SILENT, pdf_data, None, errors, warnings)
    _require(saved and not errors.value, f"SolidWorks 保存 {destination.suffix} 失败")
    return int(warnings.value)


def _select_front_plane(part):
    current = part.FirstFeature()
    while current is not None:
        if current.GetTypeName2() == "RefPlane":
            _require(current.Select2(False, 0), "无法选择新零件的基准面")
            return current
        current = current.GetNextFeature()
    raise NativeError("零件模板缺少标准基准面")


def _build_part(part, plan):
    part.ClearSelection2(True)
    plane = _select_front_plane(part)
    sketch = part.SketchManager
    feature = part.FeatureManager
    x, y, height = (value / MM_PER_METRE for value in plan["bounding_box_mm"])
    sketch.InsertSketch(True)
    rectangle = sketch.CreateCenterRectangle(0.0, 0.0, 0.0, x / 2, y / 2, 0.0)
    _require(rectangle, "SolidWorks 未能创建安装板轮廓")
    base = feature.FeatureExtrusion2(
        True, False, False, END_BLIND, END_BLIND, height, 0.0,
        False, False, False, False, 0.0, 0.0, False, False, False, False,
        True, True, True, START_SKETCH_PLANE, 0.0, False,
    )
    _require(base is not None, "SolidWorks 未能拉伸安装板")
    base.Name = "DraftPilot Plate"

    part.ClearSelection2(True)
    _require(plane.Select2(False, 0), "无法选择通孔草图的基准面")
    sketch.InsertSketch(True)
    for hole in plan["features"][1]["sketch"]["holes"]:
        circle = sketch.CreateCircleByRadius(hole["x_mm"] / MM_PER_METRE,
                                             hole["y_mm"] / MM_PER_METRE, 0.0,
                                             hole["diameter_mm"] / (2 * MM_PER_METRE))
        _require(circle is not None, "SolidWorks 未能创建一个通孔轮廓")
    # The holes start at the original sketch plane. A two-sided through cut
    # passes through the body regardless of the normal of that plane.
    cut = feature.FeatureCut3(
        False, False, False, END_THROUGH_ALL, END_THROUGH_ALL, height, height,
        False, False, False, False, 0.0, 0.0, False, False, False, False,
        False, True, True, False, False, False, START_SKETCH_PLANE, 0.0, False,
    )
    _require(cut is not None and part.ForceRebuild3(False), "SolidWorks 通孔切除或重建失败")
    cut.Name = "DraftPilot Through Holes"


def _build_drawing(drawing, part_path, plan):
    sheet_names = drawing.GetSheetNames()
    _require(sheet_names and len(sheet_names) == 1, "请使用单图纸页的工程图模板")
    sheet = drawing.GetCurrentSheet()
    _, _, _, _, first_angle, width, height = sheet.GetProperties()[:7]
    _require(width >= 0.20 and height >= 0.14, "请使用 A4 或更大的单页工程图模板")
    length, breadth, thickness = (value / MM_PER_METRE for value in plan["bounding_box_mm"])
    limit = min(width * .26 / length, width * .24 / breadth, height * .33 / breadth,
                height * .17 / thickness)
    scale = next((candidate for candidate in VIEW_SCALES if candidate <= limit), None)
    _require(scale, "工程图模板尺寸不足以容纳零件视图")
    top_y = .36 if first_angle else .84
    right_x = .13 if first_angle else .52
    for name, x, y in (("*Front", .32, .60), ("*Top", .32, top_y), ("*Right", right_x, .60)):
        view = drawing.CreateDrawViewFromModelView3(str(part_path), name, width * x, height * y, 0.0)
        _require(view is not None, f"SolidWorks 未能创建 {name} 视图")
        view.UseSheetScale = False
        view.ScaleDecimal = scale

    drawing.ClearSelection2(True)
    size = plan["bounding_box_mm"]
    notes = [
        "DRAFTPILOT | GEOMETRY REVIEW",
        "Size %.6g x %.6g x %.6g mm" % tuple(size),
        "Through holes | X/Y from plate centre",
    ]
    for label, hole in zip(CORNER_NAMES, plan["features"][1]["sketch"]["holes"]):
        notes.append(f'{label}: X {hole["x_mm"]:g}  Y {hole["y_mm"]:g}  DIA {hole["diameter_mm"]:g} mm')
    notes.append("Material and tolerances to be specified")
    note = drawing.InsertNote("\n".join(notes))
    _require(note is not None, "SolidWorks 未能插入工程图尺寸说明")
    _require(note.GetAnnotation().SetPosition2(width * .64, height * .76, 0.0),
             "SolidWorks 未能放置工程图尺寸说明")
    _require(drawing.ForceRebuild3(False), "SolidWorks 工程图重建失败")


class WindowsCom:
    def __init__(self, pythoncom, win32):
        self.pythoncom = pythoncom
        self.win32 = win32

    def int_ref(self):
        return self.win32.VARIANT(self.pythoncom.VT_BYREF | self.pythoncom.VT_I4, 0)


def _generate(sw, com, plan, directory):
    stem = "DraftPilot_" + uuid4().hex[:10]
    part_path = directory / (stem + PART_EXTENSION)
    drawing_path = directory / (stem + DRAWING_EXTENSION)
    pdf_path = directory / (stem + ".pdf")
    part_template = _template(sw, "DRAFTPILOT_PART_TEMPLATE", PART_TEMPLATE, ".prtdot")
    drawing_template = _template(sw, "DRAFTPILOT_DRAWING_TEMPLATE", DRAWING_TEMPLATE, ".drwdot")
    owned = []
    try:
        part = sw.NewDocument(part_template, 0, 0.0, 0.0)
        _require(part is not None, "SolidWorks 无法用模板创建新零件")
        owned.append(part)
        _build_part(part, plan)
        measurements = _verify_geometry(part, plan)
        warnings = {"part": _save(part, part_path, com)}

        drawing = sw.NewDocument(drawing_template, 0, 0.0, 0.0)
        _require(drawing is not None, "SolidWorks 无法用模板创建新工程图")
        owned.append(drawing)
        _build_drawing(drawing, part_path, plan)
        warnings["drawing"] = _save(drawing, drawing_path, com)
        export = sw.GetExportFileData(PDF_EXPORT)
        _require(export is not None, "SolidWorks 未返回 PDF 导出对象")
        export.ViewPdfAfterSaving = False
        warnings["pdf"] = _save(drawing, pdf_path, com, export)
    finally:
        for doc in reversed(owned):
            try:
                # SaveAs changes a document title. Close only documents created here.
                sw.CloseDoc(doc.GetTitle())
            except Exception:
                LOGGER.warning("SolidWorks could not close a DraftPilot document")
    files = (part_path, drawing_path, pdf_path)
    for file in files:
        _require(file.is_file() and 0 < file.stat().st_size <= MAX_FILE_SIZE,
                 "SolidWorks 导出缺失或超出文件大小限制")
    with pdf_path.open("rb") as pdf:
        _require(pdf.read(5) == b"%PDF-", "SolidWorks 未返回有效的 PDF 文件")
    report = {"native_model_created": True, "geometry": measurements, "save_warning_flags": warnings}
    result = BytesIO()
    with ZipFile(result, "w", compression=ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, file.name)
        archive.writestr("model_plan.json", json.dumps(plan, ensure_ascii=False, indent=2))
        archive.writestr("native_geometry_check.json", json.dumps(report, ensure_ascii=False, indent=2))
    result.seek(0)
    return result


def native_archive(plan):
    plan = validate_plate(plan)
    _require(sys.platform == "win32", "原生出图需要在安装了 SolidWorks 的 Windows 电脑上运行")
    if not NATIVE_LOCK.acquire(blocking=False):
        raise NativeError("SolidWorks 正在生成另一张图，请稍后重试")
    try:
        try:
            import pythoncom
            import win32com.client as win32
        except ImportError as exc:
            raise NativeError("未安装 pywin32，请按启动说明安装 Windows 依赖") from exc
        pythoncom.CoInitialize()
        try:
            try:
                sw = win32.GetActiveObject("SldWorks.Application")
            except pythoncom.com_error as exc:
                raise NativeError("请先打开 SolidWorks 2025，再点击生成") from exc
            _require(sw.RevisionNumber().split(".")[0] == "33", "本版原生出图仅开放给 SolidWorks 2025")
            with TemporaryDirectory(prefix="DraftPilot-") as temp:
                return _generate(sw, WindowsCom(pythoncom, win32), plan, Path(temp))
        finally:
            pythoncom.CoUninitialize()
    except NativeError:
        raise
    except Exception as exc:
        LOGGER.warning("DraftPilot native generation failed: %s", type(exc).__name__)
        raise NativeError("SolidWorks 生成失败，请检查模板、已打开的对话框和当前会话") from exc
    finally:
        NATIVE_LOCK.release()
