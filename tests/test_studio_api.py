"""Flask workbench/ModelPlan route checks, without network or native CAD."""
import json
import unittest

import app as cad_app


class StudioRoutesTest(unittest.TestCase):
    def setUp(self):
        cad_app.app.config["TESTING"] = True
        self.client = cad_app.app.test_client()

    def test_studio_home_and_resources(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Mechanical CAD Studio", page.data)
        self.assertIn(b"/studio.css", page.data)
        self.assertIn(b"/studio.js", page.data)
        self.assertIn("SolidWorks".encode(), page.data)
        self.assertEqual(self.client.get("/studio").status_code, 200)
        self.assertEqual(self.client.get("/studio.css").status_code, 200)
        self.assertEqual(self.client.get("/studio.js").status_code, 200)

    def test_existing_autocad_page_kept(self):
        page = self.client.get("/autocad")
        self.assertEqual(page.status_code, 200)
        self.assertIn("DWG".encode(), page.data)
        self.assertIn(b"style.css", page.data)
        self.assertEqual(self.client.get("/api/gb_presets").status_code, 200)

    def test_description_api(self):
        response = self.client.post("/api/model/plan", json={
            "mode": "text",
            "description": ("制作长120毫米宽80毫米厚8毫米的四孔安装板，"
                            "孔径10毫米，X方向孔距90毫米，Y方向孔距50毫米。"),
        })
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json
        self.assertTrue(data["success"])
        self.assertTrue(data["validation_report"]["valid"])
        self.assertEqual(data["plan"]["part_type"], "mounting_plate")
        self.assertEqual(len(data["plan"]["features"]), 2)
        self.assertFalse(data["real_solidworks_executed"])
        self.assertFalse(data["dry_run"]["native_cad_generated"])
        self.assertIn("<svg", data["preview_svg"])

    def test_parameter_form_api(self):
        response = self.client.post("/api/model/plan", json={
            "mode": "parameters", "part_type": "bushing",
            "parameters": {
                "outer_diameter_mm": 40, "inner_diameter_mm": 20, "height_mm": 60,
            },
        })
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["plan"]["part_type"], "bushing")

    def test_incomplete_dimensions_produce_422(self):
        response = self.client.post("/api/model/plan", json={
            "mode": "text", "description": "矩形板长120毫米宽80毫米",
        })
        self.assertEqual(response.status_code, 422)
        self.assertFalse(response.json["success"])
        self.assertIn("厚度", response.json["error"])

    def test_no_arbitrary_operations(self):
        response = self.client.post("/api/model/plan", json={
            "mode": "parameters", "part_type": "cylinder",
            "parameters": {"diameter_mm": 30, "height_mm": 60, "run_macro": "x"},
        })
        self.assertEqual(response.status_code, 422)

    def test_non_object_and_unknown_mode(self):
        self.assertEqual(self.client.post("/api/model/plan", json=["hello"]).status_code, 400)
        self.assertEqual(self.client.post("/api/model/plan", data="broken", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post("/api/model/plan", json={"mode": "execute_cad"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
