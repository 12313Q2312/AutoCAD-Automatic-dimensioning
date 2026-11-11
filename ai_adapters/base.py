"""
AI 适配器抽象基类
所有国产大模型适配器需继承此基类
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class AdapterBase(ABC):
    """AI 适配器抽象基类"""

    def __init__(self, api_key: str, api_base: Optional[str] = None):
        self.api_key = api_key
        self.api_base = api_base or self.default_api_base()

    @abstractmethod
    def default_api_base(self) -> str:
        """返回该模型的默认 API 地址"""
        pass

    @abstractmethod
    def analyze_image(self, image_path: str, prompt: str) -> Dict[str, Any]:
        """
        分析图片并返回结构化标注方案

        参数:
            image_path: PNG 图片路径
            prompt: 分析提示词

        返回:
            dict: 标注方案 JSON，格式:
            {
                "dimensions": [
                    {
                        "type": "aligned|rotated|diameter|radius|angular",
                        "start_point": [x, y, z],
                        "end_point": [x, y, z],
                        "text_position": [x, y, z],
                        "rotation": float,  # 仅 rotated 类型
                        "leader_length": float  # 仅 diameter/radius 类型
                    }
                ],
                "summary": "标注说明"
            }
        """
        pass

    @staticmethod
    def default_prompt() -> str:
        """默认分析提示词"""
        return (
            "你是一位专业的CAD工程制图专家。请分析这张DWG工程图纸的截图，"
            "识别出所有需要标注尺寸的部位。"
            "请严格按照以下JSON格式返回标注方案，不要包含其他内容：\n\n"
            "{\n"
            '  "dimensions": [\n'
            "    {\n"
            '      "type": "aligned",\n'
            '      "start_point": [x, y, z],\n'
            '      "end_point": [x, y, z],\n'
            '      "text_position": [x, y, z]\n'
            "    }\n"
            "  ],\n"
            '  "summary": "标注说明"\n'
            "}\n\n"
            "标注类型可选：aligned(对齐标注), rotated(线性标注), "
            "diameter(直径), radius(半径), angular(角度)。\n"
            "请按国标(GB)要求，确保标注清晰、不重叠、文字位置合理。"
        )


# 模型厂商信息
MODEL_REGISTRY = {
    "deepseek": {
        "name": "DeepSeek 识图",
        "default_base": "https://api.deepseek.com/v1",
        "model_name": "deepseek-v4",
        "class": None,  # 延迟导入
    },
    "qwen": {
        "name": "通义千问 Qwen-VL",
        "default_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen-vl-plus",
        "class": None,
    },
    "glm": {
        "name": "智谱 GLM-4V",
        "default_base": "https://open.bigmodel.cn/api/paas/v4",
        "model_name": "glm-4v-plus",
        "class": None,
    },
    "ernie": {
        "name": "文心一言 ERNIE 4.5",
        "default_base": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
        "model_name": "ernie-4.5",
        "class": None,
    },
    "kimi": {
        "name": "Kimi (月之暗面)",
        "default_base": "https://api.moonshot.cn/v1",
        "model_name": "kimi-k2.6",
        "class": None,
    },
}


def get_adapter(provider: str, api_key: str, api_base: Optional[str] = None) -> AdapterBase:
    """工厂方法：根据提供商名称创建适配器实例"""
    provider = provider.lower()

    if provider == "deepseek":
        from .deepseek import DeepSeekAdapter
        return DeepSeekAdapter(api_key, api_base)
    elif provider == "qwen":
        from .qwen import QwenAdapter
        return QwenAdapter(api_key, api_base)
    elif provider == "glm":
        from .glm import GLMAdapter
        return GLMAdapter(api_key, api_base)
    elif provider == "ernie":
        from .ernie import ErnieAdapter
        return ErnieAdapter(api_key, api_base)
    elif provider == "kimi":
        from .kimi import KimiAdapter
        return KimiAdapter(api_key, api_base)
    elif provider == "custom":
        from .openai_compat import OpenAICompatAdapter
        return OpenAICompatAdapter(api_key, api_base or "")
    else:
        raise ValueError(f"未知的模型提供商: {provider}")
