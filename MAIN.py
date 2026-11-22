"""Demostración operativa para el Jefe Operativo (La Cisterna)."""

import sqlite3

from capa_datos import RepositorioTurnos
from capa_ley_opciones import ServicioTurnos


def imprimir_calendario(nombre_completo: str, malla: list[dict], modalidades: list[str] | None = None) -> None:
    """Imprime la malla como calendario real (con las fechas de cada día)."""
    from datetime import date

    import calendario as cal

    por_fecha = {date.fromisoformat(f["fecha"]): f for f in malla}
    primero = min(por_fecha)
    anio, mes = primero.year, primero.month
    info = malla[0]
    print(f"\n{'=' * 75}")
    print(f"MALLA {cal.etiqueta_mes(anio, mes).upper()} - {nombre_completo.upper()}")
    print(f"Grupo: Turno {info['grupo_turno']} | Jornada: {info['jornada']} "
          f"| Horario: {info['horario']} | {info['cuadrante'] or 'Sin cuadrante'}"
          + (f" | {' + '.join(modalidades)}" if modalidades else ""))
    print(f"{'=' * 75}")
    print(f"{'Semana':<12}" + "".join(f"{d[:3]:<7}" for d in cal.NOMBRES_DIA))
    print("-" * 75)
    for semana in cal.semanas_del_mes(anio, mes):
        celdas = []
        for d in semana:
            f = por_fecha.get(d)
            celdas.append(f"{d.day:>2}:{f['estado']:<4}" if f and d.month == mes else f"{'':<7}")
        print(f"{semana[0].day:>2}/{semana[0].month:<2} al {semana[-1].day:>2} " + "".join(celdas))
    print("=" * 75)


def demo_individual(servicio, repo):
    # cuadrante y modalidades son propios de la persona (Luis usa moto y bicicleta)
    guardia_id = servicio.crear_integrante(
        "Luis", "PATRULLERO", "A", "DIURNO", cuadrante="Cuadrante 1", modalidades=["Moto", "Bicicleta"]
    )

    opciones = servicio.generar_opciones_malla_mensual(
        grupo_turno="A",
        jornada="DIURNO",
        horario="07:00 a 18:00",
    )

    print(f"Opciones válidas generadas: {len(opciones)}")
    for idx, op in enumerate(opciones, start=1):
        print(f"  [{idx}] {op['nombre_opcion']}")

    servicio.asignar_opcion_a_personal(guardia_id, opciones[0])
    malla = repo.obtener_malla_personal(guardia_id)
    servicio.editar_estado_dia(guardia_id, malla[0]["id"], "HE")

    imprimir_calendario(
        "Luis (Patrullero)", repo.obtener_malla_personal(guardia_id),
        servicio.obtener_modalidades_persona(guardia_id),
    )


def demo_equipo(servicio, repo):
    print("\n\nPLAN DE EQUIPO 24/7")
    nombres = [("Ana", "PATRULLERO", "A", "DIURNO"), ("Bruno", "PATRULLERO", "B", "DIURNO"),
               ("Carla", "PATRULLERO", "A", "NOCTURNO"), ("Diego", "PATRULLERO", "B", "NOCTURNO"),
               ("Elena", "PATRULLERO", "A", "NOCTURNO"),
               ("Fabián", "RADIO_OPERADOR", "A", "DIURNO"), ("Gloria", "RADIO_OPERADOR", "B", "DIURNO"),
               ("Hugo", "RADIO_OPERADOR", "A", "NOCTURNO"), ("Iris", "RADIO_OPERADOR", "B", "NOCTURNO"),
               ("Jorge", "RADIO_OPERADOR", "A", "NOCTURNO")]
    personas = [
        (servicio.crear_integrante(n, rol, grupo, jor), n, rol, jor)
        for n, rol, grupo, jor in nombres
    ]
    opciones = servicio.generar_opciones_equipo(
        personas, {"PATRULLERO": (1, 1), "RADIO_OPERADOR": (1, 1)}
    )
    for op in opciones:
        m = op["metricas"]
        print(f"  {op['nombre_opcion']:<50} cobertura {m['cobertura_pct']:.0f}%")

    elegida = opciones[0]
    servicio.asignar_plan_equipo(elegida, "08:00 a 19:00")
    # cuadrantes y modalidades se reparten por persona (aquí, automáticamente)
    servicio.repartir_cuadrantes_auto()
    servicio.repartir_modalidades_auto()
    print("Personas por cuadrante:", {
        c: d["total"] for c, d in servicio.resumen_cuadrantes()["cuadrantes"].items()
    })
    pid, nombre = personas[0][0], personas[0][1]
    imprimir_calendario(nombre, repo.obtener_malla_personal(pid), servicio.obtener_modalidades_persona(pid))


def main():
    conexion = sqlite3.connect(":memory:")
    repo = RepositorioTurnos(conexion)
    servicio = ServicioTurnos(repo)
    demo_individual(servicio, repo)
    demo_equipo(servicio, repo)


if __name__ == "__main__":
    main()
