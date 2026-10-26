# R50 — The Director's rulebook, every rule with its source, 2026-10-20

Research note for the rulebook (blueprint §11.2: `hub/modules/director/rulebook.json`, one record per rule).
Read-only research: no Hub code, spec or plan was changed. Facts only: each record states what a source says and
the tier, parameters, fix line and test the blueprint's record format asks for. Where a record goes beyond its
source, it says so and is `advise`.

**What was read.** Blueprint §11-§12, §14, §16-§18; R49 (all); `docs/library/
README.md`; the Hub's judges' bars, take measure, cue levels and mix (cited by file); `docs/video-plan/system-prompt-video-paragraph.md` (the Open
WebUI block); the six library books, already extracted as text.

**How sources are cited.**
- Books by their printed page. The page offsets were checked against each page's own header. Grindstaff (2002): PDF =
  printed + 12. Katz (1991): + 13. Zettl (1976): + 13 up to p. 439, + 11 from p. 442. Holman (2010): + 15.
- Murch (*In the Blink of an Eye*, 2nd ed.) and McKee (*Dialogue*, 2016) are ebooks with no printed page numbers in
  the extract, so they are cited by chapter. Murch's chapters: "The Rule of Six", "Most with the Least", "Why Do Cuts
  Work?", "Dragnet", "Don't Worry, It's Only a Movie". McKee's: ch. 1 "The Full Definition of Dialogue"; ch. 2 "The
  Three Functions of Dialogue"; Part Two intro "Six Dialogue Tasks"; ch. 6 "Credibility Flaws"; ch. 7 "Language
  Flaws"; ch. 8 "Content Flaws"; ch. 9 "Design Flaws"; ch. 10 "Character-Specific Dialogue"; ch. 12
  "Story/Scene/Dialogue".
- Sources the library does not hold are cited through R49, giving the original R49 quotes: Stasheff & Bretz,
  *The Television Program*, 5th ed., 1976 ("S&B"), which R49 read through a summarising fetch, so its page numbers
  may be off by one; Dmytryk; Bordwell; Arnold & Tilton; Heimbuch.
- EBU R 128 is cited only as quoted in `hub/modules/director/takejudge.py`.
- Repo facts are cited by blueprint section or file.

**The record format** (blueprint §11.2): `id`, `name`, `statement`, `source`, `scope`
(context|scene|shot|line|exchange|mix|render), `tier` (check|grade|advise, with a reason), `params`, `fix`, `test`.
- **Params.** Each param is `name = value unit — source`. A value no source gives is written `pending — first value
  from <source>`, or `pending — no source` when nothing gives one. Every param also holds `measured: null` until the
  measurement tool fills it (§11.6).
- **Fix.** The fix is addressed to a model that only has the script tools: `context_set`, `scene_add`, `scene_change`,
  `shot_add`, `line_add`, `cue_add`, `pose_add`, `event_change`, `event_move`, `event_remove`, and the mix tools
  `take_change`, `lane_change`, `clip_move` (§12.6). It names events with `{speaker, nth}`, `{cue, nth}` and
  `{shot: n}`, as the block's line 64 teaches.
- **Test.** The test is the fixture case the rule refuses. The case passes once the rule is removed, which is what the
  blueprint's contract test asserts.

**Tier convention used here** (blueprint §11.2, §11.4, §11.6):
- `check`: code decides from the script or from measurements.
- `grade`: a rubric item for the Hub's own model ask.
- `advise`: a hint, never a refusal. A rule is `advise` when its logic is sourced but its number is not. Such a record
  says "→ check when measured" and becomes `check` when §11.6 supplies the number.

---

## 1. WRITER — the exchange, the line, the beat (McKee, Grindstaff, Zettl)

The Open WebUI model writes; the Hub grades (§11.4: one ask per scene, schema held as for the context, three asks at most).
WR-1 to WR-5 keep the ids blueprint §11.4 and §16.5 already gave them.

#### WR-1 — Each line acts on the other
- **statement:** Every line is an action its speaker takes on someone in the scene (asks, pushes, refuses, reveals). A
  line that does nothing to anyone fails.
- **source:** McKee, "Six Dialogue Tasks", task 1: "Each verbal expression takes an inner action." Ch. 1: "To say
  something is to do something". Ch. 2: name the action under a line "with an active gerund ('-ing') phrase".
- **scope:** line
- **tier:** grade. Whether a line acts needs a reading. McKee's own test (name the gerund) is the rubric.
- **params:** none
- **fix:** "{speaker: <A>, nth: n} does nothing to <B>: event_change its words so <A> asks, pushes, refuses or reveals
  something to <B>."
- **test:** The Character 1 question-and-answer exchange fixture with a Character 1 line "Line 1." between two exchanges.

#### WR-2 — The scene turns
- **statement:** A scene turns at least one value at stake, by an action or a revelation. A scene with no turning point
  fails.
- **source:** McKee ch. 12: "A turning point can be created in only one of two ways: by action or revelation". "If a
  scene has no turning point … the scene is merely an exposition-filled nonevent." Also R49 §5.1 (McKee, *Story*: "No
  scene that doesn't turn").
- **scope:** scene
- **tier:** grade. A value and its change are a reading.
- **params:** none
- **fix:** "Scene n does not turn: event_change or line_add one line where <character> does or reveals something that
  changes what is at stake for <other>."
- **test:** A four-line question-and-answer fixture that ends where it began (Character 2 asks, Character 1 answers, twice).

#### WR-3 — Exposition carried in the lines, never told to someone who knows it
- **statement:** Facts reach the audience inside lines that do something. A character telling another what both
  already know fails.
- **source:** McKee, "Six Dialogue Tasks", task 3: "Statements and allusions within the lines convey exposition." Ch.
  6, empty talk: "one character telling another character something they both already know to satisfy the author's
  expositional exigencies". R49 §5.5 (web).
- **scope:** line
- **tier:** grade. "Both already know" depends on the scene.
- **params:** none
- **fix:** "{speaker: <A>, nth: n} tells <B> what <B> already knows: event_change it so the fact comes out while <A>
  acts on <B>, or event_remove it."
- **test:** The fixture line "As you know, Character 1, you are Character 1 and you are here today."

#### WR-4 — A voice per role
- **statement:** Each cast member speaks in a verbal style of that member's own. Two roles whose lines could be swapped unnoticed
  fail.
- **source:** McKee, "Six Dialogue Tasks", task 4: "A unique verbal style characterizes each role." Ch. 7: "find words
  so true to your character, they wouldn't quite fit in anyone else's mouth". Ch. 10 (character-specific dialogue).
  Grindstaff p. 12: a coached line said "in your own way". R49 §5.4 (web, "cover the character names").
- **scope:** exchange
- **tier:** grade. Style is judged across the scene.
- **params:** none
- **fix:** "<A> and <B> sound alike: event_change {speaker: <B>, nth: n} into <B>'s own words (<B>'s vocabulary, length
  and rhythm as the context gives <B>)."
- **test:** The Character 1 fixture with Character 1's lines rewritten in Character 2's register.

#### WR-5 — Mark the emotional peak, the provocation and the reveal
- **statement:** The grade marks each line that provokes, reveals, or carries a speaker to visible emotion. SW-4, SW-10,
  SW-11 and SW-13 cut on these marks.
- **source:**
  - Grindstaff pp. 19-20: the emotional peak (the book's "money shot") is "joy, sorrow, rage, or remorse expressed in visible, bodily terms".
  - Grindstaff p. 116: what brings it on is a volatile topic, surprise, or an opposing view.
  - Grindstaff p. 250: "All good television is built around moments of dramatic revelation."
  - Blueprint §16.5 names the rule WR-5.
- **scope:** line
- **tier:** grade. The mark is a reading of the line.
- **params:** none
- **fix:** none. WR-5 marks lines and refuses nothing.
- **test:** The Character 1 fixture's "The last word is mine!" followed by the gasp cue must carry a mark. Without the rule,
  SW-10 cuts nothing there.

#### WR-6 — No narration copied (deterministic proxy for WR-3)
- **statement:** A line that repeats a run of the story text word for word is refused before the grade is
  asked.
- **source:**
  - Blueprint §11.4: "a line whose words are a substring of the story (narration copied, the run on the server)".
  - The block, `system-prompt-video-paragraph.md:78`: "never my narration copied".
  - McKee task 3, as in WR-3.
- **scope:** line
- **tier:** check. A string match.
- **params:** `copy_words` (shortest repeated run that counts) = pending — no source.
- **fix:** "{speaker: <A>, nth: n} repeats the story's words: event_change it into what <A> would say to <B>."
- **test:** A fixture line equal to the story's sentence "Character 2 asks Character 1 about Topic 1."

#### WR-7 — Beats build; one pattern repeated is one beat
- **statement:** Each beat of action and reaction tops the one before. The same action met the same way again adds no
  beat and fails.
- **source:**
  - McKee, "Six Dialogue Tasks", task 2: "Each beat of action/reaction intensifies the scene, building to and around
    its turning point."
  - Ch. 12: "No matter how many times a pattern of action/reaction repeats, it constitutes one, and only one, beat."
  - Ch. 9: repetitious beats.
- **scope:** exchange
- **tier:** grade
- **params:** none
- **fix:** "{speaker: <A>, nth: n} repeats the beat of {speaker: <A>, nth: n−1}: event_change it to a new tactic
  (threaten, plead, mock, reveal) or event_remove it."
- **test:** A fixture with three "Admit it!" / "No!" pairs in a row.

#### WR-8 — Imply rather than explain (not on the nose)
- **statement:** Lines suggest what lies under them. A line that states a character's whole thought or feeling outright
  gets a hint.
- **source:** McKee ch. 8: "Writing on-the-nose means putting a character's fullest thoughts and deepest emotions
  directly and fully into what [the character] says out loud". "Dialogue should imply, not explain". Nonrealist genres are "the
  great exception". R49 §5.5.
- **scope:** line
- **tier:** advise. The form limits it: a live-audience speaker's public confession is the programme's point (Grindstaff pp. 19-21,
  100-101; R49 §4.5; conflict C-9).
- **params:** none
- **fix:** "{speaker: <A>, nth: n} says outright what <A> feels; it may land harder as an act on <B> (event_change)."
- **test:** Speaker 1 line "I feel sad and angry about Topic 1." gets the hint, and no refusal.

#### WR-9 — The last word cues the reply
- **statement:** A speech ends on the word that seals its meaning and draws the reply.
- **source:** McKee ch. 9: "ideally, the last word or phrase of each speech is the core word that seals meaning and
  cues a reaction from the other side of the scene."
- **scope:** line
- **tier:** advise. McKee states it as an ideal.
- **params:** none
- **fix:** "{speaker: <A>, nth: n} ends on filler; end it on the word <B> answers (event_change)."
- **test:** A fixture line ending "…, you know what I mean?" gets the hint.

#### WR-10 — Short words as emotion rises; no clutter
- **statement:** Lines get shorter as emotion and risk rise. Greetings and filler that do nothing are cut.
- **source:** McKee ch. 7: "The more emotional people become, the shorter the words and sentences they use"; "Eliminate
  clutter" ("Hi, how ya doing?").
- **scope:** line
- **tier:** advise. McKee gives no length.
- **params:** none
- **fix:** "{speaker: <A>, nth: n} is marked as rage (WR-5) and runs N words: event_change it shorter."
- **test:** A 40-word line marked by WR-5 gets the hint.

#### WR-11 — No long speech without a change (run of lines)
- **statement:** One speaker does not hold the floor for more than `max_run_lines` lines in a row without a change. A
  long speech is broken into beats against the listener.
- **source:**
  - McKee ch. 8: "any speech that runs on for too long without change in value charge risks lifelessness". The fix is
    to break a long speech into beats between the speaker and the silent character.
  - Blueprint §11.4 (deterministic proxy, `params.max_run_lines`).
- **scope:** exchange
- **tier:** advise → check when measured. The rule is sourced; its number is not.
- **params:** `max_run_lines` = pending — no source (McKee gives no count).
- **fix:** "<A> speaks N lines in a row ({speaker: <A>, nth: i}…{nth: j}): line_add a reply from <B> between them, or
  event_remove one."
- **test:** A fixture with six Character 1 lines in a row.

#### WR-12 — Speaking rate
- **statement:** A line's planned rate (its words over its planned seconds) lies between two and three words a second.
- **source:** McKee ch. 8: "The average speaking rate ranges between two to three words per second".
- **scope:** line
- **tier:** advise. McKee gives an average, not a limit, and the measured take is the real length.
- **params:** `words_per_s_min` = 2 /s, `words_per_s_max` = 3 /s — McKee ch. 8.
- **fix:** "{speaker: <A>, nth: n} is planned at 4.1 words a second: event_change it shorter."
- **test:** A 20-word line planned at 4.0 s gets the hint.

#### WR-13 — Speaker 1 speaks in Speaker 1's own question-and-answer exchange
- **statement:** A question-and-answer exchange scene has at least one lead speaker line. Speaker 1 introduces, asks and closes.
- **source:**
  - Blueprint §11.4 proxy: "the lead speaker silent through the lead speaker's own exchange".
  - Zettl p. 421, script 15.16: "HOST--INTRODUCES SHOW", "HOST--INTRODUCES GUEST", "HOST--ASKS FIRST QUESTION",
    "HOST--MAKES CLOSING REMARKS".
  - Grindstaff p. 4: Speaker 1 "prodded for more details".
- **scope:** scene
- **tier:** check. A count of Speaker 1's lines.
- **params:** `lead_lines_min` = 1 per question-and-answer exchange scene — blueprint §11.4 ("silent").
- **fix:** "Scene n has no line from <lead>: line_add {speaker: <lead>} a question to <speaker> before {speaker: <speaker>,
  nth: 1}."
- **test:** A fixture scene holding only Character 1's lines.

#### WR-14 — Speaker 1 asks open questions and follows up
- **statement:** Speaker 1's questions open Speaker 2 up and follow what Speaker 2 said. Yes/no questions and double questions
  fail.
- **source:**
  - Zettl p. 344: "an interviewer probing tactfully, yet persistently, into the guest's attitudes and feelings".
  - Zettl p. 442: Speaker 1 is clued in to the key questions.
  - Grindstaff pp. 3, 99: questions are prepared for Speaker 1.
  - R49 §5.9 (web: open-ended questions; follow-ups; "Double-barreled questions … confuse the source").
- **scope:** exchange
- **tier:** grade
- **params:** none
- **fix:** "{speaker: <lead>, nth: n} can be answered yes or no: event_change it into an open question about what <speaker>
  just said."
- **test:** A fixture with Speaker 1 asking only "Do you like Topic 1?" and "Is Topic 1 true?".

#### WR-15 — Speaker 2 leads with the point; never a bare yes or no
- **statement:** A speaker's answer gives its highlight first, then how Speaker 2 got there. A bare "Yes." or "No." fails.
- **source:**
  - Grindstaff pp. 100-101: "Say what you found and then how you got there. Don't build up to a point."
  - Grindstaff p. 116: "it is better to have a guest wander and digress than give simple yes or no answers".
- **scope:** line
- **tier:** grade
- **params:** none
- **fix:** "{speaker: <speaker>, nth: n} answers only 'No.': event_change it so <speaker> gives the point first, then why."
- **test:** A fixture speaker line "Yes."

#### WR-16 — Desires cross in conflict
- **statement:** The characters' scene intentions oppose each other. A scene whose desires run side by side, never
  crossing, fails.
- **source:**
  - McKee ch. 9, splintered scenes: "The characters' desires run side by side, never crossing in conflict".
  - McKee ch. 12: "If the writer were to grant the character [the character's] scene intention, the scene would stop".
  - McKee ch. 8: the duelogue is fixed by "a third thing".
- **scope:** scene
- **tier:** grade
- **params:** none
- **fix:** "In scene n <A> and <B> want things that never meet: event_change {speaker: <B>, nth: 1} so <B> wants what
  <A> is trying to stop."
- **test:** A fixture where lead speaker and speaker agree on every line.

#### WR-17 — The strongest story goes first
- **statement:** In a programme of several segments, the most important speaker (the most energetic talker, the one with the
  most at stake) leads.
- **source:** Grindstaff p. 123: "The most important guest always goes on first, setting the tone and framework for
  subsequent events". p. 124: "Lead with your most explosive story." Grindstaff states no rule that segments escalate
  (R49 §6; conflict C-10).
- **scope:** scene (the order of scenes)
- **tier:** advise. "Most important" is a reading across scenes, and no script tool reorders scenes yet. It becomes a
  grade when one does.
- **params:** none
- **fix:** "The strongest story (<speaker>) is in scene k: write it first (scene_add it before the others)."
- **test:** A two-scene fixture with the quiet speaker first and the confrontation second gets the hint.

#### WR-18 — Hold the surprise for a later segment
- **statement:** A fact or a speaker that will surprise someone on stage is held back and brought on later.
- **source:**
  - Grindstaff p. 117: speakers "can't mention [the late speaker's] affair until after [the late speaker's] wife joins [the late speaker] onstage".
  - Grindstaff pp. 12-13: the sister brought on in the third segment.
  - Grindstaff p. 182: "out came 'the opposition'".
- **scope:** scene
- **tier:** advise. Grindstaff shows the practice but states no rule.
- **params:** none
- **fix:** "<speaker>'s reveal comes in scene 1 line 2; it may land harder later (event_move it into a later scene)."
- **test:** A fixture revealing the secret in the first line gets the hint.

#### WR-19 — A segment ends on a tease, applause in and out of breaks
- **statement:** Before a break Speaker 1 teases what is next to camera. The audience applauds going into and coming out
  of a break.
- **source:**
  - Grindstaff p. 5: the tease, "Up next is a woman whose … Don't go away!"
  - Grindstaff p. 46: "Don't go away, we'll be right back".
  - Grindstaff p. 67: audiences "clap wildly going in and out of commercial breaks".
- **scope:** scene
- **tier:** advise. It is a practice of the form; the script has no break event.
- **params:** none
- **fix:** "Scene n ends without a tease: line_add {speaker: <lead>} a tease to camera at its end and cue_add applause
  after it."
- **test:** A two-scene fixture whose first scene ends on a speaker line gets the hint.

#### WR-20 — The scene keeps its named length
- **statement:** A scene with a named length runs within 10 % of it. The last scene is held to it as well.
- **source:**
  - `hub/modules/director/length.py` (10 %; `least_ms` = 900 × s, `most_ms` = 1 100 × s).
  - Round 1 F6 (19 s for "about 30") and F9 (32.6 s for 30; the last scene is never refused).
  - Zettl p. 416: time cues back-timed from the end. Zettl p. 362: a performer must be ready to fill or cram.
- **scope:** scene
- **tier:** check. Timing arithmetic.
- **params:** `length_tolerance` = 10 % — `hub/modules/director/length.py`.
- **fix:** "Scene n runs 32.6 s, outside 27.0-33.0 s: event_remove or shorten a line by about N words (event_change)."
- **test:** Round 1's file: scene 1 marked 30 s at 32.6 s and last in the script, refused at the lock.

## 2. STAGER — positions, the line, the house (Katz chs. 9-11, Zettl)

Code places people from the cast and the set (§11.1, §11.5). The model may pick a named position, never invent one.

#### ST-1 — The staging pattern follows the cast count
- **statement:** A scene's staging is one of Katz's named patterns, chosen by how many players are on stage:
  - two players: the I pattern, Positions One to Ten;
  - three players: the A or L pattern;
  - four or more: a few key set-ups around the principal two.
- **source:**
  - Katz p. 176: "The only arrangement for two subjects is the I pattern".
  - Katz p. 177: "the basic building block … the line of action can be established between only two people at a
    time".
  - The positions, pp. 178-194: One face-to-face p. 178; Two shoulder-to-shoulder p. 182; Three at 90° p. 184.
  - Katz p. 195 (A and L patterns); pp. 209-211 (groups).
- **scope:** scene
- **tier:** check. Code picks from the count.
- **params:** none
- **fix:** none to the Director. The stager sets the pattern. A hand choice outside the list is refused: "choose one of
  <named positions>".
- **test:** A two-player scene given an A pattern.

#### ST-2 — Speaker 1 sits at one side of the other speakers
- **statement:** With two or more speakers, Speaker 1 is placed at one end of the row, never between them.
- **source:**
  - Zettl p. 271: "put the host, not in the middle, but to one side of the guests. Otherwise you will not be able to
    maintain proper screen positions."
  - Zettl pp. 273-274, figs. 10.19-10.20.
  - Katz p. 202: the L arrangement "occurs when a single player is addressing two others".
  - This corrects Katz's A pattern "as might be expected in an interview" (p. 198); see C-8.
- **scope:** context
- **tier:** check. Speaker 1's `home` must be the lowest or highest among the stage cast.
- **params:** none
- **fix:** "<lead> stands between <speaker 1> and <speaker 2>: context_set <lead> home to <a value left of both speakers>."
- **test:** A fixture with lead speaker home 50 and speakers at 20 and 80.

#### ST-3 — One line of conversation; every camera on one side of it
- **statement:** The stage line runs through the stage cast from Speaker 1. Every set-up of the scene's camera set is
  on the audience side of it.
- **source:**
  - Zettl p. 272: "For closeups as well as over-the-shoulder shooting, keep both cameras on the same side of the
    vector line."
  - Zettl p. 469: the line of conversation is "the principal vector that you should not cross with your cameras".
  - Katz p. 130: "only camera positions within the established semicircle are permitted".
  - S&B p. 51 (R49 §2.9).
- **scope:** scene
- **tier:** check. Geometry from `home` and the set-ups.
- **params:** none
- **fix:** "{shot: n} is shot from behind the stage line: event_change its camera to one of this scene's set-ups:
  <list>."
- **test:** A camera set with one set-up behind the other speakers' chairs.

#### ST-4 — A few set-ups, reused
- **statement:** A scene uses at most four sight lines (set-ups) and returns to them rather than making new ones.
- **source:**
  - Katz p. 211: "Limit yourself to a few key setups. If you are establishing more than four sightlines to move
    around space in a large group, you are creating unnecessary problems."
  - Katz p. 196: "reuse positions when possible". Katz p. 135: reusing setups gives "a consistent sense of space".
  - Zettl p. 421: "If you can do a show with two cameras, don't request three."
- **scope:** scene
- **tier:** check. Count the distinct set-ups.
- **params:** `sightlines_max` = 4 — Katz p. 211.
- **fix:** "Scene n uses 5 set-ups: event_change {shot: k} camera to the set-up of {shot: j}."
- **test:** A fixture scene with five distinct camera angles.

#### ST-5 — Cameras numbered left to right
- **statement:** The camera set's cameras are numbered from the farthest left (1) to the farthest right.
- **source:** Zettl p. 454 (15.35): camera 1 "on the farthest left side of the action and the highest-number camera on
  the farthest right side". Crossed cameras complicate directing.
- **scope:** scene
- **tier:** check. Naming from geometry.
- **params:** none
- **fix:** none (code names the cameras).
- **test:** A camera set whose camera 1 stands right of camera 2.

#### ST-6 — Pairs are matched
- **statement:** The two singles, or the two OTS shots, of a conversing pair share framing height and lens, and their
  sight lines fall at the same distance from the lens.
- **source:**
  - S&B pp. 33-34 (R49 §2.9): "It is important that they be matched, however, or they will not cut smoothly
    together"; "use lenses at the same focal length".
  - Katz p. 179: OTS "usually shot as matched pairs maintaining consistent lens and framing choices".
  - Katz p. 176: equal sight-line distance in alternating close-ups.
  - Framing heights: Katz fig. 6.1, p. 122.
- **scope:** shot
- **tier:** check. The framing fields of the pair are compared.
- **params:** none
- **fix:** "{shot: n} (medium on Character 1) does not match its pair {shot: m} (close-up on Character 2): event_change its framing
  to close-up."
- **test:** An OTS pair framed medium on one side and close-up on the other.

#### ST-7 — Everyone on stage is wholly on stage, and apart
- **statement:** Each stage cast member's place maps inside the stage with the member's whole figure. No two members share a
  place.
- **source:** Round 1 F1: both cast at home 0, "figures stacked half off the left edge" (`tween.ts:136-141`); the fix
  named there is an inset range and spread equal homes. No book.
- **scope:** context
- **tier:** check. Arithmetic on `home`.
- **params:** `home_inset` = pending — no source (F1 names the fix, not the number); `home_spread_min` = pending — no
  source.
- **fix:** none to the Director. The stager insets and spreads (F1). "context_set <name> home: a number of 0-100" is the
  only hand fix.
- **test:** Round 1's model-written context with Character 2 and Character 1 both at home 0.

#### ST-8 — Seated where the staging seats them
- **statement:** A role that the scene's staging seats (speakers in chairs, Speaker 1 at a table) holds a sitting pose from
  the scene's start.
- **source:** Round 1 F5: stick figures standing though story, context and sketch have them seated. Blueprint §11.5's
  `three_camera` preset: "the others seated".
- **scope:** scene
- **tier:** check, from the staging record. When only the story says it, it is a grade question.
- **params:** none
- **fix:** "<speaker> stands in a chair staging: pose_add {shot: 1, character: <speaker>, pose: sit} at 0."
- **test:** Round 1's script (Character 2 and Character 1 standing at a table with microphones).

#### ST-9 — Eye contact for a question-and-answer exchange
- **statement:** Speaker 1 faces Speaker 2 through the question-and-answer exchange. Stagings without eye contact (Katz Positions
  Four-Nine) are for tension, not the default.
- **source:**
  - Zettl p. 422: Speaker 1 "will face the guest for the rest of the interview".
  - Katz p. 185: from Position Four on, stagings "create tension … due to the absence of eye contact between the
    players".
- **scope:** scene
- **tier:** advise. Choosing tension is a director's choice.
- **params:** none
- **fix:** "<lead> faces away from <speaker> through scene n; for an ordinary question-and-answer exchange: pose_add a head turn to <speaker>."
- **test:** A fixture with Position Seven for a calm question-and-answer exchange gets the hint.

#### ST-10 — Speaker 1 turns to camera to open and close
- **statement:** Speaker 1 speaks into the lens at the opening and closing (and for a tease). Through the question-and-answer exchange Speaker 1
  faces Speaker 2.
- **source:**
  - Zettl p. 422: "The host will turn into the camera for the opening and closing".
  - Zettl p. 359: "look directly into the lens whenever you intend to establish eye contact with your viewer".
  - Grindstaff pp. 5, 46: teases to camera.
- **scope:** line
- **tier:** advise. Addressing the camera mid-scene (Grindstaff's teases) is allowed.
- **params:** none
- **fix:** "{speaker: <lead>, nth: n} is addressed to the camera mid-exchange; address it to <speaker> (event_change) or
  keep it as a tease."
- **test:** A lead speaker line to camera in the middle of an exchange gets the hint.

#### ST-11 — The house is the set's second half
- **statement:** A set carries `audience: none | heard | seen`.
  - The house is drawn only on `seen`.
  - A `seen` set names at least two featured members.
  - Without featured members, reaction cut-ins stay on the `row` plate at medium distance.
- **source:**
  - Blueprint §16.1-16.2 (Hub design, no book).
  - Grindstaff p. 121: the audience in the studio is "an integral part of the genre".
  - Zettl p. 194: an audience on camera is the programme's choice (its monitors are turned off).
  - Holman p. 166: a multi-camera comedy's track breakdown keeps "Audience reaction (laughs)" its own stem.
- **scope:** context
- **tier:** check. Fields and counts on the set record.
- **params:** `featured_min` = 2 — blueprint §16.2 (design value, no book).
- **fix:** none to the Director (the set is made in Sets/Casting). The rule answers with what the switcher may use.
- **test:** A `seen` set with no featured member that is asked for a close audience reaction.

#### ST-12 — Who sits where in the house
- **statement:** Featured audience members sit near the front (and on the aisle for questions). An expert or a planted
  party may sit in the house and speaks in the last segment.
- **source:**
  - Grindstaff p. 127: sitting "near the front of the stage increases the chance of getting targeted for a reaction
    shot"; the aisle, "the chance of getting chosen by the host to ask a question".
  - Grindstaff p. 89: experts come "only during the last segment of a show … sometimes seated in the audience".
  - Grindstaff p. 122: planted people with a stake in the audience.
- **scope:** context
- **tier:** advise. Grindstaff gives the odds, not a rule.
- **params:** none
- **fix:** "Featured member <name> sits in row 9; seat <name> in the front rows (context_set place {where: house, row: 1})."
- **test:** A featured member placed in the back row gets the hint.

#### ST-13 — Speaker 1 into the house: a hand microphone, the person picked by order or raised hand
- **statement:** When Speaker 1 goes into the audience, Speaker 1 walks to the person with a hand microphone. Questioners are
  taken in a set order or by a raised hand.
- **source:** Zettl p. 155: the performer walks up to people with a hand microphone; "The sequence of students asking
  questions is predetermined, or the students asking questions identify themselves by raising their arms." Blueprint
  §16.4 (`move` blocking event).
- **scope:** scene
- **tier:** advise. The `move` event is not built yet (A.3 gains it).
- **params:** none
- **fix:** "<lead> answers <member> in row 3 from the stage; move <lead> there first (the move event, when A.3 has it)."
- **test:** A fixture where an audience member's line is answered by a lead speaker at stage home gets the hint.

#### ST-14 — Talent moves, cameras stay
- **statement:** Block people so that they, not the cameras, do most of the moving. Stage for the camera, not for the
  room.
- **source:** Zettl p. 449: "Always try to block talent in such a way that the talent rather than your cameras will do
  most of the moving." Zettl p. 424: "stage your action for the camera, and not for an audience as you would in the
  theater".
- **scope:** scene
- **tier:** advise
- **params:** none
- **fix:** "{shot: n} pans to follow <A>; let <A> come into the set-up (pose_add / move) instead."
- **test:** A fixture with three camera moves in one scene gets the hint.

#### ST-15 — The three-camera preset and its cameras
- **statement:** `three_camera`:
  - Speaker 1 standing or at a table, the other speakers in chairs, the audience in front;
  - three cameras numbered left to right: the outer two on close shots of the principal two, the centre on the wider
    master or two-shot;
  - a camera able to turn to the house for audience reaction.
- **source:**
  - Blueprint §11.5 (the preset).
  - Katz pp. 130-133: the triangle "is used extensively for live television programs such as quiz shows, sports
    programs and sit-coms"; the middle camera "always obtains the two-shot".
  - R49 §4.1 (web): "the two outer cameras shoot close-up shots or 'crosses' … the central camera … a wider master
    shot".
  - Zettl p. 454 (numbering). Zettl p. 470: a third camera "can get reaction shots from the audience" (a hearing
    remote, not a multi-camera production).
- **scope:** scene
- **tier:** check. Code builds it.
- **params:** `cameras` = 3 — Katz pp. 130-131 / R49 §4.1. A live-audience programme's own count was not found; one 1994 taping had
  seven (R49 §4.2). measured: pending.
- **fix:** none (code).
- **test:** A three-camera-preset scene whose camera set has no centre two-shot set-up.

## 3. SWITCHER — when the picture cuts and to what (R49 §2-§4, Zettl chs. 10 & 15, Katz, Murch, S&B)

Code cuts each scene's exchange into shots (§11.3). A hand shot is checked against the same rules. Shot kinds:
`establishing | single | two_shot | ots | reaction | insert | audience | wide`, plus from §16.5 `audience_wide |
audience_reaction | member_in_house | plant_single`.

#### SW-1 — A scene opens on the shot that shows who is where
- **statement:** A scene's first shot is the establishing wide or the two-shot with everyone on stage in frame. In the
  programme's first scene, a lead speaker-to-camera close-up may come before it.
- **source:**
  - Katz glossary p. 358: the establishing shot is "Typically a long shot at the beginning of a scene designed to …
    orient them to … relative placement of subjects".
  - Zettl p. 511: "Orientation shot, usually a long shot". Zettl p. 422: "the director first reveals the basic
    relationship of host and guest".
  - Zettl p. 421 (15.16): "CU of host. Host faces camera." then "2-shot of host and guest".
  - Holman p. 36: "picture editors almost always start with the master shot".
  - R49 §1.4-1.5.
  - Conflicts: C-3.
- **scope:** scene
- **tier:** check. The first shot's kind and who is in frame.
- **params:** none
- **fix:** "Scene n opens on a single of <A>: shot_add a wide of everyone on stage before {shot: 1}, or event_change
  {shot: 1} to the two-shot."
- **test:** A fixture scene opening on Character 1's close-up.

#### SW-2 — Cut to the new speaker as the speaker begins
- **statement:** When the speaker changes, the picture cuts to the new speaker's single, or to that speaker's side of the OTS
  pair, at that speaker's measured speech start.
- **source:**
  - S&B p. 47 (R49 §2.7): "As one individual finishes speaking (to someone not in the shot), we cut to the second person
    just as [that person] begins to reply."
  - Zettl p. 273: "In an interview, the cut occurs generally at the end of a question or answer".
  - Zettl pp. 434-435: "Cut to CU" beside each new speaker in the panel script.
  - Murch "Dragnet" calls this pattern "a shallow simplicity"; see C-1. It is decided for this form.
  - Zettl's own exceptions are carried by SW-4, SW-6 and SW-21.
  - The block's "not each time the next one starts to talk" (`system-prompt-video-paragraph.md:73`) is corrected by
    this rule.
- **scope:** exchange
- **tier:** check. A speaker change and the cut time are both in the script and the takes.
- **params:** `cut_late_ms` = 0 ms — S&B "just as [that person] begins to reply" (at the new speaker's measured `speech_start_ms`).
  The blueprint's "slightly late" has no source (C-2). measured: pending.
- **fix:** For a hand shot: "{speaker: <B>, nth: n} begins inside {shot: k} on <A>: shot_add a single of <B> at <B>'s
  line's start, or event_move {shot: k}'s end there."
- **test:** The Character 1 fixture's l1 (Character 2) to l2 (Character 1) with no cut at l2's start, the round 1 pattern of one wide
  shot over four lines.

#### SW-3 — Cut at a phrase end, never inside a word
- **statement:** A cut on dialogue falls at the end of a sentence, a phrase, a question or an answer. A cut that lands
  inside a measured word is refused.
- **source:**
  - Zettl p. 273: "cutting at the end of a sentence or phrase produces a cleaner rhythm than in the middle".
  - Blueprint §11.3: "a cut that lands mid-word … refused with the rule".
  - Zettl p. 248: out of a film, the cue is the last words.
- **scope:** shot
- **tier:** check. Word timestamps from the words judge.
- **params:** none
- **fix:** "{shot: k} cuts inside <word> of {speaker: <A>, nth: n}: event_move it to <the phrase end, ms>."
- **test:** A hand shot whose start falls 120 ms into a measured word.

#### SW-4 — The reaction cut-in: when, and of whom
- **statement:** A reaction of the person spoken to is cut in during a line that runs past `reaction_after_ms`, or that
  WR-5 marks as a provocation or reveal.
- **source:**
  - Blueprint §11.3 rule 3.
  - S&B p. 46 (R49 §2.8): "the reaction of the listener is often more interesting and telling than that of the
    speaker".
  - Katz p. 227: "we learn as much from the reaction as we do from the action".
  - Katz p. 228: the reaction "doesn't have to be a CU of the man's face".
  - Zettl p. 426: "an occasional reaction shot of the host".
- **scope:** exchange
- **tier:** advise → check when measured. The trigger is sourced; the threshold is not. The WR-5 mark path is a check
  now.
- **params:** `reaction_after_ms` = pending — no source. R49 §6: no published length for a line's shot or a reaction
  shot. First value from the measured recording (§11.6).
- **fix:** For a hand reaction: "{shot: k} is a reaction of <C>, who is not spoken to in {speaker: <A>, nth: n}:
  event_change it to a reaction of <B>."
- **test:** A Character 1 line marked by WR-5 with no reaction of Character 2 cut in, once the mark path is a check.

#### SW-5 — Reactions sparingly
- **statement:** Cast reaction shots are occasional. A scene does not spend more than `reaction_share_max` of its
  picture on them, and never cuts two reactions back to back.
- **source:**
  - S&B p. 40 (R49 §2.8): "It is not common, however, that the audience is more interested in a person who is listening
    than in a person who is speaking." Overused, the audience may think the camera is on the wrong person.
  - Zettl p. 426 ("occasional"). Zettl p. 422 (Speaker 1 "simply is not important in this interview").
  - Round 1's audit: "reaction shots taught without 'sparingly'".
  - Conflicts: C-6.
- **scope:** scene
- **tier:** advise → check when measured. The number comes from the measured recording.
- **params:** `reaction_share_max` = pending — first value from the measured recording (§11.6 "reaction-cut frequency").
- **fix:** "Scene n spends 40 % of its picture on reactions: event_remove {shot: k}."
- **test:** A fixture with a reaction on every Character 1 line gets the hint.

#### SW-6 — A reaction comes a second early and lies inside the line
- **statement:** A reaction (and every cutaway) lies inside a line's time, carrying `during: <line id>`, and the line's
  sound continues over it. It is cut in about a second before the moment it shows.
- **source:**
  - S&B p. 40 (R49 §2.8): "It is wise to cut to [Speaker 1] a second early so that we may take in [Speaker 1's] expression".
  - Zettl p. 273: "reaction shots are often smoother when they occur during, rather than at the end of, phrases or
    sentences".
  - Katz glossary p. 361: a reaction shot is "the shot of a player listening while another player's voice continues on
    the sound track".
  - Holman p. 165: the L-cut, "Sound established in one scene overlaps into the next".
  - Blueprint §11.3 (data model).
  - R49 §2.3 (Dmytryk, web): "Find the first frame of the reaction and add 3-4 frames."
- **scope:** shot
- **tier:** check. Times against the line and the mark.
- **params:** `reaction_lead_ms` = 1000 ms — S&B p. 40 ("a second early"). measured: pending.
- **fix:** "{shot: k} (reaction of <B>) starts after the line it answers ends: event_move it to start inside {speaker:
  <A>, nth: n}, about a second before <the marked words>."
- **test:** A reaction shot placed after its line's end, with no line under it.

#### SW-7 — A cutaway needs someone speaking and shows no speaking mouth
- **statement:** A reaction, insert or audience shot with no line sounding under it is refused. A cutaway never frames
  the mouth of the one speaking.
- **source:**
  - Blueprint §11.3: "a reaction with nobody speaking … refused".
  - Katz p. 361 (the reaction shot's definition, in SW-6).
  - Holman p. 118: cutaways are shots that "above all else, do not show the mouth of the person speaking"; lip flap is
    "when the picture shows a speaking person whose voice we do not hear" (also p. 32).
- **scope:** shot
- **tier:** check
- **params:** none
- **fix:** "{shot: k} (reaction of <B>) has no line under it: event_move it inside {speaker: <A>, nth: n} or
  event_remove it."
- **test:** A reaction shot placed over a 2 s gap with no line.

#### SW-8 — A run of short lines holds the two-shot
- **statement:** When `run_min_lines` or more lines, each shorter than `short_line_ms`, alternate between two people,
  the switcher holds the two-shot (or one OTS side) instead of cutting single to single.
- **source:**
  - Katz p. 182: "this use of CUs tends to break up the scene". Katz p. 188: "overcutting destroys the unity of the
    scene".
  - S&B p. 49 (R49 §3.5): "There is a quick limit, luckily, to fast cutting in television".
  - Zettl p. 276: switching cannot keep up fast cutting among three or four cameras.
  - Murch "Dragnet": the cut per line ("Have you been downtown yet?" Cut. "No." Cut.) as the shallow pattern.
  - Blueprint §11.3 rule 4.
- **scope:** exchange
- **tier:** advise → check when measured. The rule is sourced; both numbers are not.
- **params:** `short_line_ms` = pending — no source; `run_min_lines` = pending — no source. First values from a
  run on the server (§11.6).
- **fix:** For a hand cut: "{shot: k}…{shot: m} cut single to single on one-word lines: event_remove them and let the
  two-shot hold."
- **test:** A fixture of six one-word exchanges cut as six singles gets the hint.

#### SW-9 — An entrance plays wide, cut while the person is still in frame
- **statement:** A speaker's entrance is shown on the wide (then a fuller shot of Speaker 2). The cut out of an entrance or an
  exit comes while the person is partly in frame. A cleared frame is held 1-2 s.
- **source:**
  - R49 §4.7 (Heimbuch, web): on a speaker's entrance the crew used wide shots, then head-to-toe shots.
  - Katz p. 155: an exit or entrance is cut "while the subject is still partially within the frame"; a cleared frame is
    held "for a minimum of 1-2 seconds"; opening on the subject already in frame "is somewhat abrupt".
  - Blueprint §11.3 rule 5.
- **scope:** shot
- **tier:** check, when an entrance event exists (a `move` onto the stage, or a cue the script marks as entrance).
- **params:** `cleared_frame_min_ms` = 1000 ms — Katz p. 155 ("a minimum of 1-2 seconds", the low end). measured:
  pending.
- **fix:** "<speaker>'s entrance at {cue, nth} is on <speaker>'s close-up: event_change {shot: k} to the wide."
- **test:** A fixture entrance cut straight to Speaker 2's close-up.

#### SW-10 — The emotional peak lands on a face
- **statement:** When a WR-5-marked line lands (a reveal, a provocation, a breaking point), the picture goes to the
  close shot of the one it lands on.
- **source:**
  - Grindstaff p. 250: "All good television is built around moments of dramatic revelation … hence the importance of
    slow motion and the close-up."
  - Grindstaff pp. 19-20: the emotional peak is on the body ("[the partner's] jaw drops in rage and disbelief").
  - Zettl pp. 274-275: the closeup is "an especially effective intensifier if the action remains largely internal".
  - Zettl p. 255: "A cut to a tighter shot generally intensifies the screen event".
  - Blueprint §11.3 rule 5 says the reveal "returns to the wide, then to the reaction". See C-7.
- **scope:** exchange
- **tier:** check, once WR-5 has marked the line.
- **params:** none
- **fix:** For a hand shot: "{speaker: <A>, nth: n} (marked reveal) lands on a wide: event_change {shot: k} to a close
  shot of <B>."
- **test:** The Character 1 fixture's marked "The last word is mine!" covered only by the wide.

#### SW-11 — An audience cue may cut to the audience, then back on Speaker 1
- **statement:** On a `reaction` cue (applause, laughter, gasp), the switcher may cut to `audience_wide` or
  `audience_reaction`, then returns to the stage on Speaker 1.
- **source:**
  - Blueprint §11.3 rule 6 and §16.5.
  - Grindstaff pp. 127-129: reaction shots are sought, and additional ones taped after the programme ("inserted at
    appropriate moments later in the editing process", p. 129).
  - Zettl p. 470: a camera for "reaction shots from the audience".
  - R49 §4.7 (web): "You also want to make sure you get those reaction shots, too, for bigger laughs."
- **scope:** shot
- **tier:** check. The cue kind and the set's `audience` field decide.
- **params:** none
- **fix:** "{shot: k} (audience) is followed by a speaker's single: event_change {shot: k+1} to <lead>."
- **test:** A gasp cue on a `seen` set with an audience shot followed by Character 1's single.

#### SW-12 — No house in picture unless the set shows it
- **statement:** On a set with `audience: none`, no audience shot. On `heard`, the reaction sound plays and no audience
  picture is cut.
- **source:**
  - Blueprint §16.1, §16.5: "never on a set with `audience: none`; on `heard`, the sound fires and no picture does".
  - Holman p. 166: a multi-camera comedy's audience reaction is its own sound stem.
  - Zettl p. 194: showing the audience is the programme's choice.
- **scope:** shot
- **tier:** check
- **params:** none
- **fix:** "{shot: k} shows the audience, which this set does not show: event_remove it."
- **test:** An `audience_wide` shot on a `heard` set.

#### SW-13 — The audience reaction cut-in
- **statement:** An `audience_reaction` is a featured member's single (or the `row` plate, ST-11). It is cut in about a
  second before the line it reacts to lands, and held `reaction_hold_ms`. Nobody mugging or waving is chosen.
- **source:**
  - Blueprint §16.5.
  - S&B p. 40 (a second early, SW-6).
  - Grindstaff pp. 127-128: "the cameras will avoid those sections of the audience in which anyone waves, makes faces,
    or shouts out unsolicited comments".
  - Grindstaff p. 66: "big reactions" are encouraged.
- **scope:** shot
- **tier:** advise → check when measured. The hold time is not sourced.
- **params:** `reaction_lead_ms` = 1000 ms — S&B p. 40; `reaction_hold_ms` = pending — first value from the measured
  recording (§11.6, the hand labels).
- **fix:** "{shot: k} cuts to the house after the line has landed: event_move it to about a second before {speaker:
  <A>, nth: n}'s marked words."
- **test:** An audience reaction placed 2 s after the marked line ends gets the hint.

#### SW-14 — Cut to whom Speaker 1 looks at in the house
- **statement:** When Speaker 1 turns to an audience member and addresses that member, the switcher cuts to that person.
- **source:** R49 §4.7 (Heimbuch, web; one live-audience director): "If we didn't, it would have been a lost opportunity,
  and the people at home would have been confused." Katz p. 200: "Cutting on [the man's] head turn is a powerful editing cue."
- **scope:** shot
- **tier:** advise. One web source for the form, and the look is not modelled yet.
- **params:** none
- **fix:** "{speaker: <lead>, nth: n} is addressed to <member>, who is never seen: shot_add a `member_single` of
  <member> inside it."
- **test:** A lead speaker line addressed to a featured member with no shot of that member gets the hint.

#### SW-15 — Screen sides are kept; crossing the line needs a neutral shot between
- **statement:** Every shot keeps each person on the screen side the stage line gives that person. Speaker 1's single stays on
  Speaker 1's side.
  - A cut that would flip a side, including the turn to the house's reverse set-up and back (§16.4), has a cutaway or
    a straight-on neutral shot between.
  - A straight flip is refused.
- **source:**
  - Zettl pp. 270-271: "the viewer expects the people to remain in their relative screen positions even during
    closeups or reverse-angle shooting".
  - Zettl p. 274: "Keep the closeup of the host on the left side of the screen".
  - Zettl pp. 254, 509, the cutaway: "neutral as to screen direction (usually straight-on shots). Used to intercut
    between two shots in which the screen direction is reversed."
  - Katz p. 130; Katz pp. 136-139 (a player crossing "seen clearly"; the cutaway "a quick fix").
  - S&B p. 51 (R49 §2.9).
  - Conflicts: C-4.
- **scope:** shot
- **tier:** check. Sides follow from `home` and the set-up.
- **params:** none
- **fix:** "{shot: k} puts <lead> screen-right after {shot: k−1} had <lead> screen-left: shot_add a neutral (audience or
  straight-on) shot between, or event_change {shot: k} to a set-up on the stage line's side."
- **test:** The house reverse cut straight after a stage two-shot.

#### SW-16 — No near-identical cut
- **statement:** Two shots in a row differ in set-up or framing. A cut to the same or nearly the same view (a jump cut)
  is refused unless repeated on purpose.
- **source:**
  - Zettl p. 269: "don't cut to nearly identical shots unless you want to repeat a certain picture sequence for effect …
    Why cut, if you show the viewer exactly the same thing?" Glossary, "Jump Cut", p. 514.
  - Murch, "Why Do Cuts Work?": a change "neither subtle nor total" jars.
  - R49 §1.9 (the 30-degree rule, web; no book gives the angle).
  - Round 1 F10: an inserted shot repeats the wide.
- **scope:** shot
- **tier:** check. Set-up and framing compared.
- **params:** `min_angle_deg` = pending — 30° is web-only (R49 §1.9). Zettl gives no angle, "a slightly different point
  of view" (p. 269).
- **fix:** "{shot: k} repeats {shot: k−1}'s view (wide of Character 2 and Character 1): event_remove it or event_change its framing."
- **test:** Round 1 readout 2's order s1 (wide), s3 (the same wide) as written before s4 was inserted.

#### SW-17 — No jump from an extreme long shot to a close shot
- **statement:** Between an extreme long shot and a close-up or extreme close-up (in either direction), a medium shot
  comes between.
- **source:**
  - Zettl p. 269: "Cutting from an extreme long shot to an extreme closeup, or from extreme angles, makes for poor
    subject continuity."
  - Zettl p. 270: "You should zoom in somewhat, or cut to a medium shot, before cutting to the closeup."
  - Zettl's five steps XLS, LS, MS, CU, XCU: p. 72.
  - Katz p. 121 disagrees for film ("Today … audiences easily accept extreme changes in scale"); see C-5.
- **scope:** shot
- **tier:** check, on the framing scale.
- **params:** Which Hub framings count as XLS = pending. `audience_wide` and the set's widest plate are candidates; the
  set plates decide.
- **fix:** "{shot: k} cuts from the house wide to <A>'s close-up: shot_add a medium of <A> between, or event_change
  {shot: k} to a medium shot."
- **test:** `audience_wide` followed directly by a speaker's close-up.

#### SW-18 — Shot floor
- **statement:** No shot is shorter than `shot_min_ms`.
- **source:**
  - Hub timing: `layout.SHOT_MIN_MS` 1 000 ms (citing `layout.py:17-18`; blueprint §11.8's property test "no
    shot under the floor").
  - No book gives a shot minimum. The nearest figure is Katz's cleared-frame hold of "a minimum of 1-2 seconds"
    (p. 155).
  - Round 1 F11: an empty 1 s shot s4.
- **scope:** shot
- **tier:** check
- **params:** `shot_min_ms` = 1000 ms — `layout.py` (engineering value, no book). measured: pending (§11.6 "fraction of
  shots under 2 s").
- **fix:** "{shot: k} runs 0.6 s: event_remove it, or event_move its end to at least 1.0 s after its start."
- **test:** A hand shot of 600 ms.

#### SW-19 — Hold ceiling, and staying when nothing better is offered
- **statement:** A shot is held while it is the best one, up to `shot_max_hold_ms`. The switcher does not cut without
  a reason.
- **source:**
  - Zettl pp. 269-270: "If you cannot vary the shot, don't change it. Don't be afraid to stay on one camera, even for a
    relatively long period of time."
  - Zettl p. 421: "staying on the one camera that delivers the most expressive picture".
  - Murch, "Most with the Least": "it takes more work and discernment to decide where not to cut".
  - R49 §2.3, §3.5 (Dmytryk, web): "Never make a cut without a positive reason."
  - Blueprint §11.3 rule 7.
- **scope:** shot
- **tier:** advise → check when measured. Zettl and Murch argue for long holds and give no ceiling.
- **params:** `shot_max_hold_ms` = pending — first value from the measured recording (§11.6).
- **fix:** "{shot: k} holds 14 s on the wide over four speakers; consider shot_add a single of <B> at {speaker: <B>,
  nth: n}."
- **test:** A 14 s wide over a four-line exchange gets the hint.

#### SW-20 — The scene's cutting rate is the form's
- **statement:** A scene's average shot length lies in the form's measured range.
- **source:**
  - R49 §3.3 (Arnold & Tilton, web): median shot length of late-century multi-camera comedy series 2.8-4.0 s.
  - R49 §3.4: Shot Logger, all TV genres, ASL 6.04 s, with no question-and-answer programme in the log.
  - Murch, "Dragnet": a dialogue scene "would still feel 'normal' (in an American film) averaging six cuts per minute
    or less".
  - R49 §3.2 (Bordwell, web): 2-3 s per shot in intensified continuity.
  - Blueprint §11.3 rule 7: the production's own number is not known.
  - Conflicts: C-6.
- **scope:** scene
- **tier:** advise → check when measured. No source gives the form's figure.
- **params:** `asl_range_s` = 2.8-4.0 s — R49 §3.3 (a multi-camera comedy figure, standing in per §11.6). measured:
  pending (the first recording file measured, §11.6).
- **fix:** "Scene n averages 9.5 s a shot against 2.8-4.0 s: the switcher's cut is the remedy; hand shots: event_remove
  the extra cuts or shot_add."
- **test:** Round 1's scene (3 shots of about 9.5 s, blueprint §10) gets the hint.

#### SW-21 — Cut on the action
- **statement:** When someone moves while speaking (rises, sits, turns), the cut goes on the movement, during it, to a
  wider shot. It does not wait for the phrase end.
- **source:**
  - Zettl p. 272: "When cutting on action, cut during the motion … not before or after it"; a person rising from a
    chair: "cut to a wider shot just after [the person] has started to rise but before [the person] stands".
  - Zettl p. 273: "Action is usually the stronger motivation for a cut than dialogue."
  - Katz pp. 154-155: "Cutting on the action is found in virtually all types of sequences".
- **scope:** shot
- **tier:** check. A pose change (sit/stand) inside a line is in the script.
- **params:** `action_cut_after_ms` = pending — no source. Zettl: "just after [the person] has started".
- **fix:** "<speaker> stands (pose at 12.4 s) inside {shot: k}'s close-up: shot_add a wider shot starting just after
  12.4 s."
- **test:** A stand pose mid-line inside a close-up with no cut.

#### SW-22 — Cut on the look: the pivot
- **statement:** When Speaker 1 turns Speaker 1's attention to another person, the turn is the cue. The next shot is the person
  Speaker 1 now addresses.
- **source:**
  - Katz p. 135: "The establishment of a new line is usually set up with a shot of a person who turns [the person's] attention to
    a new area or person within the frame."
  - Katz p. 200: "The direction of the man's look is the determining factor."
  - Katz p. 123: "the most natural cut is the cut on the look" (Godard).
  - Zettl p. 421: "Host turns to guest. CU guest."
- **scope:** exchange
- **tier:** advise. The look is not yet a field. When a line's `addressed` changes it can be a check.
- **params:** none
- **fix:** "{speaker: <lead>, nth: n} turns to <C>; shot_add <C>'s single after the turn of <lead>."
- **test:** A lead speaker line whose addressee changes from speaker 1 to speaker 2 with no shot of speaker 2 gets the hint.

#### SW-23 — Groups: OTS and an occasional group shot for three; singles for larger groups
- **statement:**
  - With three players, after the establishing shot the conversation is carried in OTS shots, with an occasional
    three-shot or two-shot.
  - With four or more, each speaker gets a close-up of that speaker.
  - A panel lead speaker's handover by name cuts to the named speaker.
- **source:**
  - Katz pp. 197-198: "After the establishing shot, an entire conversation can be comfortably handled in OTS shots and
    an occasional three-shot or two-shot to vary the rhythm."
  - Katz p. 209: "close-ups are often used in favor of three- and four-player group shots, since this helps
    differentiate the players".
  - Zettl pp. 434-435: "Isn't that true, [Speaker 1]?" then "Cut to CU of [Speaker 1]".
- **scope:** exchange
- **tier:** check. The cast count and the line addressee are in the script.
- **params:** `group_singles_from` = 4 players — Katz p. 209 ("three- and four-player group shots" give way to
  close-ups); Katz pp. 197-198 for three.
- **fix:** "Scene n (five on stage) cuts to the five-shot for {speaker: <D>, nth: 1}: event_change {shot: k} to <D>'s
  close-up."
- **test:** A five-person panel fixture cut only on group shots.

#### SW-24 — In a question-and-answer exchange, Speaker 2 is the picture
- **statement:** Through a question-and-answer exchange Speaker 2's close shots carry most of the picture, varied between medium and
  extreme close. Speaker 1 is seen at the opening, the closing, Speaker 1's questions and an occasional reaction.
- **source:**
  - Zettl p. 421 (15.16): "INTERVIEW: Favor guest with CU's and XCU's."
  - Zettl p. 422: "the key visualization should be a closeup of the guest's face"; "[Speaker 1] simply is not important in this
    interview".
  - Zettl p. 426: "an occasional reaction shot of the host".
  - Grindstaff p. 4: "The camera was tight on the first guest".
  - Conflicts: C-1 (Zettl's one-camera case cuts on no speaker change).
- **scope:** scene
- **tier:** advise → check when measured. No source gives the share.
- **params:** `speaker_share_min` = pending — first value from the measured recording (§11.6).
- **fix:** "Scene n shows <lead> for 60 % of its picture; <speaker>'s close shots should carry it (the switcher's cut;
  hand shots: event_change {shot: k} to <speaker>)."
- **test:** A question-and-answer exchange fixture where lead speaker singles cover most of the picture gets the hint.

#### SW-25 — The close: the two-shot, Speaker 1 to camera
- **statement:** The programme's last shot is the two-shot (or the wide) with Speaker 1 turned to camera for Speaker 1's closing
  words.
- **source:**
  - Zettl p. 421 (15.16): "CLOSING: 2-shot of host and guest. Host faces camera and closes show."
  - Zettl p. 423 (15.17): "Zoom back to 2-shot".
  - Katz p. 205: a late wide shot "might serve as … the final shot".
  - Holman p. 149: an ending signified pictorially by moving "up to an extreme wideshot".
- **scope:** scene (the last scene)
- **tier:** check. The last shot's kind and the last line's addressee.
- **params:** none
- **fix:** "The scene ends on <speaker>'s close-up: shot_add the two-shot for {speaker: <lead>, nth: last}."
- **test:** A fixture whose last shot is a speaker close-up.

#### SW-26 — Move in; return wide only as a pause or the end
- **statement:** A scene's cutting moves from the wide toward closer shots. A return to the full wide mid-scene is a
  deliberate pause (or a re-establishing shot after confusion).
- **source:**
  - Katz p. 129: "If the long shot is used with these two tighter framings, the editing pattern invariably moves in
    close and does not return to the full shot."
  - Katz p. 205: a late wide as "a dramatic pause in the middle of the scene".
  - Holman p. 36: as the scene progresses, "more and more use is made of close-ups, helping to build the tension and
    intimacy".
  - R49 §1.4 (re-establishing shot, web).
- **scope:** scene
- **tier:** advise. Katz, for Katz's own part, allows the pause.
- **params:** none
- **fix:** "Scene n returns to the wide three times; keep one as a pause (event_remove {shot: k})."
- **test:** A fixture alternating wide and close every line gets the hint.

#### SW-27 — Transitions: cuts within a scene
- **statement:**
  - Within a scene every transition is a cut.
  - The programme fades in at its start and goes to black at its end.
  - Dissolves and wipes are used sparingly and never within an exchange.
  - Going to black before a break is optional and not overused.
- **source:**
  - Zettl p. 255: the cut "is the most common and least obtrusive transition device".
  - Zettl pp. 256-257, the dissolve: "Don't overuse them; they create no rhythmic beat".
  - Zettl p. 258: "start each program by fading in"; "You should end every program by taking it to black"; "Be careful
    not to go to black too often".
  - Zettl p. 259, the wipe: "Use it sparingly".
- **scope:** shot
- **tier:** check. The transition is a field.
- **params:** none
- **fix:** "{shot: k} dissolves inside the exchange: event_change its transition to a cut."
- **test:** A dissolve between two singles of one exchange.

#### SW-28 — The insert for a thing shown
- **statement:** When someone shows an object the line is about (a book, a photo, a bottle), an insert close-up of it
  may be cut in. The other camera does not duplicate it.
- **source:**
  - Zettl p. 255: "the guest holds up the book [Speaker 2] has written … you cut to a closeup".
  - Zettl p. 455: "One, get a closeup of the book".
  - Zettl p. 194: the other camera goes "to another shot that does not needlessly duplicate camera 1's closeup".
  - Katz p. 359: an insert is "Usually a close-up showing an important detail of a scene".
- **scope:** shot
- **tier:** advise. Whether a line shows an object is a reading.
- **params:** none
- **fix:** "{speaker: <A>, nth: n} holds up the bottle; shot_add an insert of it inside the line."
- **test:** A line "Look at this bottle!" with no insert gets the hint.

#### SW-29 — No single of someone who is not there
- **statement:** A single, OTS or reaction names only a person on stage (or in the house) at that time.
- **source:** Blueprint §11.3: "a single of someone not on stage: refused with the rule". Hub consistency; no book.
- **scope:** shot
- **tier:** check
- **params:** none
- **fix:** "{shot: k} is a single of <X>, who is not in scene n: event_change it to <someone on stage> or event_remove
  it."
- **test:** A single of a removed cast member (cf. round 1 audit: `frame.py:99-109`, a removed member's name kept in
  camera words).

#### SW-30 — The same exchange always cuts the same way
- **statement:** The switcher is deterministic. The same exchange and staging give the same shots, with ties broken by
  a seed.
- **source:** Blueprint §11.3: "the same exchange always cuts the same way (a seeded tie-break), so the sketches and
  the lock stay stable". Hub design; no book.
- **scope:** scene
- **tier:** check
- **params:** none
- **fix:** none (code).
- **test:** The Character 1 fixture cut twice must give identical shot lists.

## 4. SOUND / MIX — levels, peaks, masking, overlaps, crowd, ducking, dead air (Holman; EBU R 128 via `takejudge.py`)

Code measures and mixes (§12). The mix tools answer the fix lines. Holman's chapters cited: 2 (psychoacoustics,
pp. 25-37), 7 (production mixing, pp. 117-118), 10 (sound design, pp. 145-151), 11 (editing, pp. 157-167), 12
(mixing, pp. 171-185). Holman gives no LUFS/LKFS targets. Holman names ATSC RP-A/85 only in a footnote with no value
(p. 196, n. 5).

#### MX-1 — Every line sits at the dialogue anchor
- **statement:** Each line take's speech is gained so its integrated loudness equals `dialogue_lufs`.
- **source:**
  - Blueprint §12.2.3.
  - `takejudge.PARAMS` (`dialogue_lufs` −23.0, `hub/modules/director/takejudge.py:17`), taken from EBU R 128 as quoted "the Programme Loudness
    Level shall be normalised to a Target Level of −23.0 LUFS".
  - EBU R 128 measures a programme "without emphasis on specific foreground elements such as speech". The anchor
    on speech is therefore the Hub's choice, not the standard's.
- **scope:** mix
- **tier:** check. Measured by ffmpeg `ebur128`.
- **params:** `dialogue_lufs` = −23.0 LUFS — EBU R 128 via `takejudge.py`. measured: pending (whether `ebur128`'s
  gated loudness of one line matches the ear).
- **fix:** none to the Director. The gain is set on arrival. The change by ear: "take_change {id: <line>, gain_db}".
- **test:** A take measured at −30 LUFS left at gain 0.

#### MX-2 — A take far off level is flagged
- **statement:** A take whose speech loudness, before gain, is more than `level_tolerance_db` from the anchor is flagged
  "level". It is never retaken for it.
- **source:** Blueprint §12.2.3. `takejudge.PARAMS` (`level_tolerance_db` 10.0, `takejudge.py:20`).
- **scope:** mix
- **tier:** check
- **params:** `level_tolerance_db` = 10.0 dB — `takejudge.py` (engineering value, no book). measured: pending (how
  often the voices are flagged).
- **fix:** "l3's take is −35.2 LUFS: take_change {id: l3, redo}."
- **test:** A fixture take at −35 LUFS not flagged.

#### MX-3 — No peak over full scale after gain; the programme under −1 dBTP
- **statement:** A take whose true peak plus its gain would pass `clip_dbtp` is flagged. The finished track's true
  peak never exceeds `true_peak_dbtp`.
- **source:**
  - EBU R 128 as quoted "The True Peak Level of a programme shall not exceed −1 dBTP (dB True Peak) during
    production".
  - `takejudge.PARAMS` (`clip_dbtp` 0.0 = full scale; `true_peak_dbtp` −1.0; `takejudge.py:18-19`).
  - The mix (limiter last, measured at 4× oversampling; `hub/modules/director/mix.py`).
  - Holman p. 177: limiting to "control the highest level signals".
- **scope:** mix
- **tier:** check
- **params:** `true_peak_dbtp` = −1.0 dBTP — EBU R 128 via `takejudge.py`. `clip_dbtp` = 0.0 dBTP — `takejudge.py` (full
  scale).
- **fix:** "l4 peaks at +1.3 dBTP after +9.0 dB: take_change {id: l4, gain_db: <lower>} or {redo}."
- **test:** A take at −30 LUFS with a −2 dBFS peak gained by +7 dB.

#### MX-4 — The track meets its loudness target
- **statement:** The rendered track's integrated loudness equals the mix target.
- **source:**
  - Blueprint §12.5 ("the integrated loudness at the target") and §12.2.
  - The mix (`target {lufs: −23.0, true_peak_dbtp: −1.0, source: "EBU R 128 (2020)"}`; `loudnorm` once, then the
    limiter).
  - ATSC A/85 (named by blueprint §12.2 and by Holman p. 196 n. 5): its value is **source pending**. Neither R49 nor
    the Hub's code quotes it.
- **scope:** mix
- **tier:** check, measured on the render (9c).
- **params:**
  - `target_lufs` = −23.0 LUFS — EBU R 128 via `takejudge.py` and `mix.py`.
  - `target_tolerance_lu` = 1 LU — the mixer test's bound (`I` −23 ± 1 LUFS; a test bound, not a standard).
  - ATSC value: source pending.
- **fix:** none to the Director (the loudness pass sets it). A failure is a Hub defect.
- **test:** A mix whose `loudnorm` is skipped and that measures −18 LUFS.

#### MX-5 — Cues sit under the dialogue
- **statement:** A cue take is gained to its kind's level: effect and reaction 4 dB under the anchor, music 10 dB
  under, the room 22 dB under.
- **source:**
  - `takejudge.PARAMS` (`cue_lufs`: effect −27, reaction −27, music −33, room −45; `takejudge.py:21-26`). Its reasons:
    events between lines, 4 dB under; music 10 dB under, the engine mixer's own ducking depth (R42 §2); the room heard
    only in the gaps.
  - Holman p. 173: Foley "turned down relative to the dialog element to assume its proper relationship in the mix".
- **scope:** mix
- **tier:** check
- **params:**
  - `cue_lufs.effect` = −27 LUFS, `cue_lufs.reaction` = −27 LUFS, `cue_lufs.music` = −33 LUFS, `cue_lufs.room` = −45
    LUFS — `takejudge.py` (engineering values; a listen first).
  - measured: pending.
- **fix:** "The applause c2 is louder than the lines around it: lane_change {lane: reaction, gain_db: −6}."
- **test:** A reaction take left at −15 LUFS.

#### MX-6 — No line masked by the bed under it
- **statement:** A line's speech is not more than `mask_db` below the sum of the beds (reaction, effect, music) under
  it.
- **source:**
  - Holman pp. 28-29 (frequency and temporal masking: "Louder sounds cover up softer ones").
  - Holman p. 149: designers leave "'little holes' for dialog … because of the space carved in the sound effects for
    them".
  - Holman p. 175: music peaks meeting "the minimum level of the dialog and the dialog is obscured".
  - Holman p. 37 gives the edge of intelligibility in a lab: speech understood "some 16 dB underneath noise" with the
    talker's video. This is a limit, not a mix target.
  - Blueprint §12.6.
- **scope:** mix
- **tier:** advise → check when measured. Blueprint §12.6 makes it a check; no source gives the number.
- **params:** `mask_db` = pending — no source gives a mix value (Holman p. 37's 16 dB is the lab edge).
- **fix:** "Shot 3: Character 1's line sits 9 dB under the applause: lane_change {lane: reaction, gain_db: −9}, or clip_move
  {id: c2, at_ms: <after l4's end>}." (blueprint §12.6's own example)
- **test:** An applause clip at −15 LUFS laid over a −23 LUFS line gets the flag.

#### MX-7 — Every line is heard in the mix
- **statement:** On the rendered track, the words judge hears each line at its placed time.
- **source:**
  - Holman p. 149: "convention demands that all dialog be intelligible, even when the director says the line is of no
    importance".
  - Holman p. 171: "Even throwaway lines … will get audience members to … ask: 'What did [the speaker] say?'"
  - Blueprint §12.5: "each line heard at its time".
- **scope:** mix
- **tier:** check
- **params:** `mix_words_bar` = 0.80 — `scene_words_bar` (`hub/settings.py:45-54`; the room under the voice; Whisper's
  miss rate on it not known). measured: pending.
- **fix:** "l3 is heard 55 % in the mix (under c2): lane_change {lane: reaction, gain_db: −6}, or clip_move {id: c2}."
- **test:** A mix where a line is buried under a 0 dB music clip.

#### MX-8 — Overlaps only where written as an interruption
- **statement:** Two lines sound at once only when the Director wrote the second as an interruption. Any other overlap
  in the placed mix is flagged.
- **source:**
  - Holman p. 117: "Overlapping dialog from various actors speaking at the same time causes one of the most serious
    potential problems editorially".
  - Holman p. 160: replacing an overlapped line results in "'doubling' … usually painfully audible".
  - Grindstaff p. 12: speakers coached to "butt in, interrupt".
  - Zettl pp. 432-433: an interruption written with "--" and a parenthetical (an example, no rule).
  - Blueprint §12.3, §12.6.
- **scope:** mix
- **tier:** check. Placed times on the lanes.
- **params:** none. Overlap is not writable today (A.3 refuses it).
- **fix:** "l4 starts under l3 though it is not an interruption: clip_move {id: l4, at_ms: <l3's end + turn>}."
- **test:** Two lines placed 400 ms overlapping with no interruption mark.

#### MX-9 — Lanes by speaker and by kind
- **statement:** Each speaker has a dialogue lane, and the audience reaction, effects, music and room are each
  their own lane, so each can be levelled alone.
- **source:**
  - Holman p. 159: "Some mixers, however, prefer different characters to be split out to separate tracks … the ability
    to process each actor's voice separately".
  - Holman p. 166: the multi-camera comedy breakdown "Dialog, Music, Effects, Audience reaction (laughs)".
  - Blueprint §12.3. The mix's lanes (`hub/modules/director/place.py`).
- **scope:** mix
- **tier:** check. The lane list.
- **params:** none
- **fix:** none (code builds the lanes).
- **test:** A mix with two speakers on one dialogue lane.

#### MX-10 — A reaction is never cut dead
- **statement:** An applause or laughter clip keeps its natural decay. Its out-point is not before the measured decay
  end, and its fade-out is at most half the clip and at most 1 s.
- **source:**
  - Blueprint §12.2.4 and §12.6 (a track that sounds like a soundboard).
  - `takemeasure.py` (`decay_ms`: the end minus the last moment the momentary loudness is within 10 dB of its loudest;
    `hub/worker/adapters/takemeasure.py:15-17`, `DECAY_DB`).
  - `place.fades` (a reaction fades 100 ms in; `hub/modules/director/place.py:137-143`).
- **scope:** mix
- **tier:** check
- **params:**
  - `reaction_fade_in_ms` = 100 ms — `place.fades`.
  - `reaction_fade_out_ms` = min(1000, kept/2) ms.
  - `decay_window_db` = 10 dB.
  - All engineering values, no book. measured: pending.
- **fix:** "c2 (applause) is cut 600 ms before its decay ends: take_change {id: c2, out_ms: <its decay end>}."
- **test:** A reaction clip whose `out_ms` lies 600 ms before its `decay_ms` end.

#### MX-11 — The beds duck under the dialogue
- **statement:** The reaction, effect and music lanes are ducked by the dialogue sum. A music clip under a line with no
  ducking is flagged.
- **source:**
  - Holman p. 175: a compressor keeps music "faded under a dialog source" at an even level; "the mixer should process
    the background sound first rather than the foreground sound"; compressing the combined track gives "pumping".
  - Blueprint §12.3, §12.5, §12.6.
  - The join's `sidechaincompress` (the values below; `hub/worker/joincmd.py`).
- **scope:** mix
- **tier:** check
- **params:**
  - `duck_threshold` = 0.05 and `duck_ratio` = 6 — `joincmd.DUCK` (`hub/worker/joincmd.py:159`).
  - `duck_attack_ms` = 200 ms and `duck_release_ms` = 600 ms — R42 §2, the engine mixer.
  - `duck_min_db` = 3 dB — the mixer test's bound (the music stem is at least 3 dB lower inside a line).
  - Holman p. 175 gives a compressor's typical starting values as attack 80 ms and release 0.5 s (C-11).
  - measured: pending (by ear).
- **fix:** "Music m1 is not ducked under l2: lane_change {lane: music, duck: true}."
- **test:** A music lane with `duck` false under a line.

#### MX-12 — Dead air is flagged
- **statement:** A gap with no line longer than `dead_air_ms` between two lines of one exchange is flagged, never
  silently filled.
- **source:**
  - Blueprint §12.4.
  - Holman p. 160: "Black equals silence in this example, and cutting to it would be just as obvious as missing the
    picture—so with sound."
  - Round 1 F8b: about 15 s of the 31.6 s is dead air (holes held by `auto` poses, 3128-10652 and 18356-25732).
- **scope:** exchange
- **tier:** advise. Blueprint §12.4 says advise. It becomes a check when the number is measured.
- **params:**
  - `dead_air_ms` = pending — no source.
  - Context: the normal turn gap is `TURN_MS` 180 ms (`layout.py`; the engine's dialogue pause 0.18 s, blueprint §1);
    cross-language turn gaps lie "within a range of 250 ms" of their mean (R49 §5.8, Stivers et al., web).
- **fix:** "Scene 1 has 7.5 s of silence after {speaker: Character 2, nth: 1}: event_move {speaker: Character 2, nth: 2} to its
  end, or line_add a line there."
- **test:** Round 1's script file (`web/tests/e2e/fixtures/script-2.json`) with its 7.5 s hole.

#### MX-13 — Room tone runs under the whole scene
- **statement:** The room lane carries one continuous presence under the whole track, so the gaps between lines are
  never digital silence.
- **source:**
  - Holman p. 160: "To smooth dialog tracks, it is essential to have a recording to fill in between the gaps".
  - Holman p. 29: a parallel ambience track masks background changes and gives "smooth-sounding edits and good
    continuity".
  - Holman p. 32: record "room tone" "as a continuous background presence under the scene".
  - Holman p. 148: ambience's "constancy across picture cuts provides an anchor".
  - Blueprint §12.3. The room clip looped to the track's length `L` (`place.py:132`, `mix.py:67`).
- **scope:** mix
- **tier:** check
- **params:** `room_lufs` = −45 LUFS — `takejudge.py` (see MX-5).
- **fix:** none (code makes and loops the room). A missing room take is answered by `script_track`.
- **test:** A mix with no room lane.

#### MX-14 — The crowd carries no words
- **statement:** Audience and room takes carry no discrete intelligible speech. Words heard in a cue take are flagged.
- **source:**
  - Holman p. 118: a walla track is "a track containing no discrete audible speech but providing the right sort of
    level of action".
  - The design rule: no crowd chatter in prompts; speech outside lines is garble.
- **scope:** mix
- **tier:** check. The words judge does not run on cue takes today (`heard: null`), so this needs it run on
  them.
- **params:** `cue_words_max` = 0 words — Holman p. 118 ("no discrete audible speech").
- **fix:** "c2 (laughter) contains words ('oh my god'): take_change {id: c2, redo}."
- **test:** A laughter take in which Whisper hears a phrase.

#### MX-15 — Dialogue centred; off-screen lines may be panned
- **statement:** Dialogue is placed centre, not panned shot by shot. Off-screen lines may be panned to the side.
- **source:** Holman p. 37: "The standard is now to place most dialog in the center channel, despite its not matching
  the picture in each shot"; "Off-screen lines are routinely panned to far left or right". Holman p. 36 (the jump at
  the cut).
- **scope:** mix
- **tier:** advise. `pan` is not built (§12.7 later).
- **params:** none
- **fix:** none until `pan` exists.
- **test:** When `pan` lands: an on-screen line panned per shot gets the hint.

#### MX-16 — Compress the sources, not the programme; the limiter last and light
- **statement:** Dynamics act per lane (the beds' ducking) and the limiter acts last. Limiting beyond about 5-6 dB of
  gain reduction, or dialogue compression beyond 6-8 dB, gets a hint.
- **source:**
  - Holman p. 175: "It is thus best to compress each individual source alone and then to combine sources, rather than
    to try to compress the entire program"; on dialogue, "small amounts of compression, on the order of 6 to 8 dB of
    maximum gain reduction".
  - Holman p. 177: "5 to 6 dB of limiting can be practically inaudible".
  - `loudnorm` then `alimiter`, last.
- **scope:** mix
- **tier:** advise. The limiter's gain reduction is not measured today.
- **params:** `limit_gr_max_db` = 6 dB — Holman p. 177. `dialog_comp_max_db` = 8 dB — Holman p. 175.
- **fix:** "The limiter takes 9 dB off the track's peaks around c2: lane_change {lane: reaction, gain_db: −4}."
- **test:** A mix with one +6 dB applause clip that drives 9 dB of limiting gets the hint.

#### MX-17 — Lines follow each other at the turn gap
- **statement:** A line that followed the one before it is placed at that line's measured speech end plus `turn_ms`,
  unless the Director made a pause or an interruption.
- **source:**
  - Blueprint §12.4 (A.4's rule on measured times).
  - The placement (`layout.TURN_MS`, `hub/modules/director/place.py:86`).
  - The engine's dialogue pause 0.18 s (blueprint §1).
  - R49 §5.8 (Stivers et al., web): turn-taking minimises silence between turns.
- **scope:** exchange
- **tier:** check. Placement arithmetic.
- **params:** `turn_ms` = 180 ms — `layout.py` / engine `dialogue.py` (blueprint §1); no book. measured: pending.
- **fix:** none (code places). A made pause is the Director's: "event_move {speaker, nth}".
- **test:** A short take that leaves the next line at its planned time instead of being pulled back.

#### MX-18 — Each take trimmed to its speech
- **statement:** A take's clip runs from its measured speech start to its measured speech end. Lead and tail silence
  and stray sound (a cough, a garbled first second) are outside it, and are cut, not re-rendered.
- **source:**
  - Blueprint §12.2.2.
  - `takemeasure.py` (sound regions by `silencedetect` at −45 dB and 0.15 s; loudness only over at least 400 ms, ebur128's
    momentary block).
  - Holman p. 160: dialog editors cut out noises between words.
- **scope:** mix
- **tier:** check
- **params:** `silence_db` = −45 dB and `silence_min_s` = 0.15 s; `loudness_min_ms` = 400 ms
  (ebur128's block). All engineering values.
- **fix:** "l1's take starts with 1.1 s of garble: take_change {id: l1, in_ms: 1100}."
- **test:** The fixture take with a garbled first second kept inside the clip.

#### MX-19 — The voice's energy holds from take to take
- **statement:** A line's take keeps its speaker's energy, pace and emotion consistent with the speaker's other lines in the
  scene, unless the line itself changes them.
- **source:** Holman p. 32: "Keeping the energy level correct from take to take, and not slipping, marks good direction
  and acting." Holman p. 118: actors "have got to 'speak up' over the background noise that isn't there!"
- **scope:** line
- **tier:** advise. No measure of energy is built.
- **params:** none
- **fix:** "l5 sounds flat beside Character 2's other lines: take_change {id: l5, redo}, or event_change its emotion."
- **test:** Not testable until an energy measure exists. Recorded as a gap (G-12).

## 5. CONTROL / JUDGES — the render's bars (blueprint §17.2-§17.4, §17.8)

The bars are law (§17.8). The first values are the Hub's settings (`hub/settings.py:45-54`),
not yet tuned from measured numbers. A flag names the bar and the number.

#### CT-1 — The face is the sheet's
- **statement:** In a shot's render, each character's face matches that character's sheet. The median similarity must reach
  `clip_face_bar`, and the face must not be lost.
- **source:**
  - The H3 notes' same-person line 0.28.
  - `ShotJudge` (the median, not the minimum: a face that starts low and holds passes;
    `hub/modules/generate_image/judgeshot.py:115-118`).
  - Blueprint §17.4, §17.8.
- **scope:** render
- **tier:** check
- **params:** `clip_face_bar` = 0.30 — `hub/settings.py:45-54`. measured: pending (the sheets).
- **fix:** none to the Director. The Hub re-renders up to `scene_takes_max`, then flags "<name>'s face 0.21, bar 0.30".
- **test:** A take whose face median reads 0.21.

#### CT-2 — The mouth moves with the words
- **statement:** The speaker's mouth movement falls inside the speaker's speech. `lips` must reach `clip_lips_bar`, and the
  mouth must not be still while the speaker speaks. The control draws the mouth only inside the speaker's measured line windows.
- **source:**
  - The mouth judge's `lips` (`hub/worker/adapters/mouth.py:75-79`): at 0.50 the mouth's movement is unrelated to the
    speech.
  - Blueprint §17.2: "zero outside [the speaker's] measured line windows".
- **scope:** render
- **tier:** check
- **params:** `clip_lips_bar` = 0.60 — `hub/settings.py:45-54`. measured: pending.
- **fix:** none to the Director (re-render, then flag "Character 2's mouth 0.38, bar 0.60").
- **test:** A take with `lips` 0.38.

#### CT-3 — No one else's mouth moves
- **statement:** In a shot, only the person whose line is sounding moves a mouth. A listener or extra with a moving
  mouth (lip flap) fails.
- **source:**
  - Blueprint §17.2: "No one else's mouth moves (C4's mouth judge, kept)".
  - Holman p. 32: lip flap is "a defect in which we see but do not hear a person speaking". Holman p. 118: it "shows
    very poor technique".
- **scope:** render
- **tier:** advise → check when measured. The mouth judge scores the speaker only; no bar for the others
  exists.
- **params:** `others_lips_max` = pending — no source.
- **fix:** none to the Director (re-render).
- **test:** A two-shot render where the listener's mouth moves through the speaker's line gets the flag once the bar
  exists.

#### CT-4 — The shot is the size it was written
- **statement:** A character's face height, as a share of the frame (median), lies in the band its shot's framing
  names.
- **source:**
  - The frame judge: the bands close-up, medium and wide; `frame_close`, `frame_wide`.
  - The frame counts toward the take when the shot names a band (C-12).
  - Blueprint §17.4 ("framing against the control").
- **scope:** render
- **tier:** check
- **params:** `frame_close` = 0.30, `frame_wide` = 0.12 (face height share) — `hub/settings.py:45-54`. measured: pending.
- **fix:** none to the Director (re-render, then flag "Character 2's face is 0.09 of the height; the shot asked for a
  close-up").
- **test:** A close-up take whose face median is 0.09 of the height.

#### CT-5 — The shot's words are heard
- **statement:** Whisper hears the shot's lines in its clip's soundtrack at `scene_words_bar` or above.
- **source:** `scene_words_bar` (`hub/settings.py:45-54`; a clip's soundtrack: the room under the voice). Blueprint §17.4.
- **scope:** render
- **tier:** check
- **params:** `scene_words_bar` = 0.80 — `hub/settings.py:45-54` (Whisper's miss rate on it not known). measured: pending.
- **fix:** none to the Director (re-render, then flag "heard 62 %, bar 80 %").
- **test:** A clip with 62 % of its words heard.

#### CT-6 — A line's take is heard; three tries
- **statement:** A line's take is heard at `speech_words_bar` or above. Under it, the line is taken again up to
  `takes_max`, then flagged.
- **source:** The speech route (a clean WAV). `speech_takes_max` 3, `speech_words_bar` 0.90 (`hub/settings.py:45-54`). Blueprint §12.2.1.
  `takemeasure.py`.
- **scope:** line
- **tier:** check
- **params:** `speech_words_bar` = 0.90. `takes_max` = 3 — blueprint §12.2 / `hub/settings.py:45-54`.
  measured: pending.
- **fix:** none to the Director. After three, the flag says why: "take_change {id, redo}" is the chat message's.
- **test:** A line whose three takes are heard at 70 %, not flagged.

#### CT-7 — No speech that is not the line
- **statement:** A take's speech outside its heard words (the speech spans before the first heard word and after the
  last) totals no more than `scene_unscripted_seconds`.
- **source:** `ShotJudge` ("<speaker> makes <x.x> s of speech that is not the line"; `judgeshot.py:9`). Blueprint §12.2.1
  (`extra_speech`).
- **scope:** render
- **tier:** check
- **params:** `scene_unscripted_seconds` = 2.5 s — `hub/settings.py:45-54` (not measured on the server;
  range 0.5-10, `hub/settingsmods.py:24`).
- **fix:** none to the Director (re-render, then flag).
- **test:** A fixture with words at 5.0-9.6 s and speech spans 0.2-9.8 s.

#### CT-8 — A shot's takes are bounded
- **statement:** A shot is rendered at most `scene_takes_max` times, within `scene_retake_minutes` of measured render
  time. The best take is kept and every take is kept.
- **source:** `ShotJudge` and `presstakes` (`judgeshot.py:1-7`). Blueprint §17.4 ("up to the rulebook's `takes_max`, then flagged with
  why").
- **scope:** render
- **tier:** check
- **params:** `scene_takes_max` = 2 (1-4) and `scene_retake_minutes` = 15 min (0-120) —
  `hub/settings.py:45-54`, ranges `hub/settingsmods.py:22`.
- **fix:** none (code).
- **test:** A shot failing every bar that renders a third take.

#### CT-9 — No speech in a shot's words outside its lines
- **statement:** A shot's action and camera words hold no speech verb. What someone says goes in lines only.
- **source:** A word list (`speak`, `talking`, `chatter`, `introduces <self>`, `announces`, `shouts`, `sings` …;
  a form name containing a speech word allowed): "what [the character] says goes in lines only, and the action says what [the character] does with [the character's] body".
- **scope:** shot
- **tier:** check. A word list.
- **params:** none
- **fix:** "{shot: n}'s action says someone speaks ('begins to speak'): event_change it to what the character does with the character's body;
  what the character says goes in lines only."
- **test:** A shot whose camera words read "Character 1 begins to speak".

#### CT-10 — The render unit is one control window
- **statement:** A shot renders as one job of at most one control window. A longer stretch is split into shots.
- **source:** Blueprint §17 intro and §17.6 (R48 §7: 362-frame control windows, 17n+5 frames; "15.08 s; A.4's cap
  exists for this reason"). `layout.SHOT_MAX_MS` (blueprint §10).
- **scope:** render
- **tier:** check
- **params:** `shot_max_ms` = 15080 ms — blueprint §17.6 / R48 §7 (engine fact). `window_frames` = 362 — R48 §7.
- **fix:** "{shot: n} runs 18 s: shot_add a second shot of the same camera at a sentence end inside it."
- **test:** An 18 s shot.

#### CT-11 — One aspect for the script
- **statement:** Every picture of a script (plates, sketches, control canvas, renders) has the aspect of its set. The
  aspect is the set record's `format`.
- **source:** Blueprint §18.1 (one aspect per script, from its set; sketch size 448×336 at 4:3).
- **scope:** context
- **tier:** check
- **params:** `aspect` = 4:3 — blueprint §18.1.
- **fix:** none (set by the set record).
- **test:** A 16:9 sketch requested for a 4:3 set.

#### CT-12 — A flag names its bar and its number
- **statement:** Every "flagged" names the rule, the bar and the measured value.
- **source:** Blueprint §17.8: "a 'flagged with why' always names the bar and the number". Blueprint §11.2: a refusal
  carries `rule: {id, source}`.
- **scope:** render
- **tier:** check. The contract test checks the format.
- **params:** none
- **fix:** none (code).
- **test:** A flag string without its number.

---

## 6. Conflicts: where the sources disagree, and the decision for this form

The production is a multi-camera production with a live audience, taped as if live and switched by a director. The
decision rule: **for live switching, the television sources (Zettl 1976, Stasheff & Bretz 1976 via R49) win over the
film sources (Murch, Katz, Bordwell).**
- **They describe this production method.** They write for the studio of two to four cameras cut at the instant by a
  technical director on the director's calls (Zettl p. 259: "The decision for a cut and the execution of the cut are
  virtually simultaneous").
- **The film sources describe postproduction.** An editor chooses each out-point from all the footage (Murch,
  "Dragnet": Murch marks it "in real time" on the editing machine).
- **Zettl draws the line too.** "In instantaneous editing you usually try to reflect the action and feeling of the
  actual event rather than constructing a new one, as in postproduction editing" (p. 276). Intricate complexity
  editing belongs in postproduction (p. 276).
- **Murch limits Murch's own figures.** Murch's cut rates are "in an American film" ("Dragnet").

Grindstaff wins on what the form wants (the emotional peak, the order of speakers, the audience). Holman wins on sound,
except where the repo has a measured or standardised number.

**C-1. Cutting on a new speaker.**
- *Murch, "Dragnet":* cutting to each new speaker is "a shallow simplicity that doesn't reflect the grammar of complex
  exchanges". One turns to the listener "while that person is still talking".
- *The Open WebUI block* (`system-prompt-video-paragraph.md:73`) teaches the same: "not each time the next
  one starts to talk".
- *S&B p. 47 (R49 §2.7):* "we cut to the second person just as [that person] begins to reply". *Zettl p. 273:* "In an interview,
  the cut occurs generally at the end of a question or answer". *Zettl pp. 434-435:* a cut to each new speaker's
  closeup in the panel.
- *Zettl's one-camera question-and-answer exchange (p. 422)* makes no cut at all on a change of speaker.

**Decision:** cut to the new speaker (SW-2, check). Murch's branch points survive as Zettl's own exceptions: the
reaction during a phrase (SW-4, SW-6), the cut on action mid-speech (SW-21), the two-shot held through a run of short
lines (SW-8). The one-camera exception is replaced by the three-camera plan (ST-15) and its speaker emphasis (SW-24).
The block's line 73 is to be corrected at Step 13, as the round-1 audit recorded.

**C-2. How late the cut on the new speaker comes.**
- Blueprint §11.3 rule 2 says "slightly late (Stasheff & Bretz, R49 §2.7)". S&B's sentence says "just as [that person] begins".
  No source read gives a delay.
- Zettl's only figure (p. 248) is a director calling the take "a second or two" early to cover the T.D.'s reaction
  time. The Hub cuts without that delay.

**Decision:** `cut_late_ms` = 0 ms, at the measured speech start (SW-2). The property test "a speaker change cut within
`params.cut_late_ms`" uses it. The measured recording gives it.

**C-3. How a scene opens.**
- *Open wide:* Katz p. 358; Holman p. 36 ("picture editors almost always start with the master shot"); R49 §1.4-1.5.
- *Open on Speaker 1's close-up to camera, then the two-shot:* Zettl p. 421.
- *A cold open "tight on the first guest":* Grindstaff p. 4.
- *Withholding the full view, then a late wide:* Katz pp. 202, 205.

**Decision:** each scene opens on the shot that shows who is where, the wide or the two-shot (Zettl's two-shot "reveals
the basic relationship", p. 422). The programme's first scene may put Speaker 1's close-up to camera first (Zettl's
question-and-answer exchange opening) (SW-1, check). The cold open and the withheld view are not offered. No source states them as a rule
for this form.

**C-4. Crossing the line.**
- *For the rule:* Zettl pp. 270-274, 469; S&B p. 51; Katz p. 130.
- *Against it:* Katz calls its assumptions "overstated" (p. 142): "If it works, use it" (p. 187). Murch ranks planarity
  and 3-D continuity last of Murch's six, to be given up first ("The Rule of Six"). Murch also notes that a multi-camera
  comedy series' spatial correctness "absolutely does not prevent bad cuts" (note 9).
- *TV wins:* in switching there is no later pass to repair a flip. Zettl's lead speaker-at-one-side plan exists to keep screen
  positions (p. 271).

**Decision:** SW-15 and ST-3 are checks; the reverse to the house is bridged by a neutral shot or cutaway.

**C-5. Scale jumps.**
- *Katz p. 121:* "Today … audiences easily accept extreme changes in scale".
- *Zettl pp. 269-270:* no cut from an extreme long shot to an extreme closeup; go through a medium shot first. Viewers
  "may not be able to recognize exactly whose closeup it is".
- *Murch ("Why Do Cuts Work?")* objects to the opposite case, a change too small.

**Decision:** Zettl (SW-17, check), and Murch's case is carried by SW-16.

**C-6. Shot length, cut rate and reaction frequency.**
- *Shot length and cut rate:* Murch gives "six cuts per minute or less" for "normal" American film dialogue (an average
  of 10 s or more). Bordwell gives 2-3 s per shot (R49 §3.2). Late-century multi-camera comedy series run medians of 2.8-4.0 s
  (R49 §3.3). Zettl gives no number and says "Don't be afraid to stay on one camera" (p. 270). No source gives a figure for
  this kind of multi-camera production (R49 §6).
- *Reaction frequency:* S&B p. 40 and Zettl p. 426 say "sparingly" and "occasional". Katz p. 227 says "we learn as much
  from the reaction". S&B p. 46 says the listener is "often more interesting and telling" in a question-and-answer exchange. Grindstaff
  pp. 127-129 shows audience reactions sought and even taped afterwards.

**Decision:** nothing numeric is decided from books.
- SW-20 holds R49 §3.3's range as the published stand-in, as blueprint §11.6 says, at tier `advise` until the
  recording is measured.
- Cast reactions are sparing (SW-5, advise until measured). Audience reactions fire on cues and WR-5 marks (SW-11,
  SW-13): the form's own practice (Grindstaff), not the film rule.

**C-7. What a reveal or an emotional peak cuts to.**
- Blueprint §11.3 rule 5: "returns to the wide, then to the reaction of the one it lands on".
- *Grindstaff p. 250:* "hence the importance of slow motion and the close-up". *Zettl pp. 274-275:* the closeup
  intensifies internal action. *Zettl p. 255:* a cut to a longer shot "reduces the event impact".
- The wide for an entrance has a source (R49 §4.7, web; Katz p. 155).

**Decision:** an entrance goes wide (SW-9). A reveal or an emotional peak lands on the close shot of the one it lands on
(SW-10). The blueprint's "returns to the wide" holds for entrances only. This is a decision for the rulebook; the
blueprint's wording is the assistant's to reconcile.

**C-8. Three players: where Speaker 1 sits.**
- *Katz p. 198:* the A pattern (the third player between the others) is "as might be expected in an interview".
- *Zettl p. 271:* lead speaker "not in the middle, but to one side of the guests". That is Katz's own L arrangement (p. 202).

**Decision:** Zettl (ST-2, check).

**C-9. Saying the feeling out loud.**
- *McKee ch. 8:* on-the-nose dialogue is a flaw (except in nonrealist genres).
- *Grindstaff:* producers want speakers to state the point first (pp. 100-101) and to show raw emotion (pp. 19-21). The
  form's speakers make "public confessions" (R49 §4.5).

**Decision:** WR-8 is `advise` only. WR-1 (action) and WR-15 (point first) are graded. A confession is allowed when it
is an act on someone.

**C-10. Do segments escalate?**
- Segments escalating toward an emotional peak: no source states it.
- *Grindstaff p. 123* states the opposite ordering rule: the most important speaker goes first. "Escalated" occurs once,
  inside a segment (p. 13). R49 §6 records this.

**Decision:** WR-17 (strongest first, advise) and WR-18 (hold a surprise, advise). No escalation rule enters the
rulebook.

**C-11. Ducking time constants.**
- *Holman p. 175:* a compressor's "typical starting value" is 80 ms attack and 0.5 s release.
- *The repo* (from the engine mixer, R42 §2): 200 ms attack, 600 ms release, threshold 0.05, ratio 6.

**Decision:** keep the built values as the first values (MX-11). They are what the mixer test proves, and they match
the engine's own mixer. Holman's are recorded beside them as the book's starting point. Listening decides.

**C-12. Does a wrong framing re-render?**
- *One rule:* the frame verdict never re-takes: a wrong size is a rewrite of the shot.
- *The Hub's judges and blueprint §17.4:* the frame counts toward the take when the shot names a band.

**Decision:** the judges and the blueprint (CT-4, check, re-render).

**C-13. The loudness standard.**
- `takejudge.py` and `mix.py` quote EBU R 128 (−23 LUFS, −1 dBTP). Blueprint §12.2 names "EBU R 128 / ATSC A/85".
- US television's standard is ATSC A/85. Its value is not quoted anywhere read here (Holman
  p. 196 n. 5 names it only).

**Decision:** −23 LUFS / −1 dBTP stand (MX-1, MX-3, MX-4). They are the only quoted text. The A/85 number is **source
pending**.

**C-14. Inserts and body parts.**
- R49 §1.13's two web sources disagree on whether an insert may show a body part.
- *Katz p. 359:* an insert is "a close-up showing an important detail". *Katz p. 228:* a close-up of hands can be a
  reaction.

**Decision:** an insert shows an object (SW-28). Hands and feet of a listener are a reaction (SW-4). Katz carries both.

## 7. Gaps: what the blueprint asks for that no source supports, and numbers to be measured

Rules the blueprint names that no source read here gives a number or a rule for. Each stays `advise` until a source or
the measurement tool (§11.6) supplies it:
- **G-1. The multi-camera production's cutting rate.** ASL, cuts per minute, and the fraction of shots under 2 s (SW-20, SW-18's
  measure). Not found in any source (R49 §6; Shot Logger has no question-and-answer programme). First value from the measurement tool (§11.6).
- **G-2. When a reaction comes.** `reaction_after_ms` (SW-4), `reaction_share_max` (SW-5), `reaction_hold_ms` (SW-13),
  audience-cut frequency (SW-11). No source gives a shot length for a reaction or a line (R49 §6). Hand labels on
  a sample.
- **G-3. The two-shot run.** `short_line_ms` and `run_min_lines` (SW-8) have no source.
- **G-4. Hold ceiling, speaker share, run of lines.** `shot_max_hold_ms` (SW-19), `speaker_share_min` (SW-24) and
  `max_run_lines` (WR-11) have no source.
- **G-5. Cut timing on a new speaker.** `cut_late_ms` (SW-2) is 0 by S&B's wording; no source measures it (C-2).
- **G-6. Mix numbers with no source.**
  - `mask_db` (MX-6) and `dead_air_ms` (MX-12): no source. Holman gives only the lab edge of intelligibility (p. 37).
  - The ATSC A/85 target: source pending (C-13).
  - `level_tolerance_db` 10 and the cue levels (MX-2, MX-5) are the specs' engineering values with no book behind
    them.
- **G-7. Camera plan for a multi-camera production with a live audience.**
  - Which camera holds Speaker 2's close-up, when the director cuts to the house, and how a lead speaker's walk into the
    audience is covered: not found in any book or web page read (R49 §6, §7.3.8).
  - ST-15's three cameras rest on Katz's triangle and a web description of multi-camera practice. One 1994 taping used
    seven (R49 §4.2).
  - The reverse set-up to the house (§16.4) has only Zettl's remote example (p. 469) and the hand microphone (p. 155).
- **G-8. Rules with no book at all (Hub design or findings from runs, sourced to the repo):**
  - ST-7 (inset and spread homes, F1);
  - ST-11's two featured members (§16.2);
  - SW-29 (no single of an absent person);
  - SW-30 (determinism);
  - the switcher's shot kinds;
  - CT-11 (4:3);
  - CT-12 (flag format).

  They are checks by design, not by a craft source.
- **G-9. The cut on the look and the pivot (SW-22).** Sourced (Katz, Zettl), but the script has no look field, so the
  rule stays advise until `addressed` changes drive it.
- **G-10. No-one-else's-mouth (CT-3).** No bar exists; the mouth judge scores only the speaker.
- **G-11. Words in crowd takes (MX-14).** The words judge does not run on cue takes. The rule needs it.
- **G-12. Energy and consistency of a voice across takes (MX-19).** No measure is built.
- **G-13. What counts as an extreme long shot (SW-17).** It depends on the set's plates (`audience_wide`, the set's
  widest). The jump-cut angle (SW-16) is web-only (30°, R49 §1.9). Zettl gives no angle.
- **G-14. Grading reliability.** Whether the configured model grades McKee's rules (WR-1-4, 7, 14-16) reliably is not known
  (blueprint §11.8). The planner harness's readout decides. Murch's six weights are not in the copy (R49 §6).
- **G-15. Scene reordering.** WR-17 has no script tool to act through (no scene move in the block's tool list).

## 8. Summary table

| id | name | tier | scope | source (short) |
|---|---|---|---|---|
| WR-1 | Each line acts on the other | grade | line | McKee task 1, ch. 1-2 |
| WR-2 | The scene turns | grade | scene | McKee ch. 12 |
| WR-3 | Exposition carried, not told to one who knows | grade | line | McKee task 3, ch. 6 |
| WR-4 | A voice per role | grade | exchange | McKee task 4, ch. 7, 10; Grindstaff p. 12 |
| WR-5 | Mark emotional peak / provocation / reveal | grade | line | Grindstaff pp. 19-20, 116, 250; bp §16.5 |
| WR-6 | No narration copied | check | line | bp §11.4; block :78 |
| WR-7 | Beats build; no repeated beat | grade | exchange | McKee task 2, ch. 9, 12 |
| WR-8 | Imply, don't explain | advise | line | McKee ch. 8 (vs Grindstaff, C-9) |
| WR-9 | The last word cues the reply | advise | line | McKee ch. 9 |
| WR-10 | Shorter as emotion rises; no clutter | advise | line | McKee ch. 7 |
| WR-11 | No long speech without a change | advise→check | exchange | McKee ch. 8; bp §11.4 |
| WR-12 | Speaking rate 2-3 words/s | advise | line | McKee ch. 8 |
| WR-13 | Speaker 1 speaks in Speaker 1's question-and-answer exchange | check | scene | bp §11.4; Zettl p. 421 |
| WR-14 | Lead speaker: open questions, follow-ups | grade | exchange | Zettl pp. 344, 442; Grindstaff pp. 3, 99 |
| WR-15 | Speaker: point first, no bare yes/no | grade | line | Grindstaff pp. 100-101, 116 |
| WR-16 | Desires cross in conflict | grade | scene | McKee ch. 8, 9, 12 |
| WR-17 | Strongest story first | advise | scene | Grindstaff pp. 123-124 |
| WR-18 | Hold the surprise for later | advise | scene | Grindstaff pp. 12-13, 117, 182 |
| WR-19 | Tease before a break; applause in/out | advise | scene | Grindstaff pp. 5, 46, 67 |
| WR-20 | Scene keeps its named length (±10 %) | check | scene | `hub/modules/director/length.py`; Zettl p. 416 |
| ST-1 | Pattern follows cast count | check | scene | Katz pp. 176-195, 209-211 |
| ST-2 | Lead speaker at one side of the other speakers | check | context | Zettl pp. 271-274; Katz p. 202 |
| ST-3 | One line; cameras on one side | check | scene | Zettl pp. 272, 469; Katz p. 130; S&B p. 51 |
| ST-4 | At most four set-ups, reused | check | scene | Katz pp. 135, 196, 211; Zettl p. 421 |
| ST-5 | Cameras numbered left to right | check | scene | Zettl p. 454 |
| ST-6 | Pairs matched | check | shot | S&B pp. 33-34; Katz pp. 176, 179 |
| ST-7 | Wholly on stage, apart | check | context | round 1 F1 |
| ST-8 | Seated where staged seated | check | scene | round 1 F5; bp §11.5 |
| ST-9 | Eye contact for a question-and-answer exchange | advise | scene | Zettl p. 422; Katz p. 185 |
| ST-10 | Lead speaker to camera at open/close | advise | line | Zettl pp. 359, 422; Grindstaff pp. 5, 46 |
| ST-11 | The house: none/heard/seen; featured ≥ 2 | check | context | bp §16.1-2; Grindstaff p. 121; Zettl p. 194; Holman p. 166 |
| ST-12 | Featured front/aisle; experts in house | advise | context | Grindstaff pp. 89, 122, 127 |
| ST-13 | Lead speaker into house: hand mic, order/raised hand | advise | scene | Zettl p. 155; bp §16.4 |
| ST-14 | Talent moves, cameras stay | advise | scene | Zettl pp. 424, 449 |
| ST-15 | Studio preset, three cameras | check | scene | bp §11.5; Katz pp. 130-133; Zettl pp. 454, 470; R49 §4.1 |
| SW-1 | Open on who is where | check | scene | Katz p. 358; Zettl pp. 421-422, 511; Holman p. 36 |
| SW-2 | Cut to the new speaker as the speaker begins | check | exchange | S&B p. 47; Zettl pp. 273, 434-435 (vs Murch, C-1) |
| SW-3 | Cut at a phrase end, not mid-word | check | shot | Zettl p. 273; bp §11.3 |
| SW-4 | Reaction cut-in: when, of whom | advise→check | exchange | bp §11.3; S&B p. 46; Katz pp. 227-228 |
| SW-5 | Reactions sparingly | advise→check | scene | S&B p. 40; Zettl pp. 422, 426 |
| SW-6 | Reaction a second early, inside the line | check | shot | S&B p. 40; Zettl p. 273; Katz p. 361; Holman p. 165 |
| SW-7 | Cutaway needs speech; no speaking mouth | check | shot | bp §11.3; Holman pp. 32, 118 |
| SW-8 | Short-line run holds the two-shot | advise→check | exchange | Katz pp. 182, 188; S&B p. 49; Zettl p. 276; Murch "Dragnet" |
| SW-9 | Entrance wide; cut while in frame | check | shot | R49 §4.7; Katz p. 155 |
| SW-10 | Emotional peak lands on a face | check | exchange | Grindstaff pp. 19-20, 250; Zettl pp. 255, 274-275 |
| SW-11 | Audience cue → audience, back on lead speaker | check | shot | bp §11.3, §16.5; Grindstaff pp. 127-129; Zettl p. 470 |
| SW-12 | No house in picture unless seen | check | shot | bp §16.1, §16.5; Holman p. 166; Zettl p. 194 |
| SW-13 | Audience reaction cut-in | advise→check | shot | bp §16.5; S&B p. 40; Grindstaff pp. 66, 127-128 |
| SW-14 | Cut to whom Speaker 1 looks at | advise | shot | R49 §4.7 (web); Katz p. 200 |
| SW-15 | Screen sides kept; neutral between | check | shot | Zettl pp. 254, 270-274, 509; Katz pp. 130, 136-139 |
| SW-16 | No near-identical cut | check | shot | Zettl pp. 269, 514; Murch "Why Do Cuts Work?"; F10 |
| SW-17 | No XLS ↔ close jump | check | shot | Zettl pp. 72, 269-270 (vs Katz p. 121) |
| SW-18 | Shot floor 1 s | check | shot | layout.py; Katz p. 155 |
| SW-19 | Hold ceiling; cut only with reason | advise→check | shot | Zettl pp. 269-270, 421; Murch "Most with the Least" |
| SW-20 | Cutting rate in form range | advise→check | scene | R49 §3.2-3.4; Murch "Dragnet" |
| SW-21 | Cut on the action | check | shot | Zettl pp. 272-273; Katz pp. 154-155 |
| SW-22 | Cut on the look: the pivot | advise | exchange | Katz pp. 123, 135, 200; Zettl p. 421 |
| SW-23 | Groups: OTS for three, singles for more | check | exchange | Katz pp. 197-198, 209; Zettl pp. 434-435 |
| SW-24 | In a question-and-answer exchange Speaker 2 is the picture | advise→check | scene | Zettl pp. 421-422, 426; Grindstaff p. 4 |
| SW-25 | The close: two-shot, lead speaker to camera | check | scene | Zettl pp. 421, 423; Katz p. 205; Holman p. 149 |
| SW-26 | Move in; wide only as pause or end | advise | scene | Katz pp. 129, 205; Holman p. 36 |
| SW-27 | Cuts within a scene; fades at ends | check | shot | Zettl pp. 255-259 |
| SW-28 | Insert for a thing shown | advise | shot | Zettl pp. 194, 255, 455; Katz p. 359 |
| SW-29 | No single of someone not there | check | shot | bp §11.3 |
| SW-30 | Same exchange, same cut | check | scene | bp §11.3 |
| MX-1 | Lines at the dialogue anchor −23 LUFS | check | mix | EBU R 128 via takejudge.py |
| MX-2 | Far-off take flagged (10 dB) | check | mix | takejudge.py |
| MX-3 | No clip after gain; ≤ −1 dBTP | check | mix | EBU R 128 via takejudge.py; Holman p. 177 |
| MX-4 | Track at its loudness target | check | mix | mix.py; EBU R 128; ATSC pending |
| MX-5 | Cues under the dialogue | check | mix | takejudge.py; Holman p. 173 |
| MX-6 | No line masked by the bed | advise→check | mix | Holman pp. 28-29, 37, 149, 175; bp §12.6 |
| MX-7 | Every line heard in the mix | check | mix | Holman pp. 149, 171; bp §12.5; settings |
| MX-8 | Overlap only as interruption | check | mix | Holman pp. 117, 160; Grindstaff p. 12 |
| MX-9 | Lanes by speaker and kind | check | mix | Holman pp. 159, 166; bp §12.3 |
| MX-10 | Reaction never cut dead | check | mix | bp §12.2.4, place.py |
| MX-11 | Beds duck under dialogue | check | mix | Holman p. 175; joincmd.py (vs Holman values, C-11) |
| MX-12 | Dead air flagged | advise | exchange | bp §12.4; Holman p. 160; F8b |
| MX-13 | Room tone under everything | check | mix | Holman pp. 29, 32, 148, 160 |
| MX-14 | Crowd carries no words | check | mix | Holman p. 118; the design rule |
| MX-15 | Dialogue centred; off-screen panned | advise | mix | Holman pp. 36-37 |
| MX-16 | Compress sources; light limiter last | advise | mix | Holman pp. 175, 177 |
| MX-17 | Lines at the turn gap (180 ms) | check | exchange | bp §12.4; R49 §5.8 |
| MX-18 | Each take trimmed to its speech | check | mix | bp §12.2.2; Holman p. 160 |
| MX-19 | Energy holds take to take | advise | line | Holman pp. 32, 118 |
| CT-1 | Face is the sheet's (0.30) | check | render | settings; judgeshot.py |
| CT-2 | Mouth with the words (0.60) | check | render | settings; bp §17.2 |
| CT-3 | No one else's mouth moves | advise→check | render | bp §17.2; Holman pp. 32, 118 |
| CT-4 | Shot is the size written | check | render | settings (C-12) |
| CT-5 | Shot's words heard (0.80) | check | render | settings |
| CT-6 | Line take heard (0.90); 3 tries | check | line | settings; bp §12.2 |
| CT-7 | No unscripted speech (2.5 s) | check | render | settings; judgeshot.py |
| CT-8 | Shot takes bounded (2; 15 min) | check | render | settings |
| CT-9 | No speech verbs outside lines | check | shot | a word list |
| CT-10 | Render unit ≤ one window (15.08 s) | check | render | bp §17.6; R48 §7 |
| CT-11 | One aspect (4:3) | check | context | bp §18.1 |
| CT-12 | A flag names bar and number | check | render | bp §11.2, §17.8 |

Counts: 96 rules.

| Department | Rules | check | grade | advise | advise→check |
|---|---|---|---|---|---|
| Writer | 20 | 3 | 9 | 7 | 1 |
| Stager | 15 | 10 | 0 | 5 | 0 |
| Switcher | 30 | 19 | 0 | 4 | 7 |
| Sound/mix | 19 | 14 | 0 | 4 | 1 |
| Control | 12 | 11 | 0 | 0 | 1 |
| **Total** | **96** | **57** | **9** | **20** | **10** |

("advise→check": the rule is sourced, its number is pending. It runs as `advise` until §11.6 or a source supplies the
number.)

**Sources not read in the original:**
- Stasheff & Bretz; Dmytryk; Bordwell; Arnold & Tilton; Heimbuch; Stivers: all through R49 only.
- EBU R 128: through `takejudge.py`'s quotation.
- ATSC A/85: not read.
- `timberg.txt` (Timberg, *Television Talk*) sits in the scratchpad but is not in `docs/library/` and was not read
  for R50.
