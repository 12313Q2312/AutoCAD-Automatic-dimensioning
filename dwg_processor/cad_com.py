"""
AutoCAD COM 封装层 — 支持多版本自动检测(2024/2025/2026) 的 COM 操作接口
"""

import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# AutoCAD 版本 ProgID 探测优先级（最新优先）
CAD_PROGIDS = [
    "AutoCAD.Application.25.1",  # 2026
    "AutoCAD.Application.25.0",  # 2025
    "AutoCAD.Application.24.3",  # 2024
    "AutoCAD.Application.25",    # 25系通用
    "AutoCAD.Application.24",    # 24系通用
]

# 版本号映射
CAD_VERSION_MAP = {
    "25.1": "AutoCAD 2026",
    "25.0": "AutoCAD 2025",
    "24.3": "AutoCAD 2024",
    "25": "AutoCAD 25系",
    "24": "AutoCAD 24系",
}


class AutoCADError(Exception):
    """AutoCAD 操作异常"""
    pass


class AutoCADApp:
    """AutoCAD 应用程序封装"""

    def __init__(self, visible: bool = False):
        self.app = None
        self.doc = None
        self.version = None
        self.version_name = None
        self.visible = visible

    def detect_version(self) -> Optional[str]:
        """
        检测已安装的 AutoCAD 版本
        返回 ProgID，未安装返回 None
        """
        import win32com.client

        for prog_id in CAD_PROGIDS:
            try:
                test_app = win32com.client.Dispatch(prog_id)
                ver = test_app.Version
                try:
                    test_app.Quit()
                except:
                    pass
                test_app = None
                self.version = prog_id
                # 解析版本名
                for key, name in CAD_VERSION_MAP.items():
                    if ver.startswith(key):
                        self.version_name = name
                        break
                if not self.version_name:
                    self.version_name = f"AutoCAD (版本 {ver})"
                logger.info(f"检测到 AutoCAD: {self.version_name} ({prog_id})")
                return prog_id
            except Exception:
                continue
        logger.warning("未检测到已安装的 AutoCAD")
        return None

    def connect(self, prog_id: Optional[str] = None) -> bool:
        """
        连接 AutoCAD
        - prog_id: 指定版本，None 则自动检测
        返回是否成功
        """
        import win32com.client
        import pythoncom

        if prog_id:
            self.version = prog_id
        elif not self.version:
            if not self.detect_version():
                return False

        try:
            pythoncom.CoInitialize()
            self.app = win32com.client.Dispatch(self.version)
            self.app.Visible = self.visible
            logger.info(f"已连接 AutoCAD: {self.version_name or self.version}")
            return True
        except Exception as e:
            logger.error(f"连接 AutoCAD 失败: {e}")
            raise AutoCADError(f"无法连接到 AutoCAD ({self.version}): {e}")

    def open_drawing(self, dwg_path: str) -> bool:
        """打开 DWG 文件"""
        if not self.app:
            raise AutoCADError("AutoCAD 未连接，请先调用 connect()")

        if not os.path.exists(dwg_path):
            raise AutoCADError(f"文件不存在: {dwg_path}")

        try:
            abs_path = os.path.abspath(dwg_path)
            self.doc = self.app.Documents.Open(abs_path)
            logger.info(f"已打开文件: {abs_path}")
            return True
        except Exception as e:
            logger.error(f"打开 DWG 失败: {dwg_path}: {e}")
            raise AutoCADError(f"打开文件失败 {dwg_path}: {e}")

    def close_drawing(self, save: bool = True):
        """关闭当前 DWG"""
        if self.doc:
            try:
                self.doc.Close(save)
                logger.info(f"已关闭文档(save={save})")
            except Exception as e:
                logger.warning(f"关闭文档时出错: {e}")
            finally:
                self.doc = None

    def get_model_space(self):
        """获取模型空间对象"""
        if not self.doc:
            raise AutoCADError("未打开文档。")
        return self.doc.ModelSpace

    def get_paper_space(self):
        """获取图纸空间对象"""
        if not self.doc:
            raise AutoCADError("未打开文档。")
        return self.doc.PaperSpace

    def save_as(self, output_path: str):
        """另存为"""
        if not self.doc:
            raise AutoCADError("未打开文档。")
        try:
            self.doc.SaveAs(os.path.abspath(output_path))
            logger.info(f"已另存为: {output_path}")
        except Exception as e:
            logger.error(f"保存文件失败: {e}")
            raise AutoCADError(f"保存文件失败: {e}")

    def save(self):
        """保存当前文档"""
        if not self.doc:
            raise AutoCADError("未打开文档。")
        try:
            self.doc.Save()
            logger.info("已保存文档")
        except Exception as e:
            logger.error(f"保存失败: {e}")
            raise AutoCADError(f"保存失败: {e}")

    def export_to_png(self, output_png: str, width: int = 1600, height: int = 1200) -> bool:
        """导出当前视图为 PNG"""
        if not self.doc:
            raise AutoCADError("未打开文档。")

        abs_path = os.path.abspath(output_png)
        png_dir = os.path.dirname(abs_path)
        if png_dir and not os.path.exists(png_dir):
            os.makedirs(png_dir, exist_ok=True)

        try:
            # AutoCAD Export: filename without extension, format as second param
            base = abs_path
            if base.lower().endswith(".png"):
                base = base[:-4]
            self.doc.Export(base, "PNG")
            logger.info(f"已导出 PNG: {abs_path}")
            # 等待文件写入完成
            time.sleep(1)
            return os.path.exists(abs_path)
        except Exception as e:
            logger.error(f"导出 PNG 失败: {e}")
            # 尝试替代方案：用 Plot 方式
            try:
                return self._plot_to_png(output_png, width, height)
            except Exception as e2:
                logger.error(f"Plot 导出也失败: {e2}")
                raise AutoCADError(f"导出 PNG 失败: {e}")

    def _plot_to_png(self, output_png: str, width: int, height: int) -> bool:
        """备用方案：通过 Plot 方式导出 PNG"""
        abs_path = os.path.abspath(output_png)
        # 设置布局名称
        layout = self.doc.ActiveLayout

        # 设置输出为 PNG
        layout.ConfigName = "PNG"
        layout.PlotType = 1  # acDisplay: 显示范围
        layout.PlotOrigin(0, 0)
        layout.PlotPaperUnits = 0  # mm
        layout.PlotRotation = 0

        # 设置图纸尺寸
        from win32com.client import constants
        try:
            layout.CanonicalMediaName = f"USER{width}x{height}"
        except:
            pass

        self.doc.Plot.PlotToFile(abs_path)
        time.sleep(1)
        return os.path.exists(abs_path)

    def get_all_entities(self):
        """获取模型空间中所有实体"""
        ms = self.get_model_space()
        entities = []
        for i in range(ms.Count):
            entities.append(ms.Item(i))
        return entities

    def add_dim_aligned(self, start_point, end_point, text_position):
        """添加对齐标注"""
        if not self.doc:
            raise AutoCADError("未打开文档。")
        ms = self.get_model_space()
        return ms.AddDimAligned(start_point, end_point, text_position)

    def add_dim_rotated(self, start_point, end_point, text_position, rotation_angle):
        """添加旋转标注"""
        if not self.doc:
            raise AutoCADError("未打开文档。")
        ms = self.get_model_space()
        return ms.AddDimRotated(start_point, end_point, text_position, rotation_angle)

    def add_dim_diameter(self, center_point, chord_point, leader_length):
        """添加直径标注"""
        if not self.doc:
            raise AutoCADError("未打开文档。")
        ms = self.get_model_space()
        return ms.AddDimDiametric(center_point, chord_point, leader_length)

    def add_dim_radius(self, center_point, chord_point, leader_length):
        """添加半径标注"""
        if not self.doc:
            raise AutoCADError("未打开文档。")
        ms = self.get_model_space()
        return ms.AddDimRadial(center_point, chord_point, leader_length)

    def add_dim_angular(self, vertex, first_line_start, first_line_end, second_line_start, second_line_end, text_position):
        """添加角度标注"""
        if not self.doc:
            raise AutoCADError("未打开文档。")
        ms = self.get_model_space()
        return ms.AddDimAngular(vertex, first_line_start, first_line_end,
                                second_line_start, second_line_end, text_position)

    def zoom_extents(self):
        """缩放到图形范围"""
        if not self.doc:
            raise AutoCADError("未打开文档。")
        self.doc.SendCommand("_zoom\ne\n")

    def get_preferences(self):
        """获取系统配置"""
        if not self.app:
            raise AutoCADError("AutoCAD 未连接")
        return self.app.Preferences

    def disconnect(self):
        """断开连接并清理"""
        self.close_drawing(save=False)
        if self.app:
            try:
                self.app.Quit()
            except:
                pass
            self.app = None
        logger.info("已断开 AutoCAD 连接")


def detect_installed_cad() -> Optional[dict]:
    """
    检测已安装 AutoCAD 版本（独立函数，不创建实例）
    返回 {"prog_id": str, "version_name": str} 或 None
    """
    import win32com.client

    for prog_id in CAD_PROGIDS:
        try:
            app = win32com.client.Dispatch(prog_id)
            ver = app.Version
            app.Quit()
            app = None

            version_name = CAD_VERSION_MAP.get(
                next((k for k in CAD_VERSION_MAP if ver.startswith(k)), ""),
                f"AutoCAD (版本 {ver})"
            )
            return {"prog_id": prog_id, "version_name": version_name}
        except Exception:
            continue
    return None