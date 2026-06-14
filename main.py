"""
Asistente de IA para Comuneros - Backend Unificado
Combina la API de conversación + Webhook de WhatsApp (Twilio) en un solo servidor.
"""
import uuid
import os
import logging
import requests as http_requests

from fastapi import FastAPI, Form, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from twilio.twiml.messaging_response import MessagingResponse

from gemini_service import analizar_problema, generar_alternativas, interpretar_seleccion
from queries import buscar_proyectos, crear_proyecto, crear_peticion

load_dotenv()

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Asistente de IA para Comuneros",
    description="API conversacional con integración WhatsApp (Twilio) y Supabase.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Almacenamiento de sesiones en memoria ────────────────────────────────────
# { session_id: { "state": str, "metadata": dict } }
SESSIONS: dict = {}
# Mapeo phone -> session_id para WhatsApp
WHATSAPP_SESSIONS: dict = {}


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS DE CONVERSACIÓN
# ══════════════════════════════════════════════════════════════════════════════

def _nueva_sesion(phone_origin: str = "") -> dict:
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "state": "START",
        "metadata": {"phone_origin": phone_origin} if phone_origin else {}
    }
    return {"session_id": session_id, "estado": "START",
            "mensaje": "¡Hola! 👋 Soy tu asistente de IA para la comunidad. ¿En qué necesidad o problema te puedo ayudar hoy?"}


def _sugerir_alternativas(session_id: str, session: dict, problema: str, categoria: str) -> dict:
    alternativas = generar_alternativas(problema, categoria)
    session["state"] = "AWAITING_ALTERNATIVE_SELECTION"
    session["metadata"]["alternativas_propuestas"] = alternativas

    alternativas_list = ""
    for i, alt in enumerate(alternativas, start=1):
        alternativas_list += (
            f"\n💡 *Propuesta {i}: {alt['titulo']}*\n"
            f"   Carrera: {alt['facultad']} | ODS: {alt['ods']}\n"
            f"   _{alt['descripcion']}_\n"
        )

    return {
        "session_id": session_id,
        "estado": "AWAITING_ALTERNATIVE_SELECTION",
        "mensaje": (
            f"No encontré proyectos registrados para la categoría *{categoria.capitalize()}*.\n\n"
            f"Aquí tienes 3 propuestas alternativas diseñadas por la IA:\n"
            f"{alternativas_list}\n"
            f"¿Cuál te gustaría registrar oficialmente? Responde *1*, *2*, *3* o *NINGUNO*."
        )
    }


def _procesar_mensaje(session_id: str, mensaje: str) -> dict:
    """Núcleo de la máquina de estados conversacional."""

    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"state": "START", "metadata": {}}

    session = SESSIONS[session_id]
    state = session["state"]
    metadata = session["metadata"]
    phone_origin = metadata.get("phone_origin", "desconocido")

    # ── State: START ──────────────────────────────────────────────────────────
    if state == "START":
        if not mensaje:
            return {"session_id": session_id, "estado": "START",
                    "mensaje": "Por favor, describe tu problema o necesidad. Ejemplo: 'Mis cuyes están muriendo por la helada'."}

        analisis = analizar_problema(mensaje)
        categoria         = analisis.get("categoria", "otro").lower().strip()
        titulo_propuesto  = analisis.get("titulo_propuesto", "Proyecto de Apoyo Comunitario")
        facultad_propuesta = analisis.get("facultad_propuesta", "Trabajo Social")
        ods_propuesta     = analisis.get("ods_propuesta", "ODS 17: Alianzas")

        metadata.update({
            "problema": mensaje, "categoria": categoria,
            "titulo_propuesto": titulo_propuesto,
            "facultad_propuesta": facultad_propuesta,
            "ods_propuesta": ods_propuesta
        })

        proyectos = buscar_proyectos(categoria)

        if proyectos:
            session["state"] = "AWAITING_PROJECT_SELECTION"
            metadata["proyectos_encontrados"] = proyectos

            proyectos_list = ""
            for i, p in enumerate(proyectos, start=1):
                proyectos_list += (
                    f"\n📌 *Opción {i}: {p.get('titulo', 'Sin Título')}*\n"
                    f"   Carrera: {p.get('facultad', 'No especificada')} | ODS: {p.get('ods', 'No especificado')}\n"
                )

            return {
                "session_id": session_id,
                "estado": "AWAITING_PROJECT_SELECTION",
                "mensaje": (
                    f"Clasifiqué tu necesidad en: *{categoria.capitalize()}*.\n\n"
                    f"Encontré {len(proyectos)} proyecto(s) registrado(s):\n"
                    f"{proyectos_list}\n"
                    f"¿Te interesa alguno? Responde con el número (ej. *1*, *2*) o *NINGUNO* para ver alternativas."
                )
            }
        else:
            return _sugerir_alternativas(session_id, session, mensaje, categoria)

    # ── State: AWAITING_PROJECT_SELECTION ─────────────────────────────────────
    elif state == "AWAITING_PROJECT_SELECTION":
        if not mensaje:
            return {"session_id": session_id, "estado": state,
                    "mensaje": "Por favor, selecciona una opción válida (1, 2…) o responde NINGUNO."}

        proyectos = metadata.get("proyectos_encontrados", [])
        opcion = interpretar_seleccion(mensaje, len(proyectos))

        if isinstance(opcion, int) and 1 <= opcion <= len(proyectos):
            proyecto = proyectos[opcion - 1]
            try:
                crear_peticion(proyecto=proyecto.get("titulo"),
                               phone_origin=phone_origin,
                               id_proyect=proyecto.get("id"))
                respuesta = (
                    f"¡Excelente! He registrado tu solicitud para:\n"
                    f"📋 *{proyecto.get('titulo')}*\n"
                    f"- Carrera: {proyecto.get('facultad')}\n"
                    f"- Contacto: {phone_origin}\n"
                    f"- Estado: Enviado\n\n"
                    f"Pronto nos comunicamos contigo. ¡Gracias! 🙌\n\n¿Deseas realizar otra consulta?"
                )
            except Exception as e:
                respuesta = f"Seleccionaste el proyecto *{proyecto.get('titulo')}*, pero hubo un error al registrar la petición: {e}"

            session["state"] = "START"
            session["metadata"] = {"phone_origin": phone_origin}
            return {"session_id": session_id, "estado": "START", "mensaje": respuesta}

        elif opcion == "NINGUNO":
            return _sugerir_alternativas(session_id, session, metadata["problema"], metadata["categoria"])

        else:
            return {"session_id": session_id, "estado": state,
                    "mensaje": "No entendí tu selección. Responde con el número del proyecto (ej. 1, 2) o NINGUNO."}

    # ── State: AWAITING_ALTERNATIVE_SELECTION ─────────────────────────────────
    elif state == "AWAITING_ALTERNATIVE_SELECTION":
        if not mensaje:
            return {"session_id": session_id, "estado": state,
                    "mensaje": "Por favor, selecciona una propuesta alternativa (1, 2 o 3)."}

        alternativas = metadata.get("alternativas_propuestas", [])
        opcion = interpretar_seleccion(mensaje, len(alternativas))

        if isinstance(opcion, int) and 1 <= opcion <= len(alternativas):
            alt = alternativas[opcion - 1]
            try:
                res_proj = crear_proyecto(titulo=alt["titulo"], facultad=alt["facultad"],
                                          ods=alt["ods"], categoria=metadata["categoria"])
                new_id = res_proj.data[0].get("id") if res_proj and res_proj.data else None
                crear_peticion(proyecto=alt["titulo"], phone_origin=phone_origin, id_proyect=new_id)

                respuesta = (
                    f"¡Registrado! 🎉\n"
                    f"📋 *{alt['titulo']}*\n"
                    f"- Categoría: {metadata['categoria'].capitalize()}\n"
                    f"- Carrera: {alt['facultad']}\n"
                    f"- ODS: {alt['ods']}\n"
                    f"- Contacto: {phone_origin}\n"
                    f"- Estado: Enviado\n\n"
                    f"Pronto nos pondremos en contacto contigo. ¡Muchas gracias! 🙌\n\n¿Deseas realizar otra consulta?"
                )
            except Exception as e:
                respuesta = f"Hubo un problema al registrar la propuesta: {e}. Por favor intenta de nuevo."

            session["state"] = "START"
            session["metadata"] = {"phone_origin": phone_origin}
            return {"session_id": session_id, "estado": "START", "mensaje": respuesta}

        elif opcion == "NINGUNO":
            session["state"] = "START"
            session["metadata"] = {"phone_origin": phone_origin}
            return {"session_id": session_id, "estado": "START",
                    "mensaje": "Entendido, no registré ninguna propuesta. ¿En qué otra cosa puedo ayudarte?"}

        else:
            return {"session_id": session_id, "estado": state,
                    "mensaje": "No entendí tu selección. Responde con 1, 2, 3 o NINGUNO."}

    # ── Fallback ──────────────────────────────────────────────────────────────
    session["state"] = "START"
    session["metadata"] = {"phone_origin": phone_origin}
    return {"session_id": session_id, "estado": "START",
            "mensaje": "Ocurrió un error en el flujo. ¿En qué te puedo ayudar?"}


# ══════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS REST (para frontend / pruebas directas)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"status": "online", "mensaje": "Asistente de IA para comuneros - v2.0"}


@app.get("/saludar")
@app.post("/saludar")
def saludar(data: dict = None):
    phone_origin = ""
    if data:
        phone_origin = data.get("phone_origin", "")
    res = _nueva_sesion(phone_origin)
    return res


@app.post("/analizar")
def analizar(data: dict):
    session_id     = data.get("session_id")
    mensaje        = data.get("mensaje") or data.get("problema", "")
    phone_origin   = data.get("phone_origin")

    if not session_id:
        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = {"state": "START", "metadata": {}}

    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"state": "START", "metadata": {}}

    if phone_origin:
        SESSIONS[session_id]["metadata"]["phone_origin"] = phone_origin

    return _procesar_mensaje(session_id, mensaje)


# ══════════════════════════════════════════════════════════════════════════════
#  WEBHOOK WHATSAPP (Twilio) — mismo puerto
# ══════════════════════════════════════════════════════════════════════════════

def _es_saludo(mensaje: str) -> bool:
    msg = (mensaje.lower().strip()
           .replace("¡", "").replace("!", "")
           .replace("¿", "").replace("?", ""))
    saludos = {
        "hola", "buenos dias", "buenos días", "buenas tardes",
        "buenas noches", "hi", "hello", "empezar", "inicio",
        "reiniciar", "reset", "start"
    }
    return msg in saludos

def _es_fin_conversacion(estado: str, mensaje: str) -> bool:
    """Detecta si la conversación terminó para limpiar la sesión de WhatsApp."""
    fin_frases = [
        "¿Deseas realizar otra consulta?",
        "¿En qué otra cosa puedo ayudarte?",
        "no registré ninguna propuesta",
    ]
    return estado == "START" and any(f in mensaje for f in fin_frases)


@app.post("/whatsapp")
async def whatsapp_webhook(
    Body: str = Form(None),
    From: str = Form(None),
    WaId: str = Form(None)
):
    """Webhook para recibir mensajes de WhatsApp enviados por Twilio."""
    phone  = From or f"whatsapp:{WaId}"
    texto  = (Body or "").strip()

    logger.info(f"[WA] De: {phone} | Mensaje: {texto}")

    try:
        # Si no hay sesión o el usuario saluda → nueva sesión
        if phone not in WHATSAPP_SESSIONS or _es_saludo(texto):
            res = _nueva_sesion(phone_origin=phone)
            WHATSAPP_SESSIONS[phone] = res["session_id"]
            bot_response = res["mensaje"]
        else:
            res = _procesar_mensaje(WHATSAPP_SESSIONS[phone], texto)
            # Actualizar session_id si se regeneró
            WHATSAPP_SESSIONS[phone] = res["session_id"]
            bot_response = res["mensaje"]

            if _es_fin_conversacion(res["estado"], bot_response):
                logger.info(f"[WA] Sesión terminada para {phone}")
                del WHATSAPP_SESSIONS[phone]

    except Exception as e:
        logger.error(f"[WA] Error: {e}")
        bot_response = "❌ Ocurrió un error. Por favor, intenta más tarde."

    twiml = MessagingResponse()
    twiml.message(bot_response)
    logger.info(f"[WA] Respuesta a {phone}: {bot_response[:80]}...")
    return Response(content=str(twiml), media_type="application/xml")


@app.get("/whatsapp")
async def whatsapp_verify():
    return {"status": "ok", "message": "Webhook de WhatsApp activo"}


@app.get("/sessions")
async def list_sessions():
    """Solo para debugging."""
    return {
        "api_sessions": list(SESSIONS.keys()),
        "whatsapp_sessions": list(WHATSAPP_SESSIONS.keys())
    }

@app.get("/healthz")
def health_check():
    """Endpoint para monitoreo de salud (UptimeRobot, Render, etc.)"""
    return {"status": "healthy", "timestamp": time.time()}


import threading
import time
import requests
import os

def keep_alive():
    """
    Mantiene la aplicación activa en Render Free Tier.
    Hace ping a /healthz cada 4 minutos (240 segundos).
    """
    # Obtener la URL base de la aplicación
    # En Render, RENDER_EXTERNAL_URL es la URL pública completa
    base_url = os.getenv('RENDER_EXTERNAL_URL', 'https://agent-whatsapp-haoq.onrender.com')
    
    # También podemos obtener el hostname
    hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME', 'agent-whatsapp-haoq.onrender.com')
    
    # URLs para mantener activo
    urls_to_ping = [
        f"{base_url}/healthz",
        f"{base_url}/whatsapp",  # GET request (devuelve estado)
        f"https://{hostname}/healthz"
    ]
    
    while True:
        for url in urls_to_ping:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    print(f"✅ Keep-alive ping exitoso: {url}")
                else:
                    print(f"⚠️ Ping a {url} respondió con: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"❌ Error haciendo ping a {url}: {str(e)}")
            except Exception as e:
                print(f"❌ Error inesperado: {str(e)}")
        
        # Esperar 4 minutos (menos que el timeout de Render que es 15 min)
        time.sleep(240)

# Iniciar el thread solo si estamos en Render (opcional)
if os.getenv('RENDER'):
    thread = threading.Thread(target=keep_alive, daemon=True)
    thread.start()
    print("🔄 Keep-alive thread iniciado")