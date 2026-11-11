"""
推荐引擎
统计用户使用频率，返回 Top3 常用配置
"""

import json
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# 默认数据文件路径
DEFAULT_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "user_data",
    "usage_records.json",
)


class RecommendationEngine:
    """推荐引擎"""

    def __init__(self, data_path: str = DEFAULT_DATA_PATH):
        self.data_path = data_path
        self._ensure_file()

    def _ensure_file(self):
        """确保数据文件存在"""
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        if not os.path.exists(self.data_path):
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def load_history(self) -> list:
        """读取历史记录"""
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def save_history(self, records: list):
        """保存历史记录"""
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def record_usage(self, config: dict, mode: str, folder: str = ""):
        """
        记录一次使用

        参数:
            config: 标注配置参数
            mode: "standard" 或 "ai"
            folder: 文件夹路径（可选）
        """
        records = self.load_history()

        # 创建配置指纹用于去重
        fingerprint = json.dumps(config, sort_keys=True)

        # 查找是否已有相同配置
        found = False
        for record in records:
            if json.dumps(record.get("config", {}), sort_keys=True) == fingerprint:
                record["count"] = record.get("count", 0) + 1
                record["last_used"] = datetime.now().isoformat()
                record["mode"] = mode
                if folder:
                    record["folder"] = folder
                found = True
                break

        if not found:
            records.append({
                "config": config,
                "mode": mode,
                "folder": folder,
                "count": 1,
                "last_used": datetime.now().isoformat(),
            })

        self.save_history(records)

    def get_top3(self, current_config: Optional[dict] = None) -> List[dict]:
        """
        获取 Top3 常用配置

        参数:
            current_config: 当前配置（可选，用于排除自身）

        返回:
            [{"config": {...}, "mode": "...", "count": N, "last_used": "..."}, ...]
        """
        records = self.load_history()

        # 按使用次数排序
        sorted_records = sorted(records, key=lambda r: r.get("count", 0), reverse=True)

        # 排除当前配置
        if current_config:
            current_fp = json.dumps(current_config, sort_keys=True)
            sorted_records = [
                r for r in sorted_records
                if json.dumps(r.get("config", {}), sort_keys=True) != current_fp
            ]

        # 返回 Top3
        return sorted_records[:3]

    def clear_history(self):
        """清空历史记录"""
        self.save_history([])
