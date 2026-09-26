class Usuario:
    def __init__(self, id=None, nombre="", apellido="", correo="", rol="POSTULANTE"):
        self.id = id
        self.nombre = nombre
        self.apellido = apellido
        self.correo = correo
        self.rol = rol

    def nombre_completo(self):
        return f"{self.nombre} {self.apellido}"
