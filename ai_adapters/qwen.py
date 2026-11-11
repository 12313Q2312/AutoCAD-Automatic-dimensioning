"""通义千问 Qwen-VL 适配器"""

import base64
import json
import logging
from typing import Optional, Dict, Any

import httpx
from .base import AdapterBase

logger = logging.getLogger(__name__)


class QwenAdapter(AdapterBase):
    def default_api_base(self) -> str:
        return "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def analyze_image(self, image_path: str, prompt: str) -> Dict[str, Any]:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "model": "qwen-vl-plus",
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

        logger.info("正在调用 通义千问 Qwen-VL API...")
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
            logger.warning(f"通义千问返回非 JSON: {content[:200]}")
            return {"dimensions": [], "summary": content}
