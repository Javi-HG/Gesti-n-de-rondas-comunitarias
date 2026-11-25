"""Vacaciones (VAC) y licencias médicas (LM): carga por fechas y bloqueo de asignación a turnos."""
from datetime import date

import pytest

from constantes_reglas import ESTADOS_AUSENCIA, ESTADOS_LIBRES, HORARIOS_DIURNOS
from conftest import ANIO, MES, filas_con_estado

DESDE, HASTA = date(ANIO, MES, 10), date(ANIO, MES, 16)  # 7 días, del martes 10 al lunes 16


def estados_entre(servicio, pid, desde=DESDE, hasta=HASTA):
    return {f["fecha"]: f["estado"] for f in servicio.malla_vista(pid) if desde <= f["fecha"] <= hasta}


class TestCargaDeAusencias:
    @pytest.mark.parametrize("estado", ["VAC", "LM"])
    def test_marca_todos_los_dias_del_rango(self, servicio, plan_ab, estado):
        # Arrange
        pid = plan_ab["ids"]["P0"]
        # Act
        resultado = servicio.aplicar_ausencia(pid, DESDE, HASTA, estado)
        # Assert
        assert resultado["dias"] == 7
        assert resultado["aplicados"] == 7
        assert resultado["sin_malla"] == 0
        assert set(estados_entre(servicio, pid).values()) == {estado}

    def test_no_toca_los_dias_fuera_del_rango(self, servicio, plan_ab):
        # Arrange
        pid = plan_ab["ids"]["P0"]
        antes = estados_entre(servicio, pid, date(ANIO, MES, 1), date(ANIO, MES, 9))
        # Act
        servicio.aplicar_ausencia(pid, DESDE, HASTA, "LM")
        # Assert
        assert estados_entre(servicio, pid, date(ANIO, MES, 1), date(ANIO, MES, 9)) == antes

    def test_no_afecta_a_otras_personas(self, servicio, plan_ab):
        # Arrange
        otro = plan_ab["ids"]["P1"]
        antes = estados_entre(servicio, otro)
        # Act
        servicio.aplicar_ausencia(plan_ab["ids"]["P0"], DESDE, HASTA, "VAC")
        # Assert
        assert estados_entre(servicio, otro) == antes

    def test_los_dias_sin_malla_se_informan_y_no_se_modifican(self, servicio, plan_ab):
        # Arrange: el rango termina en diciembre, mes que aún no está planificado
        pid = plan_ab["ids"]["P0"]
        # Act
        resultado = servicio.aplicar_ausencia(pid, date(ANIO, MES, 28), date(ANIO, 12, 3), "VAC")
        # Assert
        assert resultado["aplicados"] < resultado["dias"]
        assert resultado["sin_malla"] == resultado["dias"] - resultado["aplicados"]

    def test_informa_los_dias_que_quedan_bajo_el_minimo_de_personas(self, servicio, plan_ab):
        # Arrange / Act
        resultado = servicio.aplicar_ausencia(plan_ab["ids"]["P0"], DESDE, HASTA, "LM")
        # Assert: la lista trae (fecha, cantidad) con cantidad menor al mínimo
        for fecha, cantidad in resultado["bajo_minimo"]:
            assert isinstance(fecha, date)
            assert cantidad < 3

    def test_aplicar_dos_veces_no_pierde_el_estado_original(self, servicio, plan_ab):
        # Arrange
        pid = plan_ab["ids"]["P0"]
        original = estados_entre(servicio, pid)
        servicio.aplicar_ausencia(pid, DESDE, HASTA, "VAC")
        # Act: la licencia reemplaza a las vacaciones, y luego se quita
        servicio.aplicar_ausencia(pid, DESDE, HASTA, "LM")
        servicio.quitar_ausencia(pid, DESDE, HASTA)
        # Assert
        assert estados_entre(servicio, pid) == original


class TestValidacionDeAusencias:
    def test_rechaza_estados_que_no_son_ausencias(self, servicio, plan_ab):
        with pytest.raises(ValueError, match="Solo se pueden cargar por fechas"):
            servicio.aplicar_ausencia(plan_ab["ids"]["P0"], DESDE, HASTA, "HE")

    def test_rechaza_un_rango_invertido(self, servicio, plan_ab):
        with pytest.raises(ValueError, match="no puede ser anterior"):
            servicio.aplicar_ausencia(plan_ab["ids"]["P0"], HASTA, DESDE, "VAC")

    def test_rechaza_rangos_de_mas_de_un_anio(self, servicio, plan_ab):
        with pytest.raises(ValueError, match="no puede superar un año"):
            servicio.aplicar_ausencia(plan_ab["ids"]["P0"], date(2026, 1, 1), date(2027, 6, 1), "VAC")

    def test_rechaza_una_persona_inexistente(self, servicio, plan_ab):
        with pytest.raises(ValueError, match="no existe"):
            servicio.aplicar_ausencia(9999, DESDE, HASTA, "VAC")

    def test_rechaza_una_persona_sin_malla_en_esas_fechas(self, servicio, equipo):
        with pytest.raises(ValueError, match="no tiene malla"):
            servicio.aplicar_ausencia(equipo["P0"], DESDE, HASTA, "LM")

    def test_las_ausencias_validas_son_vacaciones_y_licencia_medica(self):
        assert set(ESTADOS_AUSENCIA) == {"VAC", "LM"}

    def test_las_ausencias_cuentan_como_dias_libres_para_el_art_38(self):
        assert {"VAC", "LM"} <= set(ESTADOS_LIBRES)


class TestQuitarAusencia:
    def test_devuelve_cada_dia_a_su_estado_anterior(self, servicio, plan_ab):
        # Arrange
        pid = plan_ab["ids"]["P0"]
        original = estados_entre(servicio, pid)
        servicio.aplicar_ausencia(pid, DESDE, HASTA, "VAC")
        # Act
        quitados = servicio.quitar_ausencia(pid, DESDE, HASTA)
        # Assert
        assert quitados == 7
        assert estados_entre(servicio, pid) == original

    def test_sin_ausencias_no_cambia_nada(self, servicio, plan_ab):
        pid = plan_ab["ids"]["P0"]
        original = estados_entre(servicio, pid)

        assert servicio.quitar_ausencia(pid, DESDE, HASTA) == 0
        assert estados_entre(servicio, pid) == original

    def test_rechaza_un_rango_invertido(self, servicio, plan_ab):
        with pytest.raises(ValueError, match="no puede ser anterior"):
            servicio.quitar_ausencia(plan_ab["ids"]["P0"], HASTA, DESDE)


class TestBloqueoDeAsignacionAturnos:
    @pytest.fixture
    def con_licencia(self, servicio, plan_ab):
        pid = plan_ab["ids"]["P0"]
        servicio.aplicar_ausencia(pid, DESDE, HASTA, "LM")
        return pid

    @pytest.mark.parametrize("nuevo", ["T", "HE", "HEN", "L"])
    def test_un_dia_con_licencia_no_se_puede_cambiar(self, servicio, con_licencia, nuevo):
        # Arrange
        fila = filas_con_estado(servicio, con_licencia, "LM")[0]
        # Act / Assert
        with pytest.raises(ValueError, match="no puede ser asignada a un turno"):
            servicio.editar_estado_dia(con_licencia, fila["id"], nuevo)

    def test_un_dia_con_vacaciones_tambien_esta_bloqueado(self, servicio, plan_ab):
        # Arrange
        pid = plan_ab["ids"]["P0"]
        servicio.aplicar_ausencia(pid, DESDE, HASTA, "VAC")
        fila = filas_con_estado(servicio, pid, "VAC")[0]
        # Act / Assert
        with pytest.raises(ValueError, match="vacaciones"):
            servicio.editar_estado_dia(pid, fila["id"], "T")

    def test_el_dia_bloqueado_conserva_su_ausencia(self, servicio, con_licencia):
        # Arrange
        fila = filas_con_estado(servicio, con_licencia, "LM")[0]
        # Act
        with pytest.raises(ValueError):
            servicio.editar_estado_dia(con_licencia, fila["id"], "T")
        # Assert
        assert next(f for f in servicio.malla_vista(con_licencia) if f["id"] == fila["id"])["estado"] == "LM"

    @pytest.mark.parametrize("ausencia", ["VAC", "LM"])
    def test_no_se_pueden_marcar_ausencias_dia_por_dia(self, servicio, plan_ab, ausencia):
        # Arrange
        pid = plan_ab["ids"]["P0"]
        fila = filas_con_estado(servicio, pid, "L")[0]
        # Act / Assert
        with pytest.raises(ValueError, match="se cargan por fechas"):
            servicio.editar_estado_dia(pid, fila["id"], ausencia)

    def test_no_se_puede_intercambiar_un_dia_de_turno_con_uno_de_licencia(self, servicio, con_licencia):
        # Arrange
        ausente = filas_con_estado(servicio, con_licencia, "LM")[0]
        turno = filas_con_estado(servicio, con_licencia, "T")[0]
        # Act / Assert
        with pytest.raises(ValueError, match="no puede ser asignada a un turno"):
            servicio.intercambiar_dias(con_licencia, turno["id"], ausente["id"])

    def test_quitada_la_ausencia_el_dia_vuelve_a_poder_editarse(self, servicio, con_licencia):
        # Arrange
        servicio.quitar_ausencia(con_licencia, DESDE, HASTA)
        fila = next(f for f in servicio.malla_vista(con_licencia) if f["fecha"] == DESDE)
        # Act
        servicio.editar_estado_dia(con_licencia, fila["id"], "HE")
        # Assert
        assert next(f for f in servicio.malla_vista(con_licencia) if f["id"] == fila["id"])["estado"] == "HE"

    def test_replanificar_el_mes_no_pisa_la_ausencia_con_un_turno(self, servicio, plan_ab, con_licencia):
        # Arrange
        opcion = servicio.generar_opciones_turnos_ab()[0]
        # Act
        servicio.asignar_turnos_ab(opcion, list(HORARIOS_DIURNOS))
        # Assert
        assert set(estados_entre(servicio, con_licencia).values()) == {"LM"}

    def test_el_ausente_no_cuenta_en_las_personas_por_dia(self, servicio, plan_ab):
        # Arrange: un día de la licencia en que la persona trabajaría
        pid = plan_ab["ids"]["P0"]
        dia = next(f["fecha"] for f in servicio.malla_vista(pid) if f["estado"] == "T" and DESDE <= f["fecha"] <= HASTA)
        antes = servicio.personas_por_dia()[dia.day - 1]
        # Act
        servicio.aplicar_ausencia(pid, DESDE, HASTA, "LM")
        # Assert
        assert servicio.personas_por_dia()[dia.day - 1] == antes - 1

    def test_la_licencia_no_afecta_el_descanso_legal_de_la_persona(self, servicio, plan_ab):
        # Arrange
        pid = plan_ab["ids"]["P0"]
        servicio.aplicar_ausencia(pid, DESDE, HASTA, "LM")
        # Act
        estados = {f["fecha"]: f["estado"] for f in servicio.malla_vista(pid)}
        # Assert
        assert servicio.cumple_descanso_calendario("DIURNO", estados, ANIO, MES)
