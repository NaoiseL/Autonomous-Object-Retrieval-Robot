#include "MeMegaPi.h"
#include <Adafruit_NeoPixel.h>
#include <IRremote.h>
#include "Server.h"
 

// Lights Configuration
#define NUM_LEDS 4
Adafruit_NeoPixel stripA(NUM_LEDS, A13, NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel stripB(NUM_LEDS, A14, NEO_GRB + NEO_KHZ800);

// Motor Mapping
MeMegaPiDCMotor motor1(PORT3A);
MeMegaPiDCMotor motor2(PORT2A);
MeMegaPiDCMotor motor3(PORT3B);
MeMegaPiDCMotor motor4(PORT2B);

// Constants
#define SPEED_FORWARD 50
#define SPEED_TURN 40
#define SPEED_SEARCH 30
#define SPEED_BACKWARD 50
#define SPEED_TURN_180 60



// Servo Settings
Servo tiltServo;
Servo clawServo;

#define SERVO_STOP 90      // Neutral (Adjust to 88-92 if it creeps)
#define SERVO_CW 180       // Close speed
#define SERVO_CCW 0        // Open speed
#define ACTION_TIME 200   // Time to spin for full grip/release
#define TURN_180_TIME 1800
#define IR_SENSOR_PIN A12
#define BUZZER_PIN 2
#define IR_PIN 4/////

// TRACKING POSITION: Necessary for smooth transitions
int currentTilt = 135; 
int currentClaw = 170;

String inputString = "";
bool stringComplete = false;
bool isGrasping = false;
bool partyMode = false;

// IR Receiver
IRrecv irrecv(IR_PIN);
decode_results results;

// IR Remote Codes (NEC format - replace with your remote's codes)
#define BUTTON_1 0xFF6897  // Grasp
#define BUTTON_2 0xFF9867  // Release
#define BUTTON_3 0xFFB04F  // Search
#define BUTTON_4 0xFF30CF  // Party Mode

void setup() {
    Serial.begin(9600);
    
    pinMode(IR_SENSOR_PIN, INPUT);
    pinMode(BUZZER_PIN, OUTPUT);
    noTone(BUZZER_PIN); // Ensure buzzer is off initially
    
    irrecv.enableIRIn(); // Start IR receiver
    
    stripA.begin();
    stripB.begin();
    setStripColor(stripA.Color(0, 0, 0));
    
    // IMPORTANT: Attach the servo pin here
        // Attach servos to pins A14 and A15
    tiltServo.attach(A11);
    clawServo.attach(A15);

    // Initial neutral positions
    tiltServo.write(currentTilt);
    clawServo.write(currentClaw);

    stopMotors();
    Serial.println("READY");
}

void loop() {
    // Handle IR remote input
    if (irrecv.decode(&results)) {
        handleIR(results.value);
        irrecv.resume();
    }
    
    // Handle party mode LED effects
    if (partyMode) {
        updatePartyMode();
    }
    
    while (Serial.available()) {
        char inChar = (char)Serial.read();
        if (inChar == '\n') {
            stringComplete = true;
        } else {
            inputString += inChar;
        }
    }
    
    if (stringComplete) {
        inputString.trim();
        executeCommand(inputString);
        inputString = "";
        stringComplete = false;
    }
    
    // IR sensor fail-safe
    if (digitalRead(IR_SENSOR_PIN) == LOW && !isGrasping) {
        executeCommand("GRASP");
    }
    
    delay(5);
}

void smoothMove(Servo &s, int target, int &current, int speed) {
    target = constrain(target, 0, 180);
    while (current != target) {
        if (current < target) current++;
        else current--;
        s.write(current);
        delay(speed); 
    }
}
// helper function for led control
void setStripColor(uint32_t color) {
    for(int i = 0; i < NUM_LEDS; i++) {
        stripA.setPixelColor(i, color);
        stripB.setPixelColor(i, color);
    }
    stripA.show();
    stripB.show();
}

void executeCommand(String cmd) {
    if (cmd == "LEFT") {
        setStripColor(stripA.Color(0, 0, 255)); // Blue for turning
        motor1.run(SPEED_TURN);
        motor2.run(SPEED_TURN);
        motor3.run(SPEED_TURN);
        motor4.run(SPEED_TURN);
        Serial.println("EXEC: LEFT");
    }
    else if (cmd == "RIGHT") {
        setStripColor(stripA.Color(0, 0, 255)); // Blue for turning
        motor1.run(-SPEED_TURN);
        motor2.run(-SPEED_TURN);
        motor3.run(-SPEED_TURN);
        motor4.run(-SPEED_TURN);
        Serial.println("EXEC: RIGHT");
    }
    else if (cmd == "FORWARD") {
        setStripColor(stripA.Color(0, 255, 0)); // Green for forward
        motor1.run(-SPEED_FORWARD);
        motor2.run(SPEED_FORWARD);
        motor3.run(-SPEED_FORWARD);
        motor4.run(SPEED_FORWARD);
        Serial.println("EXEC: FORWARD");
    }
    else if (cmd == "BACKWARD") {
        setStripColor(stripA.Color(255, 0, 0)); // Red for reverse
        motor1.run(SPEED_BACKWARD);
        motor2.run(-SPEED_BACKWARD);
        motor3.run(SPEED_BACKWARD);
        motor4.run(-SPEED_BACKWARD);
        tone(BUZZER_PIN, 1000); // Continuous beep while reversing
        Serial.println("EXEC: BACKWARD");
    }
    else if (cmd == "SEARCH") {
        setStripColor(stripA.Color(255, 255, 0)); // Yellow for searching
        motor1.run(-SPEED_SEARCH);
        motor2.run(-SPEED_SEARCH);
        motor3.run(-SPEED_SEARCH);
        motor4.run(-SPEED_SEARCH);
        Serial.println("EXEC: SEARCH");
    }
    else if (cmd == "GRASP") {
        Serial.println("EXEC: GRASPING");
        stopMotors();
        
        
        // 3. Close claw
        smoothMove(clawServo, 55, currentClaw, 10);
        delay(1000);

        // 4. Tilt up
        smoothMove(tiltServo, 110, currentTilt, 10);
        delay(2000);

        isGrasping = true;
        Serial.println("EXEC: GRASP_COMPLETE");
    }
    else if (cmd == "RELEASE") {
        Serial.println("EXEC: RELEASING");
        
        // 1. Tilt down
        smoothMove(tiltServo, 140, currentTilt, 10);
        delay(500);

        // 2. Open claw
        smoothMove(clawServo, 170, currentClaw, 15);
        delay(500);
                
        isGrasping = false;
        Serial.println("EXEC: RELEASE_COMPLETE");
    }


    else if (cmd == "TURN_180") {
        Serial.println("EXEC: TURN_180");
        motor1.run(-SPEED_TURN_180);
        motor2.run(-SPEED_TURN_180);
        motor3.run(-SPEED_TURN_180);
        motor4.run(-SPEED_TURN_180);
        delay(TURN_180_TIME);
        stopMotors();
        Serial.println("EXEC: TURN_180_COMPLETE");
    }
    else if (cmd == "STOP") {
        setStripColor(stripA.Color(0, 0, 0)); // Off when stopped
        stopMotors();
        tone(BUZZER_PIN, 1000, 200); // Beep once for 200ms
        Serial.println("EXEC: STOP");
    }

    else {
        Serial.print("UNKNOWN: ");
        Serial.println(cmd);
    }
}

void stopMotors() {
    motor1.stop();
    motor2.stop();
    motor3.stop();
    motor4.stop();
    noTone(BUZZER_PIN); // Stop buzzer when motors stop
}

void handleIR(unsigned long value) {
    switch (value) {
        case BUTTON_1:
            executeCommand("GRASP");
            break;
        case BUTTON_2:
            executeCommand("RELEASE");
            break;
        case BUTTON_3:
            executeCommand("SEARCH");
            break;
        case BUTTON_4:
            partyMode = !partyMode;
            if (!partyMode) {
                setStripColor(stripA.Color(0, 0, 0)); // Turn off LEDs when exiting party mode
            }
            break;
        default:
            // Unknown button, pause movement
            executeCommand("STOP");
            break;
    }
}

void updatePartyMode() {
    static unsigned long lastUpdate = 0;
    static int colorIndex = 0;
    static int tiltDirection = 1;
    unsigned long currentTime = millis();
    
    if (currentTime - lastUpdate > 200) { // Update every 200ms
        uint32_t colors[] = {
            stripA.Color(255, 0, 0),   // Red
            stripA.Color(0, 255, 0),   // Green
            stripA.Color(0, 0, 255),   // Blue
            stripA.Color(255, 255, 0), // Yellow
            stripA.Color(255, 0, 255), // Magenta
            stripA.Color(0, 255, 255)  // Cyan
        };

        
        setStripColor(colors[colorIndex]);
        colorIndex = (colorIndex + 1) % 6;
        
        // Move tilt servo up and down
        currentTilt += tiltDirection * 5;
        if (currentTilt >= 140 || currentTilt <= 110) {
            tiltDirection = -tiltDirection;
            currentTilt = constrain(currentTilt, 110, 140);
        }
        tiltServo.write(currentTilt);
        
        lastUpdate = currentTime;
    }
}


