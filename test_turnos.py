"""Pruebas unitarias y de integración con pytest (Patrón AAA)."""

import sqlite3
import pytest

from capa_datos import RepositorioTurnos
from capa_ley_opciones import ServicioTurnos


@pytest.fixture
def servicio():
    """Fixture: entrega un servicio conectado a una BD en memoria limpia."""
    conexion = sqlite3.connect(":memory:")
    repositorio = RepositorioTurnos(conexion)
    return ServicioTurnos(repositorio)


def test_crear_integrante_valido(servicio):
    # Arrange
    nombre = "Luis"
    apellido = "Letelier"
    rol = "GUARDIA"

    # Act
    integrante_id = servicio.crear_integrante(nombre, apellido, rol)

    # Assert
    assert integrante_id == 1


def test_crear_integrante_rol_invalido(servicio):
    # Arrange & Act & Assert
    with pytest.raises(ValueError):
        servicio.crear_integrante("Camila", "Gonzalez", "SUPERVISOR")


def test_generar_3_opciones_diurno_cumple_ley(servicio):
    # Arrange
    grupo = "A"
    jornada = "DIURNO"
    horario = "07:00 a 18:00"
    cuadrante = "Cuadrante 1"

    # Act
    opciones = servicio.generar_opciones_malla_mensual(
        grupo, jornada, horario, cuadrante
    )

    # Assert
    assert len(opciones) == 3
    for opcion in opciones:
        domingos_libres = sum(
            1 for semana in opcion["semanas"] if semana["Domingo"] == "L"
        )
        assert domingos_libres >= 2


def test_generar_3_opciones_nocturno_cumple_ley(servicio):
    # Arrange
    grupo = "B"
    jornada = "NOCTURNO"
    horario = "20:00 a 07:00"
    cuadrante = "Cuadrante 4"

    # Act
    opciones = servicio.generar_opciones_malla_mensual(
        grupo, jornada, horario, cuadrante
    )

    # Assert
    assert len(opciones) == 3
    for opcion in opciones:
        findes_libres = sum(
            1
            for sem in opcion["semanas"]
            if sem["Sábado"] == "L" and sem["Domingo"] == "L"
        )
        assert findes_libres >= 2


def test_asignar_y_editar_celda_malla_integracion(servicio):
    # Arrange
    guardia_id = servicio.crear_integrante("Alejandro", "Herrera", "GUARDIA")
    opciones = servicio.generar_opciones_malla_mensual(
        "A", "DIURNO", "09:00 a 20:00", "Cuadrante 2"
    )
    servicio.asignar_opcion_a_personal(guardia_id, opciones[0])
    malla = servicio.repositorio.obtener_malla_personal(guardia_id)
    primer_dia_id = malla[0]["id"]  # Lunes de la semana 1

    # Act: Cambiar estado 'T' a 'VAC' (Vacaciones)
    editado = servicio.editar_estado_dia(guardia_id, primer_dia_id, "VAC")

    # Assert
    assert editado is True
    malla_actualizada = servicio.repositorio.obtener_malla_personal(guardia_id)
    assert malla_actualizada[0]["estado"] == "VAC"


def test_rechaza_edicion_que_infringe_descanso_dominical(servicio):
    # Arrange
    guardia_id = servicio.crear_integrante("Monica", "Bustos", "GUARDIA")
    opciones = servicio.generar_opciones_malla_mensual(
        "A", "DIURNO", "07:00 a 18:00", "Cuadrante 3"
    )
    servicio.asignar_opcion_a_personal(guardia_id, opciones[0])
    malla = servicio.repositorio.obtener_malla_personal(guardia_id)

    # Buscar los domingos libres ('L') de la malla
    domingos_libres = [
        fila for fila in malla if fila["dia_semana"] == "Domingo" and fila["estado"] == "L"
    ]

    # Act & Assert: Intentar quitar el descanso dominical cambiando 'L' por 'T'
    with pytest.raises(ValueError, match="Edición rechazada"):
        servicio.editar_estado_dia(guardia_id, domingos_libres[0]["id"], "T")