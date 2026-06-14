# whatsapp_webhook.py
from fastapi import FastAPI, Request, Form, HTTPException, Response
from twilio.twiml.messaging_response import MessagingResponse
import requests
import os
from dotenv import load_dotenv
import logging

load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Tu API local
API_URL = os.getenv("API_URL", "http://localhost:8001")

# Almacenar sesiones en memoria (para producción usa Redis o DB)
sessions = {}

def es_saludo(mensaje: str) -> bool:
    """Detecta si el mensaje es un saludo o petición de reinicio"""
    msg = mensaje.lower().strip().replace("¡", "").replace("!", "").replace("¿", "").replace("?", "")
    saludos = {"hola", "buenos dias", "buenos días", "buenas tardes", "buenas noches", "hi", "hello", "empezar", "inicio", "reiniciar", "reset"}
    return msg in saludos

@app.post("/whatsapp")
async def whatsapp_webhook(
    Body: str = Form(None),
    From: str = Form(None),
    WaId: str = Form(None)
):
    """Webhook para recibir mensajes de WhatsApp (Twilio)"""
    
    phone_number = From or f"whatsapp:{WaId}"
    user_message = Body or ""
    
    logger.info(f"Mensaje recibido de {phone_number}: {user_message}")
    
    try:
        # Si no tiene sesión activa o el usuario envía un saludo/petición de reinicio
        if phone_number not in sessions or es_saludo(user_message):
            logger.info(f"Iniciando o reiniciando sesión para {phone_number}")
            
            # Iniciar nueva sesión
            resp = requests.post(f"{API_URL}/saludar", json={"phone_origin": phone_number})
            
            if resp.status_code == 200:
                data = resp.json()
                sessions[phone_number] = data["session_id"]
                bot_response = data["mensaje"]
                logger.info(f"Nueva sesión creada: {data['session_id']}")
            else:
                bot_response = "❌ Error al iniciar la conversación. Por favor, intenta más tarde."
        else:
            # Continuar conversación existente
            logger.info(f"Continuando sesión para {phone_number}: {sessions[phone_number]}")
            
            resp = requests.post(f"{API_URL}/analizar", json={
                "session_id": sessions[phone_number],
                "mensaje": user_message,
                "phone_origin": phone_number
            })
            
            if resp.status_code == 200:
                data = resp.json()
                bot_response = data["mensaje"]
                
                # Si la conversación terminó (volvió a START)
                # O si contiene frases de despedida/cierre
                if data["estado"] == "START" and (
                    "¿En qué otra necesidad" in bot_response or
                    "¿Deseas realizar otra consulta?" in bot_response or
                    "¿Hay algo más" in bot_response or
                    "no he registrado ninguna propuesta" in bot_response
                ):
                    logger.info(f"Conversación terminada para {phone_number}, eliminando sesión")
                    del sessions[phone_number]
            else:
                bot_response = "❌ Error al procesar tu mensaje. Por favor, intenta de nuevo."
        
        # Crear respuesta de Twilio
        twilio_response = MessagingResponse()
        twilio_response.message(bot_response)
        
        logger.info(f"Respuesta enviada a {phone_number}: {bot_response[:100]}...")
        
        # Twilio requiere que el content-type sea application/xml o text/xml
        return Response(content=str(twilio_response), media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Error en webhook: {str(e)}")
        twilio_response = MessagingResponse()
        twilio_response.message("❌ Ocurrió un error. Por favor, intenta más tarde.")
        return Response(content=str(twilio_response), media_type="application/xml")

@app.get("/whatsapp")
async def whatsapp_verify():
    """Verificación para Twilio"""
    return {"status": "ok", "message": "Webhook de WhatsApp activo"}

@app.get("/sessions")
async def list_sessions():
    """Endpoint para ver sesiones activas (solo debugging)"""
    return {"active_sessions": list(sessions.keys())}