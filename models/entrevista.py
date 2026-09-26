class Entrevista:
    MODALIDADES = ("PRESENCIAL", "ONLINE", "TELEFONICA")

    def __init__(self, id=None, postulacion_id=None, modalidad="ONLINE"):
        self.id = id
        self.postulacion_id = postulacion_id
        self.modalidad = modalidad

    def modalidad_valida(self):
        return self.modalidad in self.MODALIDADES
