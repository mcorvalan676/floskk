from .usuario import Usuario

class Empresa(Usuario):
    def __init__(self, *args, nombre_empresa="", **kwargs):
        super().__init__(*args, **kwargs)
        self.nombre_empresa = nombre_empresa

    def puede_publicar(self):
        return self.rol in ("EMPRESA", "ADMIN")
