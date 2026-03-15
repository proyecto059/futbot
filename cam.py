import cv2
import numpy as np
import urllib.request
import time
import sys

url = "http://192.168.4.1:81/stream"

print("🔌 Intentando conectar al stream:", url)

try:
    stream = urllib.request.urlopen(url, timeout=10)
    print("✅ Conectado al stream correctamente")
except Exception as e:
    print("❌ Error al conectar:", e)
    sys.exit(1)

bytes_data = b''
last_save = 0
frame_count = 0
last_log = time.time()

print("📡 Esperando frames...")

try:
    while True:

        chunk = stream.read(1024)

        if not chunk:
            print("⚠️ No se recibieron datos del stream")
            time.sleep(1)
            continue

        bytes_data += chunk

        a = bytes_data.find(b'\xff\xd8')
        b = bytes_data.find(b'\xff\xd9')

        if a != -1 and b != -1:

            jpg = bytes_data[a:b+2]
            bytes_data = bytes_data[b+2:]

            frame = cv2.imdecode(
                np.frombuffer(jpg, dtype=np.uint8),
                cv2.IMREAD_COLOR
            )

            if frame is None:
                print("⚠️ Frame inválido recibido")
                continue

            frame_count += 1

            if time.time() - last_log > 5:
                print(f"📷 Frames recibidos: {frame_count}")
                last_log = time.time()

            # reducir ruido
            frame = cv2.GaussianBlur(frame, (11, 11), 0)

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            lower_orange = np.array([5, 120, 120])
            upper_orange = np.array([20, 255, 255])

            mask = cv2.inRange(hsv, lower_orange, upper_orange)

            kernel = np.ones((5, 5), np.uint8)

            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel)

            contours, _ = cv2.findContours(
                mask,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            detected = False

            for c in contours:

                area = cv2.contourArea(c)

                if area > 500:

                    (x, y), radius = cv2.minEnclosingCircle(c)

                    if radius > 10:

                        detected = True

                        center_x = int(x)
                        center_y = int(y)

                        print(
                            "🟠 Pelota detectada |",
                            "x:", center_x,
                            "y:", center_y,
                            "radio:", int(radius)
                        )

                        cv2.circle(
                            frame,
                            (center_x, center_y),
                            int(radius),
                            (0, 255, 0),
                            2
                        )

            if detected and time.time() - last_save > 1:

                filename = f"detected_{int(time.time())}.jpg"
                cv2.imwrite(filename, frame)

                print("📸 Imagen guardada:", filename)

                last_save = time.time()

except KeyboardInterrupt:
    print("\n🛑 Programa detenido por usuario (Ctrl+C)")

except Exception as e:
    print("❌ Error en el stream:", e)import cv2
import numpy as np
import urllib.request
import time
import sys

url = "http://192.168.4.1:81/stream"

print("🔌 Intentando conectar al stream:", url)

try:
    stream = urllib.request.urlopen(url, timeout=10)
    print("✅ Conectado al stream correctamente")
except Exception as e:
    print("❌ Error al conectar:", e)
    sys.exit(1)

bytes_data = b''
last_save = 0
frame_count = 0
last_log = time.time()

print("📡 Esperando frames...")

try:
    while True:

        chunk = stream.read(1024)

        if not chunk:
            print("⚠️ No se recibieron datos del stream")
            time.sleep(1)
            continue

        bytes_data += chunk

        a = bytes_data.find(b'\xff\xd8')
        b = bytes_data.find(b'\xff\xd9')

        if a != -1 and b != -1:

            jpg = bytes_data[a:b+2]
            bytes_data = bytes_data[b+2:]

            frame = cv2.imdecode(
                np.frombuffer(jpg, dtype=np.uint8),
                cv2.IMREAD_COLOR
            )

            if frame is None:
                print("⚠️ Frame inválido recibido")
                continue

            frame_count += 1

            if time.time() - last_log > 5:
                print(f"📷 Frames recibidos: {frame_count}")
                last_log = time.time()

            # reducir ruido
            frame = cv2.GaussianBlur(frame, (11, 11), 0)

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            lower_orange = np.array([5, 120, 120])
            upper_orange = np.array([20, 255, 255])

            mask = cv2.inRange(hsv, lower_orange, upper_orange)

            kernel = np.ones((5, 5), np.uint8)

            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel)

            contours, _ = cv2.findContours(
                mask,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            detected = False

            for c in contours:

                area = cv2.contourArea(c)

                if area > 500:

                    (x, y), radius = cv2.minEnclosingCircle(c)

                    if radius > 10:

                        detected = True

                        center_x = int(x)
                        center_y = int(y)

                        print(
                            "🟠 Pelota detectada |",
                            "x:", center_x,
                            "y:", center_y,
                            "radio:", int(radius)
                        )

                        cv2.circle(
                            frame,
                            (center_x, center_y),
                            int(radius),
                            (0, 255, 0),
                            2
                        )

            if detected and time.time() - last_save > 1:

                filename = f"detected_{int(time.time())}.jpg"
                cv2.imwrite(filename, frame)

                print("📸 Imagen guardada:", filename)

                last_save = time.time()

except KeyboardInterrupt:
    print("\n🛑 Programa detenido por usuario (Ctrl+C)")

except Exception as e:
    print("❌ Error en el stream:", e)