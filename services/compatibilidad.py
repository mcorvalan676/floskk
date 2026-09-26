def calcular_compatibilidad(habilidades_postulante, habilidades_oferta):
    requeridas = {x.strip().lower() for x in habilidades_oferta if x.strip()}
    disponibles = {x.strip().lower() for x in habilidades_postulante if x.strip()}

    if not requeridas:
        return 0

    return round(len(requeridas & disponibles) / len(requeridas) * 100)
