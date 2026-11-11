# -*- coding: utf-8 -*-
"""
DWG Agent 后台静默运行器（无黑窗口）
双击安装后，作为后台进程自动运行。
支持 --server 指定服务器地址，默认 http://127.0.0.1:5000
"""

import os
import sys
import time
import subprocess
import logging

# 日志写入文件（不显示黑窗口）
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_service.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def main():
    # 从同目录的 config.ini 或命令行参数获取服务器地址
    server_url = "http://127.0.0.1:5000"

    # 尝试读取配置文件
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_config.ini")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                for line in f:
                    if line.startswith("server="):
                        server_url = line.strip().split("=", 1)[1].strip()
                        break
        except Exception:
            pass

    # 命令行参数覆盖
    if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
        server_url = sys.argv[1]

    # 查找 agent 脚本位置
    agent_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dwg_agent.py")

    # 构建命令行参数
    cmd = [sys.executable, agent_script, server_url]
    if "--client" in sys.argv:
        idx = sys.argv.index("--client")
        if idx + 1 < len(sys.argv):
            cmd.extend(["--client", sys.argv[idx + 1]])
    elif "-c" in sys.argv:
        idx = sys.argv.index("-c")
        if idx + 1 < len(sys.argv):
            cmd.extend(["--client", sys.argv[idx + 1]])

    logger.info("=" * 50)
    logger.info(f"DWG Agent 后台服务启动")
    logger.info(f"服务器: {server_url}")
    logger.info(f"Agent脚本: {agent_script}")
    logger.info("=" * 50)

    while True:
        try:
            logger.info("启动 Agent 进程...")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            # 等待进程结束
            stdout, stderr = proc.communicate()
            if stdout:
                logger.info(f"[stdout] {stdout.decode('utf-8', errors='replace')}")
            if stderr:
                logger.warning(f"[stderr] {stderr.decode('utf-8', errors='replace')}")

            logger.warning(f"Agent 进程退出（code: {proc.returncode}），10秒后重启...")
            time.sleep(10)
        except KeyboardInterrupt:
            logger.info("收到退出信号")
            break
        except Exception as e:
            logger.error(f"Agent 运行异常: {e}")
            time.sleep(30)


if __name__ == "__main__":
    main()
