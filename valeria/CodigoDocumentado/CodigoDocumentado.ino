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
int ADis [5];
int contador = 0;
int sum=0;
double prom=1000;
// Guarda si alguna vez se detectó persona con ID=1

/*********************** SETUP ******************************/
void setup() {

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

/************************ LOOP ******************************/
void loop() {

    // Medir distancia con ultrasónico
    long distancia = medirDistancia();

    Serial.print("Distancia: ");
    Serial.print(distancia);
    Serial.println(" cm");

    //Promedio de la distancia
    if (contador <= 4){
      ADis[contador] = distancia;
      contador=contador+1;
    }else{
        contador = 0;
        for (int i = 0; i<=4; i++){
            sum = sum + ADis[i];
        }
        prom = sum/5;
        sum=0;
    }
    Serial.print("*********************************************");
    Serial.print("Distancia: ");
    Serial.print(prom);
    Serial.println("*********************************************");
    


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
        HUSKYLENSResult result = huskylens.read();  
        recuperarPersonaInteligente(rc);
        mapeoArea(rc);
        Serial.println("estoy buscando");
    } 

    // Si hay objeto disponible
    else
    {
        Serial.println(F("###########"));

        while (huskylens.available())
        {
            HUSKYLENSResult result = huskylens.read();  
            printResult(result);  // Imprime información del objeto
            rc = result.xCenter;


            // Si detecta ID 1 (persona entrenada)
            if (result.ID == 1){
                avanzar();                      // Avanza hacia la persona
                personaVistaAnteriormente = true; 
                Serial.println("estoy viendo a alguien");
                delay(1400);
                medirDistancia();
                // Medir distancia con ultrasónico
    long distancia = medirDistancia();

    Serial.print("Distancia: ");
    Serial.print(distancia);
    Serial.println(" cm");

    //Promedio de la distancia FO
    if (contador <= 4){
      ADis[contador] = distancia;
      contador=contador+1;
    }else{
        contador = 0;
        for (int i = 0; i<=4; i++){
            sum = sum + ADis[i];
        }
        prom = sum/5;
        sum=0;
    }
    Serial.print("*********************************************");
    Serial.print("Distancia: ");
    Serial.print(prom);
    Serial.println("*********************************************");
            }
            else if (result.ID==2 && prom<=5){
                retroceder();
            }
            else if (result.ID==1 && result.ID==2){
                avanzar();                      // Avanza hacia la persona
                personaVistaAnteriormente = true; 
                Serial.println("estoy viendo a alguien");
                delay(1400);
            }
            else if(result.ID ==2){
                mapeoArea(rc);
                Serial.println("estoy buscando buey tengo ID2");
            }
        }    
    }
}

/*************** FUNCIÓN IMPRIMIR RESULTADO ****************/
void printResult(HUSKYLENSResult result){

    // Si el resultado es un bloque detectado
    if (result.command == COMMAND_RETURN_BLOCK){
        Serial.println(String()+
        F("Block:xCenter=")+result.xCenter+
        F(",yCenter=")+result.yCenter+
        F(",width=")+result.width+
        F(",height=")+result.height+
        F(",ID=")+result.ID);
    }

    // Si es una flecha (modo línea o dirección)
    else if (result.command == COMMAND_RETURN_ARROW){
        Serial.println(String()+
        F("Arrow:xOrigin=")+result.xOrigin+
        F(",yOrigin=")+result.yOrigin+
        F(",xTarget=")+result.xTarget+
        F(",yTarget=")+result.yTarget+
        F(",ID=")+result.ID);
    }
    else{
        Serial.println("Object unknown!");
    }

    // Si es ID 1
    if (result.ID == 1){
        Serial.println("adelante");
    }
}

/******************* SENSOR ULTRASÓNICO ********************/
long medirDistancia() {

    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);

    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);   // Pulso de 10µs
    digitalWrite(TRIG_PIN, LOW);

    // Medir tiempo que tarda el eco en regresar
    long duracion = pulseIn(ECHO_PIN, HIGH, 30000);

    if (duracion == 0) return 0; // Si no recibe eco

    // Fórmula distancia = (tiempo * velocidad sonido) / 2
    long distancia = duracion * 0.034 / 2;

    return distancia;
}

/******************** MOVIMIENTO ROBOT **********************/
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

    delay(1000);  // Pausa de seguridad
}

void giro_atras(){

    digitalWrite(DIR_A, LOW);   // Motor A atrás
    digitalWrite(DIR_B, HIGH);  // Motor B adelante
    analogWrite(PWM_A, SPEED);
    analogWrite(PWM_B, 0);

    delay(1000);
}

/******************** BUSCAR PERSONA ***********************/
void buscarpersona(){

    int velocidadLenta = SPEED;  
    int SPEED = 30;  // Variable local que NO afecta la global

    digitalWrite(DIR_A, HIGH);   // Lado A adelante
    digitalWrite(DIR_B, HIGH);   // Lado B atrás

    analogWrite(PWM_A, velocidadLenta);
    analogWrite(PWM_B, velocidadLenta);

    delay(200);   // Tiempo de giro (ajustable)

    parar();
}

/******************* RECUPERAR PERSONA **********************/
void recuperarPersona() {

    // Si nunca la vio antes, no ejecuta recuperación
    if (!personaVistaAnteriormente) {
        return;
    }

    Serial.println("Perdi a la persona, ejecutando recuperacion...");

    // 1️⃣ Retrocede un poco
    digitalWrite(DIR_A, LOW);
    digitalWrite(DIR_B, HIGH);
    analogWrite(PWM_A, SPEED);
    analogWrite(PWM_B, SPEED);
    delay(600);
    parar();

    delay(1500);

    // 2️⃣ (Giro 360° comentado)

    parar();

    // 3️⃣ Reinicia memoria
    personaVistaAnteriormente = false;
}

 int recuperarPersonaInteligente(int rc) {

    
    if (!personaVistaAnteriormente) {
        return;
    }

    Serial.println("Recuperacion inteligente activada");

    int velocidadLenta = SPEED - 30;

    // =============================
    // ZONA IZQUIERDA
    // =============================
     Serial.println(rc+"xas");
    if (rc < 100) {

        Serial.println("Ultima posicion: IZQUIERDA");

        digitalWrite(DIR_A, LOW);
        digitalWrite(DIR_B, LOW);

        analogWrite(PWM_A, velocidadLenta);
        analogWrite(PWM_B, velocidadLenta);

        delay(1000);
        parar();
    }

    // =============================
    // ZONA CENTRO
    // =============================
    else if (rc >= 100 && rc <= 200) {

        Serial.println("Ultima posicion: CENTRO");

        golpeFrontal(); // Usa el ataque cuando pierde la pelota por el centro

        delay(1000);   // Ataca por 1 segundo
        parar();
    }

    // =============================
    // ZONA DERECHA
    // =============================
    else {

        Serial.println("Ultima posicion: DERECHA");

        digitalWrite(DIR_A, HIGH);
        digitalWrite(DIR_B, HIGH);

        analogWrite(PWM_A, velocidadLenta);
        analogWrite(PWM_B, velocidadLenta);

        delay(1000);
        parar();
    }

    personaVistaAnteriormente = false;
   
}

// Función auxiliar para detectar ID:1 durante pausas simulando un delay
bool pausaDeteccion(int tiempoMs) {
    unsigned long start = millis();
    while (millis() - start < tiempoMs) {
        if (huskylens.request()) {
            while (huskylens.available()) {
                HUSKYLENSResult result = huskylens.read();
                if (result.ID == 1) {
                    avanzar();
                    personaVistaAnteriormente = true;
                    return true;
                }
            }
        }
        delay(10); // Evitar saturar el puerto serial
    }
    return false;
}

bool mapeoArea(int rc){
    int velocidadLenta = SPEED - 30;
    Serial.println("Mapeo de area activado");
    Serial.print("este es el valor por donde se pierde la pelota: ");
    Serial.println(rc);

    Serial.print("vueltas: ");
    Serial.println(numVueltas);


    // ↪ 2️⃣ Giro a la DERECHA
    if (rc < 150){
        Serial.println("giro izquierda");
        digitalWrite(DIR_A, LOW);
        digitalWrite(DIR_B, LOW);
        numVueltas = numVueltas + 1;
    }else{
        Serial.println("giro derecha");
        digitalWrite(DIR_A, HIGH);
        digitalWrite(DIR_B, HIGH);
        numVueltas = numVueltas + 1;
    } 
    
    analogWrite(PWM_A, velocidadLenta);
    analogWrite(PWM_B, velocidadLenta);
    if (pausaDeteccion(800)) return true;
    parar();
    
    if (pausaDeteccion(300)) return true;

    // ↩ 3️⃣ Giro a la IZQUIERDA
    if (rc > 150){
        Serial.println("giro derecha");
        digitalWrite(DIR_A, HIGH);
        digitalWrite(DIR_B, HIGH);
        numVueltas = numVueltas + 1;
    }else{
        Serial.println("giro izquierda");
        digitalWrite(DIR_A, LOW);
        digitalWrite(DIR_B, LOW);
        numVueltas = numVueltas + 1;
    } 
    analogWrite(PWM_A, velocidadLenta);
    analogWrite(PWM_B, velocidadLenta);
    if (pausaDeteccion(800)) return true;
    parar();


    if (numVueltas >= 5){
        retroceder();
        numVueltas = 0;
        return;

    }

    if (rc > 150){
        Serial.println("giro derecha");
        digitalWrite(DIR_A, HIGH);
        digitalWrite(DIR_B, HIGH);
        numVueltas = numVueltas + 1;
    }else{
        Serial.println("giro izquierda");
        digitalWrite(DIR_A, LOW);
        digitalWrite(DIR_B, LOW);
        numVueltas = numVueltas + 1;
    } 
    analogWrite(PWM_A, velocidadLenta);
    analogWrite(PWM_B, velocidadLenta);
    if (pausaDeteccion(800)) return true;
    parar();
    

    Serial.println("Mapeo finalizado");
    return false;

}

void retroceder(){
    // 1️⃣ Retrocede un poco
    digitalWrite(DIR_A, LOW);
    digitalWrite(DIR_B, HIGH);
    analogWrite(PWM_A, SPEED);
    analogWrite(PWM_B, SPEED);
    delay(600);
}