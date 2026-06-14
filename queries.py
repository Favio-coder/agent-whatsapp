from supabase_client import supabase

def buscar_proyectos(categoria):

    response = (
        supabase
        .table("proyectos")
        .select("*")
        .eq("categoria", categoria)
        .execute()
    )

    print("Proyectos que se estan llamando: ", response.data)

    return response.data

def crear_proyecto(titulo, facultad, ods, categoria):

    return (
        supabase
        .table("proyectos")
        .insert({
            "titulo": titulo,
            "facultad": facultad,
            "ods": ods,
            "categoria": categoria
        })
        .execute()
    )

def crear_peticion(proyecto, phone_origin, id_proyect):

    return (
        supabase
        .table("peticiones")
        .insert({
            "proyecto": proyecto,
            "phone_origin": phone_origin,
            "estado": "no atendido",
            "id_proyect": id_proyect
        })
        .execute()
    )