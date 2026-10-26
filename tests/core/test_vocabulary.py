"""The repository's vocabulary (tools/vocabulary.py): no gendered pronoun or noun, no retired word or phrase, none
of the private terms (hashed in tests/core/private_terms.sha256, plus HUB_PRIVATE_TERMS when set), no machine detail
or private path, no narration, no pointer into history, and no document outside the list, anywhere git tracks; a
retired phrase or a narration broken across a line is found too.
"""

from __future__ import annotations

import os

import pytest

from tools import vocabulary as voc

ROOT = voc.repo_root()
# The article and a role noun, joined here so this file holds no retired phrase of its own.
ROLE = "the" + " owner"


@pytest.fixture(scope="module")
def report() -> voc.Report:
    return voc.scan(ROOT)


def test_private_terms_are_checked() -> None:
    assert voc.hashed_terms(ROOT), f"{voc.PRIVATE_HASHES} is missing or empty: the private terms are not checked"


def test_no_offence_anywhere(report: voc.Report) -> None:
    shown = "\n".join(str(o) for o in report.offences[:40])
    more = f"\n... and {len(report.offences) - 40} more" if len(report.offences) > 40 else ""
    assert not report.offences, (
        f"{len(report.offences)} offence(s). Reword them (the field, the value, the function or "
        f"route, the file path; the term the glossary gives).\n{shown}{more}"
    )


def test_a_phrase_broken_across_a_line_is_found() -> None:
    """The retired phrases and the narration patterns are read with line breaks folded to spaces, a
    continued line's indent and comment marker dropped; the hit is reported at its first line."""
    article, noun = ROLE.split(" ")
    for marker in ("", "# ", "    # ", "// ", " * ", "> "):
        text = f"plain line\nthe text of {article}\n{marker}{noun} picks the model\n"
        found = voc.scan_text("docs/a.md", text, None)
        assert [(o.line, o.kind) for o in found] == [(2, "retired")], repr(marker)
    dated = f"x {ROLE} asked for\n# it in PLAN.md, 2026-10-20\n"
    assert [(o.line, o.kind) for o in voc.scan_text("tools/a.py", dated, None)] == [(1, "retired"), (1, "narration")]
    # One hit on one line is counted once; words that only meet across a paragraph are still a phrase.
    assert [(o.line, o.kind) for o in voc.scan_text("docs/b.md", f"{ROLE} picks\n", None)] == [(1, "retired")]
    assert not voc.scan_text("docs/c.md", f"bathe\n{noun} picks\n", None)


def test_the_engine_capture_is_third_party_text() -> None:
    """The engine's capture and the golden written from it hold upstream's own words, not the Hub's;
    the script that writes the Hub's own sentence into the golden stays scanned."""
    assert not voc.scannable("tests/fixtures/contract/upstream-18.05/engine.json")
    assert not voc.scannable("tests/fixtures/upstream-18.05/h3.json")
    assert voc.scannable("tests/engine/capture_engine.py")


def test_scanner_matches_its_first_kinds() -> None:
    text = "request.text is typed\nhe types it\nthe scene_bible card\nplain line\n"
    found = voc.scan_text("a.txt", text, voc.private_pattern(["termx", "ab"]))
    kinds = [(o.line, o.kind) for o in found]
    assert kinds == [(2, "gendered"), (3, "retired")]
    # A private term as a word or an identifier segment, never inside another word; never printed.
    hits = voc.scan_text("b.txt", "TermX_one\nabsolutely\nfoo ab\nxTermx\n", voc.private_pattern(["termx", "ab"]))
    assert [o.line for o in hits] == [1, 3, 4]
    assert all("termx" not in str(o).lower() and o.word == "" for o in hits)
    # Pronouns are whole words only: no hit inside another word, in any case.
    assert not voc.scan_text("c.txt", "HEIGHT the shim other\n", None)


def test_private_terms_parse() -> None:
    assert voc.private_terms("One, two\nTWO,, ") == ["One", "two"]
    assert voc.private_terms("") == []
    assert voc.private_pattern([]) is None
    assert "HUB_PRIVATE_TERMS" in os.environ or voc.private_terms() == []


def test_hashed_terms_match_words_and_pairs_without_holding_the_words(tmp_path) -> None:
    root = tmp_path
    (root / voc.PRIVATE_HASHES).parent.mkdir(parents=True)
    assert voc.add_private(root, "Termx") and not voc.add_private(root, "TERMX")
    assert voc.add_private(root, "two Words")
    # The header's own prose (written by add_private) is the scanner's text; the hash lines must hold no term.
    lines = [ln.lower() for ln in (root / voc.PRIVATE_HASHES).read_text().splitlines() if not ln.startswith("#")]
    assert lines and not any("termx" in ln or "words" in ln for ln in lines)
    hashes = voc.hashed_terms(root)
    assert voc.hashed_hit("a termx here", hashes)
    assert voc.hashed_hit("TermxLine = 1", hashes)
    assert voc.hashed_hit("Two-Words", hashes) and voc.hashed_hit("two_words()", hashes)
    assert not voc.hashed_hit("termxy and words two", hashes)
    found = voc.scan_text("a.txt", "plain\nthe termx\n", None, hashes)
    assert [(o.line, o.kind, o.word) for o in found] == [(2, "private", "")]


def test_machine_path_and_narration_kinds() -> None:
    address = ".".join(("192", "168", "1", "5"))       # built from parts: no literal machine value in this file
    octet = "." + "2" * 3
    path = "/" + "/".join(("var", "mnt", "disk1", "x"))
    text = f"on {address} and the {octet} box\nunder {path}\n{ROLE} said so\n"
    hits = voc.scan_text("docs/a.md", text, None)
    assert [(o.line, o.kind) for o in hits] == [
        (1, "machine"), (1, "machine"), (2, "path"), (3, "retired"), (3, "narration")]
    # A test may use an address from TEST_NETS as a value; a docs file may not; a Homebrew path is no offence.
    assert not voc.scan_text("tests/x.py", f"('{voc.TEST_NETS[0]}10', 1)\n", None)
    assert voc.scan_text("docs/x.md", f"{voc.TEST_NETS[0]}10\n", None)
    brew = "linux" + "brew"
    assert not voc.scan_text("a.sh", f"PATH=/home/{brew}/.{brew}/bin\n", None)
    # A narration verb with a date in the same clause, and an order or word with a bracketed date.
    # Each line also holds the retired phrase; the narration hit is counted on its own.
    dated = (
        f"{ROLE} asked for it in PLAN.md, 2026-10-20\n{ROLE} wanted it on October 3\n"
        f"at {ROLE}'s order (2026-10-20)\n"
    )
    narration = [o for o in voc.scan_text("docs/d.md", dated, None) if o.kind == "narration"]
    assert [o.line for o in narration] == [1, 2, 3]
    clean = f"{ROLE} names a picture. Decided 2026-10-20\nat {ROLE}'s word, the files go\n"
    assert not [o for o in voc.scan_text("docs/e.md", clean, None) if o.kind == "narration"]


def test_role_phrases_are_retired_as_phrases_in_lines_and_paths() -> None:
    """The article and a role noun, joined by a space, hyphen or underscore, with an optional
    possessive; never the noun alone, an identifier that holds it, or a chat role."""
    user = "the" + " user"
    hits = [
        f"{ROLE} picks the model",
        f"{user.title()}'s pick is sent",
        "docs/specs/001-" + "the" + "-owners-words.md",
        "Spec 1: " + "the" + "_user said",
        "THE" + "-USER" + " box",
    ]
    for line in hits:
        found = voc.scan_text("docs/a.md", line + "\n", None)
        assert [(o.line, o.kind) for o in found] == [(1, "retired")], line
    misses = [
        "owner: Character 1",
        "the prop's owner field",
        "headers['user_agent']",
        '{"role": "user", "content": "x"}',
        "test_no_tool_writes_" + "the" + "_owners_prompt_box",
        "other users and owners",
        "bathe user",
    ]
    for line in misses:
        assert not voc.scan_text("docs/a.md", line + "\n", None), line
    # A file name is checked as a line is (scan() reads the path as line 0 through the same pattern).
    assert voc._RETIRED_RE is not None and voc._RETIRED_RE.search("docs/specs/" + "the" + "-users-text.md")


def test_gendered_nouns_and_the_research_exception() -> None:
    noun = "wo" + "man"
    assert [o.kind for o in voc.scan_text("tests/a.py", f"the {noun} 1\n", None)] == ["gendered"]
    assert not voc.scan_text("docs/video-plan/research/R1.md", f"a book's {noun}\n", None)
    assert voc.scan_text("docs/video-plan/research/R1.md", "s" + "he says\n", None)
    assert not voc.scan_text("hub/a.py", "Mr. Speaker 1 came. human, manifest, mansion\n", None)


def test_machine_kind_covers_hosts_interfaces_mail_sessions_and_gpus() -> None:
    lines = ["box." + "lan", "en" + "p5s0", "a" + "@" + "b.com", "session" + "_01AbCdEf", "cse" + "_0123456",
             "RT" + "X 4090", "the 30" + "80"]
    for line in lines:
        assert [o.kind for o in voc.scan_text("docs/a.md", line + "\n", None)] == ["machine"], line
    assert not voc.scan_text("docs/video-plan/research/R1.md", "RT" + "X 4090 report\n", None)
    assert not voc.scan_text("hub/a.py", "hub@invalid record.home(ctx) eth0\n", None)
    paths = voc.scan_text("docs/a.md", "/ro" + "ot/x and /tmp/cl" + "aude-0\n", None)
    assert [o.kind for o in paths] == ["path", "path"]


def test_record_kind() -> None:
    spec, change = "sp" + "ec 081", "C" + ".48"
    known = voc.Known(files={"docs/architecture/00-overview.md"}, specs={"200"}, pins=("af2ed29",))
    # In code and tests: any spec number, any change entry, a commit other than the engine's pin.
    lines = (f"# {spec}", f"x = 1  # ({change})", "# PLAN St" + "ep 7b", "# its D" + "4 rule",
             "# 12-CONT" + "ROLLER §3", "# as of commit 518" + "aabb", "def test_sp" + "ec_028_x():")
    for line in lines:
        assert [o.kind for o in voc.scan_text("hub/a.py", line + "\n", None, None, known)] == ["record"], line
    fine = "# upstream `af2ed29` wgp.py:12, #D1E, 3D, R48 §7, PLAN.md\n"
    assert not voc.scan_text("hub/a.py", fine, None, None, known)
    # In a document: a spec with no file, a missing path into the Hub's own folders, a removed record file.
    assert voc.scan_text("docs/a.md", f"see {spec}\n", None, None, known)
    assert not voc.scan_text("docs/a.md", "see sp" + "ec 200\n", None, None, known)
    assert voc.scan_text("docs/a.md", "docs/architecture/99-gone.md\n", None, None, known)
    assert not voc.scan_text("docs/a.md", "docs/architecture/00-overview.md and HP/README.md\n", None, None, known)
    assert voc.scan_text("docs/a.md", "PLAN" + "NER.md\n", None, None, known)


def test_file_kind() -> None:
    assert voc.file_hits("docs/notes.md", "x\n")
    assert voc.file_hits("hub/chat.log", None)
    assert voc.file_hits("docs/specs/a-b.md", "x\n")
    assert not voc.file_hits("docs/specs/200-a-thing.md", "x\n")
    assert not voc.file_hits("docs/architecture/new.md", "x\n")
    assert voc.file_hits("HANDOFF.md", "x\n" * 81) and not voc.file_hits("HANDOFF.md", "x\n" * 80)
    flow = '{"nodes": [{"type": "LoadImage", "widgets_values": ["Picture 9.png", "image"]}]}'
    assert voc.file_hits("docs/video-plan/research/w.json", flow)
    assert not voc.file_hits("docs/video-plan/research/w.json", flow.replace("Picture 9.png", "example.png"))
