"""
Asistente de IA para Comuneros - Backend Unificado v3
- API conversacional REST
- Webhook de WhatsApp (Twilio)
- Sesiones persistentes en Supabase (tabla 'sessions')
"""
import os
import time
import logging
import threading
import requests as http_requests

from fastapi import FastAPI, Form, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from twilio.twiml.messaging_response import MessagingResponse

from gemini_service import analizar_problema, generar_alternativas, interpretar_seleccion
from queries import buscar_proyectos, crear_proyecto, crear_peticion
from session_store import (
    crear_sesion,
    get_sesion,
    get_sesion_por_phone,
    get_o_crear_sesion,
    guardar_sesion,
    eliminar_sesion_por_phone,
)

load_dotenv()

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Asistente de IA para Comuneros",
    description="API conversacional con integración WhatsApp (Twilio) y Supabase.",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS DE CONVERSACIÓN
# ══════════════════════════════════════════════════════════════════════════════

def _nueva_sesion(phone_origin: str = "") -> dict:
    session_id = crear_sesion(phone_number=phone_origin)
    return {
        "session_id": session_id,
        "estado": "START",
        "mensaje": "¡Hola! 👋 Soy tu asistente de IA para la comunidad. ¿En qué necesidad o problema te puedo ayudar hoy?"
    }


def _sugerir_alternativas(session_id: str, state_data: dict, problema: str, categoria: str) -> dict:
    alternativas = generar_alternativas(problema, categoria)

    state_data["state"] = "AWAITING_ALTERNATIVE_SELECTION"
    state_data["metadata"]["alternativas_propuestas"] = alternativas
    guardar_sesion(session_id, state_data["state"], state_data["metadata"])

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
    """Núcleo de la máquina de estados conversacional (persistente en Supabase)."""

    state_data = get_o_crear_sesion(session_id)
    state    = state_data["state"]
    metadata = state_data["metadata"]
    phone_origin = metadata.get("phone_origin", "desconocido")

    # ── State: START ──────────────────────────────────────────────────────────
    if state == "START":
        if not mensaje:
            return {"session_id": session_id, "estado": "START",
                    "mensaje": "Por favor, describe tu problema o necesidad. Ejemplo: 'Mis cuyes están muriendo por la helada'."}

        analisis           = analizar_problema(mensaje)
        categoria          = analisis.get("categoria", "otro").lower().strip()
        titulo_propuesto   = analisis.get("titulo_propuesto", "Proyecto de Apoyo Comunitario")
        facultad_propuesta = analisis.get("facultad_propuesta", "Trabajo Social")
        ods_propuesta      = analisis.get("ods_propuesta", "ODS 17: Alianzas")

        metadata.update({
            "problema": mensaje,
            "categoria": categoria,
            "titulo_propuesto": titulo_propuesto,
            "facultad_propuesta": facultad_propuesta,
            "ods_propuesta": ods_propuesta
        })

        proyectos = buscar_proyectos(categoria)

        if proyectos:
            state_data["state"] = "AWAITING_PROJECT_SELECTION"
            metadata["proyectos_encontrados"] = proyectos
            guardar_sesion(session_id, state_data["state"], metadata)

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
            guardar_sesion(session_id, state_data["state"], metadata)
            return _sugerir_alternativas(session_id, state_data, mensaje, categoria)

    # ── State: AWAITING_PROJECT_SELECTION ─────────────────────────────────────
    elif state == "AWAITING_PROJECT_SELECTION":
        if not mensaje:
            return {"session_id": session_id, "estado": state,
                    "mensaje": "Por favor, selecciona una opción válida (1, 2…) o responde NINGUNO."}

        proyectos = metadata.get("proyectos_encontrados", [])
        opcion    = interpretar_seleccion(mensaje, len(proyectos))

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

            guardar_sesion(session_id, "START", {"phone_origin": phone_origin})
            return {"session_id": session_id, "estado": "START", "mensaje": respuesta}

        elif opcion == "NINGUNO":
            guardar_sesion(session_id, state_data["state"], metadata)
            return _sugerir_alternativas(session_id, state_data, metadata["problema"], metadata["categoria"])

        else:
            return {"session_id": session_id, "estado": state,
                    "mensaje": "No entendí tu selección. Responde con el número del proyecto (ej. 1, 2) o NINGUNO."}

    # ── State: AWAITING_ALTERNATIVE_SELECTION ─────────────────────────────────
    elif state == "AWAITING_ALTERNATIVE_SELECTION":
        if not mensaje:
            return {"session_id": session_id, "estado": state,
                    "mensaje": "Por favor, selecciona una propuesta alternativa (1, 2 o 3)."}

        alternativas = metadata.get("alternativas_propuestas", [])
        opcion       = interpretar_seleccion(mensaje, len(alternativas))

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

            guardar_sesion(session_id, "START", {"phone_origin": phone_origin})
            return {"session_id": session_id, "estado": "START", "mensaje": respuesta}

        elif opcion == "NINGUNO":
            guardar_sesion(session_id, "START", {"phone_origin": phone_origin})
            return {"session_id": session_id, "estado": "START",
                    "mensaje": "Entendido, no registré ninguna propuesta. ¿En qué otra cosa puedo ayudarte?"}

        else:
            return {"session_id": session_id, "estado": state,
                    "mensaje": "No entendí tu selección. Responde con 1, 2, 3 o NINGUNO."}

    # ── Fallback ──────────────────────────────────────────────────────────────
    guardar_sesion(session_id, "START", {"phone_origin": phone_origin})
    return {"session_id": session_id, "estado": "START",
            "mensaje": "Ocurrió un error en el flujo. ¿En qué te puedo ayudar?"}


# ══════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS REST
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"status": "online", "mensaje": "Asistente de IA para comuneros - v3.0"}


@app.get("/saludar")
@app.post("/saludar")
def saludar(data: dict = None):
    phone_origin = ""
    if data:
        phone_origin = data.get("phone_origin", "")
    return _nueva_sesion(phone_origin)


@app.post("/analizar")
def analizar(data: dict):
    session_id   = data.get("session_id")
    mensaje      = data.get("mensaje") or data.get("problema", "")
    phone_origin = data.get("phone_origin")

    if not session_id:
        # Sin session_id: crear nueva sesión
        return _nueva_sesion(phone_origin or "")

    # Si phone_origin viene en el request, actualizarlo en la sesión
    if phone_origin:
        state_data = get_o_crear_sesion(session_id)
        state_data["metadata"]["phone_origin"] = phone_origin
        guardar_sesion(session_id, state_data["state"], state_data["metadata"])

    return _procesar_mensaje(session_id, mensaje)


# ══════════════════════════════════════════════════════════════════════════════
#  WEBHOOK WHATSAPP (Twilio)
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
    phone = From or f"whatsapp:{WaId}"
    texto = (Body or "").strip()
    logger.info(f"[WA] De: {phone} | Mensaje: {texto}")

    try:
        # Buscar sesión existente por número de teléfono
        sesion_existente = get_sesion_por_phone(phone)

        if sesion_existente is None or _es_saludo(texto):
            # Nueva sesión (crea o sobreescribe la anterior por upsert en phone_number)
            res = _nueva_sesion(phone_origin=phone)
            bot_response = res["mensaje"]
        else:
            session_id   = sesion_existente["session_id"]
            res          = _procesar_mensaje(session_id, texto)
            bot_response = res["mensaje"]

            if _es_fin_conversacion(res["estado"], bot_response):
                logger.info(f"[WA] Conversación terminada para {phone}")
                eliminar_sesion_por_phone(phone)

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
    from supabase_client import supabase
    res = supabase.table("sessions").select("session_id, phone_number, state, updated_at").execute()
    return {"sessions": res.data, "total": len(res.data)}


# ══════════════════════════════════════════════════════════════════════════════
#  HEALTH CHECK + KEEP-ALIVE (Render Free Tier)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/healthz")
def health_check():
    return {"status": "healthy", "timestamp": time.time()}


def _keep_alive():
    """Ping cada 4 min para evitar el cold-start en Render Free."""
    base_url = os.getenv("RENDER_EXTERNAL_URL", "")
    if not base_url:
        return
    url = f"{base_url}/healthz"
    while True:
        try:
            r = http_requests.get(url, timeout=10)
            logger.info(f"[KeepAlive] {url} → {r.status_code}")
        except Exception as e:
            logger.warning(f"[KeepAlive] Error: {e}")
        time.sleep(240)


if os.getenv("RENDER"):
    t = threading.Thread(target=_keep_alive, daemon=True)
    t.start()
    logger.info("🔄 Keep-alive thread iniciado")