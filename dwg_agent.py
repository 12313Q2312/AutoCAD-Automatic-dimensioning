# -*- coding: utf-8 -*-
"""
DWG 标注工厂 — 分布式客户端 Agent
每台安装了 AutoCAD 的电脑运行此程序，连接中央服务器协作标注。

用法：
    python dwg_agent.py                          # 使用默认服务器地址
    python dwg_agent.py http://192.168.1.5:5000  # 指定服务器地址
    python dwg_agent.py http://192.168.1.5:5000 --name 张三的电脑
    python dwg_agent.py --simulate               # 模拟模式（无需 AutoCAD）
"""

import os
import sys
import json
import uuid
import time
import socket
import logging
import argparse
import threading
from datetime import datetime

import requests

# 确保可以导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dwg_processor.cad_com import AutoCADApp, detect_installed_cad, AutoCADError
from dwg_processor.auto_dim import auto_dimension_drawing
from dwg_processor.ai_processor import ai_process_drawing
from dwg_processor.style_config import DimensionStyle

# ---------- 配置 ----------
DEFAULT_SERVER_URL = "http://127.0.0.1:5000"
POLL_INTERVAL = 3  # 秒
HEARTBEAT_INTERVAL = 30  # 秒

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

class DWGAgent:
    """DWG 标注客户端 Agent"""

    def __init__(self, server_url: str, display_name: str = "", simulate: bool = False, client_id: str = ""):
        self.server_url = server_url.rstrip("/")
        self.agent_id = self._generate_agent_id()
        self.client_id = client_id
        self.hostname = socket.gethostname()
        self.display_name = display_name or self.hostname
        self.cad_version = None
        self.cad_prog_id = None
        self.status = "init"
        self.simulate = simulate
        self._stop_flag = threading.Event()

    @staticmethod
    def _generate_agent_id() -> str:
        """生成唯一 agent_id（基于主机名+UUID）"""
        host = socket.gethostname()
        short_id = uuid.uuid4().hex[:8]
        return f"{host}-{short_id}"

    def detect_cad(self) -> bool:
        """检测本机 AutoCAD 安装"""
        if self.simulate:
            self.cad_version = "模拟模式 (Simulated)"
            self.cad_prog_id = "Simulated"
            logger.info(f"🟡 模拟模式 — 假装检测到 {self.cad_version}")
            return True
        logger.info("正在检测本机 AutoCAD...")
        result = detect_installed_cad()
        if result:
            self.cad_version = result["version_name"]
            self.cad_prog_id = result["prog_id"]
            logger.info(f"检测到 {self.cad_version} ({self.cad_prog_id})")
            return True
        else:
            logger.warning("未检测到 AutoCAD，请确认已安装 AutoCAD 2024/2025/2026")
            return False

    def register(self) -> bool:
        """向服务器注册"""
        payload = {
            "agent_id": self.agent_id,
            "hostname": self.hostname,
            "display_name": self.display_name,
            "cad_version": self.cad_version,
            "client_id": self.client_id,
        }
        try:
            resp = requests.post(
                f"{self.server_url}/api/agent/register",
                json=payload,
                timeout=10,
            )
            data = resp.json()
            if data.get("success"):
                logger.info(f"注册成功: {self.agent_id}")
                self.status = "idle"
                return True
            else:
                logger.error(f"注册失败: {data.get('error', '未知错误')}")
                return False
        except requests.RequestException as e:
            logger.error(f"无法连接服务器 {self.server_url}: {e}")
            return False

    def heartbeat(self):
        """发送心跳保持在线"""
        try:
            resp = requests.post(
                f"{self.server_url}/api/agent/heartbeat",
                json={"agent_id": self.agent_id},
                timeout=5,
            )
            data = resp.json()
            if not data.get("success"):
                logger.warning(f"心跳异常: {data.get('error')}")
        except requests.RequestException:
            logger.warning("心跳发送失败，服务器可能离线")

    def poll_task(self):
        """向服务器轮询待办任务，返回任务 dict 或 None"""
        try:
            resp = requests.get(
                f"{self.server_url}/api/agent/task/{self.agent_id}",
                timeout=10,
            )
            data = resp.json()
            if data.get("success") and data.get("has_task"):
                return data["task"]
        except requests.RequestException:
            pass
        return None

    def report_progress(self, task_id: str, progress: float, current_file: str = ""):
        """上报进度"""
        try:
            requests.post(
                f"{self.server_url}/api/agent/complete",
                json={
                    "agent_id": self.agent_id,
                    "task_id": task_id,
                    "status": "processing",
                    "progress": progress,
                    "current_file": current_file,
                },
                timeout=5,
            )
        except requests.RequestException:
            pass

    def download_file(self, session_id: str, filename: str, target_dir: str) -> str:
        """从服务端下载 DWG 文件到本地"""
        save_path = os.path.join(target_dir, filename)
        try:
            resp = requests.get(
                f"{self.server_url}/api/agent/download/{session_id}/{filename}",
                timeout=60,
            )
            if resp.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"  下载: {filename}")
                return save_path
            else:
                logger.warning(f"  下载失败 {filename}: HTTP {resp.status_code}")
                return ""
        except requests.RequestException as e:
            logger.error(f"  下载异常 {filename}: {e}")
            return ""

    def upload_result(self, session_id: str, filename: str, local_path: str):
        """向服务端上传标注完成的 DWG"""
        try:
            with open(local_path, "rb") as f:
                resp = requests.post(
                    f"{self.server_url}/api/agent/upload_result/{session_id}/{filename}",
                    files={"file": (filename, f, "application/octet-stream")},
                    timeout=120,
                )
            data = resp.json()
            if data.get("success"):
                logger.info(f"  上传结果: {filename}")
            else:
                logger.warning(f"  上传失败 {filename}: {data.get('error')}")
        except requests.RequestException as e:
            logger.error(f"  上传异常 {filename}: {e}")

    def report_complete(self, task_id: str, results: dict):
        """上报任务完成"""
        try:
            resp = requests.post(
                f"{self.server_url}/api/agent/complete",
                json={
                    "agent_id": self.agent_id,
                    "task_id": task_id,
                    "status": "completed",
                    "progress": 1.0,
                    "results": results,
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("success"):
                logger.info("任务结果已上报")
            else:
                logger.warning(f"上报失败: {data.get('error')}")
            return data.get("success", False)
        except requests.RequestException as e:
            logger.error(f"上报结果时连接失败: {e}")
            return False

    def process_task(self, task: dict) -> dict:
        """执行标注任务"""
        task_id = task["id"]
        files = task["files"]
        mode = task.get("mode", "standard")
        config_data = task.get("config", {})
        ai_params = task.get("ai_params")
        session_id = task.get("session_id", "")

        self.status = "working"
        results = {}
        total = len(files)
        dim_total = 0

        logger.info(f"开始处理任务 {task_id}，共 {total} 个文件")

        if self.simulate:
            import random
            for idx, file_info in enumerate(files):
                if self._stop_flag.is_set():
                    return {"error": "任务已被取消"}
                file_name = file_info["name"]
                progress = round((idx + 0.5) / total * 100, 1)
                self.report_progress(task_id, progress, file_name)
                time.sleep(1.5)  # 模拟处理耗时
                dims = random.randint(3, 12)
                results[file_name] = {
                    "status": "completed",
                    "dims": dims,
                    "total_entities": random.randint(dims, dims + 20),
                }
                dim_total += dims
                progress = round((idx + 1) / total * 100, 1)
                self.report_progress(task_id, progress, file_name)
                logger.info(f"  [{idx+1}/{total}] {file_name} → 标注 {dims} 处")
            logger.info(f"任务 {task_id} 完成，共标注 {dim_total} 处")
            self.status = "idle"
            return {"results": results, "dim_total": dim_total}

        # ---------- 如有 session_id，从服务端下载文件 ----------
        work_dir = ""
        local_files = []
        if session_id:
            work_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "agent_work",
                session_id,
            )
            os.makedirs(work_dir, exist_ok=True)

            for file_info in files:
                if self._stop_flag.is_set():
                    return {"error": "任务已被取消"}
                fname = file_info["name"]
                local_path = self.download_file(session_id, fname, work_dir)
                if not local_path:
                    results[fname] = {"status": "failed", "error": "下载失败"}
                    continue
                local_files.append({
                    "name": fname,
                    "path": local_path,
                })
        else:
            # 传统模式：直接用 files 中的路径
            local_files = files

        if not local_files:
            return {"results": results, "error": "没有可处理的文件"}

        cad = None
        try:
            cad = AutoCADApp(visible=False)
            connected = cad.connect()
            if not connected:
                return {"error": "无法连接 AutoCAD"}

            dim_config = DimensionStyle.from_dict(config_data) if config_data else None

            for idx, file_info in enumerate(local_files):
                if self._stop_flag.is_set():
                    return {"error": "任务已被取消"}

                dwg_path = file_info["path"]
                file_name = file_info["name"]
                progress = round((idx + 0.5) / total * 100, 1)
                self.report_progress(task_id, progress, file_name)

                try:
                    cad.open_drawing(dwg_path)

                    # ★ 设置UNDO标记，之后可一键撤销
                    cad.set_undo_mark()

                    if mode == "standard":
                        result = auto_dimension_drawing(cad, dim_config)
                        results[file_name] = {
                            "status": "completed",
                            "dims": result.get("dimensioned", 0),
                            "total_entities": result.get("total", 0),
                        }
                        dim_total += result.get("dimensioned", 0)

                    elif mode == "ai":
                        if not ai_params:
                            raise ValueError("AI 模式需要 API 参数")
                        temp_id = uuid.uuid4().hex[:8]
                        png_path = os.path.join(
                            os.path.dirname(dwg_path),
                            f"_agent_temp_{temp_id}.png",
                        )
                        ai_result = ai_process_drawing(
                            cad=cad,
                            image_path=png_path,
                            api_key=ai_params["api_key"],
                            model_provider=ai_params.get("provider", "deepseek"),
                            api_base=ai_params.get("api_base"),
                            config=dim_config,
                        )
                        results[file_name] = {
                            "status": "completed" if ai_result["success"] else "failed",
                            "dims": ai_result.get("dim_count", 0),
                            "summary": ai_result.get("summary", ""),
                            "error": ai_result.get("error", ""),
                        }
                        dim_total += ai_result.get("dim_count", 0)
                        if os.path.exists(png_path):
                            os.remove(png_path)

                    try:
                        cad.save()
                    except Exception as e:
                        logger.warning(f"保存 {file_name} 失败: {e}")

                    cad.close_drawing(save=False)

                    # ★ 如果有 session_id，上传标注结果回服务端
                    if session_id:
                        self.upload_result(session_id, file_name, dwg_path)

                except Exception as e:
                    logger.warning(f"处理 {file_name} 失败: {e}")
                    results[file_name] = {"status": "failed", "error": str(e)}
                    try:
                        cad.close_drawing(save=False)
                    except Exception:
                        pass

                progress = round((idx + 1) / total * 100, 1)
                self.report_progress(task_id, progress, file_name)

            logger.info(f"任务 {task_id} 完成，共标注 {dim_total} 处")
            return {"results": results, "dim_total": dim_total}

        except Exception as e:
            logger.error(f"任务 {task_id} 失败: {e}")
            return {"error": str(e)}
        finally:
            if cad:
                try:
                    cad.disconnect()
                except Exception:
                    pass
            self.status = "idle"
            # 清理临时下载文件
            if work_dir and os.path.isdir(work_dir):
                import shutil
                try:
                    shutil.rmtree(work_dir, ignore_errors=True)
                except Exception:
                    pass

    def run(self):
        """主循环"""
        logger.info("=" * 50)
        logger.info("DWG Agent 启动")
        logger.info(f"Agent ID: {self.agent_id}")
        logger.info(f"主机名:   {self.hostname}")
        logger.info(f"服务器:   {self.server_url}")
        logger.info("=" * 50)

        # 1. 检测 CAD
        if not self.detect_cad():
            logger.error("未检测到 AutoCAD，Agent 退出")
            return

        # 2. 注册
        if not self.register():
            logger.error("注册失败，Agent 退出")
            return

        # 3. 启动心跳线程
        def heartbeat_loop():
            while not self._stop_flag.is_set():
                self._stop_flag.wait(HEARTBEAT_INTERVAL)
                if not self._stop_flag.is_set():
                    self.heartbeat()

        heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        heartbeat_thread.start()

        # 4. 主循环：轮询任务
        logger.info("开始轮询任务...")
        try:
            while not self._stop_flag.is_set():
                task = self.poll_task()
                if task:
                    logger.info(f"收到任务: {task['id']}")
                    result = self.process_task(task)
                    self.report_complete(task["id"], result)
                else:
                    self._stop_flag.wait(POLL_INTERVAL)
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在退出...")
        finally:
            self._stop_flag.set()
            heartbeat_thread.join(timeout=2)
            logger.info("Agent 已停止")


def main():
    parser = argparse.ArgumentParser(description="DWG 标注工厂 — 客户端 Agent")
    parser.add_argument(
        "server",
        nargs="?",
        default=DEFAULT_SERVER_URL,
        help=f"服务器地址 (默认: {DEFAULT_SERVER_URL})",
    )
    parser.add_argument(
        "--name", "-n",
        default="",
        help="显示名称 (默认: 本机主机名)",
    )
    parser.add_argument(
        "--simulate", "-s",
        action="store_true",
        help="模拟模式（无需 AutoCAD，用于测试）",
    )
    parser.add_argument(
        "--client", "-c",
        default="",
        help="客户端标识，与网页中的 client_id 一致（必填）",
    )
    args = parser.parse_args()

    if not args.client:
        print("错误：必须指定 --client 参数，与网页端的 client_id 一致")
        sys.exit(1)

    agent = DWGAgent(server_url=args.server, display_name=args.name, simulate=args.simulate, client_id=args.client)
    agent.run()


if __name__ == "__main__":
    main()
