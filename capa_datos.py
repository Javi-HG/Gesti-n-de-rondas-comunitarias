"""Capa de persistencia: concentra todo el acceso SQL y transacciones."""

import sqlite3


class RepositorioTurnos:
    """Gestiona el almacenamiento de personal y mallas de turnos."""

    def __init__(self, conexion: sqlite3.Connection):
        self.conexion = conexion
        self._crear_tablas()

    def _crear_tablas(self) -> None:
        with self.conexion:
            self.conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS personal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    apellido TEXT NOT NULL,
                    rol TEXT NOT NULL
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

    def registrar_personal(self, nombre: str, apellido: str, rol: str) -> int:
        with self.conexion:
            cursor = self.conexion.execute(
                "INSERT INTO personal (nombre, apellido, rol) VALUES (?, ?, ?)",
                (nombre, apellido, rol),
            )
            return cursor.lastrowid

    def guardar_malla_completa(self, registros: list[tuple]) -> None:
        """Guarda en una sola transacción atómica toda una propuesta de malla."""
        with self.conexion:
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

    def obtener_malla_personal(self, personal_id: int) -> list[dict]:
        cursor = self.conexion.execute(
            """
            SELECT id, grupo_turno, jornada, horario, cuadrante,
                   dia_semana, semana_mes, estado
            FROM asignaciones_turno
            WHERE personal_id = ?
            ORDER BY semana_mes, id
            """,
            (personal_id,),
        )
        columnas = [col[0] for col in cursor.description]
        return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]