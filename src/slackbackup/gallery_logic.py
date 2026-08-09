#!/usr/bin/env python3
"""Builds a self-contained HTML thumbnail gallery of a workspace's harvested
bot-embedded images (bot_images_logic's __bot-images/ folders - see
SlackBackup sat-es4), grouped by channel/AO and sorted by backblast date
within each group. No external assets: the page only links to the already-
downloaded local image files via relative paths, and its size-toggle
control is inline CSS/JS.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from .bot_images_logic import DEFAULT_OUT_SUBDIR, GONE_MARKER_SUFFIX

# bot_images_logic.target_filename's convention: "YYYY-MM-DD_<original-name>".
_FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)$")


def scan_workspace_images(workspace_dir: Path, out_subdir: str = DEFAULT_OUT_SUBDIR) -> dict[str, list[dict]]:
    """Returns {channel_name: [{date, filename, rel_path}, ...]}, each
    channel's list sorted by date ascending. Only channels with at least
    one image are included. `date` is None (sorts first) for a filename
    that doesn't match the YYYY-MM-DD_ prefix convention, rather than
    silently dropping it - an unexpected filename is more useful visible
    than hidden."""
    result: dict[str, list[dict]] = {}
    if not workspace_dir.is_dir():
        return result

    for channel_dir in sorted(workspace_dir.iterdir()):
        images_dir = channel_dir / out_subdir
        if not images_dir.is_dir():
            continue

        entries = []
        for image_path in sorted(images_dir.iterdir()):
            if not image_path.is_file():
                continue
            if image_path.name.endswith(GONE_MARKER_SUFFIX):
                # A confirmed-404 marker (bot_images_logic), not an image.
                continue
            match = _FILENAME_DATE_RE.match(image_path.name)
            date = match.group(1) if match else None
            entries.append(
                {
                    "date": date,
                    "filename": image_path.name,
                    "rel_path": f"{channel_dir.name}/{out_subdir}/{image_path.name}",
                }
            )
        if entries:
            entries.sort(key=lambda e: (e["date"] or "", e["filename"]))
            result[channel_dir.name] = entries

    return result


_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{ --thumb-size: 200px; --gap: 12px; --bg: #ffffff; --fg: #1a1a1a; --muted: #666; --card-bg: #f5f5f5; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #1a1a1a; --fg: #eee; --muted: #aaa; --card-bg: #262626; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: var(--bg); color: var(--fg); margin: 0; padding: 24px; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 4px; }}
  .meta {{ color: var(--muted); margin: 0 0 20px; font-size: 0.9rem; }}
  .size-toggle {{ margin-bottom: 24px; display: flex; gap: 8px; align-items: center; }}
  .size-toggle button {{
    padding: 6px 14px; border-radius: 6px; border: 1px solid var(--muted); background: var(--card-bg);
    color: var(--fg); cursor: pointer; font-size: 0.9rem;
  }}
  .size-toggle button.active {{ background: var(--fg); color: var(--bg); border-color: var(--fg); }}
  .channel-group {{ margin-bottom: 36px; }}
  .channel-group h2 {{ font-size: 1.1rem; border-bottom: 1px solid var(--muted); padding-bottom: 6px; }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(var(--thumb-size), 1fr));
    gap: var(--gap);
  }}
  .thumb {{ background: var(--card-bg); border-radius: 8px; overflow: hidden; }}
  .thumb a {{ display: block; }}
  .thumb img {{ width: 100%; height: var(--thumb-size); object-fit: cover; display: block; }}
  .thumb .caption {{ padding: 6px 8px; font-size: 0.75rem; color: var(--muted); }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="meta">{image_count} image(s) across {channel_count} channel(s)</p>
<div class="size-toggle">
  <span>Thumbnail size:</span>
  <button data-size="120" class="active">Small</button>
  <button data-size="200">Medium</button>
  <button data-size="320">Large</button>
</div>
{groups}
<script>
document.querySelectorAll('.size-toggle button').forEach(function (btn) {{
  btn.addEventListener('click', function () {{
    document.documentElement.style.setProperty('--thumb-size', btn.dataset.size + 'px');
    document.querySelectorAll('.size-toggle button').forEach(function (b) {{ b.classList.remove('active'); }});
    btn.classList.add('active');
  }});
}});
</script>
</body>
</html>
"""

_GROUP_TEMPLATE = """\
<section class="channel-group">
  <h2>{channel}</h2>
  <div class="grid">
{thumbs}
  </div>
</section>
"""

_THUMB_TEMPLATE = """\
    <div class="thumb">
      <a href="{rel_path}" target="_blank" rel="noopener">
        <img src="{rel_path}" loading="lazy" alt="{filename}">
      </a>
      <div class="caption">{date}</div>
    </div>"""


def generate_html(images_by_channel: dict[str, list[dict]], title: str = "Bot Image Gallery") -> str:
    image_count = sum(len(v) for v in images_by_channel.values())
    channel_count = len(images_by_channel)

    groups = []
    for channel in sorted(images_by_channel):
        thumbs = "\n".join(
            _THUMB_TEMPLATE.format(
                rel_path=html.escape(e["rel_path"]),
                filename=html.escape(e["filename"]),
                date=html.escape(e["date"] or "(undated)"),
            )
            for e in images_by_channel[channel]
        )
        groups.append(_GROUP_TEMPLATE.format(channel=html.escape(channel), thumbs=thumbs))

    return _TEMPLATE.format(
        title=html.escape(title),
        image_count=image_count,
        channel_count=channel_count,
        groups="\n".join(groups),
    )


def generate_gallery(workspace_dir: Path, out_path: Path | None = None, title: str | None = None) -> Path:
    """Scans workspace_dir and writes the gallery HTML into out_path
    (default: <workspace_dir>/image-gallery.html). Returns the path
    written. An empty scan still writes a valid (empty-state) page rather
    than erroring, so re-running after clearing all images doesn't leave a
    stale gallery behind."""
    images_by_channel = scan_workspace_images(workspace_dir)
    out_path = out_path or (workspace_dir / "image-gallery.html")
    title = title or f"{workspace_dir.name} — Bot Image Gallery"
    out_path.write_text(generate_html(images_by_channel, title=title))
    return out_path
