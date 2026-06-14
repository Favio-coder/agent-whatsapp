# test_whatsapp_simulator.py
import requests
import time
import sys

# ─── Configuración ────────────────────────────────────────────────────────────
# Servidor unificado: main.py expone TANTO la API como el webhook de WhatsApp
WHATSAPP_WEBHOOK_URL = "http://localhost:8000/whatsapp"
API_URL = "http://localhost:8000"

def simular_mensaje_whatsapp(phone_number: str, message: str):
    """Simula un mensaje entrante de WhatsApp (formato Twilio form-data)"""
    data = {
        "Body": message,
        "From": phone_number,
        "WaId": phone_number.replace("whatsapp:", "")
    }

    print(f"\n📱 [{phone_number}] → {message}")
    try:
        response = requests.post(WHATSAPP_WEBHOOK_URL, data=data, timeout=30)
        if response.status_code == 200:
            # Extraer solo el texto del TwiML para que sea legible en consola
            import re
            texto = re.search(r"<Message>(.*?)</Message>", response.text, re.DOTALL)
            msg_limpio = texto.group(1) if texto else response.text
            print(f"🤖 Bot: {msg_limpio}")
            return response.text
        else:
            print(f"❌ Error HTTP {response.status_code}: {response.text}")
            return None
    except requests.exceptions.ConnectionError:
        print("❌ No se pudo conectar al servidor. ¿Está corriendo uvicorn main:app en el puerto 8000?")
        sys.exit(1)

def probar_flujo_completo():
    """Prueba el flujo completo de conversación"""
    
    phone = "whatsapp:+51987654321"
    
    print("=" * 60)
    print("🧪 PROBANDO FLUJO DE WHATSAPP")
    print("=" * 60)
    
    # Paso 1: Primer mensaje (inicia conversación)
    simular_mensaje_whatsapp(phone, "Hola")
    time.sleep(1)
    
    # Paso 2: Describir un problema
    simular_mensaje_whatsapp(phone, "Mis cuyes se están muriendo por las heladas")
    time.sleep(1)
    
    # Paso 3: Seleccionar una opción (si hay proyectos)
    simular_mensaje_whatsapp(phone, "1")
    time.sleep(1)
    
    print("\n" + "=" * 60)
    print("✅ Prueba completada")
    print("=" * 60)

if __name__ == "__main__":
    probar_flujo_completo()