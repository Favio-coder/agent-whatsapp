# run_servers.py
import subprocess
import sys
import time
import threading

def run_main_api():
    """Ejecuta tu API principal en el puerto 8000"""
    subprocess.run([
        sys.executable, "-m", "uvicorn", "main:app", 
        "--host", "0.0.0.0", "--port", "8000", "--reload"
    ])

def run_whatsapp_webhook():
    """Ejecuta el webhook de WhatsApp en el puerto 8001"""
    subprocess.run([
        sys.executable, "-m", "uvicorn", "whatsapp_webhook:app", 
        "--host", "0.0.0.0", "--port", "8001", "--reload"
    ])

if __name__ == "__main__":
    print("🚀 Iniciando servidores...")
    print("📡 API Principal: http://localhost:8000")
    print("📱 WhatsApp Webhook: http://localhost:8001")
    
    # Ejecutar en hilos separados
    threading.Thread(target=run_main_api).start()
    time.sleep(2)
    threading.Thread(target=run_whatsapp_webhook).start()
    
    print("✅ Servidores iniciados. Presiona Ctrl+C para detener.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Deteniendo servidores...")