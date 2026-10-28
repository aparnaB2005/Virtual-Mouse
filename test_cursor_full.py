import cv2
import mediapipe as mp
import math
import os
import threading
import time
from datetime import datetime
import pyautogui
from enum import IntEnum

try:
    import screen_brightness_control as sbc
    BRIGHT_OK = True
except ImportError:
    BRIGHT_OK = False
    print("[!] pip install screen-brightness-control  (needed for brightness gesture)")

# ---- PERF FIX #1: pyautogui adds a hidden 0.1s sleep after EVERY call by default
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False
mp_hands = mp.solutions.hands

# ---- tweakables
CAM_W, CAM_H = 640, 480
SMOOTH_ALPHA = 0.6     # 1.0 = no extra smoothing, lower = smoother but more delay
LOST_LIMIT = 8         # frames without a hand before we treat it as "hand left frame"
ADJ_STEP = 0.025       # hand travel (fraction of frame height) per volume/brightness step
MAX_STEPS = 3          # max steps applied in one frame (stops sudden jumps)
BRIGHT_STEP = 3        # % brightness per step
SCROLL_STEP = 0.015    # hand travel per scroll step (smaller = scrolls faster)
SCROLL_AMOUNT = 100    # scroll units per step
SHOT_HOLD = 1.5        # seconds to hold the screenshot gesture
SHOT_COOLDOWN = 3.0    # seconds before another screenshot can fire
SHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")


class Gest(IntEnum):
    FIST = 0
    PINKY = 1
    RING = 2
    MID = 4
    LAST3 = 7
    INDEX = 8
    FIRST2 = 12
    PALM = 15
    V_GEST = 33
    TWO_FINGER_CLOSED = 34
    ROCK = 9             # index + pinky (new: screenshot)
    THREE = 14           # index + middle + ring up (new: brightness)
    PINCH = 35           # OK-sign (new: volume)


# ---- PERF FIX #2: threaded camera reader, always gives the LATEST frame
class CamStream:
    def __init__(self, src=0):
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.frame = None
        self.new = False
        self.running = True
        self.lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            ok, f = self.cap.read()
            if ok:
                with self.lock:
                    self.frame = f
                    self.new = True
            else:
                time.sleep(0.005)

    def read(self):
        with self.lock:
            if not self.new:
                return None
            self.new = False
            return self.frame

    def release(self):
        self.running = False
        time.sleep(0.05)
        self.cap.release()


def get_signed_dist(lm, p1, p2):
    sign = 1 if lm[p1].y < lm[p2].y else -1
    dist = math.sqrt((lm[p1].x - lm[p2].x)**2 + (lm[p1].y - lm[p2].y)**2)
    return dist * sign

def get_dist(lm, p1, p2):
    return math.sqrt((lm[p1].x - lm[p2].x)**2 + (lm[p1].y - lm[p2].y)**2)

def get_dz(lm, p1, p2):
    return abs(lm[p1].z - lm[p2].z)

def get_finger_state(lm):
    points = [[8,5,0],[12,9,0],[16,13,0],[20,17,0]]
    finger_state = 0
    for tip, mcp, wrist in points:
        try:
            ratio = round(get_signed_dist(lm, tip, mcp) / get_signed_dist(lm, mcp, wrist), 1)
        except ZeroDivisionError:
            ratio = 0
        finger_state = finger_state << 1
        if ratio > 0.5:
            finger_state |= 1
    return finger_state

def classify_gesture(lm, finger_state):
    if finger_state in [Gest.LAST3, Gest.PALM] and get_dist(lm, 8, 4) < 0.05:
        return Gest.PINCH
    elif finger_state == Gest.FIRST2:
        d1 = get_dist(lm, 8, 12)
        d2 = get_dist(lm, 5, 9)
        ratio = d1 / d2 if d2 else 0
        if ratio > 1.7:
            return Gest.V_GEST
        else:
            return Gest.TWO_FINGER_CLOSED if get_dz(lm, 8, 12) < 0.1 else Gest.MID
    else:
        return finger_state


# ---- cursor movement (same dead-zone / scaled / fast zones as before)
SCREEN_W, SCREEN_H = pyautogui.size()   # PERF FIX #3: query once, not every frame
prev_hand = None
smooth_pt = None

def get_damped_position(lm):
    global prev_hand, smooth_pt
    point = 9
    raw_x = lm[point].x * SCREEN_W
    raw_y = lm[point].y * SCREEN_H

    # light smoothing on the raw hand point to kill jitter
    if smooth_pt is None:
        smooth_pt = (raw_x, raw_y)
    else:
        smooth_pt = (SMOOTH_ALPHA * raw_x + (1 - SMOOTH_ALPHA) * smooth_pt[0],
                     SMOOTH_ALPHA * raw_y + (1 - SMOOTH_ALPHA) * smooth_pt[1])
    x, y = int(smooth_pt[0]), int(smooth_pt[1])

    x_old, y_old = pyautogui.position()

    if prev_hand is None:
        prev_hand = (x, y)

    delta_x = x - prev_hand[0]
    delta_y = y - prev_hand[1]
    distsq = delta_x**2 + delta_y**2
    prev_hand = (x, y)

    if distsq <= 35:
        ratio = 0
    elif distsq <= 900:
        ratio = 0.07 * (distsq ** 0.5)
    else:
        ratio = 2.1

    nx = x_old + delta_x * ratio
    ny = y_old + delta_y * ratio
    # keep inside screen
    return max(0, min(SCREEN_W - 1, nx)), max(0, min(SCREEN_H - 1, ny))


# ---- volume / brightness control
adjust_anchor = None
adjust_mode = None

def reset_adjust():
    global adjust_anchor, adjust_mode
    adjust_anchor = None
    adjust_mode = None

def adjust_steps(lm, mode, step=ADJ_STEP):
    """Dial-style: moving hand up/down returns +/- steps relative to an anchor."""
    global adjust_anchor, adjust_mode
    y = lm[9].y
    if mode != adjust_mode or adjust_anchor is None:
        adjust_mode, adjust_anchor = mode, y
        return 0
    steps = int((adjust_anchor - y) / step)   # hand up => positive
    if steps:
        adjust_anchor -= steps * step
    return max(-MAX_STEPS, min(MAX_STEPS, steps))

def change_volume(steps):
    key = 'volumeup' if steps > 0 else 'volumedown'
    for _ in range(abs(steps)):
        pyautogui.press(key)

class BrightnessCtl:
    """Brightness calls are slow (WMI), so they run in a background thread -> no lag in the main loop."""
    def __init__(self):
        self.target = 50
        if BRIGHT_OK:
            try:
                v = sbc.get_brightness()
                self.target = v[0] if isinstance(v, (list, tuple)) else v
            except Exception:
                pass
        self.applied = self.target
        threading.Thread(target=self._loop, daemon=True).start()

    def nudge(self, steps):
        self.target = max(0, min(100, self.target + steps * BRIGHT_STEP))

    def _loop(self):
        while True:
            if BRIGHT_OK and self.target != self.applied:
                try:
                    sbc.set_brightness(self.target)
                    self.applied = self.target
                except Exception:
                    time.sleep(0.2)
            time.sleep(0.05)

bright = BrightnessCtl()

# ---- screenshot (hold-to-trigger)
shot_hold_start = None
last_shot_time = 0.0

def save_screenshot():
    """Runs in a background thread so saving the PNG never freezes the mouse."""
    def _run():
        try:
            os.makedirs(SHOT_DIR, exist_ok=True)
            path = os.path.join(SHOT_DIR, datetime.now().strftime("shot_%Y%m%d_%H%M%S.png"))
            pyautogui.screenshot(path)
        except Exception as e:
            print("[!] screenshot failed:", e)
    threading.Thread(target=_run, daemon=True).start()

def draw_hud(image, mode):
    if mode == "SCROLL":
        cv2.putText(image, "SCROLL: hand up = up, down = down", (10, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 120, 255), 2)
    elif mode == "SHOT" and shot_hold_start is not None:
        prog = min(1.0, (time.time() - shot_hold_start) / SHOT_HOLD)
        cv2.putText(image, "HOLD FOR SCREENSHOT", (10, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.rectangle(image, (10, 95), (210, 110), (255, 255, 255), 2)
        cv2.rectangle(image, (10, 95), (10 + int(200 * prog), 110), (0, 255, 255), -1)
    if time.time() - last_shot_time < 1.5:
        cv2.putText(image, "SCREENSHOT SAVED", (10, 140),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    if mode == "VOLUME":
        cv2.putText(image, "VOLUME: hand up = +, down = -", (10, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 200, 0), 2)
    elif mode == "BRIGHTNESS":
        h, w = image.shape[:2]
        cv2.putText(image, f"BRIGHTNESS {int(bright.target)}%", (10, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 255), 2)
        top, bot, x1, x2 = 100, h - 40, w - 40, w - 20
        cv2.rectangle(image, (x1, top), (x2, bot), (255, 255, 255), 2)
        fill = int(bot - (bot - top) * bright.target / 100)
        cv2.rectangle(image, (x1, fill), (x2, bot), (0, 220, 255), -1)

prev_gesture = Gest.PALM
confirmed_gesture = Gest.PALM
frame_count = 0
click_flag = False
drag_flag = False
lost_frames = 0

gesture_labels = {0:"FIST",1:"PINKY",2:"RING",4:"MID",7:"LAST3",8:"INDEX",
                  9:"ROCK",12:"FIRST2",14:"THREE",15:"PALM",33:"V_GEST",34:"TWO_FINGER_CLOSED",35:"PINCH"}


def reset_hand_state():
    """Called when the hand leaves the frame: release drag, forget stale position."""
    global prev_hand, smooth_pt, prev_gesture, confirmed_gesture
    global frame_count, click_flag, drag_flag, shot_hold_start
    if drag_flag:
        drag_flag = False
        pyautogui.mouseUp(button="left")   # never leave the button stuck down
    reset_adjust()
    shot_hold_start = None
    prev_hand = None
    smooth_pt = None
    prev_gesture = Gest.PALM
    confirmed_gesture = Gest.PALM
    frame_count = 0
    click_flag = False


stream = CamStream(0)
# PERF FIX #4: model_complexity=0 = lite hand model, much faster
with mp_hands.Hands(model_complexity=0, max_num_hands=1,
                    min_detection_confidence=0.5, min_tracking_confidence=0.5) as hands:
    while True:
        frame = stream.read()
        if frame is None:
            if cv2.waitKey(1) & 0xFF == 27:
                break
            continue

        image = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False          # PERF FIX #5: avoids a copy inside mediapipe
        results = hands.process(rgb)

        if results.multi_hand_landmarks:
            lost_frames = 0
            hud_mode = None
            lm = results.multi_hand_landmarks[0].landmark
            fstate = get_finger_state(lm)
            current = classify_gesture(lm, fstate)

            if current == prev_gesture:
                frame_count += 1
            else:
                frame_count = 0
            prev_gesture = current

            if frame_count > 4:
                confirmed_gesture = current

            if confirmed_gesture != Gest.ROCK:
                shot_hold_start = None

            if confirmed_gesture == Gest.V_GEST:
                x, y = get_damped_position(lm)
                pyautogui.moveTo(x, y)       # PERF FIX #6: no duration=0.1 blocking
                click_flag = True

            elif confirmed_gesture == Gest.FIST:
                if not drag_flag:
                    drag_flag = True
                    pyautogui.mouseDown(button="left")
                x, y = get_damped_position(lm)
                pyautogui.moveTo(x, y)

            else:
                if drag_flag:
                    drag_flag = False
                    pyautogui.mouseUp(button="left")
                prev_hand = None
                smooth_pt = None

                if confirmed_gesture not in (Gest.PINCH, Gest.THREE, Gest.PINKY):
                    reset_adjust()

                if confirmed_gesture == Gest.PINCH:          # OK-sign -> volume
                    click_flag = False
                    steps = adjust_steps(lm, "VOLUME")
                    if steps:
                        change_volume(steps)
                    hud_mode = "VOLUME"

                elif confirmed_gesture == Gest.THREE:        # 3 fingers -> brightness
                    click_flag = False
                    steps = adjust_steps(lm, "BRIGHTNESS")
                    if steps:
                        bright.nudge(steps)
                    hud_mode = "BRIGHTNESS"

                elif confirmed_gesture == Gest.PINKY:        # pinky only -> scroll
                    click_flag = False
                    steps = adjust_steps(lm, "SCROLL", SCROLL_STEP)
                    if steps:
                        pyautogui.scroll(steps * SCROLL_AMOUNT)
                    hud_mode = "SCROLL"

                elif confirmed_gesture == Gest.ROCK:         # index + pinky held -> screenshot
                    click_flag = False
                    now = time.time()
                    if shot_hold_start is None:
                        shot_hold_start = now
                    elif now - shot_hold_start >= SHOT_HOLD and now - last_shot_time >= SHOT_COOLDOWN:
                        save_screenshot()
                        last_shot_time = now
                    hud_mode = "SHOT"

                elif confirmed_gesture == Gest.MID and click_flag:
                    pyautogui.click()
                    click_flag = False

                elif confirmed_gesture == Gest.INDEX and click_flag:
                    pyautogui.click(button='right')
                    click_flag = False

                elif confirmed_gesture == Gest.TWO_FINGER_CLOSED and click_flag:
                    pyautogui.doubleClick()
                    click_flag = False

            label = gesture_labels.get(confirmed_gesture, str(confirmed_gesture))
            cv2.putText(image, label, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            draw_hud(image, hud_mode)

        else:
            # hand out of frame: tolerate tiny detection drops, then reset cleanly
            lost_frames += 1
            if lost_frames > LOST_LIMIT:
                reset_hand_state()
                cv2.putText(image, "NO HAND", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        cv2.imshow('Cursor Test', image)
        if cv2.waitKey(1) & 0xFF == 27:
            break

reset_hand_state()
stream.release()
cv2.destroyAllWindows()
