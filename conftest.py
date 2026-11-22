"""Fixtures compartidas: base SQLite en memoria, servicio fijado en noviembre de 2026 y un equipo de ejemplo."""
import sqlite3
from datetime import date

import pytest

from capa_datos import RepositorioTurnos
from capa_ley_opciones import ServicioTurnos
from constantes_reglas import HORARIOS_DIURNOS

ANIO, MES = 2026, 11  # noviembre de 2026: parte en domingo y tiene 5 domingos (1, 8, 15, 22 y 29)


@pytest.fixture
def repo():
    return RepositorioTurnos(sqlite3.connect(":memory:"))


@pytest.fixture
def servicio(repo):
    srv = ServicioTurnos(repo)
    srv.fijar_periodo(ANIO, MES)
    return srv


@pytest.fixture
def equipo(servicio):
    """8 patrulleros sin plan: turno A y B, mitad diurnos y mitad nocturnos. Devuelve {nombre: id}."""
    ids = {}
    for i in range(8):
        grupo = "AB"[i % 2]
        jornada = "DIURNO" if i % 4 < 2 else "NOCTURNO"
        ids[f"P{i}"] = servicio.crear_integrante(f"P{i}", "PATRULLERO", grupo, jornada)
    return ids


@pytest.fixture
def plan_ab(servicio, equipo):
    """El mismo equipo con el plan de turnos A/B de la primera opción ya asignado a noviembre."""
    opcion = servicio.generar_opciones_turnos_ab()[0]
    servicio.asignar_turnos_ab(opcion, list(HORARIOS_DIURNOS))
    return {"ids": equipo, "opcion": opcion}


def filas_con_estado(servicio, personal_id, estado, mes=MES):
    """Filas de la malla de la persona, dentro del mes, que tienen el estado indicado."""
    return [
        f for f in servicio.malla_vista(personal_id)
        if f["estado"] == estado and f["fecha"].month == mes
    ]


def primer_dia_de_trabajo(servicio, personal_id, desde=date(ANIO, MES, 9)):
    """Primera fecha de turno (T) de la persona a partir de `desde`."""
    return next(f["fecha"] for f in servicio.malla_vista(personal_id)
                if f["estado"] == "T" and f["fecha"] >= desde)
