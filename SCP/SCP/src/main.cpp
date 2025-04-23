#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <SPI.h>
#include <MFRC522.h>
#include <ESP32Servo.h> // Using ESP32Servo library

// ------------------ Wi-Fi Credentials ---------------------
const char* WIFI_SSID     = "iPhone";
const char* WIFI_PASSWORD = "Nityaa14";

// ------------------ MQTT Broker Settings -------------------
const char* MQTT_BROKER   = "broker.emqx.io";
const int   MQTT_PORT     = 1883;
const char* MQTT_CLIENT_ID = "esp32_parking_system";
const char* MQTT_PUB_TOPIC = "parking/status";

// ------------------ Ultrasonic Sensor Settings ------------
#define NUM_SENSORS 5
#define DISTANCE_THRESHOLD 20 // Distance threshold in cm

// Define pins for each ultrasonic sensor
const int TRIG_PINS[NUM_SENSORS] = {12, 4, 16, 18, 20};
const int ECHO_PINS[NUM_SENSORS] = {13, 15, 17, 2, 21};

// ------------------ RFID Settings ------------------------
// Pin definitions for ESP32-S3 to RFID-RC522
#define RST_PIN     14    // Reset pin (can be any available GPIO)
#define SS_PIN      39    // SPI CS pin (GPIO 39)
#define SCK_PIN     36    // SPI Clock pin (GPIO 36)
#define MOSI_PIN    35    // SPI MOSI pin (GPIO 35)
#define MISO_PIN    37    // SPI MISO pin (GPIO 37)

// ------------------ Servo Motor Settings ------------------
#define SERVO_PIN    5     // GPIO pin 5 for servo motor (as requested)
#define SERVO_OPEN   90    // Servo angle for open gate (90 degrees)
#define SERVO_CLOSED 0     // Servo angle for closed gate (0 degrees)

// ------------------ Variables ----------------------------
WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
MFRC522 rfid(SS_PIN, RST_PIN); // Create MFRC522 instance
Servo gateServo;               // Create servo instance

int parkingSlotStatus[NUM_SENSORS] = {0}; // 0 = empty, 1 = occupied

// ------------------ Function Prototypes --------------------
void setupWiFi();
void reconnectMQTT();
void publishParkingStatus();
float readUltrasonicSensor(int sensorIndex);
void checkRFID();
void openGate();
void closeGate();
String getCardUID();

// ------------------ Setup Function -------------------------
void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("------------------------------");
    Serial.println("  Smart Parking System Start  ");
    Serial.println("------------------------------");
    
    // Initialize ultrasonic sensor pins
    for (int i = 0; i < NUM_SENSORS; i++) {
        pinMode(TRIG_PINS[i], OUTPUT);
        pinMode(ECHO_PINS[i], INPUT);
        digitalWrite(TRIG_PINS[i], LOW);
    }
    Serial.println("Ultrasonic sensors initialized.");

    // Connect to Wi-Fi
    setupWiFi();

    // Setup MQTT
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
    
    // Attempt to connect to MQTT
    reconnectMQTT();
    
    // Initialize SPI with the specific pins for RFID
    SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN, SS_PIN);
    
    // Initialize MFRC522
    rfid.PCD_Init();
    
    // Show details of the MFRC522 reader
    rfid.PCD_DumpVersionToSerial();
    
    Serial.println("RFID Reader initialized. Waiting for cards...");
    
    // Initialize ESP32 Servo
    // Allow allocation of all timers
    ESP32PWM::allocateTimer(0);
    ESP32PWM::allocateTimer(1);
    ESP32PWM::allocateTimer(2);
    ESP32PWM::allocateTimer(3);
    
    // Set servo properties
    gateServo.setPeriodHertz(50);    // Standard 50 Hz servo
    gateServo.attach(SERVO_PIN, 500, 2400); // Attach the servo to pin with min/max pulse width
    
    // Ensure gate is closed at startup
    gateServo.write(SERVO_CLOSED);
    Serial.println("Servo motor initialized. Gate is closed.");
    
    // Important: Detach the servo after setting initial position
    // This prevents continuous operation when idle
    delay(500); // Give time for servo to reach position
    gateServo.detach();
}

// ------------------ Main Loop ------------------------------
void loop() {
    if (!mqttClient.connected()) {
        reconnectMQTT();
    }

    mqttClient.loop();

    // Read all sensors and update parking status
    for (int i = 0; i < NUM_SENSORS; i++) {
        float distance = readUltrasonicSensor(i);
        if (distance > 0 && distance < DISTANCE_THRESHOLD) {
            parkingSlotStatus[i] = 1; // Occupied
        } else {
            parkingSlotStatus[i] = 0; // Empty
        }

        Serial.printf("Sensor %d: %.2f cm - Status: %s\n", i + 1, distance, parkingSlotStatus[i] ? "Occupied" : "Empty");
    }

    // Publish status
    publishParkingStatus();
    
    // Check for RFID cards (only here will the servo move)
    checkRFID();

    delay(5000); // Wait for 5 seconds before next sensor reading
}

// ------------------ Wi-Fi Connection -----------------------
void setupWiFi(){
    Serial.print("Connecting to Wi-Fi SSID: ");
    Serial.println(WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    while (WiFi.status() != WL_CONNECTED){
        delay(500);
        Serial.print(".");
    }

    Serial.println("\nWi-Fi connected.");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
}

// ------------------ MQTT Reconnect -------------------------
void reconnectMQTT(){
    while (!mqttClient.connected()) {
        Serial.print("Attempting MQTT connection...");
        // Attempt to connect
        if (mqttClient.connect(MQTT_CLIENT_ID)) {
            Serial.println("connected.");
            // Subscribe to reservation topic if needed
            // mqttClient.subscribe("parking/reservations");
        } else {
            Serial.print("failed, rc=");
            Serial.print(mqttClient.state());
            Serial.println(" Retrying in 5 seconds.");
            delay(5000);
        }
    }
}

// ------------------ Read Ultrasonic Sensor ------------------
float readUltrasonicSensor(int sensorIndex){
    // Trigger the sensor
    digitalWrite(TRIG_PINS[sensorIndex], LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PINS[sensorIndex], HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PINS[sensorIndex], LOW);

    // Read the echo pin
    long duration = pulseIn(ECHO_PINS[sensorIndex], HIGH, 30000); // Timeout after 30ms
    if(duration == 0){
        // No echo received
        return -1;
    }

    // Calculate distance in cm
    float distance = (duration * 0.034) / 2;

    return distance;
}

// ------------------ Publish Parking Status -------------------
void publishParkingStatus(){
    // Payload format 
    String payload = "{ \"slots\": [";
    for(int i = 0; i < NUM_SENSORS; i++){
        payload += "{ \"id\": " + String(i) + ", \"status\": " + String(parkingSlotStatus[i]) + " }";
        if(i < NUM_SENSORS -1){
            payload += ", ";
        }
    }
    payload += "] }";

    mqttClient.publish(MQTT_PUB_TOPIC, payload.c_str());
    Serial.println("Published parking status to MQTT:");
    Serial.println(payload);
}

// Function removed - No RFID data publishing to MQTT

// ------------------ Open Gate ----------------------------
void openGate() {
    Serial.println("Opening gate...");
    
    // Re-attach servo for movement
    gateServo.attach(SERVO_PIN, 500, 2400);
    delay(100); // Brief delay for stability
    
    // Move to CLOSED position first to ensure proper starting point
    gateServo.write(SERVO_CLOSED);
    delay(100);
    
    // Move forward from closed (0°) to open (90°) position
    Serial.println("Moving gate forward to open position...");
    for (int pos = SERVO_CLOSED; pos <= SERVO_OPEN; pos += 5) {
        gateServo.write(pos);
        delay(15); // Small delay for smooth movement
    }
    
    // Make sure we reach exactly 90 degrees
    gateServo.write(SERVO_OPEN);
    Serial.println("Gate opened successfully at 90 degrees.");
}

// ------------------ Close Gate ----------------------------
void closeGate() {
    Serial.println("Closing gate...");
    
    // Move backward from open (90°) to closed (0°) position
    Serial.println("Moving gate backward to closed position...");
    for (int pos = SERVO_OPEN; pos >= SERVO_CLOSED; pos -= 5) {
        gateServo.write(pos);
        delay(15); // Small delay for smooth movement
    }
    
    // Make sure we reach exactly 0 degrees
    gateServo.write(SERVO_CLOSED);
    delay(500); // Give time to reach position
    Serial.println("Gate closed successfully at 0 degrees.");
    
    // Important: Detach the servo when not in use to prevent continuous operation
    gateServo.detach();
}

// ------------------ Get Card UID as String -------------------
String getCardUID() {
    String cardID = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
        if (rfid.uid.uidByte[i] < 0x10) {
            cardID += "0";
        }
        cardID += String(rfid.uid.uidByte[i], HEX);
    }
    cardID.toUpperCase();
    return cardID;
}

// ------------------ Check RFID ----------------------------
void checkRFID() {
    // Check if a new card is present
    if (!rfid.PICC_IsNewCardPresent())
        return;
        
    // Read the card
    if (!rfid.PICC_ReadCardSerial())
        return;
    
    // Get card UID as string
    String cardID = getCardUID();
    
    // Display user access message
    Serial.println();
    Serial.print("User ID: ");
    Serial.print(cardID);
    Serial.println(" has used the Smart Car Parking.");
    
    // Open the gate
    openGate();
    
    // Wait for 3 seconds with the gate open (changed from 5 seconds)
    delay(3000);
    
    // Close the gate
    closeGate();
    
    // Print card type to Serial
    Serial.print("PICC type: ");
    MFRC522::PICC_Type piccType = rfid.PICC_GetType(rfid.uid.sak);
    Serial.println(rfid.PICC_GetTypeName(piccType));
    
    // Read data from the card (if available)
    byte readBuffer[18];
    byte size = sizeof(readBuffer);
    
    // Try to read the first data block (block 4, which is the first block of sector 1)
    byte status = rfid.MIFARE_Read(4, readBuffer, &size);
    if (status == MFRC522::STATUS_OK) {
        Serial.println("Data from card:");
        for (uint8_t i = 0; i < 16; i++) {
            Serial.print(readBuffer[i] < 0x10 ? " 0" : " ");
            Serial.print(readBuffer[i], HEX);
        }
        Serial.println();
        
        // Convert to ASCII if it's text data
        Serial.println("Data as text:");
        for (uint8_t i = 0; i < 16; i++) {
            if (readBuffer[i] >= 32 && readBuffer[i] <= 126) { // Printable ASCII
                Serial.write(readBuffer[i]);
            } else {
                Serial.print('.');
            }
        }
        Serial.println();
    }
    
    // Halt PICC and get ready for next card
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    
    Serial.println("Card reading complete. Gate operation finished. Ready for next card.");
}