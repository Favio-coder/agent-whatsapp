import time
from main import saludar, analizar, SESSIONS
from supabase_client import supabase

def run_tests():
    print("=== INICIANDO PRUEBAS DEL ASISTENTE DE COMUNEROS (V2) ===")
    phone_test = "+51987654321"
    
    # 1. Test Greet
    print("\n--- 1. Probando saludo inicial ---")
    res_saludo = saludar({"phone_origin": phone_test})
    session_id = res_saludo["session_id"]
    print("Session ID:", session_id)
    print("Respuesta:", res_saludo["mensaje"])
    assert res_saludo["estado"] == "START"
    
    time.sleep(3)
    
    # 2. Test input with existing projects (Category: salud)
    print("\n--- 2. Probando problema con proyecto existente (salud) ---")
    data_existente = {
        "session_id": session_id,
        "mensaje": "Nuestra gente se está enfermando mucho por el frío y no tenemos doctores ni medicinas en la comunidad, necesitamos salud urgente.",
        "phone_origin": phone_test
    }
    res_existente = analizar(data_existente)
    print("Estado transicionado:", res_existente["estado"])
    print("Respuesta del Bot:")
    print(res_existente["mensaje"])
    assert res_existente["estado"] == "AWAITING_PROJECT_SELECTION"
    
    time.sleep(3)
    
    # 3. Test selecting the project (should create a petition for existing project)
    print("\n--- 3. Probando selección de proyecto existente (opción 1) ---")
    data_seleccion_proj = {
        "session_id": session_id,
        "mensaje": "Me interesa la primera opción",
        "phone_origin": phone_test
    }
    res_sel_proj = analizar(data_seleccion_proj)
    print("Estado transicionado:", res_sel_proj["estado"])
    print("Respuesta del Bot:")
    print(res_sel_proj["mensaje"])
    assert res_sel_proj["estado"] == "START"
    
    # Verify petition was created in Supabase for existing project
    print("\n--- 3.1. Verificando petición para proyecto existente en Supabase ---")
    db_pet_existente = (
        supabase
        .table("peticiones")
        .select("*")
        .eq("phone_origin", phone_test)
        .eq("proyecto", "Proyecto para salud ")
        .execute()
    )
    print("Peticiones encontradas:", db_pet_existente.data)
    assert len(db_pet_existente.data) > 0
    # Clean up the petition
    pet_existente_id = db_pet_existente.data[0]["id"]
    supabase.table("peticiones").delete().eq("id", pet_existente_id).execute()
    print("Petición de prueba eliminada.")
    
    time.sleep(3)
    
    # 4. Test input with non-existing projects (Category: agua)
    print("\n--- 4. Probando problema sin proyecto existente (agua) ---")
    res_saludo_2 = saludar({"phone_origin": phone_test})
    session_id_2 = res_saludo_2["session_id"]
    
    data_no_existente = {
        "session_id": session_id_2,
        "mensaje": "En mi comunidad no hay agua potable, tomamos agua del río y los niños se enferman del estómago, queremos un sistema de agua limpia.",
        "phone_origin": phone_test
    }
    res_no_existente = analizar(data_no_existente)
    print("Estado transicionado:", res_no_existente["estado"])
    print("Respuesta del Bot:")
    print(res_no_existente["mensaje"])
    assert res_no_existente["estado"] == "AWAITING_ALTERNATIVE_SELECTION"
    
    # Check that alternatives were generated
    session_data = SESSIONS[session_id_2]
    alts = session_data["metadata"]["alternativas_propuestas"]
    print(f"Alternativas generadas ({len(alts)}): {[a['titulo'] for a in alts]}")
    assert len(alts) == 3
    
    # Check that none of the alternatives has "Facultad" in the "facultad" string
    for alt in alts:
        print(f"Carrera sugerida: '{alt['facultad']}' (valido: {'Facultad' not in alt['facultad']})")
        assert "Facultad" not in alt["facultad"]
        assert "facultad" not in alt["facultad"]
    
    time.sleep(3)
    
    # 5. Test selecting alternative 2 (should register project AND create petition in Supabase)
    print("\n--- 5. Probando selección y registro de alternativa 2 ---")
    alt_elegida = alts[1] # Opción 2
    print(f"Registrando opción 2: {alt_elegida['titulo']}")
    
    data_sel_alt = {
        "session_id": session_id_2,
        "mensaje": "quiero registrar la opcion 2",
        "phone_origin": phone_test
    }
    res_sel_alt = analizar(data_sel_alt)
    print("Estado transicionado:", res_sel_alt["estado"])
    print("Respuesta del Bot:")
    print(res_sel_alt["mensaje"])
    assert res_sel_alt["estado"] == "START"
    
    # 6. Verify Project and Petition in Supabase
    print("\n--- 6. Verificando inserción de proyecto y petición en Supabase ---")
    time.sleep(2) # Wait a bit for Supabase to persist
    
    # Check project
    db_res_proj = supabase.table("proyectos").select("*").eq("titulo", alt_elegida["titulo"]).execute()
    print("Registros de proyectos en DB:", db_res_proj.data)
    assert len(db_res_proj.data) > 0
    inserted_project_id = db_res_proj.data[0]["id"]
    
    # Check petition
    db_res_pet = (
        supabase
        .table("peticiones")
        .select("*")
        .eq("id_proyect", inserted_project_id)
        .eq("phone_origin", phone_test)
        .execute()
    )
    print("Registros de peticiones en DB:", db_res_pet.data)
    assert len(db_res_pet.data) > 0
    inserted_petition_id = db_res_pet.data[0]["id"]
    
    # 7. Cleanup project and petition
    print("\n--- 7. Limpiando datos de prueba ---")
    del_pet = supabase.table("peticiones").delete().eq("id", inserted_petition_id).execute()
    print("Petición eliminada:", del_pet.data)
    
    del_proj = supabase.table("proyectos").delete().eq("id", inserted_project_id).execute()
    print("Proyecto eliminado:", del_proj.data)
    
    print("\n=== ¡TODAS LAS PRUEBAS V2 PASARON EXITOSAMENTE! ===")

if __name__ == "__main__":
    run_tests()
