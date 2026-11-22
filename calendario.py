"""Calendario real y empalme entre meses (motor puro, sin base de datos ni interfaz).

El motor de turnos calcula ciclos de 28 días (4 semanas, lunes a domingo). Aquí esos ciclos se
proyectan sobre meses reales (28 a 31 días, que parten en distinto día de la semana).

Como todos los patrones del catálogo son cíclicos (el final del ciclo empalma con su inicio),
proyectarlos mantiene intactos los bloques de trabajo (3 a 6 días) y de descanso (3 días).
Para empalmar con otro mes se elige la «fase» (0 a 3 semanas de desplazamiento): así el
primer día del mes continúa lo que venía del mes anterior y el último día calza con el siguiente.
"""

from datetime import date, timedelta

CICLO = 28
NOMBRES_MES = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)
NOMBRES_MES_CORTO = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
NOMBRES_DIA = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
LETRAS_DIA = "LMMJVSD"
FASES = 4  # desplazamientos de 0, 7, 14 y 21 días: mantienen cada día de la semana en su lugar

MIN_TRABAJO, MAX_TRABAJO, BLOQUE_LIBRE = 3, 6, 3


def etiqueta_mes(anio: int, mes: int) -> str:
    return f"{NOMBRES_MES[mes - 1]} {anio}"


def primer_dia(anio: int, mes: int) -> date:
    return date(anio, mes, 1)


def ultimo_dia(anio: int, mes: int) -> date:
    return primer_dia(*mes_siguiente(anio, mes)) - timedelta(days=1)


def mes_anterior(anio: int, mes: int) -> tuple[int, int]:
    return (anio - 1, 12) if mes == 1 else (anio, mes - 1)


def mes_siguiente(anio: int, mes: int) -> tuple[int, int]:
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def dias_del_mes(anio: int, mes: int) -> list[date]:
    d, fin = primer_dia(anio, mes), ultimo_dia(anio, mes)
    return [d + timedelta(days=k) for k in range((fin - d).days + 1)]


def lunes_inicial(anio: int, mes: int) -> date:
    d = primer_dia(anio, mes)
    return d - timedelta(days=d.weekday())


def semanas_del_mes(anio: int, mes: int) -> list[list[date]]:
    """Filas lunes-domingo que cubren el mes (incluye días del mes anterior/siguiente)."""
    lunes, fin = lunes_inicial(anio, mes), ultimo_dia(anio, mes)
    semanas = []
    while lunes <= fin:
        semanas.append([lunes + timedelta(days=k) for k in range(7)])
        lunes += timedelta(days=7)
    return semanas


def rango_vista(anio: int, mes: int) -> tuple[date, date]:
    """Primer y último día de la grilla de calendario (de lunes a domingo)."""
    semanas = semanas_del_mes(anio, mes)
    return semanas[0][0], semanas[-1][-1]


def indice_ciclo(fecha: date, anio: int, mes: int, fase: int) -> int:
    """Posición (0-27) del ciclo de 28 días que le toca a `fecha` en esta fase."""
    return ((fecha - lunes_inicial(anio, mes)).days + 7 * fase) % CICLO


def proyectar(valores28, anio: int, mes: int, fase: int, margen: int = CICLO) -> dict[date, object]:
    """{fecha: valor} para el mes y `margen` días antes y después (extensión cíclica)."""
    ini = primer_dia(anio, mes) - timedelta(days=margen)
    fin = ultimo_dia(anio, mes) + timedelta(days=margen)
    resultado, d = {}, ini
    while d <= fin:
        resultado[d] = valores28[indice_ciclo(d, anio, mes, fase)]
        d += timedelta(days=1)
    return resultado


def _corridas(bits: list[int]) -> list[tuple[int, int]]:
    res: list[list[int]] = []
    for b in bits:
        if res and res[-1][0] == b:
            res[-1][1] += 1
        else:
            res.append([b, 1])
    return [(b, n) for b, n in res]


def violaciones_empalme(bits: list[int]) -> int:
    """Cuántos bloques interiores rompen el ciclo (bit 1 = libre, 0 = trabajo).

    El primer y el último bloque quedan fuera: pueden estar cortados por el borde de la ventana.
    Bloque de trabajo válido: 3 a 6 días. Bloque de descanso válido: exactamente 3 días.
    """
    corridas = _corridas(bits)
    malos = 0
    for b, n in corridas[1:-1]:
        if b == 0 and not (MIN_TRABAJO <= n <= MAX_TRABAJO):
            malos += 1
        elif b == 1 and n != BLOQUE_LIBRE:
            malos += 1
    return malos


def _contiguos(datos: dict[date, int], desde: date, paso: int, maximo: int = CICLO) -> list[tuple[date, int]]:
    """Días consecutivos con datos a partir de `desde` (hacia atrás si paso=-1)."""
    salida, d = [], desde
    while d in datos and len(salida) < maximo:
        salida.append((d, datos[d]))
        d += timedelta(days=paso)
    return salida


def puntaje_fase(bits28, anio: int, mes: int, fase: int, vecinos: dict[date, int]) -> tuple[int, int]:
    """(violaciones de empalme, días que no coinciden) de una fase frente a los meses vecinos.

    `vecinos`: {fecha: 1 libre / 0 trabaja} de lo ya guardado FUERA del mes elegido.
    """
    proy = proyectar(bits28, anio, mes, fase)
    dias = dias_del_mes(anio, mes)
    previos = list(reversed(_contiguos(vecinos, dias[0] - timedelta(days=1), -1)))
    siguientes = _contiguos(vecinos, dias[-1] + timedelta(days=1), +1)
    linea = [b for _d, b in previos] + [proy[d] for d in dias] + [b for _d, b in siguientes]
    desajuste = sum(1 for d, b in previos + siguientes if proy.get(d) != b)
    return violaciones_empalme(linea), desajuste


def elegir_fase(secuencias: list[tuple[list[int], dict[date, int]]], anio: int, mes: int,
                comun: bool = True) -> list[int]:
    """Fase para cada secuencia [(bits28, vecinos)].

    comun=True: una sola fase para todos (conserva la coordinación del equipo).
    comun=False: cada secuencia elige la suya.
    """
    if not secuencias:
        return []
    puntajes = [[puntaje_fase(bits, anio, mes, f, vec) for f in range(FASES)] for bits, vec in secuencias]
    if comun:
        totales = [
            (sum(p[f][0] for p in puntajes), sum(p[f][1] for p in puntajes)) for f in range(FASES)
        ]
        mejor = min(range(FASES), key=lambda f: (totales[f], f))
        return [mejor] * len(secuencias)
    return [min(range(FASES), key=lambda f: (p[f], f)) for p in puntajes]
