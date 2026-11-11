"""
国标（GB）标注样式配置
所有标注参数的结构化定义与默认值
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class DimensionStyle:
    """标注样式配置"""
    # === 文字样式 ===
    font: str = "gbeitc.shx"           # 字体（国标斜体）
    text_size: float = 2.5             # 文字高度（mm）
    text_offset: float = 1.0           # 文字偏移量
    text_style_name: str = "GB_TEXT"   # 文字样式名称
    text_position: int = 0             # 0=居中, 1=上方, 2=下方, 3=自定义

    # === 箭头 ===
    arrow_type: str = "_ClosedFill"    # 实心闭合箭头
    arrow_size: float = 2.0            # 箭头大小

    # === 标注线 ===
    line_color: int = 1                # 颜色索引 1=红色(标注层常用)
    line_weight: int = 30              # 线宽 30=0.30mm
    line_extend: float = 1.0           # 尺寸界线超出量
    line_offset: float = 0.625         # 尺寸界线起点偏移量
    baseline_spacing: float = 8.0      # 基线标注间距

    # === 精度 ===
    precision: int = 2                 # 小数位数
    tolerance_precision: int = 2       # 公差小数位数
    round_distance: float = 0.0        # 舍入值 (0=不指定)
    decimal_separator: int = 0         # 0=句点, 1=逗号

    # === 单位 ===
    unit_format: int = 2               # 2=十进制
    suffix: str = ""                   # 后缀 (如 "mm")

    # === 标注策略 ===
    dim_offset_factor: float = 3.0     # 标注线偏移系数 = text_size × 系数
    overlap_check: bool = True         # 是否启用防重叠检测

    def to_dict(self) -> dict:
        """转为字典"""
        return asdict(self)

    @classmethod
    def gb_default(cls) -> "DimensionStyle":
        """国标默认配置"""
        return cls()

    @classmethod
    def from_dict(cls, data: dict) -> "DimensionStyle":
        """从字典创建"""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


# 国标预设快捷配置
GB_PRESETS = {
    "机械制图 (GB): 标准": DimensionStyle(
        font="gbeitc.shx",
        text_size=3.5,
        arrow_type="_ClosedFill",
        arrow_size=2.5,
        precision=2,
        suffix="",
    ),
    "机械制图 (GB): 精细": DimensionStyle(
        font="gbeitc.shx",
        text_size=2.5,
        arrow_type="_ClosedFill",
        arrow_size=2.0,
        precision=3,
        suffix="",
    ),
    "建筑制图 (GB): 标准": DimensionStyle(
        font="gbenor.shx",
        text_size=3.0,
        arrow_type="_ArchTick",
        arrow_size=2.0,
        precision=1,
        suffix="",
    ),
    "建筑制图 (GB): 大标注": DimensionStyle(
        font="gbenor.shx",
        text_size=5.0,
        arrow_type="_ArchTick",
        arrow_size=3.0,
        precision=0,
        suffix="mm",
    ),
}
