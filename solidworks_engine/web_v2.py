"""Loopback Flask routes for the DraftPilot v2 workspace."""
import ipaddress
import json
import os
import sys
from urllib.parse import urlsplit

from flask import Blueprint, jsonify, request, send_file

from .cloud import AUDIO_LIMIT, IMAGE_LIMIT, CloudProvider, ProviderError, normalize_sketch
from .dialogue import NUMBER_FIELDS, apply_turn, validate_state
from .model import ModelPlanError
from .native import NativeError, native_archive
from .plate_v2 import FIELDS, validate_plate

bp = Blueprint("draftpilot_v2", __name__)
TEXT_LIMIT = 1000
AUDIO_TYPES = {"audio/webm": "recording.webm", "audio/mp4": "recording.m4a", "audio/ogg": "recording.ogg"}


@bp.before_request
def local_request():
    try:
        host = urlsplit(request.host_url).hostname
    except ValueError:
        return jsonify(error="请求地址无效"), 400
    origin = request.headers.get("Origin")
    try:
        loopback_peer = ipaddress.ip_address(request.remote_addr).is_loopback
    except (TypeError, ValueError):
        loopback_peer = False
    if (host not in ("localhost", "127.0.0.1", "::1") or not loopback_peer
            or (origin and origin != request.host_url.rstrip("/"))):
        return jsonify(error="请从本机 DraftPilot 工作台提交"), 403


@bp.errorhandler(ModelPlanError)
def model_error(exc):
    return jsonify(error=str(exc), field=exc.field), 422


@bp.errorhandler(ProviderError)
def provider_error(exc):
    return jsonify(error=str(exc)), 503


@bp.errorhandler(NativeError)
def native_error(exc):
    return jsonify(error=str(exc)), 503


def _body_limit(limit):
    # Check before Flask parses JSON or multipart. Browser requests provide a length.
    if request.content_length is None or request.content_length > limit:
        raise ModelPlanError("请求过大或缺少内容长度，请缩短输入", "request")


@bp.get("/api/model/v2/status")
def status():
    cloud = bool(os.getenv("DRAFTPILOT_API_KEY") and os.getenv("DRAFTPILOT_MODEL"))
    return jsonify(cloud_configured=cloud, voice_configured=cloud and bool(
        os.getenv("DRAFTPILOT_TRANSCRIPTION_MODEL")), native_available=sys.platform == "win32")


@bp.post("/api/model/v2/turn")
def turn():
    _body_limit(IMAGE_LIMIT + 64 * 1024)
    sketch = None
    if request.mimetype == "multipart/form-data":
        raw_state = request.form.get("state", "null")
        try:
            state = json.loads(raw_state)
        except (ValueError, RecursionError):
            return jsonify(error="对话状态无效"), 400
        text = request.form.get("text", "")
        file = request.files.get("sketch")
        if file is None:
            return jsonify(error="请选择草图"), 400
        sketch = normalize_sketch(file.stream.read(IMAGE_LIMIT + 1))
    else:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error="请求应为 JSON 对象"), 400
        state, text = body.get("state"), body.get("text", "")
    if not isinstance(text, str) or len(text) > TEXT_LIMIT or (not text.strip() and sketch is None):
        return jsonify(error="请输入 1 至 1000 字的描述，或选择草图"), 400
    draft, plan, pending_hole = validate_state(state)
    missing = next((key for key in FIELDS if key not in draft), None) if plan is None else None
    proposal = CloudProvider.from_env().interpret(text.strip(), draft, plan, missing, sketch, pending_hole)
    if not text.strip() and isinstance(proposal, dict) and any(
            proposal.get(field) is not None for field in NUMBER_FIELDS):
        raise ModelPlanError("请用文字或语音明确尺寸，草图仅提供布局", "sketch")
    return jsonify(apply_turn(draft, plan, proposal, sketch is not None, pending_hole))


@bp.post("/api/model/v2/transcribe")
def transcribe():
    _body_limit(AUDIO_LIMIT + 16 * 1024)
    audio = request.files.get("audio")
    if audio is None or audio.mimetype not in AUDIO_TYPES:
        return jsonify(error="请选择 WebM、M4A 或 Ogg 录音"), 400
    data = audio.stream.read(AUDIO_LIMIT + 1)
    if not data or len(data) > AUDIO_LIMIT:
        return jsonify(error="录音为空或超过 4 MiB，请重新录制"), 400
    text = CloudProvider.from_env().transcribe(data, AUDIO_TYPES[audio.mimetype], audio.mimetype)
    return jsonify(text=text)


@bp.post("/api/model/v2/native")
def native():
    _body_limit(64 * 1024)
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"plan"}:
        return jsonify(error="请选择并确认一份安装板预览"), 400
    archive = native_archive(validate_plate(body["plan"]))
    response = send_file(archive, mimetype="application/zip", as_attachment=True,
                         download_name="DraftPilot_SolidWorks.zip", max_age=0)
    response.cache_control.no_store = True
    return response
