"""Capa de persistencia: concentra todo el acceso SQL y transacciones."""

import sqlite3


class RepositorioTurnos:
    """Gestiona el almacenamiento de personal, cuadrantes, modalidades y mallas de turnos."""

    def __init__(self, conexion: sqlite3.Connection):
        self.conexion = conexion
        self._crear_tablas()

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
                    cuadrante TEXT
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

    def eliminar_personal(self, personal_id: int) -> None:
        """Elimina a la persona junto con su malla y sus modalidades (una sola transacción)."""
        with self.conexion:
            self.conexion.execute("DELETE FROM asignaciones_turno WHERE personal_id = ?", (personal_id,))
            self.conexion.execute("DELETE FROM modalidades_persona WHERE personal_id = ?", (personal_id,))
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
            f"SELECT id, nombre, {apellido}, rol, grupo_turno, jornada, cuadrante FROM personal"
        )

    def listar_personal(self) -> list[dict]:
        cursor = self.conexion.execute(self._select_personal() + " ORDER BY id")
        columnas = [col[0] for col in cursor.description]
        return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]

    def obtener_persona(self, personal_id: int) -> dict | None:
        cursor = self.conexion.execute(self._select_personal() + " WHERE id = ?", (personal_id,))
        fila = cursor.fetchone()
        if fila is None:
            return None
        return dict(zip([col[0] for col in cursor.description], fila))

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
    def guardar_malla_completa(self, registros: list[tuple]) -> None:
        """Guarda en una sola transacción atómica toda una propuesta de malla."""
        with self.conexion:
            self._insertar_registros(registros)

    def reemplazar_mallas(self, personal_ids: list[int], registros: list[tuple]) -> None:
        """Borra las mallas previas de las personas indicadas y guarda las nuevas,
        todo en una única transacción (si algo falla no se pierde la malla anterior)."""
        with self.conexion:
            self.conexion.executemany(
                "DELETE FROM asignaciones_turno WHERE personal_id = ?",
                [(pid,) for pid in personal_ids],
            )
            self._insertar_registros(registros)

    def _insertar_registros(self, registros: list[tuple]) -> None:
        self.conexion.executemany(
            """
            INSERT INTO asignaciones_turno (
                personal_id, grupo_turno, jornada, horario,
                cuadrante, dia_semana, semana_mes, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            registros,
        )

    def actualizar_celda_turno(self, asignacion_id: int, nuevo_estado: str) -> bool:
        with self.conexion:
            cursor = self.conexion.execute(
                "UPDATE asignaciones_turno SET estado = ? WHERE id = ?",
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

    def obtener_malla_personal(self, personal_id: int) -> list[dict]:
        """Malla del mes; el cuadrante devuelto es siempre el propio de la persona."""
        cursor = self.conexion.execute(
            """
            SELECT a.id, a.grupo_turno, a.jornada, a.horario,
                   COALESCE(p.cuadrante, '') AS cuadrante,
                   a.dia_semana, a.semana_mes, a.estado
            FROM asignaciones_turno a
            JOIN personal p ON p.id = a.personal_id
            WHERE a.personal_id = ?
            ORDER BY a.semana_mes, a.id
            """,
            (personal_id,),
        )
        columnas = [col[0] for col in cursor.description]
        return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]

    # --------------------------------------------------------------- modalidades
    def obtener_modalidades(self) -> dict[int, list[str]]:
        """{personal_id: [modalidades]} de todos los que tienen alguna."""
        res: dict[int, list[str]] = {}
        for pid, modalidad in self.conexion.execute(
            "SELECT personal_id, modalidad FROM modalidades_persona ORDER BY personal_id, modalidad"
        ):
            res.setdefault(pid, []).append(modalidad)
        return res

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
