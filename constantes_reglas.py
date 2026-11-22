"""Configuración y constantes del dominio operativo (La Cisterna)."""

CUADRANTES = (
    "Cuadrante 1",
    "Cuadrante 2",
    "Cuadrante 3",
    "Cuadrante 4",
    "Cuadrante 5",
    "Cuadrante 6",
)

ROLES_PERSONAL = ("GUARDIA", "RADIO_OPERADOR")

GRUPOS_TURNO = ("A", "B")

HORARIOS_DIURNOS = (
    "07:00 a 18:00",
    "08:00 a 19:00",
    "09:00 a 20:00",
)

HORARIO_NOCTURNO = "20:00 a 07:00"

ESTADOS_CELDA = ("T", "L", "VAC", "HE", "HEN")

DIAS_SEMANA = (
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
)

# Restricción legal (Art. 38 Código del Trabajo - Jornadas Excepcionales 4x3)
MIN_DOMINGOS_LIBRES_DIURNO = 2
MIN_FINDES_LIBRES_NOCTURNO = 2