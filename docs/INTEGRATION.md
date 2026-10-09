# Connecting your model project (no coding needed from you)

## What to share with the assistant
1. **Zip your project folder** and upload it in the chat.
2. Include: your Python files, the trained model files (`.pt`, `.h5`, `.keras`, `.onnx`), `requirements.txt` if you have one, and 5 to 10 sample images or short clips of real faces and fake ones (photo, phone screen).
3. Leave out: the training dataset, virtual environments (`venv`, `.venv`), `.git`, passwords, API keys, and personal data.
4. Tell the assistant, in one line, which file you run today (for example `python main.py`) and what it prints for a real face and a fake one.

## What the assistant does with it
- Runs `tools/inspect_project.py` to find the model files, the predict code, the input size, the class order and the preprocessing.
- Reorganizes code that opens the camera itself (`cv2.VideoCapture`) into one function that takes a single frame and returns REAL or FAKE with a confidence.
- Connects it (`FG_VERIFIER=custom` or `model`), tests it on your sample images, and runs `scripts/check.py`.
- Fills the connection into the web app and checks it on a phone, a tablet and a computer layout.

## Try it yourself first (optional)
```
python tools/inspect_project.py path/to/your/project
```
It prints what it found and writes a draft `models/model.json`. It never changes your project.

## Three ways to connect
| Mode | Use when | Setting |
|---|---|---|
| custom | Your project already has a function that predicts from a frame | `FG_VERIFIER=custom` and `FG_CUSTOM=your_module:your_function`, project in `backend/model_project/` |
| model | You have YOLO weights and a Keras classifier | `FG_VERIFIER=model` and fill `backend/models/model.json` |
| demo | Placeholder while you wait | `FG_VERIFIER=demo` |

Your function may return `("REAL", 0.93)`, `("FAKE", 0.88)`, a dict with `label` and `confidence`, a single number (chance it is real), or just `"REAL"`. Frames arrive in OpenCV order (BGR) by default. Set `FG_BGR=0` if your code expects RGB.

## How to know it works
Run `python scripts/check.py`. Every line should say PASS, then start the app and look at the engine name under Verification in the staff console.
