class Postulacion:
    ESTADOS = (
        "POSTULADO", "REVISION", "PRESELECCIONADO",
        "ENTREVISTA", "SELECCIONADO", "RECHAZADO", "FINALIZADO"
    )

    def __init__(self, id=None, oferta_id=None, postulante_id=None, estado="POSTULADO"):
        self.id = id
        self.oferta_id = oferta_id
        self.postulante_id = postulante_id
        self.estado = estado

    def cambiar_estado(self, nuevo_estado):
        if nuevo_estado not in self.ESTADOS:
            raise ValueError("Estado no válido")
        self.estado = nuevo_estado
