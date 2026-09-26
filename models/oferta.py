class OfertaLaboral:
    def __init__(self, id=None, empresa_id=None, titulo="", descripcion="", estado="ACTIVA"):
        self.id = id
        self.empresa_id = empresa_id
        self.titulo = titulo
        self.descripcion = descripcion
        self.estado = estado

    def esta_activa(self):
        return self.estado == "ACTIVA"
