"""Demostración operativa para el Jefe Operativo (La Cisterna)."""

import sqlite3
from capa_datos import RepositorioTurnos
from capa_ley_opciones import ServicioTurnos


def imprimir_tabla_semanal(nombre_completo: str, malla: list[dict]) -> None:
    print(f"\n{'=' * 75}")
    print(f"MALLA MENSUAL 4x3 - {nombre_completo.upper()}")
    print(f"Grupo: Turno {malla[0]['grupo_turno']} | Jornada: {malla[0]['jornada']} "
          f"| Horario: {malla[0]['horario']} | {malla[0]['cuadrante']}")
    print(f"{'=' * 75}")
    print(f"{'Semana':<10} {'Lun':<6} {'Mar':<6} {'Mié':<6} {'Jue':<6} {'Vie':<6} {'Sáb':<6} {'Dom':<6}")
    print("-" * 75)

    semanas = {1: [], 2: [], 3: [], 4: []}
    for fila in malla:
        semanas[fila["semana_mes"]].append(fila["estado"])

    for num_sem, estados in semanas.items():
        fila_str = f"Semana {num_sem:<3} " + "".join(f"{est:<6}" for est in estados)
        print(fila_str)
    print("=" * 75)


def main():
    conexion = sqlite3.connect(":memory:")
    repo = RepositorioTurnos(conexion)
    servicio = ServicioTurnos(repo)

    # 1. Jefe Operativo registra personal
    guardia_id = servicio.crear_integrante("Luis", "Letelier", "GUARDIA")

    # 2. Genera las 3 opciones legales (Art. 38 Código del Trabajo)
    opciones = servicio.generar_opciones_malla_mensual(
        grupo_turno="A",
        jornada="DIURNO",
        horario="07:00 a 18:00",
        cuadrante="Cuadrante 1",
    )

    print(f"Opciones válidas generadas: {len(opciones)}")
    for idx, op in enumerate(opciones, start=1):
        print(f"  [{idx}] {op['nombre_opcion']} - Cumple descanso legal dominical")

    # 3. Asigna la Opción 1 y edita un día a Horas Extras (HE)
    servicio.asignar_opcion_a_personal(guardia_id, opciones[0])
    malla = repo.obtener_malla_personal(guardia_id)
    servicio.editar_estado_dia(guardia_id, malla[0]["id"], "HE")

    # 4. Muestra la tabla final
    malla_final = repo.obtener_malla_personal(guardia_id)
    imprimir_tabla_semanal("Luis Letelier (Guardia)", malla_final)


if __name__ == "__main__":
    main()