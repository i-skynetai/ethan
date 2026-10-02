#!/usr/bin/env python3
"""Turn a command's real output into a terminal-style SVG for the docs.

    ./run.sh --demo | python3 tools/render-terminal.py "./run.sh --demo" > docs/images/demo.svg

The text is drawn as it came, line for line; long lines are wrapped, nothing is edited.
Render the PNG beside it at its own size, for example with headless Chrome:
    chrome --headless --force-device-scale-factor=2 --window-size=820,<height> \
           --screenshot=docs/images/demo.png docs/images/demo.svg
"""
import html, sys, textwrap

WIDTH, COLS, LINE = 820, 96, 19
COLOURS = {"you": "#86efac", "router": "#fde68a", "launch": "#fde68a", "ledger": "#93c5fd",
           "kb": "#93c5fd", "model": "#93c5fd"}

cmd = sys.argv[1] if len(sys.argv) > 1 else ""
rows = [(f"$ {cmd}", "#86efac")]
for raw in sys.stdin.read().rstrip("\n").split("\n"):
    colour = COLOURS.get(raw.split(" ")[0], "#e2e8f0")
    for part in textwrap.wrap(raw, COLS, subsequent_indent="         ") or [""]:
        rows.append((part, colour))

height = 52 + LINE * len(rows)
out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}">',
       f'<rect width="{WIDTH}" height="{height}" rx="10" fill="#0f172a"/>',
       '<circle cx="22" cy="20" r="6" fill="#ef4444"/><circle cx="42" cy="20" r="6" fill="#f59e0b"/>'
       '<circle cx="62" cy="20" r="6" fill="#22c55e"/>',
       f'<text x="{WIDTH // 2}" y="25" font-family="-apple-system, Helvetica, Arial, sans-serif" '
       f'font-size="12" fill="#94a3b8" text-anchor="middle">terminal — real output of {html.escape(cmd)}</text>',
       '<g font-family="Menlo, Monaco, Consolas, \'DejaVu Sans Mono\', monospace" font-size="13" xml:space="preserve">']
for i, (text, colour) in enumerate(rows):
    out.append(f'<text x="22" y="{52 + LINE * i}" fill="{colour}">{html.escape(text)}</text>')
out += ["</g>", "</svg>"]
print("\n".join(out))
