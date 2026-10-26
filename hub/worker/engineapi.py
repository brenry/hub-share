"""The Hub's side of the engine seam (Stage 9, R9 §3): the types the Hub speaks, one adapter protocol, `select`.

Stdlib only, and engine-free: no engine key, no model name. What an engine calls things lives in its adapter
(`hub/worker/adapters/`), and what it does not publish in the adapter's facts file. Every type here crosses the wire
as a plain dict (`enginewire.wire`) and comes back through `enginewire.parse`, which refuses a field it does not know.
The wire (`protocol.PROTO` 2) carries a request in the words of `enginerequests` (re-exported here): a picture, a
clip, a spoken line or a join. A request names its pictures by the Hub's roles (`Reference.role`): a picture model's
`reference`; a clip's `start` and `end` frames, the `source` clip it continues, or an `identity`. The adapter turns
a request into the task its engine takes (`Adapter.task`, from the model's catalog entry): the keys, the prompt
letters, the reference list and the window are the adapter's alone.
"""
from __future__ import annotations

import json
import os
import typing
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

try:
    from .enginerequests import (  # noqa: F401  (re-exported: the seam's request types)
        KIND_ROLES,
        REQUESTS,
        ROLES,
        Canvas,
        ClipRequest,
        Duck,
        FramesRequest,
        JoinItem,
        JoinRequest,
        JoinSound,
        Loudness,
        MixClip,
        MixLane,
        PictureRequest,
        Reference,
        Request,
        SoundRequest,
        SpeechRequest,
        VoiceRequest,
    )
except ImportError:  # run as a script by the engine's Python
    from enginerequests import (  # noqa: F401
        KIND_ROLES,
        REQUESTS,
        ROLES,
        Canvas,
        ClipRequest,
        Duck,
        FramesRequest,
        JoinItem,
        JoinRequest,
        JoinSound,
        Loudness,
        MixClip,
        MixLane,
        PictureRequest,
        Reference,
        Request,
        SoundRequest,
        SpeechRequest,
        VoiceRequest,
    )

STAGES = ("cancelled", "oom", "generation", "runtime")     # a Failure's stage


@dataclass(frozen=True)
class EngineInfo:
    engine: str                    # the adapter's id
    version: str
    watch: list[str] = field(default_factory=list)   # paths whose change invalidates the catalog


@dataclass(frozen=True)
class Steps:
    default: int | None
    min: int | None = None
    max: int | None = None
    locked: bool = False


@dataclass(frozen=True)
class Guidance:
    default: float | None


@dataclass(frozen=True)
class Loras:
    dirs: list[str]
    recursive: bool


@dataclass(frozen=True)
class References:
    roles: list[str]
    min: int
    max: int


@dataclass(frozen=True)
class Frames:
    min: int
    step: int
    max: int
    default: int


@dataclass(frozen=True)
class Tier:
    name: str
    sizes: dict[str, list[int]]    # aspect -> [w, h]


@dataclass(frozen=True)
class Encoders:
    ids: list[str]
    names: dict[str, str]
    default: str | None
    found: list[str] | None        # None: the adapter cannot tell


@dataclass(frozen=True)
class Video:
    fps: int
    frames: Frames
    tiers: list[Tier]
    encoders: Encoders
    one_pass: bool                 # the adapter can keep a clip in one pass
    continues: bool = False
    overlap: int | None = None


@dataclass(frozen=True)
class ModelFacts:
    id: str
    name: str
    family: str
    status: str                    # missing | partial | available
    kind: str                      # image | video | speech
    base: str | None
    steps: Steps
    guidance: Guidance | None
    block: int
    loras: Loras | None
    references: References | None
    video: Video | None
    why_not: str | None = None     # one plain line: the engine has the model, the adapter cannot drive it




@dataclass(frozen=True)
class Loading:
    model: str


@dataclass(frozen=True)
class Loaded:
    model: str


@dataclass(frozen=True)
class Progress:
    phase: str
    step: int | None
    steps: int | None
    text: str = ""


@dataclass(frozen=True)
class Output:
    path: str


@dataclass(frozen=True)
class Failure:
    stage: str                     # one of STAGES
    text: str


@dataclass(frozen=True)
class Done:
    ok: bool
    model: str | None
    error: Failure | None = None


EVENTS: dict[str, type] = {c.__name__.lower(): c for c in (Loading, Loaded, Progress, Output, Done)}


@dataclass(frozen=True)
class KeyFamilies:
    """How one engine names a key per model family, as its adapter's facts file says (None: the engine has no such
    convention, and the rule finds nothing). Prefix fields are whole definition field names; suffix fields end a
    definition field, a setting or a `generate_video` keyword whose start is the family's own."""
    manifest: str | None = None          # field: the model takes an ordered identity reference list
    manifest_limits: str | None = None   # field: {kind: cap} for that list
    detail_choices: str | None = None    # field: (label, value) pairs of the reference detail
    detail_default: str | None = None    # field: the default value among them
    references: str | None = None        # suffix: the setting that is the reference list (the task key)
    detail: str | None = None            # suffix: the setting that is the reference detail (the task key)
    one_pass: str | None = None          # suffix: the switch that chains passes
    sidecar: str | None = None           # suffix: a flag saying the model runs in another runtime
    encoder: str | None = None           # suffix: the text encoder task key ...
    encoder_default: str | None = None   # ... + this: the definition field holding its default
    encoder_variants: str | None = None  # ... + this: the definition field holding its variants

    def suffixes(self) -> dict[str, str]:
        """{rule: the suffix it matches}, for the rules this engine has."""
        pairs = {"references": self.references, "detail": self.detail, "one_pass": self.one_pass,
                 "sidecar": self.sidecar,
                 "encoder_default": self.encoder and self.encoder_default and self.encoder + self.encoder_default,
                 "encoder_variants": self.encoder and self.encoder_variants and self.encoder + self.encoder_variants}
        return {k: v for k, v in pairs.items() if v}

    def fields(self) -> list[str]:
        """The whole definition field names this engine's families use."""
        return [v for v in (self.manifest, self.manifest_limits, self.detail_choices, self.detail_default) if v]


@runtime_checkable
class Adapter(Protocol):
    """One engine line behind the seam. `probe(root, session)`: the root (and, once opened, its session) is one this
    adapter drives; `facts()`: its facts file; `task(request, entry)`: a request as the engine task, from the model's
    catalog entry; `translate`: that task as the engine takes it, forced values on top (`factory_underneath`: the
    factory settings under it). `factory_settings`, `lora_root`, `lora_search` and `lora_recursive`: the engine's own
    answers the catalog helpers ask for; `native`: the clip facts a line publishes otherwise (`{"why_not": line}`: one
    it cannot drive); `line_facts`: what a definition does not say; `forced_config`: what its config must hold;
    `prepare`, `opened(w)`, `lacking`: what the engine would fetch, found before it tries (`faults`); the frames one
    pass holds (`window`) and a continue leaves off its source (`dropped`); `pointers`, `modelfiles`;
    `finish`: what the line does to a task's files before they are reported (a spoken line's joins)."""
    name: str
    flavour: str
    families: KeyFamilies
    factory_underneath: bool
    lora_recursive: bool
    forced_config: dict[str, Any]
    READS: dict[str, dict[str, str]]
    pointers: Any; modelfiles: Any  # noqa: E702

    def probe(self, root: str, session: Any = None) -> bool: ...
    def facts(self) -> dict[str, Any]: ...
    def task(self, request: Any, entry: dict) -> dict: ...
    def translate(self, task: dict, factory: dict) -> dict: ...
    def factory_settings(self, w: Any, model_type: str) -> dict: ...
    def lora_root(self, w: Any) -> str: ...
    def lora_search(self, w: Any, model_type: str) -> list[str]: ...
    def prepare(self, root: str) -> None: ...
    def opened(self, w: Any) -> None: ...
    def lacking(self, w: Any, model_type: str | None) -> list[str]: ...
    def native(self, w: Any, model_type: str, model_def: dict) -> dict[str, Any] | None: ...
    def line_facts(self, w: Any, model_type: str, model_def: dict) -> dict[str, Any]: ...
    def window(self, task: dict) -> int | None: ...
    def dropped(self, task: dict) -> int: ...
    def finish(self, request: Any, sent: dict, files: list[str]) -> dict[str, Any] | None: ...   # + a verdict
    def plan(self, session: Any, task: dict) -> dict[str, Any]: ...   # the engine's plan of a task


def read_facts(path: str) -> dict[str, Any]:
    """An adapter's facts file: one JSON object holding `families` (`KeyFamilies` fields) and `models`."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("families"), dict):
        raise ValueError(f"{os.path.basename(path)}: not an adapter facts file")
    return data


class NoAdapter(LookupError):
    """No adapter drives this root: the text is the one line shown."""


def select(root: str, adapters: typing.Sequence[Adapter], session: Any = None) -> Adapter:
    """The first adapter (in probe order) whose `probe` accepts the root; NoAdapter (one line) when none does."""
    for adapter in adapters:
        if adapter.probe(root, session):
            return adapter
    raise NoAdapter(f"No engine adapter drives {root} (looked for: {', '.join(a.name for a in adapters)})")
