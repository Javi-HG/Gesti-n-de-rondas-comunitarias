"""Configuración y constantes del dominio operativo (La Cisterna)."""

CUADRANTES = (
    "Cuadrante 1",
    "Cuadrante 2",
    "Cuadrante 3",
    "Cuadrante 4",
    "Cuadrante 5",
    "Cuadrante 6",
)

# La feria es un destino de servicio alternativo al cuadrante, solo para bicicletas.
FERIA = "Feria"
DESTINOS_SERVICIO = CUADRANTES + (FERIA,)

# Cada cuadrante debe tener al menos esta cantidad de patrulleros con modalidad Móvil.
MIN_MOVILES_POR_CUADRANTE = 1

# Para sumar cargos nuevos basta agregarlos aquí; el planificador de equipo
# calcula la cobertura por cada rol registrado.
ROLES_PERSONAL = ("PATRULLERO", "RADIO_OPERADOR", "SUPERVISOR")

# Solo los patrulleros tienen modalidad (Móvil, Moto, Infantería, Bicicleta)
ROL_PATRULLERO = "PATRULLERO"

# Modalidad de patrullaje / servicio
MODALIDADES = ("Móvil", "Moto", "Infantería", "Bicicleta")

GRUPOS_TURNO = ("A", "B")

JORNADAS = ("DIURNO", "NOCTURNO")

HORARIOS_DIURNOS = (
    "07:00 a 18:00",
    "08:00 a 19:00",
    "09:00 a 20:00",
)

HORARIO_NOCTURNO = "20:00 a 07:00"

ESTADOS_CELDA = ("T", "L", "VAC", "HE", "HEN")

# Estados en los que la persona NO trabaja (cuentan como día libre para el Art. 38)
ESTADOS_LIBRES = ("L", "VAC")

DIAS_SEMANA = (
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
)

SEMANAS_MES = 4

# Restricción legal (Art. 38 Código del Trabajo - Jornadas Excepcionales 4x3)
MIN_DOMINGOS_LIBRES_DIURNO = 2
MIN_FINDES_LIBRES_NOCTURNO = 2
