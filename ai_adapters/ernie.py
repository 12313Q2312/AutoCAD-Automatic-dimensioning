"""文心一言 ERNIE 4.5 适配器"""

import base64
import json
import logging
from typing import Optional, Dict, Any

import httpx
from .base import AdapterBase

logger = logging.getLogger(__name__)


class ErnieAdapter(AdapterBase):
    """
    文心一言适配器
    注意：ERNIE API 需要通过百度千帆平台获取 access_token
    这里使用 OpenAI 兼容模式（如果开通了千帆的 OpenAI 兼容接口）
    """

    def default_api_base(self) -> str:
        return "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat"

    def analyze_image(self, image_path: str, prompt: str) -> Dict[str, Any]:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # 文心一言不使用 OpenAI 兼容格式，用自有格式
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_base64",
                            "image_base64": image_data,
                            "image_type": "png",
                        }
                    ]
                }
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        headers = {
            "Content-Type": "application/json",
        }

        logger.info("正在调用 文心一言 ERNIE API...")
        resp = httpx.post(
            f"{self.api_base}?access_token={self.api_key}",
            json=payload,
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()

        content = result.get("result", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"文心一言返回非 JSON: {content[:200]}")
            return {"dimensions": [], "summary": content}
