#include <Arduino_BuiltIn.h>

/***************************************************
 HUSKYLENS + Sensores IR de línea blanca
 ***************************************************/

#include "HUSKYLENS.h"
#include "SoftwareSerial.h"

/*********** Objetos principales ***************/
HUSKYLENS huskylens;
SoftwareSerial mySerial(10, 11); // RX=10, TX=11

void printResult(HUSKYLENSResult result);

/*********** Pines de motores ***************/
const byte DIR_A = 2;
const byte PWM_A = 5;
const byte DIR_B = 4;
const byte PWM_B = 6;

/*********** Pines sensor ultrasónico ***************/
const byte TRIG_PIN = 12;
const byte ECHO_PIN = 13;

/*********** Pines sensores IR (línea blanca) ***************/
const byte IR_IZQ   = 7;
const byte IR_CENT  = 8;
const byte IR_DER   = 9;

/*********** Constantes del sistema ***************/
const int SPEED    = 80;
const int DIST_MIN = 20;

/*********** Variables de estado ***************/
bool personaVistaAnteriormente = false;
int  x          = 0;
int  rc         = 0;
int  numVueltas = 0;
int  ADis[3];
int  contador   = 0;
int  sum        = 0;
double prom     = 1000;

// -------- SENSOR DE SONIDO --------
const int SOUND_PIN = A3;
int umbralSonido = 20;
int contadorSonido = 0;
bool sistemaActivo = false;
unsigned long tiempoVentana = 0;  // ← Nueva variable

/*********************** SETUP ******************************/
void setup() {

    Serial.begin(9600);
    mySerial.begin(9600);

    pinMode(SOUND_PIN, INPUT);

    while (!huskylens.begin(mySerial)) {
        Serial.println(F("Begin failed!"));
        Serial.println(F("1.Check Protocol Type: Serial 9600"));
        Serial.println(F("2.Check connection."));
        delay(100);
    }

    // Motores
    pinMode(DIR_A, OUTPUT);
    pinMode(PWM_A, OUTPUT);
    pinMode(DIR_B, OUTPUT);
    pinMode(PWM_B, OUTPUT);

    // Ultrasónico
    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);

    // Sensores IR
    pinMode(IR_IZQ,  INPUT);
    pinMode(IR_CENT, INPUT);
    pinMode(IR_DER,  INPUT);
}

/************************ LOOP ******************************/
void loop() {

    // ───────── ACTIVACIÓN POR SILBIDO ─────────
    if (!sistemaActivo) {

        int valor = analogRead(SOUND_PIN);
        Serial.print("Sonido: ");
        Serial.println(valor);

        if (valor > umbralSonido) {
            contadorSonido++;
            Serial.print("Picos detectados: ");
            Serial.println(contadorSonido);
        }

        // Ventana de 1 segundo: si no llega a 3 picos, reinicia
        if (millis() - tiempoVentana > 500) {
            contadorSonido = 0;
            tiempoVentana = millis();
        }

        if (contadorSonido >= 1) {
            sistemaActivo = true;
            contadorSonido = 0;
            Serial.println(">>> SISTEMA ACTIVADO <<<");
            delay(800);
        }

        return;
    }

    // ── 1. Verificar línea blanca ANTES de cualquier movimiento ──
    if (lineaBlancaDetectada()) {
        manejarLineaBlanca();
        return;
    }

    // ── 2. Medir distancia ──
    long distancia = medirDistancia();
    Serial.print("Distancia: ");
    Serial.print(distancia);
    Serial.println(" cm");

    // Promedio de distancia (ventana de 3 muestras)
    if (contador <= 2) {
        ADis[contador] = distancia;
        contador++;
    } else {
        contador = 0;
        for (int i = 0; i <= 2; i++) sum += ADis[i];
        prom = sum / 3.0;
        sum  = 0;
    }
    Serial.print("*** Promedio distancia: ");
    Serial.print(prom);
    Serial.println(" cm ***");

    // ── 3. Solicitar datos al HUSKYLENS ──
    if (!huskylens.request()) {
        Serial.println(F("Fail to request data from HUSKYLENS"));
    }
    else if (!huskylens.isLearned()) {
        Serial.println(F("Nothing learned, press learn button"));
    }
    else if (!huskylens.available()) {
        Serial.println(F("No block or arrow appears"));
        huskylens.read();
        recuperarPersonaInteligente(rc);
        mapeoArea(rc);
        Serial.println("Buscando persona...");
    }
    else {
        Serial.println(F("###########"));

        bool hasID1 = false;
        bool hasID2 = false;

        while (huskylens.available()) {
            HUSKYLENSResult result = huskylens.read();
            printResult(result);
            rc = result.xCenter;
            if (result.ID == 1) hasID1 = true;
            if (result.ID == 2) hasID2 = true;
        }

        if (hasID1 && hasID2 && prom <= 15) {
            Serial.println("ID1 + ID2 con dist <= 15. Retrocediendo...");
            retroceder();
            mapeoArea(rc);
        }
        else if (hasID1) {
            avanzar();
            personaVistaAnteriormente = true;
            Serial.println("Viendo persona (ID 1)");
            delay(1400);
            Serial.print("*** Distancia: ");
            Serial.print(prom);
            Serial.println(" cm ***");
        }
        else if (hasID2) {
            if (prom <= 15) {
                Serial.println("ID2 y dist <= 15. Retrocediendo...");
                retroceder();
                mapeoArea(rc);
            } else {
                Serial.println("Buscando... tengo ID2");
                mapeoArea(rc);
            }
        }
    }
}

/*************** DETECCIÓN LÍNEA BLANCA ********************/
bool lineaBlancaDetectada() {
    const int CONFIRMACIONES_REQUERIDAS = 5;
    const int INTERVALO_MS = 10;

    int contIzq  = 0;
    int contCent = 0;
    int contDer  = 0;

    for (int i = 0; i < CONFIRMACIONES_REQUERIDAS; i++) {
        if (digitalRead(IR_IZQ)  == LOW) contIzq++;
        if (digitalRead(IR_CENT) == LOW) contCent++;
        if (digitalRead(IR_DER)  == LOW) contDer++;
        delay(INTERVALO_MS);
    }

    bool izq  = (contIzq  >= CONFIRMACIONES_REQUERIDAS);
    bool cent = (contCent >= CONFIRMACIONES_REQUERIDAS);
    bool der  = (contDer  >= CONFIRMACIONES_REQUERIDAS);

    if (izq || cent || der) {
        Serial.print("Linea CONFIRMADA -> IZQ:");
        Serial.print(izq); Serial.print(" CENT:");
        Serial.print(cent); Serial.print(" DER:");
        Serial.println(der);
        return true;
    }
    return false;
}

void manejarLineaBlanca() {
    Serial.println("=== LINEA BLANCA: parando y girando 180 grados ===");

    parar();
    delay(500);

    digitalWrite(DIR_A, HIGH);
    digitalWrite(DIR_B, HIGH);
    analogWrite(PWM_A, SPEED);
    analogWrite(PWM_B, SPEED);
    delay(1100);

    parar();
    delay(300);

    Serial.println("=== Giro 180 completado. Reanudando rutinas... ===");

    personaVistaAnteriormente = false;
    numVueltas = 0;
}

/*************** FUNCIÓN IMPRIMIR RESULTADO ****************/
void printResult(HUSKYLENSResult result) {
    if (result.command == COMMAND_RETURN_BLOCK) {
        Serial.println(String() +
            F("Block:xCenter=") + result.xCenter +
            F(",yCenter=")      + result.yCenter +
            F(",width=")        + result.width   +
            F(",height=")       + result.height  +
            F(",ID=")           + result.ID);
    }
    else if (result.command == COMMAND_RETURN_ARROW) {
        Serial.println(String() +
            F("Arrow:xOrigin=") + result.xOrigin +
            F(",yOrigin=")      + result.yOrigin +
            F(",xTarget=")      + result.xTarget +
            F(",yTarget=")      + result.yTarget +
            F(",ID=")           + result.ID);
    }
    else {
        Serial.println("Object unknown!");
    }

    if (result.ID == 1) Serial.println("adelante");
}

/******************* SENSOR ULTRASÓNICO ********************/
long medirDistancia() {
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);

    long duracion = pulseIn(ECHO_PIN, HIGH, 30000);
    if (duracion == 0) return 0;
    return duracion * 0.034 / 2;
}

/******************** MOVIMIENTO ROBOT **********************/
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

void giro_atras() {
    digitalWrite(DIR_A, LOW);
    digitalWrite(DIR_B, HIGH);
    analogWrite(PWM_A, SPEED);
    analogWrite(PWM_B, 0);
    delay(1000);
}

void retroceder() {
    digitalWrite(DIR_A, LOW);
    digitalWrite(DIR_B, HIGH);
    analogWrite(PWM_A, SPEED);
    analogWrite(PWM_B, SPEED);
    delay(600);
}

/******************** BUSCAR PERSONA ***********************/
void buscarpersona() {
    int velocidadLenta = SPEED;
    digitalWrite(DIR_A, HIGH);
    digitalWrite(DIR_B, HIGH);
    analogWrite(PWM_A, velocidadLenta);
    analogWrite(PWM_B, velocidadLenta);
    delay(200);
    parar();
}

/******************* RECUPERAR PERSONA **********************/
void recuperarPersona() {
    if (!personaVistaAnteriormente) return;

    Serial.println("Perdi a la persona, ejecutando recuperacion...");

    digitalWrite(DIR_A, LOW);
    digitalWrite(DIR_B, HIGH);
    analogWrite(PWM_A, SPEED);
    analogWrite(PWM_B, SPEED);
    delay(600);
    parar();
    delay(1500);
    parar();

    personaVistaAnteriormente = false;
}

int recuperarPersonaInteligente(int rc) {
    if (!personaVistaAnteriormente) return 0;

    Serial.println("Recuperacion inteligente activada");

    int velocidadLenta = SPEED - 30;

    if (rc < 100) {
        Serial.println("Ultima posicion: IZQUIERDA");
        digitalWrite(DIR_A, LOW);
        digitalWrite(DIR_B, LOW);
        analogWrite(PWM_A, velocidadLenta);
        analogWrite(PWM_B, velocidadLenta);
        delay(1000);
        parar();
    }
    else if (rc >= 100 && rc <= 200) {
        Serial.println("Ultima posicion: CENTRO");
        avanzar();
        delay(1000);
        parar();
    }
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
    return 0;
}

/******** PAUSA CON DETECCIÓN (no bloquea con delay) *******/
bool pausaDeteccion(int tiempoMs) {
    unsigned long start = millis();
    while (millis() - start < tiempoMs) {

        if (lineaBlancaDetectada()) {
            parar();
            manejarLineaBlanca();
            return false;
        }

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
        delay(10);
    }
    return false;
}

/********************* MAPEO DE ÁREA ***********************/
bool mapeoArea(int rc) {
    int velocidadLenta = SPEED - 30;
    Serial.println("Mapeo de area activado");
    Serial.print("Posicion perdida X: ");
    Serial.println(rc);
    Serial.print("Vueltas: ");
    Serial.println(numVueltas);

    if (rc < 150) {
        Serial.println("Giro izquierda");
        digitalWrite(DIR_A, LOW);
        digitalWrite(DIR_B, LOW);
    } else {
        Serial.println("Giro derecha");
        digitalWrite(DIR_A, HIGH);
        digitalWrite(DIR_B, HIGH);
    }
    numVueltas++;
    analogWrite(PWM_A, velocidadLenta);
    analogWrite(PWM_B, velocidadLenta);
    if (pausaDeteccion(800)) return true;
    parar();
    if (pausaDeteccion(300)) return true;

    if (rc > 150) {
        Serial.println("Giro derecha");
        digitalWrite(DIR_A, HIGH);
        digitalWrite(DIR_B, HIGH);
    } else {
        Serial.println("Giro izquierda");
        digitalWrite(DIR_A, LOW);
        digitalWrite(DIR_B, LOW);
    }
    numVueltas++;
    analogWrite(PWM_A, velocidadLenta);
    analogWrite(PWM_B, velocidadLenta);
    if (pausaDeteccion(800)) return true;
    parar();

    if (numVueltas >= 5) {
        retroceder();
        numVueltas = 0;
        return false;
    }

    if (rc > 150) {
        Serial.println("Giro derecha");
        digitalWrite(DIR_A, HIGH);
        digitalWrite(DIR_B, HIGH);
    } else {
        Serial.println("Giro izquierda");
        digitalWrite(DIR_A, LOW);
        digitalWrite(DIR_B, LOW);
    }
    numVueltas++;
    analogWrite(PWM_A, velocidadLenta);
    analogWrite(PWM_B, velocidadLenta);
    if (pausaDeteccion(800)) return true;
    parar();

    Serial.println("Mapeo finalizado");
    return false;
}