# Autonomous Object Retrieval Robot

3rd Year Project (EE3126), University of Galway — Supervisor: Prof. Peter Corcoran

An autonomous mobile robot that finds, grasps, and returns three coloured objects (blue, red, green) in sequence, with no human intervention. A camera and OpenCV identify each object by colour, the robot drives itself into grasping range, picks the object up with a custom 3D-printed servo gripper, then retraces its own path in reverse to return home — repeating for all three objects.

*The three 3D-printed retrieval objects. Each is an inverted cone, so closing the gripper around it also lifts it off the ground — no separate lift axis needed.*

Team project by **Naoise Lowry** and **Caoimhin Malone**.
- Naoise: computer vision, object detection, and navigation logic (`temp.py` / `temp2.py`, `Colour Calibrator.py`, `Calibration`); battery mount design
- Caoimhin: gripper arm design, camera mount design, Arduino motor/servo control firmware, and a separate attempt at a web-based remote control dashboard (`PiORR/`) — see note below

## How it works

1. Scan for the target object by rotating in place
2. Detect it using calibrated HSV colour segmentation (OpenCV)
3. Approach it using reactive navigation — steer to keep the object centred in frame, drive forward until it's within grasping range
4. Record every movement command from first detection to grasp
5. Grasp the object with the servo-driven gripper
6. Replay the recorded movements in reverse (mirrored) to return to the starting point
7. Release the object, repeat for the next colour in sequence (blue → red → green)

A Raspberry Pi 5 handles vision and decision-making; an Arduino Mega (MegaPi) handles real-time motor/servo control, connected over USB serial.

## Repo structure

```
ORR/
├── main.py                  # Core vision, detection, and navigation logic — the final working system
├── main_v1.py                # Earlier iteration, kept for reference
├── Colour Calibrator.py     # Interactive HSV threshold calibration tool (for the flipped camera)
├── Calibration               # Standalone distance-calibration script (blue blob detection)
├── ORR.ino                 # Final Arduino sketch (motors, servos, NeoPixel status LEDs, buzzer, IR receiver)
├── Arduino_v2.0             # Earlier Arduino iteration
├── mBot_Control_v2.ino       # Earlier Arduino iteration
├── object_version5.stl      # 3D model of the retrieval object (inverted cone design)
├── Pictures/              #Various images of the robot
├── PiORR/
│   ├── main.py            # Copy of the core logic with an added, experimental web dashboard integration
│   ├── server.py          # Flask + SocketIO web dashboard: live video stream, manual override, mission control
│   ├── discovery.py        # UDP broadcast so the dashboard could find the robot on the network
│   └── requirements.txt    # Python dependencies for the dashboard
```

> **Note on `PiORR/`:** this was a separate attempt to add a browser-based remote control dashboard (live video stream + manual override) on top of the core system. It's an interesting extension, but it wasn't confirmed to work reliably and isn't part of the tested, submitted system — the core deliverable is `temp.py` / `temp2.py` plus the Arduino sketch.

## Notable technical detail: the colour inversion problem

The camera is physically mounted flipped (horizontal + vertical), which is necessary for the mount design — but as a side effect of the camera's internal processing, this **inverts the perceived colours**: real blue reads as orange, red as cyan, and green as magenta. All HSV threshold calibration had to target the *inverted* colours rather than the real ones. `Colour Calibrator.py` is the tool built to handle this — it lets you tune HSV sliders live against the flipped camera feed and save the resulting thresholds.

## Experimental extension: web dashboard (unconfirmed)

`PiORR/server.py` is a small Flask + SocketIO server, intended to provide:
- A live MJPEG video stream from the robot's camera (`/video`)
- Manual override controls (forward/left/right/stop) over WebSocket
- Remote mission start/stop and return-path trigger
- A live status feed (current stage, objects retrieved, recording state)

`discovery.py` was meant to broadcast the robot's presence on the local network via UDP so a dashboard client could find it automatically. This was an attempt to add browser-based remote control on top of the working system — it's included here for completeness, but it was not confirmed to work reliably and shouldn't be assumed functional.

## Setup

**Raspberry Pi (Python) — core working system:**
```bash
pip install opencv-python numpy pyserial
python main.py
```
(`main_v1.py` is an earlier iteration, kept for reference — not used for the final tested system.)

**Arduino (MegaPi):**
- Open `ORR.ino` in the Arduino IDE
- Install the `MeMegaPi` and `Adafruit_NeoPixel` libraries
- Flash to the Arduino Mega 2560 (MegaPi controller)

**Calibration:**
Run `Colour Calibrator.py` first to generate HSV threshold values for your lighting conditions and objects, then paste the resulting ranges into `main.py`.

**Web dashboard (experimental, PiORR/):**
```bash
cd PiORR
pip install -r requirements.txt
python main.py
```
Not confirmed to work reliably — try at your own risk.

## Hardware

- Makeblock mBot Mega (4WD chassis, Arduino Mega 2560-based MegaPi controller)
- Raspberry Pi 5 (8GB)
- Pi Camera Module 3
- Custom 3D-printed two-servo gripper (grip + tilt, two degrees of freedom)
- IR receiver (TSOP38238) for manual override
- NeoPixel LED strips + buzzer for status feedback
- 12V, 3A rechargeable battery pack, custom 3D-printed mount

## Results

Across 20 trials per object: 98% detection / 90% retrieval success (blue), 95% / 100% (red), 92% / 95% (green). Full three-object mission success rate: 95% overall.

## Known limitations / future work

- No obstacle avoidance — assumes a clear test area
- No environment mapping; purely reactive, camera-driven navigation
- Colour detection is lighting-sensitive
- Planned: a dedicated distance sensor for close-range accuracy, dynamic path planning (e.g. RRT) for obstacle handling, shape-based recognition alongside colour
