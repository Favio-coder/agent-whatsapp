import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

model = genai.GenerativeModel("gemini-3.1-flash-lite")

CARRERAS_VALIDAS = [
    "Enfermería", "Medicina Humana", "Arquitectura", "Ingeniería Civil", 
    "Ingeniería de Minas", "Ingeniería de Sistemas", "Ingeniería Eléctrica y Electrónica", 
    "Ingeniería Mecánica", "Ingeniería Metalúrgica y de Materiales", "Ingeniería Química", 
    "Ingeniería Química Industrial", "Ingeniería Química Ambiental", "Administración de Empresas", 
    "Contabilidad", "Economía", "Administración de Negocios - Tarma", 
    "Administración Hotelera y Turismo - Tarma", "Antropología", "Ciencias de la Comunicación", 
    "Derecho y Ciencias Políticas", "Sociología", "Trabajo Social", 
    "Educación Inicial", "Educación Primaria", 
    "Educación Filosofía, Ciencias Sociales y Relaciones Humanas", 
    "Educación Lengua, Literatura y Comunicación", "Educación Ciencias Naturales y Ambientales", 
    "Educación Ciencias Matemáticas e Informática", "Educación Física y Psicomotricidad", 
    "Agronomía", "Ingeniería Forestal y Ambiental", "Ingeniería en Industrias Alimentarias", 
    "Zootecnia", "Ing. Agroindustrial - Tarma", "Ing. Agronomía Tropical - Satipo", 
    "Ing. Forestal Tropical - Satipo", "Ing. Industrias Alimentarias Tropical - Satipo", 
    "Zootecnia Tropical- Satipo"
]

import json
import re

def _extraer_json(texto_respuesta):
    # Search for json block
    match = re.search(r'```json\s*(.*?)\s*```', texto_respuesta, re.DOTALL)
    if match:
        texto_clean = match.group(1)
    else:
        texto_clean = texto_respuesta.strip()
    
    try:
        return json.loads(texto_clean)
    except Exception as e:
        # Fallback parsing: look for first '{' or '[' to the last '}' or ']'
        match_obj = re.search(r'(\{.*\}|\[.*\])', texto_clean, re.DOTALL)
        if match_obj:
            try:
                return json.loads(match_obj.group(1))
            except:
                pass
        raise e

def analizar_problema(texto):
    carreras_str = ", ".join(CARRERAS_VALIDAS)
    prompt = f"""
    Eres un especialista en proyectos de proyección social universitaria.
    Analiza la necesidad descrita por un comunero y clasifícala en una de las categorías válidas.
    También genera un título sugerido, la carrera universitaria más apta para realizarlo, y el ODS principal relacionado.

    Categorías válidas:
    - agricultura
    - agua
    - salud
    - educacion
    - infraestructura
    - tecnologia
    - medio_ambiente
    - energia
    - emprendimiento
    - turismo
    - inclusion social
    - seguridad alimentaria
    - transporte
    - vivienda
    - gestion publica
    - otro

    Carreras universitarias válidas para "facultad_propuesta":
    {carreras_str}

    Problema del comunero:
    "{texto}"

    Responde ESTRICTAMENTE en formato JSON con la siguiente estructura (no agregues texto fuera del JSON):
    {{
        "categoria": "categoría_elegida",
        "titulo_propuesto": "Título corto y claro del proyecto propuesto",
        "facultad_propuesta": "Carrera elegida (DEBE ser exactamente uno de los nombres de la lista de carreras de arriba, sin agregar la palabra 'Facultad' ni 'Facultad de')",
        "ods_propuesta": "ODS relacionado (ej. ODS 2: Hambre Cero)"
    }}
    """
    response = model.generate_content(prompt)
    try:
        res_json = _extraer_json(response.text)
        # Clean up any accidental "Facultad de" prefix in post-processing just in case
        fac = res_json.get("facultad_propuesta", "")
        for prefix in ["Facultad de ", "Facultad ", "facultad de ", "facultad "]:
            if fac.startswith(prefix):
                fac = fac[len(prefix):]
        res_json["facultad_propuesta"] = fac.strip()
        return res_json
    except Exception:
        # Fallback defaults
        return {
            "categoria": "otro",
            "titulo_propuesto": "Proyecto de Apoyo Comunitario",
            "facultad_propuesta": "Trabajo Social",
            "ods_propuesta": "ODS 17: Alianzas para lograr los objetivos"
        }

def generar_alternativas(problema, categoria):
    carreras_str = ", ".join(CARRERAS_VALIDAS)
    prompt = f"""
    Eres un especialista en formulación de proyectos de proyección social universitaria.
    El comunero tiene el siguiente problema: "{problema}"
    La categoría del problema es: "{categoria}"

    Propón exactamente 3 alternativas de proyectos universitarios viables para resolver este problema en esa categoría.
    Cada propuesta debe contener:
    1. "titulo": Título claro y conciso del proyecto.
    2. "facultad": La carrera universitaria más pertinente (DEBE ser exactamente uno de los nombres de la lista de carreras de abajo, sin agregar la palabra 'Facultad' ni 'Facultad de').
    3. "ods": El ODS más relacionado (ej. ODS 2: Hambre Cero, ODS 3: Salud y Bienestar, ODS 6: Agua Limpia, etc.).
    4. "descripcion": Una descripción breve del proyecto y cómo ayuda (máximo 2 frases).

    Lista de carreras válidas:
    {carreras_str}

    Responde ESTRICTAMENTE en formato JSON como un arreglo de 3 objetos con la siguiente estructura (no agregues texto fuera del JSON):
    [
        {{
            "titulo": "Título de la propuesta 1",
            "facultad": "Carrera seleccionada de la lista 1",
            "ods": "ODS relacionado 1",
            "descripcion": "Descripción breve 1"
        }},
        ...
    ]
    """
    response = model.generate_content(prompt)
    try:
        alternativas = _extraer_json(response.text)
        # Clean up any accidental "Facultad de" prefix in post-processing
        for alt in alternativas:
            fac = alt.get("facultad", "")
            for prefix in ["Facultad de ", "Facultad ", "facultad de ", "facultad "]:
                if fac.startswith(prefix):
                    fac = fac[len(prefix):]
            alt["facultad"] = fac.strip()
        return alternativas
    except Exception:
        return [
            {
                "titulo": f"Proyecto de Apoyo en {categoria.capitalize()} - Opción A",
                "facultad": "Trabajo Social",
                "ods": "ODS 17: Alianzas",
                "descripcion": f"Desarrollo de soluciones locales para {problema}."
            },
            {
                "titulo": f"Proyecto de Capacitación en {categoria.capitalize()} - Opción B",
                "facultad": "Educación Primaria",
                "ods": "ODS 4: Educación de Calidad",
                "descripcion": f"Capacitación comunitaria para afrontar problemáticas de {categoria}."
            },
            {
                "titulo": f"Implementación Técnica en {categoria.capitalize()} - Opción C",
                "facultad": "Ingeniería de Sistemas",
                "ods": "ODS 9: Industria, Innovación e Infraestructura",
                "descripcion": f"Asesoramiento y soporte técnico directo en la comunidad."
            }
        ]

def interpretar_seleccion(mensaje_usuario, cantidad_opciones):
    prompt = f"""
    Analiza la respuesta del usuario para determinar qué opción ha seleccionado o si ha decidido no elegir ninguna.
    
    El usuario tenía {cantidad_opciones} opciones numeradas de 1 a {cantidad_opciones}.
    Mensaje del usuario: "{mensaje_usuario}"
    
    Determina si el usuario:
    - Seleccionó un número de opción específico (por ejemplo: "1", "el primero", "me quedo con la segunda", "la 3"). Si es así, identifica el índice (un número entero de 1 a {cantidad_opciones}).
    - Indicó que no desea ninguna de las opciones (por ejemplo: "ninguno", "no", "no me gusta ninguno", "ninguna", "ninguno de esos"). Si es así, responde con "NINGUNO".
    - Respondió algo inválido o no relacionado. Si es así, responde con "INVALIDO".
    
    Responde ESTRICTAMENTE en formato JSON (sin texto adicional):
    {{
        "opcion_elegida": <número entero de 1 a {cantidad_opciones} | "NINGUNO" | "INVALIDO">,
        "explicacion": "Breve explicación de la interpretación"
    }}
    """
    response = model.generate_content(prompt)
    try:
        data = _extraer_json(response.text)
        val = data.get("opcion_elegida", "INVALIDO")
        # If it returned a string representation of an int, parse it
        if isinstance(val, str) and val.isdigit():
            val = int(val)
        return val
    except Exception:
        msg = mensaje_usuario.lower()
        if "ningun" in msg or " no " in msg or msg.startswith("no") or "ninguna" in msg:
            return "NINGUNO"
        for i in range(1, cantidad_opciones + 1):
            if str(i) in msg or f"opcion {i}" in msg or f"opción {i}" in msg:
                return i
        return "INVALIDO"