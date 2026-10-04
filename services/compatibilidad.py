def _lista_habilidades(value):
    if value is None:
        return []
    if isinstance(value, str):
        return value.split(",")
    return list(value)


def _habilidades_normalizadas(value):
    habilidades = {}
    for item in _lista_habilidades(value):
        visible = str(item).strip()
        normalizada = " ".join(visible.casefold().split())
        if normalizada:
            habilidades.setdefault(normalizada, visible)
    return habilidades


def analizar_compatibilidad(habilidades_postulante, habilidades_oferta, perfil=None):
    disponibles = _habilidades_normalizadas(habilidades_postulante)
    requeridas = _habilidades_normalizadas(habilidades_oferta)
    coincidencias = [
        habilidad for clave, habilidad in requeridas.items()
        if clave in disponibles
    ]
    faltantes = [
        habilidad for clave, habilidad in requeridas.items()
        if clave not in disponibles
    ]

    if requeridas:
        porcentaje = round(len(coincidencias) / len(requeridas) * 100)
        if porcentaje >= 75:
            nivel = "Alta"
        elif porcentaje >= 40:
            nivel = "Media"
        else:
            nivel = "Baja"
        explicacion = (
            f"Coinciden {len(coincidencias)} de {len(requeridas)} "
            "habilidades indicadas en la oferta."
        )
    else:
        porcentaje = None
        nivel = "Sin datos suficientes"
        explicacion = (
            "La oferta no especifica habilidades para comparar. "
            "No se puede calcular una coincidencia de habilidades."
        )

    campos_sin_informacion = []
    if perfil is not None:
        for campo, etiqueta in (
            ("habilidades", "Habilidades"),
            ("experiencia", "Experiencia"),
            ("educacion", "Educación"),
            ("descripcion", "Presentación profesional"),
            ("objetivo_profesional", "Objetivo profesional"),
        ):
            valor = perfil.get(campo)
            if not isinstance(valor, str) or not valor.strip():
                campos_sin_informacion.append(etiqueta)

    return {
        "porcentaje": porcentaje,
        "nivel": nivel,
        "coincidencias": coincidencias,
        "requisitos_faltantes": faltantes,
        "total_habilidades_requeridas": len(requeridas),
        "campos_sin_informacion": campos_sin_informacion,
        "explicacion": explicacion,
        "criterio": (
            "Compara únicamente las habilidades escritas en el perfil y "
            "las habilidades indicadas en la oferta. No evalúa a la persona "
            "ni predice una contratación."
        ),
    }


def calcular_compatibilidad(habilidades_postulante, habilidades_oferta):
    analisis = analizar_compatibilidad(
        habilidades_postulante,
        habilidades_oferta,
    )
    return analisis["porcentaje"] or 0
