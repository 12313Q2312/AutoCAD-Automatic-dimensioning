"""Safe SVG sketch of validated plan geometry. Illustration only, no 3D CAD."""
from .model import validate_plan


def render_svg(plan: dict) -> str:
    validate_plan(plan)
    kind, p = plan["part_type"], plan["parameters"]
    canvas_w, canvas_h = 600, 390
    # Fixed text and controlled numeric parameters only. No raw user strings.
    if kind in ("rectangular_plate", "mounting_plate"):
        w, h = p["length_mm"], p["width_mm"]
        scale = min(430 / w, 250 / h)
        rw, rh = w * scale, h * scale
        x, y = (canvas_w-rw)/2, (canvas_h-rh)/2 + 4
        shapes = [
            f'<rect x="{x:.3f}" y="{y:.3f}" width="{rw:.3f}" height="{rh:.3f}" '
            'rx="3" fill="#dbe9e8" stroke="#254958" stroke-width="2.5"/>',
        ]
        if kind == "mounting_plate":
            radius = p["hole_diameter_mm"] * scale / 2
            for cx, cy in plan["features"][1]["sketch"]["centers_mm"]:
                px = canvas_w/2 + cx * scale
                py = canvas_h/2 + 4 - cy * scale
                shapes.append(
                    f'<circle cx="{px:.3f}" cy="{py:.3f}" r="{radius:.3f}" '
                    'fill="#f8faf9" stroke="#254958" stroke-width="2.5"/>'
                )
        label = f'{w:g} × {h:g} × {p["thickness_mm"]:g} mm'
    else:
        d = p.get("outer_diameter_mm", p.get("diameter_mm"))
        radius = min(d * min(430 / d, 250 / d) / 2, 125)
        shapes = [
            f'<circle cx="300" cy="198" r="{radius:.3f}" fill="#dbe9e8" '
            'stroke="#254958" stroke-width="2.5"/>'
        ]
        if kind == "bushing":
            inner = radius * p["inner_diameter_mm"] / d
            shapes.append(
                f'<circle cx="300" cy="198" r="{inner:.3f}" fill="#f8faf9" '
                'stroke="#254958" stroke-width="2.5"/>'
            )
        label = f'Ø{d:g} × {p["height_mm"]:g} mm'
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 390" role="img" '
        'aria-label="经验证的二维几何示意图，非真实SolidWorks模型">'
        '<rect width="600" height="390" rx="16" fill="#f8faf9"/>'
        '<g stroke="#d9e5e4" stroke-width="1">'
        '<path d="M300 28 V350 M40 198 H560" stroke-dasharray="6 9"/>'
        '</g>'
        + "".join(shapes)
        + '<g fill="#254958" font-family="Arial, sans-serif" font-size="16" text-anchor="middle">'
        + f'<text x="300" y="366">{label}</text>'
        + '</g>'
        + '<text x="22" y="29" fill="#738b91" font-size="12" font-family="Arial">'
        + 'GEOMETRY PREVIEW / NOT A SOLIDWORKS MODEL</text>'
        + '</svg>'
    )
