"""
Face Lock Pro v3.0
Биометрическая аутентификация с проверкой живости
Модульная структура в одном файле
"""

import cv2
import mediapipe as mp
import numpy as np
import json
import os
import time
import ctypes
import sys
import shutil
import hashlib
import secrets
import logging
import threading
from collections import deque
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, field

# ==============================================================================
# МОДУЛЬ 1: НАСТРОЙКИ (CONFIG)
# ==============================================================================

@dataclass
class CameraSettings:
    """Настройки камеры"""
    device_id: int = 0
    width: int = 640
    height: int = 480
    fps: int = 30
    exposure: Optional[float] = None
    brightness: Optional[float] = None
    contrast: Optional[float] = None
    saturation: Optional[float] = None
    sharpness: Optional[float] = None
    gain: Optional[float] = None


@dataclass
class DetectionSettings:
    """Настройки детекции"""
    confidence_threshold: float = 0.5
    num_faces: int = 1
    
    min_face_detection_confidence: float = 0.5
    min_face_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5
    
    min_hand_detection_confidence: float = 0.5
    min_hand_presence_confidence: float = 0.5
    
    mole_min_area: int = 4
    mole_max_area: int = 200
    mole_contrast_threshold: int = 15
    mole_merge_distance: int = 15
    mole_max_count: int = 30
    mole_match_threshold: float = 0.6
    
    lip_movement_threshold: float = 0.004
    lip_speech_threshold: float = 0.012


@dataclass
class LivenessSettings:
    """Настройки проверки живости"""
    timeout: float = 8.0
    restart_timeout: float = 5.0
    challenge_timeout: float = 3.0
    
    blink_weight: float = 0.4
    lip_weight: float = 0.3
    mole_weight: float = 0.3
    
    liveness_threshold: float = 0.55
    blink_threshold: float = 0.015
    min_blink_history: int = 10


@dataclass
class SecuritySettings:
    """Настройки безопасности"""
    block_watchdog_timeout: float = 30.0
    encryption_iterations: int = 100000
    encryption_key_length: int = 32
    deepfake_edge_min: float = 0.01
    deepfake_edge_max: float = 0.5


@dataclass
class UISettings:
    """Настройки интерфейса"""
    window_title: str = "Face Lock Pro"
    window_width: int = 800
    window_height: int = 600
    
    color_moles: Tuple[int, int, int] = (0, 0, 255)
    color_face: Tuple[int, int, int] = (200, 255, 0)
    color_hand: Tuple[int, int, int] = (255, 165, 0)
    color_success: Tuple[int, int, int] = (0, 255, 0)
    color_error: Tuple[int, int, int] = (0, 0, 255)
    color_warning: Tuple[int, int, int] = (0, 255, 255)
    
    point_size: int = 3


@dataclass
class Config:
    """Главный конфиг"""
    camera: CameraSettings = field(default_factory=CameraSettings)
    detection: DetectionSettings = field(default_factory=DetectionSettings)
    liveness: LivenessSettings = field(default_factory=LivenessSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)
    ui: UISettings = field(default_factory=UISettings)
    
    script_dir: Path = field(default_factory=lambda: Path(__file__).parent.absolute())
    data_dir: Path = field(default_factory=lambda: Path(__file__).parent.absolute() / "data")
    models_dir: Path = field(default_factory=lambda: Path(__file__).parent.absolute() / "models")
    logs_dir: Path = field(default_factory=lambda: Path(__file__).parent.absolute() / "logs")
    
    face_json: Path = field(init=False)
    gesture_json: Path = field(init=False)
    moles_json: Path = field(init=False)
    face_photo: Path = field(init=False)
    gesture_photo: Path = field(init=False)
    moles_photo: Path = field(init=False)
    
    face_model: Path = field(init=False)
    hand_model: Path = field(init=False)
    
    distance_tolerance: float = 8.0
    num_neighbors: int = 3
    
    def __post_init__(self):
        self.face_json = self.data_dir / "face_data.enc"
        self.gesture_json = self.data_dir / "gesture_data.enc"
        self.moles_json = self.data_dir / "moles_data.enc"
        self.face_photo = self.data_dir / "face_photo.jpg"
        self.gesture_photo = self.data_dir / "gesture_photo.jpg"
        self.moles_photo = self.data_dir / "moles_photo.jpg"
        self.face_model = self.models_dir / "face_landmarker.task"
        self.hand_model = self.models_dir / "hand_landmarker.task"
    
    def load_from_file(self, config_path: Path):
        if not config_path.exists():
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if 'camera' in data:
                cam = data['camera']
                self.camera.device_id = cam.get('device_id', 0)
                self.camera.width = cam.get('width', 640)
                self.camera.height = cam.get('height', 480)
                self.camera.fps = cam.get('fps', 30)
                self.camera.exposure = cam.get('exposure')
                self.camera.brightness = cam.get('brightness')
                self.camera.contrast = cam.get('contrast')
                self.camera.saturation = cam.get('saturation')
                self.camera.sharpness = cam.get('sharpness')
                self.camera.gain = cam.get('gain')
            
            if 'detection' in data:
                det = data['detection']
                self.detection.confidence_threshold = det.get('confidence_threshold', 0.5)
                self.detection.mole_min_area = det.get('mole_min_area', 4)
                self.detection.mole_max_area = det.get('mole_max_area', 200)
                self.detection.mole_contrast_threshold = det.get('mole_contrast_threshold', 15)
                self.detection.mole_merge_distance = det.get('mole_merge_distance', 15)
                self.detection.mole_max_count = det.get('mole_max_count', 30)
                self.detection.mole_match_threshold = det.get('mole_match_threshold', 0.6)
                self.detection.lip_movement_threshold = det.get('lip_movement_threshold', 0.004)
            
            if 'liveness' in data:
                liv = data['liveness']
                self.liveness.timeout = liv.get('timeout', 8.0)
                self.liveness.liveness_threshold = liv.get('liveness_threshold', 0.55)
                self.liveness.blink_weight = liv.get('blink_weight', 0.4)
                self.liveness.lip_weight = liv.get('lip_weight', 0.3)
                self.liveness.mole_weight = liv.get('mole_weight', 0.3)
            
            if 'security' in data:
                sec = data['security']
                self.security.block_watchdog_timeout = sec.get('block_watchdog_timeout', 30.0)
            
            print(f"✅ Настройки загружены из {config_path}")
            
        except Exception as e:
            print(f"⚠️ Ошибка загрузки настроек: {e}")
    
    def save_to_file(self, config_path: Path):
        data = {
            'camera': {
                'device_id': self.camera.device_id,
                'width': self.camera.width,
                'height': self.camera.height,
                'fps': self.camera.fps,
                'exposure': self.camera.exposure,
                'brightness': self.camera.brightness,
                'contrast': self.camera.contrast,
                'saturation': self.camera.saturation,
                'sharpness': self.camera.sharpness,
                'gain': self.camera.gain,
            },
            'detection': {
                'confidence_threshold': self.detection.confidence_threshold,
                'mole_min_area': self.detection.mole_min_area,
                'mole_max_area': self.detection.mole_max_area,
                'mole_contrast_threshold': self.detection.mole_contrast_threshold,
                'mole_merge_distance': self.detection.mole_merge_distance,
                'mole_max_count': self.detection.mole_max_count,
                'mole_match_threshold': self.detection.mole_match_threshold,
                'lip_movement_threshold': self.detection.lip_movement_threshold,
            },
            'liveness': {
                'timeout': self.liveness.timeout,
                'liveness_threshold': self.liveness.liveness_threshold,
                'blink_weight': self.liveness.blink_weight,
                'lip_weight': self.liveness.lip_weight,
                'mole_weight': self.liveness.mole_weight,
            },
            'security': {
                'block_watchdog_timeout': self.security.block_watchdog_timeout,
            }
        }
        
        config_path.parent.mkdir(exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"✅ Настройки сохранены в {config_path}")


# ==============================================================================
# МОДУЛЬ 2: ЛОГИРОВАНИЕ (LOGGER)
# ==============================================================================

class LoggerManager:
    """Управление логами"""
    _instance = None
    _logger = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        config = Config()
        config.logs_dir.mkdir(exist_ok=True)
        
        log_file = config.logs_dir / f"face_lock_{datetime.now().strftime('%Y%m%d')}.log"
        
        self._logger = logging.getLogger("FaceLockPro")
        self._logger.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self._logger.addHandler(file_handler)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)
    
    def get_logger(self) -> logging.Logger:
        return self._logger


# ==============================================================================
# МОДУЛЬ 3: КРИПТОГРАФИЯ (CRYPTO)
# ==============================================================================

class CryptoManager:
    """Шифрование биометрических данных"""
    
    def __init__(self):
        config = Config()
        self.data_dir = config.data_dir
        
        # СНАЧАЛА задаем параметры
        self.iterations = config.security.encryption_iterations
        self.key_length = config.security.encryption_key_length
        
        # ПОТОМ инициализируем все остальное
        self.salt = self._get_or_create_salt()
        self.key = self._derive_key()
        self.logger = LoggerManager().get_logger()
    
    def _get_or_create_salt(self) -> bytes:
        salt_file = self.data_dir / ".salt"
        if salt_file.exists():
            with open(salt_file, 'rb') as f:
                return f.read()
        else:
            self.data_dir.mkdir(exist_ok=True)
            salt = secrets.token_bytes(32)
            with open(salt_file, 'wb') as f:
                f.write(salt)
            return salt
    
    def _derive_key(self) -> bytes:
        system_info = f"{os.getenv('COMPUTERNAME', '')}{os.getenv('USERNAME', '')}{os.getenv('PROCESSOR_IDENTIFIER', '')}"
        return hashlib.pbkdf2_hmac(
            'sha256',
            system_info.encode('utf-8'),
            self.salt,
            self.iterations,
            dklen=self.key_length
        )
    
    def encrypt_data(self, data_str: str) -> str:
        data_bytes = data_str.encode('utf-8')
        key_bytes = self.key * (len(data_bytes) // self.key_length + 1)
        encrypted = bytes(a ^ b for a, b in zip(data_bytes, key_bytes[:len(data_bytes)]))
        return encrypted.hex()
    
    def decrypt_data(self, encrypted_hex: str) -> str:
        try:
            encrypted_bytes = bytes.fromhex(encrypted_hex)
            key_bytes = self.key * (len(encrypted_bytes) // self.key_length + 1)
            decrypted = bytes(a ^ b for a, b in zip(encrypted_bytes, key_bytes[:len(encrypted_bytes)]))
            return decrypted.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Ошибка расшифровки: {e}")
            return ""
    
    def encrypt_dict(self, data: dict) -> str:
        return self.encrypt_data(json.dumps(data, ensure_ascii=False))
    
    def decrypt_dict(self, encrypted_hex: str) -> dict:
        json_str = self.decrypt_data(encrypted_hex)
        return json.loads(json_str) if json_str else {}


# ==============================================================================
# МОДУЛЬ 4: БЕЗОПАСНЫЙ BLOCKINPUT
# ==============================================================================

class SafeBlockInput:
    """Безопасная блокировка ввода с watchdog"""
    
    def __init__(self):
        self._blocked = False
        self._timer = None
        self._user32 = ctypes.windll.user32
        self.config = Config()
        self.logger = LoggerManager().get_logger()
        self._watchdog_timeout = self.config.security.block_watchdog_timeout
    
    def block(self, on: bool) -> bool:
        if on:
            def watchdog():
                time.sleep(self._watchdog_timeout)
                if self._blocked:
                    self.logger.warning(f"⚠️ Watchdog: принудительная разблокировка (таймаут {self._watchdog_timeout}с)")
                    self._user32.BlockInput(False)
                    self._blocked = False
            
            if self._timer:
                self._timer.cancel()
            
            result = self._user32.BlockInput(True)
            if result:
                self._blocked = True
                self._timer = threading.Timer(self._watchdog_timeout, watchdog)
                self._timer.daemon = True
                self._timer.start()
                return True
            return False
        else:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self._user32.BlockInput(False)
            self._blocked = False
            return True
    
    @property
    def is_blocked(self) -> bool:
        return self._blocked


# ==============================================================================
# МОДУЛЬ 5: КАМЕРА (CAMERA)
# ==============================================================================

class CameraManager:
    """Управление камерой"""
    
    def __init__(self):
        self.config = Config().camera
        self.logger = LoggerManager().get_logger()
        self.cap = None
        self.is_opened = False
        self.frame_count = 0
        self.current_fps = 0
        self._fps_counter = 0
        self._fps_time = time.time()
    
    def open(self) -> bool:
        try:
            self.cap = cv2.VideoCapture(self.config.device_id, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.logger.error(f"Не удалось открыть камеру {self.config.device_id}")
                return False
            
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.config.fps)
            
            if self.config.exposure is not None:
                self.cap.set(cv2.CAP_PROP_EXPOSURE, self.config.exposure)
            if self.config.brightness is not None:
                self.cap.set(cv2.CAP_PROP_BRIGHTNESS, self.config.brightness)
            if self.config.contrast is not None:
                self.cap.set(cv2.CAP_PROP_CONTRAST, self.config.contrast)
            if self.config.saturation is not None:
                self.cap.set(cv2.CAP_PROP_SATURATION, self.config.saturation)
            if self.config.sharpness is not None:
                self.cap.set(cv2.CAP_PROP_SHARPNESS, self.config.sharpness)
            if self.config.gain is not None:
                self.cap.set(cv2.CAP_PROP_GAIN, self.config.gain)
            
            self.is_opened = True
            self.logger.info(f"✅ Камера: {self.config.width}x{self.config.height} @ {self.config.fps}fps")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка камеры: {e}")
            return False
    
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self.cap or not self.is_opened:
            return False, None
        
        ret, frame = self.cap.read()
        if ret:
            self.frame_count += 1
            self._fps_counter += 1
            if time.time() - self._fps_time >= 1.0:
                self.current_fps = self._fps_counter
                self._fps_counter = 0
                self._fps_time = time.time()
            return True, frame
        
        return False, None
    
    def get_settings(self) -> dict:
        if not self.cap:
            return {}
        return {
            'width': int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            'height': int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            'fps': int(self.cap.get(cv2.CAP_PROP_FPS)),
            'brightness': self.cap.get(cv2.CAP_PROP_BRIGHTNESS),
            'contrast': self.cap.get(cv2.CAP_PROP_CONTRAST),
        }
    
    def release(self):
        if self.cap:
            self.cap.release()
            self.is_opened = False
            self.logger.info("Камера освобождена")


# ==============================================================================
# МОДУЛЬ 6: ДЕТЕКТОР ЛИЦА (FACE DETECTOR)
# ==============================================================================

class FaceDetector:
    """Детекция лица через MediaPipe"""
    
    _instance = None
    _landmarker = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        self.config = Config()
        self.logger = LoggerManager().get_logger()
        self._landmarker = None
        
        BaseOptions = mp.tasks.BaseOptions
        self.FaceLandmarker = mp.tasks.vision.FaceLandmarker
        self.FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
        self.VisionRunningMode = mp.tasks.vision.RunningMode
        
        self._load_model()
    
    def _load_model(self):
        if not self.config.face_model.exists():
            self.logger.error(f"Модель лица не найдена: {self.config.face_model}")
            return
        
        try:
            options = self.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(
                    model_asset_path=str(self.config.face_model)
                ),
                running_mode=self.VisionRunningMode.VIDEO,
                num_faces=self.config.detection.num_faces,
                min_face_detection_confidence=self.config.detection.min_face_detection_confidence,
                min_face_presence_confidence=self.config.detection.min_face_presence_confidence,
                min_tracking_confidence=self.config.detection.min_tracking_confidence
            )
            self._landmarker = self.FaceLandmarker.create_from_options(options)
            self.logger.info("✅ Модель лица загружена")
        except Exception as e:
            self.logger.error(f"Ошибка загрузки модели лица: {e}")
    
    def detect(self, rgb_image: np.ndarray) -> Optional:
        if self._landmarker is None:
            return None
        
        try:
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
            res = self._landmarker.detect_for_video(img, int(time.time() * 1000))
            if res and res.face_landmarks:
                return res.face_landmarks[0]
            return None
        except Exception as e:
            self.logger.debug(f"Ошибка детекции лица: {e}")
            return None
    
    def get_points_128(self, points, h: int, w: int) -> List[Tuple[int, int]]:
        result = []
        step = 468 / 128
        for i in range(128):
            idx = int(i * step)
            if idx < 468:
                result.append((int(points[idx].x * w), int(points[idx].y * h)))
        return result
    
    def get_points_all(self, points, h: int, w: int) -> List[Tuple[int, int]]:
        return [(int(points[i].x * w), int(points[i].y * h)) for i in range(468)]
    
    @staticmethod
    def check_models() -> bool:
        config = Config()
        missing = []
        if not config.face_model.exists():
            missing.append(f"face_landmarker.task -> {config.models_dir}")
        if not config.hand_model.exists():
            missing.append(f"hand_landmarker.task -> {config.models_dir}")
        
        if missing:
            print("\n" + "=" * 60)
            print("❌ ОТСУТСТВУЮТ МОДЕЛИ:")
            for m in missing:
                print(f"   • {m}")
            print(f"\n📁 Скачайте модели в папку: {config.models_dir}")
            print("=" * 60 + "\n")
            return False
        return True


# ==============================================================================
# МОДУЛЬ 7: ДЕТЕКТОР РУКИ (HAND DETECTOR)
# ==============================================================================

class HandDetector:
    """Детекция руки через MediaPipe"""
    
    _instance = None
    _landmarker = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        self.config = Config()
        self.logger = LoggerManager().get_logger()
        self._landmarker = None
        
        self.HandLandmarker = mp.tasks.vision.HandLandmarker
        self.HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
        self.VisionRunningMode = mp.tasks.vision.RunningMode
        
        self._load_model()
    
    def _load_model(self):
        if not self.config.hand_model.exists():
            return
        
        try:
            options = self.HandLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(
                    model_asset_path=str(self.config.hand_model)
                ),
                running_mode=self.VisionRunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=self.config.detection.min_hand_detection_confidence,
                min_hand_presence_confidence=self.config.detection.min_hand_presence_confidence,
                min_tracking_confidence=self.config.detection.min_tracking_confidence
            )
            self._landmarker = self.HandLandmarker.create_from_options(options)
            self.logger.info("✅ Модель руки загружена")
        except Exception as e:
            self.logger.error(f"Ошибка загрузки модели руки: {e}")
    
    def detect(self, rgb_image: np.ndarray) -> Optional:
        if self._landmarker is None:
            return None
        
        try:
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
            res = self._landmarker.detect_for_video(img, int(time.time() * 1000))
            if res and res.hand_landmarks:
                return res.hand_landmarks[0]
            return None
        except:
            return None
    
    def get_points(self, points, h: int, w: int) -> List[Tuple[int, int]]:
        return [(int(points[i].x * w), int(points[i].y * h)) for i in range(21)]


# ==============================================================================
# МОДУЛЬ 8: ДЕТЕКТОР РОДИНОК (MOLES DETECTOR)
# ==============================================================================

class MoleDetector:
    """Детекция родинок и шрамов на лице"""
    
    def __init__(self):
        self.config = Config()
        self.logger = LoggerManager().get_logger()
        self.moles = []
        self.mole_positions = []
    
    def detect_moles(self, frame: np.ndarray, face_roi: Optional[Tuple[int, int, int, int]] = None) -> List[Tuple[int, int, int, float]]:
        if frame is None:
            return []
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        if face_roi is not None:
            x, y, w, h = face_roi
            roi = gray[y:y+h, x:x+w]
        else:
            roi = gray
            x, y = 0, 0
        
        if roi.size == 0:
            return []
        
        blurred = cv2.GaussianBlur(roi, (5, 5), 0)
        diff = cv2.absdiff(roi, blurred)
        _, threshold = cv2.threshold(diff, self.config.detection.mole_contrast_threshold, 255, cv2.THRESH_BINARY)
        
        kernel = np.ones((3, 3), np.uint8)
        threshold = cv2.morphologyEx(threshold, cv2.MORPH_OPEN, kernel, iterations=1)
        threshold = cv2.morphologyEx(threshold, cv2.MORPH_CLOSE, kernel, iterations=2)
        
        contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        detected = []
        h_roi, w_roi = roi.shape
        
        for contour in contours:
            area = cv2.contourArea(contour)
            min_area = self.config.detection.mole_min_area
            max_area = self.config.detection.mole_max_area
            
            if area < min_area or area > max_area:
                continue
            
            (cx, cy), radius = cv2.minEnclosingCircle(contour)
            cx, cy = int(cx), int(cy)
            radius = int(radius)
            
            if cy < h_roi * 0.2 or cy > h_roi * 0.85:
                continue
            if cx < w_roi * 0.1 or cx > w_roi * 0.9:
                continue
            
            if self._is_dark_spot(roi, cx, cy, radius):
                abs_x = x + cx
                abs_y = y + cy
                confidence = self._calculate_confidence(roi, cx, cy, radius)
                
                if confidence > 0.3:
                    detected.append((abs_x, abs_y, radius, confidence))
        
        detected = self._merge_nearby(detected)
        detected.sort(key=lambda x: x[3], reverse=True)
        
        self.moles = detected[:self.config.detection.mole_max_count]
        self.mole_positions = [(x, y) for x, y, _, _ in self.moles]
        
        return self.moles
    
    def _is_dark_spot(self, roi: np.ndarray, cx: int, cy: int, radius: int) -> bool:
        h, w = roi.shape
        if cx - radius < 0 or cx + radius >= w or cy - radius < 0 or cy + radius >= h:
            return False
        
        mask = np.zeros_like(roi)
        cv2.circle(mask, (cx, cy), radius, 255, -1)
        inner = roi[mask > 0]
        
        if len(inner) < 5:
            return False
        
        mask_outer = np.zeros_like(roi)
        cv2.circle(mask_outer, (cx, cy), radius * 2, 255, -1)
        cv2.circle(mask_outer, (cx, cy), radius, 0, -1)
        outer = roi[mask_outer > 0]
        
        if len(outer) < 10:
            return False
        
        return (np.mean(outer) - np.mean(inner)) > 10
    
    def _calculate_confidence(self, roi: np.ndarray, cx: int, cy: int, radius: int) -> float:
        h, w = roi.shape
        if cx - radius < 0 or cx + radius >= w or cy - radius < 0 or cy + radius >= h:
            return 0.0
        
        mask = np.zeros_like(roi)
        cv2.circle(mask, (cx, cy), radius, 255, -1)
        inner = roi[mask > 0]
        
        if len(inner) < 5:
            return 0.0
        
        mask_outer = np.zeros_like(roi)
        cv2.circle(mask_outer, (cx, cy), radius * 2, 255, -1)
        cv2.circle(mask_outer, (cx, cy), radius, 0, -1)
        outer = roi[mask_outer > 0]
        
        if len(outer) < 10:
            return 0.0
        
        contrast = (np.mean(outer) - np.mean(inner)) / (np.mean(outer) + 1)
        return min(1.0, max(0.0, contrast * 2))
    
    def _merge_nearby(self, moles: List, distance: int = None) -> List:
        if distance is None:
            distance = self.config.detection.mole_merge_distance
        
        if not moles:
            return []
        
        merged = []
        used = [False] * len(moles)
        
        for i, mole in enumerate(moles):
            if used[i]:
                continue
            
            group = [mole]
            used[i] = True
            
            for j in range(i + 1, len(moles)):
                if used[j]:
                    continue
                
                dx = mole[0] - moles[j][0]
                dy = mole[1] - moles[j][1]
                if np.sqrt(dx*dx + dy*dy) < distance:
                    group.append(moles[j])
                    used[j] = True
            
            if len(group) == 1:
                merged.append(group[0])
            else:
                merged.append((
                    int(np.mean([m[0] for m in group])),
                    int(np.mean([m[1] for m in group])),
                    int(np.mean([m[2] for m in group])),
                    np.mean([m[3] for m in group])
                ))
        
        return merged
    
    def draw_moles(self, frame: np.ndarray, color: Tuple[int, int, int] = None, draw_labels: bool = True) -> np.ndarray:
        if color is None:
            color = Config().ui.color_moles
        
        for i, (x, y, radius, confidence) in enumerate(self.moles):
            cv2.circle(frame, (x, y), radius, color, 1)
            cv2.circle(frame, (x, y), 1, color, 2)
            
            if draw_labels:
                label = f"M{i+1}: {confidence:.2f}"
                cv2.putText(frame, label, (x + radius + 5, y - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)
        
        cv2.putText(frame, f"MOLES: {len(self.moles)}", (10, 260),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        
        return frame


# ==============================================================================
# МОДУЛЬ 9: ДЕТЕКТОР ДВИЖЕНИЯ ГУБ (LIPS DETECTOR)
# ==============================================================================

class LipMovementDetector:
    """Детекция движения губ для анти-спуфинга"""
    
    def __init__(self):
        self.config = Config()
        self.logger = LoggerManager().get_logger()
        
        self.LIP_TOP = [61, 62, 63, 64, 65, 66, 67, 78, 80, 81, 82, 84, 87, 88, 91, 95]
        self.LIP_BOTTOM = [76, 77, 78, 79, 80, 81, 82, 84, 85, 86, 87, 88, 89, 90, 95, 96]
        
        self.history = deque(maxlen=30)
        self.movement_buffer = deque(maxlen=10)
        self.speech_detected = False
        self.MOVEMENT_THRESHOLD = self.config.detection.lip_movement_threshold
    
    def extract_features(self, points) -> Optional[dict]:
        if not points:
            return None
        
        lip_points = []
        for idx in self.LIP_TOP + self.LIP_BOTTOM:
            if idx < len(points):
                lip_points.append((points[idx].x, points[idx].y))
        
        if len(lip_points) < 10:
            return None
        
        n_top = len(self.LIP_TOP)
        top_points = np.array(lip_points[:n_top])
        bottom_points = np.array(lip_points[n_top:])
        
        left_corner = np.array([points[61].x, points[61].y])
        right_corner = np.array([points[291].x, points[291].y])
        mouth_width = np.linalg.norm(right_corner - left_corner)
        
        top_center = np.mean(top_points, axis=0)
        bottom_center = np.mean(bottom_points, axis=0)
        mouth_height = np.linalg.norm(top_center - bottom_center)
        
        aspect_ratio = mouth_height / (mouth_width + 0.001)
        mouth_area = mouth_width * mouth_height
        
        return {
            'width': mouth_width,
            'height': mouth_height,
            'aspect_ratio': aspect_ratio,
            'area': mouth_area,
            'closure': min(1.0, aspect_ratio / 0.3)
        }
    
    def detect_movement(self, features: dict) -> Tuple[bool, float]:
        if not features:
            self.history.clear()
            return False, 0.0
        
        self.history.append(features)
        
        if len(self.history) < 5:
            return False, 0.0
        
        movements = []
        for i in range(1, len(self.history)):
            prev = self.history[i-1]
            curr = self.history[i]
            dw = abs(curr['width'] - prev['width'])
            dh = abs(curr['height'] - prev['height'])
            da = abs(curr['area'] - prev['area'])
            movement = dw * 0.3 + dh * 0.5 + da * 0.2
            movements.append(movement)
        
        if not movements:
            return False, 0.0
        
        avg_movement = np.mean(movements)
        
        if avg_movement > self.MOVEMENT_THRESHOLD:
            self.movement_buffer.append(avg_movement)
            return True, avg_movement
        
        return False, avg_movement
    
    def detect_speech(self) -> bool:
        if len(self.history) < 10:
            return False
        
        closure = [f['closure'] for f in list(self.history)[-10:]]
        changes = [abs(closure[i] - closure[i-1]) for i in range(1, len(closure))]
        
        if not changes:
            return False
        
        avg_change = np.mean(changes)
        max_change = np.max(changes)
        
        if avg_change > 0.15 and max_change > 0.3:
            self.speech_detected = True
            return True
        
        self.speech_detected = False
        return False


# ==============================================================================
# МОДУЛЬ 10: ПРОВЕРКА ЖИВОСТИ (LIVENESS)
# ==============================================================================

class LivenessChecker:
    """Проверка живости с Challenge-Response"""
    
    def __init__(self):
        self.config = Config()
        self.logger = LoggerManager().get_logger()
        
        self.blink_history = deque(maxlen=20)
        self.smile_history = deque(maxlen=20)
        self.total_blinks = 0
        self.eye_open = True
        self.challenge_phase = "idle"
        self.challenge_type = None
        self.challenge_time = 0
        self.challenge_attempts = 0
        self.head_positions = deque(maxlen=30)
        self.blink_pattern = deque(maxlen=10)
        
        self.lip_history = deque(maxlen=30)
        self.liveness_score = 0.0
        self.mole_match_score = 0.0
        
        self.challenges = {
            "blink_twice": self._check_blink_sequence,
            "smile": self._check_smile,
            "turn_left": self._check_head_turn,
            "turn_right": self._check_head_turn,
            "speak": self._check_speech,
        }
        
        self.lip_detector = LipMovementDetector()
    
    def _check_blink_sequence(self, points) -> bool:
        if len(self.blink_pattern) < 3:
            return False
        pattern = list(self.blink_pattern)
        blink_count = 0
        for i in range(1, len(pattern)):
            if pattern[i-1] and not pattern[i]:
                blink_count += 1
        return blink_count >= 2
    
    def _check_smile(self, points) -> bool:
        if not points:
            return False
        top = np.mean([[points[i].x, points[i].y] for i in [61, 62, 63, 64, 65, 66, 67]], axis=0)
        bottom = np.mean([[points[i].x, points[i].y] for i in [76, 77, 78, 79, 80, 81, 82]], axis=0)
        left = np.array([points[61].x, points[61].y])
        right = np.array([points[291].x, points[291].y])
        mouth_h = np.linalg.norm(top - bottom)
        mouth_w = np.linalg.norm(left - right)
        return (mouth_h / mouth_w) > 0.45
    
    def _check_head_turn(self, points, direction="left") -> bool:
        if not points:
            return False
        nose_tip = points[1]
        nose_bridge = points[168]
        dx = nose_tip.x - nose_bridge.x
        if direction == "left" and dx < -0.05:
            return True
        elif direction == "right" and dx > 0.05:
            return True
        return False
    
    def _check_speech(self, points) -> bool:
        if not points:
            return False
        features = self.lip_detector.extract_features(points)
        if features:
            return self.lip_detector.detect_speech()
        return False
    
    def get_ear(self, points, side) -> float:
        if side == 'left':
            idx = [33, 133, 157, 158, 159, 160, 161, 173]
        else:
            idx = [362, 263, 387, 386, 385, 384, 398, 466]
        pts = np.array([[points[i].x, points[i].y] for i in idx])
        v1 = np.linalg.norm(pts[1] - pts[5])
        v2 = np.linalg.norm(pts[2] - pts[4])
        h = np.linalg.norm(pts[0] - pts[3])
        return (v1 + v2) / (2.0 * h)
    
    def is_smiling(self, points) -> bool:
        top = np.mean([[points[i].x, points[i].y] for i in [61, 62, 63, 64, 65, 66, 67]], axis=0)
        bottom = np.mean([[points[i].x, points[i].y] for i in [76, 77, 78, 79, 80, 81, 82]], axis=0)
        left = np.array([points[61].x, points[61].y])
        right = np.array([points[291].x, points[291].y])
        mouth_h = np.linalg.norm(top - bottom)
        mouth_w = np.linalg.norm(left - right)
        return (mouth_h / mouth_w) > 0.4
    
    def check_lip_movement(self, points) -> Tuple[bool, float]:
        if not points:
            return False, 0.0
        
        features = self.lip_detector.extract_features(points)
        if not features:
            return False, 0.0
        
        has_movement, movement_score = self.lip_detector.detect_movement(features)
        has_speech = self.lip_detector.detect_speech()
        
        score = 0.0
        if has_movement:
            score += 0.6
        if has_speech:
            score += 0.4
        
        return (score > 0.3), score
    
    def verify_moles(self, current_moles: List, saved_moles_data: dict) -> Tuple[bool, float]:
        if not saved_moles_data or not current_moles:
            return False, 0.0
        
        saved_moles = saved_moles_data.get('moles', [])
        if not saved_moles:
            return True, 1.0
        
        matches = 0
        for saved in saved_moles:
            sx, sy = saved[0], saved[1]
            for curr in current_moles:
                cx, cy = curr[0], curr[1]
                if np.sqrt((sx - cx)**2 + (sy - cy)**2) < 20:
                    matches += 1
                    break
        
        match_ratio = matches / max(1, len(saved_moles))
        self.mole_match_score = match_ratio
        
        threshold = self.config.detection.mole_match_threshold
        return match_ratio >= threshold, match_ratio
    
    def check(self, points, frame: np.ndarray = None, moles: List = None, saved_moles: dict = None) -> Tuple[bool, str]:
        if not points:
            return False, "No face"
        
        left = self.get_ear(points, 'left')
        right = self.get_ear(points, 'right')
        avg = (left + right) / 2
        
        if avg < self.config.liveness.blink_threshold:
            if self.eye_open:
                self.total_blinks += 1
                self.eye_open = False
                self.blink_pattern.append(False)
        else:
            self.eye_open = True
            self.blink_pattern.append(True)
        
        self.blink_history.append(avg)
        smile = self.is_smiling(points)
        self.smile_history.append(smile)
        
        if points and hasattr(points[1], 'x'):
            self.head_positions.append(points[1].x)
        
        if len(self.blink_history) >= self.config.liveness.min_blink_history:
            blink_std = np.std(self.blink_history)
            if blink_std < 0.001 and not any(self.smile_history):
                return False, "No movement (maybe photo)"
            
            if len(self.head_positions) > 10:
                head_std = np.std(self.head_positions)
                if head_std < 0.001:
                    return False, "Head is static (suspicious)"
        
        lip_ok, lip_score = self.check_lip_movement(points)
        self.lip_history.append(lip_ok)
        
        mole_ok = False
        mole_score = 0.0
        if moles and saved_moles:
            mole_ok, mole_score = self.verify_moles(moles, saved_moles)
        
        blink_score = min(1.0, len(self.blink_history) / self.config.liveness.min_blink_history)
        smile_score = 0.5 if any(self.smile_history) else 0.0
        base_score = (blink_score * 0.5 + smile_score * 0.5)
        
        lip_score_adj = lip_score * 0.5 + (0.5 if lip_ok else 0.0)
        mole_score_adj = mole_score if saved_moles and saved_moles.get('moles') else 1.0
        
        self.liveness_score = (
            base_score * self.config.liveness.blink_weight +
            lip_score_adj * self.config.liveness.lip_weight +
            mole_score_adj * self.config.liveness.mole_weight
        )
        
        if self.total_blinks > 3 and self.challenge_phase == "idle" and self.liveness_score < 0.6:
            import random
            challenges = ["blink_twice", "smile", "turn_left", "turn_right", "speak"]
            self.challenge_type = random.choice(challenges)
            self.challenge_phase = "challenge"
            self.challenge_time = time.time()
            self.challenge_attempts += 1
            self.logger.info(f"🔐 CHALLENGE: {self.challenge_type}")
            return True, f"Challenge: {self.challenge_type}"
        
        if self.challenge_phase == "challenge":
            elapsed = time.time() - self.challenge_time
            if elapsed > self.config.liveness.challenge_timeout:
                self.challenge_phase = "idle"
                return False, "Challenge timeout"
            
            if self.challenge_type == "blink_twice" and self._check_blink_sequence(points):
                self.challenge_phase = "idle"
                self.liveness_score = max(self.liveness_score, 0.8)
                return True, "Challenge: blink twice ✓"
            elif self.challenge_type == "smile" and self._check_smile(points):
                self.challenge_phase = "idle"
                self.liveness_score = max(self.liveness_score, 0.8)
                return True, "Challenge: smile ✓"
            elif self.challenge_type == "turn_left" and self._check_head_turn(points, "left"):
                self.challenge_phase = "idle"
                self.liveness_score = max(self.liveness_score, 0.8)
                return True, "Challenge: turn left ✓"
            elif self.challenge_type == "turn_right" and self._check_head_turn(points, "right"):
                self.challenge_phase = "idle"
                self.liveness_score = max(self.liveness_score, 0.8)
                return True, "Challenge: turn right ✓"
            elif self.challenge_type == "speak" and self._check_speech(points):
                self.challenge_phase = "idle"
                self.liveness_score = max(self.liveness_score, 0.9)
                return True, "Challenge: speak ✓"
        
        if self.liveness_score >= self.config.liveness.liveness_threshold:
            return True, f"Alive (score: {self.liveness_score:.2f})"
        else:
            return False, f"Low score: {self.liveness_score:.2f}"


# ==============================================================================
# МОДУЛЬ 11: ХРАНИЛИЩЕ ДАННЫХ (STORAGE)
# ==============================================================================

class DataManager:
    """Сохранение и загрузка биометрических данных"""
    
    def __init__(self):
        self.config = Config()
        self.logger = LoggerManager().get_logger()
        self.crypto = CryptoManager()
    
    def save_shadowprint(self, frame: np.ndarray, points: List, photo_path: Path, json_path: Path) -> bool:
        if not points:
            return False
        
        try:
            self.config.data_dir.mkdir(exist_ok=True)
            test_file = self.config.data_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
        except PermissionError:
            self.logger.error("❌ Нет прав на запись!")
            return False
        
        bg = np.zeros_like(frame)
        n = len(points)
        for i in range(n):
            dists = []
            for j in range(n):
                if i == j: continue
                d = np.linalg.norm(np.array(points[i]) - np.array(points[j]))
                dists.append((d, j))
            dists.sort(key=lambda x: x[0])
            for k in range(min(self.config.num_neighbors, len(dists))):
                j = dists[k][1]
                pt1 = (int(points[i][0]), int(points[i][1]))
                pt2 = (int(points[j][0]), int(points[j][1]))
                cv2.line(bg, pt1, pt2, (255, 255, 255), 1)
        
        for pt in points:
            x, y = int(pt[0]), int(pt[1])
            cv2.circle(bg, (x, y), self.config.ui.point_size, (255, 255, 255), -1)
        
        cv2.imwrite(str(photo_path), bg)
        
        data = {
            "points": [(float(x), float(y)) for x, y in points],
            "distances": self._compute_distances(points),
            "count": len(points),
            "timestamp": time.time(),
            "version": "3.0"
        }
        
        encrypted = self.crypto.encrypt_dict(data)
        with open(json_path, 'w', encoding='utf-8') as f:
            f.write(encrypted)
        
        self.logger.info(f"✅ Данные сохранены в {json_path}")
        return True
    
    def save_moles(self, moles: List, photo_path: Path, json_path: Path) -> bool:
        if not moles:
            self.logger.warning("Нет родинок для сохранения")
            return False
        
        try:
            bg = np.zeros((480, 640, 3), dtype=np.uint8)
            for x, y, radius, confidence in moles:
                cv2.circle(bg, (x, y), radius, (0, 0, 255), 1)
                cv2.circle(bg, (x, y), 2, (0, 0, 255), -1)
                cv2.putText(bg, f"{confidence:.2f}", (x + radius + 5, y - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 255), 1)
            
            cv2.imwrite(str(photo_path), bg)
            
            data = {
                "moles": [(int(x), int(y), int(radius), float(conf)) for x, y, radius, conf in moles],
                "count": len(moles),
                "timestamp": time.time(),
                "version": "1.0"
            }
            
            encrypted = self.crypto.encrypt_dict(data)
            with open(json_path, 'w', encoding='utf-8') as f:
                f.write(encrypted)
            
            self.logger.info(f"✅ Родинки сохранены: {len(moles)} шт.")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка сохранения родинок: {e}")
            return False
    
    def load_moles(self, json_path: Path) -> dict:
        if not json_path.exists():
            return {}
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                encrypted = f.read().strip()
            return self.crypto.decrypt_dict(encrypted)
        except Exception as e:
            self.logger.error(f"Ошибка загрузки родинок: {e}")
            return {}
    
    def verify_shadowprint(self, points: List, json_path: Path) -> Tuple[bool, str]:
        if not json_path.exists():
            return False, "No data"
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                encrypted = f.read().strip()
            
            ref = self.crypto.decrypt_dict(encrypted)
            
            if len(points) != len(ref["points"]):
                return False, f"Points mismatch ({len(points)} vs {len(ref['points'])})"
            
            current = self._compute_distances(points)
            if not self._compare_distances(current, ref["distances"], self.config.distance_tolerance):
                return False, "Distances mismatch"
            
            return True, "OK"
        except Exception as e:
            self.logger.error(f"Verification error: {e}")
            return False, f"Error: {str(e)}"
    
    def _compute_distances(self, points: List) -> List:
        n = len(points)
        dists = []
        for i in range(n):
            for j in range(i+1, n):
                d = np.linalg.norm(np.array(points[i]) - np.array(points[j]))
                dists.append((i, j, float(d)))
        return dists
    
    def _compare_distances(self, d1: List, d2: List, tolerance: float) -> bool:
        if len(d1) != len(d2):
            return False
        for (i, j, a), (_, _, b) in zip(d1, d2):
            if abs(a - b) > tolerance:
                return False
        return True


# ==============================================================================
# МОДУЛЬ 12: UI И ОТРИСОВКА
# ==============================================================================

class UIManager:
    """Управление UI и отрисовкой"""
    
    def __init__(self):
        self.config = Config()
        self.logger = LoggerManager().get_logger()
        
        self.block_enabled = True
        self.restart_requested = False
        
        self.buttons = [
            {"x": 10, "y": 70, "w": 120, "h": 30, "text": "REGISTER", "action": "register"},
            {"x": 140, "y": 70, "w": 120, "h": 30, "text": "DELETE", "action": "delete"},
            {"x": 270, "y": 70, "w": 160, "h": 30, "text": "BLOCK: ON", "action": "toggle_block"},
        ]
    
    def draw_buttons(self, frame: np.ndarray):
        for btn in self.buttons:
            if btn["action"] == "toggle_block":
                color = (0, 255, 0) if self.block_enabled else (0, 0, 255)
            else:
                color = (100, 100, 200)
            
            cv2.rectangle(frame, (btn["x"], btn["y"]), (btn["x"] + btn["w"], btn["y"] + btn["h"]), color, -1)
            cv2.rectangle(frame, (btn["x"], btn["y"]), (btn["x"] + btn["w"], btn["y"] + btn["h"]), (255, 255, 255), 1)
            
            if btn["action"] == "toggle_block":
                btn["text"] = "BLOCK: ON" if self.block_enabled else "BLOCK: OFF"
            
            cv2.putText(frame, btn["text"], (btn["x"] + 10, btn["y"] + 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    
    def draw_spiderweb(self, frame: np.ndarray, points: List, color: Tuple[int, int, int]):
        if not points:
            return
        
        n = len(points)
        for i in range(n):
            dists = []
            for j in range(n):
                if i == j: continue
                d = np.linalg.norm(np.array(points[i]) - np.array(points[j]))
                dists.append((d, j))
            dists.sort(key=lambda x: x[0])
            for k in range(min(self.config.num_neighbors, len(dists))):
                j = dists[k][1]
                pt1 = (int(points[i][0]), int(points[i][1]))
                pt2 = (int(points[j][0]), int(points[j][1]))
                cv2.line(frame, pt1, pt2, color, 1)
        
        for pt in points:
            x, y = int(pt[0]), int(pt[1])
            cv2.circle(frame, (x, y), self.config.ui.point_size, (255, 255, 255), 1)
            cv2.circle(frame, (x, y), self.config.ui.point_size - 1, (0, 255, 0), -1)
    
    def mouse_callback(self, event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        
        if param.get("show_restart", False):
            rx, ry, rw, rh = 10, 250, 120, 40
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self.restart_requested = True
                self.logger.info("🔄 RESTART")
                return
        
        for btn in self.buttons:
            if btn["x"] <= x <= btn["x"] + btn["w"] and btn["y"] <= y <= btn["y"] + btn["h"]:
                if btn["action"] == "register":
                    param["register"] = True
                elif btn["action"] == "delete":
                    param["delete"] = True
                    param["delete_start"] = time.time()
                elif btn["action"] == "toggle_block":
                    self.block_enabled = not self.block_enabled
                    safe_block = SafeBlockInput()
                    safe_block.block(self.block_enabled)


# ==============================================================================
# МОДУЛЬ 13: АНТИ-СПУФИНГ (ANTI-SPOOFING)
# ==============================================================================

class AntiSpoofing:
    """Защита от спуфинга"""
    
    def __init__(self):
        self.config = Config()
        self.logger = LoggerManager().get_logger()
        self.frame_hashes = deque(maxlen=30)
        self.replay_detected = False
    
    def detect_replay(self, frame: np.ndarray) -> bool:
        frame_hash = hashlib.md5(frame.tobytes()).hexdigest()
        if frame_hash in self.frame_hashes:
            self.replay_detected = True
            self.logger.warning("🚨 REPLAY ATTACK DETECTED")
            return True
        self.frame_hashes.append(frame_hash)
        self.replay_detected = False
        return False
    
    def detect_deepfake(self, frame: np.ndarray) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])
        
        if edge_density < self.config.security.deepfake_edge_min or edge_density > self.config.security.deepfake_edge_max:
            self.logger.warning(f"⚠️ Deepfake suspected: edge_density={edge_density:.3f}")
            return True
        return False


# ==============================================================================
# МОДУЛЬ 14: ГЛАВНОЕ ПРИЛОЖЕНИЕ (MAIN APP)
# ==============================================================================

class FaceLockApp:
    """Главное приложение"""
    
    def __init__(self):
        self.config = Config()
        self.logger = LoggerManager().get_logger()
        
        self.camera = CameraManager()
        self.face_detector = FaceDetector()
        self.hand_detector = HandDetector()
        self.mole_detector = MoleDetector()
        self.liveness = LivenessChecker()
        self.data_manager = DataManager()
        self.ui = UIManager()
        self.anti_spoof = AntiSpoofing()
        self.safe_block = SafeBlockInput()
        
        self.running = True
        self.access_granted = False
        self.liveness_ok = False
        self.liveness_checked = False
        self.show_restart = False
        self.liveness_start_time = time.time()
        self.restart_timer_start = 0
        self.restart_countdown = self.config.liveness.restart_timeout
        
        self.last_face_points = []
        self.last_hand_points = []
        self.face_pts = None
        self.frame_count = 0
        
        self.saved_moles = {}
    
    def run(self):
        if not self.camera.open():
            self.logger.error("❌ Не удалось открыть камеру!")
            input("Нажмите Enter для выхода...")
            return
        
        self.saved_moles = self.data_manager.load_moles(self.config.moles_json)
        
        cv2.namedWindow(self.config.ui.window_title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.config.ui.window_title, self.config.ui.window_width, self.config.ui.window_height)
        
        param = {"register": False, "delete": False, "delete_start": 0, "show_restart": False}
        cv2.setMouseCallback(self.config.ui.window_title, self.ui.mouse_callback, param)
        
        self.logger.info("🚀 Приложение запущено")
        self.logger.info(f"📁 Данные: {self.config.data_dir}")
        self.logger.info(f"📁 Модели: {self.config.models_dir}")
        
        while self.running:
            ret, frame = self.camera.read()
            if not ret:
                continue
            
            self.frame_count += 1
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = frame.shape[:2]
            
            # Анти-спуфинг
            if self.anti_spoof.detect_replay(frame):
                cv2.putText(frame, "⚠️ REPLAY ATTACK", (10, 350),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            
            if self.anti_spoof.detect_deepfake(frame):
                cv2.putText(frame, "⚠️ DEEPFAKE", (10, 380),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            
            # Обработка кнопок
            if param["register"]:
                self._handle_register(frame, param)
            
            if param["delete"]:
                self._handle_delete(param)
            
            # Детекция
            self.face_pts = self.face_detector.detect(rgb)
            face_points_display = []
            hand_points_display = []
            
            if self.face_pts:
                face_points_display = self.face_detector.get_points_128(self.face_pts, h, w)
                self.last_face_points = face_points_display
                
                if self.frame_count % 3 == 0:
                    self.mole_detector.detect_moles(frame)
                
                if self.mole_detector.moles:
                    self.mole_detector.draw_moles(frame, color=self.config.ui.color_moles)
                
                hand_pts = self.hand_detector.detect(rgb)
                if hand_pts:
                    hand_points_display = self.hand_detector.get_points(hand_pts, h, w)
                    self.last_hand_points = hand_points_display
            
            # Проверка живости
            if not self.liveness_checked and not self.show_restart:
                if self.face_pts:
                    live_ok, live_msg = self.liveness.check(
                        self.face_pts, 
                        frame, 
                        self.mole_detector.moles,
                        self.saved_moles
                    )
                    
                    if self.liveness.challenge_phase == "challenge":
                        cv2.putText(frame, f"DO: {self.liveness.challenge_type}", (10, 310),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                        
                        elapsed = time.time() - self.liveness.challenge_time
                        remaining = max(0, self.config.liveness.challenge_timeout - elapsed)
                        cv2.putText(frame, f"Time: {remaining:.1f}s", (10, 340),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                    
                    if live_ok:
                        self.liveness_ok = True
                        self.liveness_checked = True
                        self.logger.info(f"✅ Liveness OK (score: {self.liveness.liveness_score:.2f})")
                    else:
                        elapsed = time.time() - self.liveness_start_time
                        if elapsed > self.config.liveness.timeout:
                            self.liveness_checked = True
                            self.liveness_ok = False
                            self.restart_timer_start = time.time()
                            self.logger.warning(f"❌ Liveness FAIL: {live_msg}")
                else:
                    elapsed = time.time() - self.liveness_start_time
                    if elapsed > self.config.liveness.timeout:
                        self.liveness_checked = True
                        self.liveness_ok = False
                        self.restart_timer_start = time.time()
                        self.logger.warning("❌ Face not found!")
            
            # Отрисовка
            if self.last_face_points:
                self.ui.draw_spiderweb(frame, self.last_face_points, self.config.ui.color_face)
            if self.last_hand_points:
                self.ui.draw_spiderweb(frame, self.last_hand_points, self.config.ui.color_hand)
            
            y_status = 160
            if self.liveness_ok:
                cv2.putText(frame, f"LIVENESS: OK ({self.liveness.liveness_score:.2f})", (10, y_status),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            elif self.liveness_checked and not self.liveness_ok:
                if not self.show_restart:
                    elapsed = time.time() - self.restart_timer_start
                    remaining = max(0, self.restart_countdown - elapsed)
                    cv2.putText(frame, f"⚠️ LIVENESS FAIL: {remaining:.1f}s", (10, y_status),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                    if remaining <= 0:
                        self.show_restart = True
                        param["show_restart"] = True
                        self.logger.info("🔴 RESTART button available")
                else:
                    cv2.putText(frame, "⚠️ LIVENESS FAIL", (10, y_status),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            else:
                remaining = max(0, self.config.liveness.timeout - (time.time() - self.liveness_start_time))
                cv2.putText(frame, f"LIVENESS: {remaining:.1f}s", (10, y_status),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 2)
            
            moles_status = f"MOLES: {len(self.mole_detector.moles)} found"
            cv2.putText(frame, moles_status, (10, 195),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, self.config.ui.color_moles, 1)
            
            if self.config.moles_json.exists():
                cv2.putText(frame, "🔴 MOLES SAVED", (10, 215),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
            
            if self.show_restart:
                rx, ry, rw, rh = 10, 250, 120, 40
                cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (0, 0, 255), -1)
                cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (255, 255, 255), 2)
                cv2.putText(frame, "RESTART", (rx + 15, ry + 28),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            if self.access_granted:
                cv2.putText(frame, "ACCESS GRANTED", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            elif self.config.face_json.exists() and self.last_face_points:
                cv2.putText(frame, "ACCESS DENIED", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            elif not self.config.face_json.exists() and self.last_face_points:
                cv2.putText(frame, "PRESS REGISTER", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            else:
                cv2.putText(frame, "FACE NOT FOUND", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            self.ui.draw_buttons(frame)
            block_status = "BLOCKED" if self.ui.block_enabled else "UNLOCKED"
            cv2.putText(frame, f"BLOCK: {block_status}", (10, 120),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            
            cv2.putText(frame, "🔒 ENCRYPTED | 👄 LIP | 🔴 MOLES", (10, 420),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
            
            cv2.imshow(self.config.ui.window_title, frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                self.running = False
            
            if self.liveness_ok and self.config.face_json.exists():
                if self.frame_count % 5 == 0 and self.face_pts:
                    ok, msg = self.data_manager.verify_shadowprint(
                        face_points_display, 
                        self.config.face_json
                    )
                    self.access_granted = ok
            
            if self.ui.restart_requested:
                self.ui.restart_requested = False
                self.camera.release()
                cv2.destroyAllWindows()
                self._restart()
                return
        
        self.camera.release()
        cv2.destroyAllWindows()
        self.safe_block.block(False)
        self.logger.info("Программа завершена")
    
    def _handle_register(self, frame: np.ndarray, param: dict):
        param["register"] = False
        
        if not self.last_face_points:
            self.logger.warning("❌ Нет лица для регистрации")
            return
        
        self.safe_block.block(False)
        
        h, w = frame.shape[:2]
        if self.face_pts:
            all_face = self.face_detector.get_points_all(self.face_pts, h, w)
        else:
            all_face = self.last_face_points
        
        self.data_manager.save_shadowprint(frame, all_face, self.config.face_photo, self.config.face_json)
        
        if self.last_hand_points:
            self.data_manager.save_shadowprint(frame, self.last_hand_points, self.config.gesture_photo, self.config.gesture_json)
        
        moles = self.mole_detector.detect_moles(frame)
        if moles:
            self.data_manager.save_moles(moles, self.config.moles_photo, self.config.moles_json)
            self.saved_moles = self.data_manager.load_moles(self.config.moles_json)
        
        self.logger.info("✅ Регистрация завершена")
        
        if self.ui.block_enabled:
            self.safe_block.block(True)
    
    def _handle_delete(self, param: dict):
        if time.time() - param["delete_start"] >= 2.0:
            if self.config.data_dir.exists():
                shutil.rmtree(self.config.data_dir)
                self.config.data_dir.mkdir(exist_ok=True)
            self.logger.info("🗑️ Все данные удалены!")
            self.access_granted = False
            self.saved_moles = {}
            param["delete"] = False
    
    def _restart(self):
        self.logger.info("🔄 Перезапуск...")
        time.sleep(1)
        python = sys.executable
        os.execl(python, python, *sys.argv)


# ==============================================================================
# ТОЧКА ВХОДА
# ==============================================================================

def main():
    """Главная функция"""
    try:
        config = Config()
        config.data_dir.mkdir(exist_ok=True)
        config.models_dir.mkdir(exist_ok=True)
        config.logs_dir.mkdir(exist_ok=True)
        
        if not FaceDetector.check_models():
            input("Нажмите Enter для выхода...")
            return
        
        config_path = config.script_dir / "config.json"
        config.load_from_file(config_path)
        
        app = FaceLockApp()
        app.run()
        
    except KeyboardInterrupt:
        print("\n⏹️ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        input("Нажмите Enter для выхода...")


if __name__ == "__main__":
    main()