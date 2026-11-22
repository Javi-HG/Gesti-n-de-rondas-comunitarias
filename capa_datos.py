"""Capa de persistencia: concentra todo el acceso SQL y transacciones."""

import sqlite3
from datetime import date, timedelta

from constantes_reglas import DIAS_SEMANA


class RepositorioTurnos:
    """Gestiona el almacenamiento de personal, cuadrantes, modalidades y mallas de turnos."""

    def __init__(self, conexion: sqlite3.Connection):
        self.conexion = conexion
        self._cache: dict = {}
        self._cache_version = -1
        try:  # escritura más rápida y lecturas que no se bloquean (en :memory: se ignora)
            self.conexion.execute("PRAGMA journal_mode=WAL")
            self.conexion.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError:
            pass
        self._crear_tablas()

    def _cacheado(self, clave, calcular):
        """Memoriza lecturas repetidas mientras la base no cambie (total_changes sube con
        cualquier escritura de esta conexión, así que nunca se sirve un dato viejo)."""
        version = self.conexion.total_changes
        if version != self._cache_version:
            self._cache.clear()
            self._cache_version = version
        if clave not in self._cache:
            self._cache[clave] = calcular()
        return self._cache[clave]

    # ------------------------------------------------------------------ esquema
    def _crear_tablas(self) -> None:
        with self.conexion:
            self.conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS personal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    rol TEXT NOT NULL,
                    grupo_turno TEXT,
                    jornada TEXT,
                    cuadrante TEXT,
                    movil_id INTEGER
                )
                """
            )
            self.conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS asignaciones_turno (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    personal_id INTEGER NOT NULL,
                    grupo_turno TEXT NOT NULL,
                    jornada TEXT NOT NULL,
                    horario TEXT NOT NULL,
                    cuadrante TEXT NOT NULL,
                    dia_semana TEXT NOT NULL,
                    semana_mes INTEGER NOT NULL,
                    estado TEXT NOT NULL,
                    fecha TEXT,
                    estado_previo TEXT,
                    FOREIGN KEY (personal_id) REFERENCES personal(id)
                )
                """
            )
            # una persona puede usar varias modalidades a la vez
            self.conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS modalidades_persona (
                    personal_id INTEGER NOT NULL,
                    modalidad TEXT NOT NULL,
                    PRIMARY KEY (personal_id, modalidad),
                    FOREIGN KEY (personal_id) REFERENCES personal(id)
                )
                """
            )
        self._migrar()

    def _columnas(self, tabla: str) -> set[str]:
        return {fila[1] for fila in self.conexion.execute(f"PRAGMA table_info({tabla})")}

    def _existe_tabla(self, tabla: str) -> bool:
        return self.conexion.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (tabla,)
        ).fetchone() is not None

    def _migrar(self) -> None:
        """Adapta bases creadas con versiones anteriores."""
        columnas = self._columnas("personal")
        with self.conexion:
            for nueva in ("grupo_turno", "jornada"):
                if nueva not in columnas:
                    self.conexion.execute(f"ALTER TABLE personal ADD COLUMN {nueva} TEXT")
            if "cuadrante" not in columnas:
                # el cuadrante pasa a ser de la persona: se toma el que tenía en su malla
                self.conexion.execute("ALTER TABLE personal ADD COLUMN cuadrante TEXT")
                self.conexion.execute(
                    "UPDATE personal SET cuadrante = NULLIF(("
                    "SELECT cuadrante FROM asignaciones_turno "
                    "WHERE personal_id = personal.id LIMIT 1), '')"
                )
            if "movil_id" not in self._columnas("personal"):
                # móvil (patrullero con modalidad Móvil) al que va asignado un jefe de turno
                self.conexion.execute("ALTER TABLE personal ADD COLUMN movil_id INTEGER")
            if "fecha" not in self._columnas("asignaciones_turno"):
                self.conexion.execute("ALTER TABLE asignaciones_turno ADD COLUMN fecha TEXT")
            if "estado_previo" not in self._columnas("asignaciones_turno"):
                # estado que tenía el día antes de una vacación / licencia (para poder quitarla)
                self.conexion.execute("ALTER TABLE asignaciones_turno ADD COLUMN estado_previo TEXT")
            self._fechar_mallas_antiguas()
            self.conexion.execute("DROP INDEX IF EXISTS idx_asignaciones_persona")
            self.conexion.execute(
                "CREATE INDEX IF NOT EXISTS idx_asignaciones_persona_fecha "
                "ON asignaciones_turno (personal_id, fecha)"
            )
            # el cargo GUARDIA pasó a llamarse PATRULLERO
            self.conexion.execute("UPDATE personal SET rol = 'PATRULLERO' WHERE rol = 'GUARDIA'")
            # modalidad única (tabla antigua) -> modalidades múltiples
            if self._existe_tabla("modalidad_personal"):
                self.conexion.execute(
                    "INSERT OR IGNORE INTO modalidades_persona (personal_id, modalidad) "
                    "SELECT personal_id, modalidad FROM modalidad_personal"
                )
                self.conexion.execute("DROP TABLE modalidad_personal")
        # Las bases antiguas conservan la columna apellido (NOT NULL): se rellena con vacío.
        self._tiene_apellido = "apellido" in self._columnas("personal")

    def _fechar_mallas_antiguas(self) -> None:
        """Las mallas de versiones anteriores eran 4 semanas sin fecha: se ubican en el mes actual
        (la primera semana parte el lunes en o antes del día 1) para no perderlas."""
        antiguas = self.conexion.execute(
            "SELECT id, semana_mes, dia_semana FROM asignaciones_turno WHERE fecha IS NULL"
        ).fetchall()
        if not antiguas:
            return
        hoy = date.today()
        primero = date(hoy.year, hoy.month, 1)
        lunes = primero - timedelta(days=primero.weekday())
        self.conexion.executemany(
            "UPDATE asignaciones_turno SET fecha = ? WHERE id = ?",
            [
                ((lunes + timedelta(days=(sem - 1) * 7 + DIAS_SEMANA.index(dia))).isoformat(), fila_id)
                for fila_id, sem, dia in antiguas
            ],
        )

    # ------------------------------------------------------------------ personal
    def registrar_personal(
        self, nombre: str, rol: str, grupo_turno: str, jornada: str, cuadrante: str | None = None
    ) -> int:
        with self.conexion:
            if self._tiene_apellido:
                cursor = self.conexion.execute(
                    "INSERT INTO personal (nombre, apellido, rol, grupo_turno, jornada, cuadrante) "
                    "VALUES (?, '', ?, ?, ?, ?)",
                    (nombre, rol, grupo_turno, jornada, cuadrante),
                )
            else:
                cursor = self.conexion.execute(
                    "INSERT INTO personal (nombre, rol, grupo_turno, jornada, cuadrante) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (nombre, rol, grupo_turno, jornada, cuadrante),
                )
            return cursor.lastrowid

    def actualizar_nombre(self, personal_id: int, nombre: str) -> bool:
        with self.conexion:
            cursor = self.conexion.execute(
                "UPDATE personal SET nombre = ? WHERE id = ?", (nombre, personal_id)
            )
            return cursor.rowcount > 0

    def actualizar_persona(
        self, personal_id: int, nombre: str, rol: str, grupo_turno: str, jornada: str,
        cuadrante: str | None, movil_id: int | None, modalidades: list[str],
    ) -> None:
        """Actualiza TODOS los datos de la persona en una sola transacción."""
        with self.conexion:
            self.conexion.execute(
                "UPDATE personal SET nombre = ?, rol = ?, grupo_turno = ?, jornada = ?, "
                "cuadrante = ?, movil_id = ? WHERE id = ?",
                (nombre, rol, grupo_turno, jornada, cuadrante, movil_id, personal_id),
            )
            self.conexion.execute(
                "UPDATE asignaciones_turno SET cuadrante = ? WHERE personal_id = ?",
                (cuadrante or "", personal_id),
            )
            self.conexion.execute("DELETE FROM modalidades_persona WHERE personal_id = ?", (personal_id,))
            self.conexion.executemany(
                "INSERT OR IGNORE INTO modalidades_persona (personal_id, modalidad) VALUES (?, ?)",
                [(personal_id, m) for m in modalidades],
            )

    def registrar_varios(self, filas: list[tuple]) -> list[int]:
        """Carga masiva en UNA transacción: si algo falla no se guarda a nadie.
        filas: (nombre, rol, grupo_turno, jornada, cuadrante|None, [modalidades])."""
        ids = []
        with self.conexion:
            for nombre, rol, grupo, jornada, cuadrante, modalidades in filas:
                if self._tiene_apellido:
                    cur = self.conexion.execute(
                        "INSERT INTO personal (nombre, apellido, rol, grupo_turno, jornada, cuadrante) "
                        "VALUES (?, '', ?, ?, ?, ?)", (nombre, rol, grupo, jornada, cuadrante),
                    )
                else:
                    cur = self.conexion.execute(
                        "INSERT INTO personal (nombre, rol, grupo_turno, jornada, cuadrante) "
                        "VALUES (?, ?, ?, ?, ?)", (nombre, rol, grupo, jornada, cuadrante),
                    )
                ids.append(cur.lastrowid)
                self.conexion.executemany(
                    "INSERT OR IGNORE INTO modalidades_persona (personal_id, modalidad) VALUES (?, ?)",
                    [(cur.lastrowid, m) for m in modalidades],
                )
        return ids

    def eliminar_personal(self, personal_id: int) -> None:
        """Elimina a la persona junto con su malla y sus modalidades (una sola transacción)."""
        with self.conexion:
            self.conexion.execute("DELETE FROM asignaciones_turno WHERE personal_id = ?", (personal_id,))
            self.conexion.execute("DELETE FROM modalidades_persona WHERE personal_id = ?", (personal_id,))
            self.conexion.execute("UPDATE personal SET movil_id = NULL WHERE movil_id = ?", (personal_id,))
            self.conexion.execute("DELETE FROM personal WHERE id = ?", (personal_id,))

    def actualizar_perfil_turno(self, personal_id: int, grupo_turno: str, jornada: str) -> None:
        with self.conexion:
            self.conexion.execute(
                "UPDATE personal SET grupo_turno = ?, jornada = ? WHERE id = ?",
                (grupo_turno, jornada, personal_id),
            )

    def _select_personal(self) -> str:
        apellido = "apellido" if self._tiene_apellido else "'' AS apellido"
        return (
            f"SELECT id, nombre, {apellido}, rol, grupo_turno, jornada, cuadrante, movil_id FROM personal"
        )

    def listar_personal(self) -> list[dict]:
        def leer():
            cursor = self.conexion.execute(self._select_personal() + " ORDER BY id")
            columnas = [col[0] for col in cursor.description]
            return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        return [dict(p) for p in self._cacheado("personal", leer)]

    def obtener_persona(self, personal_id: int) -> dict | None:
        cursor = self.conexion.execute(self._select_personal() + " WHERE id = ?", (personal_id,))
        fila = cursor.fetchone()
        if fila is None:
            return None
        return dict(zip([col[0] for col in cursor.description], fila))

    def actualizar_movil(self, personal_id: int, movil_id: int | None) -> None:
        with self.conexion:
            self.conexion.execute(
                "UPDATE personal SET movil_id = ? WHERE id = ?", (movil_id, personal_id)
            )

    # ---------------------------------------------------------------- cuadrantes
    def actualizar_cuadrante(self, personal_ids: list[int], cuadrante: str | None) -> None:
        """Cuadrante propio de cada persona (independiente de su malla). None lo quita."""
        with self.conexion:
            self.conexion.executemany(
                "UPDATE personal SET cuadrante = ? WHERE id = ?",
                [(cuadrante, pid) for pid in personal_ids],
            )
            # la columna de la malla es solo una copia informativa
            self.conexion.executemany(
                "UPDATE asignaciones_turno SET cuadrante = ? WHERE personal_id = ?",
                [(cuadrante or "", pid) for pid in personal_ids],
            )

    # -------------------------------------------------------------------- mallas
    def reemplazar_mallas(
        self, personal_ids: list[int], registros: list[tuple], desde: date, hasta: date
    ) -> None:
        """Borra las mallas de las personas indicadas entre `desde` y `hasta` (inclusive) y guarda
        las nuevas, todo en una única transacción (si algo falla no se pierde lo anterior).

        registros: (personal_id, grupo_turno, jornada, horario, cuadrante, fecha(date), estado)."""
        with self.conexion:
            # las vacaciones y licencias ya cargadas son hechos reales: se conservan al replanificar
            ausencias = [
                fila for pid in personal_ids for fila in self.conexion.execute(
                    "SELECT personal_id, fecha, estado FROM asignaciones_turno "
                    "WHERE personal_id = ? AND fecha BETWEEN ? AND ? AND estado IN ('VAC', 'LM')",
                    (pid, desde.isoformat(), hasta.isoformat()),
                ).fetchall()
            ]
            self.conexion.executemany(
                "DELETE FROM asignaciones_turno WHERE personal_id = ? AND fecha BETWEEN ? AND ?",
                [(pid, desde.isoformat(), hasta.isoformat()) for pid in personal_ids],
            )
            self.conexion.executemany(
                """
                INSERT INTO asignaciones_turno (
                    personal_id, grupo_turno, jornada, horario,
                    cuadrante, dia_semana, semana_mes, estado, fecha
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (pid, grupo, jornada, horario, cuadrante, DIAS_SEMANA[f.weekday()],
                     (f.day - 1) // 7 + 1, estado, f.isoformat())
                    for pid, grupo, jornada, horario, cuadrante, f, estado in registros
                ],
            )
            self.conexion.executemany(
                "UPDATE asignaciones_turno SET estado_previo = estado, estado = ? "
                "WHERE personal_id = ? AND fecha = ?",
                [(est, pid, fecha) for pid, fecha, est in ausencias],
            )

    def aplicar_ausencia(self, personal_id: int, desde: date, hasta: date, estado: str) -> int:
        """Marca vacaciones / licencia médica en los días con malla entre dos fechas (inclusive).
        Guarda lo que había para poder quitarla después. Devuelve los días modificados."""
        with self.conexion:
            self.conexion.execute(
                "UPDATE asignaciones_turno SET estado_previo = CASE WHEN estado IN ('VAC', 'LM') "
                "THEN estado_previo ELSE estado END, estado = ? "
                "WHERE personal_id = ? AND fecha BETWEEN ? AND ?",
                (estado, personal_id, desde.isoformat(), hasta.isoformat()),
            )
            return self.conexion.execute("SELECT changes()").fetchone()[0]

    def quitar_ausencia(self, personal_id: int, desde: date, hasta: date) -> int:
        """Devuelve cada día con vacaciones / licencia a lo que tenía antes (libre si no se sabe)."""
        with self.conexion:
            self.conexion.execute(
                "UPDATE asignaciones_turno SET estado = COALESCE(estado_previo, 'L'), estado_previo = NULL "
                "WHERE personal_id = ? AND fecha BETWEEN ? AND ? AND estado IN ('VAC', 'LM')",
                (personal_id, desde.isoformat(), hasta.isoformat()),
            )
            return self.conexion.execute("SELECT changes()").fetchone()[0]

    def actualizar_celda_turno(self, asignacion_id: int, nuevo_estado: str) -> bool:
        with self.conexion:
            cursor = self.conexion.execute(
                "UPDATE asignaciones_turno SET estado = ?, estado_previo = NULL WHERE id = ?",
                (nuevo_estado, asignacion_id),
            )
            return cursor.rowcount > 0

    def intercambiar_estados(self, asignacion_a: int, asignacion_b: int) -> None:
        """Intercambia el estado de dos días en una sola transacción."""
        with self.conexion:
            fila_a = self.conexion.execute(
                "SELECT estado FROM asignaciones_turno WHERE id = ?", (asignacion_a,)
            ).fetchone()
            fila_b = self.conexion.execute(
                "SELECT estado FROM asignaciones_turno WHERE id = ?", (asignacion_b,)
            ).fetchone()
            if fila_a is None or fila_b is None:
                raise ValueError("Uno de los días ya no existe.")
            self.conexion.execute(
                "UPDATE asignaciones_turno SET estado = ? WHERE id = ?", (fila_b[0], asignacion_a)
            )
            self.conexion.execute(
                "UPDATE asignaciones_turno SET estado = ? WHERE id = ?", (fila_a[0], asignacion_b)
            )

    _COLUMNAS_MALLA = (
        "a.id, a.personal_id, a.grupo_turno, a.jornada, a.horario, COALESCE(p.cuadrante, '') AS cuadrante, "
        "a.dia_semana, a.semana_mes, a.estado, a.fecha"
    )

    def obtener_malla_personal(
        self, personal_id: int, desde: date | None = None, hasta: date | None = None
    ) -> list[dict]:
        """Malla de una persona ordenada por fecha (todo, o solo entre `desde` y `hasta`)."""
        sql = (
            f"SELECT {self._COLUMNAS_MALLA} FROM asignaciones_turno a "
            "JOIN personal p ON p.id = a.personal_id WHERE a.personal_id = ?"
        )
        params: list = [personal_id]
        if desde is not None and hasta is not None:
            sql += " AND a.fecha BETWEEN ? AND ?"
            params += [desde.isoformat(), hasta.isoformat()]
        cursor = self.conexion.execute(sql + " ORDER BY a.fecha, a.id", params)
        columnas = [col[0] for col in cursor.description]
        return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]

    def obtener_mallas_rango(self, desde: date, hasta: date) -> dict[int, list[dict]]:
        """{personal_id: filas} de todo el equipo entre dos fechas, en UNA sola consulta."""
        crudo = self._cacheado(("mallas", desde, hasta), lambda: self._leer_mallas_rango(desde, hasta))
        return {pid: [dict(f) for f in filas] for pid, filas in crudo.items()}

    def _leer_mallas_rango(self, desde: date, hasta: date) -> dict[int, list[dict]]:
        cursor = self.conexion.execute(
            f"SELECT {self._COLUMNAS_MALLA} FROM asignaciones_turno a "
            "JOIN personal p ON p.id = a.personal_id WHERE a.fecha BETWEEN ? AND ? "
            "ORDER BY a.personal_id, a.fecha, a.id",
            (desde.isoformat(), hasta.isoformat()),
        )
        columnas = [col[0] for col in cursor.description]
        res: dict[int, list[dict]] = {}
        for fila in cursor.fetchall():
            d = dict(zip(columnas, fila))
            res.setdefault(d["personal_id"], []).append(d)
        return res

    # --------------------------------------------------------------- modalidades
    def obtener_modalidades(self) -> dict[int, list[str]]:
        """{personal_id: [modalidades]} de todos los que tienen alguna."""
        def leer():
            res: dict[int, list[str]] = {}
            for pid, modalidad in self.conexion.execute(
                "SELECT personal_id, modalidad FROM modalidades_persona ORDER BY personal_id, modalidad"
            ):
                res.setdefault(pid, []).append(modalidad)
            return res
        return {pid: list(m) for pid, m in self._cacheado("modalidades", leer).items()}

    def obtener_modalidades_persona(self, personal_id: int) -> list[str]:
        return self.obtener_modalidades().get(personal_id, [])

    def reemplazar_modalidades(self, modalidades: dict[int, list[str]]) -> None:
        """Deja a cada persona exactamente con las modalidades indicadas."""
        with self.conexion:
            self.conexion.executemany(
                "DELETE FROM modalidades_persona WHERE personal_id = ?",
                [(pid,) for pid in modalidades],
            )
            self.conexion.executemany(
                "INSERT OR IGNORE INTO modalidades_persona (personal_id, modalidad) VALUES (?, ?)",
                [(pid, m) for pid, lista in modalidades.items() for m in lista],
            )

    def agregar_modalidades(self, modalidades: dict[int, list[str]]) -> None:
        """Suma modalidades sin quitar las que la persona ya tenía."""
        with self.conexion:
            self.conexion.executemany(
                "INSERT OR IGNORE INTO modalidades_persona (personal_id, modalidad) VALUES (?, ?)",
                [(pid, m) for pid, lista in modalidades.items() for m in lista],
            )

    def quitar_modalidad(self, personal_ids: list[int], modalidad: str) -> None:
        with self.conexion:
            self.conexion.executemany(
                "DELETE FROM modalidades_persona WHERE personal_id = ? AND modalidad = ?",
                [(pid, modalidad) for pid in personal_ids],
            )
