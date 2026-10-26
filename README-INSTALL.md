# Installing the Hub

One command, on the server. Run it as your normal user, without `sudo`. Nothing is downloaded: the Python packages come from the zip. If anything fails, the installer undoes that run.

## 1. The server

Copy `hub-release-<date-time>.zip` to the server, open a terminal in that folder, and run:

```
unzip -q hub-release-<date-time>.zip && bash hub-release-<date-time>/install/install-hub.sh
```

The installer finds an existing install through the `hub` command on this computer and updates it in place. With no install yet, it puts the hub under `$HOME/hub`, or under the folder given with `--prefix DIR`. The text below writes `<prefix>` for that folder. Your settings and images live in its `data` folder. The image engine is the Hub's own, upstream WanGP in `<prefix>/engine` (section 3); a repair or update keeps the engine settings as they are. It starts the hub on port 42010, at boot and again after a crash, and adds the `hub` command. It asks once whether only your home network may reach port 42010. Saying yes adds two firewall rules, and `sudo` asks for your password.

At the end it prints a **pairing link** for the desk computer's screens. It works once, within 10 minutes.

Once running, the hub writes one kind of file into the engine's code: a small pointer file in its `finetunes` folder for each new model file it recognises (`auto_*.json`, marked `hub_auto`). The hub never copies, moves or deletes a weight file: it reads them in the model folders you set in Settings.

Your pictures live in one place, the Temp (`data/outputs`, the Temp in Media), plus the Drive folder you choose. A picture is its pixels: no metadata inside it, no record of how it was made, no prompt kept anywhere. Fifteen seconds after the last Hub window closes, the prompt, the reference boxes and the chat are forgotten; the next window starts from the pictures in Temp and your saved settings.

Language models are not part of the Hub. The Hub's chat box talks to Open WebUI (Settings → Assistant).

## 2. The desk computer

The desk computer shows the Hub's screens in a browser or in a desk client that opens web pages as windows; nothing of the Hub is installed on it. The server's address is what `hub network show` prints on the server, written below as `<server>`.

1. Open the pairing link once on the desk computer. The desk is now paired; the pairing is a cookie, shared by every window of the same browser or client.
2. Open `http://<server>:42010/` for the Hub's main screen.
3. For Media on another monitor, open `http://<server>:42010/media` in a second window and put it there.

In a desk client that keeps saved addresses, save the plain addresses above, not the pairing link, so the used code is not kept.

## 3. The Hub's own engine

The engine is upstream WanGP, kept in `<prefix>/engine`: `app` (its code, a git checkout), `env` (its Python environment) and `python` (that environment's own Python). Its code and environment are made once (an engine checkout step outside this installer); then, once:

```
bash <prefix>/install/install-engine.sh --dry-run
bash <prefix>/install/install-engine.sh
```

The first line only lists what it would do. The second points the hub at the engine, writes the app's config (from the old engine's, without its secrets; your model folders are not in it), checks that the engine starts, and stops and restarts the hub. It asks before it starts and undoes everything if a step fails. Run again, it repairs.

The model and LoRA folders stay the ones you set in Settings → Image models: the engine reads the weights where they are, and nothing in those folders is moved, copied or deleted, even files upstream calls deprecated.

To go back: `bash <prefix>/install/uninstall.sh --engine` puts the hub's engine settings back as they were before the install (your model and LoRA folders stay as they are now).

## New link, or an address changed

Run these in a terminal on the server:
- `hub pair --name Desk` makes a new pairing link for the screens.
- `hub network show` shows the server's address, port and paired devices.
- If the **server's** address changed, run `hub network reset`. It finds the new address and restarts the hub. Then pair again with `hub pair --name Desk`, and change the saved addresses on the desk computer.
- If the **desk's** address changed, the hub says "Pair this device again". Run `hub pair --name Desk` and open the link on the desk computer.

To keep addresses from changing, give the server and the desk computer fixed addresses in your router (a "DHCP reservation").

## Restart, or another port

- Restart: Settings → About → Restart, or `hub restart` on the server.
- Port: Settings → Assistant → Connection → Port, or `hub network set --port <n>`. If you added the firewall rules, run the installer again so they cover the new port.

## Update or repair

Run the same command from a newer zip. Your settings and images stay. What an older hub kept about pictures (reference copies, thumbnail cache, the favorites list, LoRA notes and covers) is erased at the first start; favorites are now the `Favorites` folder inside each day of the Temp.

## Remove

`bash <prefix>/install/uninstall.sh`. This removes exactly what the installer added: the program, its Python environment, the service, the `hub` command, the start-at-boot setting and the firewall rules. It keeps your images and settings in `<prefix>/data`; add `--purge` to remove those too. The engine (`engine/`) is not removed with the hub: `uninstall.sh --engine` puts the hub's engine settings back, and `uninstall.sh --engine --purge` also removes the engine's code and Python (section 3). The pointer files stay in the engine's `finetunes` folder; to list them: `grep -l '"hub_auto": true' <prefix>/engine/app/finetunes/*.json`.

**Rarely needed options for `install-hub.sh`:**
- `--prefix DIR` (the install folder; default: the existing install the `hub` command points at, else `$HOME/hub`), `--bind IP`, `--engine-root DIR`, `--engine-python FILE`, `--python FILE` (the system Python 3.13 or 3.14 to build from) and `--lora-folder DIR` (repeat it for more folders);
- `--no-firewall` skips the firewall question;
- `--yes` answers yes to its questions.
