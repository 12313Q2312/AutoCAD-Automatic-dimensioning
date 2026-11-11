"""
自动标注核心算法 — 标准模式
遍历模型空间实体，自动识别几何图形并添加国标尺寸标注
"""

import math
import logging
from typing import List, Tuple, Optional
from .style_config import DimensionStyle
from .cad_com import AutoCADApp, AutoCADError

logger = logging.getLogger(__name__)


def _get_entity_type(entity) -> str:
    """获取实体类型名称"""
    try:
        return entity.EntityType
    except:
        try:
            return entity.ObjectName
        except:
            return "Unknown"


def _get_entity_bounds(entity) -> Optional[Tuple[float, float, float, float]]:
    """
    获取实体外接矩形 (min_x, min_y, max_x, max_y)
    通过 BoundingBox 方法
    """
    try:
        min_point = entity.GetBoundingBox[0]
        max_point = entity.GetBoundingBox[1]
        return (min_point[0], min_point[1], max_point[0], max_point[1])
    except:
        return None


def _distance(p1, p2) -> float:
    """计算两点距离"""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def _midpoint(p1, p2) -> Tuple[float, float, float]:
    """计算中点"""
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, p1[2] if len(p1) > 2 else 0)


def _offset_point(p1, p2, distance: float) -> Tuple[float, float, float]:
    """
    计算从 p1 到 p2 方向上偏移 distance 的点
    用于标注线定位（在图形外侧）
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.sqrt(dx ** 2 + dy ** 2)
    if length < 0.001:
        return (p1[0], p1[1] + distance, p1[2] if len(p1) > 2 else 0)
    nx = -dy / length  # 垂直方向（法线）
    ny = dx / length
    z = p1[2] if len(p1) > 2 else 0
    return (
        (p1[0] + p2[0]) / 2 + nx * distance,
        (p1[1] + p2[1]) / 2 + ny * distance,
        z
    )


def _perpendicular_offset(point, line_start, line_end, offset: float) -> Tuple[float, float, float]:
    """
    计算点到直线的垂线方向偏移 offset 后的点
    用于标注文字位置
    """
    dx = line_end[0] - line_start[0]
    dy = line_end[1] - line_start[1]
    length = math.sqrt(dx ** 2 + dy ** 2)
    if length < 0.001:
        return (point[0], point[1] + offset, point[2] if len(point) > 2 else 0)

    # 法线方向
    nx = -dy / length
    ny = dx / length

    # 判断点在线的哪一侧
    # 用叉积: (p - line_start) × (line_end - line_start)
    cp = (point[0] - line_start[0]) * dy - (point[1] - line_start[1]) * dx
    side = 1 if cp >= 0 else -1

    z = point[2] if len(point) > 2 else 0
    return (
        point[0] + nx * offset * side,
        point[1] + ny * offset * side,
        z
    )


def _is_vertical(line) -> bool:
    """判断直线是否近似垂直（用于决定标注方向）"""
    try:
        sp = line.StartPoint
        ep = line.EndPoint
        dx = abs(ep[0] - sp[0])
        dy = abs(ep[1] - sp[1])
        return dy > dx * 2
    except:
        return False


def _is_horizontal(line) -> bool:
    """判断直线是否近似水平"""
    try:
        sp = line.StartPoint
        ep = line.EndPoint
        dx = abs(ep[0] - sp[0])
        dy = abs(ep[1] - sp[1])
        return dx > dy * 2
    except:
        return False


def _get_line_angle(line) -> float:
    """获取直线角度（弧度）"""
    try:
        sp = line.StartPoint
        ep = line.EndPoint
        return math.atan2(ep[1] - sp[1], ep[0] - sp[0])
    except:
        return 0.0


def process_line(cad: AutoCADApp, entity, config: DimensionStyle) -> int:
    """
    处理直线实体，添加尺寸标注
    返回添加的标注数量
    """
    count = 0
    try:
        sp = entity.StartPoint
        ep = entity.EndPoint

        # 跳过过短的线（< 2mm）
        length = _distance(sp, ep)
        if length < 2.0:
            return 0

        offset = config.text_size * config.dim_offset_factor

        # 判断主要方向
        dx = abs(ep[0] - sp[0])
        dy = abs(ep[1] - sp[1])

        if dx > dy * 2:
            # 水平为主 → 添加水平线性标注
            text_pos = _perpendicular_offset(_midpoint(sp, ep), sp, ep, offset)
            cad.add_dim_rotated(sp, ep, text_pos, 0)
            count += 1
        elif dy > dx * 2:
            # 垂直为主 → 添加垂直线性标注
            text_pos = _perpendicular_offset(_midpoint(sp, ep), sp, ep, offset)
            cad.add_dim_rotated(sp, ep, text_pos, math.pi / 2)
            count += 1
        else:
            # 斜线 → 添加对齐标注
            text_pos = _perpendicular_offset(_midpoint(sp, ep), sp, ep, offset)
            cad.add_dim_aligned(sp, ep, text_pos)
            count += 1

    except Exception as e:
        logger.warning(f"标注直线失败: {e}")

    return count


def process_circle(cad: AutoCADApp, entity, config: DimensionStyle) -> int:
    """
    处理圆实体，添加直径标注 + 中心标记
    """
    count = 0
    try:
        center = entity.Center
        radius = entity.Radius

        if radius < 1.0:
            return 0

        offset = config.text_size * config.dim_offset_factor

        # 直径标注（水平方向）
        left = (center[0] - radius, center[1], center[2] if len(center) > 2 else 0)
        right = (center[0] + radius, center[1], center[2] if len(center) > 2 else 0)
        text_pos = (center[0], center[1] + offset, center[2] if len(center) > 2 else 0)

        cad.add_dim_diameter(right, left, radius + offset)
        count += 1

        # 可选：再添加一个垂直方向的直径标注
        top = (center[0], center[1] + radius, center[2] if len(center) > 2 else 0)
        bottom = (center[0], center[1] - radius, center[2] if len(center) > 2 else 0)
        text_pos2 = (center[0] + offset, center[1], center[2] if len(center) > 2 else 0)
        cad.add_dim_diameter(top, bottom, radius + offset)
        count += 1

    except Exception as e:
        logger.warning(f"标注圆失败: {e}")

    return count


def process_arc(cad: AutoCADApp, entity, config: DimensionStyle) -> int:
    """
    处理圆弧实体，添加半径标注
    """
    count = 0
    try:
        center = entity.Center
        radius = entity.Radius

        if radius < 1.0:
            return 0

        # 取圆弧中点方向作为标注引线方向
        start_angle = entity.StartAngle
        end_angle = entity.EndAngle
        mid_angle = (start_angle + end_angle) / 2

        chord_point = (
            center[0] + radius * math.cos(mid_angle),
            center[1] + radius * math.sin(mid_angle),
            center[2] if len(center) > 2 else 0
        )

        leader_length = config.text_size * config.dim_offset_factor
        cad.add_dim_radius(center, chord_point, leader_length)
        count += 1

    except Exception as e:
        logger.warning(f"标注圆弧失败: {e}")

    return count


def process_polyline(cad: AutoCADApp, entity, config: DimensionStyle) -> int:
    """
    处理多段线，逐段标注 + 整体外接矩形长宽标注
    """
    count = 0
    try:
        coordinates = entity.Coordinates
        # 2D 多段线：坐标数组是 [x1,y1, x2,y2, ...]
        # 3D 多段线：坐标数组是 [x1,y1,z1, x2,y2,z2, ...]

        # 判断是 2D 还是 3D（根据常规多段线，2D为偶数个）
        is_2d = (len(coordinates) % 2 == 0)

        points = []
        if is_2d:
            for i in range(0, len(coordinates), 2):
                points.append((coordinates[i], coordinates[i + 1], 0))
        else:
            for i in range(0, len(coordinates), 3):
                points.append((coordinates[i], coordinates[i + 1], coordinates[i + 2]))

        if len(points) < 2:
            return 0

        # 判断闭合多段线
        is_closed = False
        try:
            is_closed = entity.Closed
        except:
            pass

        offset = config.text_size * config.dim_offset_factor

        # 判断是否接近矩形（4个点 + 闭合）
        if is_closed and len(points) == 4:
            # 可能是矩形 → 标注长宽
            d01 = _distance(points[0], points[1])
            d12 = _distance(points[1], points[2])
            # 长边加水平标注，短边加垂直标注
            if d01 >= d12:
                # p0-p1 是长边
                text_pos1 = _perpendicular_offset(
                    _midpoint(points[0], points[1]), points[0], points[1], offset)
                cad.add_dim_rotated(points[0], points[1], text_pos1, 0)
                count += 1
                # p1-p2 是短边
                text_pos2 = _perpendicular_offset(
                    _midpoint(points[1], points[2]), points[1], points[2], offset)
                cad.add_dim_rotated(points[1], points[2], text_pos2, math.pi / 2)
                count += 1
            else:
                text_pos1 = _perpendicular_offset(
                    _midpoint(points[1], points[2]), points[1], points[2], offset)
                cad.add_dim_rotated(points[1], points[2], text_pos1, 0)
                count += 1
                text_pos2 = _perpendicular_offset(
                    _midpoint(points[0], points[1]), points[0], points[1], offset)
                cad.add_dim_rotated(points[0], points[1], text_pos2, math.pi / 2)
                count += 1
        else:
            # 一般多段线 → 逐段标注
            for i in range(len(points) - 1):
                p1 = points[i]
                p2 = points[i + 1]

                seg_len = _distance(p1, p2)
                if seg_len < 2.0:
                    continue

                dx = abs(p2[0] - p1[0])
                dy = abs(p2[1] - p1[1])
                text_pos = _perpendicular_offset(_midpoint(p1, p2), p1, p2, offset)

                if dx > dy * 2:
                    cad.add_dim_rotated(p1, p2, text_pos, 0)
                elif dy > dx * 2:
                    cad.add_dim_rotated(p1, p2, text_pos, math.pi / 2)
                else:
                    cad.add_dim_aligned(p1, p2, text_pos)
                count += 1

    except Exception as e:
        logger.warning(f"标注多段线失败: {e}")

    return count


def process_lwpolyline(cad: AutoCADApp, entity, config: DimensionStyle) -> int:
    """
    处理轻量多段线 (AcDbPolyline)，与多段线类似但坐标获取方式不同
    """
    count = 0
    try:
        num_vertices = entity.NumberOfVertices
        if num_vertices < 2:
            return 0

        points = []
        for i in range(num_vertices):
            pt = entity.Coordinate(i)
            points.append((pt[0], pt[1], 0))

        is_closed = False
        try:
            is_closed = entity.Closed
        except:
            pass

        offset = config.text_size * config.dim_offset_factor
        bulges = []
        for i in range(num_vertices):
            try:
                bulges.append(entity.GetBulge(i))
            except:
                bulges.append(0.0)

        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            seg_len = _distance(p1, p2)
            if seg_len < 2.0:
                continue

            text_pos = _perpendicular_offset(_midpoint(p1, p2), p1, p2, offset)
            dx = abs(p2[0] - p1[0])
            dy = abs(p2[1] - p1[1])

            if dx > dy * 2:
                cad.add_dim_rotated(p1, p2, text_pos, 0)
            elif dy > dx * 2:
                cad.add_dim_rotated(p1, p2, text_pos, math.pi / 2)
            else:
                cad.add_dim_aligned(p1, p2, text_pos)
            count += 1

        # 外接矩形整体标注
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        total_width = max_x - min_x
        total_height = max_y - min_y

        if total_width > 5.0:
            bl = (min_x, min_y, 0)
            br = (max_x, min_y, 0)
            tp = (min_x, max_y, 0)
            text_w = _perpendicular_offset(_midpoint(bl, br), bl, br, offset * 1.5)
            cad.add_dim_rotated(bl, br, text_w, 0)
            count += 1

            text_h = _perpendicular_offset(_midpoint(bl, tp), bl, tp, offset * 1.5)
            cad.add_dim_rotated(bl, tp, text_h, math.pi / 2)
            count += 1

    except Exception as e:
        logger.warning(f"标注轻量多段线失败: {e}")

    return count


# 实体类型分发映射
ENTITY_PROCESSORS = {
    "AcDbLine": process_line,
    "AcDbCircle": process_circle,
    "AcDbArc": process_arc,
    "AcDbPolyline": process_polyline,
    "AcDb2dPolyline": process_polyline,
    "AcDb3dPolyline": process_polyline,
    "AcDbPolyline3d": process_polyline,
    # "AcDbLWPolyline" 在 _get_entity_type 中实际上是 "AcDbPolyline"
}


def auto_dimension_drawing(cad: AutoCADApp, config: Optional[DimensionStyle] = None) -> dict:
    """
    对当前打开的 DWG 执行自动标注

    参数:
        cad: AutoCADApp 实例（已打开文档）
        config: 标注样式配置，None 则使用国标默认

    返回:
        {"total": int, "dimensioned": int, "skipped": int, "errors": int}
    """
    if config is None:
        config = DimensionStyle.gb_default()

    result = {"total": 0, "dimensioned": 0, "skipped": 0, "errors": 0}

    try:
        msg = "自动标注开始..."
        logger.info(msg)
        cad.doc.SendCommand(f"(princ \"{msg}\\n\")")

        entities = cad.get_all_entities()
        total_count = entities.Count
        result["total"] = total_count

        logger.info(f"模型空间共 {total_count} 个实体")

        for i in range(total_count):
            try:
                entity = entities.Item(i)
                entity_type = _get_entity_type(entity)

                # 跳过非几何实体
                if entity_type.startswith("AcDbText") or entity_type.startswith("AcDbMText"):
                    result["skipped"] += 1
                    continue
                if entity_type.startswith("AcDbDimension"):
                    result["skipped"] += 1
                    continue
                if entity_type.startswith("AcDbBlockReference"):
                    result["skipped"] += 1
                    continue

                # 查找对应的处理器
                processor = ENTITY_PROCESSORS.get(entity_type)
                if processor is None:
                    # 对于轻量多段线, ObjectName 可能是 AcDbPolyline
                    try:
                        obj_name = entity.ObjectName
                        processor = ENTITY_PROCESSORS.get(obj_name)
                    except:
                        obj_name = entity_type

                if processor is None:
                    result["skipped"] += 1
                    continue

                # 执行标注
                count = processor(cad, entity, config)
                if count > 0:
                    result["dimensioned"] += count
                else:
                    result["skipped"] += 1

            except Exception as e:
                logger.warning(f"处理实体 #{i} 时出错: {e}")
                result["errors"] += 1

        # 缩放至全部图形
        try:
            cad.zoom_extents()
        except:
            pass

        msg = f"自动标注完成: 标注 {result['dimensioned']} 处, 跳过 {result['skipped']} 个, 错误 {result['errors']} 个"
        logger.info(msg)

    except Exception as e:
        logger.error(f"自动标注整体失败: {e}")
        result["errors"] = result["total"]

    return result
