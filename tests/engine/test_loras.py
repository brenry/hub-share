"""LoRA panel backend: safetensors headers, the folder scan, the strengths, covers and routes."""
from __future__ import annotations

import base64
import io
import json
import os
import struct

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.core.features import tools_of
from hub.core.schema import check
from hub.modules.loras import header, manifest, routes, scan, userdata
from tests.engine.helpers import FakeCtx, FakeEngine, FakeRequest, load_catalog, snapshot, write_lora


def png_bytes(w: int = 64, h: int = 48, color: tuple = (200, 100, 50)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), color).save(out, "PNG")
    return out.getvalue()


KOHYA = {"ss_network_dim": "32", "ss_network_alpha": "16", "ss_base_model_version": "flux2",
         "ss_num_train_images": "120", "ss_resolution": "(1024, 1024)",
         "ss_tag_frequency": json.dumps({"a": {"inkstyle": 5, " lines": 2, "": 9}, "b": {"inkstyle": 1, "z": 2}}),
         "modelspec.trigger_phrase": "inkstyle, bold lines; sketch",
         "sd.artifact.v1": json.dumps({"triggers": ["Inkstyle", "extra"], "recommended_weight": 0.7})}


@pytest.fixture
def lib(tmp_path):
    loras = tmp_path / "loras"
    fam = loras / "flux2_klein_9b"
    write_lora(fam / "comic_ink_lineart.safetensors", KOHYA)
    write_lora(fam / "style" / "film-grain.safetensors", {"modelspec.title": "Film Grain Pro"})
    write_lora(fam / "style" / "deep" / "x.sft")
    (fam / "style" / "film-grain.preview.png").write_bytes(png_bytes())
    (fam / "notes.txt").write_text("not a lora")
    write_lora(tmp_path / "outside.safetensors")
    os.symlink(tmp_path / "outside.safetensors", fam / "escape.safetensors")
    os.symlink(fam / "comic_ink_lineart.safetensors", fam / "inside-link.safetensors")
    os.symlink(tmp_path, fam / "dirlink")
    thumb = "data:image/png;base64," + base64.b64encode(png_bytes(32, 32)).decode()
    write_lora(loras / "z_image" / "embedded.safetensors", {"modelspec.thumbnail": thumb})
    cat = load_catalog("catalog_upstream.json", loras)
    ctx = FakeCtx("loras", tmp_path / "data", FakeEngine(cat))
    ctx.loras, ctx.cat = loras, cat
    return ctx


# ---------------------------------------------------------------- header
def test_header_reads_only_the_facts_the_panel_shows(tmp_path):
    meta, tensors = header.read(str(write_lora(tmp_path / "a.safetensors", {"k": "v", "n": 1})))
    assert meta == {"k": "v"} and tensors["a.lora_down.weight"]["shape"] == [16, 64]
    facts = header.summary(*header.read(str(write_lora(tmp_path / "b.safetensors", KOHYA))))
    assert facts == {"title": None, "triggers": ["inkstyle", "bold lines", "sketch", "extra"], "weight": 0.7,
                     "thumb": False}, "training tags, rank, base model, image counts: not read, not shown"
    assert header.summary({}, {}) == {"title": None, "triggers": [], "weight": None, "thumb": False}


@pytest.mark.parametrize("raw", [
    b"", b"\x01\x02", struct.pack("<Q", 0), struct.pack("<Q", 10) + b"{}",
    struct.pack("<Q", 5) + b"nope!", struct.pack("<Q", 2) + b"[]",
    struct.pack("<Q", 200 * 1024 * 1024) + b"{}",
])
def test_bad_or_huge_headers_mean_no_metadata(tmp_path, raw):
    path = tmp_path / "bad.safetensors"
    path.write_bytes(raw)
    assert header.read(str(path)) is None


def test_huge_header_is_refused_without_reading(tmp_path):
    path = tmp_path / "huge.safetensors"
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", 90 * 1024 * 1024) + b"{")
    assert header.read(str(path), cap=1024) is None
    assert header.read(str(path)) is None


# ---------------------------------------------------------------- scan
def test_scan_follows_the_engine_folder_rule(lib):
    fam = scan.family_of(lib.cat, "flux2_klein_9b")
    found = {e.rel: e for e in scan.scan(fam)}
    assert set(found) == {"comic_ink_lineart.safetensors", "inside-link.safetensors", "style/film-grain.safetensors",
                          "style/deep/x.sft"}
    assert found["style/film-grain.safetensors"].sidecar.endswith("film-grain.preview.png")
    assert scan.find(fam, "flux2_klein_9b/escape.safetensors") is None
    assert scan.find(fam, "flux2_klein_9b/../outside.safetensors") is None
    assert scan.find(fam, "flux2_klein_9b/dirlink/outside.safetensors") is None
    assert scan.find(fam, "z_image/embedded.safetensors") is None
    assert scan.display_name("comic_ink_lineart", None) == "Comic Ink Lineart"
    assert scan.display_name("FilmGrain-v2", None) == "FilmGrain v2"
    assert scan.display_name("x", "Title Wins") == "Title Wins"


async def test_list_route_sorts_by_name_and_reports_covers(lib):
    items = await routes.list_loras(lib, FakeRequest({"model": "flux2_klein_9b"}))
    assert [i["name"] for i in items] == ["Comic Ink Lineart", "Film Grain Pro", "Inside Link", "X"]
    ink = next(i for i in items if i["file"] == "comic_ink_lineart.safetensors")
    assert set(ink) == {"id", "name", "file", "fileTriggers", "cover", "strength", "defaultStrength", "addedAt"}
    assert ink["fileTriggers"][0] == "inkstyle" and ink["defaultStrength"] == 0.7
    assert ink["cover"] is None and ink["strength"] is None
    grain = next(i for i in items if i["name"] == "Film Grain Pro")
    assert set(grain["cover"]) == {"url"}
    assert grain["cover"]["url"].startswith("/api/loras/thumb?id=flux2_klein_9b%2Fstyle%2Ffilm-grain.safetensors&v=")
    assert grain["defaultStrength"] == 1.0
    assert await routes.list_loras(lib, FakeRequest({"model": "unknown"})) == []


# ---------------------------------------------------------------- the strengths
async def test_strength_is_the_only_thing_kept_and_null_forgets_it(lib):
    def req(body: dict) -> FakeRequest:
        return FakeRequest({"id": "flux2_klein_9b/comic_ink_lineart.safetensors"}, json.dumps(body).encode())

    assert await routes.patch_user(lib, req({"strength": 0.75})) == {"strength": 0.75}
    rec = userdata.all_entries(lib)["flux2_klein_9b/comic_ink_lineart.safetensors"]
    assert set(rec) == {"strength", "size", "mtime"} and rec["size"] > 0 and isinstance(rec["mtime"], int)
    items = await routes.list_loras(lib, FakeRequest({"model": "flux2_klein_9b"}))
    assert next(i for i in items if i["file"] == "comic_ink_lineart.safetensors")["strength"] == 0.75
    for bad in ({"strength": 2.5}, {"strength": True}, {"notes": "n"}, {"triggers": ["a"]}, {"cover": "abc"},
                {"strength": 1, "notes": "n"}, {}, []):
        with pytest.raises(Invalid):
            await routes.patch_user(lib, req(bad))
    assert await routes.patch_user(lib, req({"strength": None})) == {}
    assert userdata.all_entries(lib) == {}


async def test_rename_keeps_the_strength(lib):
    old = "flux2_klein_9b/comic_ink_lineart.safetensors"
    await routes.patch_user(lib, FakeRequest({"id": old}, b'{"strength": 0.6}'))
    fam = lib.loras / "flux2_klein_9b"
    os.unlink(fam / "inside-link.safetensors")
    os.rename(fam / "comic_ink_lineart.safetensors", fam / "style" / "ink-renamed.safetensors")
    await routes.list_loras(lib, FakeRequest({"model": "flux2_klein_9b"}))
    data = userdata.all_entries(lib)
    assert old not in data and data["flux2_klein_9b/style/ink-renamed.safetensors"]["strength"] == 0.6


def test_ambiguous_rename_keeps_the_orphan_and_empty_entries_go(lib):
    fam = scan.family_of(lib.cat, "flux2_klein_9b")
    lib.doc(userdata.DOC, {}).replace({"version": 1, "loras": {
        "flux2_klein_9b/gone.safetensors": {"size": 10, "mtime": 5, "strength": 0.5},
        "flux2_klein_9b/old.safetensors": {"size": 10, "mtime": 5, "notes": "left over from before"}}})
    twins = [scan.Entry(f"flux2_klein_9b/{n}", n, n, 10, 5, 5, None) for n in ("a.safetensors", "b.safetensors")]
    loras = userdata.reconcile(lib, fam.key, twins)
    assert loras == {"flux2_klein_9b/gone.safetensors": {"size": 10, "mtime": 5, "strength": 0.5}}


# ---------------------------------------------------------------- covers
async def test_covers_come_from_the_sidecar_or_the_file_and_stay_in_memory(lib):
    grain = {"id": "flux2_klein_9b/style/film-grain.safetensors"}
    sidecar = await routes.thumb(lib, FakeRequest({**grain, "size": "96"}))
    assert sidecar.media_type == "image/webp" and Image.open(io.BytesIO(sidecar.body)).size == (96, 96)
    embedded = await routes.thumb(lib, FakeRequest({"id": "z_image/embedded.safetensors", "size": "96"}))
    assert embedded.status_code == 200 and Image.open(io.BytesIO(embedded.body)).size == (96, 96)
    none = await routes.thumb(lib, FakeRequest({"id": "flux2_klein_9b/style/deep/x.sft", "size": "96"}))
    assert none.status_code == 404
    assert len(lib.files.thumbs._items) == 2 and not list(lib.data_dir.rglob("*.webp")), "memory only"
    with pytest.raises(Invalid):
        await routes.thumb(lib, FakeRequest({**grain, "size": "500"}))
    with pytest.raises(Invalid):
        await routes.thumb(lib, FakeRequest({"id": "flux2_klein_9b/missing.safetensors", "size": "96"}))


async def test_lora_folders_are_never_written(lib):
    before = snapshot(lib.loras)
    ink = {"id": "flux2_klein_9b/comic_ink_lineart.safetensors"}
    await routes.list_loras(lib, FakeRequest({"model": "flux2_klein_9b"}))
    await routes.patch_user(lib, FakeRequest(ink, b'{"strength": 1}'))
    await routes.thumb(lib, FakeRequest({"id": "flux2_klein_9b/style/film-grain.safetensors", "size": "336"}))
    assert snapshot(lib.loras) == before


def test_loras_register_one_listing_and_no_routes_that_write_more():
    assert manifest.MODULE.screen is None and manifest.MODULE.actions == ()
    assert [t.name for t in tools_of(manifest.MODULE)] == ["list_loras"]
    assert {(r.method, r.path) for r in manifest.MODULE.routes} == {("GET", ""), ("PATCH", "/user"), ("GET", "/thumb")}


async def test_list_loras_gives_the_panel_facts_for_a_model(lib):
    tool = tools_of(manifest.MODULE)[0]
    assert tool.description == "LoRAs in a model's folder: id, name, trigger words from the file, default strength."
    assert tool.input_schema == {"type": "object", "additionalProperties": False,
                                 "properties": {"model": {"type": "string"}}, "required": ["model"]}
    out = await tool.fn(lib, check(tool.input_schema, {"model": "flux2_klein_9b"}))
    assert [x["name"] for x in out["loras"]] == ["Comic Ink Lineart", "Film Grain Pro", "Inside Link", "X"]
    assert out["loras"][0] == {"id": "flux2_klein_9b/comic_ink_lineart.safetensors", "name": "Comic Ink Lineart",
                               "triggers": ["inkstyle", "bold lines", "sketch", "extra"], "default_strength": 0.7}
    assert set(out["loras"][1]) == {"id", "name", "triggers", "default_strength"}, "no cover, no owner strength"
    assert await tool.fn(lib, {"model": "unknown"}) == {"loras": []}
    with pytest.raises(Invalid, match="model is required"):
        check(tool.input_schema, {})
    lib.engine = FakeEngine(None)
    with pytest.raises(Invalid, match="The engine's Python or folder is not set up; run hub init"):
        await tool.fn(lib, {"model": "flux2_klein_9b"})
