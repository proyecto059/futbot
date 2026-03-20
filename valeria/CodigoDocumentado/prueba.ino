#include <Arduino_BuiltIn.h>  // Librería base de Arduino

/***************************************************
 HUSKYLENS An Easy-to-use AI Machine Vision Sensor
 Sensor de visión artificial con IA integrada
 ***************************************************/

/*********** Librerías necesarias ***************/
#include "HUSKYLENS.h"        // Librería oficial del sensor HUSKYLENS
#include "SoftwareSerial.h"   // Permite crear puerto serial por software

/*********** Objetos principales ***************/
HUSKYLENS huskylens;          
SoftwareSerial mySerial(10, 11); // RX=10, TX=11 (comunicación con HUSKYLENS)
// Cable verde -> Pin 10
// Cable azul  -> Pin 11

void printResult(HUSKYLENSResult result); // Prototipo de función
//int ultimaPosicionX = 160;   // centro por defecto

/*********** Pines de motores ***************/
const byte DIR_A = 2;   // Dirección motor A
const byte PWM_A = 5;   // Velocidad motor A (PWM)
const byte DIR_B = 4;   // Dirección motor B
const byte PWM_B = 6;   // Velocidad motor B (PWM)

/*********** Pines sensor ultrasónico ***************/
const byte TRIG_PIN = 12;  // Disparo del pulso
const byte ECHO_PIN = 13;  // Recepción del eco

/*********** Constantes del sistema ***************/
const int SPEED = 80;     // Velocidad base de motores (0-255)
const int DIST_MIN = 20;  // Distancia mínima de seguridad en cm

/*********** Variable de estado ***************/
bool personaVistaAnteriormente = false; 
int x = 0 ;
int rc = 0;
int numVueltas= 0;
int ADis [3];
int contador = 0;
int sum=0;
double prom=1000;
// Guarda si alguna vez se detectó persona con ID=1

/*********************** SETUP ******************************/

void setup() {
  // put your setup code here, to run once:

    Serial.begin(9600);       // Monitor serial
    mySerial.begin(9600);     // Comunicación con HUSKYLENS

    // Intentar iniciar comunicación con HUSKYLENS
    while (!huskylens.begin(mySerial))
    {
        Serial.println(F("Begin failed!"));
        Serial.println(F("1.Check Protocol Type: Serial 9600"));
        Serial.println(F("2.Check connection."));
        delay(100);
    }

    // Configuración pines motores
    pinMode(DIR_A, OUTPUT);
    pinMode(PWM_A, OUTPUT);
    pinMode(DIR_B, OUTPUT);
    pinMode(PWM_B, OUTPUT);

    // Configuración pines ultrasónico
    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);
  }

void loop() {

    // Solicitar datos al HUSKYLENS
    if (!huskylens.request()){ 
        Serial.println(F("Fail to request data from HUSKYLENS"));
    }

    // Si no hay objeto aprendido
    else if(!huskylens.isLearned()){
        Serial.println(F("Nothing learned, press learn button"));
    }

    // Si no detecta ningún objeto en pantalla
    else if(!huskylens.available()){
        Serial.println(F("No block or arrow appears"));
        
        // Si acabamos de perder de vista la pelota/obetivo
        if (personaVistaAnteriormente) {
            Serial.println("Objetivo perdido. Avanzando un poco y parando...");
            avanzar();       // Avanza hacia adelante por inercia/búsqueda
            delay(600);      // Tiempo que avanza (puedes ajustar los 600ms)
            parar();         // Se detiene completamente
            personaVistaAnteriormente = false; // Reiniciamos el estado
        } else {
            parar();         // Si no veíamos nada antes, se mantiene detenido
        }
    } 

    // Si hay objeto disponible
    else
    {
        Serial.println(F("###########"));

        bool hasID1 = false;
        bool hasID2 = false;

        while (huskylens.available())
        {
            HUSKYLENSResult result = huskylens.read();  
            printResult(result);  // Imprime información del objeto
            rc = result.xCenter;

            if (result.ID == 1) hasID1 = true;
            if (result.ID == 2) hasID2 = true;
        }

        // Si detecta ID 1 y ID 2 juntos con distancia <= 15
            if (hasID1) {
            golpeFrontal();                     // Avanza a máxima velocidad
            personaVistaAnteriormente = true;   // Registramos que vimos la pelota/objetivo
            Serial.println("estoy viendo a alguien (ID 1)");
            delay(500);
            
            // Promedio de la distancia FO
            Serial.print("*********************************************");
            Serial.print("Distancia: ");
            Serial.println("*********************************************");
        }
    }
}

void avanzar() {

    digitalWrite(DIR_A, HIGH);  // Motor A adelante
    digitalWrite(DIR_B, LOW);   // Motor B adelante
    analogWrite(PWM_A, SPEED);
    analogWrite(PWM_B, SPEED);
}

void golpeFrontal(){

    int velAlta = 255;  // Velocidad máxima permitida por PWM (0-255)
    
    digitalWrite(DIR_A, HIGH);  // Motor A adelante
    digitalWrite(DIR_B, LOW);   // Motor B adelante
    analogWrite(PWM_A, velAlta);
    analogWrite(PWM_B, velAlta);
}

void parar() {
    analogWrite(PWM_A, 0);
    analogWrite(PWM_B, 0);
}