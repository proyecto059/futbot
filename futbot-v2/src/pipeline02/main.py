import sys  #Se implementa para comunicarse con el sistema, principalmente para especificar donde python busca archivos
import os   #Permite la interacción con el sistema operativo para entrar en las carpetas necesarias
import logging #Se implementa para mostrar mensajes determinados por consola

# Añadir el directorio 'src' principal al PYTHONPATH para importar correctamente 'vision' y 'motors'
current_dir = os.path.dirname(os.path.abspath(__file__))    #Esta linea obtiene la ruta del archivo actual que es main.py, convierte ruta parcial en absoluta
src_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))    #Esta linea sube dos niveles en el directorio (hasta src) lo cual da la raiz del proyecto y se guarda como src_dir
if src_dir not in sys.path: #Valida que src_dir no esté en sys.path
    sys.path.insert(0, src_dir) #Se implementa "sys" para establecer el PATH en src_dir como por defecto 

logging.basicConfig(    #Se estblece el formato para los mensajes de consola
    level=logging.INFO,     #Se establece el nivel de informacion a mostrar, solo se mostraran mensajes informativos, errores y adevertencias
    format="%(asctime)s [%(levelname)s] %(message)s",   #Se define la forma del mensaje mostrado en consola 
    datefmt="%H:%M:%S", #Se define el formato de la hora
)
log = logging.getLogger("turbopi") #Se define el logger o la consola con el nombre turbopi

def main():
    vision = None   #Se declara la variable vision se le asigna un valor mas adelante
    motors = None   #Se declara la variable motors se le asigna un valor mas adelante
    pipeline = None #Se declara la variable pipeline se le asigna un valor mas adelante

    try:    #Protección contra errores
        from vision import HybridVisionService #Se utiliza libreria vision, librerira propia en el proyecto
        from motors import MotorService #Se utiliza libreria motors, librerira propia en el proyecto    
        
        # Importar el nuevo Pipeline5 refactorizado
        from pipeline5.pipeline_service import Pipeline5Service #Se establece que el archivo main donde viene 

        log.info("event=controller_started mode=pipeline5") #Se muestra un mensaje en consola que se esta usando el pipeline5

        vision = HybridVisionService() #Se instancia el servicio de vision
        motors = MotorService() #Se instancia el servicio de motores

        pipeline = Pipeline5Service(vision, motors) #Se instancia el pipeline5 pasandole los servicios de vision y motores
        pipeline.run() #Se ejecuta el pipeline5

    except KeyboardInterrupt:
        log.info("event=shutdown reason=keyboard_interrupt")
    except Exception as exc:
        log.exception("event=runtime_error error=%s", exc)
    finally:
        if pipeline is not None:
            pipeline.close()    #Se cierra el pipeline
        if motors is not None:
            motors.stop(200)    #Se detienen los motores
            motors.close()      #Se cierran los motores
        if vision is not None:
            vision.close()      #Se cierra la vision

if __name__ == "__main__":
    main()
