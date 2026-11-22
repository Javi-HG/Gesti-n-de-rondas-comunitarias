"""Cobertura horaria de 24 horas: qué horas de cada día quedan atendidas.

Motor puro (sin base de datos ni interfaz). El mes de 28 días se trata como cíclico:
el turno nocturno del último día termina en la mañana del primer día del mes siguiente.
"""

DIAS_MES = 28
HORAS_DIA = 24


def parsear_horario(horario: str) -> tuple[int, int]:
    """'07:00 a 18:00' -> (7, 18)."""
    ini, fin = horario.split(" a ")
    return int(ini.split(":")[0]), int(fin.split(":")[0])


def horas_turno(horario: str) -> list[tuple[int, int]]:
    """Pares (desplazamiento_de_día, hora) que cubre un turno que parte en el día base."""
    ini, fin = parsear_horario(horario)
    if ini < fin:
        return [(0, h) for h in range(ini, fin)]
    return [(0, h) for h in range(ini, HORAS_DIA)] + [(1, h) for h in range(0, fin)]


def cobertura_por_dia(turnos) -> list[set[int]]:
    """turnos: iterable de (indice_dia 0..27, horario). Devuelve las horas cubiertas por día."""
    dias = [set() for _ in range(DIAS_MES)]
    for k, horario in turnos:
        for desp, hora in horas_turno(horario):
            dias[(k + desp) % DIAS_MES].add(hora)
    return dias


def rangos_horas(horas) -> str:
    """{18, 19} -> '18:00–20:00'; {0..6, 18, 19} -> '00:00–07:00, 18:00–20:00'."""
    faltan = sorted(horas)
    if not faltan:
        return ""
    rangos, ini, prev = [], faltan[0], faltan[0]
    for h in faltan[1:]:
        if h != prev + 1:
            rangos.append((ini, prev + 1))
            ini = h
        prev = h
    rangos.append((ini, prev + 1))
    return ", ".join(f"{a:02d}:00–{b:02d}:00" for a, b in rangos)


def elegir_horarios(personas: list[dict], horarios: list[str], vueltas: int = 3) -> dict:
    """Elige el horario diurno de cada persona para que cada grupo (cargo) cubra las 24 horas.

    personas: [{"id", "grupo", "dias": [28 valores: None | "D" | "N"]}]
    horarios: horarios diurnos permitidos. El turno nocturno es fijo (20:00 a 07:00).
    Devuelve {id: horario_diurno} solo para quienes trabajan algún día diurno.
    Criterio: minimizar las horas sin cubrir; a igualdad, repartir mejor la dotación.
    """
    from constantes_reglas import HORARIO_NOCTURNO

    conteo: dict[str, list[list[int]]] = {}

    def tabla(grupo):
        return conteo.setdefault(grupo, [[0] * HORAS_DIA for _ in range(DIAS_MES)])

    def sumar(grupo, dias, horario_dia, signo):
        t = tabla(grupo)
        for k, tipo in enumerate(dias):
            if tipo is None:
                continue
            for desp, hora in horas_turno(horario_dia if tipo == "D" else HORARIO_NOCTURNO):
                t[(k + desp) % DIAS_MES][hora] += signo

    def costo(grupo, dias, horario_dia):
        """(horas sin cubrir, sobre-cobertura) de las celdas que toca esta persona."""
        t = tabla(grupo)
        tocadas = set()
        for k, tipo in enumerate(dias):
            if tipo == "D":
                for desp, hora in horas_turno(horario_dia):
                    tocadas.add(((k + desp) % DIAS_MES, hora))
        # el costo se mide sobre el día completo para ver el hueco real
        dias_tocados = {d for d, _h in tocadas}
        huecos = sum(1 for d in dias_tocados for h in range(HORAS_DIA) if t[d][h] + (1 if (d, h) in tocadas else 0) == 0)
        exceso = sum((t[d][h] + (1 if (d, h) in tocadas else 0)) ** 2 for d, h in tocadas)
        return huecos, exceso

    elegidos: dict = {}
    diurnas = [p for p in personas if "D" in p["dias"]]
    for p in personas:  # primero lo fijo: los turnos nocturnos
        sumar(p["grupo"], [("N" if t == "N" else None) for t in p["dias"]], horarios[0], +1)
    for i, p in enumerate(diurnas):  # reparto inicial
        elegidos[p["id"]] = horarios[i % len(horarios)]
        sumar(p["grupo"], [("D" if t == "D" else None) for t in p["dias"]], elegidos[p["id"]], +1)
    for _ in range(vueltas):
        cambio = False
        for p in diurnas:
            solo_d = [("D" if t == "D" else None) for t in p["dias"]]
            sumar(p["grupo"], solo_d, elegidos[p["id"]], -1)
            mejor = min(horarios, key=lambda h: (costo(p["grupo"], solo_d, h), horarios.index(h)))
            cambio |= mejor != elegidos[p["id"]]
            elegidos[p["id"]] = mejor
            sumar(p["grupo"], solo_d, mejor, +1)
        if not cambio:
            break
    return elegidos


def cobertura_fechas(turnos, dias) -> list[set[int]]:
    """Horas cubiertas en cada fecha de `dias`. turnos: iterable de (fecha, horario).

    Un turno nocturno que parte la víspera cubre las primeras horas del día siguiente."""
    from datetime import timedelta

    por_fecha = {d: set() for d in dias}
    for fecha, horario in turnos:
        for desp, hora in horas_turno(horario):
            d = fecha + timedelta(days=desp)
            if d in por_fecha:
                por_fecha[d].add(hora)
    return [por_fecha[d] for d in dias]
