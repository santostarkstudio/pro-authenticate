# Testing on computer, tablet and phone before going online

## 1. Start the app
```
./run.sh              # Mac and Linux          run.bat   # Windows
python scripts/run_local.py --https           # needed for the camera on phones and tablets
```
The terminal prints two addresses: one for this computer and one for phones and tablets on the same Wi-Fi.

## 2. Why HTTPS matters
Browsers only allow the camera and microphone on `https://` pages (and on `localhost`). With `--https` the app makes a self-signed certificate. Phones show a warning once: choose Advanced, then continue. For a cleaner test over the internet use a tunnel such as Cloudflare Tunnel or ngrok, which gives a real HTTPS address.

## 3. Pages to open
- Candidate: the main address, then enter the interview code.
- Staff: the same address with `#/admin` added, or port 8082 when using Docker.

## 4. Device checklist
| Check | Computer | Tablet | Phone |
|---|---|---|---|
| Layout fits without sideways scrolling | | | |
| Camera and microphone permission works | | | |
| Candidate joins, waits, is admitted | | | |
| Candidate video appears on the staff console | | | |
| Click video: expanded view opens | | | |
| Pinch or wheel zoom, pan, freeze, save evidence | | | |
| Full screen (iPhone does not support it; the expanded view fills the screen instead) | | | |
| Rotating the device keeps working | | | |
| Buttons are easy to tap | | | |

Browsers to try: Chrome and Edge on computers, Safari on iPhone and iPad, Chrome on Android, plus Firefox once.

## 5. Typical problems
- **Camera blocked:** allow it in the browser address bar, or open the page in its own tab if you are inside a preview window.
- **Phone cannot reach the address:** same Wi-Fi, and allow the port through the computer's firewall.
- **Slow verdicts:** check `python scripts/check.py`, and use smaller frames if the model is heavy.
