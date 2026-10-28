# Virtual Mouse: Hand-Gesture Controlled Cursor

Control your computer with just your hand and a normal webcam. No special hardware needed.

Move the cursor, click, drag, change volume and brightness, scroll and take screenshots, all with hand gestures.

Built with **Python**, **OpenCV**, **MediaPipe** and **PyAutoGUI**.

---

## What it can do

| Gesture | What it does |
|---|---|
| V sign (index + middle finger, spread apart) | Move the cursor |
| Middle finger only | Left click |
| Index finger only | Right click |
| Index + middle fingers together | Double click |
| Fist | Drag (hold and move) |
| Open palm (all fingers up) | Idle / rest. Does nothing, and releases a drag |
| OK sign (thumb and index touching) | Volume: move hand **up** = louder, **down** = quieter |
| Three fingers (index + middle + ring) | Brightness: move hand **up** = brighter, **down** = dimmer |
| Pinky only | Scroll: move hand **up** = scroll up, **down** = scroll down |
| Rock sign (index + pinky), hold for 1.5 s | Take a screenshot |

Press **ESC** in the camera window to quit.

### How clicking works (important!)

Clicks only work **right after the V gesture**:

1. Show the **V sign** and move the cursor to what you want.
2. Change to the click gesture: middle finger (left click), index finger (right click) or two fingers together (double click).
3. To click again, show the **V sign** first.

This is on purpose, so random hand movements don't click by accident.

### Tip: how a gesture gets recognised

A gesture must stay steady for about 6 frames (around 0.2 seconds) before it counts. Hold each pose for a moment and the program will pick it up.

---

## Before you start

You need:

- A computer with a **webcam** (laptop webcam is fine)
- **Python 3.9 to 3.12** (MediaPipe often does not install on newer versions)
- Good lighting, with your hand about **40 to 60 cm** from the camera

Check your Python version:

```bash
python --version
```

If it says Python 3.13 or higher, or the command is not found, install Python 3.12 from https://www.python.org/downloads/ (on Windows, tick **"Add Python to PATH"** during installation).

---

## Setup (step by step)

### 1. Get the code

**Option A: with Git**
```bash
git clone https://github.com/aparnaB2005/Virtual-Mouse.git
cd virtual-mouse
```

**Option B: without Git**
Click the green **Code** button on GitHub, choose **Download ZIP**, extract it, and open the folder in a terminal (or in VS Code).

### 2. Create a virtual environment

A virtual environment keeps this project's libraries separate from the rest of your computer.

**Windows**
```bash
python -m venv venv
venv\Scripts\activate
```

**Mac / Linux**
```bash
python3 -m venv venv
source venv/bin/activate
```

When it works, you will see `(venv)` at the start of your terminal line.

> **Windows PowerShell error about scripts being disabled?** Run this once, then try activating again:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 3. Install the libraries

```bash
pip install -r requirements.txt
```

This installs OpenCV, MediaPipe, PyAutoGUI, screen-brightness-control and Pillow. It can take a few minutes.

If you don't have the `requirements.txt` file, create one with this content:

```
opencv-python
mediapipe==0.10.14
numpy<2
pyautogui
screen-brightness-control
pillow
```

### 4. Run it

```bash
python test_cursor_full.py
```

A window called **Cursor Test** opens with your camera view. Show your hand and try the gestures.

### 5. Using VS Code (optional)

1. Open the project folder in VS Code (`File > Open Folder`).
2. Press `Ctrl+Shift+P`, choose **Python: Select Interpreter**, and pick the one inside `venv`.
3. Open the terminal with `` Ctrl+` `` and run `python test_cursor_full.py`.

> Run it from the terminal. The "Run Code" button can cause camera and window problems.

---

## What you see on the screen

- **Top-left (green):** the gesture the program has confirmed, such as `V_GEST`, `FIST` or `PALM`
- **Cyan / yellow / pink text:** the current mode (volume, brightness, scroll)
- **Bar on the right edge:** the brightness level while you change brightness
- **Progress bar:** fills up while you hold the rock sign for a screenshot
- **"SCREENSHOT SAVED":** a screenshot was taken
- **"NO HAND" (red):** your hand is out of the frame

Screenshots are saved in a `screenshots/` folder next to the script.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Camera window is black or does not open | Close other apps using the camera (Zoom, Teams). In the code, change `CamStream(0)` to `CamStream(1)` |
| `pip install mediapipe` fails | Check your Python version (use 3.9 to 3.12) |
| Errors about `numpy` or `protobuf` | Run `pip install "numpy<2" mediapipe==0.10.14` |
| Cursor does not move on Mac | Allow **Camera** and **Accessibility** access for Terminal or VS Code in System Settings |
| Volume gesture does nothing on Mac | Volume keys are only supported on Windows and Linux |
| Brightness does not change | Works on laptop screens. Many external monitors do not support it |
| Gestures are not detected | Use better lighting, keep your hand 40 to 60 cm away, and hold each gesture steady |
| Gesture picked up wrongly | Keep your hand upright and facing the camera |
| Cursor is jumpy or laggy | Close other heavy programs and improve the lighting |

---

## Known limitations

- Works with **one hand** and the **main monitor** only
- Works best with an **upright hand**; a sideways or tilted hand can be misread
- Volume and brightness are tuned for **Windows laptops**
- If two hands are in view, the program may switch between them

---

## Project structure

```
virtual-mouse/
├── test_cursor_full.py   # the main program
├── requirements.txt      # libraries to install
├── screenshots/          # created automatically when you take screenshots
└── README.md
```