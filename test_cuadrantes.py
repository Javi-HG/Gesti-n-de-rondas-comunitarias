"""Cuadrantes (6 + Feria): Feria solo para bicicletas, motos sin cuadrante, al menos un Móvil por cuadrante."""
import pytest

from constantes_reglas import (
    CUADRANTES, DESTINOS_SERVICIO, FERIA, MIN_MOVILES_POR_CUADRANTE, MIN_POR_TURNO_MODALIDAD,
)


def patrullero(servicio, nombre, modalidades, cuadrante=None, grupo="A", jornada="DIURNO"):
    return servicio.crear_integrante(nombre, "PATRULLERO", grupo, jornada, cuadrante, modalidades)


def cuadrante_de(repo, pid):
    return repo.obtener_persona(pid)["cuadrante"]


class TestConstantes:
    def test_hay_seis_cuadrantes_numerados(self):
        assert CUADRANTES == tuple(f"Cuadrante {n}" for n in range(1, 7))

    def test_los_destinos_son_los_seis_cuadrantes_mas_la_feria(self):
        assert DESTINOS_SERVICIO == CUADRANTES + (FERIA,)
        assert len(DESTINOS_SERVICIO) == 7

    def test_cada_cuadrante_necesita_al_menos_un_movil(self):
        assert MIN_MOVILES_POR_CUADRANTE == 1


class TestAsignarCuadrante:
    @pytest.mark.parametrize("cuadrante", CUADRANTES)
    def test_un_movil_puede_ir_a_cualquiera_de_los_seis_cuadrantes(self, servicio, repo, cuadrante):
        # Arrange
        pid = patrullero(servicio, "Movil", ["Móvil"])
        # Act
        asignados = servicio.asignar_cuadrante([pid], cuadrante)
        # Assert
        assert asignados == 1
        assert cuadrante_de(repo, pid) == cuadrante

    def test_la_feria_se_asigna_a_una_bicicleta(self, servicio, repo):
        pid = patrullero(servicio, "Bici", ["Bicicleta"])

        servicio.asignar_cuadrante([pid], FERIA)

        assert cuadrante_de(repo, pid) == FERIA

    def test_una_bicicleta_tambien_puede_ir_a_un_cuadrante(self, servicio, repo):
        pid = patrullero(servicio, "Bici", ["Bicicleta"])

        servicio.asignar_cuadrante([pid], "Cuadrante 3")

        assert cuadrante_de(repo, pid) == "Cuadrante 3"

    @pytest.mark.parametrize("modalidades", [["Móvil"], ["Infantería"], ["Moto", "Móvil"], []])
    def test_la_feria_se_rechaza_si_no_usa_bicicleta(self, servicio, repo, modalidades):
        # Arrange
        pid = patrullero(servicio, "Pie", modalidades)
        # Act / Assert
        with pytest.raises(ValueError, match="Feria solo se asigna a quienes usan bicicleta"):
            servicio.asignar_cuadrante([pid], FERIA)
        assert cuadrante_de(repo, pid) is None

    def test_las_motos_no_llevan_cuadrante(self, servicio, repo):
        pid = patrullero(servicio, "Moto", ["Moto"])

        with pytest.raises(ValueError, match="motos no tienen cuadrante"):
            servicio.asignar_cuadrante([pid], "Cuadrante 1")
        assert cuadrante_de(repo, pid) is None

    def test_moto_con_otra_modalidad_si_puede_tener_cuadrante(self, servicio, repo):
        pid = patrullero(servicio, "Mixto", ["Moto", "Móvil"])

        servicio.asignar_cuadrante([pid], "Cuadrante 2")

        assert cuadrante_de(repo, pid) == "Cuadrante 2"

    def test_un_destino_inexistente_se_rechaza(self, servicio):
        pid = patrullero(servicio, "Movil", ["Móvil"])

        with pytest.raises(ValueError, match="Destino inválido"):
            servicio.asignar_cuadrante([pid], "Cuadrante 7")

    def test_sin_integrantes_se_rechaza(self, servicio):
        with pytest.raises(ValueError, match="al menos un integrante"):
            servicio.asignar_cuadrante([], "Cuadrante 1")

    def test_si_uno_de_varios_no_cumple_no_se_cambia_a_nadie(self, servicio, repo):
        # Arrange
        movil = patrullero(servicio, "Movil", ["Móvil"])
        moto = patrullero(servicio, "Moto", ["Moto"])
        # Act
        with pytest.raises(ValueError, match="Moto"):
            servicio.asignar_cuadrante([movil, moto], "Cuadrante 4")
        # Assert: valida a todos antes de cambiar a alguien
        assert cuadrante_de(repo, movil) is None

    def test_quitar_el_cuadrante_con_none(self, servicio, repo):
        pid = patrullero(servicio, "Movil", ["Móvil"], "Cuadrante 5")

        servicio.asignar_cuadrante([pid], None)

        assert cuadrante_de(repo, pid) is None


class TestReglasAlCrearOEditar:
    def test_crear_una_moto_con_cuadrante_se_rechaza(self, servicio):
        with pytest.raises(ValueError, match="motos no tienen cuadrante"):
            patrullero(servicio, "Moto", ["Moto"], "Cuadrante 1")

    def test_crear_con_feria_sin_bicicleta_se_rechaza(self, servicio):
        with pytest.raises(ValueError, match="Feria"):
            patrullero(servicio, "Movil", ["Móvil"], FERIA)

    def test_crear_con_un_cuadrante_inexistente_se_rechaza(self, servicio):
        with pytest.raises(ValueError, match="Destino inválido"):
            patrullero(servicio, "Movil", ["Móvil"], "Cuadrante 9")

    def test_un_radio_operador_no_puede_ir_a_la_feria(self, servicio):
        with pytest.raises(ValueError, match="Feria"):
            servicio.crear_integrante("Radio", "RADIO_OPERADOR", "A", "DIURNO", FERIA)

    def test_solo_los_patrulleros_tienen_modalidad(self, servicio):
        with pytest.raises(ValueError, match="Solo los patrulleros"):
            servicio.crear_integrante("Radio", "RADIO_OPERADOR", "A", "DIURNO", None, ["Móvil"])

    def test_pasar_a_solo_moto_le_quita_el_cuadrante(self, servicio, repo):
        # Arrange
        pid = patrullero(servicio, "Mixto", ["Móvil", "Moto"], "Cuadrante 1")
        # Act
        servicio.asignar_modalidades([pid], ["Moto"])
        # Assert
        assert cuadrante_de(repo, pid) is None

    def test_dejar_la_bicicleta_le_quita_la_feria(self, servicio, repo):
        pid = patrullero(servicio, "Bici", ["Bicicleta"], FERIA)

        servicio.quitar_modalidad([pid], "Bicicleta")

        assert cuadrante_de(repo, pid) is None

    def test_editar_a_una_moto_con_cuadrante_se_rechaza_y_no_guarda_nada(self, servicio, repo):
        # Arrange
        pid = patrullero(servicio, "Movil", ["Móvil"], "Cuadrante 1")
        # Act
        with pytest.raises(ValueError, match="motos no tienen cuadrante"):
            servicio.editar_integrante(pid, "Cambiado", "PATRULLERO", "A", "DIURNO", "Cuadrante 1", ["Moto"])
        # Assert
        assert repo.obtener_persona(pid)["nombre"] == "Movil"

    def test_editar_el_cargo_a_no_patrullero_con_modalidades_se_rechaza(self, servicio):
        pid = patrullero(servicio, "Movil", ["Móvil"])

        with pytest.raises(ValueError, match="Solo los patrulleros"):
            servicio.editar_integrante(pid, "Movil", "SUPERVISOR", "A", "DIURNO", None, ["Móvil"])


class TestRepartoAutomatico:
    @pytest.fixture
    def plantilla(self, servicio):
        """24 patrulleros sin modalidad ni cuadrante, 6 por cada combinación turno × jornada."""
        for i in range(24):
            patrullero(servicio, f"P{i}", [], None, "AB"[i % 2], "DIURNO" if i % 4 < 2 else "NOCTURNO")

    def test_cada_cuadrante_queda_con_al_menos_un_movil(self, servicio, plantilla):
        # Arrange
        servicio.repartir_modalidades_auto()
        # Act
        servicio.repartir_cuadrantes_auto()
        resumen = servicio.resumen_cuadrantes()
        # Assert
        assert resumen["faltan_movil"] == []
        for nombre, datos in resumen["cuadrantes"].items():
            if nombre in CUADRANTES:
                assert datos["por_modalidad"]["Móvil"] >= MIN_MOVILES_POR_CUADRANTE

    def test_ninguna_moto_queda_con_cuadrante(self, servicio, repo, plantilla):
        # Arrange
        servicio.repartir_modalidades_auto()
        servicio.repartir_cuadrantes_auto()
        # Act
        mods = servicio.obtener_modalidades()
        solo_moto = [p for p in servicio.listar_personal() if set(mods.get(p["id"], [])) == {"Moto"}]
        # Assert
        assert solo_moto
        assert all(p["cuadrante"] is None for p in solo_moto)

    def test_la_feria_solo_la_tienen_quienes_usan_bicicleta(self, servicio, plantilla):
        servicio.repartir_modalidades_auto()
        servicio.repartir_cuadrantes_auto()

        mods = servicio.obtener_modalidades()
        en_feria = [p for p in servicio.listar_personal() if p["cuadrante"] == FERIA]
        assert all("Bicicleta" in mods[p["id"]] for p in en_feria)

    def test_el_reparto_de_modalidades_deja_dos_motos_y_dos_bicicletas_por_turno(self, servicio, plantilla):
        # Arrange / Act
        servicio.repartir_modalidades_auto()
        resumen = servicio.resumen_turnos_modalidad()
        # Assert
        assert len(resumen) == 4  # turno A/B × diurno/nocturno
        for fila in resumen:
            assert fila["cumple"]
            for modalidad, minimo in MIN_POR_TURNO_MODALIDAD.items():
                assert fila[modalidad] >= minimo

    def test_el_minimo_por_turno_es_dos_motos_y_dos_bicicletas(self):
        assert MIN_POR_TURNO_MODALIDAD == {"Moto": 2, "Bicicleta": 2}

    def test_un_turno_con_una_sola_moto_no_cumple(self, servicio):
        # Arrange
        patrullero(servicio, "M1", ["Moto"])
        patrullero(servicio, "B1", ["Bicicleta"])
        patrullero(servicio, "B2", ["Bicicleta"])
        # Act
        fila = servicio.resumen_turnos_modalidad()[0]
        # Assert
        assert (fila["Moto"], fila["Bicicleta"], fila["cumple"]) == (1, 2, False)


class TestJefeDeTurno:
    def test_se_asigna_a_mano_a_un_movil_y_a_un_cuadrante(self, servicio, repo):
        # Arrange
        movil = patrullero(servicio, "Movil", ["Móvil"])
        jefe = servicio.crear_integrante("Jefa", "JEFE_TURNO", "A", "DIURNO")
        # Act
        servicio.asignar_jefe_turno(jefe, movil, "Cuadrante 2")
        # Assert
        persona = repo.obtener_persona(jefe)
        assert (persona["movil_id"], persona["cuadrante"]) == (movil, "Cuadrante 2")

    def test_nunca_se_asigna_cuadrante_automaticamente(self, servicio, repo):
        # Arrange
        patrullero(servicio, "Movil", ["Móvil"])
        jefe = servicio.crear_integrante("Jefa", "JEFE_TURNO", "A", "DIURNO")
        # Act
        servicio.repartir_cuadrantes_auto()
        # Assert
        assert cuadrante_de(repo, jefe) is None

    def test_el_movil_debe_ser_un_patrullero_con_modalidad_movil(self, servicio):
        # Arrange
        moto = patrullero(servicio, "Moto", ["Moto"])
        jefe = servicio.crear_integrante("Jefa", "JEFE_TURNO", "A", "DIURNO")
        # Act / Assert
        with pytest.raises(ValueError, match="modalidad Móvil"):
            servicio.asignar_jefe_turno(jefe, moto, None)

    def test_solo_un_jefe_de_turno_puede_recibir_la_asignacion(self, servicio):
        pid = patrullero(servicio, "Movil", ["Móvil"])

        with pytest.raises(ValueError, match="Jefe de turno"):
            servicio.asignar_jefe_turno(pid, None, "Cuadrante 1")

    def test_el_jefe_no_puede_ir_a_la_feria(self, servicio):
        jefe = servicio.crear_integrante("Jefa", "JEFE_TURNO", "A", "DIURNO")

        with pytest.raises(ValueError, match="Feria"):
            servicio.asignar_jefe_turno(jefe, None, FERIA)

    def test_si_el_patrullero_deja_de_ser_movil_el_jefe_pierde_el_movil(self, servicio, repo):
        # Arrange
        movil = patrullero(servicio, "Movil", ["Móvil"])
        jefe = servicio.crear_integrante("Jefa", "JEFE_TURNO", "A", "DIURNO")
        servicio.asignar_jefe_turno(jefe, movil, None)
        # Act
        servicio.asignar_modalidades([movil], ["Infantería"])
        # Assert
        assert repo.obtener_persona(jefe)["movil_id"] is None
