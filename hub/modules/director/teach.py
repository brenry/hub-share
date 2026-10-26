"""What the script tools say: `SAY`, each tool's description (one line of
at most 200 characters ending with ".", `hub/core/registry.py`), and `CITES`, the numbers of
`docs/video-plan/research/R49-dialogue-coverage-and-exchange.md` the words of a description rest on.
`shot_add`, `line_add` and `cue_add` say what their fields hold, as the block's "Directing a script" paragraph teaches
(the camera: framing, who is in frame and the reason; a line: the speaker's own words, acting on the other; a cue:
a sound the story names or the audience's reaction); `scene_add` and `scene_change` carry the length named,
which is the length rule (`length.py`) and cites no R49 number. `shot_add` and `event_change` name the camera object;
`script_lock` and `script_unlock` come last. `shot_add` and `line_add` say they only add and name the tool that
changes (not R49); `event_move`, `event_change` and `event_remove` say `ref` names what the
message names; `CITES` rests on the words kept. `scene_change` names `done`, `event_remove` an empty shot (PLAN
Step 7b items 3, 4). `script_track` (its `Action` is `track.ACTION`); `script_stems` last (`mix.ACTION`).
`scene_change`, `script_lock`, `script_unlock` and `script_track` say what each does: `done` marks a scene written,
`script_lock` starts the takes as `script_track` does, `script_unlock` clears the record of the last takes,
`script_track` takes any written script, locked or not.
`script_say` first, the chat message whole; `script_start` says the Hub writes the whole script in its
chat. `script_render` last (`render.ACTION`). `script_say` takes every message of a script
chat (the Hub reads render and done itself); the block's Scripts paragraph is that one rule, and teaches no tool,
field or syntax of the others.
"""
from __future__ import annotations

SAY = {
    "script_say": "Every message of the script chat, the words exactly: the Hub writes the story, "
                  "changes what the message asks, renders or says it done, and answers its line; reply with it, call "
                  "nothing else.",
    "script_start": "Start a new script from a story; the Hub asks the model for its context, cast from "
                    "Characters only; in the Hub's chat it writes the whole script from the chat message.",
    "context_set": "Add a cast member to the script's context or replace that member's given fields, and replace the "
                 "set's and the style's given fields; to renames a member everywhere; remove: true takes a member "
                 "out.",
    "scene_add": "Add a scene at the end of the script, its cast from the context; seconds: the length named "
                 "for it, the Director's target: each answer says it and what the scene runs.",
    "scene_change": "Set the length named for a scene by its number, in seconds (0 takes it off); done: "
                    "true marks it written.",
    "shot_add": "Add a shot to a scene, after one of its shots or at its end; camera: framing, move, on: who is in "
                "frame; seconds held; action: what we see happen in it.",
    "line_add": "Add a new line after a shot's last line, never in place of one (event_change does that): the "
                "speaker's own words and own voice, acting on the other, who answers it; never the "
                "narration copied.",
    "cue_add": "Add a sound cue to a shot, at a line's start or end or after its last line: a sound the story names, "
               "or the audience reacting to what happens on stage.",
    "pose_add": "Add a character's pose to a shot, at a line's start or end or start_ms after the shot's start.",
    "event_move": "Move a line, cue or pose to start start_ms after the start of its shot, or of the named shot of "
                  "its scene; ref names it as the message does: {speaker, nth} or {cue, nth}.",
    "event_change": "Change a line's, cue's or pose's fields, or a shot's (fields {camera: {framing, move, on}, "
                    "seconds, action}); ref names it as the message does: {speaker, nth}, {cue, nth}, {shot: n}.",
    "event_remove": "Remove a line, cue or pose, or an empty shot; ref names it as the message does: {speaker, nth} "
                    "the speaker's nth line, {cue, nth}, {shot: n}, counted in the scene in timeline order.",
    "script_read": "Read the open script, or open the script of that name and read it.",
    "script_lock": "Start the open script's takes, as script_track does.",
    "script_unlock": "Clear the open script's record of its last takes; the next script_track records it again.",
    "script_track": "Render the open script's lines, cues and the room, one take each where none is or it changed, "
                    "judged and levelled; any written script, locked or not.",
    "script_stems": "Mix the open script again and write one WAV per lane beside its track.",
    "script_render": "Render the open script as one video, locked or not: each shot's clip from its camera, cast and "
                     "lines, joined in order; no voice file, take or lock is needed.",
}

CITES = {
    "scene_add": (),                                   # the length rule (`length.py`)
    "scene_change": (),
    "shot_add": ("7.1.1", "7.1.3", "1.4", "1.7", "1.13", "7.4.2", "2.3", "7.2.5", "7.2.6"),
    "line_add": ("7.5.1", "7.5.3", "7.5.2", "5.1", "5.2", "5.8", "5.6", "7.3.5",
                 "5.4", "7.5.6", "7.5.5", "5.5"),
    "cue_add": ("7.3.6", "4.4"),
}
