"""Motor de planificación 4x3 (lógica pura, sin base de datos ni interfaz).

Modelo
------
- Mes de 4 semanas (Lunes a Domingo) = 28 días; cada persona trabaja 16 y descansa 12.
- Ciclo 4x3: bloques de 3 días libres consecutivos; entre bloques se trabajan 3 a 6 días
  (4 es lo normal). El primer y el último bloque del mes pueden quedar partidos.
- Art. 38: jornada diurna -> mínimo MIN_DOMINGOS_LIBRES_DIURNO domingos libres;
  con turnos nocturnos -> mínimo MIN_FINDES_LIBRES_NOCTURNO fines de semana libres.
- Cobertura 24/7: cada rol tiene su dotación mínima de día y de noche, y se resuelve
  de forma independiente por rol.
"""

import random
from functools import lru_cache

from constantes_reglas import (
    DIAS_SEMANA,
    MIN_DOMINGOS_LIBRES_DIURNO,
    MIN_FINDES_LIBRES_NOCTURNO,
    SEMANAS_MES,
)

DIURNO = "DIURNO"
NOCTURNO = "NOCTURNO"
ESTADO_TURNO = "T"
ESTADO_LIBRE = "L"

DIAS_MES = 7 * SEMANAS_MES
DIAS_TRABAJO_MES = 16
LIBRES_POR_BLOQUE = 3
TRABAJO_MIN, TRABAJO_MAX = 3, 6

MODOS = {
    "D": (DIURNO,) * SEMANAS_MES,
    "N": (NOCTURNO,) * SEMANAS_MES,
    "DN": (DIURNO, NOCTURNO, DIURNO, NOCTURNO),
    "ND": (NOCTURNO, DIURNO, NOCTURNO, DIURNO),
}

# nombre, parámetros de búsqueda
ESTRATEGIAS = [
    ("Equipos fijos día / noche", {"modos": ("D", "N"), "exceso": 0.4, "bonus": 0.0}),
    ("Máximo descanso de fin de semana", {"modos": ("D", "N"), "exceso": 0.1, "bonus": 0.6}),
    ("Rotación semanal día / noche", {"modos": ("DN", "ND"), "exceso": 0.4, "bonus": 0.0}),
    ("Mixto (fijos y rotativos)", {"modos": ("D", "N", "DN", "ND"), "exceso": 0.3, "bonus": 0.2}),
    ("Con holgura para ausencias", {"modos": ("D", "N"), "exceso": -0.05, "bonus": 0.0}),
    ("Rotación + fines de semana libres", {"modos": ("DN", "ND"), "exceso": 0.1, "bonus": 0.6}),
]

# Cuando todos tienen jornada asignada nadie rota entre día y noche
ESTRATEGIAS_FIJAS = [
    ("Equilibrada", {"modos": ("D", "N"), "exceso": 0.4, "bonus": 0.0}),
    ("Máximo descanso de fin de semana", {"modos": ("D", "N"), "exceso": 0.1, "bonus": 0.6}),
    ("Con holgura para ausencias", {"modos": ("D", "N"), "exceso": -0.05, "bonus": 0.0}),
    ("Lo más regular posible (4x3 puro)", {"modos": ("D", "N"), "exceso": 0.3, "bonus": 0.0, "irreg": 0.8}),
]

MODOS_POR_JORNADA = {DIURNO: ("D",), NOCTURNO: ("N",), None: tuple(MODOS)}


# ------------------------------------------------------------ catálogo de patrones
def _corridas(seq):
    """[(bit, largo), ...] con bit 0 = trabajo, 1 = libre."""
    res = []
    for bit in seq:
        if res and res[-1][0] == bit:
            res[-1][1] += 1
        else:
            res.append([bit, 1])
    return [(b, n) for b, n in res]


@lru_cache(maxsize=1)
def _catalogo():
    """Todos los patrones de 28 días (1 = libre) que respetan el ciclo 4x3.

    Devuelve (diurnos, nocturnos, irregularidad, findes_libres):
    - diurnos: cumplen domingos libres mínimos (Art. 38 diurno).
    - nocturnos: cumplen fines de semana libres mínimos (Art. 38 nocturno / rotativo).
    - irregularidad: cuánto se aleja del 4x3 puro (0 = perfecto).
    """
    encontrados = set()

    def rec(dias, tipo, trabajo):
        restante = DIAS_MES - len(dias)
        if restante == 0:
            if trabajo == DIAS_TRABAJO_MES:
                encontrados.add(tuple(dias))
            return
        es_trabajo = tipo == "T"
        maximo = TRABAJO_MAX if es_trabajo else LIBRES_POR_BLOQUE
        minimo = TRABAJO_MIN if es_trabajo else LIBRES_POR_BLOQUE
        siguiente = "L" if es_trabajo else "T"
        for largo in range(1, min(maximo, restante) + 1):
            if largo == restante or largo >= minimo:  # bloque completo o final partido
                nuevo = trabajo + (largo if es_trabajo else 0)
                if nuevo <= DIAS_TRABAJO_MES:
                    rec(dias + [0 if es_trabajo else 1] * largo, siguiente, nuevo)

    for tipo in ("T", "L"):  # el primer bloque puede venir partido del mes anterior
        es_trabajo = tipo == "T"
        maximo = TRABAJO_MAX if es_trabajo else LIBRES_POR_BLOQUE
        for largo in range(1, maximo + 1):
            rec([0 if es_trabajo else 1] * largo, "L" if es_trabajo else "T",
                largo if es_trabajo else 0)

    diurnos, nocturnos, irreg, findes = [], [], {}, {}
    for seq in sorted(encontrados):
        corr = _corridas(seq)
        irreg[seq] = sum(abs(n - 4) for b, n in corr[1:-1] if b == 0)
        domingos = sum(seq[7 * w + 6] for w in range(SEMANAS_MES))
        fines = sum(seq[7 * w + 5] and seq[7 * w + 6] for w in range(SEMANAS_MES))
        findes[seq] = fines
        if domingos >= MIN_DOMINGOS_LIBRES_DIURNO:
            diurnos.append(seq)
        if fines >= MIN_FINDES_LIBRES_NOCTURNO:
            nocturnos.append(seq)
    return diurnos, nocturnos, irreg, findes


def minimo_personas(min_dia: int, min_noche: int) -> int:
    """Cota inferior por rol: cada persona puede trabajar como máximo
    (4 - domingos libres mínimos) domingos al mes."""
    domingos_max = SEMANAS_MES - MIN_DOMINGOS_LIBRES_DIURNO
    total = SEMANAS_MES * (min_dia + min_noche)
    return -(-total // domingos_max)


def seq_a_semanas(seq):
    """Convierte un patrón de 28 días a [{'Lunes': 'T', ...}, ...] (4 semanas)."""
    return [
        {
            dia: (ESTADO_LIBRE if seq[7 * s + d] else ESTADO_TURNO)
            for d, dia in enumerate(DIAS_SEMANA)
        }
        for s in range(SEMANAS_MES)
    ]


def grilla_a_semanas(grilla):
    return [
        {dia: grilla[7 * s + d][0] for d, dia in enumerate(DIAS_SEMANA)}
        for s in range(SEMANAS_MES)
    ]


def resumen_patron(seq) -> str:
    """Texto corto para nombrar una opción individual."""
    domingos = sum(seq[7 * w + 6] for w in range(SEMANAS_MES))
    fines = sum(seq[7 * w + 5] and seq[7 * w + 6] for w in range(SEMANAS_MES))
    _d, _n, irreg, _f = _catalogo()
    tipo = "4x3 regular" if irreg[seq] == 0 else "4x3 con ajuste de días"
    return f"{tipo} · {domingos} domingos libres · {fines} fines de semana libres"


def opciones_individuales(jornada: str, cantidad: int = 5):
    """Patrones variados y válidos para una sola persona.

    Primero los 4x3 puros (distintos días de descanso) y luego los más parecidos
    pero lo más distintos entre sí, para ofrecer alternativas reales.
    """
    diurnos, nocturnos, irreg, findes = _catalogo()
    pool = diurnos if jornada == DIURNO else nocturnos

    def distancia(a, b):
        return sum(x != y for x, y in zip(a, b))

    puros = [s for s in pool if irreg[s] == 0]
    elegidas = sorted(puros, key=lambda s: (-findes[s], s))[:cantidad]
    cercanos = [s for s in pool if irreg[s] in (1, 2) and s not in elegidas] or [
        s for s in pool if s not in elegidas
    ]
    while len(elegidas) < cantidad and cercanos:
        mejor = max(
            cercanos,
            key=lambda s: (min(distancia(s, e) for e in elegidas) if elegidas else 0,
                           -irreg[s], findes[s]),
        )
        elegidas.append(mejor)
        cercanos.remove(mejor)
    return elegidas


# ------------------------------------------------------------ evaluación y búsqueda
@lru_cache(maxsize=None)
def _trabajados(modo_clave: str, seq: tuple):
    modo = MODOS[modo_clave]
    return tuple(
        (0 if modo[k // 7] == DIURNO else 1, k) for k in range(DIAS_MES) if seq[k] == 0
    )


def _grilla(modo_clave: str, seq: tuple):
    modo = MODOS[modo_clave]
    return [
        (ESTADO_LIBRE if seq[k] else ESTADO_TURNO, modo[k // 7]) for k in range(DIAS_MES)
    ]


def validar_art38(grilla) -> bool:
    domingos = sum(
        1 for s in range(SEMANAS_MES) if grilla[s * 7 + 6][0] == ESTADO_LIBRE
    )
    findes = sum(
        1 for s in range(SEMANAS_MES)
        if grilla[s * 7 + 5][0] == ESTADO_LIBRE and grilla[s * 7 + 6][0] == ESTADO_LIBRE
    )
    hay_noche = any(est == ESTADO_TURNO and jor == NOCTURNO for est, jor in grilla)
    if hay_noche:
        return findes >= MIN_FINDES_LIBRES_NOCTURNO
    return domingos >= MIN_DOMINGOS_LIBRES_DIURNO


def _costo(cnt, req, exceso: float) -> float:
    total = 0.0
    for t in (0, 1):
        r = req[t]
        for v in cnt[t]:
            d = v - r
            if d < 0:
                total -= d * 10
            elif d > 0:
                if exceso > 0:
                    total += exceso * d
                elif r > 0:
                    total += exceso * min(d, 1)
    return total


def _resolver_rol(n, req, cfg, catalogo, rng, permitidos, iteraciones=3000, reinicios=4):
    """permitidos[i]: modos que puede usar la persona i (una jornada fija = un solo modo)."""
    diurnos, nocturnos, irreg, findes = catalogo
    validas_noche, validas_dia = set(nocturnos), set(diurnos)
    exceso, bonus = cfg["exceso"], cfg["bonus"]
    peso_irreg = cfg.get("irreg", 0.15)
    modos_p = [
        tuple(m for m in cfg["modos"] if m in permitidos[i]) or tuple(permitidos[i])
        for i in range(n)
    ]

    def elegir_seq(modo):
        return rng.choice(diurnos if modo == "D" else nocturnos)

    def compatible(modo, sq):
        return sq in (validas_dia if modo == "D" else validas_noche)

    def bono(sq):
        return bonus * (findes[sq] - MIN_FINDES_LIBRES_NOCTURNO) - peso_irreg * irreg[sq]

    mejor, mejor_costo = None, None
    for _ in range(reinicios):
        est = []
        for i in range(n):
            modo = rng.choice(modos_p[i])
            est.append((modo, elegir_seq(modo)))
        cnt = [[0] * DIAS_MES for _ in range(2)]
        for modo, sq in est:
            for t, i in _trabajados(modo, sq):
                cnt[t][i] += 1
        extra = sum(bono(sq) for _m, sq in est)
        costo = _costo(cnt, req, exceso) - extra
        for _ in range(iteraciones):
            k = rng.randrange(n)
            modo0, sq0 = est[k]
            if rng.random() < 0.3:
                modo1 = rng.choice(modos_p[k])
                sq1 = sq0 if compatible(modo1, sq0) else elegir_seq(modo1)
            else:
                modo1, sq1 = modo0, elegir_seq(modo0)
            if (modo1, sq1) == (modo0, sq0):
                continue
            for t, i in _trabajados(modo0, sq0):
                cnt[t][i] -= 1
            for t, i in _trabajados(modo1, sq1):
                cnt[t][i] += 1
            extra1 = extra - bono(sq0) + bono(sq1)
            costo1 = _costo(cnt, req, exceso) - extra1
            if costo1 <= costo:
                est[k] = (modo1, sq1)
                costo, extra = costo1, extra1
            else:
                for t, i in _trabajados(modo1, sq1):
                    cnt[t][i] -= 1
                for t, i in _trabajados(modo0, sq0):
                    cnt[t][i] += 1
        if mejor_costo is None or costo < mejor_costo:
            mejor, mejor_costo = list(est), costo
    return mejor


def _armar_opcion(estrategia, personas, asign, requerimientos):
    personas_ord = sorted(personas, key=lambda p: (p[2], p[1]))
    asignaciones, conteo = {}, {}
    for pid, _nombre, rol in personas_ord:
        modo, seq = asign[pid]
        grilla = _grilla(modo, seq)
        if not validar_art38(grilla):
            return None
        asignaciones[pid] = {"modo": modo, "seq": seq, "grilla": grilla}
        c = conteo.setdefault(rol, [[0] * DIAS_MES for _ in range(2)])
        for k, (est, jor) in enumerate(grilla):
            if est == ESTADO_TURNO:
                c[0 if jor == DIURNO else 1][k] += 1

    req = {rol: tuple(requerimientos.get(rol, (0, 0))) for rol in conteo}
    total = cumplidos = 0
    avisos = []
    for rol, c in conteo.items():
        faltan = 0
        for t in (0, 1):
            r = req[rol][t]
            if r <= 0:
                continue
            for v in c[t]:
                total += 1
                if v >= r:
                    cumplidos += 1
                else:
                    faltan += r - v
        if faltan:
            n = sum(1 for p in personas_ord if p[2] == rol)
            avisos.append(
                f"{rol}: faltan {faltan} turnos-persona en el mes "
                f"(hay {n}; mínimo teórico {minimo_personas(*req[rol])})."
            )

    findes = [
        sum(
            1 for s in range(SEMANAS_MES)
            if a["grilla"][s * 7 + 5][0] == ESTADO_LIBRE
            and a["grilla"][s * 7 + 6][0] == ESTADO_LIBRE
        )
        for a in asignaciones.values()
    ]
    return {
        "estrategia": estrategia,
        "personas": personas_ord,
        "asignaciones": asignaciones,
        "req": req,
        "conteo": conteo,
        "avisos": avisos,
        "metricas": {
            "cobertura_pct": 100.0 * cumplidos / total if total else 100.0,
            "findes_prom": sum(findes) / len(findes) if findes else 0.0,
        },
    }


def generar_opciones_equipo(personas, requerimientos):
    """personas: [(id, nombre, rol[, jornada])]; requerimientos: {rol: (min_dia, min_noche)}.

    Si una persona trae jornada (DIURNO/NOCTURNO) se respeta; con jornada None el motor decide.
    Devuelve varias opciones distintas (una por estrategia) ordenadas por cobertura.
    """
    jornadas = {p[0]: (p[3] if len(p) > 3 else None) for p in personas}
    personas = [(p[0], p[1], p[2]) for p in personas]
    if len(personas) < 2:
        raise ValueError("Seleccione al menos 2 integrantes.")
    if not any(sum(r) > 0 for r in requerimientos.values()):
        raise ValueError("Indique al menos una persona requerida en algún turno.")

    catalogo = _catalogo()
    por_rol = {}
    for p in personas:
        por_rol.setdefault(p[2], []).append(p)

    opciones, firmas = [], set()
    estrategias = ESTRATEGIAS if any(j is None for j in jornadas.values()) else ESTRATEGIAS_FIJAS
    for nombre, cfg in estrategias:
        for _ in range(4):
            rng = random.Random()
            asign = {}
            for rol, miembros in por_rol.items():
                req = tuple(requerimientos.get(rol, (0, 0)))
                permitidos = [MODOS_POR_JORNADA[jornadas[p[0]]] for p in miembros]
                estados = _resolver_rol(len(miembros), req, cfg, catalogo, rng, permitidos)
                for p, est in zip(miembros, estados):
                    asign[p[0]] = est
            firma = tuple(sorted((pid, e[0], e[1]) for pid, e in asign.items()))
            if firma in firmas:
                continue
            opcion = _armar_opcion(nombre, personas, asign, requerimientos)
            if opcion is None:
                continue
            firmas.add(firma)
            opciones.append(opcion)
            break

    opciones.sort(key=lambda o: (-o["metricas"]["cobertura_pct"], -o["metricas"]["findes_prom"]))
    for i, op in enumerate(opciones, start=1):
        op["nombre_opcion"] = f"Opción {i} · {op['estrategia']}"
    return opciones


# ------------------------------------------------- turnos A y B (cada turno junto)
def _mascara_trabajo(seq) -> int:
    """Bits en 1 = días del mes en que se trabaja."""
    return sum(1 << k for k, libre in enumerate(seq) if not libre)


def opciones_turnos_ab(personas, cantidad: int = 4):
    """Patrones para que todo el turno A trabaje junto y todo el turno B también.

    personas: [(id, nombre, rol, grupo, jornada)] con grupo 'A' o 'B'.
    Todos los integrantes de un turno comparten los mismos días de trabajo y de descanso
    (sus horarios pueden diferir). Se buscan pares de patrones que se complementen para
    cubrir el mes sin días vacíos, respetando el Art. 38 en ambos turnos.
    """
    diurnos, nocturnos, irreg, findes = _catalogo()
    miembros = {"A": [], "B": []}
    for p in personas:
        if p[3] in miembros:
            miembros[p[3]].append(p)
    if not miembros["A"] or not miembros["B"]:
        raise ValueError("Los turnos A y B necesitan al menos un integrante cada uno.")

    def pool(grupo):
        # si alguien del turno es nocturno rige la regla más exigente
        return nocturnos if any(p[4] == NOCTURNO for p in miembros[grupo]) else diurnos

    combos = {}  # (rol, jornada) -> [hay en A, hay en B]
    for indice, grupo in enumerate(("A", "B")):
        for p in miembros[grupo]:
            combos.setdefault((p[2], p[4]), [False, False])[indice] = True

    candidatos = []
    for sa in pool("A"):
        ma = _mascara_trabajo(sa)
        for sb in pool("B"):
            mb = _mascara_trabajo(sb)
            huecos = 0
            for hay_a, hay_b in combos.values():
                cubierto = (ma if hay_a else 0) | (mb if hay_b else 0)
                huecos += DIAS_MES - bin(cubierto).count("1")
            puntaje = 20 * huecos + irreg[sa] + irreg[sb] - 0.3 * (findes[sa] + findes[sb])
            candidatos.append((puntaje, huecos, sa, sb))
    candidatos.sort(key=lambda c: (c[0], c[2], c[3]))

    elegidas, usados_a, usados_b = [], set(), set()
    for puntaje, huecos, sa, sb in candidatos:
        if sa in usados_a or sb in usados_b:
            continue  # opciones realmente distintas entre sí
        elegidas.append((huecos, sa, sb))
        usados_a.add(sa)
        usados_b.add(sb)
        if len(elegidas) == cantidad:
            break

    opciones = []
    for i, (huecos, sa, sb) in enumerate(elegidas, start=1):
        ma, mb = _mascara_trabajo(sa), _mascara_trabajo(sb)
        avisos = []
        for (rol, jornada), (hay_a, hay_b) in combos.items():
            cubierto = (ma if hay_a else 0) | (mb if hay_b else 0)
            faltan = DIAS_MES - bin(cubierto).count("1")
            if faltan:
                donde = "solo en el turno A" if hay_a and not hay_b else (
                    "solo en el turno B" if hay_b and not hay_a else "en ambos turnos")
                avisos.append(
                    f"{rol} {'de día' if jornada == DIURNO else 'de noche'} ({donde}): "
                    f"{faltan} días del mes sin nadie de turno."
                )
        opciones.append(
            {
                "nombre_opcion": f"Opción {i}",
                "seq_a": sa,
                "seq_b": sb,
                "avisos": avisos,
                "metricas": {
                    "huecos": huecos,
                    "ambos_turnos": bin(ma & mb).count("1"),
                    "findes_a": findes[sa],
                    "findes_b": findes[sb],
                },
            }
        )
    return opciones
