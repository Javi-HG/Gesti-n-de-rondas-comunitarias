"""Capa de lógica de negocio: reglas 4x3, validación legal y edición."""



from constantes_reglas import (
    CUADRANTES,
    DIAS_SEMANA,
    ESTADOS_CELDA,
    GRUPOS_TURNO,
    HORARIO_NOCTURNO,
    HORARIOS_DIURNOS,
    MIN_DOMINGOS_LIBRES_DIURNO,
    MIN_FINDES_LIBRES_NOCTURNO,
    ROLES_PERSONAL,
)
class ServicioTurnos:
    #Orquesta la planificación operativa de guardias y radio operadores.

    def __init__(self, repositorio):
        # Principio SOLID (D): Inversión de dependencias
        self.repositorio = repositorio

    def crear_integrante(self, nombre: str, apellido: str, rol: str) -> int:
        if not nombre.strip() or not apellido.strip():
            raise ValueError("El nombre y apellido son obligatorios.")
        if rol not in ROLES_PERSONAL:
            raise ValueError(f"Rol inválido. Debe ser uno de: {ROLES_PERSONAL}")
        return self.repositorio.registrar_personal(nombre.strip(), apellido.strip(), rol)

    def generar_opciones_malla_mensual(
        self,
        grupo_turno: str,
        jornada: str,
        horario: str,
        cuadrante: str,
    ) -> list[dict]:
        """
        Genera 3 opciones válidas de malla mensual (4 semanas) bajo sistema 4x3:
        - Diurno: asegura >= 2 domingos libres al mes.
        - Nocturno: asegura >= 2 fines de semana (Sábado y Domingo) libres al mes.
        """
        self._validar_parametros_malla(grupo_turno, jornada, horario, cuadrante)

        # Patrones semanales 4x3 (Lunes a Domingo): 4 días 'T', 3 días 'L'
        patrones_base = {
            "Opcion 1 (Inicio Lunes)": ["T", "T", "T", "T", "L", "L", "L"],
            "Opcion 2 (Inicio Martes)": ["L", "T", "T", "T", "T", "L", "L"],
            "Opcion 3 (Inicio Miércoles)": ["L", "L", "T", "T", "T", "T", "L"],
        }

        opciones_validas = []

        for nombre_opcion, patron_semana in patrones_base.items():
            # Construye las 4 semanas del mes rotando para garantizar descanso legal
            semanas = []
            for num_semana in range(1, 5):
                if jornada == "DIURNO":
                    # Semanas 1 y 3 usa patrón con domingo libre; semanas 2 y 4 alterna
                    dias = (
                        patron_semana
                        if num_semana in (1, 3)
                        else ["L", "L", "L", "T", "T", "T", "T"]
                    )
                else:
                    # Nocturno: asegura sábado y domingo libres en semanas 1, 2 y 3
                    dias = (
                        ["T", "T", "T", "T", "L", "L", "L"]
                        if num_semana in (1, 2, 3)
                        else ["L", "L", "T", "T", "T", "T", "L"]
                    )

                semanas.append(dict(zip(DIAS_SEMANA, dias)))

            if self.cumple_descanso_legal(jornada, semanas):
                opciones_validas.append(
                    {
                        "nombre_opcion": nombre_opcion,
                        "grupo_turno": grupo_turno,
                        "jornada": jornada,
                        "horario": horario,
                        "cuadrante": cuadrante,
                        "semanas": semanas,
                    }
                )

        return opciones_validas

    def cumple_descanso_legal(self, jornada: str, semanas: list[dict]) -> bool:
        """Verifica Art. 38 Código del Trabajo según tipo de jornada."""
        if jornada == "DIURNO":
            domingos_libres = sum(1 for sem in semanas if sem["Domingo"] == "L")
            return domingos_libres >= MIN_DOMINGOS_LIBRES_DIURNO

        findes_libres = sum(
            1 for sem in semanas if sem["Sábado"] == "L" and sem["Domingo"] == "L"
        )
        return findes_libres >= MIN_FINDES_LIBRES_NOCTURNO

    def asignar_opcion_a_personal(
        self, personal_id: int, opcion_seleccionada: dict
    ) -> None:
        """Persiste la opción elegida por el Jefe Operativo en la base de datos."""
        registros = []
        for idx, semana in enumerate(opcion_seleccionada["semanas"], start=1):
            for dia, estado in semana.items():
                registros.append(
                    (
                        personal_id,
                        opcion_seleccionada["grupo_turno"],
                        opcion_seleccionada["jornada"],
                        opcion_seleccionada["horario"],
                        opcion_seleccionada["cuadrante"],
                        dia,
                        idx,
                        estado,
                    )
                )
        self.repositorio.guardar_malla_completa(registros)

    def editar_estado_dia(
        self, personal_id: int, asignacion_id: int, nuevo_estado: str
    ) -> bool:
        """Permite editar una celda (T, L, VAC, HE, HEN) validando descanso legal."""
        if nuevo_estado not in ESTADOS_CELDA:
            raise ValueError(f"Estado inválido. Permitidos: {ESTADOS_CELDA}")

        malla_actual = self.repositorio.obtener_malla_personal(personal_id)
        if not malla_actual:
            raise ValueError("El integrante no tiene turnos asignados.")

        # Simula el cambio antes de guardar para no infringir la ley
        jornada = malla_actual[0]["jornada"]
        semanas_simuladas = {1: {}, 2: {}, 3: {}, 4: {}}
        for fila in malla_actual:
            estado = nuevo_estado if fila["id"] == asignacion_id else fila["estado"]
            semanas_simuladas[fila["semana_mes"]][fila["dia_semana"]] = estado

        if not self.cumple_descanso_legal(jornada, list(semanas_simuladas.values())):
            raise ValueError(
                "Edición rechazada: incumple el descanso dominical/fin de semana legal."
            )

        return self.repositorio.actualizar_celda_turno(asignacion_id, nuevo_estado)

    def _validar_parametros_malla(
        self, grupo_turno: str, jornada: str, horario: str, cuadrante: str
    ) -> None:
        if grupo_turno not in GRUPOS_TURNO:
            raise ValueError("El grupo de turno debe ser 'A' o 'B'.")
        if cuadrante not in CUADRANTES:
            raise ValueError(f"Cuadrante inválido. Opciones: {CUADRANTES}")
        if jornada == "DIURNO" and horario not in HORARIOS_DIURNOS:
            raise ValueError(f"Horario diurno inválido. Opciones: {HORARIOS_DIURNOS}")
        if jornada == "NOCTURNO" and horario != HORARIO_NOCTURNO:
            raise ValueError(f"Horario nocturno debe ser '{HORARIO_NOCTURNO}'.")