#define password "1337"

/* simple password checker
This is not secure, this is just for demonstrating uart implant attacks
Listen for strings on uart
When the password is entered, respond  "authorized"
When anything else is entered, respond "denied"
*/

void setup() {
  Serial.begin(9600);
}

void loop() {
  if (Serial.available()){
    String input = Serial.readStringUntil('\n');
    input.trim();
    if (input==password){
      Serial.println("AUTHORIZED");
    } else {
      Serial.println("DENIED");
    }
    while (Serial.available()) {
      Serial.read(); 
    }
  }
}