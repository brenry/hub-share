# 07 — External programs and the rebuild order

## 7.1 External programs the Hub depends on

| Program | Machine | Who installs it | The Hub's use | Does the Hub change it? |
|---|---|---|---|---|
| **Upstream WanGP** (its `wgp.py` and its Python) | the server | The engine installer (`install/install-engine.sh`, section 3 of `README-INSTALL.md`) | The image and video engine, kept at `<prefix>/engine` (`app`, `env`, `python`). The Hub installer refuses a prefix inside the engine folder. | Only `finetunes/auto_*.json`: pointer files the running Hub writes and deletes (marked `hub_auto`). Nothing else; the installer only reads. |
| **Image models and LoRA files** | the server | By hand | Read from the model folders and LoRA folders in Settings | No. Never copied, moved, linked or deleted. LoRA strengths live in Hub data. |
| **NVIDIA driver** | the server | By hand | GPU memory readings (VRAM manager) | No |
| **Python 3.13 or 3.14** (system) | the server | By hand / the OS | The base of the Hub's own Python environment, built offline from the zip's wheels, hash-checked | No |
| **firewalld** | the server | The OS | Optional: two rules limiting the Hub's port to the LAN; asked first; needs `sudo` | Only on a yes at the prompt; `uninstall.sh` removes them |
| **systemd (user)** | the server | The OS | `hub.service`, started at boot (linger) and after a crash | Installs that one unit |
| **Open WebUI** | the server, 127.0.0.1 | By hand | The chat box sends the conversation to it; it can call the Hub's tool server at `/mcp` | One chat titled "Hub" while a tool-server conversation is open, deleted at New chat and when the Hub stops |
| **The desk client** (a browser, or a client that opens web pages as windows) | the desk | By hand | Shows the Hub's screens (`/` and `/media`) | No. The addresses are added by hand (`README-INSTALL.md` §2). |

**Not dependencies:** any cloud service; the older fork the first engine came from.


## 7.2 Rebuild order from two blank machines

### The server
1. OS with the NVIDIA driver, Python 3.13 or 3.14, firewalld.
2. The model and LoRA folders, anywhere on the server's disks.
3. Open WebUI on 127.0.0.1, with its models.
4. Build the release zip in the dev copy: `python tools/release.py` → `dist/hub-release-<date-time>.zip`. It needs `wheels/` (it fetches them on the dev side if missing).
5. Install: the one line in `README-INSTALL.md` §1. The Hub at `<prefix>` (`$HOME/hub` unless `--prefix`), the service, the firewall question, a pairing link.
6. The engine: `README-INSTALL.md` §3 (the checkout, then `install/install-engine.sh`).
7. Restore `data/` from a backup, with the Hub stopped. Backup line (run now): `tar czf ~/hub-data-$(date +%F).tgz -C <prefix> data`
8. The pointer files in `<engine>/finetunes/auto_*.json` come back by themselves at the next model scan.

### The desk
Nothing of the Hub is installed here. The desk client opens `http://<server>:42010/` and `http://<server>:42010/media`, paired with the link the server printed.

### Then
- Settings → Assistant → Open WebUI: Address (`http://127.0.0.1:3000`), API key (Open WebUI → Settings → Account → API keys), Save, Model.
- For images from the chat: Settings → Assistant → Access on; copy the Key; in Open WebUI → Admin → External Tools add `http://127.0.0.1:42010/mcp` with Auth: Bearer and that key; then pick it under Tool server.
- Check: a message in the chat box gets a reply; a draft asked of the assistant writes the draft page; Generate puts the image in Media.
