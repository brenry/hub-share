"""Helpers for the image-engine tests: a fake engine root, the real worker on a socketpair,
safetensors writers, folder snapshots and a minimal module context (api.Ctx)."""
from __future__ import annotations

import copy
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hub.core import characters
from hub.core.api import Invalid, Job
from hub.core.files import Files
from hub.core.thumbs import ThumbStore
from hub.settings import DEFAULTS
from hub.worker import adapters, engineapi, enginewire, protocol

HERE = Path(__file__).resolve().parent
FAKE_ENGINE = HERE / "fake_engine"
FIXTURES = HERE.parent / "fixtures"
FAKE_WORKER = HERE.parent / "fakes" / "fake_worker.py"
WORKER = HERE.parents[1] / "hub" / "worker" / "main.py"
ENGINE_PYTHON = os.environ.get("HUB_TEST_ENGINE_PYTHON", sys.executable)


def write_lora(path: Path, meta: dict[str, str] | None = None, tensors: dict | None = None) -> Path:
    header: dict[str, Any] = dict(tensors or {"a.lora_down.weight": {"dtype": "F16", "shape": [16, 64],
                                                                      "data_offsets": [0, 2048]}})
    if meta is not None:
        header["__metadata__"] = meta
    raw = json.dumps(header).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"\0" * 2048)
    return path


UPSTREAM_H3 = FIXTURES / "upstream-18.05" / "h3.json"
SETTING_NAMES = '''"""Upstream's `shared/utils/setting_names.py` as the test root carries it: the accepted settings of
the captured fixture (tests/fixtures/upstream-18.05/h3.json), which the upstream adapter checks each task against."""
import json

_FIXTURE = {fixture!r}


def accepted_setting_names():
    with open(_FIXTURE, encoding="utf-8") as f:
        return list(json.load(f)["accepted_settings"])
'''


def make_engine_root(base: Path, flavour: str = "upstream", *, h3: bool = False) -> Path:
    """A copy of the fake engine as it sits on a server: settings/, LoRA folders, its own config. `flavour` is
    "upstream" (current Wan2GP) or "legacy" (the older fork HocusPocus carries). `h3` (upstream only): the root as
    upstream 18.05 shows its H3 line and Qwen Image 2.1, from the capture (`upstream_h3`)."""
    assert not h3 or flavour == "upstream"
    root = base / "engine"
    shutil.copytree(FAKE_ENGINE, root, ignore=shutil.ignore_patterns("__pycache__"))
    spec = json.loads((root / "fake_engine.json").read_text())
    spec["flavour"] = flavour
    spec["fakes"], spec["hub_clip"] = str(HERE.parent / "fakes"), str(HERE.parents[1] / "hub" / "core" / "clip.py")
    config: dict[str, Any] = {}
    if h3:
        config = upstream_h3(root, spec)
    (root / "fake_engine.json").write_text(json.dumps(spec))
    (root / "settings").mkdir()
    for key in spec["lora_keys"].values():
        (root / "loras" / key).mkdir(parents=True, exist_ok=True)
    write_lora(root / "loras" / "flux2_klein_9b" / "grain.safetensors", {"modelspec.title": "Film Grain"})
    write_lora(root / "loras" / "flux2_klein_9b" / "style" / "ink.safetensors")
    (root / "wgp_config.json").write_text(json.dumps(
        {"services": {"api_key": "SECRET"}, "checkpoints_paths": ["ckpts"], "last_model_type": "z_image", **config}))
    return root


def upstream_h3(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """`make_engine_root(h3=True)`'s part: the root as upstream 18.05 shows its models, from the capture
    (`UPSTREAM_H3`, written from it): each captured model a definition file the fake loads as the real engine does
    (the definition whole, its own settings beside it) and, as the fake's knowledge of it, its factory settings as
    captured, its architecture (none of its own: the definitions are whole, and the fork's Omni architecture shares a
    name with upstream's 33B Ref2VA), its LoRA folder and its files present; the engine's version, families and
    accepted settings (`shared/utils/setting_names.py`), and no `generate_video` (18.05 has none). The fork's H3
    definitions and the fake's own Qwen Image 2.1 give way; the other picture models stay the fake's. Returns the
    server config the fixture names."""
    fixture = json.loads(UPSTREAM_H3.read_text(encoding="utf-8"))
    for old in [*(root / "defaults").glob("minimax_h3*.json"), *(root / "defaults").glob("qwen_image_21*.json")]:
        old.unlink()
    spec.update(version=fixture["engine"]["version"], settings_version=fixture["engine"]["settings_version"],
                families=fixture["families"], generate_video=None, factory={})
    for model_type, m in fixture["models"].items():
        definition = {**m["definition"], "architecture": m["architecture"], "family": m["family"]}
        own = definition.pop("settings", {})
        (root / "defaults" / f"{model_type}.json").write_text(json.dumps({"model": definition, **own}))
        spec["factory"][model_type] = m["factory"]
        spec["architectures"][m["architecture"]] = {"architecture": m["architecture"]}   # one fork arch shares a name
        spec["handler_defaults"].pop(m["architecture"], None)
        spec["lora_keys"][m["architecture"]] = m["lora_key"]
        spec["available"].append(model_type)
        for name in present(fixture["models"], model_type):       # a capture names a weight file by its base name
            (root / "ckpts" / name).parent.mkdir(exist_ok=True)
            (root / "ckpts" / name).touch()
    (root / "shared" / "utils" / "setting_names.py").write_text(SETTING_NAMES.format(fixture=str(UPSTREAM_H3)))
    return dict(fixture["server_config"])


def present(models: dict[str, Any], model_type: str) -> list[str]:
    """The files a captured model loads that the fake checks are here: its main weight file (a definition naming
    another model's files takes that model's) and the extra files it pulls in."""
    definition = models[model_type]["definition"]
    urls = definition.get("URLs") or []
    main = (present(models, urls)[:1] if urls in models else []) if isinstance(urls, str) else list(urls)[:1]
    return [*main, *(definition.get("preload_URLs") or []), *(definition.get("loras") or [])]


def snapshot(path: Path) -> dict[str, tuple[bool, int, int]]:
    """Every file and folder under `path` with its size and mtime: equal snapshots = no writes."""
    out = {}
    for folder, dirs, files in os.walk(path):
        for name in dirs + files:
            p = Path(folder) / name
            st = p.lstat()
            out[str(p.relative_to(path))] = (p.is_dir(), st.st_size, st.st_mtime_ns)
    return out


def task(model: str = "flux2_klein_9b", **extra: Any) -> dict[str, Any]:
    """A picture request as it crosses the wire (PROTO 2): the fake engine's small picture unless `extra` says
    otherwise (`PictureRequest` fields: prompt, size, seed, steps, guidance, loras, references)."""
    fields: dict[str, Any] = {"prompt": "a cat", "size": (64, 48), "seed": 7, **extra}
    return enginewire.request_wire(engineapi.PictureRequest(model, **fields))


def clip_task(model: str = "minimax_h3", **extra: Any) -> dict[str, Any]:
    """A clip request as it crosses the wire: the fake engine's shortest clip unless `extra` says otherwise
    (`ClipRequest` fields)."""
    fields: dict[str, Any] = {"prompt": "a shot", "size": (960, 544), "seed": 7, "frames": 124, "steps": 2, **extra}
    return enginewire.request_wire(engineapi.ClipRequest(model, **fields))


class Worker:
    """The real worker process on a socketpair, driven synchronously."""

    def __init__(self, root: Path, state: Path, *engine_args: str, parent: int | None = None,
                 python: str = ENGINE_PYTHON) -> None:
        self.sock, child = socket.socketpair()
        argv = [python, "-B", str(WORKER), "--fd", str(child.fileno()), "--parent", str(parent or os.getpid()),
                "--root", str(root), "--state", str(state), "--", *engine_args]
        self.proc = subprocess.Popen(argv, pass_fds=(child.fileno(),), stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        child.close()
        self.buf = protocol.LineBuffer()
        self.seen: list[dict[str, Any]] = []

    def send(self, message: dict[str, Any]) -> None:
        self.sock.sendall(protocol.encode(message))

    def until(self, done: Callable[[dict[str, Any]], bool], timeout: float = 20.0) -> list[dict[str, Any]]:
        got: list[dict[str, Any]] = []
        end = time.monotonic() + timeout
        while True:
            self.sock.settimeout(max(0.01, end - time.monotonic()))
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError(f"worker closed; got {got}")
            for line in self.buf.feed(chunk):
                msg = protocol.decode(line)
                got.append(msg)
                self.seen.append(msg)
                if done(msg):
                    return got

    def close(self) -> None:
        self.sock.close()
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


def engine_task(request: dict[str, Any], catalog: dict[str, Any] | None) -> dict[str, Any]:
    """The engine task the worker's adapter makes of a module's request (a plan task) for the catalog's engine line,
    key for key."""
    parsed = enginewire.request_parse(request)
    entry = next(m for m in (catalog or {})["models"] if m["id"] == parsed.model)
    return adapters.by_flavour(((catalog or {}).get("engine") or {}).get("api", "legacy")).task(parsed, entry)


def load_catalog(name: str, loras: Path | None = None) -> dict[str, Any]:
    """A catalog fixture; with `loras`, every LoRA folder is moved under that local folder."""
    cat = json.loads((FIXTURES / name).read_text())
    if loras is not None:
        old = cat["engine"]["loras_root"]
        for m in cat["models"]:
            m["lora_dirs"] = [str(loras / os.path.relpath(d, old)) for d in m["lora_dirs"]]
    return cat


# ---------------------------------------------------------------- a minimal api.Ctx
class FakeDoc:
    def __init__(self, default: dict) -> None:
        self.value = copy.deepcopy(default)
        self.writes = 0

    def get(self) -> dict:
        return copy.deepcopy(self.value)

    def patch(self, changes: dict) -> dict:
        self.value.update(copy.deepcopy(changes))
        self.writes += 1
        return self.get()

    def replace(self, value: dict) -> None:
        self.value = copy.deepcopy(value)
        self.writes += 1


class FakeFiles:
    """Media roots under `data` (outputs, Drive) and, with `chars`, a Characters folder: the characters' own
    calls (characters, character, character_put) are hub.core.characters' over these roots, as in Files."""

    def __init__(self, data: Path, chars: Path | None = None) -> None:
        self.data = data
        self.roots = {"out": data / "outputs", "drive": data / "Drive"}
        if chars is not None:
            self.roots["chars"] = chars
        self.thumbs = ThumbStore()
        self.deleted: list[list[str]] = []

    def resolve(self, item_id: str) -> Path:
        root, _, rel = item_id.partition("/")
        if root not in self.roots or not rel or ".." in rel.split("/"):
            raise ValueError("That image is no longer available")
        return self.roots[root] / rel

    def existing_image(self, item_id: str) -> Path:
        try:
            path = self.resolve(item_id)
        except ValueError:
            raise Invalid("item", "That image is no longer available") from None
        root = os.path.realpath(self.roots[item_id.partition("/")[0]])
        if os.path.commonpath([root, os.path.realpath(path)]) != root or not path.is_file():
            raise Invalid("item", "That image is no longer available")
        return path

    def url(self, item_id: str) -> str:
        return f"/files/{item_id}"

    def kind(self, item_id: str) -> str | None:
        return Files.kind(self, item_id)   # type: ignore[arg-type]  # by the id alone, as the real one

    def regroup(self, ids: list[str], group: str) -> list[tuple[str, str]]:
        return Files(self.data).regroup(ids, group)

    def delete(self, ids: list[str]) -> list[str]:
        self.deleted.append(ids)
        return ids

    # the characters: hub.core.characters over these roots, as the real Files calls it
    @property
    def _real(self) -> dict[str, Path]:
        return {k: Path(os.path.realpath(v)) for k, v in self.roots.items()}

    def _drop_thumbs(self, src: Path) -> None:
        self.thumbs.forget(f"{src}|")

    def characters(self) -> list[dict]:
        return characters.listing(self)

    def character(self, name: str) -> str | None:
        return characters.find(self, name)

    def character_put(self, name: str, item_id: str) -> str:
        return characters.put(self, name, item_id)

    def character_rename(self, item_id: str, name: str) -> str:
        return characters.rename(self, item_id, name)

    def character_remove(self, item_id: str) -> str:
        return characters.remove(self, item_id)

    def character_notes(self, item_id: str, text: str) -> str:
        return characters.set_notes(self, item_id, text)

    def character_voice(self, item_id: str, text: str) -> str:
        return characters.set_voice(self, item_id, text)

    def character_sample(self, name: str) -> Path | None:
        return characters.sample_of(self, name)


class FakeBus:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict]] = []

    def publish(self, lane: str, type: str, data: dict) -> None:
        self.sent.append((lane, type, data))

    def presence(self) -> dict:
        return {}


class FakeEngine:
    def __init__(self, catalog: dict[str, Any] | None, resident: str | None = None) -> None:
        self.catalog, self.resident, self.calls = catalog, resident, 0
        self.files: list[dict[str, Any]] = []        # the weights panel's per-file records
        self.plan: Any = {"valid": True, "windows": [], "warnings": [], "errors": [], "notes": []}
        self.planned: list[Any] = []                   # the requests asked to plan

    async def query(self, what: str, **args: Any) -> dict:
        self.calls += 1
        if self.catalog is None:
            raise RuntimeError("The engine's Python or folder is not set up; run hub init")
        if what == "weights":
            present = [m for m in self.catalog["models"] if m.get("status") in ("available", "partial")]
            return {"bases": [{"id": m["id"], "name": m["name"]} for m in present], "files": self.files}
        if what == "plan":                            # the plan a test gave (`plans`), keyed by nothing
            self.planned.append(args.get("request"))
            if isinstance(self.plan, Exception):
                raise self.plan
            return copy.deepcopy(self.plan)
        return {**copy.deepcopy(self.catalog), "resident": self.resident}


class FakeJobs:
    """Builds plans with the module's own builder; every job starts queued, as in core."""

    def __init__(self, ctx: FakeCtx, builders: dict[str, Callable[..., Any]]) -> None:
        self.ctx, self.builders, self.jobs = ctx, builders, {}

    def submit(self, kind: str, params: dict) -> Job:
        plan = self.builders[kind](copy.deepcopy(params), self.ctx)
        job = Job(id=f"j_{len(self.jobs) + 1}", kind=kind, tool=kind.split(".")[0], state="queued", plan=plan)
        self.jobs[job.id] = (job, params)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id, (None,))[0]

    def cancel(self, job_id: str) -> Job | None:
        return self.get(job_id)

    def note(self, job_id: str, **values: Any) -> Job | None:
        job = self.get(job_id)
        if job is not None:
            job.notes.update(values)
        return job

    def refuse(self, job_id: str, text: str) -> Job | None:
        job = self.get(job_id)
        if job is not None and job.state == "queued":
            job.error, job.state = text, "failed"
        return job

    def card(self, job_id: str) -> dict | None:
        """The queue's card (`JobBook.record`'s fields the takes line reads)."""
        job = self.get(job_id)
        if job is None:
            return None
        task = getattr(job, "task", 0)
        return {"id": job_id, "state": job.state, "position": getattr(job, "position", None),
                "progress": {"index": task, "count": len(job.plan.tasks)} if task else None,
                "summary": getattr(job.plan, "summary", {})}


class FakeCtx:
    def __init__(self, module_id: str, data: Path, engine: FakeEngine,
                 builders: dict[str, Callable[..., Any]] | None = None) -> None:
        self.module_id, self.data_dir = module_id, data / module_id
        self.settings = copy.deepcopy(DEFAULTS["modules"].get(module_id, {}))   # as validated settings give it
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.files, self.bus, self.engine = FakeFiles(data), FakeBus(), engine
        self.jobs = FakeJobs(self, builders or {})
        self.docs: dict[str, FakeDoc] = {}
        self.events: list[tuple[str, dict]] = []
        self.services: dict[str, Callable[..., Any]] = {}   # what `offer` put there

    def doc(self, name: str, default: dict) -> FakeDoc:
        return self.docs.setdefault(name, FakeDoc(default))

    def emit(self, event: str, data: dict) -> None:
        self.events.append((event, data))

    def offer(self, name: str, fn: Callable[..., Any]) -> None:
        self.services[name] = fn

    def service(self, name: str) -> Callable[..., Any]:
        if name not in self.services:
            raise Invalid("assistant", "The assistant is not running")
        return self.services[name]


class FakeRequest:
    def __init__(self, query: dict[str, str] | None = None, body: bytes = b"") -> None:
        self.query_params, self._body = query or {}, body

    async def body(self) -> bytes:
        return self._body

    async def json(self) -> Any:
        return json.loads(self._body)
