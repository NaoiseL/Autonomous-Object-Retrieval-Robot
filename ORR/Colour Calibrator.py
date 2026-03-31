#!/usr/bin/env python3
"""
Colour Calibration Tool for Flipped Camera
Use this to find the exact HSV ranges for your objects
Camera is flipped (hflip=1, vflip=1) - colours are inverted:
    Real BLUE appears ORANGE in camera
    Real RED appears CYAN in camera
    Real GREEN appears MAGENTA in camera
"""

import cv2
import numpy as np
from picamera2 import Picamera2
from libcamera import Transform
import time
import os

# ============================================================================
# CONFIGURATION
# ============================================================================

FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Initial HSV ranges (starting points - you'll adjust these)
INITIAL_RANGES = {
    'blue (looks orange)': {
        'lower': np.array([5, 100, 100]),
        'upper': np.array([30, 255, 255])
    },
    'red (looks cyan)': {
        'lower': np.array([85, 100, 100]),
        'upper': np.array([115, 255, 255])
    },
    'green (looks magenta)': {
        'lower1': np.array([140, 100, 100]),
        'upper1': np.array([170, 255, 255]),
        'lower2': np.array([0, 100, 100]),
        'upper2': np.array([10, 255, 255])
    }
}

# ============================================================================
# CALIBRATION CLASS
# ============================================================================

class ColourCalibrator:
    def __init__(self):
        self.camera = None
        self.current_colour = 'blue (looks orange)'
        self.current_ranges = INITIAL_RANGES[self.current_colour].copy()
        self.is_dual_range = False
        self.show_mask = True
        self.min_area = 500
        self.calibration_points = []  # Store calibration data
        
        # For trackbar windows
        self.window_name = "Colour Calibration"
        self.mask_window = "Mask View"
        self.controls_window = "Controls"
        
    def init_camera(self):
        """Initialise the flipped camera"""
        try:
            print("Initialising camera with flip (hflip=1, vflip=1)...")
            self.camera = Picamera2()
            
            # Apply flip transform - THIS CAUSES COLOUR INVERSION
            transform = Transform(hflip=1, vflip=1)
            
            config = self.camera.create_video_configuration(
                main={"size": (FRAME_WIDTH, FRAME_HEIGHT), "format": "RGB888"},
                transform=transform
            )
            self.camera.configure(config)
            self.camera.start()
            time.sleep(2)
            print("Camera started successfully")
            return True
        except Exception as e:
            print(f"Camera init error: {e}")
            return False
    
    def create_trackbars(self):
        """Create trackbars for HSV adjustment"""
        cv2.namedWindow(self.controls_window)
        
        if not self.is_dual_range:
            # Single range trackbars
            cv2.createTrackbar('H Low', self.controls_window, 
                              self.current_ranges['lower'][0], 180, self.nothing)
            cv2.createTrackbar('H High', self.controls_window, 
                              self.current_ranges['upper'][0], 180, self.nothing)
            cv2.createTrackbar('S Low', self.controls_window, 
                              self.current_ranges['lower'][1], 255, self.nothing)
            cv2.createTrackbar('S High', self.controls_window, 
                              self.current_ranges['upper'][1], 255, self.nothing)
            cv2.createTrackbar('V Low', self.controls_window, 
                              self.current_ranges['lower'][2], 255, self.nothing)
            cv2.createTrackbar('V High', self.controls_window, 
                              self.current_ranges['upper'][2], 255, self.nothing)
        else:
            # Dual range trackbars (for magenta/green)
            cv2.createTrackbar('H1 Low', self.controls_window, 
                              self.current_ranges['lower1'][0], 180, self.nothing)
            cv2.createTrackbar('H1 High', self.controls_window, 
                              self.current_ranges['upper1'][0], 180, self.nothing)
            cv2.createTrackbar('H2 Low', self.controls_window, 
                              self.current_ranges['lower2'][0], 180, self.nothing)
            cv2.createTrackbar('H2 High', self.controls_window, 
                              self.current_ranges['upper2'][0], 180, self.nothing)
            cv2.createTrackbar('S Low', self.controls_window, 
                              100, 255, self.nothing)  # Shared S
            cv2.createTrackbar('S High', self.controls_window, 
                              255, 255, self.nothing)  # Shared S
            cv2.createTrackbar('V Low', self.controls_window, 
                              100, 255, self.nothing)  # Shared V
            cv2.createTrackbar('V High', self.controls_window, 
                              255, 255, self.nothing)  # Shared V
    
    def nothing(self, x):
        """Dummy function for trackbar"""
        pass
    
    def update_ranges_from_trackbars(self):
        """Get current trackbar values"""
        if not self.is_dual_range:
            self.current_ranges['lower'] = np.array([
                cv2.getTrackbarPos('H Low', self.controls_window),
                cv2.getTrackbarPos('S Low', self.controls_window),
                cv2.getTrackbarPos('V Low', self.controls_window)
            ])
            self.current_ranges['upper'] = np.array([
                cv2.getTrackbarPos('H High', self.controls_window),
                cv2.getTrackbarPos('S High', self.controls_window),
                cv2.getTrackbarPos('V High', self.controls_window)
            ])
        else:
            # Get S and V values
            s_low = cv2.getTrackbarPos('S Low', self.controls_window)
            s_high = cv2.getTrackbarPos('S High', self.controls_window)
            v_low = cv2.getTrackbarPos('V Low', self.controls_window)
            v_high = cv2.getTrackbarPos('V High', self.controls_window)
            
            self.current_ranges['lower1'] = np.array([
                cv2.getTrackbarPos('H1 Low', self.controls_window),
                s_low, v_low
            ])
            self.current_ranges['upper1'] = np.array([
                cv2.getTrackbarPos('H1 High', self.controls_window),
                s_high, v_high
            ])
            self.current_ranges['lower2'] = np.array([
                cv2.getTrackbarPos('H2 Low', self.controls_window),
                s_low, v_low
            ])
            self.current_ranges['upper2'] = np.array([
                cv2.getTrackbarPos('H2 High', self.controls_window),
                s_high, v_high
            ])
    
    def detect_colour(self, frame_bgr):
        """Apply current HSV ranges to detect colour"""
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        
        if not self.is_dual_range:
            mask = cv2.inRange(hsv, self.current_ranges['lower'], 
                              self.current_ranges['upper'])
        else:
            mask1 = cv2.inRange(hsv, self.current_ranges['lower1'], 
                               self.current_ranges['upper1'])
            mask2 = cv2.inRange(hsv, self.current_ranges['lower2'], 
                               self.current_ranges['upper2'])
            mask = cv2.bitwise_or(mask1, mask2)
        
        # Clean up mask
        kernel = np.ones((5,5), np.uint8)
        mask = cv2.erode(mask, kernel, iterations=1)
        mask = cv2.dilate(mask, kernel, iterations=2)
        
        return mask
    
    def analyse_detection(self, mask, frame_bgr):
        """Analyse detected blobs and return info"""
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, 
                                       cv2.CHAIN_APPROX_SIMPLE)
        
        result = {
            'blob_count': len(contours),
            'largest_area': 0,
            'total_area': 0,
            'avg_hue': 0,
            'avg_sat': 0,
            'avg_val': 0,
            'has_good_blob': False
        }
        
        if contours:
            # Find largest contour
            largest = max(contours, key=cv2.contourArea)
            result['largest_area'] = cv2.contourArea(largest)
            result['has_good_blob'] = result['largest_area'] > self.min_area
            
            # Calculate total area
            for contour in contours:
                result['total_area'] += cv2.contourArea(contour)
            
            # Calculate average HSV of largest blob
            if result['has_good_blob']:
                mask_blob = np.zeros_like(mask)
                cv2.drawContours(mask_blob, [largest], -1, 255, -1)
                
                hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
                result['avg_hue'] = np.mean(hsv[:,:,0][mask_blob > 0])
                result['avg_sat'] = np.mean(hsv[:,:,1][mask_blob > 0])
                result['avg_val'] = np.mean(hsv[:,:,2][mask_blob > 0])
        
        return result, contours, largest if contours else None
    
    def draw_info(self, frame, mask, result, contours):
        """Draw calibration info on frame"""
        # Draw mask overlay
        mask_coloured = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        mask_coloured[mask > 0] = [0, 255, 0]  # Green overlay
        overlay = cv2.addWeighted(frame, 0.7, mask_coloured, 0.3, 0)
        
        # Draw contours
        cv2.drawContours(overlay, contours, -1, (0, 0, 255), 2)
        
        # Draw info text
        y_offset = 30
        lines = [
            f"Colour: {self.current_colour}",
            f"Blobs: {result['blob_count']}",
            f"Largest area: {result['largest_area']:.0f} px",
            f"Min area threshold: {self.min_area}",
            f"Detection: {'GOOD' if result['has_good_blob'] else 'POOR'}",
        ]
        
        if result['has_good_blob']:
            lines.extend([
                f"Avg Hue: {result['avg_hue']:.1f}",
                f"Avg Sat: {result['avg_sat']:.1f}",
                f"Avg Val: {result['avg_val']:.1f}"
            ])
        
        for line in lines:
            cv2.putText(overlay, line, (10, y_offset), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, 
                       (255, 255, 255), 1)
            y_offset += 20
        
        # Draw current ranges
        y_offset = FRAME_HEIGHT - 100
        cv2.putText(overlay, "Current HSV ranges:", (10, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 0), 1)
        y_offset += 20
        
        if not self.is_dual_range:
            range_text = f"  H:{self.current_ranges['lower'][0]}-{self.current_ranges['upper'][0]}"
            range_text += f"  S:{self.current_ranges['lower'][1]}-{self.current_ranges['upper'][1]}"
            range_text += f"  V:{self.current_ranges['lower'][2]}-{self.current_ranges['upper'][2]}"
            cv2.putText(overlay, range_text, (10, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
        else:
            cv2.putText(overlay, f"Range1 H:{self.current_ranges['lower1'][0]}-{self.current_ranges['upper1'][0]}", 
                       (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
            y_offset += 15
            cv2.putText(overlay, f"Range2 H:{self.current_ranges['lower2'][0]}-{self.current_ranges['upper2'][0]}", 
                       (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
            y_offset += 15
            cv2.putText(overlay, f"S:{self.current_ranges['lower1'][1]}-{self.current_ranges['upper1'][1]}", 
                       (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
            y_offset += 15
            cv2.putText(overlay, f"V:{self.current_ranges['lower1'][2]}-{self.current_ranges['upper1'][2]}", 
                       (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
        
        # Draw instructions
        instructions = [
            "1-3: Select colour (1=Blue/Orange, 2=Red/Cyan, 3=Green/Magenta)",
            "m: Toggle mask view",
            "+/-: Adjust min area threshold",
            "s: Save current ranges",
            "q: Quit"
        ]
        y_inst = FRAME_HEIGHT - 30
        for inst in instructions:
            cv2.putText(overlay, inst, (10, y_inst),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 200, 255), 1)
            y_inst -= 15
        
        return overlay
    
    def save_ranges(self):
        """Save current ranges to file"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"calibrated_ranges_{timestamp}.py"
        
        with open(filename, 'w') as f:
            f.write("# Calibrated HSV ranges for flipped camera\n")
            f.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            if not self.is_dual_range:
                f.write(f"# {self.current_colour}\n")
                f.write(f"LOWER = np.array([{self.current_ranges['lower'][0]}, "
                       f"{self.current_ranges['lower'][1]}, {self.current_ranges['lower'][2]}])\n")
                f.write(f"UPPER = np.array([{self.current_ranges['upper'][0]}, "
                       f"{self.current_ranges['upper'][1]}, {self.current_ranges['upper'][2]}])\n")
            else:
                f.write(f"# {self.current_colour} (dual range)\n")
                f.write(f"LOWER1 = np.array([{self.current_ranges['lower1'][0]}, "
                       f"{self.current_ranges['lower1'][1]}, {self.current_ranges['lower1'][2]}])\n")
                f.write(f"UPPER1 = np.array([{self.current_ranges['upper1'][0]}, "
                       f"{self.current_ranges['upper1'][1]}, {self.current_ranges['upper1'][2]}])\n")
                f.write(f"LOWER2 = np.array([{self.current_ranges['lower2'][0]}, "
                       f"{self.current_ranges['lower2'][1]}, {self.current_ranges['lower2'][2]}])\n")
                f.write(f"UPPER2 = np.array([{self.current_ranges['upper2'][0]}, "
                       f"{self.current_ranges['upper2'][1]}, {self.current_ranges['upper2'][2]}])\n")
        
        print(f"\n[SAVED] Ranges saved to {filename}")
        print("Current ranges:")
        if not self.is_dual_range:
            print(f"  LOWER = [{self.current_ranges['lower'][0]}, "
                  f"{self.current_ranges['lower'][1]}, {self.current_ranges['lower'][2]}]")
            print(f"  UPPER = [{self.current_ranges['upper'][0]}, "
                  f"{self.current_ranges['upper'][1]}, {self.current_ranges['upper'][2]}]")
        else:
            print(f"  LOWER1 = [{self.current_ranges['lower1'][0]}, "
                  f"{self.current_ranges['lower1'][1]}, {self.current_ranges['lower1'][2]}]")
            print(f"  UPPER1 = [{self.current_ranges['upper1'][0]}, "
                  f"{self.current_ranges['upper1'][1]}, {self.current_ranges['upper1'][2]}]")
            print(f"  LOWER2 = [{self.current_ranges['lower2'][0]}, "
                  f"{self.current_ranges['lower2'][1]}, {self.current_ranges['lower2'][2]}]")
            print(f"  UPPER2 = [{self.current_ranges['upper2'][0]}, "
                  f"{self.current_ranges['upper2'][1]}, {self.current_ranges['upper2'][2]}]")
    
    def run(self):
        """Main calibration loop"""
        # Initialise camera
        if not self.init_camera():
            return
        
        # Create windows
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.namedWindow(self.mask_window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 800, 600)
        cv2.resizeWindow(self.mask_window, 400, 300)
        
        # Create trackbars for initial colour
        self.create_trackbars()
        
        print("\n" + "="*60)
        print("COLOUR CALIBRATION TOOL")
        print("="*60)
        print("\nInstructions:")
        print("  1. Press 1 for Blue object (looks ORANGE in camera)")
        print("  2. Press 2 for Red object (looks CYAN in camera)")
        print("  3. Press 3 for Green object (looks MAGENTA in camera)")
        print("\nAdjust trackbars until your object is clearly detected")
        print("The mask view shows what's being detected")
        print("Press 's' to save current ranges")
        print("Press 'q' to quit")
        print("="*60 + "\n")
        
        try:
            while True:
                # Capture frame
                frame_rgb = self.camera.capture_array()
                frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                
                # Update ranges from trackbars
                self.update_ranges_from_trackbars()
                
                # Detect colour
                mask = self.detect_colour(frame_bgr)
                
                # Analyse detection
                result, contours, largest = self.analyse_detection(mask, frame_bgr)
                
                # Create display
                display = self.draw_info(frame_bgr, mask, result, contours)
                
                # Create mask display
                mask_display = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                mask_display[mask > 0] = [0, 255, 0]  # Green for detected areas
                
                # Show frames
                cv2.imshow(self.window_name, display)
                cv2.imshow(self.mask_window, mask_display)
                
                # Handle keys
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    self.save_ranges()
                elif key == ord('m'):
                    self.show_mask = not self.show_mask
                elif key == ord('+') or key == ord('='):
                    self.min_area += 100
                    print(f"Min area threshold: {self.min_area}")
                elif key == ord('-') or key == ord('_'):
                    self.min_area = max(100, self.min_area - 100)
                    print(f"Min area threshold: {self.min_area}")
                elif key == ord('1'):
                    self.current_colour = 'blue (looks orange)'
                    self.current_ranges = INITIAL_RANGES[self.current_colour].copy()
                    self.is_dual_range = False
                    cv2.destroyWindow(self.controls_window)
                    self.create_trackbars()
                    print(f"\nSwitched to: {self.current_colour}")
                elif key == ord('2'):
                    self.current_colour = 'red (looks cyan)'
                    self.current_ranges = INITIAL_RANGES[self.current_colour].copy()
                    self.is_dual_range = False
                    cv2.destroyWindow(self.controls_window)
                    self.create_trackbars()
                    print(f"\nSwitched to: {self.current_colour}")
                elif key == ord('3'):
                    self.current_colour = 'green (looks magenta)'
                    self.current_ranges = INITIAL_RANGES[self.current_colour].copy()
                    self.is_dual_range = True
                    cv2.destroyWindow(self.controls_window)
                    self.create_trackbars()
                    print(f"\nSwitched to: {self.current_colour}")
                
        except KeyboardInterrupt:
            print("\nCalibration interrupted")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean shutdown"""
        print("\nCleaning up...")
        if self.camera:
            self.camera.stop()
        cv2.destroyAllWindows()
        print("Done.")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Kill old processes
    os.system("sudo pkill -9 -f python3 2>/dev/null")
    os.system("sudo pkill -9 -f picamera 2>/dev/null")
    time.sleep(1)
    
    # Run calibrator
    calibrator = ColourCalibrator()
    calibrator.run()#!/usr/bin/env python3
"""
Color Calibration Tool for Flipped Camera
Use this to find the exact HSV ranges for your objects
Camera is flipped (hflip=1, vflip=1) - colors are inverted:
    Real BLUE appears ORANGE in camera
    Real RED appears CYAN in camera
    Real GREEN appears MAGENTA in camera
"""

import cv2
import numpy as np
from picamera2 import Picamera2
from libcamera import Transform
import time
import os

# ============================================================================
# CONFIGURATION
# ============================================================================

FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Initial HSV ranges (starting points - you'll adjust these)
INITIAL_RANGES = {
    'blue (looks orange)': {
        'lower': np.array([5, 100, 100]),
        'upper': np.array([30, 255, 255])
    },
    'red (looks cyan)': {
        'lower': np.array([85, 100, 100]),
        'upper': np.array([115, 255, 255])
    },
    'green (looks magenta)': {
        'lower1': np.array([140, 100, 100]),
        'upper1': np.array([170, 255, 255]),
        'lower2': np.array([0, 100, 100]),
        'upper2': np.array([10, 255, 255])
    }
}

# ============================================================================
# CALIBRATION CLASS
# ============================================================================

class ColorCalibrator:
    def __init__(self):
        self.camera = None
        self.current_color = 'blue (looks orange)'
        self.current_ranges = INITIAL_RANGES[self.current_color].copy()
        self.is_dual_range = False
        self.show_mask = True
        self.min_area = 500
        self.calibration_points = []  # Store calibration data
        
        # For trackbar windows
        self.window_name = "Color Calibration"
        self.mask_window = "Mask View"
        self.controls_window = "Controls"
        
    def init_camera(self):
        """Initialize the flipped camera"""
        try:
            print("Initializing camera with flip (hflip=1, vflip=1)...")
            self.camera = Picamera2()
            
            # Apply flip transform - THIS CAUSES COLOR INVERSION
            transform = Transform(hflip=1, vflip=1)
            
            config = self.camera.create_video_configuration(
                main={"size": (FRAME_WIDTH, FRAME_HEIGHT), "format": "RGB888"},
                transform=transform
            )
            self.camera.configure(config)
            self.camera.start()
            time.sleep(2)
            print("Camera started successfully")
            return True
        except Exception as e:
            print(f"Camera init error: {e}")
            return False
    
    def create_trackbars(self):
        """Create trackbars for HSV adjustment"""
        cv2.namedWindow(self.controls_window)
        
        if not self.is_dual_range:
            # Single range trackbars
            cv2.createTrackbar('H Low', self.controls_window, 
                              self.current_ranges['lower'][0], 180, self.nothing)
            cv2.createTrackbar('H High', self.controls_window, 
                              self.current_ranges['upper'][0], 180, self.nothing)
            cv2.createTrackbar('S Low', self.controls_window, 
                              self.current_ranges['lower'][1], 255, self.nothing)
            cv2.createTrackbar('S High', self.controls_window, 
                              self.current_ranges['upper'][1], 255, self.nothing)
            cv2.createTrackbar('V Low', self.controls_window, 
                              self.current_ranges['lower'][2], 255, self.nothing)
            cv2.createTrackbar('V High', self.controls_window, 
                              self.current_ranges['upper'][2], 255, self.nothing)
        else:
            # Dual range trackbars (for magenta/green)
            cv2.createTrackbar('H1 Low', self.controls_window, 
                              self.current_ranges['lower1'][0], 180, self.nothing)
            cv2.createTrackbar('H1 High', self.controls_window, 
                              self.current_ranges['upper1'][0], 180, self.nothing)
            cv2.createTrackbar('H2 Low', self.controls_window, 
                              self.current_ranges['lower2'][0], 180, self.nothing)
            cv2.createTrackbar('H2 High', self.controls_window, 
                              self.current_ranges['upper2'][0], 180, self.nothing)
            cv2.createTrackbar('S Low', self.controls_window, 
                              100, 255, self.nothing)  # Shared S
            cv2.createTrackbar('S High', self.controls_window, 
                              255, 255, self.nothing)  # Shared S
            cv2.createTrackbar('V Low', self.controls_window, 
                              100, 255, self.nothing)  # Shared V
            cv2.createTrackbar('V High', self.controls_window, 
                              255, 255, self.nothing)  # Shared V
    
    def nothing(self, x):
        """Dummy function for trackbar"""
        pass
    
    def update_ranges_from_trackbars(self):
        """Get current trackbar values"""
        if not self.is_dual_range:
            self.current_ranges['lower'] = np.array([
                cv2.getTrackbarPos('H Low', self.controls_window),
                cv2.getTrackbarPos('S Low', self.controls_window),
                cv2.getTrackbarPos('V Low', self.controls_window)
            ])
            self.current_ranges['upper'] = np.array([
                cv2.getTrackbarPos('H High', self.controls_window),
                cv2.getTrackbarPos('S High', self.controls_window),
                cv2.getTrackbarPos('V High', self.controls_window)
            ])
        else:
            # Get S and V values
            s_low = cv2.getTrackbarPos('S Low', self.controls_window)
            s_high = cv2.getTrackbarPos('S High', self.controls_window)
            v_low = cv2.getTrackbarPos('V Low', self.controls_window)
            v_high = cv2.getTrackbarPos('V High', self.controls_window)
            
            self.current_ranges['lower1'] = np.array([
                cv2.getTrackbarPos('H1 Low', self.controls_window),
                s_low, v_low
            ])
            self.current_ranges['upper1'] = np.array([
                cv2.getTrackbarPos('H1 High', self.controls_window),
                s_high, v_high
            ])
            self.current_ranges['lower2'] = np.array([
                cv2.getTrackbarPos('H2 Low', self.controls_window),
                s_low, v_low
            ])
            self.current_ranges['upper2'] = np.array([
                cv2.getTrackbarPos('H2 High', self.controls_window),
                s_high, v_high
            ])
    
    def detect_color(self, frame_bgr):
        """Apply current HSV ranges to detect color"""
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        
        if not self.is_dual_range:
            mask = cv2.inRange(hsv, self.current_ranges['lower'], 
                              self.current_ranges['upper'])
        else:
            mask1 = cv2.inRange(hsv, self.current_ranges['lower1'], 
                               self.current_ranges['upper1'])
            mask2 = cv2.inRange(hsv, self.current_ranges['lower2'], 
                               self.current_ranges['upper2'])
            mask = cv2.bitwise_or(mask1, mask2)
        
        # Clean up mask
        kernel = np.ones((5,5), np.uint8)
        mask = cv2.erode(mask, kernel, iterations=1)
        mask = cv2.dilate(mask, kernel, iterations=2)
        
        return mask
    
    def analyze_detection(self, mask, frame_bgr):
        """Analyze detected blobs and return info"""
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, 
                                       cv2.CHAIN_APPROX_SIMPLE)
        
        result = {
            'blob_count': len(contours),
            'largest_area': 0,
            'total_area': 0,
            'avg_hue': 0,
            'avg_sat': 0,
            'avg_val': 0,
            'has_good_blob': False
        }
        
        if contours:
            # Find largest contour
            largest = max(contours, key=cv2.contourArea)
            result['largest_area'] = cv2.contourArea(largest)
            result['has_good_blob'] = result['largest_area'] > self.min_area
            
            # Calculate total area
            for contour in contours:
                result['total_area'] += cv2.contourArea(contour)
            
            # Calculate average HSV of largest blob
            if result['has_good_blob']:
                mask_blob = np.zeros_like(mask)
                cv2.drawContours(mask_blob, [largest], -1, 255, -1)
                
                hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
                result['avg_hue'] = np.mean(hsv[:,:,0][mask_blob > 0])
                result['avg_sat'] = np.mean(hsv[:,:,1][mask_blob > 0])
                result['avg_val'] = np.mean(hsv[:,:,2][mask_blob > 0])
        
        return result, contours, largest if contours else None
    
    def draw_info(self, frame, mask, result, contours):
        """Draw calibration info on frame"""
        # Draw mask overlay
        mask_colored = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        mask_colored[mask > 0] = [0, 255, 0]  # Green overlay
        overlay = cv2.addWeighted(frame, 0.7, mask_colored, 0.3, 0)
        
        # Draw contours
        cv2.drawContours(overlay, contours, -1, (0, 0, 255), 2)
        
        # Draw info text
        y_offset = 30
        lines = [
            f"Color: {self.current_color}",
            f"Blobs: {result['blob_count']}",
            f"Largest area: {result['largest_area']:.0f} px",
            f"Min area threshold: {self.min_area}",
            f"Detection: {'GOOD' if result['has_good_blob'] else 'POOR'}",
        ]
        
        if result['has_good_blob']:
            lines.extend([
                f"Avg Hue: {result['avg_hue']:.1f}",
                f"Avg Sat: {result['avg_sat']:.1f}",
                f"Avg Val: {result['avg_val']:.1f}"
            ])
        
        for line in lines:
            cv2.putText(overlay, line, (10, y_offset), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, 
                       (255, 255, 255), 1)
            y_offset += 20
        
        # Draw current ranges
        y_offset = FRAME_HEIGHT - 100
        cv2.putText(overlay, "Current HSV ranges:", (10, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 0), 1)
        y_offset += 20
        
        if not self.is_dual_range:
            range_text = f"  H:{self.current_ranges['lower'][0]}-{self.current_ranges['upper'][0]}"
            range_text += f"  S:{self.current_ranges['lower'][1]}-{self.current_ranges['upper'][1]}"
            range_text += f"  V:{self.current_ranges['lower'][2]}-{self.current_ranges['upper'][2]}"
            cv2.putText(overlay, range_text, (10, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
        else:
            cv2.putText(overlay, f"Range1 H:{self.current_ranges['lower1'][0]}-{self.current_ranges['upper1'][0]}", 
                       (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
            y_offset += 15
            cv2.putText(overlay, f"Range2 H:{self.current_ranges['lower2'][0]}-{self.current_ranges['upper2'][0]}", 
                       (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
            y_offset += 15
            cv2.putText(overlay, f"S:{self.current_ranges['lower1'][1]}-{self.current_ranges['upper1'][1]}", 
                       (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
            y_offset += 15
            cv2.putText(overlay, f"V:{self.current_ranges['lower1'][2]}-{self.current_ranges['upper1'][2]}", 
                       (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)
        
        # Draw instructions
        instructions = [
            "1-3: Select color (1=Blue/Orange, 2=Red/Cyan, 3=Green/Magenta)",
            "m: Toggle mask view",
            "+/-: Adjust min area threshold",
            "s: Save current ranges",
            "q: Quit"
        ]
        y_inst = FRAME_HEIGHT - 30
        for inst in instructions:
            cv2.putText(overlay, inst, (10, y_inst),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 200, 255), 1)
            y_inst -= 15
        
        return overlay
    
    def save_ranges(self):
        """Save current ranges to file"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"calibrated_ranges_{timestamp}.py"
        
        with open(filename, 'w') as f:
            f.write("# Calibrated HSV ranges for flipped camera\n")
            f.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            if not self.is_dual_range:
                f.write(f"# {self.current_color}\n")
                f.write(f"LOWER = np.array([{self.current_ranges['lower'][0]}, "
                       f"{self.current_ranges['lower'][1]}, {self.current_ranges['lower'][2]}])\n")
                f.write(f"UPPER = np.array([{self.current_ranges['upper'][0]}, "
                       f"{self.current_ranges['upper'][1]}, {self.current_ranges['upper'][2]}])\n")
            else:
                f.write(f"# {self.current_color} (dual range)\n")
                f.write(f"LOWER1 = np.array([{self.current_ranges['lower1'][0]}, "
                       f"{self.current_ranges['lower1'][1]}, {self.current_ranges['lower1'][2]}])\n")
                f.write(f"UPPER1 = np.array([{self.current_ranges['upper1'][0]}, "
                       f"{self.current_ranges['upper1'][1]}, {self.current_ranges['upper1'][2]}])\n")
                f.write(f"LOWER2 = np.array([{self.current_ranges['lower2'][0]}, "
                       f"{self.current_ranges['lower2'][1]}, {self.current_ranges['lower2'][2]}])\n")
                f.write(f"UPPER2 = np.array([{self.current_ranges['upper2'][0]}, "
                       f"{self.current_ranges['upper2'][1]}, {self.current_ranges['upper2'][2]}])\n")
        
        print(f"\n[SAVED] Ranges saved to {filename}")
        print("Current ranges:")
        if not self.is_dual_range:
            print(f"  LOWER = [{self.current_ranges['lower'][0]}, "
                  f"{self.current_ranges['lower'][1]}, {self.current_ranges['lower'][2]}]")
            print(f"  UPPER = [{self.current_ranges['upper'][0]}, "
                  f"{self.current_ranges['upper'][1]}, {self.current_ranges['upper'][2]}]")
        else:
            print(f"  LOWER1 = [{self.current_ranges['lower1'][0]}, "
                  f"{self.current_ranges['lower1'][1]}, {self.current_ranges['lower1'][2]}]")
            print(f"  UPPER1 = [{self.current_ranges['upper1'][0]}, "
                  f"{self.current_ranges['upper1'][1]}, {self.current_ranges['upper1'][2]}]")
            print(f"  LOWER2 = [{self.current_ranges['lower2'][0]}, "
                  f"{self.current_ranges['lower2'][1]}, {self.current_ranges['lower2'][2]}]")
            print(f"  UPPER2 = [{self.current_ranges['upper2'][0]}, "
                  f"{self.current_ranges['upper2'][1]}, {self.current_ranges['upper2'][2]}]")
    
    def run(self):
        """Main calibration loop"""
        # Initialize camera
        if not self.init_camera():
            return
        
        # Create windows
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.namedWindow(self.mask_window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window_name, 800, 600)
        cv2.resizeWindow(self.mask_window, 400, 300)
        
        # Create trackbars for initial color
        self.create_trackbars()
        
        print("\n" + "="*60)
        print("COLOR CALIBRATION TOOL")
        print("="*60)
        print("\nInstructions:")
        print("  1. Press 1 for Blue object (looks ORANGE in camera)")
        print("  2. Press 2 for Red object (looks CYAN in camera)")
        print("  3. Press 3 for Green object (looks MAGENTA in camera)")
        print("\nAdjust trackbars until your object is clearly detected")
        print("The mask view shows what's being detected")
        print("Press 's' to save current ranges")
        print("Press 'q' to quit")
        print("="*60 + "\n")
        
        try:
            while True:
                # Capture frame
                frame_rgb = self.camera.capture_array()
                frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                
                # Update ranges from trackbars
                self.update_ranges_from_trackbars()
                
                # Detect color
                mask = self.detect_color(frame_bgr)
                
                # Analyze detection
                result, contours, largest = self.analyze_detection(mask, frame_bgr)
                
                # Create display
                display = self.draw_info(frame_bgr, mask, result, contours)
                
                # Create mask display
                mask_display = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
                mask_display[mask > 0] = [0, 255, 0]  # Green for detected areas
                
                # Show frames
                cv2.imshow(self.window_name, display)
                cv2.imshow(self.mask_window, mask_display)
                
                # Handle keys
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    self.save_ranges()
                elif key == ord('m'):
                    self.show_mask = not self.show_mask
                elif key == ord('+') or key == ord('='):
                    self.min_area += 100
                    print(f"Min area threshold: {self.min_area}")
                elif key == ord('-') or key == ord('_'):
                    self.min_area = max(100, self.min_area - 100)
                    print(f"Min area threshold: {self.min_area}")
                elif key == ord('1'):
                    self.current_color = 'blue (looks orange)'
                    self.current_ranges = INITIAL_RANGES[self.current_color].copy()
                    self.is_dual_range = False
                    cv2.destroyWindow(self.controls_window)
                    self.create_trackbars()
                    print(f"\nSwitched to: {self.current_color}")
                elif key == ord('2'):
                    self.current_color = 'red (looks cyan)'
                    self.current_ranges = INITIAL_RANGES[self.current_color].copy()
                    self.is_dual_range = False
                    cv2.destroyWindow(self.controls_window)
                    self.create_trackbars()
                    print(f"\nSwitched to: {self.current_color}")
                elif key == ord('3'):
                    self.current_color = 'green (looks magenta)'
                    self.current_ranges = INITIAL_RANGES[self.current_color].copy()
                    self.is_dual_range = True
                    cv2.destroyWindow(self.controls_window)
                    self.create_trackbars()
                    print(f"\nSwitched to: {self.current_color}")
                
        except KeyboardInterrupt:
            print("\nCalibration interrupted")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean shutdown"""
        print("\nCleaning up...")
        if self.camera:
            self.camera.stop()
        cv2.destroyAllWindows()
        print("Done.")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Kill old processes
    os.system("sudo pkill -9 -f python3 2>/dev/null")
    os.system("sudo pkill -9 -f picamera 2>/dev/null")
    time.sleep(1)
    
    # Run calibrator
    calibrator = ColorCalibrator()
    calibrator.run()
