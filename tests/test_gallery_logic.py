from slackbackup import gallery_logic


def _touch(path, content=b"fake-png-bytes"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_scan_workspace_images_groups_by_channel_and_sorts_by_date(tmp_path):
    ws = tmp_path / "f3kirkland"
    _touch(ws / "ao-urban-ruck" / "__bot-images" / "2026-07-17_b.png")
    _touch(ws / "ao-urban-ruck" / "__bot-images" / "2026-04-03_a.png")
    _touch(ws / "ao-borderlands" / "__bot-images" / "2026-07-20_c.png")

    result = gallery_logic.scan_workspace_images(ws)

    assert set(result.keys()) == {"ao-urban-ruck", "ao-borderlands"}
    dates = [e["date"] for e in result["ao-urban-ruck"]]
    assert dates == ["2026-04-03", "2026-07-17"]


def test_scan_workspace_images_skips_channels_with_no_bot_images(tmp_path):
    ws = tmp_path / "f3kirkland"
    (ws / "ao-torque" / "__bot-images").mkdir(parents=True)
    _touch(ws / "ao-urban-ruck" / "__bot-images" / "2026-07-17_b.png")

    result = gallery_logic.scan_workspace_images(ws)

    assert set(result.keys()) == {"ao-urban-ruck"}


def test_scan_workspace_images_handles_missing_date_prefix(tmp_path):
    ws = tmp_path / "f3kirkland"
    _touch(ws / "ao-urban-ruck" / "__bot-images" / "no-date-prefix.png")

    result = gallery_logic.scan_workspace_images(ws)

    assert result["ao-urban-ruck"][0]["date"] is None


def test_scan_workspace_images_rel_path_is_relative_to_workspace_dir(tmp_path):
    ws = tmp_path / "f3kirkland"
    _touch(ws / "ao-urban-ruck" / "__bot-images" / "2026-07-17_b.png")

    result = gallery_logic.scan_workspace_images(ws)

    assert result["ao-urban-ruck"][0]["rel_path"] == "ao-urban-ruck/__bot-images/2026-07-17_b.png"


def test_scan_workspace_images_missing_workspace_dir_returns_empty(tmp_path):
    result = gallery_logic.scan_workspace_images(tmp_path / "does-not-exist")
    assert result == {}


def test_generate_html_includes_size_toggle_buttons():
    html = gallery_logic.generate_html({"ao-urban-ruck": [{"date": "2026-07-17", "filename": "b.png", "rel_path": "ao-urban-ruck/__bot-images/b.png"}]})
    assert "Small" in html and "Medium" in html and "Large" in html
    assert "data-size=\"120\"" in html
    assert "data-size=\"200\"" in html
    assert "data-size=\"320\"" in html


def test_generate_html_embeds_relative_image_paths_and_dates():
    html = gallery_logic.generate_html({"ao-urban-ruck": [{"date": "2026-07-17", "filename": "b.png", "rel_path": "ao-urban-ruck/__bot-images/b.png"}]})
    assert "ao-urban-ruck/__bot-images/b.png" in html
    assert "2026-07-17" in html
    assert "ao-urban-ruck" in html


def test_generate_html_escapes_channel_and_filename():
    html = gallery_logic.generate_html({"<script>": [{"date": None, "filename": "x&y.png", "rel_path": "x/x&y.png"}]})
    assert "<h2><script>" not in html  # channel name not left un-escaped as its own tag
    assert "&lt;script&gt;" in html


def test_generate_html_empty_scan_is_still_valid_page():
    html = gallery_logic.generate_html({})
    assert "0 image(s)" in html
    assert "<html" in html


def test_generate_gallery_writes_to_default_path(tmp_path):
    ws = tmp_path / "f3kirkland"
    _touch(ws / "ao-urban-ruck" / "__bot-images" / "2026-07-17_b.png")

    out = gallery_logic.generate_gallery(ws)

    assert out == ws / "image-gallery.html"
    assert out.exists()
    assert "ao-urban-ruck" in out.read_text()


def test_generate_gallery_respects_custom_out_path(tmp_path):
    ws = tmp_path / "f3kirkland"
    _touch(ws / "ao-urban-ruck" / "__bot-images" / "2026-07-17_b.png")
    custom = tmp_path / "somewhere-else.html"

    out = gallery_logic.generate_gallery(ws, out_path=custom)

    assert out == custom
    assert custom.exists()
