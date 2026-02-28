#include <Arduino_BuiltIn.h>

/***************************************************
 HUSKYLENS An Easy-to-use AI Machine Vision Sensor
 <https://www.dfrobot.com/product-1922.html>
 
 ***************************************************
 This example shows the basic function of library for HUSKYLENS via Serial.
 
 Created 2020-03-13
 By [Angelo qiao](Angelo.qiao@dfrobot.com)
 
 GNU Lesser General Public License.
 See <http://www.gnu.org/licenses/> for details.
 All above must be included in any redistribution
 ****************************************************/

/***********Notice and Trouble shooting***************
 1.Connection and Diagram can be found here
 <https://wiki.dfrobot.com/HUSKYLENS_V1.0_SKU_SEN0305_SEN0336#target_23>
 2.This code is tested on Arduino Uno, Leonardo, Mega boards.
 ****************************************************/

#include "HUSKYLENS.h"
#include "SoftwareSerial.h"

HUSKYLENS huskylens;
SoftwareSerial mySerial(10, 11); // RX, TX
//HUSKYLENS green line >> Pin 10; blue line >> Pin 11
void printResult(HUSKYLENSResult result);

// Pines de motores (YA CONFIRMADOS)
// ===================
const byte DIR_A = 2;
const byte PWM_A = 5;
const byte DIR_B = 4;
const byte PWM_B = 6;

// ===================
// Pines ultrasónico
// ===================
const byte TRIG_PIN = 12;
const byte ECHO_PIN = 13;

// ===================
const int SPEED = 80;
const int DIST_MIN = 20; // cm (distancia de frenado)

bool personaVistaAnteriormente = false;


void setup() {
    //Serial.begin(115200);
    Serial.begin(9600);
    mySerial.begin(9600);
    while (!huskylens.begin(mySerial))
    {
        Serial.println(F("Begin failed!"));
        Serial.println(F("1.Please recheck the \"Protocol Type\" in HUSKYLENS (General Settings>>Protocol Type>>Serial 9600)"));
        Serial.println(F("2.Please recheck the connection."));
        delay(100);
    }

  // Motores
  pinMode(DIR_A, OUTPUT);
  pinMode(PWM_A, OUTPUT);
  pinMode(DIR_B, OUTPUT);
  pinMode(PWM_B, OUTPUT);

  // Ultrasonico
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
}

void loop() {
 long distancia = medirDistancia();

  Serial.print("Distancia: ");
  Serial.print(distancia);
  Serial.println(" cm");

    if (!huskylens.request()){
        Serial.println(F("Fail to request data from HUSKYLENS, recheck the connection!"));
    }
    else if(!huskylens.isLearned()){
        Serial.println(F("Nothing learned, press learn button on HUSKYLENS to learn one!"));
    }
    else if(!huskylens.available()){
        Serial.println(F("No block or arrow appears on the screen!"));
        parar();
        
        recuperarPersona();
        buscarpersona();
        Serial.println("estoy buscando");
        
    } 
    else
    {
        Serial.println(F("###########"));
        while (huskylens.available())
        {
            HUSKYLENSResult result = huskylens.read();  //no sabemos
            printResult(result);

            if (result.ID == 1){
                avanzar();
                personaVistaAnteriormente = true; 
                Serial.println("estoy viendo a alguien");
                delay(500);
            }else{
                buscarpersona();
                Serial.println("ya te dije q estoy buscando");
                delay(3000);
                parar();
                delay(3000);
            }
        }    
    }
}

void printResult(HUSKYLENSResult result){
    if (result.command == COMMAND_RETURN_BLOCK){
        Serial.println(String()+F("Block:xCenter=")+result.xCenter+F(",yCenter=")+result.yCenter+F(",width=")+result.width+F(",height=")+result.height+F(",ID=")+result.ID);
    }
    else if (result.command == COMMAND_RETURN_ARROW){
        Serial.println(String()+F("Arrow:xOrigin=")+result.xOrigin+F(",yOrigin=")+result.yOrigin+F(",xTarget=")+result.xTarget+F(",yTarget=")+result.yTarget+F(",ID=")+result.ID);
    }
    else{
        Serial.println("Object unknown!");
    }

    if (result.ID == 1){
        Serial.println("adelante");
    }
}


long medirDistancia() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);

  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duracion = pulseIn(ECHO_PIN, HIGH, 30000); // 30 ms timeout

  if (duracion == 0) return 0; // fuera de rango

  long distancia = duracion * 0.034 / 2;
  return distancia;
}

void avanzar() {
  digitalWrite(DIR_A, HIGH);
  digitalWrite(DIR_B, LOW);
  analogWrite(PWM_A, SPEED);
  analogWrite(PWM_B, SPEED);
}

void parar() {
  analogWrite(PWM_A, 0);
  analogWrite(PWM_B, 0);
  
  delay(1000);
}

void giro_atras(){
  digitalWrite(DIR_A, LOW);
  digitalWrite(DIR_B, HIGH);
  analogWrite(PWM_A, SPEED);
  analogWrite(PWM_B, 0);

  delay(1000);
}

void buscarpersona(){
   
   /* //giro adelante derecha
    digitalWrite(DIR_A, HIGH);
    digitalWrite(DIR_B, HIGH);
    analogWrite(PWM_A, SPEED);
    analogWrite(PWM_B, SPEED);
    delay(2000);
    parar();
    delay(2000);

    //Giro atras izquierda

    digitalWrite(DIR_A, HIGH);
    digitalWrite(DIR_B, HIGH);
    analogWrite(PWM_A, SPEED);
    analogWrite(PWM_B, SPEED);
    delay(2000);
    parar();
    delay(2000);

    //giro adelante iaquierda
    digitalWrite(DIR_A, HIGH);
    digitalWrite(DIR_B, HIGH);
    analogWrite(PWM_A, SPEED);
    analogWrite(PWM_B, SPEED);
    delay(2000);
    parar();
    delay(2000);

    //Giro atras derecha
    digitalWrite(DIR_A, HIGH);
    digitalWrite(DIR_B, HIGH);
    analogWrite(PWM_A, SPEED);
    analogWrite(PWM_B, SPEED);
    delay(2000);
    parar();
    delay(2000);
    */
     int velocidadLenta = SPEED;   // 🔧 Ajusta si quieres más lento
  int SPEED = 30;
  // Lado A adelante
  digitalWrite(DIR_A, HIGH);

  // Lado B atrás
  digitalWrite(DIR_B, HIGH);

  analogWrite(PWM_A, velocidadLenta);
  analogWrite(PWM_B, velocidadLenta);

  delay(200);   // 🔧 CALIBRAR hasta que sea exactamente 180°

  parar();

}
void recuperarPersona() {

    if (!personaVistaAnteriormente) {
        return;   // Si nunca la vio, no hace nada
    }

    Serial.println("Perdi a la persona, ejecutando recuperacion...");

    // 🔙 1. Retroceder un poco
    digitalWrite(DIR_A, LOW);
    digitalWrite(DIR_B, HIGH);
    analogWrite(PWM_A, SPEED);
    analogWrite(PWM_B, SPEED);
    delay(600);   // 🔧 Ajustar distancia de retroceso
    parar();

    delay(1500);

    // 🔄 2. Giro completo 360° lento
    //int velocidadLenta = SPEED - 50;

    /*digitalWrite(DIR_A, HIGH);
    digitalWrite(DIR_B, HIGH);
    analogWrite(PWM_A, velocidadLenta);
    analogWrite(PWM_B, velocidadLenta);

    delay(2000);   // 🔧 Ajustar hasta que sea 360° real*/
    parar();

    // 🧠 3. Reiniciar memoria
    personaVistaAnteriormente = false;
}