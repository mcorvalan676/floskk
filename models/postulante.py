from .usuario import Usuario

class Postulante(Usuario):
    def __init__(self, *args, telefono="", ciudad="", region="", **kwargs):
        super().__init__(*args, **kwargs)
        self.telefono = telefono
        self.ciudad = ciudad
        self.region = region

    def perfil_completo(self):
        return bool(self.nombre and self.apellido and self.correo)
