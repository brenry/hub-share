"""Vocabulary scan: the words, references and files that must not be in this repository.

Eight kinds of offence, each matched its own way:
- gendered: a gendered pronoun or noun, matched as a whole word, any case (in a research note, which quotes
  third-party text, the pronouns only). Code, comments, tests and docs state facts
  in the code's terms (the field, the value, the function or route, the file path) and speak of "the character";
  never of a gender.
- retired: a word this project no longer uses, matched anywhere inside a word (identifiers included), any case; or a
  phrase (an entry whose words are joined by "+"), matched as whole words joined by a space, hyphen or underscore,
  with an optional possessive ('s or s), so a file path is checked as a line is and an identifier that holds one of
  the words alone stays legal. The list is RETIRED below; the Planner adds to it only on approval.
- private: the private terms (names and words). They come from two places and are never printed by this module:
  the file tests/core/private_terms.sha256, which holds a salted SHA-256 hash per term (one or two words), so the
  repository can carry the check without carrying the words (a hash of a common word can be guessed by trying words;
  it hides the terms from a reader, not from a determined search); and the environment variable HUB_PRIVATE_TERMS
  (comma- or newline-separated), matched as a whole word or as a segment of an identifier, any case. A term is added
  with `python tools/vocabulary.py --add-private "<term>"`, which writes only its hash.
- machine: anything that identifies the server, the desk or a session: a private network address, a host written as
  its last octet, a `.lan` host, a network interface name, an email address, a session ID, a GPU model (allowed only
  in the research notes, which report third-party hardware). An OS or machine name is a private term (above).
- path: an absolute path from the server's, the desk's or a session's disks (/var/mnt, /mnt, /var/home, /home/<name>,
  /root, /tmp/claude). The docs say "the install prefix", "the model folders", or a placeholder path under /srv or
  $HOME.
- narration: a sentence that reports what was said, asked, written or decided in a message, or dates those words.
  A document states what the Hub does; it is not a diary. The patterns are NARRATION below.
- record: a pointer into the project's history instead of a fact: a change entry (`C.<n>`) anywhere; in code and
  tests (CODE_PREFIXES) a spec number or a commit other than the engine's pin; in a document, a spec number with no
  file in docs/specs/, a `docs/` or `.claude/` path that does not exist, or a removed record file (REMOVED_DOCS);
  a numbered design document that no longer exists (`12-NAME §3`); in code and tests also a step of the plan
  (`PLAN Step 7b`) or a spec's decision number (`D4`). The engine's facts files are checked for this kind too.
- file: a document outside DOCS (the only documents this repository holds), a spec file not named NNN-<name>.md,
  a working file over its line limit (LIMITS), or a picture name other than example.png in a workflow JSON under
  docs/ (a LoadImage node's widget values).

A retired phrase or a narration pattern can break across a line: each file is also read with its line breaks folded
to spaces (a continued line's leading whitespace and comment marker, `#`, `//`, `*` or `>`, dropped), and a hit that
spans a line break is reported at its first line. A pronoun or a single word cannot break, so words are read per line.

`python tools/vocabulary.py` (or `--all`) prints every offence and fails when there is one; `--counts` prints the
totals per kind.

Scanned: every file git tracks (with HUB_SCAN_REF set, every file of that commit, read from git), except binary
files, third-party books under docs/library/, the engine's own texts as captured (tests/fixtures/contract/upstream-*,
tests/fixtures/upstream-*), and this scanner's own three files. Run from anywhere inside the repository, or give
--root.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

PRONOUNS = ("he", "him", "his", "himself", "she", "her", "hers", "herself")
GENDERED_NOUNS = (
    "man", "men", "woman", "women", "girl", "girls", "boy", "boys", "male", "males", "female", "females", "lady",
    "ladies", "gentleman", "gentlemen", "guy", "guys", "mother", "mothers", "father", "fathers", "son", "sons",
    "daughter", "daughters", "husband", "husbands", "wife", "wives", "brother", "brothers", "sister", "sisters",
    "actress", "actresses", "madam", "sir", "boyfriend", "girlfriend", "mom", "dad", "aunt", "uncle",
    "niece", "nephew", "grandma", "grandpa",
)
RETIRED: dict[str, str] = {
    # word: why it is retired. Its replacement is decided in the terminology map, not here.
    "bible": "the cards above the Storyboard timeline; their name in the UI is decided in the map",
    # A phrase: the article and a role noun. A sentence names the field, value, function, route or path instead.
    "the+owner": "a sentence states the fact in the code's terms",
    "the+user": "a sentence states the fact in the code's terms",
}
# The role phrase is written `the[ ]owner` here, so the pattern's own text holds no retired phrase.
NARRATION = (
    r"\bthe[ ]owner(?:'s)?,? (?:said|says|told|reported|answered|replied|confirmed|decided|agreed|complained)\b",
    r"\bthe[ ]owner,? 20\d\d-\d\d-\d\d",
    r"\bowner'?s own words\b",
    r"\bthe[ ]owner: \"",
    r"\bquote(?:d|s)? (?:from |of )?the[ ]owner\b",
    # A narration verb with a date in the same clause (a clause ends at . ; ! ? before a space or the line end).
    r"\bthe[ ]owner (?:asked|wanted|named|ordered)\b(?:[^.;!?\n]|[.;!?](?=\S))*?"
    r"(?:\b20\d\d-\d\d-\d\d\b|\bon (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{1,2}\b)",
    r"\bat the[ ]owner's (?:order|word) ?\((?:on )?20\d\d-\d\d-\d\d\b[^)]*\)",
)
KINDS = ("gendered", "retired", "private", "machine", "path", "narration", "record", "file")
# The only documents: these files, and anything under these folders.
DOCS = (
    "CLAUDE.md", "PLAN.md", "HANDOFF.md", "README.md", "README-INSTALL.md", "docs/BACKLOG.md", "docs/GLOSSARY.md",
    "docs/SESSIONS.md", "docs/SHARE.md",
)
DOCS_FOLDERS = ("docs/architecture/", "docs/video-plan/", "docs/library/", "docs/specs/", ".claude/")
DOC_SUFFIXES = {".md", ".txt", ".rst", ".log", ".org", ".adoc", ".doc", ".docx", ".odt", ".rtf", ".csv"}
LIMITS = {"HANDOFF.md": 80, "PLAN.md": 150, "docs/BACKLOG.md": 100}  # lines: state and order, never history
REMOVED_DOCS = ("PLANNER", "ARCHITECT", "AUTOPILOT", "OWNER-SETUP", "20-BUILD-SPEC", "Hub-Systems-and-Changes")
CODE_PREFIXES = ("hub/", "web/src/", "web/tests/", "tests/", "tools/", "install/", "deploy/")
ENGINE_PIN_FILE = "install/install-engine.sh"
RESEARCH = "docs/video-plan/research/"
PRIVATE_HASHES = Path("tests/core/private_terms.sha256")
HASH_SALT = "hub-vocabulary-v1:"
TEST_NETS = ("192.168.0.", "10.0.0.")  # addresses a test may use as a value; any other private address is an offence
OWN_FILES = {"tools/vocabulary.py", "tests/core/test_vocabulary.py", str(PRIVATE_HASHES)}
# Third-party text: books under docs/library/; the engine's own texts, as captured from the server.
SKIP_PREFIXES = (
    "docs/library/", "tests/fixtures/contract/upstream-", "tests/fixtures/upstream-",
    "hub/worker/adapters/upstream.facts.json", "hub/worker/adapters/fork.facts.json",  # the engine's own names
    "web/package-lock.json", "requirements/",  # generated lock files
)
BINARY_SUFFIXES = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".zip", ".gz", ".tar", ".whl", ".mp4", ".mp3", ".wav", ".ogg", ".webm", ".pyc", ".so", ".bin", ".safetensors",
}
MAX_BYTES = 2_000_000

_PRONOUN_RE = re.compile(r"\b(?:" + "|".join(PRONOUNS + GENDERED_NOUNS) + r")\b", re.IGNORECASE)
_PRONOUN_ONLY_RE = re.compile(r"\b(?:" + "|".join(PRONOUNS) + r")\b", re.IGNORECASE)
def _retired_alt(entry: str) -> str:
    """A word matches inside any word; a phrase ("a+b") matches as whole words joined by space, hyphen or underscore,
    with an optional possessive."""
    if "+" not in entry:
        return re.escape(entry)
    return r"\b" + r"[ _-]+".join(re.escape(w) for w in entry.split("+")) + r"(?:'s|s)?\b"


_RETIRED_RE = re.compile("|".join(_retired_alt(w) for w in RETIRED), re.IGNORECASE) if RETIRED else None
_PHRASES = [w for w in RETIRED if "+" in w]
_PHRASE_RE = re.compile("|".join(_retired_alt(w) for w in _PHRASES), re.IGNORECASE) if _PHRASES else None
_CONTINUED_RE = re.compile(r"^\s*(?:#+|//+|\*+|>+)?\s*")  # a continued line's indent and comment marker
_MACHINE_RE = re.compile(
    r"\b(?:192\.168|10|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}(?:\.\d{1,3})?\b"  # a private IPv4 address
    r"|(?<![\w.])\.\d{3}\b",  # a host written as its last octet
    re.IGNORECASE,
)
_PATH_RE = re.compile(
    r"(?<![\w.])/(?:var/mnt|mnt|var/home|home)/(?!linuxbrew\b)[A-Za-z0-9_]+|(?<![\w.])/root/|(?<![\w.])/tmp/claude"
)
_HOST_RE = re.compile(
    r"\b[A-Za-z0-9-]+\.(?:lan|localdomain|home\.arpa)\b"           # a host on the local network
    r"|\b(?:enp|eno|ens|enx|wlp|wlan)\d\w*"                          # a network interface
    r"|[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"  # an email address
    r"|\bsession_0[0-9A-Za-z]{5,}|\bcse_[0-9A-Za-z]{6,}"               # a session ID
)
_GPU_RE = re.compile(r"\b(?:RTX|GTX|Quadro|Radeon|Titan)\s?[A-Z]?\d{3,4}\b|\bthe [2-5]0[5-9]0(?: Ti)?\b", re.IGNORECASE)
_CHANGE_RE = re.compile(r"(?<![\w.])C\.\d{1,3}\b")
_SPEC_RE = re.compile(r"(?<![A-Za-z])(?:specs?[ _-]?|docs/specs/)(\d{3})(?!\d)", re.IGNORECASE)
_COMMIT_RE = re.compile(r"`([0-9a-f]{7,40})`|\bcommits? ([0-9a-f]{7,40})\b")
# A path into the Hub's own document folders (a bare docs/<name>.md may be a third-party file, cited in research).
_DOCREF_RE = re.compile(
    r"(?<![\w/.-])((?:docs/(?:architecture|video-plan|specs|library)|\.claude)/[\w./-]*[\w-]\.md)\b"
)
_REMOVED_RE = re.compile(r"(?<![\w/-])(?:" + "|".join(re.escape(d) for d in REMOVED_DOCS) + r")\.md\b")
_OLDDOC_RE = re.compile(r"(?<![\w/])\d{2}-[A-Z]{3,}(?:-[A-Z]+)*(?=\s?§|\.md\b)")  # a numbered design doc, gone
# In code and tests only: a step of the plan (the plan's steps are deleted once built) or a spec's decision number.
_CODE_RECORD_RE = re.compile(r"\bPLAN(?:\.md)?(?:'s)?\s(?:[Ss]tep\s)?\d+[a-z]?\b|(?<![\w.#-])D\d{1,2}[a-z]?\b")
_SPEC_FILE_RE = re.compile(r"docs/specs/(?:\d{3}-[a-z0-9-]+|TEMPLATE)\.md")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
_WORD_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")  # words, with camelCase split
_NARRATION_RE = re.compile("|".join(NARRATION), re.IGNORECASE)


def private_terms(env: str | None = None) -> list[str]:
    raw = os.environ.get("HUB_PRIVATE_TERMS", "") if env is None else env
    seen: list[str] = []
    for part in re.split(r"[,\n]", raw):
        term = part.strip()
        if term and term.lower() not in (s.lower() for s in seen):
            seen.append(term)
    return seen


def _any_case(term: str) -> str:
    return "".join(f"[{c.lower()}{c.upper()}]" if c.isalpha() else re.escape(c) for c in term)


def private_pattern(terms: list[str]) -> re.Pattern[str] | None:
    """A term as a whole word, or as a segment of an identifier (`term_x`, `xTerm`, `TermX`), in any case.

    Built letter by letter rather than with IGNORECASE, so the boundary classes keep their case."""
    if not terms:
        return None
    alts = "|".join(_any_case(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(r"(?:(?<![A-Za-z0-9])|(?<=[a-z0-9])(?=[A-Z]))(?:" + alts + r")(?![a-z0-9])")


def normalize(term: str) -> str:
    return " ".join(_WORD_RE.findall(term)).lower()


def term_hash(term: str) -> str:
    return hashlib.sha256((HASH_SALT + normalize(term)).encode()).hexdigest()


def hashed_terms(root: Path) -> set[str]:
    path = root / PRIVATE_HASHES
    if not path.exists():
        return set()
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")}


def add_private(root: Path, term: str) -> bool:
    """Append the term's hash to the file (never the term). False when it was already there."""
    h = term_hash(term)
    have = hashed_terms(root)
    if h in have:
        return False
    path = root / PRIVATE_HASHES
    head = "" if path.exists() else (
        "# Salted SHA-256 hashes of the private terms, one per line; the terms themselves are never written.\n"
        "# Add one: python tools/vocabulary.py --add-private \"<term>\"   (one or two words; case does not matter)\n"
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(head + h + "\n")
    return True


def hashed_hit(line: str, hashes: set[str]) -> bool:
    """True when any word, or any two adjacent words, of the line hashes to a private term."""
    if not hashes:
        return False
    words = [w.lower() for w in _WORD_RE.findall(line)]
    for i, w in enumerate(words):
        if hashlib.sha256((HASH_SALT + w).encode()).hexdigest() in hashes:
            return True
        if i + 1 < len(words) and hashlib.sha256((HASH_SALT + w + " " + words[i + 1]).encode()).hexdigest() in hashes:
            return True
    return False


@dataclass
class Offence:
    path: str
    line: int
    kind: str
    word: str  # "" for a private term: never printed

    def __str__(self) -> str:
        shown = "" if self.kind == "private" else f" {self.word!r}"
        return f"{self.path}:{self.line}: {self.kind}{shown}"


@dataclass(repr=False)
class Report:
    root: Path
    private_checked: bool
    offences: list[Offence] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def kinds_by_file(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for o in self.offences:
            out.setdefault(o.path, set()).add(o.kind)
        return out

    def counts(self) -> dict[str, int]:
        c = dict.fromkeys(KINDS, 0)
        for o in self.offences:
            c[o.kind] += 1
        return c


def repo_root(start: Path | None = None) -> Path:
    here = start or Path.cwd()
    out = subprocess.run(["git", "-C", str(here), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"not inside a git repository: {here}")
    return Path(out.stdout.strip())


def scan_ref() -> str:
    """The commit to scan instead of the working tree (HUB_SCAN_REF, set by the push gate to HEAD: what is pushed)."""
    return os.environ.get("HUB_SCAN_REF", "").strip()


def tracked_files(root: Path) -> list[str]:
    ref = scan_ref()
    argv = ["ls-tree", "-r", "-z", "--name-only", ref] if ref else ["ls-files", "-z"]
    out = subprocess.run(["git", "-C", str(root), *argv], capture_output=True, text=True, check=True)
    return [p for p in out.stdout.split("\0") if p]


def read_tracked(root: Path, rel: str) -> str | None:
    """A tracked file's text (from HUB_SCAN_REF when set); None when it is too big, missing or not UTF-8."""
    ref = scan_ref()
    if ref:
        out = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{rel}"], capture_output=True)
        data = out.stdout if out.returncode == 0 else None
    else:
        full = root / rel
        data = full.read_bytes() if full.is_file() else None
    if data is None or len(data) > MAX_BYTES:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scannable(path: str) -> bool:
    if path in OWN_FILES or path.startswith(SKIP_PREFIXES):
        return False
    return Path(path).suffix.lower() not in BINARY_SUFFIXES


@dataclass
class Known:
    """What exists: the files a reference may point at, the open spec numbers, the engine's pinned commit."""

    files: set[str] = field(default_factory=set)
    specs: set[str] = field(default_factory=set)
    pins: tuple[str, ...] = ()


def known_of(root: Path, tracked: list[str]) -> Known:
    files = set(tracked) | set(DOCS)
    specs = {m.group(1) for f in tracked if (m := re.match(r"docs/specs/(\d{3})-", f))}
    pin_file = root / ENGINE_PIN_FILE
    text = pin_file.read_text(encoding="utf-8") if pin_file.is_file() else ""
    pins = tuple(sorted(set(re.findall(r"\b[0-9a-f]{7,40}\b", text))))
    return Known(files, specs, pins)


def _record_hits(path: str, n: int, line: str, known: Known | None) -> list[Offence]:
    out = [Offence(path, n, "record", m.group(0)) for m in _CHANGE_RE.finditer(line)]
    out += [Offence(path, n, "record", m.group(0)) for m in _REMOVED_RE.finditer(line)]
    out += [Offence(path, n, "record", m.group(0)) for m in _OLDDOC_RE.finditer(line)]
    in_code = path.startswith(CODE_PREFIXES)
    if in_code:
        out += [Offence(path, n, "record", m.group(0)) for m in _CODE_RECORD_RE.finditer(line)]
    for m in _SPEC_RE.finditer(line):
        if in_code or (known is not None and m.group(1) not in known.specs):
            out.append(Offence(path, n, "record", m.group(0)))
    if in_code:
        pins = known.pins if known is not None else ()
        for m in _COMMIT_RE.finditer(line):
            sha = m.group(1) or m.group(2)
            if not any(p.startswith(sha) or sha.startswith(p) for p in pins):
                out.append(Offence(path, n, "record", sha))
    elif known is not None:
        for m in _DOCREF_RE.finditer(line):
            ref = m.group(1)
            if ref not in known.files and not any(f.startswith(ref.rsplit(".", 1)[0]) for f in known.files):
                out.append(Offence(path, n, "record", ref))
    return out


def scan_text(
    path: str, text: str, private_re: re.Pattern[str] | None, hashes: set[str] | None = None,
    known: Known | None = None,
) -> list[Offence]:
    found: list[Offence] = []
    hashes = hashes or set()
    research = path.startswith(RESEARCH)
    for n, line in enumerate(text.splitlines(), 1):
        # A research note quotes third-party text (books, upstream examples): there only the pronouns are checked.
        for m in (_PRONOUN_ONLY_RE if research else _PRONOUN_RE).finditer(line):
            found.append(Offence(path, n, "gendered", m.group(0)))
        if _RETIRED_RE is not None:
            for m in _RETIRED_RE.finditer(line):
                found.append(Offence(path, n, "retired", m.group(0)))
        if (private_re is not None and private_re.search(line)) or hashed_hit(line, hashes):
            found.append(Offence(path, n, "private", ""))
        for m in _MACHINE_RE.finditer(line):
            # A test may use an address from TEST_NETS as a value; any other private address is an offence there too.
            in_tests = path.startswith(("tests/", "web/tests/"))
            if in_tests and m.group(0)[0].isdigit() and m.group(0).startswith(TEST_NETS):
                continue
            found.append(Offence(path, n, "machine", m.group(0)))
        for m in _HOST_RE.finditer(line):
            found.append(Offence(path, n, "machine", m.group(0)))
        if not research:
            for m in _GPU_RE.finditer(line):
                found.append(Offence(path, n, "machine", m.group(0)))
        for m in _PATH_RE.finditer(line):
            found.append(Offence(path, n, "path", m.group(0)))
        for m in _NARRATION_RE.finditer(line):
            found.append(Offence(path, n, "narration", m.group(0)))
        found.extend(_record_hits(path, n, line, known))
    found.extend(folded_hits(path, text))
    return found


def _workflow_pictures(text: str) -> list[str]:
    """The picture names a workflow JSON's LoadImage nodes hold (top level and subgraphs), other than example.png."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    nodes = list(data.get("nodes") or [])
    for graph in (data.get("definitions") or {}).get("subgraphs") or []:
        nodes += graph.get("nodes") or []
    names: list[str] = []
    for node in nodes:
        if not isinstance(node, dict) or "LoadImage" not in str(node.get("type", "")):
            continue
        values = node.get("widgets_values")
        values = list(values.values()) if isinstance(values, dict) else values or []
        values += list((node.get("widgets_values_named") or {}).values())
        names += [v for v in values if isinstance(v, str) and v.lower().endswith(IMAGE_SUFFIXES) and v != "example.png"]
    return names


def file_hits(rel: str, text: str | None) -> list[Offence]:
    """The file kind: where a document may live, how a spec is named, how long a working file may grow, and the
    picture names a workflow under docs/ may hold."""
    out: list[Offence] = []
    if Path(rel).suffix.lower() in DOC_SUFFIXES and rel not in DOCS and not rel.startswith(DOCS_FOLDERS):
        out.append(Offence(rel, 0, "file", "a document outside the list (.claude/rules/docs.md)"))
    if rel.startswith("docs/specs/") and not _SPEC_FILE_RE.fullmatch(rel):
        out.append(Offence(rel, 0, "file", "a spec is docs/specs/NNN-<name>.md"))
    if text is None:
        return out
    limit = LIMITS.get(rel)
    if limit is not None and len(text.splitlines()) > limit:
        out.append(Offence(rel, limit + 1, "file", f"over {limit} lines"))
    if rel.startswith("docs/") and rel.endswith(".json") and _workflow_pictures(text):
        out.append(Offence(rel, 1, "file", "a picture name other than example.png"))
    return out


def folded_hits(path: str, text: str) -> list[Offence]:
    """The retired phrases and the narration patterns on the text with its line breaks folded to spaces (each line's
    indent and comment marker dropped): a hit that spans a line break, reported at its first line."""
    parts: list[str] = []
    starts: list[int] = []  # the folded offset where each line begins
    at = 0
    for line in text.splitlines():
        part = _CONTINUED_RE.sub("", line, count=1)
        starts.append(at)
        parts.append(part)
        at += len(part) + 1
    folded = " ".join(parts)

    def line_of(offset: int) -> int:
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    found: list[Offence] = []
    for kind, pattern in (("retired", _PHRASE_RE), ("narration", _NARRATION_RE)):
        if pattern is None:
            continue
        for m in pattern.finditer(folded):
            first, last = line_of(m.start()), line_of(m.end() - 1)
            if first != last:
                found.append(Offence(path, first, kind, m.group(0)))
    return found


def scan(root: Path | None = None, terms: list[str] | None = None) -> Report:
    root = root or repo_root()
    terms = private_terms() if terms is None else terms
    private_re = private_pattern(terms)
    hashes = hashed_terms(root)
    report = Report(root=root, private_checked=private_re is not None or bool(hashes))
    tracked = tracked_files(root)
    known = known_of(root, tracked)
    for rel in tracked:
        if rel in OWN_FILES:
            continue
        if rel.startswith(SKIP_PREFIXES):
            report.offences.extend(file_hits(rel, None))
            if rel.endswith(".facts.json"):  # the engine's names are allowed there; a pointer into history is not
                facts = read_tracked(root, rel) or ""
                for n, line in enumerate(facts.splitlines(), 1):
                    report.offences.extend(_record_hits(rel, n, line, known))
            continue
        # The file's name counts too (line 0): a retired word or a private term in a path is an offence.
        if _RETIRED_RE is not None:
            for m in _RETIRED_RE.finditer(rel):
                report.offences.append(Offence(rel, 0, "retired", m.group(0)))
        if (private_re is not None and private_re.search(rel)) or hashed_hit(rel, hashes):
            report.offences.append(Offence(rel, 0, "private", ""))
        if not scannable(rel):
            report.offences.extend(file_hits(rel, None))
            continue
        text = read_tracked(root, rel)
        if text is None:
            report.skipped.append(rel)
            report.offences.extend(file_hits(rel, None))
            continue
        report.offences.extend(file_hits(rel, text))
        report.offences.extend(scan_text(rel, text, private_re, hashes, known))
    return report


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--root=")]
    root_arg = next((a.split("=", 1)[1] for a in argv if a.startswith("--root=")), None)
    root = Path(root_arg).resolve() if root_arg else repo_root()
    if "--add-private" in args:
        i = args.index("--add-private")
        if i + 1 >= len(args):
            print("usage: --add-private \"<term>\"", file=sys.stderr)
            return 2
        print("added" if add_private(root, args[i + 1]) else "already listed")
        return 0
    report = scan(root)
    if "--counts" in args:
        for kind, n in report.counts().items():
            note = "" if kind != "private" or report.private_checked else " (HUB_PRIVATE_TERMS not set)"
            print(f"{kind}: {n}{note}")
        print(f"files with an offence: {len(report.kinds_by_file())}; files skipped: {len(report.skipped)}")
        return 0
    for o in report.offences:
        print(o)
    if not report.private_checked:
        print("note: HUB_PRIVATE_TERMS not set; private terms were not checked", file=sys.stderr)
    return 1 if report.offences else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
