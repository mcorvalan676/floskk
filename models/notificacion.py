class Notificacion:
    def __init__(self, usuario_id, mensaje, leida=False):
        self.usuario_id = usuario_id
        self.mensaje = mensaje
        self.leida = bool(leida)

    def marcar_como_leida(self):
        self.leida = True
