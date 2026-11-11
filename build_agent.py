# -*- coding: utf-8 -*-
"""
DWG Agent 打包脚本
运行: python build_agent.py
生成: dist/agent_install/
"""

import os
import sys
import shutil

# 切换到脚本所在目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))

try:
    import PyInstaller
except ImportError:
    os.system("pip install pyinstaller")
    import PyInstaller

print("=" * 50)
print("DWG Agent 打包工具")
print("=" * 50)

# 清理旧构建
for d in ["build", "dist"]:
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)

# 用 PyInstaller 打包 agent_service.py
cmd = [
    "pyinstaller",
    "--onefile",           # 单个 exe
    "--console",           # 首次双击会显示控制台，有日志可看（后续可用 --noconsole）
    "--name", "DWGAgent",
    "--add-data", f"dwg_agent.py{os.pathsep}.",
    "--add-data", "dwg_processor;dwg_processor",
    "--add-data", "ai_adapters;ai_adapters",
    "--add-data", "recommendation;recommendation",
    "--hidden-import", "pywin32",
    "--hidden-import", "win32com",
    "--hidden-import", "pythoncom",
    "--hidden-import", "PIL",
    "agent_service.py",
]

print("正在打包，请等待...")
sys.stdout.flush()

result = os.system(" ".join(cmd))

if result == 0:
    print("\n✅ 打包成功！")
    print(f"\n生成文件: dist/DWGAgent.exe")
    print(f"\n使用方法:")
    print(f"  1. 把 DWGAgent.exe 发给客户端电脑")
    print(f"  2. 客户端双击运行（会显示一个黑窗口）")
    print(f"  3. 看到 '启动成功' 后即可关闭黑窗口（后续会在后台运行）")
    print(f"\n  或者创建快捷方式加参数:")
    print(f"    DWGAgent.exe http://你的IP:5000")
else:
    print("\n❌ 打包失败，检查上面错误信息")
