"""
Flask 后端主入口
提供 DWG 扫描、批量标注、AI 模式、推荐等 API
"""

import os
import json
import uuid
import logging
import threading
from datetime import datetime
from typing import Optional

from flask import Flask, request, jsonify, send_from_directory, send_file

from dwg_processor.cad_com import AutoCADApp, detect_installed_cad, AutoCADError
from dwg_processor.auto_dim import auto_dimension_drawing
from dwg_processor.ai_processor import ai_process_drawing
from dwg_processor.style_config import DimensionStyle, GB_PRESETS
from recommendation.engine import RecommendationEngine

# ---------- 配置 ----------
app = Flask(__name__, static_folder="static", static_url_path="")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 全局推荐引擎
recommender = RecommendationEngine()

# 任务进度存储
tasks: dict = {}

# 分布式 Agent 注册表
agents: dict = {}


# ---------- 工具函数 ----------

def _scan_dwg_files(folder: str) -> list:
    """扫描文件夹下所有 .dwg 文件"""
    if not os.path.isdir(folder):
        return []
    files = []
    for f in os.listdir(folder):
        if f.lower().endswith(".dwg"):
            full_path = os.path.join(folder, f)
            files.append({
                "name": f,
                "path": full_path,
                "size": os.path.getsize(full_path),
                "mtime": os.path.getmtime(full_path),
            })
    return sorted(files, key=lambda x: x["name"])


def _batch_process_task(task_id: str, files: list, config: dict, mode: str, ai_params: Optional[dict]):
    """后台批量标注任务"""
    task = tasks[task_id]
    task["status"] = "running"
    task["started_at"] = datetime.now().isoformat()
    task["total"] = len(files)

    cad = AutoCADApp(visible=False)

    try:
        # 连接 AutoCAD
        connected = cad.connect()
        if not connected:
            task["status"] = "failed"
            task["error"] = "未检测到 AutoCAD，请确认已安装 AutoCAD 2024/2025/2026"
            return

        task["cad_version"] = cad.version_name or cad.version

        for idx, file_info in enumerate(files):
            dwg_path = file_info["path"]
            task["current"] = idx + 1
            task["current_file"] = file_info["name"]
            task["results"][file_info["name"]] = {"status": "processing", "dims": 0}

            try:
                # 打开 DWG
                cad.open_drawing(dwg_path)

                # ★ 标记撤销点：标注前打标记，以便之后一键撤销
                if not task.get("undo_marks"):
                    task["undo_marks"] = {}
                task["undo_marks"][file_info["name"]] = True
                cad.set_undo_mark()

                if mode == "standard":
                    # 标准模式：自动几何识别标注
                    dim_config = DimensionStyle.from_dict(config) if config else None
                    result = auto_dimension_drawing(cad, dim_config)
                    dim_count = result.get("dimensioned", 0)
                    task["results"][file_info["name"]] = {
                        "status": "completed",
                        "dims": dim_count,
                        "total_entities": result.get("total", 0),
                        "dwg_path": dwg_path,  # 存路径，撤销时用
                    }

                elif mode == "ai":
                    # AI 模式：大模型分析后标注
                    if not ai_params:
                        raise ValueError("AI 模式需要提供 API 参数")

                    png_path = os.path.join(
                        app.config["UPLOAD_FOLDER"],
                        f"{uuid.uuid4().hex}_{file_info['name']}.png",
                    )
                    result = ai_process_drawing(
                        cad=cad,
                        image_path=png_path,
                        api_key=ai_params["api_key"],
                        model_provider=ai_params.get("provider", "deepseek"),
                        api_base=ai_params.get("api_base"),
                        config=DimensionStyle.from_dict(config) if config else None,
                    )
                    task["results"][file_info["name"]] = {
                        "status": "completed" if result["success"] else "failed",
                        "dims": result.get("dim_count", 0),
                        "summary": result.get("summary", ""),
                        "error": result.get("error", ""),
                        "dwg_path": dwg_path,  # 存路径，撤销时用
                    }
                    # 清理临时 PNG
                    if os.path.exists(png_path):
                        os.remove(png_path)

                # 保存
                try:
                    cad.save()
                except Exception as e:
                    logger.warning(f"保存 {file_info['name']} 失败: {e}")

                cad.close_drawing(save=True)

            except Exception as e:
                logger.error(f"处理 {file_info['name']} 失败: {e}")
                task["results"][file_info["name"]] = {
                    "status": "failed",
                    "error": str(e),
                }
                try:
                    cad.close_drawing(save=False)
                except:
                    pass

            task["progress"] = round((idx + 1) / len(files) * 100, 1)

        # ★ 标注完成，标记可撤销
        task["has_undo"] = True

        # 任务完成
        task["status"] = "completed"
        task["completed_at"] = datetime.now().isoformat()
        task["progress"] = 100

    except Exception as e:
        logger.error(f"批量任务整体失败: {e}")
        task["status"] = "failed"
        task["error"] = str(e)
    finally:
        try:
            cad.disconnect()
        except:
            pass


# ---------- API 路由 ----------

@app.route("/")
def index():
    """前端主页"""
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """扫描文件夹，返回 .dwg 文件列表"""
    data = request.get_json(silent=True) or {}
    folder = data.get("folder", "")

    if not folder:
        return jsonify({"success": False, "error": "请提供文件夹路径"})

    if not os.path.isdir(folder):
        return jsonify({"success": False, "error": f"文件夹不存在: {folder}"})

    files = _scan_dwg_files(folder)
    return jsonify({
        "success": True,
        "folder": folder,
        "files": files,
        "count": len(files),
    })


@app.route("/api/detect_cad", methods=["POST"])
def api_detect_cad():
    """检测 AutoCAD 安装版本"""
    result = detect_installed_cad()
    if result:
        return jsonify({"success": True, "version": result})
    return jsonify({"success": False, "error": "未检测到 AutoCAD"})


@app.route("/api/gb_presets", methods=["GET"])
def api_gb_presets():
    """获取国标预设列表"""
    presets = {}
    for name, style in GB_PRESETS.items():
        presets[name] = style.to_dict()
    return jsonify({"success": True, "presets": presets})


@app.route("/api/start", methods=["POST"])
def api_start():
    """启动批量标注任务"""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    files_data = data.get("files", [])  # [{name, path, ...}]
    config = data.get("config", {})
    mode = data.get("mode", "standard")
    ai_params = data.get("ai_params")

    # 支持 session_id 方式（客户端上传的文件）
    if session_id and session_id in UPLOAD_SESSION:
        session = UPLOAD_SESSION[session_id]
        files = session["files"]
    elif files_data:
        files = files_data if isinstance(files_data, list) else []
    else:
        return jsonify({"success": False, "error": "请提供文件"})

    if not files:
        return jsonify({"success": False, "error": "没有需要处理的文件"})

    # 创建任务
    task_id = uuid.uuid4().hex[:12]
    # 从上传会话获取 client_id
    client_id = ""
    if session_id and session_id in UPLOAD_SESSION:
        client_id = UPLOAD_SESSION[session_id].get("client_id", "")
    tasks[task_id] = {
        "id": task_id,
        "status": "queued",
        "progress": 0,
        "total": len(files),
        "current": 0,
        "current_file": "",
        "results": {},
        "error": "",
        "files": files,  # 存文件列表，撤销时用
        "session_id": session_id,  # 上传文件的会话ID
        "client_id": client_id,
    }

    task_payload = {
        "id": task_id, "task_id": task_id,
        "files": files, "mode": mode,
        "config": config, "ai_params": ai_params,
        "session_id": session_id,
        "client_id": client_id,
    }

    # 派发任务：只派给同 client_id 的空闲 Agent
    def _find_matching_agent(cid):
        for aid, info in agents.items():
            if info.get("status") == "idle" and not info.get("task_queue"):
                if info.get("client_id") == cid:
                    return aid
        return None

    if client_id:
        match = _find_matching_agent(client_id)
        if match:
            task_payload["files"] = [{
                "name": f["name"],
                "session_id": session_id,
            } for f in files]
            agents[match]["task_queue"].append(task_payload)
            tasks[task_id]["dispatched_to"] = match
            logger.info(f"Task {task_id} dispatched to agent {match} (client: {client_id})")
        else:
            tasks[task_id]["status"] = "queued"
            tasks[task_id]["waiting_for_agent"] = True
            if not hasattr(app, "_pending_tasks"):
                app._pending_tasks = []
            app._pending_tasks.append((task_id, task_payload))
            logger.info(f"Task {task_id} queued for client: {client_id}")
    else:
        tasks[task_id]["status"] = "queued"
        tasks[task_id]["waiting_for_agent"] = True
        if not hasattr(app, "_pending_tasks"):
            app._pending_tasks = []
        app._pending_tasks.append((task_id, task_payload))
        logger.info(f"Task {task_id} queued (no client_id)")

    return jsonify({
        "success": True,
        "task_id": task_id,
        "total_files": len(files),
    })


@app.route("/api/progress/<task_id>")
def api_progress(task_id: str):
    """查询任务进度"""
    task = tasks.get(task_id)
    if not task:
        return jsonify({"success": False, "error": "任务不存在"})

    return jsonify({
        "success": True,
        "task": {
            "id": task["id"],
            "status": task["status"],
            "progress": task["progress"],
            "total": task["total"],
            "current": task["current"],
            "current_file": task.get("current_file", ""),
            "results": task.get("results", {}),
            "error": task.get("error", ""),
            "cad_version": task.get("cad_version", ""),
            "started_at": task.get("started_at", ""),
            "completed_at": task.get("completed_at", ""),
            "has_undo": task.get("has_undo", False),
            "undo_progress": task.get("undo_progress", 0),
            "waiting_for_agent": task.get("waiting_for_agent", False),
        }
    })


@app.route("/api/recommendations", methods=["POST"])
def api_recommendations():
    """获取 Top3 推荐配置"""
    data = request.get_json(silent=True) or {}
    current_config = data.get("current_config")
    top3 = recommender.get_top3(current_config)
    return jsonify({"success": True, "recommendations": top3})


@app.route("/api/record_usage", methods=["POST"])
def api_record_usage():
    """记录用户使用配置"""
    data = request.get_json(silent=True) or {}
    config = data.get("config", {})
    mode = data.get("mode", "standard")
    folder = data.get("folder", "")

    recommender.record_usage(config, mode, folder)
    return jsonify({"success": True})


@app.route("/api/task_list", methods=["GET"])
def api_task_list():
    """获取所有任务列表"""
    task_list = []
    for tid, task in tasks.items():
        task_list.append({
            "id": tid,
            "status": task["status"],
            "progress": task["progress"],
            "total": task["total"],
            "current": task["current"],
            "current_file": task.get("current_file", ""),
        })
    return jsonify({"success": True, "tasks": task_list})


# ---------- 客户端文件上传 ----------

UPLOAD_SESSION: dict = {}  # session_id -> {"files": [...], "created_at": ...}

@app.route("/api/upload", methods=["POST"])
def api_upload():
    """客户端上传 DWG 文件"""
    session_id = request.form.get("session_id", uuid.uuid4().hex[:12])
    client_id = request.form.get("client_id", "")
    uploaded = request.files.getlist("files")

    if not uploaded:
        return jsonify({"success": False, "error": "请选择文件"})

    session_dir = os.path.join(app.config["UPLOAD_FOLDER"], session_id)
    os.makedirs(session_dir, exist_ok=True)

    files = []
    for f in uploaded:
        if not f.filename.lower().endswith(".dwg"):
            continue
        save_path = os.path.join(session_dir, f.filename)
        f.save(save_path)
        files.append({
            "name": f.filename,
            "path": save_path,
            "size": os.path.getsize(save_path),
        })

    if not files:
        return jsonify({"success": False, "error": "没有有效的 DWG 文件"})

    UPLOAD_SESSION[session_id] = {
        "files": files,
        "client_id": client_id,
        "created_at": datetime.now().isoformat(),
    }

    logger.info(f"上传会话: {session_id}, client: {client_id}, {len(files)} 个文件")
    return jsonify({
        "success": True,
        "session_id": session_id,
        "client_id": client_id,
        "files": files,
        "count": len(files),
    })


@app.route("/api/session/<session_id>", methods=["GET"])
def api_session(session_id: str):
    """查询上传会话信息"""
    session = UPLOAD_SESSION.get(session_id)
    if not session:
        return jsonify({"success": False, "error": "会话不存在"})
    return jsonify({
        "success": True,
        "session_id": session_id,
        "files": session["files"],
        "count": len(session["files"]),
        "created_at": session["created_at"],
    })


@app.route("/api/download/<session_id>/<filename>")
def api_download(session_id: str, filename: str):
    """客户端下载标注完成的 DWG"""
    session = UPLOAD_SESSION.get(session_id)
    if not session:
        return jsonify({"success": False, "error": "会话不存在"}), 404

    # 从会话中找对应文件
    file_info = None
    for f in session.get("files", []):
        if f["name"] == filename:
            file_info = f
            break

    if not file_info:
        return jsonify({"success": False, "error": "文件不存在"}), 404

    # 尝试 output 版本（标注后的），没有则返回原文件
    base_name, ext = os.path.splitext(filename)
    output_name = f"{base_name}_annotated{ext}"
    output_dir = os.path.join(app.config["UPLOAD_FOLDER"], session_id, "output")
    output_path = os.path.join(output_dir, output_name)

    if os.path.exists(output_path):
        return send_file(output_path, as_attachment=True, download_name=output_name)
    elif os.path.exists(file_info["path"]):
        return send_file(file_info["path"], as_attachment=True, download_name=filename)
    else:
        return jsonify({"success": False, "error": "文件不存在"}), 404


@app.route("/api/agent/download/<session_id>/<filename>")
def api_agent_download(session_id: str, filename: str):
    """Agent 下载待处理的 DWG 文件"""
    session = UPLOAD_SESSION.get(session_id)
    if not session:
        return jsonify({"success": False, "error": "会话不存在"}), 404

    file_info = None
    for f in session.get("files", []):
        if f["name"] == filename:
            file_info = f
            break

    if not file_info or not os.path.exists(file_info["path"]):
        return jsonify({"success": False, "error": "文件不存在"}), 404

    return send_file(file_info["path"], as_attachment=True, download_name=filename)


@app.route("/api/agent/upload_result/<session_id>/<filename>", methods=["POST"])
def api_agent_upload_result(session_id: str, filename: str):
    """Agent 上传标注完成的 DWG"""
    output_dir = os.path.join(app.config["UPLOAD_FOLDER"], session_id, "output")
    os.makedirs(output_dir, exist_ok=True)

    base_name, ext = os.path.splitext(filename)
    output_name = f"{base_name}_annotated{ext}"
    save_path = os.path.join(output_dir, output_name)

    if "file" in request.files:
        f = request.files["file"]
        f.save(save_path)
    elif request.data:
        with open(save_path, "wb") as f:
            f.write(request.data)
    else:
        return jsonify({"success": False, "error": "没有文件数据"})

    logger.info(f"Agent 上传标注结果: {output_name}")
    return jsonify({"success": True, "path": save_path})


@app.route("/api/results/<session_id>")
def api_results(session_id: str):
    """查询任务结果（供下载列表使用）"""
    session = UPLOAD_SESSION.get(session_id)
    if not session:
        return jsonify({"success": False, "error": "会话不存在"})

    output_dir = os.path.join(app.config["UPLOAD_FOLDER"], session_id, "output")
    results = []
    if os.path.isdir(output_dir):
        for fname in os.listdir(output_dir):
            if fname.lower().endswith(".dwg"):
                results.append({
                    "name": fname,
                    "path": os.path.join(output_dir, fname),
                    "size": os.path.getsize(os.path.join(output_dir, fname)),
                })

    return jsonify({
        "success": True,
        "session_id": session_id,
        "original_count": len(session.get("files", [])),
        "results": results,
    })


# ---------- 启动 ----------


# ---------- Agent ----------

@app.route("/api/agent/register", methods=["POST"])
def api_agent_register():
    data = request.get_json(silent=True) or {}
    agent_id = data.get("agent_id", "")
    if not agent_id:
        return jsonify({"success": False, "error": "missing agent_id"})
    agents[agent_id] = {
        "agent_id": agent_id,
        "hostname": data.get("hostname", ""),
        "display_name": data.get("display_name", agent_id),
        "cad_version": data.get("cad_version", ""),
        "client_id": data.get("client_id", ""),
        "status": "idle",
        "last_seen": datetime.now().isoformat(),
        "current_task_id": None,
        "task_queue": [],
    }
    logger.info(f"Agent registered: {agent_id} (client: {data.get('client_id', '')})")
    # 检查是否有等待中的任务（只派同 client_id 的）
    if hasattr(app, "_pending_tasks") and app._pending_tasks:
        cid = data.get("client_id", "")
        still_pending = []
        for task_id, payload in app._pending_tasks:
            if payload.get("client_id") == cid and len(agents[agent_id].get("task_queue", [])) == 0:
                agents[agent_id]["task_queue"].append(payload)
                tasks[task_id]["dispatched_to"] = agent_id
                tasks[task_id]["status"] = "queued"
                logger.info(f"Pending task {task_id} dispatched to {agent_id}")
            else:
                still_pending.append((task_id, payload))
        app._pending_tasks = still_pending

    return jsonify({"success": True, "agent_id": agent_id})


@app.route("/api/agent/heartbeat", methods=["POST"])
def api_agent_heartbeat():
    data = request.get_json(silent=True) or {}
    agent_id = data.get("agent_id", "")
    if agent_id in agents:
        agents[agent_id]["last_seen"] = datetime.now().isoformat()
        if agents[agent_id].get("status") == "offline":
            agents[agent_id]["status"] = "idle"
        # 检查是否有等待中的任务（只派同 client_id 的）
        if hasattr(app, "_pending_tasks") and app._pending_tasks:
            cid = agents[agent_id].get("client_id", "")
            still_pending = []
            for task_id, payload in app._pending_tasks:
                if payload.get("client_id") == cid and len(agents[agent_id].get("task_queue", [])) == 0:
                    agents[agent_id]["task_queue"].append(payload)
                    tasks[task_id]["dispatched_to"] = agent_id
                    tasks[task_id]["status"] = "queued"
                    logger.info(f"Pending task {task_id} dispatched to {agent_id}")
                else:
                    still_pending.append((task_id, payload))
            app._pending_tasks = still_pending

        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Agent not registered"})


@app.route("/api/agent/task/<agent_id>")
def api_agent_task(agent_id: str):
    agent = agents.get(agent_id)
    if not agent:
        return jsonify({"success": False, "error": "Agent not registered"})
    agent["last_seen"] = datetime.now().isoformat()
    if agent["task_queue"]:
        task_info = agent["task_queue"].pop(0)
        task_id = task_info["task_id"]
        if task_id in tasks:
            tasks[task_id]["status"] = "running"
            tasks[task_id]["agent_id"] = agent_id
            tasks[task_id]["started_at"] = datetime.now().isoformat()
            tasks[task_id]["waiting_for_agent"] = False  # 已分配到 Agent
            agent["status"] = "working"
            agent["current_task_id"] = task_id
            return jsonify({"success": True, "has_task": True, "task": task_info})
    agent["status"] = "idle"
    return jsonify({"success": True, "has_task": False})


@app.route("/api/agent/complete", methods=["POST"])
def api_agent_complete():
    data = request.get_json(silent=True) or {}
    agent_id = data.get("agent_id", "")
    task_id = data.get("task_id", "")
    status = data.get("status", "completed")
    if agent_id in agents:
        agents[agent_id]["last_seen"] = datetime.now().isoformat()
    if status == "completed" and task_id in tasks:
        task = tasks[task_id]
        task["status"] = "completed"
        task["progress"] = 100
        task["current"] = task.get("total", 0)
        task["completed_at"] = datetime.now().isoformat()
        task["has_undo"] = True
        if "results" in data:
            raw = data["results"]
            task["results"] = raw.get("results", raw)
        # Agent上报的结果补上dwg_path（从派发时记的files里取）
        if task.get("files"):
            for f in task["files"]:
                fname = f["name"]
                if fname in task.get("results", {}):
                    task["results"][fname]["dwg_path"] = f["path"]
        if agent_id in agents:
            agents[agent_id]["status"] = "idle"
            agents[agent_id]["current_task_id"] = None
        logger.info(f"Agent {agent_id} task {task_id} done")
        return jsonify({"success": True})
    elif status == "processing" and task_id in tasks:
        task = tasks[task_id]
        task["progress"] = data.get("progress", task.get("progress", 0))
        task["current_file"] = data.get("current_file", "")
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "invalid"})


@app.route("/api/agents", methods=["GET"])
def api_agents():
    now = datetime.now()
    agent_list = []
    for agent_id, agent in agents.items():
        try:
            last_seen = datetime.fromisoformat(agent["last_seen"])
            offline_seconds = (now - last_seen).total_seconds()
        except Exception:
            offline_seconds = 999
        if offline_seconds > 60 and agent.get("status") != "working":
            agent["status"] = "offline"
        agent_list.append({
            "agent_id": agent_id,
            "hostname": agent.get("hostname", ""),
            "display_name": agent.get("display_name", agent_id),
            "cad_version": agent.get("cad_version", ""),
            "status": agent.get("status", "offline"),
            "last_seen": agent.get("last_seen", ""),
            "current_task_id": agent.get("current_task_id"),
        })
    return jsonify({"success": True, "agents": agent_list})


@app.route("/api/undo/<task_id>", methods=["POST"])
def api_undo(task_id: str):
    """撤销指定任务的所有标注操作"""
    task = tasks.get(task_id)
    if not task:
        return jsonify({"success": False, "error": "任务不存在"})

    files_data = []
    for fname, result in task.get("results", {}).items():
        if result.get("status") == "completed":
            files_data.append(fname)

    if not files_data:
        return jsonify({"success": False, "error": "没有需要撤销的文件"})

    # 后台执行撤销
    def _undo_task(tid, fnames):
        t = tasks[tid]
        t["status"] = "undoing"
        t["undo_progress"] = 0
        t["undo_total"] = len(fnames)
        t["undo_current"] = 0

        cad = AutoCADApp(visible=False)
        try:
            connected = cad.connect()
            if not connected:
                t["status"] = "failed"
                t["error"] = "撤销失败：无法连接 AutoCAD"
                return

            all_results = t.get("results", {})
            for idx, fname in enumerate(fnames):
                file_result = all_results.get(fname, {})
                dwg_path = file_result.get("dwg_path", "")
                if not dwg_path:
                    continue

                t["undo_current"] = idx + 1
                t["undo_current_file"] = fname
                try:
                    cad.open_drawing(dwg_path)
                    cad.undo_to_mark()
                    cad.save()
                    cad.close_drawing(save=True)
                    logger.info(f"撤销完成: {fname}")
                except Exception as e:
                    logger.warning(f"撤销 {fname} 失败: {e}")
                    try:
                        cad.close_drawing(save=False)
                    except:
                        pass

                t["undo_progress"] = round((idx + 1) / len(fnames) * 100, 1)

            t["status"] = "completed"
            t["undo_progress"] = 100
            t["completed_at"] = datetime.now().isoformat()
            logger.info(f"撤销任务 {tid} 全部完成")
        except Exception as e:
            logger.error(f"撤销任务整体失败: {e}")
            t["status"] = "failed"
            t["error"] = str(e)
        finally:
            try:
                cad.disconnect()
            except:
                pass

    thread = threading.Thread(target=_undo_task, args=(task_id, files_data), daemon=True)
    thread.start()

    return jsonify({"success": True, "total": len(files_data)})


@app.route("/api/undo_progress/<task_id>")
def api_undo_progress(task_id: str):
    """查询撤销进度"""
    task = tasks.get(task_id)
    if not task:
        return jsonify({"success": False, "error": "任务不存在"})
    return jsonify({
        "success": True,
        "status": task.get("status"),
        "undo_progress": task.get("undo_progress", 0),
        "undo_total": task.get("undo_total", 0),
        "undo_current": task.get("undo_current", 0),
        "undo_current_file": task.get("undo_current_file", ""),
    })


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("DWG 标注工厂 启动")
    logger.info(f"上传目录: {app.config['UPLOAD_FOLDER']}")
    logger.info(f"访问地址: http://localhost:5000")
    logger.info("=" * 50)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
