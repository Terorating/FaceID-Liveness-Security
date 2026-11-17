Face Lock Pro
Hey. This is my project on computer vision and biometrics.

I'll be straight with you: I'm not claiming this is a perfect, production-ready FaceID system. I'm learning, experimenting, and digging into the topic. So if you see a hack somewhere, don't be surprised — either I meant it that way, or I haven't figured out a better way yet.

The code is open and free. Take it, break it down, modify it for your needs. The only condition is to credit the author (Terorating) if you use my code or key ideas. It's basic respect for someone else's work.

What it actually does
This isn't just facial recognition by landmark points. I tried to make it so the system can't be fooled by a regular photo or a video from a phone.

Face Mesh: Builds 468 points via MediaPipe. That's the basic part.

Anti-photo protection: Checks if you're alive. Blink, smile, turn your head — if you just sit there and don't do the tasks, no access for you. In the code, this is the EAR (eye) check, smile detection, and challenges.

Moles and scars: Looks for dark spots on the face. Yeah, you could call it paranoia, but it's fun when the system recognizes you by the mole on your cheek.

Lips: Monitors articulation. To keep deepfakes out.

Encryption: The face print isn't sitting in a plain JSON. I put some effort into PBKDF2 and AES. The key is tied to the PC's hardware (via system variables), so just copying the data folder to another machine and logging in won't work.

Blocking: If you turn on block mode, the mouse and keyboard get disabled. But there's a fail-safe timer (Watchdog) so if the app crashes, you're not left with a locked PC forever. 30 seconds — and you're free.

How to run
Clone the repo:
git clone https://github.com/Terorating/FaceID-Liveness-Security.git

Install dependencies:
pip install opencv-python mediapipe numpy cryptography

Download the MediaPipe models (face_landmarker.task and hand_landmarker.task) and drop them into the models/ folder.

Run:
python main.py

Settings
In config.json you can tweak the camera, thresholds, and timeouts. If you don't know what a parameter does — better not touch it, consider yourself warned.

Plans (what I want to finish)
Right now it's just a demo. But in the future, I want to turn this into something bigger:

Voice: Hook up key phrase and timbre recognition.

Multi-factor: Face + Voice + Secret key combination (so it's completely unbreakable).

Proper GUI: Move away from the standard OpenCV window to PyQt or CustomTkinter so it looks nice.

Server: Build an admin panel that shows who logged in and when, in real time.

Commercial: Maybe release a paid version with more features once I gain more experience.

Author
Terorating
MIT License — do whatever you want, just credit the author.

**Author:** [Terorating](https://github.com/Terorating)  
**License:** MIT (Free to use with required attribution).
