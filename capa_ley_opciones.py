"""Capa de lógica de negocio: reglas 4x3, validación legal y edición."""

import re
from datetime import date, timedelta

import calendario as cal
from constantes_reglas import (
    ROL_JEFE_TURNO,
    etiqueta_rol,
    DESTINOS_SERVICIO,
    FERIA,
    MIN_MOVILES_POR_CUADRANTE,
    CUADRANTES,
    DIAS_SEMANA,
    ESTADOS_AUSENCIA,
    ESTADOS_CELDA,
    ESTADOS_LIBRES,
    MIN_PERSONAS_POR_DIA,
    MIN_POR_TURNO_MODALIDAD,
    NOMBRES_AUSENCIA,
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
from cobertura_horaria import HORAS_DIA, cobertura_fechas, elegir_horarios, rangos_horas
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
        hoy = date.today()
        self.periodo = (hoy.year, hoy.month)  # mes que se está viendo / planificando
        self.avisos_empalme: list[str] = []  # avisos de la última asignación

    # ----------------------------------------------------------------- período
    def fijar_periodo(self, anio: int, mes: int) -> None:
        if not (2000 <= anio <= 2100 and 1 <= mes <= 12):
            raise ValueError("Mes o año fuera de rango.")
        self.periodo = (anio, mes)

    def mover_periodo(self, meses: int) -> None:
        anio, mes = self.periodo
        total = anio * 12 + (mes - 1) + meses
        self.fijar_periodo(total // 12, total % 12 + 1)

    def etiqueta_periodo(self) -> str:
        return cal.etiqueta_mes(*self.periodo)

    def _rango_mes(self) -> tuple[date, date]:
        return cal.primer_dia(*self.periodo), cal.ultimo_dia(*self.periodo)

    @staticmethod
    def _con_fecha(fila: dict) -> dict:
        fila = dict(fila)
        if isinstance(fila["fecha"], str):
            fila["fecha"] = date.fromisoformat(fila["fecha"])
        return fila

    def malla_vista(self, personal_id: int) -> list[dict]:
        """Malla de la persona en la grilla del calendario del mes (incluye días vecinos)."""
        desde, hasta = cal.rango_vista(*self.periodo)
        return [self._con_fecha(f) for f in self.repositorio.obtener_malla_personal(personal_id, desde, hasta)]

    def semanas_calendario(self) -> list[list[date]]:
        return cal.semanas_del_mes(*self.periodo)

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

    # ------------------------------------------------- edición completa y filtros
    TIPOS_FILTRO = ("Móvil", "Moto", "Bicicleta", "Infantería", "Radio operador", "Jefe de turno", "Supervisor")
    SIN_CUADRANTE_FILTRO = "__sin_cuadrante__"

    def editar_integrante(
        self,
        personal_id: int,
        nombre: str,
        rol: str,
        grupo_turno: str,
        jornada: str,
        cuadrante: str | None = None,
        modalidades: list[str] | None = None,
        movil_id: int | None = None,
    ) -> list[str]:
        """Edita todos los datos de la persona (valida todo antes de guardar).
        Devuelve avisos para mostrar al usuario (p. ej. malla a replanificar)."""
        actual = self.repositorio.obtener_persona(personal_id)
        if actual is None:
            raise ValueError("El integrante no existe.")
        nombre = (nombre or "").strip()
        if not nombre:
            raise ValueError("El nombre no puede quedar vacío.")
        if rol not in ROLES_PERSONAL:
            raise ValueError(f"Cargo inválido. Debe ser uno de: {ROLES_PERSONAL}")
        self._validar_perfil_turno(grupo_turno, jornada)
        modalidades = self._normalizar_modalidades(modalidades)
        if modalidades and rol != ROL_PATRULLERO:
            raise ValueError("Solo los patrulleros pueden tener modalidad.")
        cuadrante = cuadrante or None
        self._validar_destino(cuadrante, rol, modalidades)
        if rol != ROL_JEFE_TURNO:
            movil_id = None
        elif movil_id is not None:
            movil = self.repositorio.obtener_persona(movil_id)
            mods_movil = (
                modalidades if movil_id == personal_id
                else self.repositorio.obtener_modalidades().get(movil_id, [])
            )
            if (movil is None or movil_id == personal_id or movil["rol"] != ROL_PATRULLERO
                    or "Móvil" not in mods_movil):
                raise ValueError("El móvil debe ser otro patrullero con modalidad Móvil.")
        self.repositorio.actualizar_persona(
            personal_id, nombre, rol, grupo_turno, jornada, cuadrante, movil_id, modalidades
        )
        # un jefe que iba en este móvil lo pierde si ya no es patrullero con Móvil
        self._aplicar_reglas_destino([personal_id])
        avisos = []
        cambio_turno = (actual["grupo_turno"], actual["jornada"], actual["rol"]) != (grupo_turno, jornada, rol)
        if cambio_turno and self.repositorio.obtener_malla_personal(personal_id):
            avisos.append(
                "Cambió su turno, jornada o cargo: la malla ya guardada se mantiene tal cual. "
                "Vuelva a planificar o asigne una malla individual para que calce con el nuevo perfil."
            )
        return avisos

    def filtrar_personal(
        self,
        texto: str = "",
        cuadrante: str | None = None,
        turno: str | None = None,
        jornada: str | None = None,
        tipo: str | None = None,
    ) -> list[dict]:
        """Búsqueda y filtros combinados (todos opcionales; se exige que cumpla todos).
        texto: parte del nombre (sin importar mayúsculas ni tildes).
        cuadrante: nombre, o SIN_CUADRANTE_FILTRO para quienes no tienen.
        tipo: una modalidad (Móvil/Moto/Bicicleta/Infantería) o un cargo (Radio operador,
        Jefe de turno, Supervisor). Cada resultado incluye la clave 'modalidades'."""
        mods = self.repositorio.obtener_modalidades()
        buscado = self._plano(texto)
        por_cargo = {etiqueta_rol(r): r for r in ROLES_PERSONAL}
        resultado = []
        for p in self.repositorio.listar_personal():
            m = mods.get(p["id"], [])
            if buscado and buscado not in self._plano(f"{p['nombre']} {p.get('apellido') or ''}"):
                continue
            if cuadrante == self.SIN_CUADRANTE_FILTRO:
                if p.get("cuadrante"):
                    continue
            elif cuadrante and p.get("cuadrante") != cuadrante:
                continue
            if turno and p["grupo_turno"] != turno:
                continue
            if jornada and p["jornada"] != jornada:
                continue
            if tipo:
                if tipo in por_cargo:
                    if p["rol"] != por_cargo[tipo]:
                        continue
                elif tipo not in m:
                    continue
            resultado.append({**p, "modalidades": m})
        return resultado

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
        roles.update({"jefe de turno": ROL_JEFE_TURNO, "jefe": ROL_JEFE_TURNO,
                      "radio": "RADIO_OPERADOR", "radio operador": "RADIO_OPERADOR",
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
            "Cargo: Patrullero · Radio operador · Supervisor · Jefe de turno.",
            "Turno: A o B.   Jornada: Diurno o Nocturno.",
            "Cuadrante (opcional): Cuadrante 1 a 6 (o solo el número). Feria solo para bicicletas. "
            "Las motos no llevan cuadrante.",
            "Modalidades (opcional, solo patrulleros): Móvil, Moto, Infantería, Bicicleta. "
            "Varias separadas por +  (ej.: Móvil + Moto).",
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
        perfil = {p["id"]: (p["grupo_turno"], p["jornada"]) for p in self.repositorio.listar_personal()}
        por_turno = {}  # (grupo, jornada, modalidad) -> personas
        for pid in patrulleros:
            for m in actuales.get(pid, []):
                k = (*perfil.get(pid, (None, None)), m)
                por_turno[k] = por_turno.get(k, 0) + 1
        nuevas = {}
        for pid in objetivo:
            if actuales.get(pid):
                continue
            g, j = perfil.get(pid, (None, None))
            faltan = [m for m, mn in MIN_POR_TURNO_MODALIDAD.items() if por_turno.get((g, j, m), 0) < mn]
            if conteo["Móvil"] < meta_movil:
                m = "Móvil"
            elif faltan:  # primero se completan las 2 motos y 2 bicicletas de su turno
                m = min(faltan, key=lambda x: (por_turno.get((g, j, x), 0), MODALIDADES.index(x)))
            else:
                m = min(MODALIDADES, key=lambda x: (conteo[x], MODALIDADES.index(x)))
            conteo[m] += 1
            por_turno[(g, j, m)] = por_turno.get((g, j, m), 0) + 1
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
        # un jefe de turno deja de ir en un móvil cuando ese patrullero ya no usa Móvil
        for j in self.repositorio.listar_personal():
            if j["rol"] == ROL_JEFE_TURNO and j.get("movil_id") in personal_ids:
                if "Móvil" not in modalidades.get(j["movil_id"], []):
                    self.repositorio.actualizar_movil(j["id"], None)

    def obtener_modalidades(self) -> dict[int, list[str]]:
        return self.repositorio.obtener_modalidades()

    def obtener_mallas_equipo(self) -> list[dict]:
        """Persona + malla del mes elegido de todo el equipo (para la vista de equipo)."""
        modalidades = self.repositorio.obtener_modalidades()
        desde, hasta = self._rango_mes()
        mallas = self.repositorio.obtener_mallas_rango(desde, hasta)
        return [
            {
                "persona": p,
                "malla": [self._con_fecha(f) for f in mallas.get(p["id"], [])],
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

    @staticmethod
    def cumple_descanso_calendario(jornada: str, estados: dict, anio: int, mes: int) -> bool:
        """Art. 38 sobre el mes REAL: `estados` es {fecha: estado} (puede incluir días vecinos).

        Diurno: al menos 2 domingos del mes libres. Nocturno (o rotativo): al menos 2 fines de
        semana completos (sábado + domingo) libres, contando el fin de semana por su domingo."""
        domingos = [d for d in cal.dias_del_mes(anio, mes) if d.weekday() == 6]
        if jornada == "DIURNO":
            return sum(1 for d in domingos if estados.get(d) in ESTADOS_LIBRES) >= MIN_DOMINGOS_LIBRES_DIURNO
        libres = sum(
            1 for d in domingos
            if estados.get(d) in ESTADOS_LIBRES and estados.get(d - timedelta(days=1)) in ESTADOS_LIBRES
        )
        return libres >= MIN_FINDES_LIBRES_NOCTURNO

    def _guardar_proyeccion(self, items: list[dict], comun: bool) -> None:
        """Proyecta ciclos de 28 días sobre el mes elegido y los guarda.

        items: [{"pid","nombre","grupo","jornada","vals":[28 × (estado, jornada_dia)],
                 "horario": f(jornada_dia)->horario, "cuadrante"}].
        La fase del ciclo se elige para que el primer día continúe el mes anterior y el último
        calce con el siguiente. Con comun=True todos usan la misma fase (se mantiene la coordinación)."""
        anio, mes = self.periodo
        desde, hasta = self._rango_mes()
        previas = self.repositorio.obtener_mallas_rango(desde - timedelta(days=28), hasta + timedelta(days=28))
        secuencias = []
        for it in items:
            vec = {}
            for f in previas.get(it["pid"], []):
                fecha = date.fromisoformat(f["fecha"]) if isinstance(f["fecha"], str) else f["fecha"]
                if fecha < desde or fecha > hasta:  # solo lo que queda FUERA del mes
                    vec[fecha] = 1 if f["estado"] in ESTADOS_LIBRES else 0
            it["_bits"] = [1 if e in ESTADOS_LIBRES else 0 for e, _j in it["vals"]]
            it["_vec"] = vec
            secuencias.append((it["_bits"], vec))
        fases = cal.elegir_fase(secuencias, anio, mes, comun)

        registros, avisos = [], []
        for it, fase in zip(items, fases):
            proy = cal.proyectar(it["vals"], anio, mes, fase)
            estados = {d: e for d, (e, _j) in proy.items()}
            if not self.cumple_descanso_calendario(it["jornada"], estados, anio, mes):
                raise ValueError(f"La malla de {it['nombre']} incumple el Art. 38 en {cal.etiqueta_mes(anio, mes)}.")
            for d in cal.dias_del_mes(anio, mes):
                estado, jd = proy[d]
                registros.append((it["pid"], it["grupo"], jd, it["horario"](jd), it["cuadrante"], d, estado))
            viol, _desaj = cal.puntaje_fase(it["_bits"], anio, mes, fase, it["_vec"])
            if viol:
                avisos.append(
                    f"{it['nombre']}: el empalme con el mes vecino no calza del todo "
                    f"({viol} bloque(s) fuera del ciclo 4x3). Revise los primeros/últimos días."
                )
        self.repositorio.reemplazar_mallas([it["pid"] for it in items], registros, desde, hasta)
        self.avisos_empalme = avisos

    def asignar_opcion_a_personal(
        self, personal_id: int, opcion_seleccionada: dict
    ) -> None:
        """Ubica la opción elegida en el mes seleccionado, reemplazando la malla de ese mes.
        El cuadrante y las modalidades son propios de la persona y no se modifican."""
        persona = self.repositorio.obtener_persona(personal_id)
        if persona is None:
            raise ValueError("El integrante no existe.")
        jornada, horario = opcion_seleccionada["jornada"], opcion_seleccionada["horario"]
        vals = [
            (semana[dia], jornada) for semana in opcion_seleccionada["semanas"] for dia in DIAS_SEMANA
        ]
        self._guardar_proyeccion([{
            "pid": personal_id, "nombre": persona["nombre"], "grupo": opcion_seleccionada["grupo_turno"],
            "jornada": jornada, "vals": vals, "horario": lambda _jd: horario,
            "cuadrante": persona.get("cuadrante") or "",
        }], comun=False)

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
        items = []
        for pid, grupo, grilla, perfil in validados:
            h_dia = horario_de.get(pid, horarios[0])
            items.append({
                "pid": pid, "nombre": perfil.get("nombre", str(pid)), "grupo": grupo,
                "jornada": self._jornada_efectiva(j for _e, j in grilla), "vals": list(grilla),
                "horario": (lambda jd, h=h_dia: HORARIO_NOCTURNO if jd == "NOCTURNO" else h),
                "cuadrante": perfil.get("cuadrante") or "",
            })
        self._guardar_proyeccion(items, comun=True)
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

        items = []
        for pid, nombre, _rol, grupo, jornada in sorted(personas, key=lambda p: (p[3], p[1].lower())):
            seq = opcion["seq_a"] if grupo == "A" else opcion["seq_b"]
            if not self.cumple_descanso_legal(jornada, seq_a_semanas(seq)):
                raise ValueError(f"El patrón del turno {grupo} incumple el Art. 38 para {nombre}.")
            h_dia = horario_de.get(pid, horarios_diurnos[0] if horarios_diurnos else HORARIO_NOCTURNO)
            items.append({
                "pid": pid, "nombre": nombre, "grupo": grupo, "jornada": jornada,
                "vals": [("L" if libre else "T", jornada) for libre in seq],
                "horario": (lambda jd, h=h_dia: HORARIO_NOCTURNO if jd == "NOCTURNO" else h),
                "cuadrante": cuadrante_de.get(pid, ""),
            })
        self._guardar_proyeccion(items, comun=True)
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

    def asignar_jefe_turno(
        self, jefe_id: int, movil_id: int | None, destino: str | None
    ) -> None:
        """Asignación MANUAL del jefe de turno a un móvil (patrullero con modalidad Móvil)
        y/o a un cuadrante. Nunca se hace automáticamente."""
        jefe = self.repositorio.obtener_persona(jefe_id)
        if jefe is None or jefe["rol"] != ROL_JEFE_TURNO:
            raise ValueError("Seleccione un integrante con cargo Jefe de turno.")
        if movil_id is not None:
            movil = self.repositorio.obtener_persona(movil_id)
            mods = self.repositorio.obtener_modalidades().get(movil_id, [])
            if movil is None or movil["rol"] != ROL_PATRULLERO or "Móvil" not in mods:
                raise ValueError("El móvil debe ser un patrullero con modalidad Móvil.")
        self._validar_destino(destino, ROL_JEFE_TURNO, [])
        self.repositorio.actualizar_movil(jefe_id, movil_id)
        self.repositorio.actualizar_cuadrante([jefe_id], destino)

    def moviles_disponibles(self) -> list[dict]:
        """Patrulleros con modalidad Móvil (a los que se puede sumar un jefe de turno)."""
        mods = self.repositorio.obtener_modalidades()
        return [
            p for p in self.repositorio.listar_personal()
            if p["rol"] == ROL_PATRULLERO and "Móvil" in mods.get(p["id"], [])
        ]

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
            if p["rol"] != ROL_JEFE_TURNO  # el jefe de turno solo se asigna a mano
            and (not solo_sin_cuadrante or actual[p["id"]] is None)
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
        nombres_por_id = {q["id"]: self._nombre_de(q) for q in self.repositorio.listar_personal()}
        for p in self.repositorio.listar_personal():
            if p["rol"] == ROL_JEFE_TURNO and p.get("cuadrante") in destinos:
                destinos[p["cuadrante"]].setdefault("jefes", []).append(
                    (self._nombre_de(p), nombres_por_id.get(p.get("movil_id")))
                )
            mods = modalidades.get(p["id"], []) if p["rol"] == ROL_PATRULLERO else []
            if p.get("cuadrante") not in destinos:
                if p["rol"] != ROL_JEFE_TURNO:  # el jefe sin cuadrante es normal: se asigna a mano
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
        """Horas cubiertas (de 24) en cada día del mes elegido, por cargo y por Móvil de cada cuadrante.

        Un turno nocturno del día anterior cubre las primeras horas de la mañana siguiente.
        Devuelve [{"nombre", "horas": [una cifra por día], "faltan": [conjuntos], "completo", "es_cargo"}]."""
        modalidades = self.repositorio.obtener_modalidades()
        desde, hasta = self._rango_mes()
        dias = cal.dias_del_mes(*self.periodo)
        mallas = self.repositorio.obtener_mallas_rango(desde - timedelta(days=1), hasta)
        por_grupo: dict[str, list] = {}
        for p in self.repositorio.listar_personal():
            malla = mallas.get(p["id"])
            if not malla:
                continue
            turnos = [
                (date.fromisoformat(f["fecha"]), f["horario"])
                for f in malla if f["estado"] in ("T", "HE", "HEN")
            ]
            claves = [p["rol"]]
            es_movil = "Móvil" in modalidades.get(p["id"], [])
            if p["rol"] == ROL_PATRULLERO and es_movil and p.get("cuadrante") in CUADRANTES:
                claves.append(f"Móvil · {p['cuadrante']}")
            for clave in claves:
                por_grupo.setdefault(clave, []).extend(turnos)
        orden = [r for r in ROLES_PERSONAL if r in por_grupo] + [
            f"Móvil · {c}" for c in CUADRANTES
        ]
        resultado = []
        for nombre in orden:
            cubiertas = cobertura_fechas(por_grupo.get(nombre, []), dias)
            faltan = [set(range(HORAS_DIA)) - c for c in cubiertas]
            etiqueta = etiqueta_rol(nombre) if nombre in ROLES_PERSONAL else nombre
            resultado.append({
                "nombre": etiqueta, "horas": [len(c) for c in cubiertas], "faltan": faltan,
                "completo": all(len(c) == HORAS_DIA for c in cubiertas),
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
                f"(p. ej. el día {k + 1}: falta {rangos_horas(f)})."
            )
        return avisos

    # ------------------------------------------------------------------- Excel
    def _encabezado_dias(self, h: Hoja, fila: int, col: int) -> list:
        """Tres filas de encabezado con el mes, la letra del día y el número de cada fecha."""
        dias = cal.dias_del_mes(*self.periodo)
        h.celda(fila, col, cal.etiqueta_mes(*self.periodo), "sem")
        for k in range(1, len(dias)):
            h.celda(fila, col + k, "", "sem")
        h.combinar(fila, col, fila, col + len(dias) - 1)
        for k, d in enumerate(dias):
            estilo = "sem" if d.weekday() >= 5 else "enc"
            h.celda(fila + 1, col + k, cal.LETRAS_DIA[d.weekday()], estilo)
            h.celda(fila + 2, col + k, d.day, estilo)
            h.anchos[col + k] = 4.5
        return dias

    def exportar_excel(self, ruta: str, personal_ids: list[int] | None = None) -> int:
        """Guarda la malla del mes elegido en un archivo Excel (.xlsx). Sin ids = todo el equipo
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
        h.celda(0, 0, f"Malla mensual 4x3 · {cal.etiqueta_mes(*self.periodo)} · Seguridad La Cisterna", "titulo")
        for c, t in enumerate(encabezados):
            h.celda(2, c, t, "enc")
            h.combinar(2, c, 4, c)
            h.celda(3, c, "", "enc")
            h.celda(4, c, "", "enc")
            h.anchos[c] = (22, 16, 8, 12, 22, 14, 24)[c]
        dias = self._encabezado_dias(h, 2, base)
        n = len(dias)
        h.celda(2, base + n, "Trabaja", "enc")
        h.celda(2, base + n + 1, "Libre", "enc")
        for c in (base + n, base + n + 1):
            h.celda(3, c, "días", "enc")
            h.celda(4, c, "", "enc")
            h.anchos[c] = 8
        nombres_id = {x["id"]: self._nombre_de(x) for x in self.repositorio.listar_personal()} \
            if any(x["persona"].get("movil_id") for x in datos) else {}
        fila = 5
        for d in datos:
            p, malla = d["persona"], d["malla"]
            horarios = sorted({f["horario"] for f in malla})
            jornadas = {f["jornada"] for f in malla}
            turno = (malla[0]["grupo_turno"] if malla else p["grupo_turno"]) or "—"
            jornada = ("Rotativo" if len(jornadas) > 1 else next(iter(jornadas)).capitalize()) if malla \
                else (p["jornada"].capitalize() if p["jornada"] else "—")
            textos = (
                self._nombre_de(p), etiqueta_rol(p["rol"]), turno, jornada,
                " / ".join(horarios) if horarios else "Sin malla", p.get("cuadrante") or "—",
                (f"Va en el móvil de {nombres_id[p['movil_id']]}"
                 if p.get("movil_id") in nombres_id else " + ".join(d["modalidades"]) or "—"),
            )
            for c, t in enumerate(textos):
                h.celda(fila, c, t, "normal" if c == 0 else "centro")
            trabaja = 0
            for f in malla:
                k = (f["fecha"] - dias[0]).days
                est = f["estado"]
                if est == "T":
                    texto, estilo = "T", ("noche" if f["jornada"] == "NOCTURNO" else "dia")
                elif est in ("HE", "HEN"):
                    texto, estilo = est, "he"
                elif est == "VAC":
                    texto, estilo = "V", "vac"
                elif est == "LM":
                    texto, estilo = "LM", "lm"
                else:
                    texto, estilo = "·", "libre"
                trabaja += est in ("T", "HE", "HEN")
                h.celda(fila, base + k, texto, estilo)
            if malla:
                h.celda(fila, base + n, trabaja, "centro")
                h.celda(fila, base + n + 1, n - trabaja, "centro")
            fila += 1
        fila += 1
        h.celda(
            fila, 0,
            "Verde = día · Morado = noche · · = libre · V = vacaciones · LM = licencia médica · HE/HEN = horas extra",
            "sub",
        )
        h.congelar = (5, 1)
        hojas = [h]

        if personal_ids is None:
            hojas.append(self._hoja_cuadrantes())
            hojas.append(self._hoja_cobertura())
        guardar_xlsx(ruta, hojas)
        return len(datos)

    def _hoja_cuadrantes(self) -> Hoja:
        r = self.resumen_cuadrantes()
        h = Hoja("Cuadrantes")
        h.celda(0, 0, "Personal por cuadrante · modalidades (una persona puede usar varias)", "titulo")
        cols = (
            "Destino", "Total", *MODALIDADES, "Patrull. sin modalidad",
            "Radio operadores", "Supervisores", "Jefes de turno", "Integrantes",
        )
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
            h.celda(fila, 5 + len(MODALIDADES), d["por_rol"].get("JEFE_TURNO", 0), "centro")
            h.celda(fila, 6 + len(MODALIDADES), ", ".join(d["nombres"]), "normal")
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

    def _hoja_cobertura(self) -> Hoja:
        h = Hoja("Cobertura 24 h")
        h.celda(0, 0, f"Horas cubiertas por día (24 = día completo) · {cal.etiqueta_mes(*self.periodo)}", "titulo")
        h.celda(2, 0, "Grupo", "enc")
        h.combinar(2, 0, 4, 0)
        h.celda(3, 0, "", "enc")
        h.celda(4, 0, "", "enc")
        h.anchos[0] = 30
        self._encabezado_dias(h, 2, 1)
        fila = 5
        for g in self.cobertura_horaria():
            h.celda(fila, 0, g["nombre"], "normal")
            for k, n in enumerate(g["horas"]):
                h.celda(fila, 1 + k, n, "ok" if n == HORAS_DIA else "alerta")
            fila += 1
        conteo = self.personas_por_dia()
        if any(conteo):
            fila += 1
            h.celda(fila, 0, f"Personas en servicio (mín. {MIN_PERSONAS_POR_DIA} por día)", "normal")
            for k, n in enumerate(conteo):
                h.celda(fila, 1 + k, n, "ok" if n >= MIN_PERSONAS_POR_DIA else "alerta")
            for r in self.dias_bajo_minimo_modalidad():
                fila += 1
                h.celda(fila, 0, f"{r['modalidad']}s · {r['jornada'].lower()} (mín. {r['minimo']})", "normal")
                for k, n in enumerate(r["conteo"]):
                    h.celda(fila, 1 + k, n, "ok" if n >= r["minimo"] else "alerta")
        h.congelar = (5, 1)
        return h

    # ------------------------------------------------- vacaciones y licencias médicas
    def personas_por_dia(self, dias: list[date] | None = None) -> list[int]:
        """Cuántas personas trabajan (T, HE, HEN) cada día; por defecto los días del mes elegido."""
        dias = dias or cal.dias_del_mes(*self.periodo)
        mallas = self.repositorio.obtener_mallas_rango(dias[0], dias[-1])
        cuenta = {d: 0 for d in dias}
        self._dias_planificados = set()
        for filas in mallas.values():
            for f in filas:
                d = date.fromisoformat(f["fecha"]) if isinstance(f["fecha"], str) else f["fecha"]
                if d in cuenta:
                    self._dias_planificados.add(d)
                    if f["estado"] in ("T", "HE", "HEN"):
                        cuenta[d] += 1
        return [cuenta[d] for d in dias]

    def dias_bajo_minimo(self, dias: list[date] | None = None) -> list[tuple[date, int]]:
        """Días con menos de MIN_PERSONAS_POR_DIA personas trabajando (solo si ya hay mallas)."""
        dias = dias or cal.dias_del_mes(*self.periodo)
        conteo = self.personas_por_dia(dias)
        # un día que nadie tiene planificado (mes aún sin malla) no se marca como falta
        return [
            (d, n) for d, n in zip(dias, conteo)
            if n < MIN_PERSONAS_POR_DIA and d in self._dias_planificados
        ]

    def resumen_turnos_modalidad(self) -> list[dict]:
        """Por turno (A/B × jornada): cuántos patrulleros usan Moto y Bicicleta y si cumplen el mínimo."""
        mods = self.repositorio.obtener_modalidades()
        filas = []
        for g in GRUPOS_TURNO:
            for j in JORNADAS:
                pats = [p for p in self.repositorio.listar_personal()
                        if p["rol"] == ROL_PATRULLERO and p["grupo_turno"] == g and p["jornada"] == j]
                if not pats:
                    continue
                fila = {"turno": g, "jornada": j, "personas": len(pats)}
                for m, minimo in MIN_POR_TURNO_MODALIDAD.items():
                    fila[m] = sum(1 for p in pats if m in mods.get(p["id"], []))
                fila["cumple"] = all(fila[m] >= mn for m, mn in MIN_POR_TURNO_MODALIDAD.items())
                filas.append(fila)
        return filas

    def trabajando_por_dia_modalidad(self, modalidad: str, jornada: str, dias: list[date] | None = None) -> list[int]:
        """Cuántos patrulleros con esa modalidad trabajan cada día en esa jornada (sin ausentes)."""
        dias = dias or cal.dias_del_mes(*self.periodo)
        mods = self.repositorio.obtener_modalidades()
        con = {p["id"] for p in self.repositorio.listar_personal()
               if p["rol"] == ROL_PATRULLERO and modalidad in mods.get(p["id"], [])}
        cuenta = {d: 0 for d in dias}
        for pid, filas in self.repositorio.obtener_mallas_rango(dias[0], dias[-1]).items():
            if pid not in con:
                continue
            for f in filas:
                d = date.fromisoformat(f["fecha"]) if isinstance(f["fecha"], str) else f["fecha"]
                if d in cuenta and f["estado"] in ("T", "HE", "HEN") and f["jornada"] == jornada:
                    cuenta[d] += 1
        return [cuenta[d] for d in dias]

    def dias_bajo_minimo_modalidad(self) -> list[dict]:
        """[{"modalidad","jornada","dias":[(fecha, n)]}] con los días bajo el mínimo (Moto/Bicicleta).
        Solo se revisan días ya planificados y modalidades que alguien usa."""
        dias = cal.dias_del_mes(*self.periodo)
        self.personas_por_dia(dias)  # deja listos los días planificados
        mods = self.repositorio.obtener_modalidades()
        usadas = {m for ms in mods.values() for m in ms}
        res = []
        for m, minimo in MIN_POR_TURNO_MODALIDAD.items():
            if m not in usadas:
                continue
            for j in JORNADAS:
                cnt = self.trabajando_por_dia_modalidad(m, j, dias)
                malos = [(d, n) for d, n in zip(dias, cnt) if n < minimo and d in self._dias_planificados]
                res.append({"modalidad": m, "jornada": j, "minimo": minimo, "conteo": cnt, "dias": malos})
        return res

    @staticmethod
    def _rango_fechas(desde: date, hasta: date) -> list[date]:
        if hasta < desde:
            raise ValueError("La fecha «hasta» no puede ser anterior a «desde».")
        if (hasta - desde).days > 366:
            raise ValueError("El rango no puede superar un año.")
        return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]

    def aplicar_ausencia(self, personal_id: int, desde: date, hasta: date, estado: str) -> dict:
        """Carga vacaciones (VAC) o licencia médica (LM) entre dos fechas, inclusive.
        Devuelve {"dias", "aplicados", "sin_malla", "bajo_minimo": [(fecha, n)]}.
        Solo se marcan los días que ya tienen malla; no suma ni resta turnos del Art. 38
        porque ambos estados cuentan como días libres."""
        if estado not in ESTADOS_AUSENCIA:
            raise ValueError(f"Solo se pueden cargar por fechas: {ESTADOS_AUSENCIA}")
        if self.repositorio.obtener_persona(personal_id) is None:
            raise ValueError("El integrante no existe.")
        dias = self._rango_fechas(desde, hasta)
        if not self.repositorio.obtener_malla_personal(personal_id, desde, hasta):
            raise ValueError(
                "La persona no tiene malla en esas fechas. Planifique primero ese período "
                "(cambie de mes con ◀ ▶ y asigne la malla)."
            )
        aplicados = self.repositorio.aplicar_ausencia(personal_id, desde, hasta, estado)
        return {
            "dias": len(dias), "aplicados": aplicados, "sin_malla": len(dias) - aplicados,
            "bajo_minimo": self.dias_bajo_minimo(dias),
        }

    def quitar_ausencia(self, personal_id: int, desde: date, hasta: date) -> int:
        """Quita vacaciones / licencia de esas fechas: cada día vuelve a lo que tenía antes."""
        self._rango_fechas(desde, hasta)
        return self.repositorio.quitar_ausencia(personal_id, desde, hasta)

    def _validar_edicion(self, personal_id: int, cambios: dict[int, str]) -> None:
        """Simula los cambios {id_fila: nuevo_estado} y exige el Art. 38 en cada mes tocado."""
        desde, hasta = cal.rango_vista(*self.periodo)
        filas = [self._con_fecha(f) for f in self.repositorio.obtener_malla_personal(
            personal_id, desde - timedelta(days=14), hasta + timedelta(days=14))]
        por_id = {f["id"]: f for f in filas}
        if any(i not in por_id for i in cambios):
            raise ValueError("Los días no pertenecen a este integrante.")
        estados = {f["fecha"]: cambios.get(f["id"], f["estado"]) for f in filas}
        for anio, mes in sorted({(por_id[i]["fecha"].year, por_id[i]["fecha"].month) for i in cambios}):
            del_mes = [f for f in filas if (f["fecha"].year, f["fecha"].month) == (anio, mes)]
            jornada = self._jornada_efectiva(f["jornada"] for f in del_mes)
            if not self.cumple_descanso_calendario(jornada, estados, anio, mes):
                raise ValueError(
                    f"Cambio rechazado: dejaría a la persona sin el descanso dominical / de fin de "
                    f"semana que exige el Art. 38 en {cal.etiqueta_mes(anio, mes)}."
                )

    @staticmethod
    def _rechazar_si_ausente(*estados: str) -> None:
        """Quien está de vacaciones o con licencia no puede ser asignado a un turno ese día."""
        for est in estados:
            if est in ESTADOS_AUSENCIA:
                raise ValueError(
                    f"Ese día la persona está con {NOMBRES_AUSENCIA[est].lower()} y no puede ser "
                    "asignada a un turno. Quite primero la ausencia («Quitar ausencia…»)."
                )

    def intercambiar_dias(self, personal_id: int, asignacion_a: int, asignacion_b: int) -> bool:
        """Mueve un día de turno a otro casillero (intercambia ambos), validando el Art. 38."""
        if asignacion_a == asignacion_b:
            return False
        desde, hasta = cal.rango_vista(*self.periodo)
        filas = {f["id"]: f for f in self.repositorio.obtener_malla_personal(personal_id, desde, hasta)}
        if asignacion_a not in filas or asignacion_b not in filas:
            raise ValueError("Los días no pertenecen a este integrante.")
        estado_a, estado_b = filas[asignacion_a]["estado"], filas[asignacion_b]["estado"]
        self._rechazar_si_ausente(estado_a, estado_b)
        if estado_a == estado_b:
            return False  # nada que mover
        self._validar_edicion(personal_id, {asignacion_a: estado_b, asignacion_b: estado_a})
        self.repositorio.intercambiar_estados(asignacion_a, asignacion_b)
        return True

    def editar_estado_dia(
        self, personal_id: int, asignacion_id: int, nuevo_estado: str
    ) -> bool:
        """Permite editar una celda (T, L, VAC, HE, HEN) validando descanso legal."""
        if nuevo_estado not in ESTADOS_CELDA:
            raise ValueError(f"Estado inválido. Permitidos: {ESTADOS_CELDA}")
        if not self.repositorio.obtener_malla_personal(personal_id):
            raise ValueError("El integrante no tiene turnos asignados.")
        actual = next((f["estado"] for f in self.repositorio.obtener_malla_personal(personal_id)
                       if f["id"] == asignacion_id), None)
        if actual is None:
            raise ValueError("El día no pertenece a este integrante.")
        self._rechazar_si_ausente(actual)
        if nuevo_estado in ESTADOS_AUSENCIA:
            raise ValueError("Las vacaciones y licencias se cargan por fechas (botones «Ausencias por fechas»).")
        self._validar_edicion(personal_id, {asignacion_id: nuevo_estado})
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
