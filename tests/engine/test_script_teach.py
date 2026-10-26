"""What the script tools and the block teach (`script_say` and the Scripts paragraph's one-call rule; one rule, no other
script tool taught): each of the `ACTIONS` takes its text from `teach.SAY`, at most 200 characters ending with "."; the
five strings of `FIVE` word for word; every number in `teach.CITES` and in the block file's Scripts record bullet is a
numbered heading of R49; the block's text holds the Scripts paragraph word for word and not the Directing paragraph;
each of S1-S9 has its entry with R49 numbers in the record."""
from __future__ import annotations

import re
from pathlib import Path

from hub.modules.director import manifest, teach, tools

ROOT = Path(__file__).resolve().parents[2]
BLOCK = ROOT / "docs" / "video-plan" / "system-prompt-video-paragraph.md"
R49 = ROOT / "docs" / "video-plan" / "research" / "R49-dialogue-coverage-and-exchange.md"
NUMBER = re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")

FIVE = {
    "scene_add": "Add a scene at the end of the script, its cast from the context; seconds: the length named "
                 "for it, the Director's target: each answer says it and what the scene runs.",
    "scene_change": "Set the length named for a scene by its number, in seconds (0 takes it off); done: "
                    "true marks it written.",

    "shot_add": "Add a shot to a scene, after one of its shots or at its end; camera: framing, move, on: who is in "
                "frame; seconds held; action: what we see happen in it.",
    "line_add": "Add a new line after a shot's last line, never in place of one (event_change does that): the "
                "speaker's own words and own voice, acting on the other, who answers it; never the narration "
                "copied.",
    "cue_add": "Add a sound cue to a shot, at a line's start or end or after its last line: a sound the story names, "
               "or the audience reacting to what happens on stage.",
}
SCRIPTS = """Scripts. Every chat message in a chat about a script goes to script_say {words: "<the chat message,
exactly as written>"}, once and nothing else, even when it asks for a video or a render; reply with its line as
written and say nothing it does not say. A first chat message that tells a story starts the script."""
SAY = ("Every message of the script chat, the words exactly: the Hub writes the story, changes what the message "
       "asks, renders or says it done, and answers its line; reply with it, call nothing else.")
DIRECTING = """Directing a script. When the chat message tells the story, it is narration: you direct it as a scene of
several shots. Open on a wide shot or a two-shot that shows who is where, then carry the exchange in singles and
over-the-shoulder shots, with reaction shots of the one listening: a shot on the listener that holds the other's line.
Cut where a thought ends, on a look, or to show how a line lands; not each time the next one starts to talk. Each shot's
camera is a few words: the framing (wide, two-shot, over-the-shoulder, medium, close-up, insert), who is in frame, and
the reason for the cut as what is seen, for example: Close-up of Speaker 2 as the question lands. An important line does
not need a close-up. The dialogue is an exchange: each line does something to the other, who answers it (a question and
its answer, a push and the push back, an interruption); each beat tops the one before, and the scene turns on an action
or a revelation. Every line is that character's own words in the character's own voice: short, never the chat
message's narration copied, never telling the other what both already know. In questions and answers Speaker 1 asks
open questions and follows up; Speaker 2 gives the point first, never a bare yes or no. A cue only where the chat
message's story names a sound, or where the audience reacts to something on stage. If the chat message names a length,
give it to scene_add as seconds (a length for the whole story split across its scenes; scene_change when a later chat
message changes it); its answer and each shot line show how long the scene runs against that range: write more, or
cut, until it is inside, never by leaving silence. When a scene is written, call scene_change {scene, done: true}; it
refuses an empty shot, a silence or a length outside the range, each with its fix."""


def flat(text: str) -> str:
    return " ".join(text.split())


def headings() -> set[str]:
    """R49's numbered headings: a rule (`1.4 **…`) or a section (`### 7.6 …`)."""
    found = set()
    for line in R49.read_text(encoding="utf-8").splitlines():
        m = re.match(r"(?:### )?(\d+\.\d+(?:\.\d+)?) ", line)
        if m and (line.startswith("### ") or line[m.end():].startswith("**")):
            found.add(m.group(1))
    return found


def record() -> str:
    text = BLOCK.read_text(encoding="utf-8")
    start = text.index("- **Scripts.**")
    return text[start:text.index("\n- **", start + 1)]


def test_each_action_says_its_teach_line() -> None:
    actions = manifest.MODULE.actions                       # script_track, defined in track.py
    assert [a.name for a in actions] == list(teach.SAY)     # script_stems, defined in mix.py
    assert len(tools.ACTIONS) == 15 and len(actions) == 18  # script_lock, script_unlock, script_say;
    assert actions[-1].name == "script_render"              # script_render last
    for action in actions:
        assert action.text == teach.SAY[action.name]
        assert len(action.text) <= 200 and action.text.endswith(".")
    for name, text in FIVE.items():
        assert teach.SAY[name] == text
    assert teach.SAY["script_say"] == SAY and actions[0].name == "script_say"
    assert teach.SAY["script_start"].endswith("in the Hub's chat it writes the whole script from the chat message.")


def test_every_cited_number_is_r49s() -> None:
    known = headings()
    cited = [n for nums in teach.CITES.values() for n in nums]
    assert cited and set(cited) <= known
    in_record = NUMBER.findall(record())
    assert in_record and set(in_record) <= known, set(in_record) - known


def test_the_block_holds_the_one_rule_and_teaches_no_script_tool() -> None:
    """The Scripts paragraph is one rule; the Directing paragraph (the Hub's planner's) is not in the block,
    and no script tool but `script_say`, no field and no `Script:` word is in the block."""
    text = BLOCK.read_text(encoding="utf-8")
    block = flat(text.split("```text\n")[1].split("```")[0])
    assert flat(SCRIPTS) in block
    assert flat(DIRECTING)[:60] not in block and "Script:" not in block
    taught = set(re.findall(r"\b(?:script_\w+|context_set|scene_\w+|shot_add|line_add|cue_add|pose_add|event_\w+)\b",
                            block))
    assert taught == {"script_say"}, taught


def test_each_sentence_has_its_numbers_in_the_record() -> None:
    bullet = flat(record())
    for k in range(1, 10):
        entry = re.search(rf"S{k} (.*?)(?= S{k + 1} |$)", bullet)
        assert entry is not None, f"S{k}"
        assert NUMBER.search(entry.group(1).replace("5c.2", "")), f"S{k} has R49 numbers"
