# R23 — R21 and R22 checked against the sources, and what they change in the plan (2026-10-15)

R21 (`R21-h3-director-mode.md`) and R22 (`R22-h3-prompt-cookbook.md`)
were written outside this repo from copies of upstream WanGP, Maestro and (R21 only) HocusPocus. They were handed
over as input, not as fact. This note says what was checked here, where they differ, and the decisions taken.

## Checked here
- **Upstream WanGP `af2ed29` (the engine the Hub runs), read in a clean clone.** Every engine claim re-read holds at
  the cited line: the three FL2VA fields and six Ref2VA sections (`models/minimax_h3/prompt_enhancer.py:252`,
  `:284`); the per-family agent rules `deepy_prompt_infos` (`minimax_h3_handler.py:418`, `:504`, `:542`, `:718`,
  `:795`); the audio model's `Speaker N:` header and `[direction]` regexes and 2.6 words/s (`dialogue.py:23`,
  `:44-45`); the window commands `{duration, overlap, new_shot, no_end_image, loras_mult}` and the `[/…]` form
  (`shared/utils/frame_scheduler.py:8-9`); `PG` as the default line mode and the `PW` boundary check
  (`shared/utils/prompt_parser.py:8`, `:62`); the engine's own MCP tools `wangp_model` (`shared/mcp/server.py:1777`)
  and `wangp_validate` with its per-window plan (`shared/mcp/v2.py:863`, `shared/mcp/preflight.py:83-91`).
- **The engine does not parse the grammar.** No code outside the enhancer prompts and the agent guides reads
  `[Shot N]`, `<d>`, `(S1)` or `<scenetrans>`; the one place the engine writes them is its own speech compiler
  (`dialogue.py:196`). Both documents say this; it is the fact the design rests on.
- **Maestro, public `Blizaine/Maestro` `31d7396` = 2.6.0, shallow clone.** No MCP server (no `fastmcp` or
  `modelcontextprotocol` anywhere); the JSON-schema grammar is local-llama-server only
  (`app/services/llm_service.py:2533-2535`); the validators exist (`app/services/director/h3_dialogue.py:348`,
  `:2403`, "dialogue block N is not canonical" `:364`); speech paced at 2.8 words/s, 3.0 at most
  (`app/services/dialogue_timing.py:6-7`); a failed plan queues no job ("No video jobs were queued."). Some of R22's
  line numbers in `planners/short_film.py` are off; the quoted text is there.
- **The Hub.** The clip task is sent with `multi_prompts_gen_type: "FG"` (`hub/worker/adapters/tasks.py:181`, `:187`):
  one prompt unit per clip. Generate renders the assistant's free-text draft (`hub/modules/generate_image/tools.py`).

## Not checked here
- **HocusPocus 0.10.0.** R21 read a copy; R22 could not. Nothing of HocusPocus is on this machine. R21's
  HocusPocus numbers (0.22 s per syllable, a 2.1 words/s budget, `minimax_h3_duration.py`) stand unverified.
- The installs on the server: R22's open questions 1 and 2 (is the installed engine `af2ed29`? is the Maestro `31d7396`?). The installed
  engine is `af2ed29` (installed by `install-engine.sh`, Stage 10). The Maestro version is not recorded here.

## Where the two documents differ, and the reading taken
| Point | R21 | R22 | Here |
|---|---|---|---|
| HocusPocus | read (0.10.0) | not reachable | R21's claims kept as unverified |
| Speech pace | HP 2.1 words/s budget, 0.22 s/syllable | Maestro 2.8–3.0; upstream video: none; audio 2.6 | not an engine fact: a Hub **setting**, measured on the server's GPU |
| Where to enforce | structured tool argument → compiler → validator → length from lines | validator regexes from Maestro as "layer one" | R21's shape; R22's regexes are its test data |
| Windows | one unit per clip (`FG`) | asks whether to use `PW` + `[/…]` | **one prompt unit per clip, as the Hub does now**; a cut inside a clip is `[Shot N] At`, a hard cut is a new clip; `PW` and the window commands are not used (R22 rules 21–24 drop) |

## Decisions
1. **Order stands:** Stage 10 close (one picture, one clip on upstream), Stage 11 `--probe-join`, Stage 12 voice
   (architect spec), **Stage 13 Director** from R21 §4 with R22 §A/§E as its rule source. Nothing is built for
   Stage 13 before Stage 12 is done, and the line stays straight.
2. **The rules come from the engine, not from a paragraph.** Field names, letters, lattice, window bounds and the
   agent rules (`deepy_prompt_infos`) are read through the adapter (`READS`), as the catalog already reads the rest.
   Rates the engine does not publish (words or syllables per second) are settings.
3. **Shot 1 has no timestamp; `non_diegetic_music: N/A` when no score; one speaker id per person across a
   storyboard** — upstream's own published rules win every contradiction in R22 §F.
4. **One server test before the Stage 13 spec is final** (R21 §7): that the Open WebUI passes a nested
   object argument schema to the model as a grammar. One tool call; written into the chat when Stage 13 starts.
