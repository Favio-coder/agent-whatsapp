"""
session_store.py
Gestión de sesiones persistentes en Supabase.
Reemplaza los diccionarios SESSIONS y WHATSAPP_SESSIONS en memoria.

Tabla esperada en Supabase:
    sessions (
        session_id  TEXT PRIMARY KEY,
        phone_number TEXT UNIQUE,
        state        TEXT DEFAULT 'START',
        metadata     JSONB DEFAULT '{}',
        created_at   TIMESTAMPTZ DEFAULT NOW(),
        updated_at   TIMESTAMPTZ DEFAULT NOW()
    )
"""
import uuid
import logging
from supabase_client import supabase

logger = logging.getLogger(__name__)
TABLE = "sessions"


# ──────────────────────────────────────────────────────────────────────────────
#  Funciones internas
# ──────────────────────────────────────────────────────────────────────────────

def _get_row_by_session(session_id: str) -> dict | None:
    res = supabase.table(TABLE).select("*").eq("session_id", session_id).limit(1).execute()
    return res.data[0] if res.data else None


def _get_row_by_phone(phone_number: str) -> dict | None:
    res = supabase.table(TABLE).select("*").eq("phone_number", phone_number).limit(1).execute()
    return res.data[0] if res.data else None


# ──────────────────────────────────────────────────────────────────────────────
#  API Pública
# ──────────────────────────────────────────────────────────────────────────────

def crear_sesion(phone_number: str = "") -> str:
    """Crea una nueva sesión en Supabase y devuelve el session_id."""
    session_id = str(uuid.uuid4())
    data = {
        "session_id": session_id,
        "state": "START",
        "metadata": {"phone_origin": phone_number} if phone_number else {}
    }
    if phone_number:
        data["phone_number"] = phone_number

    try:
        # Si ya existe una fila con ese phone, la reemplazamos (upsert)
        supabase.table(TABLE).upsert(data, on_conflict="phone_number").execute()
    except Exception:
        # Si no hay phone_number, hacemos insert normal
        supabase.table(TABLE).insert(data).execute()

    logger.info(f"[Session] Nueva sesión creada: {session_id} | phone: {phone_number}")
    return session_id


def get_sesion(session_id: str) -> dict | None:
    """
    Devuelve {"state": ..., "metadata": ...} para el session_id dado.
    Retorna None si no existe.
    """
    row = _get_row_by_session(session_id)
    if not row:
        return None
    return {"state": row["state"], "metadata": row.get("metadata") or {}}


def get_sesion_por_phone(phone_number: str) -> dict | None:
    """
    Devuelve {"session_id": ..., "state": ..., "metadata": ...} por teléfono.
    Retorna None si no existe.
    """
    row = _get_row_by_phone(phone_number)
    if not row:
        return None
    return {
        "session_id": row["session_id"],
        "state": row["state"],
        "metadata": row.get("metadata") or {}
    }


def guardar_sesion(session_id: str, state: str, metadata: dict) -> None:
    """Actualiza state y metadata de una sesión existente."""
    try:
        supabase.table(TABLE).update({
            "state": state,
            "metadata": metadata
        }).eq("session_id", session_id).execute()
    except Exception as e:
        logger.error(f"[Session] Error guardando sesión {session_id}: {e}")


def eliminar_sesion_por_phone(phone_number: str) -> None:
    """Elimina la sesión asociada a un número de teléfono."""
    try:
        supabase.table(TABLE).delete().eq("phone_number", phone_number).execute()
        logger.info(f"[Session] Sesión eliminada para {phone_number}")
    except Exception as e:
        logger.error(f"[Session] Error eliminando sesión de {phone_number}: {e}")


def get_o_crear_sesion(session_id: str) -> dict:
    """
    Obtiene la sesión o crea una vacía si no existe.
    Devuelve {"state": ..., "metadata": ...}.
    """
    sesion = get_sesion(session_id)
    if sesion is None:
        # Insertar fila nueva sin phone
        supabase.table(TABLE).insert({
            "session_id": session_id,
            "state": "START",
            "metadata": {}
        }).execute()
        sesion = {"state": "START", "metadata": {}}
    return sesion
