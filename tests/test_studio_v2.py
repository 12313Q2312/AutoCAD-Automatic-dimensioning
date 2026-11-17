"""DraftPilot v2 tests. Provider and SolidWorks boundaries use explicit fakes."""
import base64
from copy import deepcopy
from io import BytesIO
import json
from math import nan
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

import app as cad_app
from solidworks_engine.cloud import CloudProvider, ProviderError
from solidworks_engine.dialogue import NUMBER_FIELDS
from solidworks_engine.model import ModelPlanError
from solidworks_engine.native import NativeError, _verify_geometry
from solidworks_engine.plate_v2 import from_symmetric_parameters, validate_plate

PARAMETERS = {"length_mm": 120, "width_mm": 80, "thickness_mm": 8,
              "hole_diameter_mm": 10, "pitch_x_mm": 90, "pitch_y_mm": 50}


def proposal(action="dimensions", hole=None, sketch="none", **values):
    return {"action": action, "hole": hole, "sketch": sketch,
            **{field: values.get(field) for field in NUMBER_FIELDS}}


def holes(plan):
    return plan["features"][1]["sketch"]["holes"]


def png():
    image = BytesIO()
    Image.new("RGB", (40, 25), "white").save(image, "PNG")
    return image.getvalue()


class DialogueRoutes(unittest.TestCase):
    def setUp(self):
        self.client = cad_app.app.test_client()
        self.provider_patch = patch("solidworks_engine.web_v2.CloudProvider.from_env")
        self.provider = self.provider_patch.start().return_value
        self.addCleanup(self.provider_patch.stop)

    def turn(self, model_result, state=None, text="测试输入"):
        self.provider.interpret.return_value = model_result
        return self.client.post("/api/model/v2/turn", json={"text": text, "state": state})

    def make_ready(self):
        response = self.turn(proposal(**PARAMETERS))
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["state"]

    def test_v2_workspace_and_v1_route(self):
        with self.client.get("/draftpilot") as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"/draftpilot.js", response.data)
        with self.client.get("/studio") as response:
            self.assertIn(b'href="/draftpilot"', response.data)
        response = self.client.post("/api/model/plan", json={
            "mode": "parameters", "part_type": "mounting_plate", "parameters": PARAMETERS,
        })
        self.assertEqual(response.json["plan"]["schema_version"], "1.0")

    def test_missing_dimensions_follow_up_then_export_preview(self):
        first = self.turn(proposal(length_mm=120, width_mm=80),
                          text="做块十二乘八厘米的板，四角打孔").json
        self.assertEqual(first["message"], "板有多厚？")
        self.assertIsNone(first["state"]["plan"])
        self.assertIsNone(first["preview_svg"])
        second = self.turn(proposal(thickness_mm=8), first["state"], text="八毫米").json
        self.assertEqual(self.provider.interpret.call_args.args[3], "thickness_mm")
        self.assertIn("直径", second["message"])
        ready = self.turn(proposal(hole_diameter_mm=10, pitch_x_mm=90, pitch_y_mm=50),
                          second["state"]).json
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["state"]["plan"]["bounding_box_mm"], [120, 80, 8])
        self.assertEqual(ready["preview_svg"].count("<circle "), 4)

    def test_single_hole_moves_and_previous_plan_stays_intact(self):
        original = self.make_ready()
        result = self.turn(proposal("hole_edit", "top_left", delta_x_mm=3),
                           original, text="左上角的孔向右移动三毫米")
        self.assertEqual(result.status_code, 200, result.json)
        updated = holes(result.json["state"]["plan"])
        before = holes(original["plan"])
        self.assertEqual(updated[0]["x_mm"], -42)
        self.assertEqual(before[0]["x_mm"], -45)
        self.assertEqual(updated[1:], before[1:])

    def test_pair_diameter_clarification_uses_pending_target(self):
        original = self.make_ready()
        question = self.turn(proposal("hole_edit", "right"), original,
                             text="右边两个孔改大一点").json
        self.assertEqual(question["status"], "clarify")
        self.assertEqual(question["state"]["pending_hole"], "right")
        response = self.turn(proposal("hole_edit", "right", new_diameter_mm=12),
                             question["state"], text="直径十二毫米")
        self.assertEqual(self.provider.interpret.call_args.args[-1], "right")
        self.assertEqual([h["diameter_mm"] for h in holes(response.json["state"]["plan"])], [10, 12, 10, 12])

    def test_edit_that_crosses_plate_edge_or_holed_quadrant_is_rejected(self):
        original = self.make_ready()
        for distance in (-15, 46):
            with self.subTest(distance=distance):
                response = self.turn(proposal("hole_edit", "top_left", delta_x_mm=distance), original)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("state", response.json)

    def test_unsupported_change_does_not_create_a_result(self):
        response = self.turn(proposal("unsupported"), text="画一个轴套")
        self.assertEqual(response.json["status"], "clarify")
        self.assertIsNone(response.json["state"]["plan"])

    def test_invalid_state_or_cross_origin_does_not_call_cloud(self):
        original = self.make_ready()
        original["plan"]["features"][0]["depth_mm"] = 99
        self.provider.interpret.reset_mock()
        response = self.turn(proposal(**PARAMETERS), original)
        self.assertEqual(response.status_code, 422)
        outside = self.client.post("/api/model/v2/turn", json={"text": "测试"},
                                   headers={"Origin": "https://example.com"})
        self.assertEqual(outside.status_code, 403)
        self.provider.interpret.assert_not_called()

    def test_image_bytes_are_normalized_and_no_image_dimensions_are_inferred_by_app(self):
        self.provider.interpret.return_value = proposal("clarify", sketch="four_corners")
        result = self.client.post("/api/model/v2/turn", data={
            "sketch": (BytesIO(png()), "paper.png"),
        })
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json["state"]["draft"], {})
        self.assertIsNone(result.json["state"]["plan"])
        self.assertTrue(self.provider.interpret.call_args.args[4].startswith(b"\xff\xd8"))

    def test_sketch_only_cannot_supply_dimensions_even_if_provider_guesses(self):
        self.provider.interpret.return_value = proposal(sketch="four_corners", **PARAMETERS)
        result = self.client.post("/api/model/v2/turn", data={
            "sketch": (BytesIO(png()), "paper.png"),
        })
        self.assertEqual(result.status_code, 422)
        self.assertNotIn("state", result.json)

    def test_unreadable_sketch_is_rejected_locally(self):
        result = self.client.post("/api/model/v2/turn", data={
            "sketch": (BytesIO(b"fake file"), "paper.png"),
        })
        self.assertEqual(result.status_code, 422)
        self.provider.interpret.assert_not_called()

    def test_voice_transcript_returns_to_user_for_review(self):
        self.provider.transcribe.return_value = "厚八毫米"
        response = self.client.post("/api/model/v2/transcribe", data={
            "audio": (BytesIO(b"mock audio"), "recording.webm", "audio/webm"),
        })
        self.assertEqual(response.json, {"text": "厚八毫米"})
        self.provider.interpret.assert_not_called()

    def test_invalid_or_oversized_request_fails_before_provider(self):
        large = self.client.post("/api/model/v2/turn", data=b"x" * (3 * 1024 * 1024),
                                 content_type="application/json")
        self.assertEqual(large.status_code, 422)
        invalid = self.client.post("/api/model/v2/turn", json=["bad"])
        self.assertEqual(invalid.status_code, 400)
        self.provider.interpret.assert_not_called()

    def test_download_revalidates_plan_and_returns_attachment(self):
        plan = self.make_ready()["plan"]
        with patch("solidworks_engine.web_v2.native_archive", return_value=BytesIO(b"fake ZIP")) as native:
            invalid = deepcopy(plan)
            invalid["features"][1]["through_all"] = False
            rejected = self.client.post("/api/model/v2/native", json={"plan": invalid})
            self.assertEqual(rejected.status_code, 422)
            native.assert_not_called()
            with self.client.post("/api/model/v2/native", json={"plan": plan}) as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "application/zip")
                self.assertIn("attachment", response.headers["Content-Disposition"])
                self.assertIn("no-store", response.headers["Cache-Control"])
            native.assert_called_once_with(plan)

    def test_provider_failure_returns_message_without_result(self):
        self.provider.interpret.side_effect = ProviderError("暂时不可用")
        response = self.turn(proposal(**PARAMETERS))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("state", response.json)

    def test_non_finite_or_boolean_numeric_proposals_are_rejected(self):
        for value in (True, nan):
            with self.subTest(value=value):
                response = self.turn(proposal(length_mm=value))
                self.assertEqual(response.status_code, 422)


class ProviderContract(unittest.TestCase):
    def test_builds_strict_json_request_to_configured_host(self):
        def receive(request):
            self.assertEqual(str(request.url), "https://cloud.test/v1/chat/completions")
            self.assertEqual(request.headers["authorization"], "Bearer synthetic-token")
            payload = json.loads(request.content)
            self.assertFalse(payload["store"])
            self.assertTrue(payload["response_format"]["json_schema"]["strict"])
            content = payload["messages"][1]["content"]
            data = json.loads(content[0]["text"])
            self.assertEqual(data["state"]["known"], {"length_mm": 120})
            self.assertEqual(data["user_message"], "八毫米")
            raw = content[1]["image_url"]["url"].split(",", 1)[1]
            self.assertEqual(base64.b64decode(raw), b"placeholder")
            return httpx.Response(200, json={"choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps(proposal(thickness_mm=8, sketch="four_corners"))},
            }]})

        provider = CloudProvider("https://cloud.test/v1", "synthetic-token", "model", None,
                                 transport=httpx.MockTransport(receive))
        result = provider.interpret("八毫米", {"length_mm": 120}, None, "thickness_mm", b"placeholder")
        self.assertEqual(result["thickness_mm"], 8)

    def test_provider_redirect_is_not_followed(self):
        transport = httpx.MockTransport(lambda _: httpx.Response(302, headers={"Location": "https://redirect.test"}))
        provider = CloudProvider("https://cloud.test", "synthetic-token", "model", None, transport=transport)
        with self.assertRaises(ProviderError):
            provider.interpret("厚八毫米", {}, None, None)


class NativeGeometry(unittest.TestCase):
    @staticmethod
    def part(plan, shift_mm=0):
        faces = []
        for index, hole in enumerate(holes(plan)):
            x = (hole["x_mm"] + (shift_mm if index == 0 else 0)) / 1000
            surface = SimpleNamespace(IsCylinder=lambda: True, CylinderParams=[
                x, hole["y_mm"] / 1000, 0, 0, 0, 1, hole["diameter_mm"] / 2000,
            ])
            faces.append(SimpleNamespace(GetSurface=lambda item=surface: item))
        body = SimpleNamespace(GetFaces=lambda: faces)
        return SimpleNamespace(GetPartBox=lambda _: [-.06, -.04, 0, .06, .04, .008],
                               GetBodies2=lambda *_: [body])

    def test_native_geometry_check_rejects_shifted_hole(self):
        plan = from_symmetric_parameters(PARAMETERS)
        validated = _verify_geometry(self.part(plan), plan)
        self.assertEqual(validated["holes"][0]["diameter_mm"], 10)
        with self.assertRaises(NativeError):
            _verify_geometry(self.part(plan, shift_mm=3), plan)

    def test_plan_validation_rejects_overflow_before_com(self):
        state = from_symmetric_parameters(PARAMETERS)
        state["parameters"]["length_mm"] = 10 ** 500
        with self.assertRaises(ModelPlanError):
            validate_plate(state)


if __name__ == "__main__":
    unittest.main()
