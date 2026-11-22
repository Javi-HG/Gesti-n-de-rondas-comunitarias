"""Capa de lógica de negocio: reglas 4x3, validación legal y edición."""

import re

from constantes_reglas import (
    DESTINOS_SERVICIO,
    FERIA,
    MIN_MOVILES_POR_CUADRANTE,
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
from exportar_excel import Hoja, guardar_xlsx, leer_xlsx
from cobertura_horaria import DIAS_MES, HORAS_DIA, cobertura_por_dia, elegir_horarios, rangos_horas
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
        modalidades = self._normalizar_modalidades(modalidades)
        if modalidades and rol != ROL_PATRULLERO:
            raise ValueError("Solo los patrulleros pueden tener modalidad.")
        self._validar_destino(cuadrante, rol, modalidades)
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

    def renombrar_integrante(self, personal_id: int, nombre: str) -> None:
        nombre = (nombre or "").strip()
        if not nombre:
            raise ValueError("El nombre no puede quedar vacío.")
        if not self.repositorio.actualizar_nombre(personal_id, nombre):
            raise ValueError("El integrante no existe.")

    # ------------------------------------------------------------- carga masiva
    COLUMNAS_CARGA = ("Nombre", "Cargo", "Turno", "Jornada", "Cuadrante", "Modalidades")

    @staticmethod
    def _plano(texto: str) -> str:
        import unicodedata
        t = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode()
        return " ".join(t.lower().replace("_", " ").split())

    def texto_a_filas(self, texto: str) -> list[list[str]]:
        """Convierte texto pegado (una persona por línea; columnas separadas por ; tab o coma)."""
        filas = []
        for linea in texto.splitlines():
            if not linea.strip():
                continue
            sep = next((d for d in (";", "\t", ",") if d in linea), None)
            filas.append([c.strip() for c in (linea.split(sep) if sep else [linea])])
        return filas

    def leer_archivo_personal(self, ruta: str) -> list[list[str]]:
        """Lee un .xlsx o .csv con el personal (primera fila puede ser el encabezado)."""
        if ruta.lower().endswith(".xlsx"):
            return leer_xlsx(ruta)
        import csv
        with open(ruta, newline="", encoding="utf-8-sig", errors="replace") as f:
            muestra = f.read(4096)
            f.seek(0)
            delim = ";" if muestra.count(";") >= muestra.count(",") else ","
            return [[c.strip() for c in fila] for fila in csv.reader(f, delimiter=delim) if any(fila)]

    def importar_personal(self, filas: list[list[str]], por_defecto: dict | None = None) -> dict:
        """Carga masiva: valida TODAS las filas y solo entonces guarda (todo o nada).

        Columnas: Nombre, Cargo, Turno, Jornada, Cuadrante, Modalidades (separadas por + o /).
        Lo que falte se toma de `por_defecto` {rol, turno, jornada, cuadrante, modalidades}.
        Quien ya existe con el mismo nombre se omite (así se puede repetir la carga).
        """
        d = por_defecto or {}
        filas = [list(f) for f in filas if any(str(c).strip() for c in f)]
        if filas and self._plano(filas[0][0]) in ("nombre", "nombres", "nombre completo"):
            filas = filas[1:]
        if not filas:
            raise ValueError("No hay personas para cargar.")

        roles = {self._plano(r): r for r in ROLES_PERSONAL}
        roles.update({"radio": "RADIO_OPERADOR", "radio operador": "RADIO_OPERADOR",
                      "radiooperador": "RADIO_OPERADOR", "guardia": ROL_PATRULLERO})
        jornadas = {"diurno": "DIURNO", "dia": "DIURNO", "nocturno": "NOCTURNO", "noche": "NOCTURNO"}
        mods = {self._plano(m): m for m in MODALIDADES}
        mods.update({"bici": "Bicicleta", "movil": "Móvil", "auto": "Móvil"})
        existentes = {self._plano(p["nombre"]) for p in self.repositorio.listar_personal()}

        errores, validas, omitidos, vistos = [], [], [], set()
        for n, fila in enumerate(filas, start=1):
            fila = (fila + [""] * 6)[:6]
            nombre = " ".join(fila[0].split())
            if not nombre:
                errores.append(f"Fila {n}: falta el nombre.")
                continue
            if self._plano(nombre) in existentes or self._plano(nombre) in vistos:
                omitidos.append(nombre)
                continue
            try:
                rol = roles.get(self._plano(fila[1]) or self._plano(d.get("rol", ROL_PATRULLERO)))
                if rol is None:
                    raise ValueError(f"cargo «{fila[1]}» no válido (use Patrullero, Radio operador o Supervisor)")
                turno = (fila[2] or d.get("turno") or "").strip().upper()
                if turno not in GRUPOS_TURNO:
                    raise ValueError("turno debe ser A o B")
                jornada = jornadas.get(self._plano(fila[3] or d.get("jornada") or ""))
                if jornada is None:
                    raise ValueError("jornada debe ser Diurno o Nocturno")
                cuad = (fila[4] or d.get("cuadrante") or "").strip()
                if cuad and self._plano(cuad) != "sin cuadrante":
                    if cuad.isdigit():
                        cuad = f"Cuadrante {cuad}"
                    cuad = next((c for c in DESTINOS_SERVICIO if self._plano(c) == self._plano(cuad)), None)
                    if cuad is None:
                        raise ValueError(f"cuadrante «{fila[4]}» no existe")
                else:
                    cuad = None
                texto_mod = fila[5] or d.get("modalidades") or ""
                lista = []
                for parte in re.split(r"[+/,|]", texto_mod) if texto_mod else []:
                    if parte.strip():
                        m = mods.get(self._plano(parte))
                        if m is None:
                            raise ValueError(f"modalidad «{parte.strip()}» no existe")
                        lista.append(m)
                lista = self._normalizar_modalidades(lista)
                if lista and rol != ROL_PATRULLERO:
                    raise ValueError("solo los patrulleros tienen modalidad")
                self._validar_destino(cuad, rol, lista)
            except ValueError as err:
                errores.append(f"Fila {n} ({nombre}): {str(err).rstrip('.')}.")
                continue
            vistos.add(self._plano(nombre))
            validas.append((nombre, rol, turno, jornada, cuad, lista))
        if errores:
            extra = f"\n… y {len(errores) - 15} error(es) más." if len(errores) > 15 else ""
            raise ValueError("No se cargó a nadie. Corrija:\n" + "\n".join(errores[:15]) + extra)
        if validas:
            self.repositorio.registrar_varios(validas)
        return {"importados": len(validas), "omitidos": omitidos}

    def plantilla_carga_excel(self, ruta: str) -> None:
        """Genera el Excel de ejemplo para la carga masiva."""
        h = Hoja("Personal")
        for c, t in enumerate(self.COLUMNAS_CARGA):
            h.celda(0, c, t, "enc")
            h.anchos[c] = (28, 16, 8, 12, 16, 26)[c]
        ejemplos = [
            ("Juan Pérez", "Patrullero", "A", "Diurno", "Cuadrante 1", "Móvil"),
            ("María López", "Patrullero", "B", "Nocturno", "", "Moto"),
            ("Pedro Soto", "Patrullero", "A", "Diurno", "Feria", "Bicicleta"),
            ("Ana Rojas", "Radio operador", "A", "Diurno", "", ""),
            ("Luis Vera", "Supervisor", "B", "Diurno", "", ""),
        ]
        for r, fila in enumerate(ejemplos, start=1):
            for c, v in enumerate(fila):
                h.celda(r, c, v, "normal")
        notas = Hoja("Instrucciones")
        lineas = [
            "Una persona por fila. Borre las filas de ejemplo antes de cargar.",
            "Cargo: Patrullero · Radio operador · Supervisor.",
            "Turno: A o B.   Jornada: Diurno o Nocturno.",
            "Cuadrante (opcional): Cuadrante 1 a 6 (o solo el número). Feria solo para bicicletas. Las motos no llevan cuadrante.",
            "Modalidades (opcional, solo patrulleros): Móvil, Moto, Infantería, Bicicleta. Varias separadas por +  (ej.: Móvil + Moto).",
            "Quien ya exista con el mismo nombre se omite.",
        ]
        for r, t in enumerate(lineas):
            notas.celda(r, 0, t, "normal")
        notas.anchos[0] = 120
        guardar_xlsx(ruta, [h, notas])

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
        self._aplicar_reglas_destino(personal_ids)

    def agregar_modalidad(self, personal_ids: list[int], modalidad: str) -> None:
        """Suma una modalidad sin quitar las que ya usa cada patrullero."""
        lista = self._normalizar_modalidades([modalidad])
        self._validar_patrulleros(personal_ids)
        self.repositorio.agregar_modalidades({pid: lista for pid in personal_ids})
        self._aplicar_reglas_destino(personal_ids)

    def quitar_modalidad(self, personal_ids: list[int], modalidad: str) -> None:
        self._normalizar_modalidades([modalidad])
        self._validar_patrulleros(personal_ids)
        self.repositorio.quitar_modalidad(personal_ids, modalidad)
        self._aplicar_reglas_destino(personal_ids)

    def repartir_modalidades_auto(self, personal_ids: list[int] | None = None) -> int:
        """Da UNA modalidad a los patrulleros que no tienen ninguna. Primero completa los
        móviles (al menos uno por cuadrante) y el resto se reparte de forma pareja.
        Quienes ya tienen modalidades no se tocan. Devuelve cuántos recibieron una."""
        patrulleros = self._ids_patrulleros()
        objetivo = [pid for pid in (personal_ids if personal_ids is not None else sorted(patrulleros))
                    if pid in patrulleros]
        actuales = self.repositorio.obtener_modalidades()
        conteo = {m: 0 for m in MODALIDADES}
        for pid in patrulleros:
            for m in actuales.get(pid, []):
                conteo[m] += 1
        meta_movil = MIN_MOVILES_POR_CUADRANTE * len(CUADRANTES)
        nuevas = {}
        for pid in objetivo:
            if actuales.get(pid):
                continue
            if conteo["Móvil"] < meta_movil:
                m = "Móvil"
            else:
                m = min(MODALIDADES, key=lambda x: (conteo[x], MODALIDADES.index(x)))
            conteo[m] += 1
            nuevas[pid] = [m]
        if nuevas:
            self.repositorio.agregar_modalidades(nuevas)
        return len(nuevas)

    @staticmethod
    def _validar_destino(destino: str | None, rol: str, modalidades: list[str]) -> None:
        """Reglas del cuadrante: las motos no llevan cuadrante y la Feria es solo de bicicletas."""
        if not destino:
            return
        if destino not in DESTINOS_SERVICIO:
            raise ValueError(f"Destino inválido. Opciones: {DESTINOS_SERVICIO}")
        if rol == ROL_PATRULLERO and modalidades and set(modalidades) == {"Moto"}:
            raise ValueError("Las motos no tienen cuadrante asignado.")
        if destino == FERIA and not (rol == ROL_PATRULLERO and "Bicicleta" in modalidades):
            raise ValueError("La Feria solo se asigna a quienes usan bicicleta.")

    def _aplicar_reglas_destino(self, personal_ids: list[int]) -> None:
        """Tras cambiar modalidades: quien queda solo con Moto pierde el cuadrante y
        quien deja la bicicleta pierde la Feria."""
        modalidades = self.repositorio.obtener_modalidades()
        sin_cuadrante = []
        for pid in personal_ids:
            p = self.repositorio.obtener_persona(pid)
            if not p or not p.get("cuadrante"):
                continue
            mods = modalidades.get(pid, [])
            solo_moto = bool(mods) and set(mods) == {"Moto"}
            if solo_moto or (p["cuadrante"] == FERIA and "Bicicleta" not in mods):
                sin_cuadrante.append(pid)
        if sin_cuadrante:
            self.repositorio.actualizar_cuadrante(sin_cuadrante, None)

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

    @staticmethod
    def _lista_horarios(horarios) -> list[str]:
        lista = [horarios] if isinstance(horarios, str) else list(horarios or [])
        if not lista or any(h not in HORARIOS_DIURNOS for h in lista):
            raise ValueError(f"Elija al menos un horario diurno válido: {HORARIOS_DIURNOS}")
        return [h for h in HORARIOS_DIURNOS if h in lista]

    def asignar_plan_equipo(
        self,
        opcion: dict,
        horarios_diurnos,
        modalidades: dict[int, list[str]] | None = None,
    ) -> list[str]:
        """Valida el Art. 38 de cada integrante y guarda todo el plan en una sola transacción.

        Los horarios diurnos se reparten entre el personal para cubrir las 24 horas.
        Devuelve los avisos de horas que aún quedan sin cubrir (lista vacía si está completo)."""
        horarios = self._lista_horarios(horarios_diurnos)
        modalidades = {
            pid: self._normalizar_modalidades(m) for pid, m in (modalidades or {}).items()
        }

        perfiles = {p["id"]: p for p in self.repositorio.listar_personal()}
        validados, grupo_por_patron, personas_h = [], {}, []
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
            validados.append((pid, grupo, grilla, perfil))
            personas_h.append({
                "id": pid, "grupo": perfil.get("rol", ""),
                "dias": [(None if e != "T" else ("N" if jd == "NOCTURNO" else "D")) for e, jd in grilla],
            })

        horario_de = elegir_horarios(personas_h, horarios)
        registros = []
        for pid, grupo, grilla, perfil in validados:
            for k, (estado, jornada_dia) in enumerate(grilla):
                registros.append(
                    (
                        pid,
                        grupo,
                        jornada_dia,
                        HORARIO_NOCTURNO if jornada_dia == "NOCTURNO" else horario_de.get(pid, horarios[0]),
                        perfil.get("cuadrante") or "",
                        DIAS_SEMANA[k % 7],
                        k // 7 + 1,
                        estado,
                    )
                )

        self.repositorio.reemplazar_mallas(list(opcion["asignaciones"]), registros)
        # la modalidad solo aplica a patrulleros; se SUMA a las que ya usan
        patrulleros = self._ids_patrulleros()
        con_modalidad = {pid: m for pid, m in modalidades.items() if pid in patrulleros and m}
        if con_modalidad:
            self.repositorio.agregar_modalidades(con_modalidad)
            self._aplicar_reglas_destino(list(con_modalidad))
        return self.avisos_horarios()

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

        cuadrante_de = {p["id"]: p.get("cuadrante") or "" for p in self.repositorio.listar_personal()}
        horarios_diurnos = self._lista_horarios(horarios_diurnos) if any(p[4] == "DIURNO" for p in personas) else []
        personas_h = []
        for pid, _n, rol, grupo, jornada in personas:
            seq = opcion["seq_a"] if grupo == "A" else opcion["seq_b"]
            personas_h.append({
                "id": pid, "grupo": rol,
                "dias": [(None if libre else ("D" if jornada == "DIURNO" else "N")) for libre in seq],
            })
        horario_de = elegir_horarios(personas_h, horarios_diurnos) if horarios_diurnos else {}

        registros = []
        for pid, nombre, _rol, grupo, jornada in sorted(personas, key=lambda p: (p[3], p[1].lower())):
            seq = opcion["seq_a"] if grupo == "A" else opcion["seq_b"]
            semanas = seq_a_semanas(seq)
            if not self.cumple_descanso_legal(jornada, semanas):
                raise ValueError(f"El patrón del turno {grupo} incumple el Art. 38 para {nombre}.")
            horario = horario_de.get(pid, horarios_diurnos[0] if horarios_diurnos else HORARIO_NOCTURNO) \
                if jornada == "DIURNO" else HORARIO_NOCTURNO
            cuad = cuadrante_de.get(pid, "")
            for idx, semana in enumerate(semanas, start=1):
                for dia, estado in semana.items():
                    registros.append((pid, grupo, jornada, horario, cuad, dia, idx, estado))
        self.repositorio.reemplazar_mallas([p[0] for p in personas], registros)
        return len(personas)

    # ---------------------------------------------------------------- cuadrantes
    def asignar_cuadrante(self, personal_ids: list[int], destino: str | None) -> int:
        """Cuadrante (o Feria, solo bicicletas) propio de cada persona; None lo quita.
        Las motos no llevan cuadrante. Es independiente de la malla."""
        if destino is not None and destino not in DESTINOS_SERVICIO:
            raise ValueError(f"Destino inválido. Opciones: {DESTINOS_SERVICIO}")
        modalidades = self.repositorio.obtener_modalidades()
        personas = {p["id"]: p for p in self.repositorio.listar_personal()}
        ids = [pid for pid in personal_ids if pid in personas]
        if not ids:
            raise ValueError("Seleccione al menos un integrante.")
        for pid in ids:  # valida a todos antes de cambiar a alguien
            try:
                self._validar_destino(destino, personas[pid]["rol"], modalidades.get(pid, []))
            except ValueError as err:
                raise ValueError(f"{personas[pid]['nombre']}: {err}") from None
        self.repositorio.actualizar_cuadrante(ids, destino)
        return len(ids)

    @staticmethod
    def _es_solo_moto(mods: list[str]) -> bool:
        return bool(mods) and set(mods) == {"Moto"}

    def repartir_cuadrantes_auto(self, solo_sin_cuadrante: bool = True) -> int:
        """Reparte a las personas entre los cuadrantes de forma pareja.

        - Primero asegura al menos un Móvil en cada cuadrante.
        - Las motos no llevan cuadrante.
        - Las bicicletas se reparten entre los cuadrantes y la Feria.
        - El resto se equilibra por tipo de servicio / cargo.
        Devuelve cuántas personas cambiaron de destino."""
        personas = self.repositorio.listar_personal()
        mods = self.repositorio.obtener_modalidades()
        cuadrantes = list(CUADRANTES)
        actual = {p["id"]: (p.get("cuadrante") or None) for p in personas}
        nuevo: dict[int, str | None] = {}

        def clase(p) -> str:
            """Tipo de servicio: Móvil > Infantería > Bicicleta > Moto; resto por cargo."""
            if p["rol"] != ROL_PATRULLERO:
                return p["rol"]
            m = mods.get(p["id"], [])
            for k in ("Móvil", "Infantería", "Bicicleta", "Moto"):
                if k in m:
                    return k
            return "Sin modalidad"

        # quienes se mueven: todos, o solo los que aún no tienen destino
        mueven = [
            p for p in personas
            if not solo_sin_cuadrante or actual[p["id"]] is None
        ]
        for p in list(mueven):
            if self._es_solo_moto(mods.get(p["id"], [])):
                nuevo[p["id"]] = None  # las motos no llevan cuadrante
                mueven.remove(p)
        fijos = {p["id"] for p in personas} - {p["id"] for p in mueven}

        # conteos de lo que ya está asignado y no se mueve
        por_clase: dict[str, dict[str, int]] = {}
        total = {d: 0 for d in DESTINOS_SERVICIO}

        def contar(p, destino, delta=1):
            if destino is None:
                return
            c = por_clase.setdefault(clase(p), {d: 0 for d in DESTINOS_SERVICIO})
            c[destino] += delta
            total[destino] += delta

        por_id = {p["id"]: p for p in personas}
        for pid in fijos:
            contar(por_id[pid], nuevo.get(pid, actual[pid]))

        # 1) al menos un Móvil por cuadrante
        moviles_libres = [p for p in mueven if clase(p) == "Móvil"]
        for c in cuadrantes:
            if por_clase.get("Móvil", {}).get(c, 0) >= MIN_MOVILES_POR_CUADRANTE:
                continue
            if not moviles_libres:
                break
            # prefiere un móvil de jornada distinta a los ya asignados al cuadrante
            jornadas_c = {
                por_id[q]["jornada"] for q in fijos | set(nuevo)
                if (nuevo.get(q, actual.get(q)) == c) and clase(por_id[q]) == "Móvil"
            }
            elegido = next((p for p in moviles_libres if p["jornada"] not in jornadas_c), moviles_libres[0])
            moviles_libres.remove(elegido)
            mueven.remove(elegido)
            nuevo[elegido["id"]] = c
            contar(elegido, c)

        # 2) el resto, equilibrado por clase (la bicicleta también puede ir a la Feria)
        for p in mueven:
            k = clase(p)
            opciones = list(DESTINOS_SERVICIO) if k == "Bicicleta" else cuadrantes
            tabla = por_clase.setdefault(k, {d: 0 for d in DESTINOS_SERVICIO})
            destino = min(opciones, key=lambda d: (tabla[d], total[d], DESTINOS_SERVICIO.index(d)))
            nuevo[p["id"]] = destino
            contar(p, destino)

        cambios: dict[str | None, list[int]] = {}
        for pid, destino in nuevo.items():
            if destino != actual[pid]:
                cambios.setdefault(destino, []).append(pid)
        for destino, ids in cambios.items():
            self.repositorio.actualizar_cuadrante(ids, destino)
        return sum(len(v) for v in cambios.values())

    def resumen_cuadrantes(self) -> dict:
        """Personas por cuadrante y Feria. Un patrullero cuenta una vez en cada modalidad que usa.
        Incluye los cuadrantes que aún no tienen ningún Móvil."""
        modalidades = self.repositorio.obtener_modalidades()
        destinos = {
            c: {
                "total": 0,
                "por_modalidad": {m: 0 for m in MODALIDADES},
                "patrulleros_sin_modalidad": 0,
                "por_rol": {},
                "nombres": [],
            }
            for c in DESTINOS_SERVICIO
        }
        sin_cuadrante, motos = [], []
        for p in self.repositorio.listar_personal():
            mods = modalidades.get(p["id"], []) if p["rol"] == ROL_PATRULLERO else []
            if p.get("cuadrante") not in destinos:
                (motos if self._es_solo_moto(mods) else sin_cuadrante).append(self._nombre_de(p))
                continue
            c = destinos[p["cuadrante"]]
            c["total"] += 1
            c["nombres"].append(self._nombre_de(p))
            if p["rol"] == ROL_PATRULLERO:
                for m in mods:
                    c["por_modalidad"][m] += 1
                if not mods:
                    c["patrulleros_sin_modalidad"] += 1
            else:
                c["por_rol"][p["rol"]] = c["por_rol"].get(p["rol"], 0) + 1
        faltan_movil = [
            c for c in CUADRANTES
            if destinos[c]["por_modalidad"]["Móvil"] < MIN_MOVILES_POR_CUADRANTE
        ]
        return {
            "cuadrantes": destinos, "sin_cuadrante": sin_cuadrante,
            "motos": motos, "faltan_movil": faltan_movil,
        }

    # --------------------------------------------------------- cobertura 24 horas
    def cobertura_horaria(self) -> list[dict]:
        """Horas cubiertas (de 24) para cada día del mes, por cargo y por Móvil de cada cuadrante.

        Devuelve [{"nombre", "horas": [28 enteros], "faltan": [28 conjuntos de horas], "completo": bool}].
        """
        modalidades = self.repositorio.obtener_modalidades()
        dias_idx = {d: i for i, d in enumerate(DIAS_SEMANA)}
        por_grupo: dict[str, list] = {}
        for p in self.repositorio.listar_personal():
            malla = self.repositorio.obtener_malla_personal(p["id"])
            if not malla:
                continue
            turnos = [
                ((f["semana_mes"] - 1) * 7 + dias_idx[f["dia_semana"]], f["horario"])
                for f in malla if f["estado"] in ("T", "HE", "HEN")
            ]
            claves = [p["rol"]]
            if p["rol"] == ROL_PATRULLERO and "Móvil" in modalidades.get(p["id"], []) and p.get("cuadrante") in CUADRANTES:
                claves.append(f"Móvil · {p['cuadrante']}")
            for clave in claves:
                por_grupo.setdefault(clave, []).extend(turnos)
        orden = [r for r in ROLES_PERSONAL if r in por_grupo] + [
            f"Móvil · {c}" for c in CUADRANTES
        ]
        resultado = []
        for nombre in orden:
            dias = cobertura_por_dia(por_grupo.get(nombre, []))
            faltan = [set(range(HORAS_DIA)) - d for d in dias]
            etiqueta = nombre.replace("_", " ").capitalize() if nombre in ROLES_PERSONAL else nombre
            resultado.append({
                "nombre": etiqueta, "horas": [len(d) for d in dias], "faltan": faltan,
                "completo": all(len(d) == HORAS_DIA for d in dias),
                "es_cargo": nombre in ROLES_PERSONAL,
            })
        return resultado

    def avisos_horarios(self) -> list[str]:
        """Textos con las horas que quedan sin cubrir por cargo (vacío = 24 h completas)."""
        avisos = []
        for g in self.cobertura_horaria():
            if not g["es_cargo"]:
                continue
            incompletos = [(k, f) for k, f in enumerate(g["faltan"]) if f]
            if not incompletos:
                continue
            k, f = incompletos[0]
            avisos.append(
                f"{g['nombre']}: {len(incompletos)} día(s) sin las 24 h cubiertas "
                f"(p. ej. día {k + 1}: falta {rangos_horas(f)})."
            )
        return avisos

    # ------------------------------------------------------------------- Excel
    def exportar_excel(self, ruta: str, personal_ids: list[int] | None = None) -> int:
        """Guarda la malla mensual en un archivo Excel (.xlsx). Sin ids = todo el equipo
        (con hojas de cuadrantes y de cobertura de 24 horas). Devuelve cuántas personas exportó."""
        datos = self.obtener_mallas_equipo()
        if personal_ids is not None:
            datos = [d for d in datos if d["persona"]["id"] in set(personal_ids)]
        if not datos:
            raise ValueError("No hay personas para exportar.")
        orden_rol = {r: i for i, r in enumerate(ROLES_PERSONAL)}
        datos.sort(key=lambda d: (
            d["persona"]["grupo_turno"] or "Z", orden_rol.get(d["persona"]["rol"], 99),
            d["persona"]["nombre"].lower(),
        ))

        h = Hoja("Malla mensual")
        encabezados = ("Nombre", "Cargo", "Turno", "Jornada", "Horario", "Cuadrante", "Modalidades")
        base = len(encabezados)
        h.celda(0, 0, "Malla mensual 4x3 · Seguridad La Cisterna", "titulo")
        for c, t in enumerate(encabezados):
            h.celda(2, c, t, "enc")
            h.combinar(2, c, 3, c)
            h.celda(3, c, "", "enc")
            h.anchos[c] = (22, 16, 8, 12, 22, 14, 24)[c]
        for sem in range(4):
            h.celda(2, base + sem * 7, f"Semana {sem + 1}", "sem")
            for d in range(1, 7):
                h.celda(2, base + sem * 7 + d, "", "sem")
            h.combinar(2, base + sem * 7, 2, base + sem * 7 + 6)
            for d in range(7):
                h.celda(3, base + sem * 7 + d, "LMMJVSD"[d], "enc")
                h.anchos[base + sem * 7 + d] = 4.5
        h.celda(2, base + 28, "Trabaja", "enc")
        h.celda(2, base + 29, "Libre", "enc")
        h.celda(3, base + 28, "días", "enc")
        h.celda(3, base + 29, "días", "enc")
        h.anchos[base + 28] = h.anchos[base + 29] = 8
        dias_idx = {d: i for i, d in enumerate(DIAS_SEMANA)}
        fila = 4
        for d in datos:
            p, malla = d["persona"], d["malla"]
            horarios = sorted({f["horario"] for f in malla})
            jornadas = {f["jornada"] for f in malla}
            turno = (malla[0]["grupo_turno"] if malla else p["grupo_turno"]) or "—"
            jornada = ("Rotativo" if len(jornadas) > 1 else next(iter(jornadas)).capitalize()) if malla \
                else (p["jornada"].capitalize() if p["jornada"] else "—")
            textos = (
                self._nombre_de(p), p["rol"].replace("_", " ").capitalize(), turno, jornada,
                " / ".join(horarios) if horarios else "Sin malla", p.get("cuadrante") or "—",
                " + ".join(d["modalidades"]) or "—",
            )
            for c, t in enumerate(textos):
                h.celda(fila, c, t, "normal" if c == 0 else "centro")
            trabaja = 0
            for f in malla:
                k = (f["semana_mes"] - 1) * 7 + dias_idx[f["dia_semana"]]
                est = f["estado"]
                if est == "T":
                    texto, estilo = "T", ("noche" if f["jornada"] == "NOCTURNO" else "dia")
                elif est in ("HE", "HEN"):
                    texto, estilo = est, "he"
                elif est == "VAC":
                    texto, estilo = "V", "vac"
                else:
                    texto, estilo = "·", "libre"
                trabaja += est in ("T", "HE", "HEN")
                h.celda(fila, base + k, texto, estilo)
            if malla:
                h.celda(fila, base + 28, trabaja, "centro")
                h.celda(fila, base + 29, 28 - trabaja, "centro")
            fila += 1
        fila += 1
        h.celda(fila, 0, "Verde = día · Morado = noche · · = libre · V = vacaciones · HE/HEN = horas extra", "sub")
        h.congelar = (4, 1)
        hojas = [h]

        if personal_ids is None:
            hojas.append(self._hoja_cuadrantes())
            hojas.append(self._hoja_cobertura(base_dias=1))
        guardar_xlsx(ruta, hojas)
        return len(datos)

    def _hoja_cuadrantes(self) -> Hoja:
        r = self.resumen_cuadrantes()
        h = Hoja("Cuadrantes")
        h.celda(0, 0, "Personal por cuadrante · modalidades (una persona puede usar varias)", "titulo")
        cols = ("Destino", "Total", *MODALIDADES, "Patrull. sin modalidad", "Radio operadores", "Supervisores", "Integrantes")
        for c, t in enumerate(cols):
            h.celda(2, c, t, "enc")
            h.anchos[c] = 14 if c < len(cols) - 1 else 60
        fila = 3
        for destino, d in r["cuadrantes"].items():
            h.celda(fila, 0, destino, "centro")
            h.celda(fila, 1, d["total"], "centro")
            for k, m in enumerate(MODALIDADES):
                n = d["por_modalidad"][m]
                alerta = m == "Móvil" and destino in CUADRANTES and n < MIN_MOVILES_POR_CUADRANTE
                h.celda(fila, 2 + k, n, "alerta" if alerta else "centro")
            h.celda(fila, 2 + len(MODALIDADES), d["patrulleros_sin_modalidad"], "centro")
            h.celda(fila, 3 + len(MODALIDADES), d["por_rol"].get("RADIO_OPERADOR", 0), "centro")
            h.celda(fila, 4 + len(MODALIDADES), d["por_rol"].get("SUPERVISOR", 0), "centro")
            h.celda(fila, 5 + len(MODALIDADES), ", ".join(d["nombres"]), "normal")
            fila += 1
        fila += 1
        h.celda(fila, 0, "Motos (no llevan cuadrante): " + (", ".join(r["motos"]) or "ninguna"), "normal")
        fila += 1
        h.celda(fila, 0, "Sin cuadrante: " + (", ".join(r["sin_cuadrante"]) or "ninguno"), "normal")
        fila += 1
        if r["faltan_movil"]:
            h.celda(fila, 0, "⚠ Cuadrantes sin Móvil: " + ", ".join(r["faltan_movil"]), "alerta")
        else:
            h.celda(fila, 0, "✔ Todos los cuadrantes tienen al menos un Móvil", "ok")
        return h

    def _hoja_cobertura(self, base_dias: int = 1) -> Hoja:
        h = Hoja("Cobertura 24 h")
        h.celda(0, 0, "Horas cubiertas por día (24 = día completo)", "titulo")
        h.celda(2, 0, "Grupo", "enc")
        h.anchos[0] = 30
        for sem in range(4):
            h.celda(2, 1 + sem * 7, f"Semana {sem + 1}", "sem")
            for d in range(1, 7):
                h.celda(2, 1 + sem * 7 + d, "", "sem")
            h.combinar(2, 1 + sem * 7, 2, 1 + sem * 7 + 6)
            for d in range(7):
                h.celda(3, 1 + sem * 7 + d, "LMMJVSD"[d], "enc")
                h.anchos[1 + sem * 7 + d] = 4.5
        h.celda(3, 0, "", "enc")
        fila = 4
        for g in self.cobertura_horaria():
            h.celda(fila, 0, g["nombre"], "normal")
            for k, n in enumerate(g["horas"]):
                h.celda(fila, 1 + k, n, "ok" if n == HORAS_DIA else "alerta")
            fila += 1
        h.congelar = (4, 1)
        return h

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
