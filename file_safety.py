"""Local DWG upload path and filename boundaries. No CAD installation required."""
import ntpath
import re
from pathlib import Path

SESSION_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_WINDOWS_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def valid_session_id(value):
    return (isinstance(value, str) and SESSION_PATTERN.fullmatch(value) is not None
            and value.upper() not in RESERVED_WINDOWS_NAMES)


def validate_dwg_name(value):
    """Only a single portable DWG basename, not a path or a Windows device name."""
    if (not isinstance(value, str) or not 1 <= len(value) <= 170
            or value != value.strip(" .") or INVALID_WINDOWS_CHARS.search(value)
            or ntpath.basename(value) != value or not value.lower().endswith(".dwg")):
        raise ValueError("DWG 文件名无效")
    stem = value[:-4]
    if not stem or stem.split(".", 1)[0].upper() in RESERVED_WINDOWS_NAMES:
        raise ValueError("DWG 文件名无效")
    return value


def safe_storage_path(root_directory, session_id, filename=None, output=False):
    """Reject traversal and existing symlinks at every caller-controlled path segment."""
    if not valid_session_id(session_id):
        raise ValueError("会话标识无效")
    if filename is not None:
        validate_dwg_name(filename)
    root = Path(root_directory).resolve()
    session = root / session_id
    output_dir = session / "output"
    destination = (output_dir if output else session) / filename if filename else (output_dir if output else session)
    for node in (session, output_dir if output else None, destination):
        if node is not None and node.is_symlink():
            raise ValueError("不允许符号链接文件路径")
    try:
        destination.resolve().relative_to(root)
    except ValueError as exc:
        raise ValueError("文件路径超出上传目录") from exc
    return str(destination)


def public_files(files):
    """Never return absolute server file paths to browser / API clients."""
    return [{"name": item["name"], "size": item["size"]} for item in files]
