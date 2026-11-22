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
ROLES_PERSONAL = ("PATRULLERO", "RADIO_OPERADOR", "SUPERVISOR", "JEFE_TURNO")

# El jefe de turno nunca se asigna automáticamente: solo a mano, a un móvil y/o un cuadrante.
ROL_JEFE_TURNO = "JEFE_TURNO"

ETIQUETAS_ROL = {
    "PATRULLERO": "Patrullero",
    "RADIO_OPERADOR": "Radio operador",
    "SUPERVISOR": "Supervisor",
    "JEFE_TURNO": "Jefe de turno",
}


def etiqueta_rol(rol: str) -> str:
    return ETIQUETAS_ROL.get(rol, rol.replace("_", " ").capitalize())

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

# T turno · L libre · VAC vacaciones · LM licencia médica · HE/HEN horas extra
ESTADOS_CELDA = ("T", "L", "VAC", "LM", "HE", "HEN")

# Vacaciones y licencias médicas se cargan por rango de fechas (no día por día)
ESTADOS_AUSENCIA = ("VAC", "LM")
NOMBRES_AUSENCIA = {"VAC": "Vacaciones", "LM": "Licencia médica"}

# Estados que se pueden cambiar día por día en la grilla
ESTADOS_DIA_EDITABLES = ("T", "L", "HE", "HEN")

# Mínimo de personas trabajando cada día (entre todos los cargos)
MIN_PERSONAS_POR_DIA = 3

# Estados en los que la persona NO trabaja (cuentan como día libre para el Art. 38)
ESTADOS_LIBRES = ("L", "VAC", "LM")

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

# Mínimo de personas con Moto y con Bicicleta en cada turno (A/B × diurno/nocturno)
# y trabajando cada día en cada jornada.
MIN_POR_TURNO_MODALIDAD = {"Moto": 2, "Bicicleta": 2}
