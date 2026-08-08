/*
||  Simple Password Entry Using Matrix Keypad
||  4/5/2012 Updates Nathan Sobieck: Nathan@Sobisource.com
||
||  7/2013 updated by joefitz@securinghardware.com
||  fixed password not reset after check
||  added support for LED strip output
||  pulled colorWipe from adafruit neopixel library and reversed direction of wipe.
||  all so it looks pretty to demonstrate a timing side channel attack against password.checkPassword()
||
||  6/2026 updated by joefitz@securinghardware.com
||  removed password, use uart to validate entry to demonstrate UART implant attacks
*/


//* is to validate password   
//# is to reset password attempt

/////////////////////////////////////////////////////////////////

//#include <Password.h> //http://www.arduino.cc/playground/uploads/Code/Password.zip
#include <Keypad.h> //http://www.arduino.cc/playground/uploads/Code/Keypad.zip
#include <Adafruit_NeoPixel.h> //https://github.com/adafruit/Adafruit_NeoPixel/archive/master.zip

#define LEDPIN 15
#define brightness 16
#define red strip.Color( brightness , 0 ,0)
#define green strip.Color(0, brightness , 0)
#define blue strip.Color(0, 0, brightness )
#define black strip.Color(0, 0, 0)
String password = "";
Adafruit_NeoPixel strip = Adafruit_NeoPixel(7, LEDPIN, NEO_GRB + NEO_KHZ800);

int keycount=0;

const byte ROWS = 4; // Four rows
const byte COLS = 3; //  columns
// Define the Keymap

char keys[ROWS][COLS] = {
  {'1','2','3'},
  {'4','5','6'},
  {'7','8','9'},
  {'*','0','#'}
};

byte rowPins[ROWS] = {13,12,14,16};//{ 2,3,4,5, };//{ 9,8,7,6 };// Connect keypad ROW0, ROW1, ROW2 and ROW3 to these Arduino pins.
byte colPins[COLS] = {5,4,0};//{ 6,7,8,9, };//{ 5,4,3,2, };// Connect keypad COL0, COL1 and COL2 to these Arduino pins.

// Create the Keypad
Keypad keypad = Keypad( makeKeymap(keys), rowPins, colPins, ROWS, COLS );

void setup(){
  Serial.begin(9600);
  strip.begin();
  strip.show();
  colorWipe(red, 50);
  keypad.addEventListener(keypadEvent); //add an event listener for this keypad
  colorWipe(blue, 50);
  colorWipe(black, 50);
}

void loop(){
  keypad.getKey();
  checkPassword();
}

// Fill the dots one after the other with a color
void colorWipe(uint32_t c, uint8_t wait) {
  for(uint16_t i=strip.numPixels(); i>0; i--) {
      strip.setPixelColor(i-1, c);
      strip.show();
      delay(wait);
  }
}

//take care of some special events
void keypadEvent(KeypadEvent eKey){
// 	Serial.print("x");
  switch (keypad.getState()){
    case PRESSED:
//    	Serial.print("Pressed: ");
//	    Serial.println(eKey);
	    switch (eKey){
    	  case '*': Serial.println(password); keycount=0;
	      case '#': password=""; keycount=0; colorWipe(strip.Color(0,0,0),0); break;
	      default: password.concat(eKey); strip.setPixelColor(keycount++, strip.Color(0,0,63));
      }
    strip.show();
  }
}

void checkPassword(){
  if (Serial.available()) {
    String input = Serial.readStringUntil('\r');
    input.trim();
    if (input=="AUTHORIZED"){
      colorWipe(green, 50);
    } else {
      colorWipe(red, 50);
    }
    while (Serial.available()) {
      Serial.read();
    } 
  }
}



