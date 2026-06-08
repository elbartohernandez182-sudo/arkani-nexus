import socket
import os

def start_writer_daemon():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 5005))
    server.listen(5)
    print("📡 [ARKANI-DAEMON]: Escritura autónoma ACTIVA en puerto 5005...")

    while True:
        conn, addr = server.accept()
        try:
            data = conn.recv(10240).decode('utf-8')
            if "|" in data:
                filename, content = data.split('|', 1)
                path = os.path.expanduser(f"~/NEXUS/NEXUS-LANG/autogen/{filename}")
                with open(path, "w") as f:
                    f.write(content)
                print(f"✅ [AUTO-GEN]: Nodo '{filename}' inyectado exitosamente.")
        except Exception as e:
            print(f"❌ Error: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    start_writer_daemon()
