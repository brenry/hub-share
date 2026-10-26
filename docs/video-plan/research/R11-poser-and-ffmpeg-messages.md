# R11 - the "Poser" and "FFMPEG" messages: where owner-visible text comes from

Facts only; no owner data. Hub = the repository root, engine = the HocusPocus checkout (`app/`, `ui/`). The exact line shown is not known (section 4).
## 1. Worker/engine text -> owner-visible message
- The worker is spawned with stdout and stderr to DEVNULL unless Settings `diagnostics` is true, then to the Hub's own stderr
  (`hub/core/supervisor.py` `_spawn`: `out = sys.stderr if sp.passthrough else DEVNULL`; flag set in `hub/core/engine.py:229-230`).
  So an engine `print` never reaches a job line. With diagnostics on it appears on the Hub's console, between Hub log lines.
- The engine session is created with `console_output=False` (`hub/worker/wan2gp.py` `open`). During a job the engine
  captures stdout/stderr per line into `stdout`/`stderr` events (`app/shared/api.py:360-372`, `_OutputCapture`). `Engine.run`
  reads only `error` and `progress` events (`hub/worker/wan2gp.py:195-210`); the rest is dropped.
- Two engine texts do reach the job line:
  a. Progress `text` = the engine's status string `p.status` (`wan2gp.py:209` -> `enginecat.progress` `enginecat.py:78` ->
     `dispatch._ev_progress` `dispatch.py:194` `e.text` -> `jobs.record` `jobs.py:175`). The web shows it only while the phase
     matches /load/ (`web/src/modules/generate-image/run/jobs.ts:27,30`). The engine's `send_cmd("progress", ...)` strings
     are free text, e.g. "Extracting " + `processes_names[...]` where `pose` is "Open Pose" and `pose_align` is
     "Aligned Open Pose" (`app/wgp.py:4932,8678`); "Extracting Face Movements" (`wgp.py:8653`).
  b. Failure: `faults.failure` (`hub/worker/faults.py:27-37`) = first line of the first engine error message, cut to 600
     chars, plus " (at file:line in function)" or " (File ... <- File ...)" from the traceback. "out of memory" becomes "Out of GPU memory".
     Any exception text the engine raises is shown, e.g. `RuntimeError("ffmpeg binary not found")` and
     `"ffmpeg decode failed for <path>: <stderr>"` (`app/shared/utils/video_decode.py:256,285`), and the audio/mux errors
     `"FFmpeg error: ..."` (`app/shared/utils/audio_video.py:461,496`).
- Start-up: `main.one_line` (`hub/worker/main.py:27-31`) makes "The engine could not start: <first line of the exception, 200 chars>"
  (or "The engine stopped while starting (check its Python packages)" for SystemExit) and sends it as `fatal`; it becomes
  `down_text` (`supervisor.py` `_read`). The Hub does not add its own "Poser" or "ffmpeg" wording anywhere:
  `grep -i "poser|ffmpeg"` over `hub/**/*.py` finds nothing; the only hit in the Hub tree is the debt note
  `docs/Hub-Systems-and-Changes.md:285` (b) "ffmpeg download attempt at start shows as a message" and (m) "Poser ... source not found".
## 2. The hold line's program names
- Text: `hub/core/plan.py:53-60` `_blocked`: "{A} and {B} are using {x.x GB} on Server GPU" (two largest names; one name -> "is").
  Names: `foreign_names` (`plan.py:44-46`) = up to three distinct names from the foreign process list, largest first.
- Process list: `hub/core/probes.py:26-47` NVML compute + graphics process lists per GPU (pid -> MB). `vram.py:41-50` drops
  pids in `lane.pids()` = only the lane worker's own pid (`engine.py:84-85`), so any CHILD of the worker, and every other
  process, is "foreign". Names then via `probes.proc_name` (`probes.py:50-66`): read `/proc/<pid>/comm`; for each
  `known_programs` key, if key is a substring of comm -> label; else if key is a substring of the joined cmdline -> label;
  else the raw comm; unreadable -> "another program (pid N)". Defaults (`hub/settings.py:33`): ollama, ComfyUI, hocuspocus
  -> "HocusPocus", kwin_wayland/Xorg/gnome-shell -> "Desktop".
- Consequences (code facts): a process shows as "HocusPocus" when its cmdline contains the lowercase string "hocuspocus"
  (typically the python server whose path contains `hocuspocus`; case sensitive, so "HocusPocus" in a path would not match).
  A process shows as "ffmpeg" when comm is `ffmpeg` and neither comm nor cmdline contains a known key (an ffmpeg whose
  command line has no path containing "hocuspocus"/"ollama"/"ComfyUI"). Comm is the executable file name (max 15 chars)
  unless the program renames itself.
- Is it an NVENC child of the HocusPocus? Not supported by the source: no `nvenc`, `hwaccel`, `cuvid` or `scale_cuda`
  anywhere in `app/` or `ui/src` (grep over .py/.ts/.tsx/.js). All encodes are CPU: `libx264` (`app/shared/utils/audio_video.py:625-641`,
  `wgp.py:6811,9619`), decode is CPU `ffmpeg ... -f rawvideo` (`video_decode.py:262-268`). The engine's pid list for the lane
  is separate from the HocusPocus server (a different process tree). Why an ffmpeg process holds VRAM cannot be
  decided from source; it needs `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` plus `ps -o pid,ppid,comm,args -p <pid>`.
- "Poser" as a comm name: no setproctitle / PR_SET_NAME / process.title in `app/`, `ui/src`, root *.js. The `ui/` scene3d
  "pose" code is browser TypeScript (`ui/src/features/scene3d/imagePoseRuntime.ts`, `Scene3DPoseSequenceControls.tsx`,
  `typingPose.ts`) - not a separate process. A browser GPU process would show as chrome/headless_shell, not Poser.
## 3. Engine strings containing "pose"/"poser" (case-insensitive)
- Whole-word "poser" appears nowhere in the engine (`app/`, `ui/src`, root scripts). Substring "poser" matches only "composer",
  "purposer", etc. and the class `PoseRefNetNoBNV3` ("PoseR"; `app/models/wan/steadydancer/small_archs.py:76`, imported at
  `app/models/wan/modules/model.py:24`, built at `:1250` - a steadydancer-conditioned Wan model); a torch error naming that
  module (a state_dict "Missing/Unexpected key(s) ... condition_embedding_align...") would be shown via section 1b.
- No `controlnet_aux`, `openpose`, `mediapipe` import in `app/` at start-up. `preprocessing.dwpose` is imported lazily, only for the
  "pose"/"pose_align" process type (`wgp.py:5498`, `onnxruntime`). Nothing pose-related prints at import. The engine banner
  is `"Powered by WanGP v... - a DeepBeepMeep Production"` (`shared/api.py:998`), written to `sys.__stdout__`.
- netguard (`hub/worker/netguard.py`) blocks non-loopback connect and name lookups with PermissionError "Outbound network is
  blocked in the engine worker" / "Name lookups are blocked in the engine worker"; `OFFLINE_ENV` sets HF_HUB_OFFLINE=1.
  Downloads that would run under it:
  a. ffmpeg: `download_ffmpeg()` runs in `_ensure_runtime` (`shared/api.py:878`) at session start (first `ensure_ready`/submit).
     It returns silently if `ffmpeg` and `ffprobe` are in `<engine>/ffmpeg_bins`, `<engine>`, or on the worker's PATH (the worker
     env is only the inherited PATH, `supervisor.py:worker_env`). Otherwise `requests.get(api.github.com...)` raises the netguard
     PermissionError inside `except Exception` -> `print("Failed to download FFmpeg binaries automatically: Name lookups are
     blocked in the engine worker")` (`shared/ffmpeg_setup.py:258`). Printed, not raised: it reaches only the Hub console, and
     only when diagnostics is on. Nothing fails at that point; later ffmpeg users raise the section 1b texts.
  b. pose weights: `download_models(file_type=0)` is called on each model load (`wgp.py:4326/4330`); its shared list includes
     folder `pose` = `dw-ll_ucoco_384.onnx`, `yolox_l.onnx` from `DeepBeepMeep/Wan2.1` (`wgp.py:3919`), plus other shared
     folders. If any is missing from every checkpoints root, `process_files_def` (`wgp.py:3696-3745`) tries `hf_hub_download`/
     `snapshot_download`; offline it raises, so the job fails at load with that exception's first line plus `(at wgp.py:N in ...)`.
     The text names the file/repo (`pose`, `dw-ll_ucoco_384.onnx`, `DeepBeepMeep/Wan2.1`), not "Poser".

## 4. One-line fix per message
- "FFMPEG ... Failed to download FFmpeg binaries automatically": put `ffmpeg` and `ffprobe` on the PATH the worker inherits, or in
  `<engine root>/ffmpeg_bins/` (BtbN build, with its lib/*.so beside it). Silences it; no Hub code change needed.
- "ffmpeg binary not found" / "ffmpeg decode failed": same fix; the second carries ffmpeg's own stderr, so needs the exact line.
- Hold line "ffmpeg and HocusPocus are using ...": needs the exact `nvidia-smi` pid list and `ps` args of the ffmpeg pid from the server; source shows no GPU use by ffmpeg.
  If it is an ffmpeg child of the Hub's own worker, adding descendants of `lane.pids()` to "ours" (`vram.py:41`) would stop it counting as foreign.
- "Poser": needs the exact line from the server (verbatim text, and whether it was in the Hub console, a job line, a toast, or the hold line). If it is a console line,
  turn diagnostics off or capture with diagnostics on. If it is a job error, the candidates are a `PoseRefNetNoBNV3` torch error or a
  `pose/` weight fetch failure (3b); for the latter put the two `pose/` files under a checkpoints root (default `ckpts`, `files_locator.py:6`).
