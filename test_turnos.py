"""Pruebas unitarias y de integración del servicio de turnos (patrón AAA).

Usan las fixtures de conftest.py: base SQLite en memoria y periodo fijado en noviembre de 2026.
"""

import pytest

from conftest import ANIO, MES, filas_con_estado

HORARIO_DIURNO = "07:00 a 18:00"
HORARIO_NOCTURNO = "20:00 a 07:00"


def test_crear_integrante_valido(servicio):
    # Arrange & Act
    integrante_id = servicio.crear_integrante("Luis Letelier", "PATRULLERO", "A", "DIURNO")

    # Assert
    persona = servicio.repositorio.obtener_persona(integrante_id)
    assert persona["nombre"] == "Luis Letelier"
    assert persona["rol"] == "PATRULLERO"


def test_crear_integrante_rol_invalido(servicio):
    with pytest.raises(ValueError, match="Rol inválido"):
        servicio.crear_integrante("Camila Gonzalez", "GUARDIA", "A", "DIURNO")


def test_crear_integrante_sin_nombre(servicio):
    with pytest.raises(ValueError, match="nombre es obligatorio"):
        servicio.crear_integrante("   ", "PATRULLERO", "A", "DIURNO")


def test_opciones_diurno_cumplen_dos_domingos_libres(servicio):
    # Act
    opciones = servicio.generar_opciones_malla_mensual("A", "DIURNO", HORARIO_DIURNO)

    # Assert
    assert len(opciones) >= 3
    for opcion in opciones:
        domingos_libres = sum(1 for semana in opcion["semanas"] if semana["Domingo"] == "L")
        assert domingos_libres >= 2


def test_opciones_nocturno_cumplen_dos_fines_de_semana_libres(servicio):
    # Act
    opciones = servicio.generar_opciones_malla_mensual("B", "NOCTURNO", HORARIO_NOCTURNO)

    # Assert
    assert len(opciones) >= 3
    for opcion in opciones:
        findes_libres = sum(
            1 for sem in opcion["semanas"] if sem["Sábado"] == "L" and sem["Domingo"] == "L"
        )
        assert findes_libres >= 2


def test_asignar_y_editar_celda_malla_integracion(servicio):
    # Arrange
    guardia_id = servicio.crear_integrante("Alejandro Herrera", "PATRULLERO", "A", "DIURNO")
    opcion = servicio.generar_opciones_malla_mensual("A", "DIURNO", HORARIO_DIURNO)[0]
    servicio.asignar_opcion_a_personal(guardia_id, opcion)
    dia_trabajo = filas_con_estado(servicio, guardia_id, "T")[0]

    # Act: un día de turno pasa a horas extra
    editado = servicio.editar_estado_dia(guardia_id, dia_trabajo["id"], "HE")

    # Assert
    assert editado is True
    nuevo = next(f for f in servicio.malla_vista(guardia_id) if f["id"] == dia_trabajo["id"])
    assert nuevo["estado"] == "HE"


def test_vacaciones_no_se_editan_dia_a_dia(servicio):
    # Arrange
    guardia_id = servicio.crear_integrante("Rosa Pérez", "PATRULLERO", "A", "DIURNO")
    opcion = servicio.generar_opciones_malla_mensual("A", "DIURNO", HORARIO_DIURNO)[0]
    servicio.asignar_opcion_a_personal(guardia_id, opcion)
    dia_trabajo = filas_con_estado(servicio, guardia_id, "T")[0]

    # Act & Assert
    with pytest.raises(ValueError, match="por fechas"):
        servicio.editar_estado_dia(guardia_id, dia_trabajo["id"], "VAC")


def test_rechaza_edicion_que_infringe_descanso_dominical(servicio):
    # Arrange
    guardia_id = servicio.crear_integrante("Mónica Bustos", "PATRULLERO", "A", "DIURNO")
    opcion = servicio.generar_opciones_malla_mensual("A", "DIURNO", HORARIO_DIURNO)[0]
    servicio.asignar_opcion_a_personal(guardia_id, opcion)
    domingos_libres = [
        f for f in filas_con_estado(servicio, guardia_id, "L") if f["fecha"].weekday() == 6
    ]
    assert len(domingos_libres) >= 2
    assert (ANIO, MES) == servicio.periodo

    # Act & Assert: quitar domingos libres hasta quedar con menos de 2 debe rechazarse
    with pytest.raises(ValueError):
        for fila in domingos_libres:
            servicio.editar_estado_dia(guardia_id, fila["id"], "T")
