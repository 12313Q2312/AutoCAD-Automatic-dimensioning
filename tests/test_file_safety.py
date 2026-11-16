"""Local-only Flask regression tests. No AutoCAD, DWG parser, or network service."""
import io
import os
from pathlib import Path
import tempfile
import unittest

import app as web


def part(filename, content=b"DWG test bytes"):
    return (io.BytesIO(content), filename)


class FileSafetyApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "uploads"
        self.root.mkdir()
        self.old_root = web.app.config["UPLOAD_FOLDER"]
        self.old_limit = web.app.config["MAX_CONTENT_LENGTH"]
        web.app.config.update(TESTING=True, UPLOAD_FOLDER=str(self.root), MAX_CONTENT_LENGTH=1024 * 1024)
        self.client = web.app.test_client()
        web.UPLOAD_SESSION.clear()
        web.tasks.clear()
        web.agents.clear()
        if hasattr(web.app, "_pending_tasks"):
            web.app._pending_tasks.clear()
        self.addCleanup(self.restore)

    def restore(self):
        web.app.config.update(TESTING=False, UPLOAD_FOLDER=self.old_root, MAX_CONTENT_LENGTH=self.old_limit)
        web.UPLOAD_SESSION.clear()
        web.tasks.clear()
        web.agents.clear()

    def upload(self, name="part.dwg", session_id="sess_1", content=b"DWG demo"):
        return self.client.post(
            "/api/upload",
            data={"session_id": session_id, "client_id": "local-A", "files": part(name, content)},
            content_type="multipart/form-data",
        )

    def test_normal_upload_agent_and_download_do_not_leak_paths(self):
        response = self.upload(name="电机支架 01.dwg")
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(response.json["success"])
        self.assertEqual(response.json["files"], [{"name": "电机支架 01.dwg", "size": 8}])
        self.assertNotIn(str(self.root), str(response.json))

        info = self.client.get("/api/session/sess_1")
        self.assertEqual(info.status_code, 200)
        self.assertNotIn(str(self.root), str(info.json))
        self.assertEqual((self.root / "sess_1" / "电机支架 01.dwg").read_bytes(), b"DWG demo")

        original = self.client.get("/api/agent/download/sess_1/电机支架 01.dwg")
        self.assertEqual(original.status_code, 200)
        self.assertEqual(original.data, b"DWG demo")
        original.close()

        output = self.client.post(
            "/api/agent/upload_result/sess_1/电机支架 01.dwg",
            data=b"annotated bytes", content_type="application/octet-stream",
        )
        self.assertEqual(output.status_code, 200, output.json)
        self.assertEqual(output.json, {"success": True, "name": "电机支架 01_annotated.dwg"})
        self.assertEqual((self.root / "sess_1" / "output" / "电机支架 01_annotated.dwg").read_bytes(), b"annotated bytes")

        results = self.client.get("/api/results/sess_1")
        self.assertEqual(results.json["results"], [{"name": "电机支架 01_annotated.dwg", "size": 15}])
        self.assertNotIn(str(self.root), str(results.json))

        downloaded = self.client.get("/api/download/sess_1/电机支架 01.dwg")
        self.assertEqual(downloaded.data, b"annotated bytes")
        downloaded.close()

        # Authorized repeated agent upload replaces only the named output.
        retry = self.client.post(
            "/api/agent/upload_result/sess_1/电机支架 01.dwg",
            data=b"retry", content_type="application/octet-stream",
        )
        self.assertEqual(retry.status_code, 200)
        self.assertEqual((self.root / "sess_1" / "output" / "电机支架 01_annotated.dwg").read_bytes(), b"retry")

    def test_rejects_malicious_sessions_without_creating_dirs(self):
        for bad in ("../escape", "/tmp/evil", "..\\outside", "dot.session", "", "a" * 65):
            if bad == "":
                continue  # Empty form field deliberately requests server-generated ID.
            with self.subTest(session=bad):
                result = self.upload(session_id=bad)
                self.assertEqual(result.status_code, 400)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_rejects_malicious_filenames(self):
        names = ["../outside.dwg", "..\\outside.dwg", "/tmp/outside.dwg",
                 "C:\\Temp\\part.dwg", "folder/name.dwg", "CON.dwg",
                 "part.dwg:stream", "part.dwg.", "part.dwg ", "notes.txt"]
        for name in names:
            with self.subTest(filename=name):
                result = self.upload(name=name, session_id="badfile")
                self.assertEqual(result.status_code, 400, result.json)
                self.assertFalse((self.root / "badfile").exists())
        self.assertFalse((self.root.parent / "outside.dwg").exists())

    def test_duplicates_and_session_reuse_do_not_overwrite(self):
        dup = self.client.post("/api/upload", data={
            "session_id": "duplicated", "files": [part("Motor.dwg"), part("motor.DWG")]
        }, content_type="multipart/form-data")
        self.assertEqual(dup.status_code, 409)
        self.assertFalse((self.root / "duplicated").exists())

        self.assertEqual(self.upload(content=b"original").status_code, 200)
        second = self.upload(content=b"overwrite")
        self.assertEqual(second.status_code, 409)
        self.assertEqual((self.root / "sess_1" / "part.dwg").read_bytes(), b"original")

        (self.root / "stale").mkdir()
        stale = self.upload(session_id="stale")
        self.assertEqual(stale.status_code, 409)

    def test_agent_result_only_for_registered_filename(self):
        self.assertEqual(self.upload().status_code, 200)
        for path in ("/api/agent/upload_result/missing/part.dwg",
                     "/api/agent/upload_result/sess_1/unknown.dwg",
                     "/api/agent/upload_result/sess_1/CON.dwg"):
            with self.subTest(path=path):
                response = self.client.post(path, data=b"bad", content_type="application/octet-stream")
                self.assertEqual(response.status_code, 404)
        self.assertFalse((self.root / "sess_1" / "output").exists())
        self.assertEqual(self.client.get("/api/download/sess_1/unknown.dwg").status_code, 404)

    def test_unrecognized_session_does_not_fall_back_to_paths(self):
        response = self.client.post("/api/start", json={
            "session_id": "missing", "files": [{"name": "outside.dwg", "path": "/somewhere/outside.dwg"}]
        })
        self.assertEqual(response.status_code, 404)
        self.assertEqual(web.tasks, {})

    def test_upload_limit_returns_json(self):
        web.app.config["MAX_CONTENT_LENGTH"] = 512
        result = self.upload(content=b"x" * 2048)
        self.assertEqual(result.status_code, 413)
        self.assertFalse(result.json["success"])
        self.assertFalse((self.root / "sess_1").exists())

    def test_rejects_preexisting_symlink(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        try:
            (self.root / "linked").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable on this runner")
        result = self.upload(session_id="linked")
        self.assertEqual(result.status_code, 400)
        self.assertEqual(list(outside.iterdir()), [])

    def test_progress_excludes_internal_paths(self):
        web.tasks["task1"] = {
            "id": "task1", "status": "completed", "progress": 100,
            "total": 1, "current": 1, "results": {
                "part.dwg": {"status": "completed", "dwg_path": "C:\\private\\part.dwg"}
            }
        }
        response = self.client.get("/api/progress/task1")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("dwg_path", str(response.json))


if __name__ == "__main__":
    unittest.main()
