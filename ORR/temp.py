#!/usr/bin/env python3
"""
BlueBot Autonomous Multi-Object Retrieval System with Reactive Obstacle Avoidance
Retrieves objects in sequence (BLUE -> RED -> GREEN) automatically
Avoids obstacles by circling around them when they block the path
Camera is FLIPPED (hflip=1, vflip=1) - colors are inverted
Records ALL movements continuously from first detection to grasp
"""

import numpy as np
import cv2
import time
import serial
import os
import math
import threading
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple, Dict, Optional, Any
from datetime import datetime
from picamera2 import Picamera2
from libcamera import Transform

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class CameraConfig:
    width: int = 640
    height: int = 480
    fps: int = 30
    hflip: bool = True
    vflip: bool = True

@dataclass
class DetectionConfig:
    min_blob_area: int = 5000
    calib_k: float = 42459450
    grasp_area_threshold: int = 115000
    obstacle_safety_margin: int = 30  # Additional pixels beyond object radius
    max_lost_frames: int = 30  # Maximum frames without target before aborting

    # Color ranges for FLIPPED camera - CALIBRATED VALUES
    color_ranges = {
        'blue': {
            'lower': np.array([0, 152, 49]),      # Calibrated for blue object
            'upper': np.array([16, 255, 255])
        },
        'red': {
            'lower': np.array([111, 130, 0]),  # Calibrated for red object
            'upper': np.array([180, 255, 255])
        },
        'green': {
            'lower1': np.array([45, 107, 0]),    # Calibrated for green object
            'upper1': np.array([89, 255, 255]),
            'lower2': np.array([180, 107, 0]),    # Note: lower2 > upper2 indicates wrap
            'upper2': np.array([180, 255, 255])    # This means 76-180 and 0 combined
        }
    }

@dataclass
class MotionConfig:
    forward_speed: int = 150
    turn_speed: int = 200
    turn_duration_90deg: float = 0.4
    turn_duration_180deg: float = 2.0          # Increased from 0.8 to match Arduino's 1.8s turn + margin
    approach_speed: int = 100
    final_approach_duration: float = 0.5
    backup_duration: float = 0.5
    orbit_duration: float = 0.3  # time to orbit around obstacle
    search_turn_duration: float = 0.2  # time to turn when searching

# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================

class ObjectColor(Enum):
    BLUE = "blue"
    RED = "red"
    GREEN = "green"

class MissionStage(Enum):
    STARTING = "starting"
    SCANNING = "scanning"
    APPROACHING = "approaching"
    AVOIDING = "avoiding"
    SEARCHING = "searching"
    GRASPING = "grasping"
    RETURNING = "returning"
    RELEASING = "releasing"
    BACKING_UP = "backing_up"
    COMPLETE = "complete"

class AvoidanceDirection(Enum):
    LEFT = "left"
    RIGHT = "right"

@dataclass
class DetectedObject:
    color: ObjectColor
    position: Tuple[int, int]
    area: float
    distance: float
    confidence: float
    timestamp: float
    is_retrieved: bool = False

@dataclass
class ActionRecord:
    frame: int
    action: str
    stage: str
    color: Optional[ObjectColor] = None

# ============================================================================
# ENHANCED COLOR DETECTOR
# ============================================================================

class ColorDetector:
    def __init__(self, config: DetectionConfig):
        self.config = config
        self.frame = None
        self.hsv = None
        self.all_objects = []
        self.target_object = None
        self.current_color = None
        self.target_first_detected = False  # Flag to track if we've ever seen the target
        self.frame_count = 0
        self.frame_width = CameraConfig().width

    def process_frame(self, frame_rgb: np.ndarray) -> List[DetectedObject]:
        self.frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        self.hsv = cv2.cvtColor(self.frame, cv2.COLOR_BGR2HSV)
        self.frame_count += 1

        all_detected = []

        for color_name, ranges in self.config.color_ranges.items():
            color = ObjectColor(color_name)

            if 'lower1' in ranges:
                mask1 = cv2.inRange(self.hsv, ranges['lower1'], ranges['upper1'])
                mask2 = cv2.inRange(self.hsv, ranges['lower2'], ranges['upper2'])
                mask = cv2.bitwise_or(mask1, mask2)
            else:
                mask = cv2.inRange(self.hsv, ranges['lower'], ranges['upper'])

            kernel = np.ones((5,5), np.uint8)
            mask = cv2.erode(mask, kernel, iterations=1)
            mask = cv2.dilate(mask, kernel, iterations=2)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                area = cv2.contourArea(contour)
                if area > self.config.min_blob_area:
                    ((x, y), radius) = cv2.minEnclosingCircle(contour)
                    cx = int(x)
                    cy = int(y)
                    distance = (self.config.calib_k / area) ** 0.5

                    obj = DetectedObject(
                        color=color,
                        position=(cx, cy),
                        area=area,
                        distance=distance,
                        confidence=0.9,
                        timestamp=time.time()
                    )
                    all_detected.append(obj)

        self.all_objects = all_detected

        # Update target object
        if self.current_color:
            self.target_object = self.get_object_by_color(self.current_color)
            if self.target_object is not None and not self.target_first_detected:
                self.target_first_detected = True
                print(f"\n[TRACK] Target {self.current_color.value} first detected at frame {self.frame_count}")

        return all_detected

    def set_target_color(self, color: ObjectColor):
        self.current_color = color
        self.target_object = self.get_object_by_color(color)
        # Don't reset target_first_detected here - it persists throughout the approach

    def reset_target_tracking(self):
        """Reset the target tracking state for a new approach"""
        self.target_first_detected = False

    def get_object_by_color(self, color: ObjectColor) -> Optional[DetectedObject]:
        same_color = [obj for obj in self.all_objects if obj.color == color and not obj.is_retrieved]
        if same_color:
            return max(same_color, key=lambda obj: obj.area)
        return None

    def get_obstacles(self, exclude_color: Optional[ObjectColor] = None) -> List[DetectedObject]:
        """Get all non-target objects"""
        obstacles = []
        for obj in self.all_objects:
            if exclude_color is not None and obj.color == exclude_color:
                continue
            if not obj.is_retrieved:
                obstacles.append(obj)
        return obstacles

    def get_object_radius(self, obj: DetectedObject) -> int:
        """Calculate approximate radius of object in pixels"""
        return int(np.sqrt(obj.area) / 2)

    def is_obstacle_blocking(self, target: DetectedObject, obstacle: DetectedObject) -> bool:
        """Check if an obstacle is in the path to the target"""
        if target is None or obstacle is None:
            return False

        # Calculate scaled safety margin based on obstacle size
        # Danger zone = object radius + safety margin
        obstacle_radius = self.get_object_radius(obstacle)
        danger_zone = obstacle_radius + self.config.obstacle_safety_margin

        # Calculate horizontal distance between target and obstacle
        horizontal_dist = abs(obstacle.position[0] - target.position[0])

        # Check if obstacle is within the danger zone horizontally
        if horizontal_dist < danger_zone:
            # Check if obstacle is between robot and target (closer than target)
            # Since all objects are same size, we can use area as proxy for distance
            if obstacle.area > target.area * 0.7:  # Obstacle is similar size/closer
                return True

        return False

    def get_action(self) -> str:
        """Get action with obstacle avoidance"""
        if self.target_object is None:
            return "SEARCH"

        center_left = self.frame_width * 20 // 100
        center_right = self.frame_width * 80 // 100

        x = self.target_object.position[0]

        # Check if target is centered enough to consider grasping
        if x >= center_left and x <= center_right:
            if self.target_object.area > self.config.grasp_area_threshold:
                return "GRASP"
            else:
                return "FORWARD"

        # Target is off-center, need to turn
        return "LEFT" if x < center_left else "RIGHT"

# ============================================================================
# REACTIVE OBSTACLE AVOIDANCE
# ============================================================================

class ObstacleAvoidance:
    def __init__(self, config: DetectionConfig, motion_config: MotionConfig):
        self.config = config
        self.motion_config = motion_config
        self.avoiding = False
        self.avoid_direction = AvoidanceDirection.LEFT
        self.obstacle_to_avoid = None
        self.avoidance_start_time = 0
        self.maneuver_step = 0  # Track which step of avoidance we're in

    def check_and_avoid(self, detector: ColorDetector, controller: 'RobotController',
                        target_color: ObjectColor) -> bool:
        """
        Check for blocking obstacles and initiate avoidance if needed.
        Returns True if avoidance is in progress.
        """
        if detector.target_object is None:
            return False

        obstacles = detector.get_obstacles(exclude_color=target_color)

        # Check each obstacle
        for obstacle in obstacles:
            if detector.is_obstacle_blocking(detector.target_object, obstacle):
                if not self.avoiding:
                    # Start avoiding this obstacle
                    self.avoiding = True
                    self.obstacle_to_avoid = obstacle
                    self.avoidance_start_time = time.time()
                    self.maneuver_step = 0

                    # Decide which way to go based on obstacle position
                    if obstacle.position[0] < detector.target_object.position[0]:
                        self.avoid_direction = AvoidanceDirection.RIGHT
                    else:
                        self.avoid_direction = AvoidanceDirection.LEFT

                    print(f"\n[AVOID] Obstacle {obstacle.color.value} detected at {obstacle.position}")
                    print(f"[AVOID] Danger zone radius: {detector.get_object_radius(obstacle) + self.config.obstacle_safety_margin} pixels")
                    print(f"[AVOID] Moving to the {self.avoid_direction.value} to get around")
                    return True
                else:
                    # Continue avoidance
                    return True

        # No obstacles blocking
        if self.avoiding:
            print("[AVOID] Path clear, resuming approach")
            self.avoiding = False
            self.obstacle_to_avoid = None
            self.maneuver_step = 0

        return False

    def execute_avoidance_maneuver(self, controller: 'RobotController',
                                   detector: ColorDetector, frame: np.ndarray,
                                   target_color: ObjectColor) -> Tuple[bool, str, float]:
        """
        Execute a smarter avoidance maneuver:
        1. Turn toward the direction of the obstacle (to go around it)
        2. Move forward slightly
        3. Turn back to face the target area
        4. Check if target is now the largest/closest
        5. Either proceed or continue circling if not

        Returns: (still_avoiding, action, duration)
        """
        if not self.avoiding:
            return False, "NONE", 0

        duration = self.motion_config.orbit_duration

        if self.maneuver_step == 0:

            print(f"[AVOID] Step 1: Turning {self.avoid_direction.value}")

            if self.avoid_direction == AvoidanceDirection.LEFT:
                controller.send_command("LEFT")
            else:
                controller.send_command("RIGHT")

            time.sleep(duration)
            controller.stop()

            self.maneuver_step = 1
            return True, "TURN", duration


        elif self.maneuver_step == 1:

            print("[AVOID] Step 2: Moving forward")

            controller.send_command("FORWARD")

            time.sleep(duration * 1.5)
            controller.stop()

            self.maneuver_step = 2
            return True, "FORWARD", duration


        elif self.maneuver_step == 2:

            print("[AVOID] Step 3: Turning back")

            if self.avoid_direction == AvoidanceDirection.LEFT:
                controller.send_command("RIGHT")
            else:
                controller.send_command("LEFT")

            time.sleep(duration)
            controller.stop()

            self.maneuver_step = 3
            return True, "TURN", duration

        elif self.maneuver_step == 3:

            print("[AVOID] Step 4: Checking if path is clear")

            self.avoiding = False
            self.obstacle_to_avoid = None
            self.maneuver_step = 0

            return False, "NONE", 0

# ============================================================================
# ROBOT CONTROLLER WITH CONTINUOUS DURATION RECORDING
# ============================================================================

class RobotController:
    def __init__(self, config: MotionConfig):
        self.config = config
        self.serial = None
        self.last_command = None
        self.command_lock = threading.Lock()
        self.action_log = []  # Continuous log from first detection to grasp
        self.recording_enabled = False  # Whether we're currently recording

    def connect(self, port: str = None) -> bool:
        if port:
            ports = [port]
        else:
            ports = ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyACM0', '/dev/ttyACM1']

        for p in ports:
            if os.path.exists(p):
                try:
                    self.serial = serial.Serial(p, 9600, timeout=1)
                    time.sleep(2)

                    start_time = time.time()
                    while time.time() - start_time < 3:
                        if self.serial.in_waiting > 0:
                            msg = self.serial.readline().decode().strip()
                            print(f"Arduino: {msg}")
                            if "READY" in msg:
                                print(f"Connected to Arduino on {p}")
                                return True
                except Exception as e:
                    print(f"Failed to connect to {p}: {e}")

        print("Could not connect to Arduino")
        return False

    def send_command(self, cmd: str, log_action=False, color=None, stage="APPROACHING"):

        if not self.serial:
            return False

        with self.command_lock:
            try:
                self.serial.write(f"{cmd}\n".encode())
                print(f"-> {cmd}")
                self.last_command = cmd
                time.sleep(0.05)
                return True

            except Exception as e:
                print(f"Command failed: {e}")
                return False

    def start_recording(self):
        self.recording_enabled = True
        if not self.action_log:
            self.action_log = []
        print("\n[RECORD] Started recording movements")

    def stop_recording(self):
        self.recording_enabled = False
        print(f"[RECORD] Recorded {len(self.action_log)} actions")

    def forward(self, duration: Optional[float] = None, color: Optional[ObjectColor] = None, stage: str = "APPROACHING"):
        self.send_command("FORWARD", color=color, stage=stage)
        if duration:
            time.sleep(duration)
            self.stop()

    def backward(self, duration: Optional[float] = None, color: Optional[ObjectColor] = None, stage: str = "APPROACHING"):
        self.send_command("BACKWARD", color=color, stage=stage)
        if duration:
            time.sleep(duration)
            time.sleep(0.1)
            self.stop()

    def left(self, duration: Optional[float] = None, color: Optional[ObjectColor] = None, stage: str = "APPROACHING"):
        self.send_command("LEFT", color=color, stage=stage)
        if duration:
            time.sleep(duration)
            self.stop()

    def right(self, duration: Optional[float] = None, color: Optional[ObjectColor] = None, stage: str = "APPROACHING"):
        self.send_command("RIGHT", color=color, stage=stage)
        if duration:
            time.sleep(duration)
            self.stop()

    def log_frame_action(self, action, frame, stage, color=None):

        if not self.recording_enabled:
            return

        # Only log movement commands
        if action not in ["FORWARD", "LEFT", "RIGHT", "BACKWARD"]:
            return

        self.action_log.append(
            ActionRecord(
                frame=frame,
                action=action,
                stage=stage,
                color=color
            )
        )

    def stop(self):
        self.send_command("STOP", log_action=False)

    def turn_degrees(self, degrees: float, color: Optional[ObjectColor] = None, stage: str = "APPROACHING"):
        if degrees > 0:
            duration = (degrees / 90) * self.config.turn_duration_90deg
            self.right(duration, color, stage)
        else:
            duration = (abs(degrees) / 90) * self.config.turn_duration_90deg
            self.left(duration, color, stage)

    def turn_180(self):
        self.send_command("TURN_180", log_action=False)
        time.sleep(self.config.turn_duration_180deg + 1)

    def grasp(self):
        self.send_command("GRASP", log_action=False)
        time.sleep(4)

    def release(self):
        self.send_command("RELEASE", log_action=False)
        time.sleep(4)

    def execute_return_path(self):

        if not self.action_log:
            print("No actions recorded")
            return

        print("\n=== RETURNING TO START ===")
        print(f"Replaying {len(self.action_log)} actions")

        return_path = list(reversed(self.action_log))
        fps = CameraConfig().fps

        for i in range(len(return_path)):
            record = return_path[i]
            action = record.action

            print(f"Return {i+1}/{len(return_path)}: {action}")

            # Start movement
            self.send_command(action)

            # Calculate correct delay
            if i < len(return_path) - 1:
                next_record = return_path[i+1]
                frame_diff = abs(record.frame - next_record.frame)
                delay = frame_diff / fps
            else:
                delay = 0.3



        print("\nReturn sequence complete")

# ============================================================================
# MAIN AUTONOMOUS ROBOT
# ============================================================================

class AutonomousSortingRobot:
    def __init__(self):
        self.cam_config = CameraConfig()
        self.detect_config = DetectionConfig()
        self.motion_config = MotionConfig()

        self.camera = None
        self.detector = ColorDetector(self.detect_config)
        self.controller = RobotController(self.motion_config)
        self.avoidance = ObstacleAvoidance(self.detect_config, self.motion_config)

        self.mission_sequence = [ObjectColor.BLUE, ObjectColor.RED, ObjectColor.GREEN]
        self.current_stage = MissionStage.STARTING
        self.frame_count = 0
        self.log_file = None
        self.camera_enabled = True

        self.start_position = (self.cam_config.width // 2, self.cam_config.height)
        self.retrieved_objects = []

        self.ir_detected = False
        self.ir_lock = threading.Lock()

        # Approach tracking
        self.approach_active = False
        self.approach_start_time = 0
        self.lost_counter = 0  # Track consecutive lost frames

    def initialize(self):
        print("\n" + "="*60)
        print("AUTONOMOUS SORTING ROBOT INITIALIZATION")
        print("="*60)
        print("Camera is FLIPPED - Color mapping (CALIBRATED):")
        print("  Real BLUE   -> appears ORANGE in camera")
        print("  Real RED    -> appears CYAN in camera")
        print("  Real GREEN  -> appears MAGENTA in camera")
        print("="*60)
        print(f"Grasp trigger: area > {self.detect_config.grasp_area_threshold} pixels")
        print(f"Min blob area: {self.detect_config.min_blob_area}")
        print(f"Obstacle safety margin: {self.detect_config.obstacle_safety_margin} pixels")
        print(f"Max lost frames: {self.detect_config.max_lost_frames}")
        print(f"180° turn duration: {self.motion_config.turn_duration_180deg}s")
        print("="*60)

        self._init_camera()

        if not self.controller.connect():
            print("WARNING: Continuing without Arduino connection")

        self._setup_logging()
        self._start_ir_reader()

        print("\n[OK] Robot initialized successfully")
        print("="*60 + "\n")

    def _init_camera(self):
        try:
            print("Initializing camera with FLIP (hflip=1, vflip=1)...")
            self.camera = Picamera2()

            transform = Transform(
                hflip=1 if self.cam_config.hflip else 0,
                vflip=1 if self.cam_config.vflip else 0
            )

            config = self.camera.create_video_configuration(
                main={"size": (self.cam_config.width, self.cam_config.height),
                      "format": "RGB888"},
                transform=transform
            )
            self.camera.configure(config)
            self.camera.start()
            time.sleep(2)
            print(f"[OK] Camera started (flipped)")
        except Exception as e:
            print(f"[ERROR] Camera init error: {e}")
            self.camera = None

    def _setup_logging(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"/home/pi/Documents/Logs/autonomous_sorting_{timestamp}.txt"
        self.log_file = open(log_filename, "w")
        self.log_file.write("AUTONOMOUS SORTING ROBOT LOG\n")
        self.log_file.write(f"Started: {datetime.now()}\n")
        self.log_file.write("="*80 + "\n")
        self.log_file.write("Timestamp,Frame,Stage,Color,Action,X,Y,Area,Distance,Status\n")
        self.log_file.flush()
        print(f"[OK] Logging to: {log_filename}")

    def _start_ir_reader(self):
        def ir_reader():
            while True:
                if self.controller.serial and self.controller.serial.in_waiting > 0:
                    try:
                        line = self.controller.serial.readline().decode().strip()
                        if line.startswith("IR:"):
                            status = line[3:]
                            with self.ir_lock:
                                self.ir_detected = (status == "DETECTED")
                    except:
                        pass
                time.sleep(0.01)

        thread = threading.Thread(target=ir_reader, daemon=True)
        thread.start()

    def log_event(self, stage: str, action: str = "", obj: Optional[DetectedObject] = None, status: str = ""):
        if not self.log_file:
            return

        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        if obj:
            line = f"{timestamp},{self.frame_count},{stage},{obj.color.value},{action},{obj.position[0]},{obj.position[1]},{obj.area:.0f},{obj.distance:.1f},{status}\n"
        else:
            line = f"{timestamp},{self.frame_count},{stage},none,{action},0,0,0,0,{status}\n"

        self.log_file.write(line)
        self.log_file.flush()

    def capture_frame(self) -> Optional[np.ndarray]:
        if not self.camera or not self.camera_enabled:
            return None

        try:
            frame = self.camera.capture_array()
            self.frame_count += 1
            return frame
        except Exception as e:
            print(f"Frame capture error: {e}")
            return None

    def find_next_target_color(self) -> Optional[ObjectColor]:
        for color in self.mission_sequence:
            already_retrieved = any(obj.color == color for obj in self.retrieved_objects)
            if not already_retrieved:
                return color
        return None

    def approach_with_avoidance(self, target_color: ObjectColor) -> bool:
        """
        Approach target while using reactive obstacle avoidance
        Records ALL movements continuously from first detection to grasp
        Lost counter only affects abort decision, NOT recording
        """
        print(f"\nApproaching {target_color.value} with obstacle avoidance...")
        self.current_stage = MissionStage.APPROACHING

        # Reset tracking state for new approach
        self.detector.reset_target_tracking()
        self.approach_active = False
        self.approach_start_time = time.time()
        self.lost_counter = 0  # Reset lost counter for new approach

        movement_count = 0
        first_detection_time = None
        recording_started = False
        search_turn_counter = 0

        while self.lost_counter < self.detect_config.max_lost_frames:
            frame = self.capture_frame()
            if frame is None:
                time.sleep(1 / self.cam_config.fps)
                continue

            # Process frame and update detection
            self.detector.process_frame(frame)
            self.detector.set_target_color(target_color)

            # Check if we have a target
            target_visible = self.detector.target_object is not None

            # First detection of this approach - START RECORDING
            if target_visible and not recording_started:
                self.approach_active = True
                recording_started = True
                first_detection_time = time.time()
                self.controller.start_recording()
                print(f"\n[TRACK] Target acquired - starting continuous recording")
                print(f"[TRACK] Will continue recording ALL movements regardless of visibility")

            if target_visible:
                # We can see the target - reset lost counter
                self.lost_counter = 0
                search_turn_counter = 0
                obj = self.detector.target_object
                movement_count += 1

                # Check for obstacles and avoid if needed
                if self.avoidance.check_and_avoid(self.detector, self.controller, target_color):
                    self.current_stage = MissionStage.AVOIDING
                    # Execute one step of avoidance maneuver with the current frame
                    still_avoiding, action, duration = self.avoidance.execute_avoidance_maneuver(
                        self.controller, self.detector, frame, target_color)

                    if still_avoiding:
                        # Still avoiding, continue loop
                        continue
                    else:
                        # Path clear, resume approaching
                        self.current_stage = MissionStage.APPROACHING
                        continue

                # No obstacles, normal approach
                action = self.detector.get_action()
                print(f"  {action}: area={obj.area:.0f}, pos={obj.position}")
                self.log_event("APPROACHING", action, obj)

                if action == "GRASP":
                    grasp_time = time.time()
                    approach_duration = grasp_time - first_detection_time if first_detection_time else 0
                    print(f"\n[TRACK] GRASP triggered at area={obj.area:.0f}")
                    print(f"[TRACK] Total approach duration: {approach_duration:.2f}s")
                    print(f"[TRACK] Total movements recorded: {movement_count}")
                    print(f"[TRACK] Action log size: {len(self.controller.action_log)}")
                    if recording_started:
                        self.controller.stop_recording()
                    self.controller.stop()
                    return True


                # Log EVERY frame movement (this is the important part)
                self.controller.log_frame_action(
                    action,
                    self.frame_count,
                    "APPROACHING",
                    target_color
                )

                # Only send command when it changes
                if action != self.controller.last_command:
                    self.controller.send_command(action)

                time.sleep(1 / self.cam_config.fps)

            else:
                # No target visible - lost counter increments but recording continues
                if recording_started:
                    self.lost_counter += 1
                    print(f"  Target temporarily lost ({self.lost_counter}/{self.detect_config.max_lost_frames}) - CONTINUING recording")
                    print(f"  Recorded {len(self.controller.action_log)} movements so far")

                    # Even though target is lost, we should still move in a search pattern
                    # These search movements are recorded too (IMPORTANT: recording continues)
                    search_turn_counter += 1
                    if search_turn_counter % 3 == 0:
                        print("  Searching for target - recording search movement")

                        # Log search movement
                        self.controller.log_frame_action(
                            "LEFT",
                            self.frame_count,
                            "SEARCHING",
                            target_color
                        )

                        # Execute the search turn
                        self.controller.turn_degrees(15)

                        self.current_stage = MissionStage.SEARCHING
                else:
                    # Haven't seen target yet this approach
                    print(f"  Waiting for target to appear...")
                    time.sleep(1 / self.cam_config.fps)

        print(f"[FAIL] Target lost for {self.detect_config.max_lost_frames} frames - aborting approach")
        if recording_started:
            print(f"  Recorded {len(self.controller.action_log)} movements before failure")
            self.controller.stop_recording()
        return False

    def execute_grasp_sequence(self, target_color: ObjectColor):
        """Execute the grasp, return, and release sequence"""
        print("\n" + "="*60)
        print(f"EXECUTING GRASP SEQUENCE for {target_color.value}")
        print("="*60)

        self.camera_enabled = False

        try:
            # Show recorded movements before return
            print(f"\nRecorded {len(self.controller.action_log)} movements during approach:")
            if self.controller.action_log:
                stage_counts = {}
                for record in self.controller.action_log:
                    if record.stage not in stage_counts:
                        stage_counts[record.stage] = 0
                    stage_counts[record.stage] += 1

                for stage, count in stage_counts.items():
                    print(f"  {stage}: {count} movements")
            else:
                print("  No movements recorded - check recording logic")

            time.sleep(1)
            self.controller.grasp()
            self.log_event("GRASPING", "grasp", status="success")

            # IMPORTANT: freeze the recorded path
            return_path_copy = list(self.controller.action_log)

            print("Performing 180deg turn...")
            self.controller.turn_180()

            # Restore the recorded path (ensures it wasn't modified)
            self.controller.action_log = return_path_copy

            print("\nStarting return path...")
            self.controller.execute_return_path()
            time.sleep(1)

            if len(self.retrieved_objects) >= 1:
                print("Repositioning for next search...")
                self.controller.turn_180()
                self.controller.forward(self.motion_config.backup_duration)

            print("\nReached starting position - STOPPING")
            self.controller.stop()
            time.sleep(1)

            print("Releasing object...")
            self.controller.release()

            # START RECORDING HERE
            print("[PATH] Recording from release point")
            self.controller.start_recording()

            print("Backing up...")

            self.controller.log_frame_action(
                "BACKWARD",
                self.frame_count,
                "REPOSITION"
            )

            self.controller.backward(self.motion_config.backup_duration)
            self.controller.stop()

            print("Turning to face search area...")

            self.controller.log_frame_action(
                "LEFT",   # direction doesn't matter for replay
                self.frame_count,
                "REPOSITION"
            )

            self.controller.turn_180()

            # Mark as retrieved
            retrieved_obj = DetectedObject(
                color=target_color,
                position=(0,0),
                area=0,
                distance=0,
                confidence=1.0,
                timestamp=time.time(),
                is_retrieved=True
            )
            self.retrieved_objects.append(retrieved_obj)

            print(f"[OK] Successfully retrieved {target_color.value}")

        finally:
            self.camera_enabled = True
            print("="*60 + "\n")

    def run_autonomous_mission(self):
        """Main mission loop with reactive avoidance"""
        print("\n" + "="*60)
        print("STARTING AUTONOMOUS MISSION")
        print(f"Sequence: {' -> '.join([c.value for c in self.mission_sequence])}")
        print("="*60)

        self.log_event("STARTING", "mission_start", status=f"sequence={[c.value for c in self.mission_sequence]}")
        mission_start_time = time.time()

        while len(self.retrieved_objects) < len(self.mission_sequence):
            self.current_stage = MissionStage.SCANNING
            print(f"\n--- Scanning for next object ---")

            target_color = self.find_next_target_color()
            if target_color is None:
                print("No target color found - mission complete?")
                break

            print(f"Searching for {target_color.value}...")

            # Initial search by turning
            found = False
            for attempt in range(12):
                frame = self.capture_frame()
                if frame is not None:
                    self.detector.process_frame(frame)
                    if self.detector.get_object_by_color(target_color) is not None:
                        found = True
                        break

                print(f"  Not found, turning ({attempt+1}/12)")
                self.controller.turn_degrees(30)
                time.sleep(1)

            if not found:
                print(f"ERROR: Could not find {target_color.value} object")
                continue

            print(f"\n[OK] Found {target_color.value}")

            # Approach with obstacle avoidance
            success = self.approach_with_avoidance(target_color)

            if success:
                self.execute_grasp_sequence(target_color)
            else:
                print(f"Failed to retrieve {target_color.value}")
                continue

            time.sleep(2)

        mission_duration = time.time() - mission_start_time

        print("\n" + "="*60)
        print("MISSION COMPLETE!")
        print("="*60)
        print(f"Retrieved: {len(self.retrieved_objects)}/{len(self.mission_sequence)} objects")
        print(f"Objects: {[obj.color.value for obj in self.retrieved_objects]}")
        print(f"Duration: {mission_duration:.1f} seconds")
        print("="*60)

        self.log_event("COMPLETE", "mission_end", status=f"duration={mission_duration:.1f},count={len(self.retrieved_objects)}")
        self.current_stage = MissionStage.COMPLETE

    def create_debug_display(self, frame: np.ndarray) -> np.ndarray:
        display = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # Draw all detected objects
        color_map = {
            ObjectColor.BLUE: (0, 165, 255),    # Orange
            ObjectColor.RED: (255, 255, 0),     # Cyan
            ObjectColor.GREEN: (255, 0, 255)    # Magenta
        }

        # Draw safety zones for obstacles (scaled with object size)
        for obj in self.detector.all_objects:
            color = color_map[obj.color]

            # Calculate object radius (half of sqrt(area))
            object_radius = self.detector.get_object_radius(obj)

            # Draw scaled safety zone for obstacles (larger than object)
            if obj != self.detector.target_object:
                # Danger zone = object radius + safety margin
                danger_zone = object_radius + self.detect_config.obstacle_safety_margin
                cv2.circle(display, obj.position, danger_zone, (0, 0, 255), 2)

                # Draw "DANGER" zone text
                cv2.putText(display, "KEEP OUT",
                           (obj.position[0] - 40, obj.position[1] - danger_zone - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

            # Draw object itself
            if obj == self.detector.target_object:
                # Target object - draw thick circle
                cv2.circle(display, obj.position, object_radius, color, 3)
                cv2.circle(display, obj.position, 5, (255, 255, 255), -1)

                camera_color = "orange" if obj.color == ObjectColor.BLUE else "cyan" if obj.color == ObjectColor.RED else "magenta"
                label = f"TARGET {obj.color.value} ({camera_color}) a:{obj.area:.0f}"
                cv2.putText(display, label, (obj.position[0] - 40, obj.position[1] - 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            else:
                # Obstacle object
                cv2.circle(display, obj.position, object_radius, color, 2)
                cv2.circle(display, obj.position, 3, color, -1)

                camera_color = "orange" if obj.color == ObjectColor.BLUE else "cyan" if obj.color == ObjectColor.RED else "magenta"
                label = f"{obj.color.value} ({camera_color})"
                cv2.putText(display, label, (obj.position[0] - 30, obj.position[1] - 20),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # Draw start position
        cv2.circle(display, self.start_position, 10, (0, 255, 255), -1)
        cv2.putText(display, "START", (self.start_position[0] - 30, self.start_position[1] - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        # Draw mission status
        y = 30
        cv2.putText(display, f"Stage: {self.current_stage.value}", (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        y += 25
        cv2.putText(display, f"Retrieved: {len(self.retrieved_objects)}/{len(self.mission_sequence)}", (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        # Show recording status and movement count
        y += 25
        if self.controller.recording_enabled:
            cv2.putText(display, f"RECORDING: {len(self.controller.action_log)} moves", (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        else:
            cv2.putText(display, f"Recorded: {len(self.controller.action_log)} moves", (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

        # Show lost counter
        y += 25
        cv2.putText(display, f"Lost frames: {self.lost_counter}/{self.detect_config.max_lost_frames}", (10, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        if self.avoidance.avoiding:
            y += 25
            cv2.putText(display, f"AVOIDING: step {self.avoidance.maneuver_step}", (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        elif self.detector.target_object:
            y += 25
            cv2.putText(display, f"Target: {self.detector.target_object.color.value}", (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 100), 1)

        # Show approach active status
        if self.approach_active:
            y += 25
            cv2.putText(display, "APPROACH ACTIVE", (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        return display

    def run(self):
        try:
            self.initialize()

            print("\nStarting autonomous mission in 3 seconds...")
            for i in range(3, 0, -1):
                print(f"{i}...")
                time.sleep(1)

            mission_thread = threading.Thread(target=self.run_autonomous_mission)
            mission_thread.daemon = True
            mission_thread.start()

            cv2.namedWindow("Autonomous Sorting Robot", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Autonomous Sorting Robot", 800, 600)

            while True:
                frame = self.capture_frame()
                if frame is not None:
                    # Update detection for display
                    self.detector.process_frame(frame)
                    display = self.create_debug_display(frame)
                    cv2.imshow("Autonomous Sorting Robot", display)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

                time.sleep(0.03)

        except KeyboardInterrupt:
            print("\nInterrupted by user")
        finally:
            self.cleanup()

    def cleanup(self):
        print("\nCleaning up...")
        self.controller.stop()
        if self.controller.serial:
            self.controller.serial.close()
        if self.camera:
            self.camera.stop()
        cv2.destroyAllWindows()
        if self.log_file:
            self.log_file.close()
        print("Cleanup complete")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    os.system("sudo pkill -9 -f python3 2>/dev/null")
    os.system("sudo pkill -9 -f picamera 2>/dev/null")
    time.sleep(1)

    print("\n" + "="*60)
    print("AUTONOMOUS SORTING ROBOT WITH REACTIVE AVOIDANCE")
    print("="*60)
    print("This robot will automatically retrieve objects in sequence:")
    print("  1. BLUE object  (appears ORANGE in flipped camera)")
    print("  2. RED object   (appears CYAN in flipped camera)")
    print("  3. GREEN object (appears MAGENTA in flipped camera)")
    print("\nCALIBRATED COLOR RANGES:")
    print("  Blue (orange):  H:0-68, S:221-255, V:0-255")
    print("  Red (cyan):     H:122-180, S:170-255, V:107-255")
    print("  Green (magenta): H:25-76 and 76-0, S:60-255, V:19-255")
    print(f"\nGrasp trigger: area > {DetectionConfig.grasp_area_threshold} pixels")
    print(f"Min blob area: {DetectionConfig.min_blob_area}")
    print(f"Obstacle safety margin: {DetectionConfig.obstacle_safety_margin} pixels")
    print(f"Max lost frames: {DetectionConfig.max_lost_frames}")
    print(f"180° turn duration: {MotionConfig().turn_duration_180deg}s")
    print("="*60 + "\n")

    robot = AutonomousSortingRobot()
    robot.run()
