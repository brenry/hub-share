# R54 — the mix: script-wide placement and the ffmpeg graph, prototyped and tested

For the mix. The prototype is in `R54-prototype/` (stdlib Python + ffmpeg 6.1.1); its tests run with
`python3 -m pytest -q -c /dev/null test_place.py test_graph.py` there (`-c /dev/null` keeps the repo's pytest settings
out). Where this note and the mix design differ, the mix code (`hub/modules/director/mix.py`) decides.


Plain Python 3.13 stdlib + ffmpeg 6.1.1. The 400-clip test takes most of the suite's time. `python3 bench.py` prints
every number below.

| file | what |
|---|---|
| `place.py` | the script-wide planned→placed map, clips, lanes, shots, `measured`, refusals |
| `graph.py` | the ffmpeg graph and the render (master, stems via `solo`) |
| `synth.py` | synthetic takes (lavfi), measured as `takemeasure.py` does; probes (ebur128 `Summary:`, silencedetect, RMS) |
| `bench.py` | the worked scene (30 s, 12 lines, 2 speakers + reaction + music = 4 lanes; room optional), comparisons |
| `test_place.py`, `test_graph.py` | 19 pure + 11 ffmpeg tests |

## Choices, and the measurements behind them

**Placement (place.py).** Lines in `(start_ms, id)` order across all shots. `E`/`P` is the latest planned end of the
dialogue so far and its placed time. A line with `start ≥ E` goes at `P + (start − E)`: right behind (`=`) is the
previous measured speech end + `TURN_MS`; a made pause (`>`) is kept exactly by the running offset. A line with
`start < E` is a written overlap: it goes at `map(start)` on its speaker's lane and adds no breakpoint that falls back. Its
overrun raises `P` (it pushes what follows). Cues, poses, panels and shots are mapped afterwards. The 1 s shot minimum
moves only the shot's cut (the clips are identical with and without shots, which the test checks). 300 random scripts:
breakpoints strictly rise in planned time and never fall in placed time, so the map is monotonic.
Limits: speakers ≤ `MAX_CAST` 16, lanes ≤ 20, clips ≤ 400 per lane and 1 000 in all, lane gain −60..24 dB, clip gain
−60..40 dB (the mix design's limits). Every number must be finite, whole ms where it is a time; bools are refused. Each refusal is one line naming the event.

**Ducking: a volume envelope computed from the placed dialogue clips, not `sidechaincompress`.** The bed goes down
10 dB (R42's engine depth), with the attack (200 ms) starting *before* each line. It comes back over 600 ms. Spans
less than 800 ms apart are merged, so the bed stays down across a turn. It is applied once to the sum of the ducked
lanes, as a binary tree of `if(lt(t,cut),…)`; ffmpeg evaluates only the branch taken, so each frame costs
log(spans). Music stem, 30 s scene:

| duck | in speech | between | depth | first 150 ms of each line | dialogue +6 dB |
|---|---|---|---|---|---|
| envelope (chosen) | −45.3 dB | −35.3 dB | **10.0 dB** | −10.0 dB | 10.0 dB |
| sidechain 0.05/6/200/600 | −37.6 | −35.3 | **2.4 dB** | −1.8 dB | — |
| sidechain 0.01/20/200/600 | −50.8 | −35.3 | 15.6 dB | −9.4 dB | 21.1 dB |

The envelope hits its stated depth at any dialogue level and is already down when the word starts. A compressor's
depth rides the dialogue level and lags by its attack. Both cost the same (0.95 vs 0.86 s).

**Master: measured gain + limiter (two ffmpeg runs), not `loudnorm`.**
- Run 1 writes the pre-master as float and reads ebur128's `I:` after `Summary:` at `-v info`.
- Run 2 applies `volume=(−23 − I) dB`, then `aresample=192000`, then
  `alimiter=limit=10^((−1−0.5)/20):attack=5:release=50:level=0:latency=1`, then back to 48 kHz.

Test case: a levelled click take (−31 LUFS, gain +4 dB, so it peaks at +3.0 dBTP in the mix) placed in a gap, with one
speaker +6 dB:

| master | limit margin 0 | margin 0.5 dB | time (30 s scene) |
|---|---|---|---|
| gain + alimiter (chosen) | −23.0 LUFS / **−1.0** dBTP | −23.0 / **−1.5** | 0.95 s |
| loudnorm one pass + alimiter | −23.2 / **−0.5** | −23.2 / −1.0 | 1.54 s |
| loudnorm two-pass linear + alimiter | −23.0 / **−0.4** | −23.0 / −0.9 | 2.62 s |

In a second gap the same click gave −1.0/−1.5 (gain) against −0.8/−1.3 (loudnorm) and −0.6/−1.1 (two-pass). Only gain
+ limiter meets both −23 ±1 LU and ≤ −1 dBTP, with 0.5 dB to spare. With no margin it sits exactly on −1.0. All three
were within ±1 LU on integrated loudness.

**Reaction fade-out: `decay_ms // 2`, floor 300 ms (not 10).** A take that stops dead measures
`decay_ms` 0. Level of its last 50 ms below its body: 10 ms fade **−0.4 dB** (a dead stop, the "soundboard"), 100 ms
8.7 dB, 300 ms 18.3 dB.

**Room:** optional. With no room take the mix is made without it, with one note (`NO_ROOM`). Its clip is looped to the
length and **not ducked**: across 30 s, every 1 s window is within 3 dB.

**Re-mix time, 30 s, 12 lines, 4 lanes: 0.88–0.95 s** (placement 0.3 ms + two ffmpeg runs); 0.84 s with the room as a
5th lane. Scaling: 100 clips over 5 min with 16 speakers take 1.4 s for the pre-master (2.3 s with a ducked bed). 400
clips over 21 min take **51.5 s** in all: about 18 s for the pre-master and 16.8 s for the 4×-oversampled limiter pass
(7.1 s without oversampling).

Also confirmed: a mono 24 kHz take measures the same before and after the graph's upmix to stereo (−21.0 vs −21.1
LUFS), so gains measured on the take file hold in the mix.

## Found wrong or underspecified in the mix design 

1. **The design's clip chain loses audio.** With `adelay` followed by the lane's `apad=whole_dur, atrim=end`, each lane comes out
   short by its first clip's delay: the Character 1 lane was 28.32 s instead of 31.0 s, and a lone clip at 27.587 s gave
   3.46 s (the clip itself was cut). The cause is ffmpeg 6.1: `adelay`'s lead-in frames carry `pts` =
   AV_NOPTS_VALUE+n, and `atrim=end` trims by `pts`. The master's length check can't see it, because the longest lane
   (music or room) is full length. Fix: `asetpts=N/SR/TB` after `adelay`, and sample-counted padding
   (`apad=whole_len`, `atrim=end_sample`). Test: `test_finding_spec_clip_chain_comes_out_short`.
2. **The design's master breaks −1 dBTP:** one `loudnorm` pass + `alimiter=limit=10^(tp/20)` gives −0.5 dBTP (table above).
   The design's own test bound "≤ −0.7 dBTP" admits this. Fix: measured gain + limiter 0.5 dB under the target. The
   design's `alimiter` also lacks `latency=1`, which shifts the whole track 5 ms late (onset 505 vs 500 ms).
3. **The design's ducking doesn't duck.** 0.05/6/200/600 presses the music 2.4 dB under −23 LUFS dialogue, so Done-means
   "beds pressed under the speech" fails. No depth is specified as a number the compressor can hold. R42's
   `depth_db` 10 is one, and the envelope holds it exactly.
4. **The design's cost is clips × length (one `adelay`'d stream per clip) and lanes × length (one `amix` per lane).** At
   the clip cap that is far from "seconds": 400 clips over 21 min took 260 s. With clips padded to the next clip's place and
   joined by `concat` on non-overlapping tracks, lane gains folded into the clips, and one stream per group
   (dialogue, ducked beds, the rest) instead of one per lane, the same mix takes 51.5 s. 1 000 clips (the cap in all) will be
   minutes, not seconds.
5. **The argv limit.** 400 clips plus a ducked bed make a 134 464-char graph. Linux refuses one argument over 128 KiB
   (`OSError: [Errno 7] Argument list too long`, verified). Past ~100 KB the graph has to go through
   `-filter_complex_script` (a file in the worker's outbox).
6. **The design's placement diverges from "right behind" in two overlap cases** (both are tests):
   - An interruption planned to end inside the line it cuts into, but whose take runs long, adds no breakpoint. The
     next line then starts while it is still speaking: an overlap nobody wrote.
   - An interruption planned to end after that line, but whose take comes back short, leaves `(end − E)` of silence
     before the next line (1 s in the test): dead air nobody made.

   Defining "the previous line" as the dialogue's latest planned end `E`, placed at `P`, the latest *placed* end, fixes
   both.
7. **The design's reaction fade floor of 10 ms** leaves a dead-cut take dead (−0.4 dB). Use a floor of ~300 ms.
8. **PLAN's "bed lanes ducked" versus blueprint §12.3:** the blueprint ducks reaction, effect and music, not the room.
   Ducking the room would make room tone swell in every gap. Underspecified: whether an **effect** written over a line
   should be pressed 10 dB under it. Here a click under l4 peaked at −7.2 dBTP against −1.0 in a gap.
9. **Gain ranges:** `takejudge` writes clip gains up to +46.9 dB (a take just above the −70 LUFS gate). The design caps a clip
   at +40, so a take between −70 and −63 LUFS makes every mix refuse until it is redone. That is coherent, because
   takejudge flags it "level" anyway, but the refusal should name the take and say to redo it.
10. **The mix's own measurement** (the gain master) must parse ebur128 at `-v info` after `Summary:`, as 9a's
    pre-check says for takes. Pass 1 needs only `I`, so it runs `ebur128` without `peak=true`.
