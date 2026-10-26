"""The requests the Hub sends across the engine seam (`engineapi`), in the Hub's words. Stdlib only, engine-free.

`PictureRequest` (one picture), `ClipRequest` (one clip), `SpeechRequest` (one spoken line: the speaker's voice sample,
or the words that describe the voice when there is none), `JoinRequest` (clips joined in the worker, no model),
`VoiceRequest` (a clip's voice turned into a speaker's, its picture kept), `SoundRequest` (a sound from a prompt
alone, the scene's audience) and `FramesRequest` (frames of a clip at full size, in the worker, no model). A request
names its pictures by the Hub's roles (`Reference.role`); each kind takes the roles `KIND_ROLES` gives it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

ROLES = ("reference", "start", "end", "source", "identity")   # a request picture's role (`Reference.role`)
KIND_ROLES = {"image": ("reference",), "video": ("start", "end", "source", "identity"),   # the roles each
              "speech": (), "voice": (), "sound": (), "frames": ()}                            # kind takes


@dataclass(frozen=True)
class Reference:
    path: str                      # absolute: the engine takes it as it is
    role: str                      # one of ROLES
    name: str | None = None        # an identity's character name, when its box is a listed character
    cutout: bool = False           # an identity's background cut out


@dataclass(frozen=True)
class PictureRequest:
    kind: ClassVar[str] = "image"
    model: str
    prompt: str
    size: tuple[int, int]
    seed: int | None               # None: no seed sent, the engine's own default
    steps: int | None = None
    guidance: float | None = None
    loras: list[tuple[str, float]] = field(default_factory=list)   # (the engine's LoRA name, strength)
    references: list[Reference] = field(default_factory=list)


@dataclass(frozen=True)
class ClipRequest:
    kind: ClassVar[str] = "video"
    model: str
    prompt: str
    size: tuple[int, int]
    seed: int | None               # None: no seed sent, the engine's own default
    frames: int                    # the clip's frames; continuing a `source`, the new part
    steps: int | None = None
    loras: list[tuple[str, float]] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    encoder: str | None = None     # a text encoder the catalog lists; None: the model's default
    detail: str | None = None      # an identity detail the catalog lists; None: the model's default
    one_pass: bool = True
    sound: str | None = None       # a sound the clip follows and keeps (absolute); None: the model's own
    sound_seconds: float | None = None   # that sound's length: the clip's
    video: str | None = None       # a reference video for the camera and the set (absolute); None: none
    video_seconds: float | None = None   # that video's length
    judge: str | None = None       # the face judge's device, "cpu" or "cuda"; None: not judged
    judge_bar: float = 0.3         # the similarity under which a face counts as lost
    speaker: str | None = None     # whose mouth the mouth judge reads; None: the one character, or largest
    voices: list[str] = field(default_factory=list)   # voice samples as audio references (absolute, in
                                                      # speaker order, at most 3); never beside `sound`
    words: str | None = None       # the shot's spoken words, heard by the words judge with `judge`


@dataclass(frozen=True)
class JoinItem:
    path: str                      # the clip's (or sound's) real path
    in_: int = field(metadata={"wire": "in"})   # first frame kept (a sound: its millisecond)
    out: int                       # first frame dropped
    fps: float                     # a sound: 1000, its milliseconds counted as frames
    w: int                         # a sound: 0
    h: int
    frames: int                    # a sound: its length in milliseconds
    audio: bool
    sound: bool = False            # a sound of track 1: no picture


@dataclass(frozen=True)
class JoinSound:
    path: str                      # a track-2 item's real path: a sound, or a clip whose sound alone is heard
    at_ms: int                     # where it starts in the saved file
    in_: int = field(metadata={"wire": "in"})   # as `JoinItem`: frames of a clip, milliseconds of a sound
    out: int
    fps: float
    level: float = 1.0             # a factor, 0 to 2
    fade_in: int = 0               # milliseconds at its start
    fade_out: int = 0              # milliseconds at its end
    duck: bool = False             # pressed down under track 1's sound


@dataclass(frozen=True)
class Duck:
    """The compressor keyed by track 1 that ducks a bed: the sequence module's settings."""
    threshold: float = 0.05
    ratio: float = 6.0
    attack: float = 50.0           # ms
    release: float = 400.0         # ms


@dataclass(frozen=True)
class Canvas:
    w: int
    h: int
    fps: float


@dataclass(frozen=True)
class MixClip:
    """A take placed on a lane of the mix: its kept span `in_ms`..`out_ms` of the file, at `at_ms`."""
    path: str                      # the take's real path
    at_ms: int
    in_ms: int
    out_ms: int
    gain_db: float                 # its measured gain
    fade_in: int                   # milliseconds
    fade_out: int
    loop: bool = False             # the room: its span looped to the mix's length


@dataclass(frozen=True)
class MixLane:
    name: str
    kind: str                      # "dialogue", "reaction", "effect", "music" or "room"
    gain_db: float
    duck: bool                     # pressed under the dialogue (reaction, effect, music only)
    clips: list[MixClip]


@dataclass(frozen=True)
class Loudness:
    lufs: float
    true_peak_dbtp: float


@dataclass(frozen=True)
class JoinRequest:
    kind: ClassVar[str] = "join"
    items: list[JoinItem]          # play order
    canvas: Canvas                 # the first item's
    audio: list[JoinSound]         # track 2: placed sounds, mixed under track 1's
    crf: int
    preset: str
    out_kind: str = "mp4"          # "mp4" (track 1 holds clips) or "wav" (sound only)
    duck: Duck = field(default_factory=Duck)   # how a ducked sound is pressed
    lanes: list[MixLane] = field(default_factory=list)   # a mix (`mixcmd`); empty: a plain join
    target: Loudness | None = None  # the mix's master; None with `solo`
    solo: int | None = None        # a stem: only lane `solo` heard, no master
    length_ms: int = 0             # the mix's length


@dataclass(frozen=True)
class SpeechRequest:
    kind: ClassVar[str] = "speech"
    model: str
    prompt: str                    # the line as typed (its own `[…]` directions kept)
    seed: int | None               # None: no seed sent, the engine's own default
    seconds: int                   # the most the line may take (the model's duration cap)
    sample: str | None = None      # the speaker's voice sample (`<Name>.wav`, absolute); None: the voice is invented
    direction: str | None = None   # the words for the voice when there is no sample (the character's `Voice`)
    turn_seconds: float | None = None   # a line planned longer goes as one turn per group of sentences
    pace: float | None = None           # the voice's measured words per second; None: the engine's 2.6
    judge: bool = False                 # the words judge hears the take and scores it
    join_seconds: float | None = None   # the crossfade at each join of a line sent as turns; None: none
    measure: bool = False               # its speech boundaries and loudness measured (`takemeasure`)


@dataclass(frozen=True)
class VoiceRequest:
    kind: ClassVar[str] = "voice"
    clip: str                      # the clip whose voice is turned (absolute); sent empty, filled by the lane from
                                   # the step that made it (`JobPlan.inputs`)
    sample: str                    # the speaker's voice sample (`<Name>.wav`, absolute)
    seed: int | None               # None: no seed sent, the engine's own default


@dataclass(frozen=True)
class SoundRequest:
    kind: ClassVar[str] = "sound"
    model: str                     # a model the catalog marks `sounds`, or a cue's kind `sound`
    prompt: str                    # the sound described, never a script
    seed: int | None               # None: no seed sent, the engine's own default
    seconds: int                   # its length, exactly
    measure: bool = False          # measured on arrival (`takemeasure`, no words)
    decay: bool = False            # and its natural decay read (`decay_ms`), a reaction cue's


@dataclass(frozen=True)
class FramesRequest:
    kind: ClassVar[str] = "frames"
    clip: str                      # the clip (absolute); sent empty, filled by the lane from the step that made it
    frames: tuple[int, ...]        # 0-based frame indices: one full-size PNG each, in this order


REQUESTS: dict[str, type] = {c.kind: c for c in (PictureRequest, ClipRequest, SpeechRequest, JoinRequest,
                                                 VoiceRequest, SoundRequest, FramesRequest)}
Request = PictureRequest | ClipRequest | SpeechRequest | JoinRequest | VoiceRequest | SoundRequest | FramesRequest
