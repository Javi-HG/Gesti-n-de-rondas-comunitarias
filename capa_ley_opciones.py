"""Capa de lógica de negocio: reglas 4x3, validación legal y edición."""

from constantes_reglas import (
    CUADRANTES,
    DIAS_SEMANA,
    ESTADOS_CELDA,
    ESTADOS_LIBRES,
    GRUPOS_TURNO,
    HORARIO_NOCTURNO,
    HORARIOS_DIURNOS,
    JORNADAS,
    MIN_DOMINGOS_LIBRES_DIURNO,
    MIN_FINDES_LIBRES_NOCTURNO,
    MODALIDADES,
    ROL_PATRULLERO,
    ROLES_PERSONAL,
)
from planificador_cobertura import (
    generar_opciones_equipo,
    grilla_a_semanas,
    opciones_individuales,
    opciones_turnos_ab,
    resumen_patron,
    seq_a_semanas,
)


class ServicioTurnos:
    """Orquesta la planificación operativa de patrulleros, radio operadores y supervisores."""

    def __init__(self, repositorio):
        # Principio SOLID (D): Inversión de dependencias
        self.repositorio = repositorio

    # ------------------------------------------------------------------ personal
    def crear_integrante(
        self,
        nombre: str,
        rol: str,
        grupo_turno: str,
        jornada: str,
        cuadrante: str | None = None,
        modalidades: list[str] | None = None,
    ) -> int:
        """Registra al integrante. Cuadrante y modalidades (solo patrulleros) son propios de cada persona."""
        if not nombre.strip():
            raise ValueError("El nombre es obligatorio.")
        if rol not in ROLES_PERSONAL:
            raise ValueError(f"Rol inválido. Debe ser uno de: {ROLES_PERSONAL}")
        self._validar_perfil_turno(grupo_turno, jornada)
        if cuadrante and cuadrante not in CUADRANTES:
            raise ValueError(f"Cuadrante inválido. Opciones: {CUADRANTES}")
        modalidades = self._normalizar_modalidades(modalidades)
        if modalidades and rol != ROL_PATRULLERO:
            raise ValueError("Solo los patrulleros pueden tener modalidad.")
        pid = self.repositorio.registrar_personal(
            nombre.strip(), rol, grupo_turno, jornada, cuadrante or None
        )
        if modalidades:
            self.repositorio.agregar_modalidades({pid: modalidades})
        return pid

    def actualizar_perfil_turno(self, personal_id: int, grupo_turno: str, jornada: str) -> None:
        self._validar_perfil_turno(grupo_turno, jornada)
        self.repositorio.actualizar_perfil_turno(personal_id, grupo_turno, jornada)

    @staticmethod
    def _validar_perfil_turno(grupo_turno: str, jornada: str) -> None:
        if grupo_turno not in GRUPOS_TURNO:
            raise ValueError(f"El turno debe ser uno de: {GRUPOS_TURNO}")
        if jornada not in JORNADAS:
            raise ValueError(f"La jornada debe ser una de: {JORNADAS}")

    def listar_personal(self) -> list[dict]:
        return self.repositorio.listar_personal()

    def eliminar_integrante(self, personal_id: int) -> None:
        """Elimina al integrante con su malla y modalidad."""
        if not any(p["id"] == personal_id for p in self.repositorio.listar_personal()):
            raise ValueError("El integrante no existe.")
        self.repositorio.eliminar_personal(personal_id)

    # ------------------------------------------------------------------ modalidad
    def _ids_patrulleros(self) -> set[int]:
        return {p["id"] for p in self.repositorio.listar_personal() if p["rol"] == ROL_PATRULLERO}

    @staticmethod
    def _normalizar_modalidades(modalidades) -> list[str]:
        """Acepta None, un texto o una lista; devuelve lista sin repetidos y validada."""
        if not modalidades:
            return []
        if isinstance(modalidades, str):
            modalidades = [modalidades]
        for m in modalidades:
            if m not in MODALIDADES:
                raise ValueError(f"Modalidad inválida. Opciones: {MODALIDADES}")
        return [m for m in MODALIDADES if m in set(modalidades)]

    def _validar_patrulleros(self, personal_ids: list[int]) -> None:
        if not personal_ids:
            raise ValueError("Seleccione al menos un patrullero.")
        if not set(personal_ids) <= self._ids_patrulleros():
            raise ValueError("Solo los patrulleros pueden tener modalidad.")

    def asignar_modalidades(self, personal_ids: list[int], modalidades) -> None:
        """Deja a cada patrullero con EXACTAMENTE las modalidades indicadas (vacío = ninguna)."""
        lista = self._normalizar_modalidades(modalidades)
        self._validar_patrulleros(personal_ids)
        self.repositorio.reemplazar_modalidades({pid: lista for pid in personal_ids})

    def agregar_modalidad(self, personal_ids: list[int], modalidad: str) -> None:
        """Suma una modalidad sin quitar las que ya usa cada patrullero."""
        lista = self._normalizar_modalidades([modalidad])
        self._validar_patrulleros(personal_ids)
        self.repositorio.agregar_modalidades({pid: lista for pid in personal_ids})

    def quitar_modalidad(self, personal_ids: list[int], modalidad: str) -> None:
        self._normalizar_modalidades([modalidad])
        self._validar_patrulleros(personal_ids)
        self.repositorio.quitar_modalidad(personal_ids, modalidad)

    def repartir_modalidades_auto(self, personal_ids: list[int] | None = None) -> int:
        """Reparte de forma pareja UNA modalidad a los patrulleros que no tienen ninguna.
        Quienes ya tienen modalidades no se tocan. Devuelve cuántos recibieron una."""
        patrulleros = self._ids_patrulleros()
        objetivo = [pid for pid in (personal_ids if personal_ids is not None else sorted(patrulleros))
                    if pid in patrulleros]
        actuales = self.repositorio.obtener_modalidades()
        conteo = {m: 0 for m in MODALIDADES}
        for pid in patrulleros:
            for m in actuales.get(pid, []):
                conteo[m] += 1
        nuevas = {}
        for pid in objetivo:
            if actuales.get(pid):
                continue
            m = min(MODALIDADES, key=lambda x: (conteo[x], MODALIDADES.index(x)))
            conteo[m] += 1
            nuevas[pid] = [m]
        if nuevas:
            self.repositorio.agregar_modalidades(nuevas)
        return len(nuevas)

    def obtener_modalidades(self) -> dict[int, list[str]]:
        return self.repositorio.obtener_modalidades()

    def obtener_mallas_equipo(self) -> list[dict]:
        """Persona + malla mensual de todo el equipo (para la vista de equipo)."""
        modalidades = self.repositorio.obtener_modalidades()
        return [
            {
                "persona": p,
                "malla": self.repositorio.obtener_malla_personal(p["id"]),
                "modalidades": modalidades.get(p["id"], []),
            }
            for p in self.repositorio.listar_personal()
        ]

    # ------------------------------------------------------------ malla individual
    def generar_opciones_malla_mensual(
        self,
        grupo_turno: str,
        jornada: str,
        horario: str,
        cantidad: int = 5,
    ) -> list[dict]:
        """
        Genera opciones válidas de malla mensual (4 semanas) bajo sistema 4x3:
        - Diurno: asegura >= 2 domingos libres al mes.
        - Nocturno: asegura >= 2 fines de semana (Sábado y Domingo) libres al mes.
        Las opciones son distintas entre sí: primero los patrones 4x3 puros y luego
        variantes con ajuste de días de descanso.
        """
        self._validar_parametros_malla(grupo_turno, jornada, horario)

        opciones_validas = []
        for patron in opciones_individuales(jornada, cantidad):
            semanas = seq_a_semanas(patron)
            if self.cumple_descanso_legal(jornada, semanas):
                opciones_validas.append(
                    {
                        "nombre_opcion": f"Opción {len(opciones_validas) + 1} · {resumen_patron(patron)}",
                        "grupo_turno": grupo_turno,
                        "jornada": jornada,
                        "horario": horario,
                        "semanas": semanas,
                    }
                )
        return opciones_validas

    def cumple_descanso_legal(self, jornada: str, semanas: list[dict]) -> bool:
        """Verifica Art. 38 Código del Trabajo según tipo de jornada.

        Cuentan como día libre los estados L (libre) y VAC (vacaciones).
        """
        if jornada == "DIURNO":
            domingos_libres = sum(1 for sem in semanas if sem["Domingo"] in ESTADOS_LIBRES)
            return domingos_libres >= MIN_DOMINGOS_LIBRES_DIURNO

        findes_libres = sum(
            1
            for sem in semanas
            if sem["Sábado"] in ESTADOS_LIBRES and sem["Domingo"] in ESTADOS_LIBRES
        )
        return findes_libres >= MIN_FINDES_LIBRES_NOCTURNO

    def asignar_opcion_a_personal(
        self, personal_id: int, opcion_seleccionada: dict
    ) -> None:
        """Persiste la opción elegida, reemplazando la malla anterior de la persona.
        El cuadrante y las modalidades son propios de la persona y no se modifican."""
        persona = self.repositorio.obtener_persona(personal_id)
        if persona is None:
            raise ValueError("El integrante no existe.")
        cuadrante = persona.get("cuadrante") or ""
        registros = []
        for idx, semana in enumerate(opcion_seleccionada["semanas"], start=1):
            for dia, estado in semana.items():
                registros.append(
                    (
                        personal_id,
                        opcion_seleccionada["grupo_turno"],
                        opcion_seleccionada["jornada"],
                        opcion_seleccionada["horario"],
                        cuadrante,
                        dia,
                        idx,
                        estado,
                    )
                )
        self.repositorio.reemplazar_mallas([personal_id], registros)

    # ------------------------------------------------------------- equipo 24/7
    def generar_opciones_equipo(self, personas: list[tuple], requerimientos: dict) -> list[dict]:
        """personas: [(id, nombre, rol, jornada)]; requerimientos: {rol: (min_dia, min_noche)}.

        Quien ya tiene jornada asignada (DIURNO/NOCTURNO) se mantiene en ella; el planificador
        solo decide la jornada de quien no la tiene (jornada None).
        """
        for persona in personas:
            if persona[2] not in ROLES_PERSONAL:
                raise ValueError(f"Rol inválido en el equipo: {persona[2]}")
        return generar_opciones_equipo(personas, requerimientos)

    def asignar_plan_equipo(
        self,
        opcion: dict,
        horario_diurno: str,
        modalidades: dict[int, list[str]] | None = None,
    ) -> None:
        """Valida el Art. 38 de cada integrante y guarda todo el plan en una sola transacción."""
        if horario_diurno not in HORARIOS_DIURNOS:
            raise ValueError(f"Horario diurno inválido. Opciones: {HORARIOS_DIURNOS}")
        modalidades = {
            pid: self._normalizar_modalidades(m) for pid, m in (modalidades or {}).items()
        }

        perfiles = {p["id"]: p for p in self.repositorio.listar_personal()}
        registros, grupo_por_patron = [], {}
        for pid, datos in opcion["asignaciones"].items():
            grilla = datos["grilla"]
            jornada = self._jornada_efectiva(j for _e, j in grilla)
            perfil = perfiles.get(pid, {})
            if perfil.get("jornada") and any(j != perfil["jornada"] for _e, j in grilla):
                raise ValueError(
                    f"El plan cambia la jornada de {perfil.get('nombre', pid)}, "
                    f"que está asignado a {perfil['jornada']}."
                )
            if not self.cumple_descanso_legal(jornada, grilla_a_semanas(grilla)):
                raise ValueError(
                    "El plan incumple el descanso legal (Art. 38) para uno de los integrantes."
                )
            # se respeta el turno (A/B) del integrante; si no tiene, se reparte por patrón
            indice = grupo_por_patron.setdefault((datos["modo"], datos["seq"]), len(grupo_por_patron))
            grupo = perfil.get("grupo_turno") or GRUPOS_TURNO[indice % len(GRUPOS_TURNO)]
            for k, (estado, jornada_dia) in enumerate(grilla):
                registros.append(
                    (
                        pid,
                        grupo,
                        jornada_dia,
                        HORARIO_NOCTURNO if jornada_dia == "NOCTURNO" else horario_diurno,
                        perfil.get("cuadrante") or "",
                        DIAS_SEMANA[k % 7],
                        k // 7 + 1,
                        estado,
                    )
                )

        self.repositorio.reemplazar_mallas(list(opcion["asignaciones"]), registros)
        # la modalidad solo aplica a patrulleros; se SUMA a las que ya usan
        patrulleros = self._ids_patrulleros()
        self.repositorio.agregar_modalidades(
            {pid: m for pid, m in modalidades.items() if pid in patrulleros and m}
        )

    # ------------------------------------------- turnos A y B (cada turno junto)
    @staticmethod
    def _nombre_de(p: dict) -> str:
        return f"{p['nombre']} {p.get('apellido') or ''}".strip()

    def resumen_turnos(self) -> dict:
        """Integrantes por turno (A/B) y quiénes aún no tienen turno o jornada."""
        res = {g: {"total": 0, "diurnos": 0, "nocturnos": 0} for g in GRUPOS_TURNO}
        sin_turno = []
        for p in self.repositorio.listar_personal():
            if p["grupo_turno"] in res and p["jornada"] in JORNADAS:
                r = res[p["grupo_turno"]]
                r["total"] += 1
                r["diurnos" if p["jornada"] == "DIURNO" else "nocturnos"] += 1
            else:
                sin_turno.append(self._nombre_de(p))
        return {"turnos": res, "sin_turno": sin_turno}

    def _personas_con_turno(self) -> list[tuple]:
        return [
            (p["id"], self._nombre_de(p), p["rol"], p["grupo_turno"], p["jornada"])
            for p in self.repositorio.listar_personal()
            if p["grupo_turno"] in GRUPOS_TURNO and p["jornada"] in JORNADAS
        ]

    def generar_opciones_turnos_ab(self) -> list[dict]:
        return opciones_turnos_ab(self._personas_con_turno())

    def asignar_turnos_ab(
        self, opcion: dict, horarios_diurnos: list[str]
    ) -> int:
        """Asigna la malla: todo el turno A con el patrón A y todo el turno B con el patrón B.

        Los integrantes diurnos de cada turno se reparten entre los horarios indicados;
        los nocturnos usan el horario nocturno. Devuelve cuántas personas se asignaron.
        """
        personas = self._personas_con_turno()
        if not personas:
            raise ValueError("No hay integrantes con turno y jornada asignados.")
        if any(p[4] == "DIURNO" for p in personas):
            if not horarios_diurnos or any(h not in HORARIOS_DIURNOS for h in horarios_diurnos):
                raise ValueError(f"Elija al menos un horario diurno válido: {HORARIOS_DIURNOS}")

        cuadrante_de = {p["id"]: p.get("cuadrante") or "" for p in self.repositorio.listar_personal()}
        registros, repartidos = [], {"A": 0, "B": 0}
        for pid, nombre, _rol, grupo, jornada in sorted(personas, key=lambda p: (p[3], p[1].lower())):
            seq = opcion["seq_a"] if grupo == "A" else opcion["seq_b"]
            semanas = seq_a_semanas(seq)
            if not self.cumple_descanso_legal(jornada, semanas):
                raise ValueError(f"El patrón del turno {grupo} incumple el Art. 38 para {nombre}.")
            if jornada == "DIURNO":
                horario = horarios_diurnos[repartidos[grupo] % len(horarios_diurnos)]
                repartidos[grupo] += 1
            else:
                horario = HORARIO_NOCTURNO
            cuad = cuadrante_de.get(pid, "")
            for idx, semana in enumerate(semanas, start=1):
                for dia, estado in semana.items():
                    registros.append((pid, grupo, jornada, horario, cuad, dia, idx, estado))
        self.repositorio.reemplazar_mallas([p[0] for p in personas], registros)
        return len(personas)

    # ---------------------------------------------------------------- cuadrantes
    def asignar_cuadrante(self, personal_ids: list[int], cuadrante: str | None) -> int:
        """Cuadrante propio de cada persona, independiente de su malla (None lo quita)."""
        if cuadrante is not None and cuadrante not in CUADRANTES:
            raise ValueError(f"Cuadrante inválido. Opciones: {CUADRANTES}")
        existentes = {p["id"] for p in self.repositorio.listar_personal()}
        ids = [pid for pid in personal_ids if pid in existentes]
        if not ids:
            raise ValueError("Seleccione al menos un integrante.")
        self.repositorio.actualizar_cuadrante(ids, cuadrante)
        return len(ids)

    def repartir_cuadrantes_auto(self, solo_sin_cuadrante: bool = True) -> int:
        """Reparte a las personas entre los cuadrantes de forma pareja.
        Por cada cargo se equilibra por separado (así cada cuadrante recibe patrulleros,
        radio operadores y supervisores). Devuelve cuántas personas se asignaron."""
        personas = self.repositorio.listar_personal()
        total = {c: 0 for c in CUADRANTES}
        por_rol: dict[str, dict[str, int]] = {}
        for p in personas:
            if p.get("cuadrante") in total:
                total[p["cuadrante"]] += 1
                r = por_rol.setdefault(p["rol"], {c: 0 for c in CUADRANTES})
                r[p["cuadrante"]] += 1
        cambios: dict[str, list[int]] = {}
        for p in personas:
            if solo_sin_cuadrante and p.get("cuadrante") in total:
                continue
            r = por_rol.setdefault(p["rol"], {c: 0 for c in CUADRANTES})
            c = min(CUADRANTES, key=lambda x: (r[x], total[x], CUADRANTES.index(x)))
            r[c] += 1
            total[c] += 1
            cambios.setdefault(c, []).append(p["id"])
        for c, ids in cambios.items():
            self.repositorio.actualizar_cuadrante(ids, c)
        return sum(len(v) for v in cambios.values())

    def resumen_cuadrantes(self) -> dict:
        """Personas por cuadrante. Un patrullero cuenta una vez en cada modalidad que usa."""
        modalidades = self.repositorio.obtener_modalidades()
        cuadrantes = {
            c: {
                "total": 0,
                "por_modalidad": {m: 0 for m in MODALIDADES},
                "patrulleros_sin_modalidad": 0,
                "por_rol": {},
                "nombres": [],
            }
            for c in CUADRANTES
        }
        sin_cuadrante = []
        for p in self.repositorio.listar_personal():
            if p.get("cuadrante") not in cuadrantes:
                sin_cuadrante.append(self._nombre_de(p))
                continue
            c = cuadrantes[p["cuadrante"]]
            c["total"] += 1
            c["nombres"].append(self._nombre_de(p))
            if p["rol"] == ROL_PATRULLERO:
                mods = modalidades.get(p["id"], [])
                for m in mods:
                    c["por_modalidad"][m] += 1
                if not mods:
                    c["patrulleros_sin_modalidad"] += 1
            else:
                c["por_rol"][p["rol"]] = c["por_rol"].get(p["rol"], 0) + 1
        return {"cuadrantes": cuadrantes, "sin_cuadrante": sin_cuadrante}

    # ------------------------------------------------------------------- edición
    def intercambiar_dias(self, personal_id: int, asignacion_a: int, asignacion_b: int) -> bool:
        """Mueve un día de turno a otro casillero (intercambia ambos), validando el Art. 38."""
        if asignacion_a == asignacion_b:
            return False
        malla = self.repositorio.obtener_malla_personal(personal_id)
        filas = {f["id"]: f for f in malla}
        if asignacion_a not in filas or asignacion_b not in filas:
            raise ValueError("Los días no pertenecen a este integrante.")
        estado_a, estado_b = filas[asignacion_a]["estado"], filas[asignacion_b]["estado"]
        if estado_a == estado_b:
            return False  # nada que mover

        jornada = self._jornada_efectiva(f["jornada"] for f in malla)
        semanas = {1: {}, 2: {}, 3: {}, 4: {}}
        for f in malla:
            estado = (
                estado_b if f["id"] == asignacion_a
                else estado_a if f["id"] == asignacion_b
                else f["estado"]
            )
            semanas[f["semana_mes"]][f["dia_semana"]] = estado
        if not self.cumple_descanso_legal(jornada, list(semanas.values())):
            raise ValueError(
                "Movimiento rechazado: dejaría al integrante sin el descanso dominical / "
                "de fin de semana que exige el Art. 38."
            )
        self.repositorio.intercambiar_estados(asignacion_a, asignacion_b)
        return True

    def editar_estado_dia(
        self, personal_id: int, asignacion_id: int, nuevo_estado: str
    ) -> bool:
        """Permite editar una celda (T, L, VAC, HE, HEN) validando descanso legal."""
        if nuevo_estado not in ESTADOS_CELDA:
            raise ValueError(f"Estado inválido. Permitidos: {ESTADOS_CELDA}")

        malla_actual = self.repositorio.obtener_malla_personal(personal_id)
        if not malla_actual:
            raise ValueError("El integrante no tiene turnos asignados.")

        # Simula el cambio antes de guardar para no infringir la ley.
        # En mallas rotativas día/noche rige la regla más exigente (nocturna).
        jornada = self._jornada_efectiva(fila["jornada"] for fila in malla_actual)
        semanas_simuladas = {1: {}, 2: {}, 3: {}, 4: {}}
        for fila in malla_actual:
            estado = nuevo_estado if fila["id"] == asignacion_id else fila["estado"]
            semanas_simuladas[fila["semana_mes"]][fila["dia_semana"]] = estado

        if not self.cumple_descanso_legal(jornada, list(semanas_simuladas.values())):
            raise ValueError(
                "Edición rechazada: incumple el descanso dominical/fin de semana legal."
            )

        return self.repositorio.actualizar_celda_turno(asignacion_id, nuevo_estado)

    # ------------------------------------------------------------------- consulta
    def obtener_modalidades_persona(self, personal_id: int) -> list[str]:
        return self.repositorio.obtener_modalidades_persona(personal_id)

    # ----------------------------------------------------------------- utilidades
    @staticmethod
    def _jornada_efectiva(jornadas) -> str:
        return "NOCTURNO" if "NOCTURNO" in set(jornadas) else "DIURNO"

    def _validar_parametros_malla(
        self, grupo_turno: str, jornada: str, horario: str
    ) -> None:
        if grupo_turno not in GRUPOS_TURNO:
            raise ValueError(f"El grupo de turno debe ser uno de: {GRUPOS_TURNO}")
        if jornada not in JORNADAS:
            raise ValueError(f"La jornada debe ser una de: {JORNADAS}")
        if jornada == "DIURNO" and horario not in HORARIOS_DIURNOS:
            raise ValueError(f"Horario diurno inválido. Opciones: {HORARIOS_DIURNOS}")
        if jornada == "NOCTURNO" and horario != HORARIO_NOCTURNO:
            raise ValueError(f"Horario nocturno debe ser '{HORARIO_NOCTURNO}'.")
