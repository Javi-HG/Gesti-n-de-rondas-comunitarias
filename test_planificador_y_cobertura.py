"""Motor de planificación 4x3 (opciones_turnos_ab) y cobertura horaria de 24 horas."""
from datetime import date

import pytest

from cobertura_horaria import (
    HORAS_DIA, cobertura_fechas, cobertura_por_dia, elegir_horarios, horas_turno, parsear_horario, rangos_horas,
)
from constantes_reglas import HORARIO_NOCTURNO, HORARIOS_DIURNOS
from planificador_cobertura import minimo_personas, opciones_turnos_ab
from conftest import ANIO, MES

PERSONAS = [
    (1, "a", "PATRULLERO", "A", "DIURNO"), (2, "b", "PATRULLERO", "B", "DIURNO"),
    (3, "c", "PATRULLERO", "A", "NOCTURNO"), (4, "d", "PATRULLERO", "B", "NOCTURNO"),
]


# ------------------------------------------------------------------------- opciones_turnos_ab
class TestOpcionesTurnosAB:
    def test_devuelve_hasta_la_cantidad_pedida(self):
        # Arrange / Act
        opciones = opciones_turnos_ab(PERSONAS, cantidad=3)
        # Assert
        assert 1 <= len(opciones) <= 3

    def test_cada_opcion_trae_los_campos_documentados(self):
        opcion = opciones_turnos_ab(PERSONAS)[0]

        assert {"nombre_opcion", "seq_a", "seq_b", "avisos", "metricas"} <= set(opcion)
        assert {"huecos", "ambos_turnos", "findes_a", "findes_b"} <= set(opcion["metricas"])

    def test_los_patrones_son_de_28_dias_con_12_libres_y_16_trabajados(self):
        # Arrange
        opciones = opciones_turnos_ab(PERSONAS)
        # Act / Assert: 1 = día libre; el sistema 4x3 deja 12 de cada 28 días libres
        for op in opciones:
            for seq in (op["seq_a"], op["seq_b"]):
                assert len(seq) == 28
                assert sum(seq) == 12
                assert set(seq) <= {0, 1}

    def test_los_bloques_de_descanso_son_de_tres_dias_y_los_de_trabajo_de_tres_a_seis(self):
        # Arrange
        seq = opciones_turnos_ab(PERSONAS)[0]["seq_a"]
        # Act: el patrón es cíclico, se parte donde cambia el valor para no cortar un bloque
        inicio = next(i for i in range(28) if seq[i] != seq[i - 1])
        rotada = seq[inicio:] + seq[:inicio]
        bloques, actual, largo = [], rotada[0], 0
        for v in rotada:
            if v == actual:
                largo += 1
            else:
                bloques.append((actual, largo))
                actual, largo = v, 1
        bloques.append((actual, largo))
        # Assert
        assert all(largo == 3 for v, largo in bloques if v == 1)
        assert all(3 <= largo <= 6 for v, largo in bloques if v == 0)

    def test_las_opciones_son_distintas_entre_si(self):
        opciones = opciones_turnos_ab(PERSONAS)

        pares = {(op["seq_a"], op["seq_b"]) for op in opciones}
        assert len(pares) == len(opciones)
        assert len({op["seq_a"] for op in opciones}) == len(opciones)

    def test_un_turno_cubre_los_dias_que_el_otro_descansa(self):
        # Arrange
        op = opciones_turnos_ab(PERSONAS)[0]
        # Act: días en que ambos turnos descansan a la vez (1 = libre en las dos secuencias)
        sin_nadie = sum(1 for a, b in zip(op["seq_a"], op["seq_b"]) if a and b)
        # Assert: los patrones se complementan, y el motor lo informa como "huecos"
        assert sin_nadie <= 2
        assert op["metricas"]["huecos"] >= 0

    def test_es_determinista_con_la_misma_entrada(self):
        assert opciones_turnos_ab(PERSONAS) == opciones_turnos_ab(PERSONAS)

    def test_exige_al_menos_un_integrante_en_cada_turno(self):
        solo_a = [p for p in PERSONAS if p[3] == "A"]

        with pytest.raises(ValueError, match="al menos un integrante"):
            opciones_turnos_ab(solo_a)

    def test_ignora_personas_con_grupo_distinto_de_a_y_b(self):
        # Arrange
        con_extra = PERSONAS + [(9, "z", "PATRULLERO", "C", "DIURNO")]
        # Act / Assert
        assert opciones_turnos_ab(con_extra) == opciones_turnos_ab(PERSONAS)

    @pytest.mark.parametrize("min_dia, min_noche, esperado", [(2, 2, 8), (1, 1, 4), (3, 1, 8)])
    def test_minimo_de_personas_por_rol(self, min_dia, min_noche, esperado):
        assert minimo_personas(min_dia, min_noche) == esperado


class TestPlanDeTurnosEnElServicio:
    def test_asigna_una_fila_por_dia_del_mes_a_cada_persona(self, servicio, plan_ab):
        # Arrange / Act (el plan ya se asignó en la fixture)
        for pid in plan_ab["ids"].values():
            malla = [f for f in servicio.malla_vista(pid) if f["fecha"].month == MES]
            # Assert
            assert len(malla) == 30

    def test_todo_el_turno_trabaja_junto(self, servicio, plan_ab):
        # Arrange
        ids = plan_ab["ids"]

        def dias_t(nombre):
            return {f["fecha"] for f in servicio.malla_vista(ids[nombre]) if f["estado"] == "T"}
        # Act / Assert: P0 y P4 son del turno A (P0 diurno, P4 nocturno): mismos días de trabajo
        assert dias_t("P0") == dias_t("P4")
        assert dias_t("P1") == dias_t("P5")

    def test_cada_persona_trabaja_unos_16_dias_de_28(self, servicio, plan_ab):
        malla = [f for f in servicio.malla_vista(plan_ab["ids"]["P0"]) if f["fecha"].month == MES]

        trabajados = sum(1 for f in malla if f["estado"] == "T")
        assert 14 <= trabajados <= 19  # 16 por ciclo de 28; un mes de 30 días trae algunos más

    def test_sin_personal_con_turno_no_se_puede_asignar(self, servicio):
        with pytest.raises(ValueError, match="No hay integrantes"):
            servicio.asignar_turnos_ab({"seq_a": (0,) * 28, "seq_b": (0,) * 28}, list(HORARIOS_DIURNOS))

    def test_el_total_de_personas_por_dia_coincide_con_los_turnos_asignados(self, servicio, plan_ab):
        # Arrange
        esperado = [0] * 30
        for pid in plan_ab["ids"].values():
            for f in servicio.malla_vista(pid):
                if f["fecha"].month == MES and f["estado"] == "T":
                    esperado[f["fecha"].day - 1] += 1
        # Act
        real = servicio.personas_por_dia()
        # Assert
        assert real == esperado


# ----------------------------------------------------------------------------- cobertura horaria
class TestHorarios:
    def test_parsear_horario(self):
        assert parsear_horario("07:00 a 18:00") == (7, 18)
        assert parsear_horario(HORARIO_NOCTURNO) == (20, 7)

    def test_turno_diurno_cubre_11_horas_el_mismo_dia(self):
        horas = horas_turno("07:00 a 18:00")

        assert len(horas) == 11
        assert all(desp == 0 for desp, _h in horas)

    def test_turno_nocturno_cruza_la_medianoche(self):
        horas = horas_turno(HORARIO_NOCTURNO)

        assert [h for d, h in horas if d == 0] == [20, 21, 22, 23]
        assert [h for d, h in horas if d == 1] == [0, 1, 2, 3, 4, 5, 6]

    def test_rangos_de_horas_agrupa_las_consecutivas(self):
        assert rangos_horas({0, 1, 2, 3, 4, 5, 6, 18, 19}) == "00:00–07:00, 18:00–20:00"

    def test_rangos_de_horas_vacio(self):
        assert rangos_horas(set()) == ""


class TestCoberturaPorDia:
    def test_el_turno_nocturno_del_ultimo_dia_se_envuelve_al_primero_del_ciclo(self):
        cubiertas = cobertura_por_dia([(27, HORARIO_NOCTURNO)])

        assert cubiertas[27] == {20, 21, 22, 23}
        assert cubiertas[0] == {0, 1, 2, 3, 4, 5, 6}

    def test_dos_diurnos_y_un_nocturno_cubren_las_24_horas(self):
        # Arrange: 07-18 + 09-20 + noche 20-07 cubren todas las horas
        turnos = [(0, "07:00 a 18:00"), (0, "09:00 a 20:00"), (0, HORARIO_NOCTURNO), (-1 % 28, HORARIO_NOCTURNO)]
        # Act
        cubiertas = cobertura_por_dia(turnos)
        # Assert
        assert cubiertas[0] == set(range(HORAS_DIA))

    def test_sin_el_segundo_diurno_quedan_horas_sin_cubrir(self):
        cubiertas = cobertura_por_dia([(0, "07:00 a 18:00"), (0, HORARIO_NOCTURNO), (27, HORARIO_NOCTURNO)])

        assert set(range(HORAS_DIA)) - cubiertas[0] == {18, 19}


class TestElegirHorarios:
    def personas(self):
        return [
            {"id": 1, "grupo": "PATRULLERO", "dias": ["D"] * 28},
            {"id": 2, "grupo": "PATRULLERO", "dias": ["D"] * 28},
            {"id": 3, "grupo": "PATRULLERO", "dias": ["N"] * 28},
        ]

    def test_reparte_dos_diurnos_en_horarios_distintos_para_cubrir_las_24_horas(self):
        # Arrange / Act
        horarios = elegir_horarios(self.personas(), ["07:00 a 18:00", "09:00 a 20:00"])
        # Assert
        assert horarios == {1: "07:00 a 18:00", 2: "09:00 a 20:00"}

    def test_los_nocturnos_no_reciben_horario_diurno(self):
        horarios = elegir_horarios(self.personas(), list(HORARIOS_DIURNOS))

        assert 3 not in horarios


class TestCoberturaPorFecha:
    def test_el_turno_de_la_vispera_cubre_la_madrugada_del_dia_siguiente(self):
        # Arrange
        dias = [date(2026, 11, 30), date(2026, 12, 1)]
        # Act
        cubiertas = cobertura_fechas([(date(2026, 11, 30), HORARIO_NOCTURNO)], dias)
        # Assert
        assert cubiertas == [{20, 21, 22, 23}, {0, 1, 2, 3, 4, 5, 6}]

    def test_ignora_las_fechas_fuera_del_rango_pedido(self):
        cubiertas = cobertura_fechas([(date(2026, 11, 30), HORARIO_NOCTURNO)], [date(2026, 11, 30)])

        assert cubiertas == [{20, 21, 22, 23}]


class TestCoberturaEnElServicio:
    def test_cada_cargo_informa_sus_horas_cubiertas_por_dia(self, servicio, plan_ab):
        # Act
        grupos = servicio.cobertura_horaria()
        patrulleros = next(g for g in grupos if g["nombre"] == "Patrullero")
        # Assert
        assert len(patrulleros["horas"]) == 30
        assert all(0 <= h <= HORAS_DIA for h in patrulleros["horas"])
        assert max(patrulleros["horas"]) == HORAS_DIA

    def test_marca_cuales_horas_faltan(self, servicio, plan_ab):
        grupos = servicio.cobertura_horaria()

        for g in grupos:
            for horas, faltan in zip(g["horas"], g["faltan"]):
                assert horas + len(faltan) == HORAS_DIA

    def test_sin_mallas_no_hay_cobertura_que_avisar(self, servicio, equipo):
        assert servicio.avisos_horarios() == []

    def test_el_mes_elegido_define_cuantos_dias_se_calculan(self, servicio, plan_ab):
        servicio.fijar_periodo(ANIO, 12)

        assert len(servicio.personas_por_dia()) == 31
