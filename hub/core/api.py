"""The module surface: the ONLY core file a module may import. Contract owned by the lead.
Builders implement the behaviour behind it; they do not change names or signatures without the lead. Stdlib only."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

# ---------------------------------------------------------------- vocabulary
Kind = Literal["image", "video", "audio", "mask", "text"]
Auth = Literal["screen", "public"]
CardStatus = Literal["ok", "attention", "off", "error"]
JobState = Literal["queued", "running", "done", "failed", "cancelled"]
LaneKind = Literal["image"]

class Invalid(Exception):
    """Raised by a module for bad input. Becomes HTTP 400 / bus `error` with {field, text}."""
    def __init__(self, field: str, text: str):
        super().__init__(text); self.field, self.text = field, text  # noqa: E702

# ---------------------------------------------------------------- declarations
@dataclass(frozen=True)
class Tab:
    label: str
    order: int

@dataclass(frozen=True)
class SocketGroup:
    id: str
    label: str
    kinds: tuple[Kind, ...]
    max: int

@dataclass(frozen=True)
class Route:
    """HTTP route mounted at /api/<module-id><path>; `fn` is async (ctx, request) -> Response | dict | list."""
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    fn: Callable[..., Awaitable[Any]]
    auth: Auth = "screen"
    body_limit: int = 65_536

@dataclass(frozen=True)
class CardState:
    summary: str                               # one short line, plain words, no directives
    status: CardStatus

@dataclass(frozen=True)
class Card:
    """A small Settings card; its panel is ui module `<id>/Card.tsx`. `order`: Generate Image 880, Network 900."""
    title: str
    order: int
    state: Callable[[Ctx], CardState]          # cheap, sync, from memory only

SettingKind = Literal["choice", "number", "integer", "text", "loras", "seed", "names", "object"]

@dataclass(frozen=True)
class Setting:
    """One control of a screen, as the core publishes it (`hub/core/features.py`). `text` is a short factual
    label ("Steps the model runs"), never an instruction. `choice` with no `choices` is any text, checked by the
    screen's `write` against a live list; `number` or `integer` with `choices` is one of those values; `text` is
    free text, at most `hi` characters when `hi` is set; `loras` is a list of {id, strength lo-hi}; `seed` is
    "random" or a whole number lo-hi, as text; `names` is a list of at most `hi` names, checked by the screen's
    `write` against a live list; `object` is as its `schema` says. Every bound is the module's."""
    name: str                                  # snake_case
    kind: SettingKind
    choices: tuple[str | int | float, ...] = ()
    lo: float | None = None
    hi: float | None = None
    text: str = ""; schema: Mapping[str, Any] | None = None  # noqa: E702  (an `object` setting's JSON Schema)

@dataclass(frozen=True)
class Screen:
    """A screen's saved settings. Published as `get_<id>_settings` and `set_<id>_settings`."""
    settings: tuple[Setting, ...]
    read: Callable[[Ctx], Awaitable[dict]]          # the settings now, as plain values
    write: Callable[[Ctx, dict], Awaitable[dict]]   # a partial change -> the settings after; raise Invalid

@dataclass(frozen=True)
class Listing:
    """A list the module can give. Published as `list_<name>`."""
    name: str                                  # snake_case
    text: str                                  # one factual line, ending with a period
    args: dict                                 # JSON Schema properties; may be empty
    fn: Callable[[Ctx, dict], Awaitable[dict]]
    required: tuple[str, ...] = ()

@dataclass(frozen=True)
class Action:
    """Something the module does. Published under its own name."""
    name: str                                  # snake_case, unique across modules
    text: str                                  # one factual line, ending with a period
    schema: dict                               # JSON Schema object, small
    fn: Callable[[Ctx, dict], Awaitable[dict]]  # returns compact JSON; raise Invalid on bad args

NO_MODEL = ""                                  # a job that loads no model (a join)

@dataclass(frozen=True)
class JobPlan:
    """What a job kind builder returns: N sequential tasks for one lane kind."""
    lane_kind: LaneKind
    model: str                                 # engine model id (for residency / VRAM planning), or NO_MODEL
    tasks: tuple[dict, ...]                    # engine requests (`request_wire`), one per picture or clip
    summary: dict                              # small, shown on cards: prompt, model label, loras, size, count
    inputs: tuple[Mapping[str, tuple[int, str]], ...] = ()   # task k's fields an earlier task's "file" fills
    prepare: Callable[[Callable[[str], None]], Awaitable[JobPlan]] | None = None   # builds the rest at start
    finish: Callable[[Mapping[int, str]], Awaitable[None]] | None = None   # last step, any end: task -> landed id
    takes: tuple[tuple[tuple[int, ...], ...], ...] = ()   # per shot, its takes, each its tasks (1-based) in order
    judge: Judge | None = None                 # asked on each take's `task_done`, read before the next take

@dataclass(frozen=True)
class Take:
    """A take's verdict: it passes every judge that ran; its rank, higher is better; its one line."""
    passes: bool
    rank: tuple[float, ...]
    line: str

class Judge(Protocol):
    """A job's judge step: `done` per take task's `task_done`; `again`: take t of shot s (1-based) may run."""
    def done(self, task: int, d: Mapping[str, Any]) -> Take | None: ...
    def again(self, shot: int, take: int) -> bool: ...

@dataclass(frozen=True)
class Module:
    id: str                                    # kebab-case; routes /api/<id>/, messages "<id>."
    title: str
    tab: Tab | None = None
    screens: tuple[str, ...] = ()
    sockets: tuple[SocketGroup, ...] = ()
    routes: tuple[Route, ...] = ()
    handlers: Mapping[str, Callable[..., Awaitable[Any]]] = field(default_factory=dict)
    lanes: tuple[str, ...] = ()                # bus lanes it publishes (auto-prefixed "<id>.")
    jobs: Mapping[str, Callable[[dict, Ctx], JobPlan]] = field(default_factory=dict)
    listens: Mapping[str, Callable[..., Awaitable[None]]] = field(default_factory=dict)
    card: Card | None = None
    screen: Screen | None = None               # the core publishes these three as MCP tools (`/mcp`)
    listings: tuple[Listing, ...] = ()
    actions: tuple[Action, ...] = ()
    start: Callable[[Ctx], Awaitable[None]] | None = None
    stop: Callable[[Ctx], Awaitable[None]] | None = None

# ---------------------------------------------------------------- runtime records
@dataclass(frozen=True)
class Device:
    """A paired screen: its id, its name, the addresses learned at pairing (accepted only from these)."""
    id: str
    name: str
    addrs: tuple[str, ...]

@dataclass(frozen=True)
class Resident:
    model: str

@dataclass
class Job:
    id: str
    kind: str                                  # e.g. "generate-image.image"
    tool: str                                  # module id
    state: JobState
    plan: JobPlan
    lane: str | None = None
    task: int = 0                              # 1-based current task
    pct: int = 0
    eta_s: float | None = None
    error: str | None = None
    outputs: list[str] = field(default_factory=list)   # media item ids
    notes: dict[str, Any] = field(default_factory=dict)   # learned after submit: `plan`, `judged`
    takes: dict[int, Take] = field(default_factory=dict)   # task -> its take's verdict, or a failed take

# ---------------------------------------------------------------- lanes (GPU work)
class JobLane(Protocol):
    """The image engine lane (core/engine.py): one local worker per GPU, seen by the VRAM manager. It runs queued
    jobs; events go to `emit`."""
    id: str                                    # "image.gpu0"
    kind: LaneKind
    gpu_uuid: str | None
    on_change: Callable[[], None]              # set by the VRAM manager; called when residency changes

    def residency(self) -> list[Resident]: ...
    def busy(self) -> bool: ...
    def pids(self) -> list[int]: ...                    # its processes: their GPU memory counts as the Hub's
    async def release(self, reason: str) -> bool: ...   # True when memory is free again
    def ready(self) -> bool: ...
    def reset(self) -> None: ...               # Start pressed: a `down` lane may start again
    async def run(self, job: Job, emit: Callable[[str, dict], None]) -> None: ...
    async def cancel(self, job_id: str) -> None: ...
    async def stop(self) -> None: ...          # hub shutdown: stop now, even mid-job

class JsonDoc(Protocol):  # ---------------------------------------------------------------- services in Ctx
    def get(self) -> dict: ...
    def patch(self, changes: dict) -> dict: ...  # shallow merge, debounced atomic write
    def replace(self, value: dict) -> None: ...

class Files(Protocol):
    roots: dict[str, Path]                     # "out" (Temp), "clips", "sounds", "scripts": Hub's own; "drive", "chars"
    thumbs: Any                                # the in-memory thumbnail store (`thumbs.ThumbStore`)
    storyboards: str | None                    # the storyboards folder, relative to the Drive (`paths.storyboards`)
    def resolve(self, item_id: str) -> Path: ...
    def existing_image(self, item_id: str) -> Path: ...   # raises Invalid unless it is an image file
    def existing_media(self, item_id: str) -> Path: ...   # an image, or a clip or sound in its root; else Invalid
    def kind(self, item_id: str) -> str | None: ...       # "image", "clip" (.mp4), "sound" (.wav) or None
    def clip_facts(self, item_id: str) -> dict | None: ...  # {w, h, fps, frames, seconds, audio}; None unreadable
    def sound_facts(self, item_id: str) -> dict | None: ...  # {seconds}; None when not a sound that reads
    def url(self, item_id: str) -> str: ...
    def thumb_url(self, item_id: str, size: int = 336) -> str | None: ...   # None for a clip or a sound
    def take_in(self, tmp: Path, suffix: str) -> str: ...    # a checked upload into Temp, named by the time
    def delete(self, ids: list[str]) -> list[str]: ...        # erases Temp and Drive files for good, thumbnails too
    def move(self, ids: list[str], to: str) -> list[tuple[str, str]]: ...   # Temp or Drive files into a Drive folder
    def regroup(self, ids: list[str], group: str) -> list[tuple[str, str]]: ...   # Temp files: out/<day>/<group>
    def folder_list(self, path: str) -> dict: ...             # {"path", "dirs", "ids"} of a drive folder
    def folder_new(self, path: str, name: str) -> str: ...
    def folder_rename(self, path: str, name: str) -> str: ...
    def folder_move(self, paths: list[str], to: str) -> list[str]: ...
    def folder_remove(self, path: str) -> None: ...           # erases the folder and its contents for good
    def characters(self) -> list[dict]: ...                   # [{name, id, notes, voice, sample}], by name
    def character(self, name: str) -> str | None: ...         # the id of the character called `name` (any case)
    def character_put(self, name: str, item_id: str) -> str: ...   # copy a picture in under a name, replacing
    def character_rename(self, item_id: str, name: str) -> str: ...   # the character's file renamed; new id
    def character_remove(self, item_id: str) -> str: ...      # the character's file erased; its name
    def character_notes(self, item_id: str, text: str) -> str: ...   # `text` saved in the file; its id
    def character_voice(self, item_id: str, text: str) -> str: ...   # the words for its voice, in the file; its id
    def character_sample(self, name: str) -> Path | None: ...  # `<Name>.wav` beside its picture, else None
    def character_views(self, name: str) -> list[str]: ...    # its view pictures' ids, `<Name>.<view>.*`
    def keep_voice(self, sound_id: str, name: str) -> str: ...   # a sound as `<Name>.wav`, replacing; its id
    def keep_audience(self, sound_id: str, kind: str) -> str: ...   # as `sounds/audience/<kind>.wav`, replacing
    def file_sound(self, item_id: str, name: str) -> str: ...   # to `sounds/audience/<name>.wav` when free; its id
    def put_picture(self, folder: str, name: str, src: str) -> str: ...   # "chars" or "drive/<path>"; replaces the stem
    def rename_picture(self, item_id: str, name: str) -> str: ...   # a named picture's new stem; type and text kept
    def picture_text(self, item_id: str) -> str: ...          # the text in a picture of a text folder, else ""
    def picture_text_set(self, item_id: str, text: str) -> str: ...   # saved in the file (now .png); its id
    def file_clip(self, item_id: str, group: str, name: str) -> str: ...   # clips/<its day>/<group>/<name>[-n].mp4
    def newest_temp(self) -> str | None: ...                  # the newest Temp picture by day and time name
    def sequences(self) -> list[dict]: ...                    # [{name, clips, seconds, changed}] by name
    def sequence(self, name: str) -> dict: ...                # {name, revision, tracks, dropped}; gone: dropped
    def sequence_new(self, name: str) -> dict: ...            # revision 0, two empty tracks
    def sequence_save(self, name: str, tracks: list, revision: int, limit: int | None = None) -> dict: ...  # CAS
    def sequence_rename(self, name: str, to: str) -> dict: ...   # {name, revision}; read before it moves
    def sequence_delete(self, name: str) -> None: ...         # the file only; never a clip
    def item_facts(self, item: dict) -> dict | None: ...      # a sequence item's {kind, id, fps, frames, seconds, ...}

class Bus(Protocol):
    def publish(self, lane: str, type: str, data: dict, key: str | None = None) -> None: ...  # key: newest replaces
    def presence(self) -> dict: ...

class Jobs(Protocol):
    def submit(self, kind: str, params: dict) -> Job: ...
    def get(self, job_id: str) -> Job | None: ...
    def cancel(self, job_id: str) -> Job | None: ...
    def note(self, job_id: str, **values: Any) -> Job | None: ...   # merge into `notes`; the card is published
    def refuse(self, job_id: str, text: str) -> Job | None: ...     # a queued job fails now with that one line
    def card(self, job_id: str) -> dict | None: ...   # as the queue shows it: `position`, `progress`

class Engine(Protocol):
    # "models" (rescan): the catalog; "weights" (choose): Image models; "files" (rescan, choose): each model's file
    # parts; "plan" (request): the engine's plan of a request; "voice": {on, lacking, line}.
    async def query(self, what: str, **args: Any) -> dict: ...

class Ctx(Protocol):
    module_id: str
    data_dir: Path                             # <data>/<module-id>/
    settings: Mapping[str, Any]                # read-only: settings["modules"][module_id]
    files: Files
    bus: Bus
    jobs: Jobs
    engine: Engine

    def doc(self, name: str, default: dict) -> JsonDoc: ...
    def emit(self, event: str, data: dict) -> None: ...   # internal core event to `listens`
    def offer(self, name: str, fn: Callable[..., Any]) -> None: ...   # a service other modules use by name
    def service(self, name: str) -> Callable[..., Any]: ...   # unknown: Invalid("assistant", ...)

# ------------------------------------------- pure helpers a module may call (stdlib only; `strip_picture`: Pillow)
from hub.core import checks, clean, clipplan, schema, sound, store, takeplan  # noqa: E402

whole, number, seed_value, seeds = checks.whole, checks.number, checks.seed_value, checks.seeds
schema_check, best_take = schema.check, takeplan.best   # a value against a JSON Schema; a best take
plain_name, write_json, strip_picture = checks.plain_name, store.write_json, clean.strip   # a picture's pixels alone
clip_facts, snap_frames, frames_for, tier_size = (clipplan.clip_facts, clipplan.snap_frames, clipplan.frames_for,
                                                  clipplan.tier_size)
sound_exact, sound_pad, speech_span = sound.exact, sound.pad, sound.speech_span   # a WAV: length; run on; heard

# ------------ a job's task: a request in the Hub's words (`request_wire(ClipRequest(...))`), no engine key (Stage 9)
from hub.worker.adapters.tasks import lipsync, spoken_line, turns  # noqa: E402, F401
from hub.worker.adapters.turns import words as spoken_words  # noqa: E402, F401  (its word count)
from hub.worker.engineapi import (  # noqa: E402, F401  (re-exported for modules)
    Canvas,
    ClipRequest,
    Duck,
    FramesRequest,
    JoinItem,
    JoinRequest,
    JoinSound,
    PictureRequest,
    Reference,
    SoundRequest,
    SpeechRequest,
    VoiceRequest,
)
from hub.worker.enginewire import request_wire  # noqa: E402, F401
