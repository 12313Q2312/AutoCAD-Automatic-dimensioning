"""
AI 模式处理器
DW→PNG 导出 → 调用大模型分析 → 解析 JSON → 执行标注
"""

import os
import json
import logging
from typing import Optional, Dict, Any

from .cad_com import AutoCADApp
from .style_config import DimensionStyle
from ai_adapters.base import get_adapter

logger = logging.getLogger(__name__)


def ai_process_drawing(
    cad: AutoCADApp,
    image_path: str,
    api_key: str,
    model_provider: str,
    api_base: Optional[str] = None,
    prompt: Optional[str] = None,
    config: Optional[DimensionStyle] = None,
) -> dict:
    """
    AI 模式：处理当前打开的 DWG 文件

    流程:
    1. 导出当前 DWG 视图为 PNG
    2. 调用 AI 适配器分析图片
    3. 解析 AI 返回的 JSON 标注方案
    4. 在 AutoCAD 中执行标注

    参数:
        cad: AutoCAD 连接实例（已打开文档）
        image_path: 导出 PNG 的保存路径
        api_key: 大模型 API Key
        model_provider: 模型提供商 (deepseek/qwen/glm/ernie/kimi/custom)
        api_base: 自定义 API 地址（可选）
        prompt: 自定义提示词（可选，使用默认）
        config: 标注样式配置（可选）

    返回:
        {"success": bool, "dim_count": int, "summary": str, "error": str}
    """
    result = {"success": False, "dim_count": 0, "summary": "", "error": ""}

    try:
        # 1. 导出 PNG
        logger.info(f"导出 DWG 为 PNG: {image_path}")
        png_dir = os.path.dirname(image_path)
        if png_dir and not os.path.exists(png_dir):
            os.makedirs(png_dir)

        exported = cad.export_to_png(image_path)
        if not exported or not os.path.exists(image_path):
            result["error"] = "导出 PNG 失败"
            logger.error(result["error"])
            return result

        logger.info(f"PNG 导出成功: {image_path}")

        # 2. 调用 AI 适配器
        adapter = get_adapter(model_provider, api_key, api_base)
        ai_prompt = prompt or adapter.default_prompt()

        logger.info(f"正在调用 {model_provider} 分析图纸...")
        ai_result = adapter.analyze_image(image_path, ai_prompt)

        if not ai_result or "dimensions" not in ai_result:
            result["error"] = f"AI 返回结果格式异常: {json.dumps(ai_result, ensure_ascii=False)[:200]}"
            logger.warning(result["error"])
            return result

        # 3. 解析并执行标注
        dims = ai_result.get("dimensions", [])
        summary = ai_result.get("summary", "")
        result["summary"] = summary
        result["dim_count"] = len(dims)

        logger.info(f"AI 返回 {len(dims)} 个标注项")

        if not dims:
            result["success"] = True
            result["error"] = "AI 未识别出需要标注的尺寸"
            return result

        # 4. 执行标注
        dims_created = 0
        for i, dim in enumerate(dims):
            try:
                dim_type = dim.get("type", "aligned")

                if dim_type == "aligned":
                    sp = dim["start_point"]
                    ep = dim["end_point"]
                    tp = dim.get("text_position", [
                        (sp[0] + ep[0]) / 2,
                        (sp[1] + ep[1]) / 2 + 10,
                        sp[2] if len(sp) > 2 else 0
                    ])
                    cad.add_dim_aligned(sp, ep, tp)

                elif dim_type == "rotated":
                    sp = dim["start_point"]
                    ep = dim["end_point"]
                    tp = dim.get("text_position", [
                        (sp[0] + ep[0]) / 2,
                        (sp[1] + ep[1]) / 2 + 10,
                        sp[2] if len(sp) > 2 else 0
                    ])
                    rotation = dim.get("rotation", 0.0)
                    cad.add_dim_rotated(sp, ep, tp, rotation)

                elif dim_type == "diameter":
                    center = dim["center_point"]
                    chord = dim["chord_point"]
                    leader = dim.get("leader_length", 10.0)
                    cad.add_dim_diameter(center, chord, leader)

                elif dim_type == "radius":
                    center = dim["center_point"]
                    chord = dim["chord_point"]
                    leader = dim.get("leader_length", 10.0)
                    cad.add_dim_radius(center, chord, leader)

                elif dim_type == "angular":
                    vertex = dim["vertex"]
                    f1s = dim["first_line_start"]
                    f1e = dim["first_line_end"]
                    f2s = dim["second_line_start"]
                    f2e = dim["second_line_end"]
                    tp = dim.get("text_position", vertex)
                    cad.add_dim_angular(vertex, f1s, f1e, f2s, f2e, tp)

                else:
                    logger.warning(f"未知标注类型: {dim_type}，跳过")
                    continue

                dims_created += 1

            except Exception as e:
                logger.warning(f"执行第 {i} 个标注项失败: {e}")
                continue

        result["success"] = True
        result["dim_count"] = dims_created
        logger.info(f"AI 标注完成: 成功创建 {dims_created}/{len(dims)} 个标注")

        # 缩放到全部图形
        try:
            cad.zoom_extents()
        except:
            pass

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"AI 模式处理失败: {e}")

    return result
