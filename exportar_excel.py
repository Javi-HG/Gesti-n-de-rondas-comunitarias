"""Exporta mallas a un archivo Excel (.xlsx) sin dependencias externas (solo biblioteca estándar)."""

import re
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

# estilos: índice -> (fuente_negrita, color_texto, color_fondo, alineación_centrada)
_ESTILOS = [
    (False, "000000", None, False),   # 0 normal
    (True, "FFFFFF", "5B2A86", True),  # 1 encabezado morado
    (True, "5B2A86", "EDE4F5", True),  # 2 encabezado semana
    (False, "FFFFFF", "2E9E5B", True),  # 3 trabaja de día
    (False, "FFFFFF", "5B2A86", True),  # 4 trabaja de noche
    (False, "6B6B7B", "ECECF2", True),  # 5 libre
    (False, "7A5200", "FFE6A8", True),  # 6 vacaciones
    (True, "FFFFFF", "B8731A", True),   # 7 horas extra
    (False, "000000", None, True),      # 8 texto centrado
    (True, "5B2A86", None, False),      # 9 título
    (False, "1F7A44", "DDF3E6", True),  # 10 cobertura completa
    (True, "B3261E", "FBE3E1", True),   # 11 cobertura incompleta / alerta
    (True, "000000", "F6F6FA", False),  # 12 subtítulo gris
]
EST = {"normal": 0, "enc": 1, "sem": 2, "dia": 3, "noche": 4, "libre": 5, "vac": 6, "he": 7,
       "centro": 8, "titulo": 9, "ok": 10, "alerta": 11, "sub": 12}


def _col(n: int) -> str:
    """0 -> A, 27 -> AB"""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class Hoja:
    def __init__(self, nombre: str):
        self.nombre = nombre[:31]
        self.filas: dict[int, dict[int, tuple]] = {}
        self.anchos: dict[int, float] = {}
        self.combinadas: list[str] = []
        self.congelar: tuple[int, int] | None = None  # (filas, columnas)

    def celda(self, fila: int, col: int, valor, estilo: str = "normal") -> None:
        self.filas.setdefault(fila, {})[col] = (valor, EST[estilo])

    def combinar(self, f1, c1, f2, c2) -> None:
        self.combinadas.append(f"{_col(c1)}{f1 + 1}:{_col(c2)}{f2 + 1}")

    def xml(self) -> str:
        partes = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
        if self.congelar:
            f, c = self.congelar
            partes.append(
                '<sheetViews><sheetView workbookViewId="0"><pane '
                + (f'xSplit="{c}" ' if c else "") + (f'ySplit="{f}" ' if f else "")
                + f'topLeftCell="{_col(c)}{f + 1}" activePane="bottomRight" state="frozen"/></sheetView></sheetViews>'
            )
        if self.anchos:
            partes.append("<cols>" + "".join(
                f'<col min="{c + 1}" max="{c + 1}" width="{w}" customWidth="1"/>'
                for c, w in sorted(self.anchos.items())) + "</cols>")
        partes.append("<sheetData>")
        for f in sorted(self.filas):
            partes.append(f'<row r="{f + 1}">')
            for c in sorted(self.filas[f]):
                valor, est = self.filas[f][c]
                ref = f"{_col(c)}{f + 1}"
                if isinstance(valor, bool) or valor is None or valor == "":
                    partes.append(f'<c r="{ref}" s="{est}"/>')
                elif isinstance(valor, (int, float)):
                    partes.append(f'<c r="{ref}" s="{est}"><v>{valor}</v></c>')
                else:
                    partes.append(
                        f'<c r="{ref}" s="{est}" t="inlineStr"><is><t xml:space="preserve">'
                        f"{escape(str(valor))}</t></is></c>"
                    )
            partes.append("</row>")
        partes.append("</sheetData>")
        if self.combinadas:
            partes.append(f'<mergeCells count="{len(self.combinadas)}">'
                          + "".join(f'<mergeCell ref="{r}"/>' for r in self.combinadas) + "</mergeCells>")
        partes.append("</worksheet>")
        return "".join(partes)


def _styles_xml() -> str:
    fuentes, rellenos, xfs = [], ['<fill><patternFill patternType="none"/></fill>',
                                  '<fill><patternFill patternType="gray125"/></fill>'], []
    mapa_f, mapa_r = {}, {}
    for negrita, color, fondo, centro in _ESTILOS:
        kf = (negrita, color)
        if kf not in mapa_f:
            mapa_f[kf] = len(fuentes)
            fuentes.append(f'<font>{"<b/>" if negrita else ""}<sz val="10"/><color rgb="FF{color}"/>'
                           f'<name val="Calibri"/></font>')
        if fondo and fondo not in mapa_r:
            mapa_r[fondo] = len(rellenos)
            rellenos.append(f'<fill><patternFill patternType="solid"><fgColor rgb="FF{fondo}"/>'
                            f'<bgColor indexed="64"/></patternFill></fill>')
        al = '<alignment horizontal="center" vertical="center" wrapText="1"/>' if centro else \
             '<alignment vertical="center"/>'
        xfs.append(f'<xf numFmtId="0" fontId="{mapa_f[kf]}" fillId="{mapa_r.get(fondo, 0)}" borderId="1" '
                   f'xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">{al}</xf>')
    borde = ('<border><left style="thin"><color rgb="FFD9D2E3"/></left><right style="thin"><color rgb="FFD9D2E3"/></right>'
             '<top style="thin"><color rgb="FFD9D2E3"/></top><bottom style="thin"><color rgb="FFD9D2E3"/></bottom>'
             '<diagonal/></border>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<fonts count="{len(fuentes)}">{"".join(fuentes)}</fonts>'
            f'<fills count="{len(rellenos)}">{"".join(rellenos)}</fills>'
            f'<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>{borde}</borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>')


def guardar_xlsx(ruta: str, hojas: list[Hoja]) -> None:
    n = len(hojas)
    contenido = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/>'
                 '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                 '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                 + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                           for i in range(1, n + 1)) + "</Types>")
    raiz = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')
    libro = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
             'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
             + "".join(f'<sheet name="{escape(h.nombre)}" sheetId="{i}" r:id="rId{i}"/>'
                       for i, h in enumerate(hojas, 1)) + "</sheets></workbook>")
    rels_libro = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                  + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                            for i in range(1, n + 1))
                  + f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                  '</Relationships>')
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", contenido)
        z.writestr("_rels/.rels", raiz)
        z.writestr("xl/workbook.xml", libro)
        z.writestr("xl/_rels/workbook.xml.rels", rels_libro)
        z.writestr("xl/styles.xml", _styles_xml())
        for i, h in enumerate(hojas, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", h.xml())


def leer_xlsx(ruta: str) -> list[list[str]]:
    """Lee la primera hoja de un .xlsx (texto y números) como lista de filas de texto."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(ruta) as z:
        compartidos = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
                compartidos.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
        hojas = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        if not hojas:
            raise ValueError("El archivo Excel no tiene hojas.")
        raiz = ET.fromstring(z.read(hojas[0]))
    filas = []
    for fila in raiz.iter(f"{{{ns['m']}}}row"):
        valores: dict[int, str] = {}
        for c in fila.findall("m:c", ns):
            ref = re.match(r"([A-Z]+)", c.get("r", ""))
            if not ref:
                continue
            col = 0
            for ch in ref.group(1):
                col = col * 26 + ord(ch) - 64
            tipo = c.get("t")
            if tipo == "inlineStr":
                texto = "".join(t.text or "" for t in c.iter(f"{{{ns['m']}}}t"))
            else:
                v = c.find("m:v", ns)
                texto = "" if v is None or v.text is None else v.text
                if tipo == "s" and texto != "":
                    texto = compartidos[int(texto)]
                elif tipo in (None, "n") and re.fullmatch(r"-?\d+\.0+", texto):
                    texto = texto.split(".")[0]
            valores[col - 1] = texto.strip()
        if valores:
            filas.append([valores.get(i, "") for i in range(max(valores) + 1)])
    return filas
