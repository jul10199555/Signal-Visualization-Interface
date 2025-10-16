import serial
import serial.tools.list_ports
import time

def find_ports():
    print("🔍 Buscando puertos disponibles...")
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("⚠️  No se encontraron puertos COM disponibles.")
    for p in ports:
        print(f"➡️  {p.device} — {p.description}")
    return ports


def test_connection(port_name, baudrate=115200, timeout=1):
    try:
        print(f"🔌 Intentando conectar a {port_name} @ {baudrate}...")
        ser = serial.Serial(port_name, baudrate, timeout=timeout)
        time.sleep(0.3)  # espera a que el micro reinicie (algunas placas lo hacen)
        
        # Limpia buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # Enviamos un simple comando de prueba
        ser.write(b"0\n")
        ser.flush()

        # Esperamos una posible respuesta
        start = time.time()
        while time.time() - start < 2:
            if ser.in_waiting:
                line = ser.readline().decode(errors="ignore").strip()
                print(f"✅ Respuesta recibida: '{line}'")
                ser.close()
                return True

        print("⚠️  No se recibió respuesta (posible desconexión o firmware no responde).")
        ser.close()
        return False

    except serial.SerialException as e:
        print(f"❌ Error al abrir el puerto: {e}")
        return False
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return False


if __name__ == "__main__":
    ports = find_ports()
    if not ports:
        exit(0)

    # Pide al usuario elegir un puerto
    port_name = input("\nEscribe el nombre del puerto a probar (ejemplo COM5 o /dev/ttyUSB0): ").strip()
    ok = test_connection(port_name)
    if ok:
        print("✅ Conexión exitosa con la tarjeta.")
    else:
        print("❌ No se logró establecer comunicación con la tarjeta.")
