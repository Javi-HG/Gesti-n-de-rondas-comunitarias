"""Art. 38 del Código del Trabajo: domingos libres (diurno) y fines de semana libres (nocturno)."""
from datetime import date, timedelta

import pytest

from constantes_reglas import MIN_DOMINGOS_LIBRES_DIURNO, MIN_FINDES_LIBRES_NOCTURNO
from planificador_cobertura import (
    DIURNO, ESTADO_LIBRE, ESTADO_TURNO, NOCTURNO, opciones_turnos_ab, validar_art38,
)
from capa_ley_opciones import ServicioTurnos
from conftest import filas_con_estado

DOMINGO = 6
SABADO = 5


def grilla(jornada, libres):
    """Grilla de 28 días (lunes a domingo × 4): turno en todos los días salvo los índices `libres`."""
    return [(ESTADO_LIBRE if k in libres else ESTADO_TURNO, jornada) for k in range(28)]


def domingos(*semanas):
    return {s * 7 + 6 for s in semanas}


def findes(*semanas):
    return {s * 7 + d for s in semanas for d in (5, 6)}


# --------------------------------------------------------------------- validar_art38 (motor 28 días)
class TestValidarArt38:
    def test_diurno_con_dos_domingos_libres_cumple(self):
        # Arrange
        g = grilla(DIURNO, domingos(0, 2))
        # Act
        resultado = validar_art38(g)
        # Assert
        assert resultado is True

    def test_diurno_con_un_domingo_libre_no_cumple(self):
        g = grilla(DIURNO, domingos(1))

        assert validar_art38(g) is False

    def test_diurno_sin_domingos_libres_no_cumple(self):
        g = grilla(DIURNO, {0, 1, 2})  # lunes a miércoles libres, ningún domingo

        assert validar_art38(g) is False

    def test_nocturno_con_dos_findes_completos_cumple(self):
        g = grilla(NOCTURNO, findes(0, 3))

        assert validar_art38(g) is True

    def test_nocturno_con_un_solo_finde_completo_no_cumple(self):
        g = grilla(NOCTURNO, findes(2))

        assert validar_art38(g) is False

    def test_nocturno_con_domingos_libres_pero_sabados_trabajados_no_cumple(self):
        # Arrange: 4 domingos libres, pero ningún sábado: no hay fin de semana completo
        g = grilla(NOCTURNO, domingos(0, 1, 2, 3))
        # Act / Assert
        assert validar_art38(g) is False

    def test_el_minimo_exigido_es_dos(self):
        assert MIN_DOMINGOS_LIBRES_DIURNO == 2
        assert MIN_FINDES_LIBRES_NOCTURNO == 2

    def test_si_hay_algun_turno_nocturno_rige_la_regla_de_fines_de_semana(self):
        # Arrange: cumple los domingos del diurno, pero hay un día nocturno y faltan findes
        g = grilla(DIURNO, domingos(0, 1))
        g[10] = (ESTADO_TURNO, NOCTURNO)
        # Act / Assert
        assert validar_art38(g) is False

    @pytest.mark.parametrize("cantidad", [1, 2, 4])
    def test_todas_las_opciones_del_motor_cumplen_el_articulo(self, cantidad):
        # Arrange
        personas = [(1, "a", "PATRULLERO", "A", "DIURNO"), (2, "b", "PATRULLERO", "B", "DIURNO"),
                    (3, "c", "PATRULLERO", "A", "NOCTURNO"), (4, "d", "PATRULLERO", "B", "NOCTURNO")]
        # Act
        opciones = opciones_turnos_ab(personas, cantidad)
        # Assert
        assert opciones
        for op in opciones:
            for seq in (op["seq_a"], op["seq_b"]):  # en la secuencia, 1 = día libre
                g = [(ESTADO_LIBRE if v else ESTADO_TURNO, NOCTURNO) for v in seq]
                assert validar_art38(g)


# --------------------------------------------------------------- cumple_descanso_calendario (mes real)
NOV_DOMINGOS = [date(2026, 11, d) for d in (1, 8, 15, 22, 29)]


def estados_mes(libres):
    """Estados de todo noviembre de 2026 (y el sábado 31 de octubre): turno salvo los días libres."""
    dias = [date(2026, 10, 31)] + [date(2026, 11, d) for d in range(1, 31)]
    return {d: ("L" if d in libres else "T") for d in dias}


class TestCumpleDescansoCalendario:
    def test_diurno_con_dos_domingos_libres_del_mes_cumple(self):
        estados = estados_mes({NOV_DOMINGOS[0], NOV_DOMINGOS[3]})

        assert ServicioTurnos.cumple_descanso_calendario("DIURNO", estados, 2026, 11) is True

    def test_diurno_con_un_domingo_libre_no_cumple(self):
        estados = estados_mes({NOV_DOMINGOS[2]})

        assert ServicioTurnos.cumple_descanso_calendario("DIURNO", estados, 2026, 11) is False

    def test_mes_de_cuatro_domingos_exige_los_mismos_dos(self):
        # Arrange: febrero de 2026 tiene 4 domingos (1, 8, 15 y 22)
        dias = [date(2026, 2, d) for d in range(1, 29)]
        estados = {d: ("L" if d.day in (8, 22) else "T") for d in dias}
        # Act / Assert
        assert ServicioTurnos.cumple_descanso_calendario("DIURNO", estados, 2026, 2) is True

    def test_nocturno_cuenta_el_fin_de_semana_completo_sabado_y_domingo(self):
        libres = {date(2026, 11, 7), date(2026, 11, 8), date(2026, 11, 14), date(2026, 11, 15)}

        assert ServicioTurnos.cumple_descanso_calendario("NOCTURNO", estados_mes(libres), 2026, 11) is True

    def test_nocturno_con_domingo_libre_y_sabado_trabajado_no_cuenta(self):
        # Arrange: 2 domingos libres, pero sus sábados se trabajan
        libres = {NOV_DOMINGOS[1], NOV_DOMINGOS[2]}
        # Act
        resultado = ServicioTurnos.cumple_descanso_calendario("NOCTURNO", estados_mes(libres), 2026, 11)
        # Assert
        assert resultado is False

    def test_el_primer_domingo_necesita_el_sabado_del_mes_anterior(self):
        # Arrange: el domingo 1 de nov solo forma fin de semana si el sábado 31 de oct también es libre
        solo_domingo = estados_mes({NOV_DOMINGOS[0], date(2026, 11, 7), date(2026, 11, 8)})
        con_sabado = {**solo_domingo, date(2026, 10, 31): "L"}
        # Act / Assert
        assert ServicioTurnos.cumple_descanso_calendario("NOCTURNO", solo_domingo, 2026, 11) is False
        assert ServicioTurnos.cumple_descanso_calendario("NOCTURNO", con_sabado, 2026, 11) is True

    @pytest.mark.parametrize("estado_libre", ["L", "VAC", "LM"])
    def test_vacaciones_y_licencia_cuentan_como_dia_libre(self, estado_libre):
        # Arrange
        estados = {d: "T" for d in (date(2026, 11, k) for k in range(1, 31))}
        estados[NOV_DOMINGOS[0]] = estado_libre
        estados[NOV_DOMINGOS[1]] = estado_libre
        # Act / Assert
        assert ServicioTurnos.cumple_descanso_calendario("DIURNO", estados, 2026, 11) is True

    def test_horas_extra_no_cuentan_como_descanso(self):
        estados = {d: "T" for d in (date(2026, 11, k) for k in range(1, 31))}
        estados[NOV_DOMINGOS[0]] = "HE"
        estados[NOV_DOMINGOS[1]] = "HEN"

        assert ServicioTurnos.cumple_descanso_calendario("DIURNO", estados, 2026, 11) is False

    def test_fechas_sin_dato_no_se_consideran_libres(self):
        assert ServicioTurnos.cumple_descanso_calendario("DIURNO", {}, 2026, 11) is False


# ------------------------------------------------- integración: el servicio rechaza ediciones ilegales
class TestEdicionConArt38:
    def test_no_permite_dejar_a_un_diurno_con_menos_de_dos_domingos_libres(self, servicio, plan_ab):
        # Arrange
        pid = plan_ab["ids"]["P0"]  # diurno
        libres = [f for f in filas_con_estado(servicio, pid, "L") if f["fecha"].weekday() == DOMINGO]
        permitidos = len(libres) - MIN_DOMINGOS_LIBRES_DIURNO
        for fila in libres[:permitidos]:
            servicio.editar_estado_dia(pid, fila["id"], "T")  # hasta el límite, todavía legal
        # Act / Assert
        with pytest.raises(ValueError, match="Art. 38"):
            servicio.editar_estado_dia(pid, libres[permitidos]["id"], "T")

    def test_el_dia_rechazado_no_se_modifica(self, servicio, plan_ab):
        # Arrange
        pid = plan_ab["ids"]["P0"]
        libres = [f for f in filas_con_estado(servicio, pid, "L") if f["fecha"].weekday() == DOMINGO]
        for fila in libres[:len(libres) - 2]:
            servicio.editar_estado_dia(pid, fila["id"], "T")
        objetivo = libres[len(libres) - 2]
        # Act
        with pytest.raises(ValueError):
            servicio.editar_estado_dia(pid, objetivo["id"], "T")
        # Assert
        despues = next(f for f in servicio.malla_vista(pid) if f["id"] == objetivo["id"])
        assert despues["estado"] == "L"

    def test_un_nocturno_necesita_dos_findes_completos(self, servicio, plan_ab):
        # Arrange
        pid = plan_ab["ids"]["P2"]  # nocturno
        malla = {f["fecha"]: f for f in servicio.malla_vista(pid)}
        findes_libres = [
            d for d, f in malla.items()
            if d.month == 11 and d.weekday() == DOMINGO and f["estado"] == "L"
            and malla.get(d - timedelta(days=1), {}).get("estado") == "L"
        ]
        assert len(findes_libres) >= MIN_FINDES_LIBRES_NOCTURNO
        sobrantes = len(findes_libres) - MIN_FINDES_LIBRES_NOCTURNO
        for d in findes_libres[:sobrantes]:
            servicio.editar_estado_dia(pid, malla[d]["id"], "T")
        # Act / Assert
        with pytest.raises(ValueError, match="Art. 38"):
            servicio.editar_estado_dia(pid, malla[findes_libres[sobrantes]]["id"], "T")

    def test_estado_inexistente_es_rechazado(self, servicio, plan_ab):
        pid = plan_ab["ids"]["P0"]
        fila = servicio.malla_vista(pid)[0]

        with pytest.raises(ValueError, match="Estado inválido"):
            servicio.editar_estado_dia(pid, fila["id"], "XYZ")

    def test_persona_sin_malla_no_puede_editarse(self, servicio, equipo):
        with pytest.raises(ValueError, match="no tiene turnos"):
            servicio.editar_estado_dia(equipo["P0"], 1, "T")
