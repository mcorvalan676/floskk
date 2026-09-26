from pathlib import Path


class Curriculum:
    def __init__(self, postulante_id, archivo):
        self.postulante_id = postulante_id
        self.archivo = archivo

    def es_pdf(self):
        return Path(self.archivo).suffix.lower() == ".pdf"
