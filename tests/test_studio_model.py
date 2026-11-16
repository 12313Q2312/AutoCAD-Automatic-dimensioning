"""ModelPlan SW-01 offline tests. No CAD, network, API keys or file writes."""
import copy
import json
import math
import unittest

from solidworks_engine import (
    ModelPlanError, parse_description, plan_from_parameters,
    render_svg, simulate, validate_plan,
)


class ModelPlanTest(unittest.TestCase):
    sample_text = (
        "创建一块长120毫米、宽80毫米、厚8毫米的安装板，"
        "四角共有四个直径10毫米的通孔，"
        "长边方向间隔90毫米，宽边方向间隔50毫米。"
    )

    def test_mounting_plate_holes_and_features(self):
        plan = parse_description(self.sample_text)
        self.assertEqual(plan["part_type"], "mounting_plate")
        self.assertEqual(plan["schema_version"], "1.0")
        self.assertEqual(plan["units"], "mm")
        self.assertEqual(plan["bounding_box_mm"], [120, 80, 8])
        self.assertEqual(len(plan["features"]), 2)
        holes = plan["features"][1]
        self.assertEqual(holes["operation"], "cut_through")
        self.assertTrue(holes["through_all"])
        self.assertEqual(
            holes["sketch"]["centers_mm"],
            [[-45.0, -25.0], [45.0, -25.0], [-45.0, 25.0], [45.0, 25.0]],
        )
        self.assertEqual(holes["sketch"]["diameter_mm"], 10)
        self.assertTrue(validate_plan(plan)["valid"])
        self.assertFalse(simulate(plan)["native_cad_generated"])

    def test_user_original_example_long_form(self):
        text = ("创建一块长120 mm、宽80 mm、厚8 mm的安装板，四角各有一个"
                "直径10毫米的通孔，孔中心距长边方向两两间隔90毫米、"
                "宽边方向间隔50毫米，孔位关于中心对称。")
        plan = parse_description(text)
        self.assertEqual(plan["parameters"]["pitch_x_mm"], 90)
        self.assertEqual(plan["parameters"]["pitch_y_mm"], 50)

    def test_cm_to_mm_normalization(self):
        text = ("创建长12厘米、宽8厘米、厚0.8厘米的四孔安装板，"
                "孔径1厘米，X方向孔距9厘米，Y方向孔距5厘米。")
        plan = parse_description(text)
        self.assertEqual(plan["parameters"], {
            "length_mm": 120, "width_mm": 80, "thickness_mm": 8,
            "hole_diameter_mm": 10, "pitch_x_mm": 90, "pitch_y_mm": 50,
        })

    def test_basic_plate(self):
        p = parse_description("制作长100毫米、宽60毫米、厚4毫米的矩形板。")
        self.assertEqual(p["part_type"], "rectangular_plate")
        self.assertEqual(len(p["features"]), 1)
        self.assertEqual(p["features"][0]["sketch"]["type"], "rectangle")

    def test_cylinder(self):
        p = parse_description("创建直径30毫米、高60毫米的圆柱。")
        self.assertEqual(p["part_type"], "cylinder")
        self.assertEqual(p["bounding_box_mm"], [30, 30, 60])
        self.assertEqual(p["features"][0]["sketch"]["type"], "circle")

    def test_bushing(self):
        p = parse_description("制作外径40毫米、内径20毫米、长60毫米的轴套。")
        self.assertEqual(p["part_type"], "bushing")
        self.assertEqual(p["features"][0]["sketch"]["type"], "annulus")
        self.assertEqual(p["bounding_box_mm"], [40, 40, 60])

    def test_deterministic_output(self):
        a = parse_description(self.sample_text)
        b = parse_description(self.sample_text)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(render_svg(a), render_svg(b))

    def test_svg_validated_and_no_user_injection(self):
        p = parse_description(self.sample_text)
        svg = render_svg(p)
        self.assertIn("<svg", svg)
        self.assertIn("<circle ", svg)
        self.assertEqual(svg.count("<circle "), 4)
        self.assertIn("NOT A SOLIDWORKS MODEL", svg)

    def test_invalid_geometry_pitches(self):
        params = {"length_mm": 120, "width_mm": 80, "thickness_mm": 8,
                  "hole_diameter_mm": 10, "pitch_x_mm": 90, "pitch_y_mm": 50}
        for x, y in [(8, 50), (90, 8), (112, 50), (90, 75)]:
            with self.subTest(x=x, y=y), self.assertRaises(ModelPlanError):
                plan_from_parameters("mounting_plate", {**params, "pitch_x_mm": x, "pitch_y_mm": y})

    def test_bushing_wall_too_thin(self):
        with self.assertRaisesRegex(ModelPlanError, "壁厚"):
            plan_from_parameters("bushing", {
                "outer_diameter_mm": 30, "inner_diameter_mm": 29,
                "height_mm": 60,
            })

    def test_invalid_sizes(self):
        for value in (-1, 0, 2001, math.inf, math.nan, True, "120", None):
            with self.subTest(value=value), self.assertRaises(ModelPlanError):
                plan_from_parameters("cylinder", {
                    "diameter_mm": value, "height_mm": 60,
                })

    def test_missing_parameter(self):
        with self.assertRaisesRegex(ModelPlanError, "缺少"):
            parse_description("制作长100毫米、宽40毫米的矩形板。")

    def test_no_units_is_not_guessed(self):
        with self.assertRaises(ModelPlanError):
            parse_description("制作长100、宽40、厚5的矩形板。")

    def test_rejects_unsupported_part(self):
        with self.assertRaises(ModelPlanError):
            parse_description("制作一个复杂六轴机器人装配体。")

    def test_rejects_other_hole_counts(self):
        with self.assertRaises(ModelPlanError):
            parse_description("制作长120毫米宽80毫米厚8毫米的三孔安装板。")

    def test_rejects_extra_parameters(self):
        with self.assertRaisesRegex(ModelPlanError, "不支持的参数"):
            plan_from_parameters("cylinder", {
                "diameter_mm": 30, "height_mm": 50, "macro": "RUN",
            })

    def test_rejects_tampered_feature_plan(self):
        p = parse_description(self.sample_text)
        altered = copy.deepcopy(p)
        altered["features"][0]["depth_mm"] = 100
        with self.assertRaisesRegex(ModelPlanError, "不一致"):
            validate_plan(altered)
        with self.assertRaises(ModelPlanError):
            render_svg(altered)

    def test_rejects_long_text(self):
        with self.assertRaises(ModelPlanError):
            parse_description("安装板" * 400)


if __name__ == "__main__":
    unittest.main()
