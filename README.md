# Face Lock Pro v3.0

Biometric authentication system in Python (FaceID + Liveness Check + Anti-Spoofing + Encrypted Data).

## 📌 About The Project

This project is my practical work for mastering computer vision, biometrics, cybersecurity, and data encryption. 

**To be clear:** I am not claiming this is an ideal or 100% enterprise-ready FaceID system. I am a beginner/learning developer, and my primary goal here is **hands-on practice, experimentation, and deep-diving into the field**.

The code is completely Open Source and free. Feel free to use, inspect, modify, optimize, or build upon it for your own needs. The only condition is to credit me (**Terorating**) if you use my code or core ideas. This is basic respect for someone else's work.

---

## 🚀 Key Features (v3.0)

* **Face Mesh Analysis:** Build and track 468 facial landmarks via MediaPipe.
* **Data Encryption (`CryptoManager`):** Biometric templates are never stored in plain JSON. Data is encrypted using PBKDF2 (SHA-256) and dynamic hardware keys.
* **Liveness Detection:** Real-time dynamic validation (Eyelid Aspect Ratio / EAR blinks, smile tracking, head rotation) + interactive challenge-response prompts.
* **Feature Detection (`MoleDetector`):** Detects and verifies unique facial marks (moles, scars) for extra security.
* **Lip Movement Analysis (`LipMovementDetector`):** Verifies speech articulation to prevent deepfake and static mask bypasses.
* **Anti-Spoofing (`AntiSpoofing`):** Replay attack detection via frame hashes + primary gradient density analysis for deepfake detection.
* **Watchdog Protection (`SafeBlockInput`):** Secure workstation locking with a background watchdog thread that automatically restores input after 30 seconds if the process freezes.

---

## 📁 Repository Structure

```text
.
├── main.py                # Main application logic
├── config.json            # Configuration file
├── models/                # MediaPipe task models (download separately)
│   ├── face_landmarker.task
│   └── hand_landmarker.task
├── data/                  # Encrypted biometric storage (do not commit)
└── logs/                  # System logs
```

---

## ⚙️ Configuration Breakdown (`config.json`)

All key parameters are exposed in `config.json`:

### 1. `camera`
* `device_id`: Webcam index (default: `0`).
* `width` / `height`: Stream resolution (`640x480`).
* `fps`: Frame rate (`30`).

### 2. `detection`
* `confidence_threshold`: Minimum confidence score for face detection.
* `mole_min_area` / `mole_max_area`: Size constraints for mole/scar detection (in pixels).
* `mole_contrast_threshold`: Contrast threshold to isolate dark skin marks.
* `mole_match_threshold`: Matching factor required to confirm identity.
* `lip_movement_threshold`: Sensitivity threshold for lip movement validation.

### 3. `liveness`
* `timeout`: Time window (in seconds) allowed for initial liveness verification.
* `liveness_threshold`: Minimum combined score required to pass liveness check (default: `0.55`).
* `blink_weight` / `lip_weight` / `mole_weight`: Score multipliers for each validation factor.
* `challenge_timeout`: Time limit to complete random challenge commands.

### 4. `security`
* `block_watchdog_timeout`: Max lock time for `BlockInput`. Guarantees input release if an uncaught exception occurs.
* `encryption_iterations`: PBKDF2 iteration count for encryption key derivation.

---

## 🛠 Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Terorating/FaceID-Liveness-Security.git
   cd FaceID-Liveness-Security
   ```

2. **Install dependencies:**
   ```bash
   pip install opencv-python mediapipe numpy cryptography
   ```

3. **Download MediaPipe models:**
   Place the following model files into the `models/` directory:
   * `face_landmarker.task`
   * `hand_landmarker.task`

4. **Run the system:**
   ```python
   python main.py
   ```

---

## 🗺 Future Roadmap & Ecosystem Plans

This repository is just the beginning. My long-term goal is to build an interconnected ecosystem of security and automation projects:

* [ ] **Voice Initialization & Speaker Recognition:** Adding voice verification, keyword triggers, and speech pattern/defect analysis.
* [ ] **Multi-Factor Unlock:** Combining FaceID, voice commands, and specific hardware key combinations for maximum security.
* [ ] **Client-Server Architecture:** Unifying future projects into a single general system where a system administrator (SysAdmin) can monitor login/logout events, activity logs, and system status across multiple machines in real time.
* [ ] **GUI Migration:** Transitioning from an OpenCV interface to a modern desktop GUI (CustomTkinter / PyQt).
* [ ] **Commercial Iterations:** Developing advanced, closed-source enterprise modifications based on open-source foundations.

---

**Author:** [Terorating](https://github.com/Terorating)  
**License:** MIT (Free to use with required attribution).