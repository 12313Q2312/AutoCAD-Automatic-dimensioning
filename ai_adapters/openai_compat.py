"""通用 OpenAI 兼容协议适配器
适用于任何兼容 OpenAI API 格式的国内模型服务
"""

import base64
import json
import logging
from typing import Optional, Dict, Any

import httpx
from .base import AdapterBase

logger = logging.getLogger(__name__)


class OpenAICompatAdapter(AdapterBase):
    """通用 OpenAI 兼容适配器"""

    def __init__(self, api_key: str, api_base: str):
        super().__init__(api_key, api_base)
        # 从 api_key 中提取模型名（格式: "模型名|实际key" 或纯 key）
        if "|" in api_key:
            parts = api_key.split("|", 1)
            self.model_name = parts[0]
            self.api_key = parts[1]
        else:
            self.model_name = ""

    def default_api_base(self) -> str:
        return ""

    def set_model(self, model_name: str):
        """设置模型名称"""
        self.model_name = model_name

    def analyze_image(self, image_path: str, prompt: str) -> Dict[str, Any]:
        if not self.api_base:
            raise ValueError("自定义模式需要提供 API 地址")
        if not self.model_name:
            raise ValueError("自定义模式需要提供模型名称")

        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_data}"
                            }
                        }
                    ]
                }
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.info(f"正在调用自定义 AI 接口: {self.api_base}")
        resp = httpx.post(
            f"{self.api_base}/chat/completions",
            json=payload,
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()

        content = result["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"自定义 API 返回非 JSON: {content[:200]}")
            return {"dimensions": [], "summary": content}
