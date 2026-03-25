#include "MeMegaPi.h"
#include <Adafruit_NeoPixel.h>
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


#define TURN_180_TIME 1800

// TRACKING POSITION: Necessary for smooth transitions
int currentClaw = 170;
int currentTilt = 100;

String inputString = "";
bool stringComplete = false;
bool isGrasping = false;




void setup() {
    Serial.begin(9600);

    stripA.begin();
    stripB.begin();
    setStripColor(stripA.Color(0, 0, 0));
    
    // IMPORTANT: Attach the servo pin here
        // Attach servos to pins A14 and A15
    tiltServo.attach(A11);
    clawServo.attach(A9);

    // Initial neutral positions
    tiltServo.write(currentTilt);
    clawServo.write(currentClaw);

    stopMotors();
    Serial.println("READY");
}

void loop() {
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
        setStripColor(stripA.Color(255, 150, 120)); // Red for reverse
       
        motor1.run(SPEED_BACKWARD);
        motor2.run(-SPEED_BACKWARD);
        motor3.run(SPEED_BACKWARD);
        motor4.run(-SPEED_BACKWARD);
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
        setStripColor(stripA.Color(255, 20, 147));
        
        // 3. Close claw
        smoothMove(clawServo, 55, currentClaw, 10);
        delay(1000);

        // 4. Tilt up
        smoothMove(tiltServo, 120, currentTilt, 10);
        delay(2000);

        isGrasping = true;
        Serial.println("EXEC: GRASP_COMPLETE");
    }
    else if (cmd == "RELEASE") {
        Serial.println("EXEC: RELEASING");
        setStripColor(stripA.Color(0, 255, 255));
        
        // 1. Tilt down
        smoothMove(tiltServo, 100, currentTilt, 10);
        delay(500);

        // 2. Open claw
        smoothMove(clawServo, 170, currentClaw, 20);
        delay(500);
                
        isGrasping = false;
        Serial.println("EXEC: RELEASE_COMPLETE");
    }


    else if (cmd == "TURN_180") {
        Serial.println("EXEC: TURN_180");
        setStripColor(stripA.Color(128, 0, 128));
        motor1.run(-SPEED_TURN_180);
        motor2.run(-SPEED_TURN_180);
        motor3.run(-SPEED_TURN_180);
        motor4.run(-SPEED_TURN_180);
        delay(TURN_180_TIME);
        stopMotors();
        Serial.println("EXEC: TURN_180_COMPLETE");
    }
    else if (cmd == "STOP") {
        setStripColor(stripA.Color(255, 0, 0)); 
        stopMotors();
      
        Serial.println("EXEC: STOP");
    }

    else if(cmd == "PARTYMODE"){
        for (int i = 0; i < 10; i++) {
            setStripColor(stripA.Color(random(255), random(255), random(255)));
            delay(200);
        }
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
}





