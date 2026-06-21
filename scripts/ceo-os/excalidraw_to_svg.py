#!/usr/bin/env python3
"""Render a hand-laid .excalidraw scene to a flat SVG for instant viewing.

Handles the element subset this project's maps use: rectangle, text, arrow.
Not a general Excalidraw renderer — just enough to `open` the capability map
without the Excalidraw app. Stdlib only.

Usage: python3 excalidraw_to_svg.py <in.excalidraw> <out.svg>
"""
import html
import json
import sys


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def render(scene: dict) -> str:
    els = [e for e in scene.get("elements", []) if not e.get("isDeleted")]
    pad = 40
    maxx = max((e["x"] + e.get("width", 0) for e in els), default=1000) + pad
    maxy = max((e["y"] + e.get("height", 0) for e in els), default=700) + pad
    bg = scene.get("appState", {}).get("viewBackgroundColor", "#ffffff")

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{maxx:.0f}" '
        f'height="{maxy:.0f}" viewBox="0 0 {maxx:.0f} {maxy:.0f}" '
        f'font-family="Helvetica,Arial,sans-serif">',
        f'<rect width="100%" height="100%" fill="{bg}"/>',
        '<defs><marker id="ah" markerWidth="9" markerHeight="9" refX="7" refY="3" '
        'orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L7,3 L0,6 Z" fill="#495057"/></marker></defs>',
    ]

    for e in els:
        t = e["type"]
        if t == "rectangle":
            out.append(
                f'<rect x="{e["x"]:.0f}" y="{e["y"]:.0f}" width="{e["width"]:.0f}" '
                f'height="{e["height"]:.0f}" rx="10" fill="{e.get("backgroundColor","#fff")}" '
                f'stroke="{e.get("strokeColor","#000")}" stroke-width="{e.get("strokeWidth",2)}"/>'
            )
        elif t == "arrow":
            pts = e.get("points", [[0, 0], [0, 0]])
            x1, y1 = e["x"] + pts[0][0], e["y"] + pts[0][1]
            x2, y2 = e["x"] + pts[-1][0], e["y"] + pts[-1][1]
            out.append(
                f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
                f'stroke="{e.get("strokeColor","#495057")}" stroke-width="{e.get("strokeWidth",2)}" '
                f'marker-end="url(#ah)"/>'
            )
        elif t == "text":
            size = e.get("fontSize", 16)
            color = e.get("strokeColor", "#212529")
            weight = "bold" if e.get("fontFamily") == 2 else "normal"
            lh = size * e.get("lineHeight", 1.25)
            x = e["x"]
            y0 = e["y"] + size  # baseline of first line
            for i, line in enumerate(e.get("text", "").split("\n")):
                out.append(
                    f'<text x="{x:.0f}" y="{y0 + i*lh:.0f}" font-size="{size:.0f}" '
                    f'fill="{color}" font-weight="{weight}" '
                    f'xml:space="preserve">{_esc(line)}</text>'
                )

    out.append("</svg>")
    return "\n".join(out)


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write("usage: excalidraw_to_svg.py <in.excalidraw> <out.svg>\n")
        return 2
    scene = json.load(open(sys.argv[1], encoding="utf-8"))
    open(sys.argv[2], "w", encoding="utf-8").write(render(scene))
    print(f"wrote {sys.argv[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
