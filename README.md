Hey. This is my project on computer vision and biometrics.

I'll be straight with you: I'm not claiming this is a perfect, production-ready FaceID system. I'm learning, experimenting, and digging into the topic. So if you see a hack somewhere, don't be surprised — either I meant it that way, or I haven't figured out a better way yet.

The code is open and free. Take it, break it down, modify it for your needs. The only condition is to credit the author (Terorating) if you use my code or key ideas. It's basic respect for someone else's work.

What it actually does (and what changed)
I recently did a full rewrite of the core. It's not just a patch — I reworked the security and liveness logic from scratch. Here is what the current version does:

Face Mesh: Builds 128 key points via MediaPipe for face comparison.

Anti-photo protection (fixed): It actually works now. The system makes you blink (using Eye Aspect Ratio with a proper hysteresis) or smile to prove you're a real person. Photos no longer pass.

Real encryption: I threw out the old XOR obfuscation. The biometric data is now encrypted with Fernet (AES) and bound to your Windows account using DPAPI. If someone steals the data folder and opens it on another PC, it's just useless garbage.

Distance normalization: Face comparison no longer breaks if you step closer to or further from the camera. Distances are normalized by face width.

Brute-force protection: If someone tries to fake the face 5 times, the system locks them out for 5 minutes.

Blocking: If you turn on block mode, the mouse and keyboard get disabled. But there's a fail-safe timer (Watchdog) so if the app crashes, you're not left with a locked PC forever.

(Note: The mole detection and lip movement features from the old v3.0 are temporarily disabled while I stabilize the core. I plan to bring them back later).

How to run
Clone the repo:
git clone https://github.com/Terorating/FaceID-Liveness-Security.git

Install dependencies:
pip install opencv-python mediapipe numpy cryptography pywin32

Download the MediaPipe models (face_landmarker.task and hand_landmarker.task) and drop them into the models/ folder.

Run:
python main.py

Settings
Right now all the parameters are in the code. If you don't know what a parameter does — better not touch it, consider yourself warned. (I'll move everything to config.json in the next update).

Plans (what I want to finish)
Right now we have a working core. But in the future, I want to turn this into something bigger:

Bring back old features: Return mole detection and lip articulation checks.

Voice: Hook up key phrase and timbre recognition.

Multi-factor: Face + Voice + Secret key combination (so it's completely unbreakable).

Proper GUI: Move away from the standard OpenCV window to PyQt or CustomTkinter so it looks nice.

Server: Build an admin panel that shows who logged in and when, in real time.

Commercial: Maybe release a paid version with more features once I gain more experience.

**Author:** [Terorating](https://github.com/Terorating)  
**License:** MIT (Free to use with required attribution).
