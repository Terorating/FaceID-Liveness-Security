"""
Face Lock Pro
version 4031
"""

import cv2
import mediapipe as mp
import numpy as np
import json
import os
import time
import ctypes
import sys
import hashlib
import random
from collections import deque
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
    CRYPTO_OK = True
except ImportError:
    CRYPTO_OK = False
    print("Fuck You: cryptography not installed")

try:
    import win32crypt
    DPAPI_OK = True
except ImportError:
    DPAPI_OK = False
    print("Fuck You: pywin32 not installed")

try:
    import tkinter as tk
    from tkinter import simpledialog, messagebox
    TK_OK = True
except ImportError:
    TK_OK = False

SCRIPT_DIR = Path(__file__).parent.absolute()
DATA_DIR = SCRIPT_DIR / "data"
MODELS_DIR = SCRIPT_DIR / "models"

FACE_JSON = DATA_DIR / "face_data.enc"
GESTURE_JSON = DATA_DIR / "gesture_data.enc"
FACE_PHOTO = DATA_DIR / "face_photo.jpg"
GESTURE_PHOTO = DATA_DIR / "gesture_photo.jpg"
KEY_FILE = DATA_DIR / ".key"
ATTEMPTS_FILE = DATA_DIR / ".attempts"

FACE_MODEL = MODELS_DIR / "face_landmarker.task"
HAND_MODEL = MODELS_DIR / "hand_landmarker.task"

NUM_NEIGHBORS = 3
DELETE_DELAY = 2.0
BLINK_EAR_CLOSED = 0.2
BLINK_EAR_OPEN = 0.4
MIN_CLOSED_FRAMES = 1
POINT_SIZE = 3
LIVENESS_TIMEOUT = 8.0
RESTART_TIMEOUT = 5.0
CHALLENGE_TIMEOUT = 3.0
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300
NORM_TOLERANCE = 0.05

user32 = ctypes.windll.user32


def check_models():
    MODELS_DIR.mkdir(exist_ok=True)
    missing = []
    if not FACE_MODEL.exists():
        missing.append(f"face_landmarker.task (expected in {MODELS_DIR})")
    if not HAND_MODEL.exists():
        missing.append(f"hand_landmarker.task (expected in {MODELS_DIR})")
    if missing:
        print("\n" + "=" * 60)
        print("MISSING MODEL FILES:")
        for m in missing:
            print(f"   - {m}")
        print(f"\nPut models into: {MODELS_DIR}")
        print("=" * 60 + "\n")
        return False
    return True


class CryptoVault:
    def __init__(self):
        self.fernet = None

    def _ask_password(self, prompt, confirm=False):
        if TK_OK:
            root = tk.Tk()
            root.withdraw()
            pwd = simpledialog.askstring("Face Lock Pro", prompt, show="*")
            if confirm:
                pwd2 = simpledialog.askstring("Face Lock Pro", "Repeat password:", show="*")
                root.destroy()
                if pwd != pwd2:
                    print("ERROR: passwords do not match")
                    return ""
                return pwd or ""
            root.destroy()
            return pwd or ""
        else:
            import getpass
            return getpass.getpass(prompt + " ")

    def _dpapi_encrypt(self, data):
        if DPAPI_OK:
            blob = win32crypt.CryptProtectData(data, "FaceLockPro", None, None, None, 0)
            return b"DPAPI:" + blob
        return b"RAW:" + data

    def _dpapi_decrypt(self, data):
        if data.startswith(b"DPAPI:"):
            if not DPAPI_OK:
                raise RuntimeError("DPAPI unavailable")
            return win32crypt.CryptUnprotectData(data[6:], None, None, None, 0)[1]
        if data.startswith(b"RAW:"):
            return data[4:]
        raise RuntimeError("Unknown key format")

    def initialize(self):
        if not CRYPTO_OK:
            print("ERROR: cryptography is required for encryption.")
            return False
        DATA_DIR.mkdir(exist_ok=True)
        if KEY_FILE.exists():
            return self._load_existing()
        return self._create_new()

    def _create_new(self):
        print("\nFirst run: setting up encryption.")
        use_password = False
        if TK_OK:
            root = tk.Tk()
            root.withdraw()
            ans = messagebox.askyesno(
                "Face Lock Pro",
                "Protect data with password?\n\nYes - password + Windows binding.\nNo - Windows binding only."
            )
            root.destroy()
            use_password = bool(ans)

        password = ""
        if use_password:
            password = self._ask_password("Create password:", confirm=True)
            if not password:
                print("ERROR: empty password - cancelled.")
                return False

        fernet_key = Fernet.generate_key()
        payload = {
            "fernet_key": fernet_key.decode(),
            "use_password": use_password,
            "password_check": hashlib.sha256(password.encode()).hexdigest() if use_password else "",
        }
        blob = self._dpapi_encrypt(json.dumps(payload).encode())
        KEY_FILE.write_bytes(blob)
        self.fernet = Fernet(fernet_key)
        print("Key created" + (" + password" if use_password else " (DPAPI)"))
        return True

    def _load_existing(self):
        try:
            blob = KEY_FILE.read_bytes()
            payload = json.loads(self._dpapi_decrypt(blob).decode())
        except Exception as e:
            print(f"ERROR: cannot decrypt key: {e}")
            return False

        if payload.get("use_password"):
            password = self._ask_password("Enter password:")
            expected = payload.get("password_check", "")
            actual = hashlib.sha256(password.encode()).hexdigest()
            if actual != expected:
                print("lol: wrong password.")
                return False

        self.fernet = Fernet(payload["fernet_key"].encode())
        return True

    def encrypt_bytes(self, data):
        return self.fernet.encrypt(data)

    def decrypt_bytes(self, token):
        try:
            return self.fernet.decrypt(token)
        except InvalidToken:
            raise RuntimeError("Wrong key or corrupted data")

    def encrypt_json(self, obj):
        return self.encrypt_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def decrypt_json(self, token):
        return json.loads(self.decrypt_bytes(token).decode("utf-8"))


class AttemptGuard:
    def __init__(self, vault):
        self.vault = vault
        self.attempts = 0
        self.locked_until = 0.0
        self._load()

    def _load(self):
        if not ATTEMPTS_FILE.exists():
            return
        try:
            data = self.vault.decrypt_json(ATTEMPTS_FILE.read_bytes())
            self.attempts = int(data.get("attempts", 0))
            self.locked_until = float(data.get("locked_until", 0.0))
        except Exception:
            pass

    def _save(self):
        data = {"attempts": self.attempts, "locked_until": self.locked_until}
        ATTEMPTS_FILE.write_bytes(self.vault.encrypt_json(data))

    def is_locked(self):
        return time.time() < self.locked_until

    def remaining_lock(self):
        return max(0.0, self.locked_until - time.time())

    def register_failure(self):
        self.attempts += 1
        if self.attempts >= MAX_ATTEMPTS:
            self.locked_until = time.time() + LOCKOUT_SECONDS
            self.attempts = 0
            print(f"LOCKED for {LOCKOUT_SECONDS} sec")
        self._save()

    def register_success(self):
        self.attempts = 0
        self.locked_until = 0.0
        self._save()


class LivenessChecker:
    def __init__(self):
        self.blink_history = deque(maxlen=30)
        self.smile_history = deque(maxlen=15)
        self.total_blinks = 0
        self.eye_state = "open"
        self.closed_frames = 0

        self.challenge_phase = "idle"
        self.challenge_type = None
        self.challenge_time = 0.0
        self.challenge_start_blinks = 0
        self._last_points = None

    
    def get_ear(self, points, side):
        # Индексы верхнего и нижнего века
        if side == "left":
            top_idx = [159, 158, 157]      # Верхнее веко
            bot_idx = [145, 153, 154]      # Нижнее веко
            left_corner = 33
            right_corner = 133
        else:
            top_idx = [386, 385, 384]      # Верхнее веко
            bot_idx = [374, 380, 373]      # Нижнее веко
            left_corner = 362
            right_corner = 263

        # Проверка, что индексы существуют )их нету(
        if any(i >= len(points) for i in top_idx + bot_idx + [left_corner, right_corner]):
            return 0.3

        # 1. Расчёт высот глаза (расстояние между верхним и нижним веком)
        top_y = np.mean([points[i].y for i in top_idx])
        bot_y = np.mean([points[i].y for i in bot_idx])
        eye_height = abs(top_y - bot_y)

        # 2. Считаем ширину глаза (расстояние между уголками)
        w = abs(points[left_corner].x - points[right_corner].x)
        
        if w <= 1e-6:
            return 0.3

        # 3. Отношение высоты к ширине
        ear = eye_height / w
        return ear

    def update_eyes(self, points):
        left = self.get_ear(points, "left")
        right = self.get_ear(points, "right")
        avg = (left + right) / 2
        self.blink_history.append(avg)

        if self.eye_state == "open":
            if avg < BLINK_EAR_CLOSED:
                print(f"[EYE] CLOSED (EAR={avg:.1f})")
                self.eye_state = "closed"
                self.closed_frames = 1
        else:
            if avg > BLINK_EAR_OPEN:
                print(f"[EYE] OPEN (EAR={avg:.1f}, closed_frames={self.closed_frames})")
                if self.closed_frames >= MIN_CLOSED_FRAMES:
                    self.total_blinks += 1
                    print(f"BLINK #{self.total_blinks}")
                self.eye_state = "open"
                self.closed_frames = 0
            else:
                self.closed_frames += 1

        return avg

    def is_smiling(self, points):
        try:
            top = np.mean([[points[i].x, points[i].y] for i in [61, 62, 63, 64, 65, 66, 67]], axis=0)
            bottom = np.mean([[points[i].x, points[i].y] for i in [76, 77, 78, 79, 80, 81, 82]], axis=0)
            left = np.array([points[61].x, points[61].y])
            right = np.array([points[291].x, points[291].y])
        except (IndexError, AttributeError):
            return False
        mouth_h = np.linalg.norm(top - bottom)
        mouth_w = np.linalg.norm(left - right)
        if mouth_w == 0:
            return False
        return (mouth_h / mouth_w) > 0.4

    def head_dx(self, points):
        try:
            return points[1].x - points[168].x
        except (IndexError, AttributeError):
            return 0.0

    def _start_challenge(self):
        self.challenge_type = random.choice(["blink_twice", "smile", "turn_left", "turn_right"])
        self.challenge_phase = "challenge"
        self.challenge_time = time.time()
        self.challenge_start_blinks = self.total_blinks
        print(f"CHALLENGE: {self.challenge_type} (start blinks: {self.challenge_start_blinks})")

    def _challenge_passed(self):
        if self.challenge_type == "blink_twice":
            return (self.total_blinks - self.challenge_start_blinks) >= 2
        if self.challenge_type == "smile":
            return any(self.smile_history)
        if self.challenge_type == "turn_left":
            return self.head_dx(self._last_points) < -0.05
        if self.challenge_type == "turn_right":
            return self.head_dx(self._last_points) > 0.05
        return False

    def check(self, points):
        if not points:
            return False, "No face", self.challenge_type if self.challenge_phase == "challenge" else None

        self._last_points = points
        self.update_eyes(points)
        self.smile_history.append(self.is_smiling(points))

        if self.challenge_phase == "idle" and len(self.blink_history) >= 5:
            self._start_challenge()

        if self.challenge_phase == "challenge":
            elapsed = time.time() - self.challenge_time
            if elapsed > CHALLENGE_TIMEOUT:
                self.challenge_phase = "failed"
                return False, "Challenge timeout", self.challenge_type
            if self._challenge_passed():
                self.challenge_phase = "passed"
                print(f"CHALLENGE PASSED: {self.challenge_type}")
                return True, f"Alive ({self.challenge_type})", self.challenge_type
            return False, f"DO: {self.challenge_type}", self.challenge_type

        if self.challenge_phase == "passed":
            return True, "Alive", None

        return False, "Warming up", None

    def draw_eye_points(self, frame, points, h, w):
        left_idx = [33, 133, 157, 158, 159, 160, 161, 173]
        right_idx = [362, 263, 387, 386, 385, 384, 398, 466]
        color = (0, 255, 0) if self.eye_state == "open" else (0, 0, 255)
        for idx in left_idx + right_idx:
            if idx < len(points):
                x = int(points[idx].x * w)
                y = int(points[idx].y * h)
                cv2.circle(frame, (x, y), 2, color, -1)
        ear = (self.get_ear(points, "left") + self.get_ear(points, "right")) / 2
        cv2.putText(frame, f"EAR: {ear:.1f}  BLINKS: {self.total_blinks}",
                    (10, 420), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def block_input(on):
    try:
        return bool(user32.BlockInput(on))
    except Exception:
        return False


def restart_app():
    print("Padla restarting...")
    time.sleep(1)
    python = sys.executable
    os.execl(python, python, *sys.argv)


BaseOptions = mp.tasks.BaseOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
HandLandmarker = mp.tasks.vision.HandLandmarker
HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

if not check_models():
    input("Press Enter to exit...")
    sys.exit(1)

face_landmarker = FaceLandmarker.create_from_options(FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=str(FACE_MODEL)),
    running_mode=VisionRunningMode.VIDEO,
    num_faces=1,
    min_face_detection_confidence=0.5,
    min_face_presence_confidence=0.5,
    min_tracking_confidence=0.5,
))
hand_landmarker = HandLandmarker.create_from_options(HandLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=str(HAND_MODEL)),
    running_mode=VisionRunningMode.VIDEO,
    num_hands=1,
    min_hand_detection_confidence=0.5,
    min_hand_presence_confidence=0.5,
    min_tracking_confidence=0.5,
))


def get_face_points(rgb):
    try:
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = face_landmarker.detect_for_video(img, int(time.time() * 1000))
        if not res.face_landmarks:
            return None
        return res.face_landmarks[0]
    except Exception:
        return None


def get_hand_points(rgb):
    try:
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = hand_landmarker.detect_for_video(img, int(time.time() * 1000))
        if not res.hand_landmarks:
            return None
        return res.hand_landmarks[0]
    except Exception:
        return None


def get_128_points(points, h, w):
    result = []
    step = 468 / 128
    for i in range(128):
        idx = int(i * step)
        if idx < len(points):
            result.append((int(points[idx].x * w), int(points[idx].y * h)))
    return result


def get_21_points(points, h, w):
    return [(int(points[i].x * w), int(points[i].y * h)) for i in range(min(21, len(points)))]


def face_scale(points):
    if len(points) >= 264:
        return np.linalg.norm(np.array(points[33]) - np.array(points[263]))
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return max(1.0, max(xs) - min(xs))


def normalized_distances(points):
    scale = face_scale(points)
    if scale <= 0:
        scale = 1.0
    n = len(points)
    out = []
    for i in range(n):
        for j in range(i + 1, n):
            d = np.linalg.norm(np.array(points[i]) - np.array(points[j])) / scale
            out.append((i, j, float(d)))
    return out


def compare_distances(d1, d2, tolerance):
    if len(d1) != len(d2):
        return False
    for (i, j, a), (_, _, b) in zip(d1, d2):
        if abs(a - b) > tolerance:
            return False
    return True


def save_shadowprint(vault, frame, points, photo_path, json_path):
    if not points:
        return False
    bg = np.zeros_like(frame)
    n = len(points)
    for i in range(n):
        dists = []
        for j in range(n):
            if i == j:
                continue
            d = np.linalg.norm(np.array(points[i]) - np.array(points[j]))
            dists.append((d, j))
        dists.sort(key=lambda x: x[0])
        for k in range(min(4, len(dists))):
            j = dists[k][1]
            cv2.line(bg, tuple(points[i]), tuple(points[j]), (255, 255, 255), 1)
    for pt in points:
        cv2.circle(bg, tuple(pt), POINT_SIZE, (255, 255, 255), -1)
    cv2.imwrite(str(photo_path), bg)

    data = {
        "points": [(float(x), float(y)) for x, y in points],
        "distances_norm": normalized_distances(points),
        "count": len(points),
        "scale": face_scale(points),
        "version": "4031",
    }
    json_path.write_bytes(vault.encrypt_json(data))
    return True


def verify_shadowprint(vault, points, json_path):
    if not json_path.exists():
        return False, "No data"
    try:
        ref = vault.decrypt_json(json_path.read_bytes())
    except Exception as e:
        return False, f"Decrypt error: {e}"
    if len(points) != len(ref.get("points", [])):
        return False, f"Points mismatch ({len(points)} vs {len(ref.get('points', []))})"
    current = normalized_distances(points)
    if not compare_distances(current, ref.get("distances_norm", []), NORM_TOLERANCE):
        return False, "Distances mismatch"
    return True, "OK"


block_enabled = True
restart_requested = False

buttons = [
    {"x": 10, "y": 70, "w": 120, "h": 30, "text": "REGISTER", "action": "register"},
    {"x": 140, "y": 70, "w": 120, "h": 30, "text": "DELETE", "action": "delete"},
    {"x": 270, "y": 70, "w": 160, "h": 30, "text": "BLOCK: ON", "action": "toggle_block"},
]


def draw_buttons(frame):
    for btn in buttons:
        if btn["action"] == "toggle_block":
            color = (0, 255, 0) if block_enabled else (0, 0, 255)
        else:
            color = (100, 100, 200)
        cv2.rectangle(frame, (btn["x"], btn["y"]), (btn["x"] + btn["w"], btn["y"] + btn["h"]), color, -1)
        cv2.rectangle(frame, (btn["x"], btn["y"]), (btn["x"] + btn["w"], btn["y"] + btn["h"]), (255, 255, 255), 1)
        if btn["action"] == "toggle_block":
            btn["text"] = "BLOCK: ON" if block_enabled else "BLOCK: OFF"
        cv2.putText(frame, btn["text"], (btn["x"] + 10, btn["y"] + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)


def mouse_callback(event, x, y, flags, param):
    global block_enabled, restart_requested
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    if param.get("show_restart", False):
        rx, ry, rw, rh = 10, 250, 120, 40
        if rx <= x <= rx + rw and ry <= y <= ry + rh:
            restart_requested = True
            print("RESTART clicked")
            return
    for btn in buttons:
        if btn["x"] <= x <= btn["x"] + btn["w"] and btn["y"] <= y <= btn["y"] + btn["h"]:
            if btn["action"] == "register":
                param["register"] = True
            elif btn["action"] == "delete":
                param["delete"] = True
                param["delete_start"] = time.time()
            elif btn["action"] == "toggle_block":
                block_enabled = not block_enabled
                block_input(block_enabled)


def draw_spiderweb(frame, points, color=(0, 255, 200)):
    if not points:
        return
    n = len(points)
    for i in range(n):
        dists = []
        for j in range(n):
            if i == j:
                continue
            d = np.linalg.norm(np.array(points[i]) - np.array(points[j]))
            dists.append((d, j))
        dists.sort(key=lambda x: x[0])
        for k in range(min(NUM_NEIGHBORS, len(dists))):
            j = dists[k][1]
            cv2.line(frame, tuple(points[i]), tuple(points[j]), color, 1)
    for pt in points:
        cv2.circle(frame, tuple(pt), POINT_SIZE, (255, 255, 255), 1)
        cv2.circle(frame, tuple(pt), POINT_SIZE - 1, (0, 255, 0), -1)


def main_loop():
    global block_enabled, restart_requested

    print("\n" + "=" * 60)
    print("   FACE LOCK PRO v1.4 (Windows)")
    print(f"   Data: {DATA_DIR}")
    print(f"   Models: {MODELS_DIR}")
    print("=" * 60)

    vault = CryptoVault()
    if not vault.initialize():
        print("ERROR: encryption init failed.")
        input("Enter...")
        return

    guard = AttemptGuard(vault)

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("Camera not available")
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    cv2.namedWindow("Face Lock Pro", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Face Lock Pro", 800, 600)

    param = {"register": False, "delete": False, "delete_start": 0, "show_restart": False}
    cv2.setMouseCallback("Face Lock Pro", mouse_callback, param)

    running = True
    registered = FACE_JSON.exists()
    access_granted = False

    liveness = LivenessChecker()

    last_face_points = []
    last_hand_points = []
    face_pts = None
    frame_count = 0

    liveness_ok = False
    liveness_checked = False
    show_restart_button = False
    restart_timer_start = 0.0
    restart_countdown = RESTART_TIMEOUT
    liveness_start_time = time.time()

    while running:
        ret, frame = cap.read()
        if not ret:
            continue
        frame_count += 1
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = frame.shape[:2]

        if param["register"]:
            param["register"] = False
            if last_face_points:
                block_input(False)
                DATA_DIR.mkdir(exist_ok=True)
                all_face = get_128_points(face_pts, h, w) if face_pts else last_face_points
                save_shadowprint(vault, frame, all_face, FACE_PHOTO, FACE_JSON)
                print("Face saved (128 points, encrypted)")
                if last_hand_points:
                    save_shadowprint(vault, frame, last_hand_points, GESTURE_PHOTO, GESTURE_JSON)
                registered = True
                if block_enabled:
                    block_input(True)
            else:
                print("No face detected")

        if param["delete"]:
            if time.time() - param["delete_start"] >= DELETE_DELAY:
                if DATA_DIR.exists():
                    for f in [FACE_JSON, GESTURE_JSON, FACE_PHOTO, GESTURE_PHOTO, ATTEMPTS_FILE]:
                        try:
                            f.unlink()
                        except FileNotFoundError:
                            pass
                print("Data deleted (encryption key kept)")
                registered = False
                access_granted = False
                param["delete"] = False

        face_pts = get_face_points(rgb)
        face_points_display = []
        hand_points_display = []
        if face_pts:
            face_points_display = get_128_points(face_pts, h, w)
            last_face_points = face_points_display
            hand_pts = get_hand_points(rgb)
            if hand_pts:
                hand_points_display = get_21_points(hand_pts, h, w)
                last_hand_points = hand_points_display
        else:
            access_granted = False

        if guard.is_locked():
            remaining = guard.remaining_lock()
            cv2.putText(frame, f"LOCKED: {remaining:.0f}s", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        if not liveness_checked and not show_restart_button and not guard.is_locked():
            if face_pts:
                ok, msg, ch = liveness.check(face_pts)
                if ch and liveness.challenge_phase == "challenge":
                    elapsed = time.time() - liveness.challenge_time
                    remaining = max(0, CHALLENGE_TIMEOUT - elapsed)
                    cv2.putText(frame, f"DO: {ch}", (10, 310),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    cv2.putText(frame, f"Time: {remaining:.1f}s", (10, 340),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                if ok:
                    liveness_ok = True
                    liveness_checked = True
                    print("LIVENESS OK")
                else:
                    if time.time() - liveness_start_time > LIVENESS_TIMEOUT:
                        liveness_checked = True
                        liveness_ok = False
                        restart_timer_start = time.time()
                        print("LIVENESS FAILED")
            else:
                if time.time() - liveness_start_time > LIVENESS_TIMEOUT:
                    liveness_checked = True
                    liveness_ok = False
                    restart_timer_start = time.time()

        if last_face_points:
            draw_spiderweb(frame, last_face_points, (0, 255, 200))
        if last_hand_points:
            draw_spiderweb(frame, last_hand_points, (0, 165, 255))
        if face_pts:
            liveness.update_eyes(face_pts)
            liveness.draw_eye_points(frame, face_pts, h, w)

        y = 160
        if liveness_ok:
            cv2.putText(frame, "LIVENESS YEEEY: OK", (10, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        elif liveness_checked and not liveness_ok:
            if not show_restart_button:
                remaining = max(0, restart_countdown - (time.time() - restart_timer_start))
                cv2.putText(frame, f"LIVENESS FAIL: {remaining:.1f}s", (10, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                if remaining <= 0:
                    show_restart_button = True
                    param["show_restart"] = True
                    print("RESTART button available")
            else:
                cv2.putText(frame, "LIVENESS FAIL", (10, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        else:
            remaining = max(0, LIVENESS_TIMEOUT - (time.time() - liveness_start_time))
            cv2.putText(frame, f"LIVENESS: {remaining:.1f}s", (10, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 2)

        if show_restart_button:
            rx, ry, rw, rh = 10, 250, 120, 40
            cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (0, 0, 255), -1)
            cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (255, 255, 255), 2)
            cv2.putText(frame, "RESTART", (rx + 15, ry + 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        if access_granted:
            cv2.putText(frame, "ACCESS GRANTED", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        elif registered and last_face_points:
            cv2.putText(frame, "ACCESS DENIED", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        elif not registered and last_face_points:
            cv2.putText(frame, "PRESS REGISTER", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        else:
            cv2.putText(frame, "FACE NOT FOUND", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        draw_buttons(frame)
        block_status = "BLOCKED" if block_enabled else "UNLOCKED"
        cv2.putText(frame, f"BLOCK: {block_status}", (10, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

        cv2.imshow("Face Lock Pro", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            running = False

        if restart_requested:
            restart_requested = False
            cap.release()
            cv2.destroyAllWindows()
            restart_app()
            return

        if liveness_ok and registered:
            if frame_count % 5 == 0 and face_pts:
                ok, msg = verify_shadowprint(vault, face_points_display, FACE_JSON)
                if ok:
                    access_granted = True
                    guard.register_success()
                else:
                    access_granted = False
                    if frame_count % 30 == 0:
                        guard.register_failure()

    cap.release()
    cv2.destroyAllWindows()
    block_input(False)
    print("Program finished")


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        block_input(False)
        print("\nInterrupted")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        block_input(False)
        input("Press Enter to exit...")
        sys.exit(1)
