from .postulacion import Postulacion


class ProcesoSeleccion:
    def __init__(self, postulacion):
        if not isinstance(postulacion, Postulacion):
            raise TypeError("El proceso requiere una postulación.")
        self.postulacion = postulacion
        self.historial = [postulacion.estado]

    def avanzar_a(self, estado):
        self.postulacion.cambiar_estado(estado)
        self.historial.append(estado)
        return estado
