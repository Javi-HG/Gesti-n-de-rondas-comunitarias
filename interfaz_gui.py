"""Interfaz Gráfica de Usuario (Capa de Presentación) para el Jefe Operativo.

Paleta morado/verde, lista de personal, grilla de colores clickeable,
asistente individual y planificador de equipo con cobertura 24/7.
"""

import sqlite3
import tkinter as tk
from tkinter import messagebox, ttk

from capa_datos import RepositorioTurnos
from capa_ley_opciones import ServicioTurnos
from constantes_reglas import (
    CUADRANTES,
    ESTADOS_CELDA,
    GRUPOS_TURNO,
    HORARIO_NOCTURNO,
    HORARIOS_DIURNOS,
    JORNADAS,
    MODALIDADES,
    ROL_PATRULLERO,
    ROLES_PERSONAL,
)
from mapa_cisterna import dibujar_mapa
from planificador_cobertura import DIURNO, NOCTURNO, minimo_personas

SIN_CUADRANTE = "Sin cuadrante"

# ---------- Paleta ----------
MORADO = "#5B2A86"
MORADO_OSC = "#3F1D61"
MORADO_CLARO = "#EDE4F5"
VERDE = "#2E9E5B"
VERDE_OSC = "#237A46"
VERDE_CLARO = "#DDF3E4"
FONDO = "#F6F3FA"
BLANCO = "#FFFFFF"
TEXTO = "#2B2B2B"
GRIS = "#6B6B7B"
ROJO = "#B42318"
ROJO_CLARO = "#F8D7DA"
SELECCION = "#111827"

# estado -> (color fondo, color texto)
COLORES_ESTADO = {
    "T": (VERDE, BLANCO),
    "L": ("#E9E9EF", "#555555"),
    "VAC": ("#8E5BC0", BLANCO),
    "HE": ("#F2B84B", "#3A2A00"),
    "HEN": ("#D98A1F", BLANCO),
}
COLOR_ESTADO_DEFECTO = (BLANCO, TEXTO)

DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")

NOMBRES_ESTADO = {
    "T": "Turno",
    "L": "Libre",
    "VAC": "Vacaciones",
    "HE": "Horas extras",
    "HEN": "H. extras nocturnas",
}


def _colores(estado: str):
    return COLORES_ESTADO.get(str(estado).upper(), COLOR_ESTADO_DEFECTO)


def _horas_cortas(horario: str) -> str:
    """'07:00 a 18:00' -> '07-18' (cabe en la celda)."""
    try:
        ini, fin = horario.split(" a ")
        return f"{ini[:2]}-{fin[:2]}"
    except ValueError:
        return horario


def _estilo_celda(estado: str, jornada: str, horario: str = ""):
    """Texto y colores de una celda: código arriba y, si es turno, las horas debajo.

    Los turnos nocturnos se ven en morado.
    """
    bg, fg = _colores(estado)
    texto = estado
    es_turno = str(estado).upper() in ("T", "HE", "HEN")
    if str(estado).upper() == "T" and str(jornada).upper() == NOCTURNO:
        bg, fg = MORADO, BLANCO
    if es_turno and horario:
        texto = f"{estado}\n{_horas_cortas(horario)}"
    return texto, bg, fg


def _oscurecer(color: str, factor: float = 0.82) -> str:
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02X%02X%02X" % (int(r * factor), int(g * factor), int(b * factor))


class BotonRedondo(tk.Canvas):
    """Botón de esquinas redondeadas con efecto al pasar el mouse."""

    def __init__(self, padre, texto, comando=None, bg=MORADO, hover=None, fg=BLANCO,
                 width=140, height=38, fondo=None, fuente=("Segoe UI", 10, "bold"), radio=14):
        if fondo is None:
            try:
                fondo = padre.cget("bg")
            except tk.TclError:
                fondo = BLANCO
        super().__init__(padre, width=width, height=height, bg=fondo,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._c_texto, self._c_cmd = texto, comando
        self._c_bg, self._c_hover = bg, hover or _oscurecer(bg)
        self._c_fg, self._c_fuente, self._c_radio = fg, fuente, radio
        self._c_actual = bg
        self.bind("<Configure>", lambda e: self._dibujar())
        self.bind("<Enter>", lambda e: self._pintar(self._c_hover))
        self.bind("<Leave>", lambda e: self._pintar(self._c_bg))
        self.bind("<ButtonRelease-1>", self._soltar)
        self._dibujar()

    def _pintar(self, color):
        self._c_actual = color
        self._dibujar()

    def _dibujar(self):
        self.delete("all")
        w = self.winfo_width() if self.winfo_width() > 1 else int(self["width"])
        h = self.winfo_height() if self.winfo_height() > 1 else int(self["height"])
        r = min(self._c_radio, h // 2)
        pts = [r, 0, r, 0, w - r, 0, w - r, 0, w, 0, w, r, w, r, w, h - r, w, h - r, w, h,
               w - r, h, w - r, h, r, h, r, h, 0, h, 0, h - r, 0, h - r, 0, r, 0, r, 0, 0]
        self.create_polygon(pts, smooth=True, fill=self._c_actual, outline="")
        self.create_text(w / 2, h / 2, text=self._c_texto, fill=self._c_fg, font=self._c_fuente)

    def _soltar(self, e):
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height() and self._c_cmd:
            self._c_cmd()

    def configure(self, cnf=None, **kw):
        if "command" in kw:
            self._c_cmd = kw.pop("command")
        if "text" in kw:
            self._c_texto = kw.pop("text")
            self._dibujar()
        if cnf or kw:
            return super().configure(cnf, **kw)

    config = configure


ESTILOS_BOTON = {
    "Morado.TButton": (MORADO, MORADO_OSC),
    "Verde.TButton": (VERDE, VERDE_OSC),
    "Rojo.TButton": (ROJO, "#8A1A11"),
    "Gris.TButton": ("#6B6B7B", "#4D4D5A"),
}


class AplicacionTurnosGUI:
    """Ventana principal del Gestor de Rondas y Turnos 4x3."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Gestor de Rondas y Turnos 4x3 - Seguridad La Cisterna")
        self.root.geometry("1260x860")
        self.root.minsize(1100, 680)
        self.root.configure(bg=FONDO)

        # Conexión persistente en archivo real (no en memoria)
        self.conexion = sqlite3.connect("turnos_la_cisterna.db")
        self.repositorio = RepositorioTurnos(self.conexion)
        self.servicio = ServicioTurnos(self.repositorio)

        self.personal_ids = []        # id de cada fila de la lista
        self.personal_etiquetas = []  # texto de cada fila de la lista
        self.cuadrante_actual = None  # cuadrante de la malla mostrada
        self.celdas = {}              # (semana, dia) -> Label
        self.malla_actual = {}        # (semana, dia) -> (id_asignacion, estado, jornada)
        self.celda_sel = None         # (semana, dia)
        self.opciones_actuales = []
        self._arr = None              # arrastre en curso

        self._configurar_estilos()
        self._construir_interfaz()
        self._cargar_lista_personal()

    # ------------------------------------------------------------------ estilos
    def _configurar_estilos(self) -> None:
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("TLabel", background=BLANCO, foreground=TEXTO, font=("Segoe UI", 10))
        st.configure("TEntry", padding=5)
        st.configure("TCombobox", padding=4)
        st.configure(
            "Morado.TButton", background=MORADO, foreground=BLANCO,
            font=("Segoe UI", 10, "bold"), padding=8, borderwidth=0,
        )
        st.map("Morado.TButton", background=[("active", MORADO_OSC)])
        st.configure(
            "Verde.TButton", background=VERDE, foreground=BLANCO,
            font=("Segoe UI", 10, "bold"), padding=8, borderwidth=0,
        )
        st.map("Verde.TButton", background=[("active", VERDE_OSC)])
        st.configure("Treeview", rowheight=28, font=("Segoe UI", 10), background=BLANCO,
                     fieldbackground=BLANCO, bordercolor="#DDD3E8")
        st.configure("Treeview.Heading", background=MORADO_CLARO, foreground=MORADO,
                     font=("Segoe UI", 10, "bold"), padding=6)
        st.map("Treeview", background=[("selected", MORADO)], foreground=[("selected", BLANCO)])
        st.configure("Radio.TRadiobutton", background=BLANCO, font=("Segoe UI", 10))
        st.configure("TNotebook", background=FONDO, borderwidth=0)
        st.configure(
            "TNotebook.Tab", padding=(14, 8), font=("Segoe UI", 10, "bold"),
            background=MORADO_CLARO, foreground=MORADO,
        )
        st.map(
            "TNotebook.Tab",
            background=[("selected", MORADO)], foreground=[("selected", BLANCO)],
        )

    # --------------------------------------------------------------- construcción
    def _tarjeta(self, padre, titulo, color_titulo=MORADO, extra=None):
        """Tarjeta blanca con barra de título de color (y controles opcionales a la derecha)."""
        marco = tk.Frame(padre, bg=BLANCO, highlightbackground="#DDD3E8", highlightthickness=1)
        barra = tk.Frame(marco, bg=color_titulo)
        barra.pack(fill=tk.X)
        tk.Label(
            barra, text=titulo, bg=color_titulo, fg=BLANCO,
            font=("Segoe UI", 10, "bold"), anchor="w", padx=12, pady=6,
        ).pack(side=tk.LEFT)
        if extra:
            extra(barra, color_titulo)
        cuerpo = tk.Frame(marco, bg=BLANCO, padx=12, pady=10)
        cuerpo.pack(fill=tk.BOTH, expand=True)
        return marco, cuerpo

    def _btn(self, padre, text="", style="Morado.TButton", command=None):
        """Botón redondeado con los colores de la aplicación."""
        bg, hover = ESTILOS_BOTON.get(style, (MORADO, MORADO_OSC))
        return BotonRedondo(
            padre, text, command, bg=bg, hover=hover,
            width=max(110, 9 * len(text) + 36), height=40,
        )

    def _controles_ancho(self, barra, color):
        """Botones − / + de la barra del panel de personal para achicar o agrandar la lista."""
        for texto, delta in (("＋", 70), ("−", -70)):
            lbl = tk.Label(
                barra, text=texto, bg=_oscurecer(color, 0.7), fg=BLANCO, cursor="hand2",
                font=("Segoe UI", 11, "bold"), width=3,
            )
            lbl.pack(side=tk.RIGHT, padx=(0, 6), pady=3)
            lbl.bind("<Button-1>", lambda e, d=delta: self._ajustar_ancho_panel(d))
        tk.Label(barra, text="Ancho:", bg=color, fg="#D6C4EA", font=("Segoe UI", 8)).pack(side=tk.RIGHT, padx=(0, 4))

    def _ajustar_ancho_panel(self, delta: int) -> None:
        try:
            x, y = self.panel.sash_coord(0)
            self.panel.sash_place(0, max(230, x + delta), y)
        except tk.TclError:
            pass

    def _marco_scroll(self, padre):
        """Marco interior con barras de desplazamiento vertical y horizontal."""
        canvas = tk.Canvas(padre, bg=BLANCO, highlightthickness=0)
        vs = ttk.Scrollbar(padre, orient=tk.VERTICAL, command=canvas.yview)
        hs = ttk.Scrollbar(padre, orient=tk.HORIZONTAL, command=canvas.xview)
        canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        interior = tk.Frame(canvas, bg=BLANCO)
        canvas.create_window((0, 0), window=interior, anchor="nw")
        interior.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        hs.pack(side=tk.BOTTOM, fill=tk.X)
        vs.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return interior

    def _pestana_scroll(self, padre):
        """Marco interior con scroll vertical que se ajusta al ancho disponible."""
        canvas = tk.Canvas(padre, bg=FONDO, highlightthickness=0)
        vs = ttk.Scrollbar(padre, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vs.set)
        interior = tk.Frame(canvas, bg=FONDO)
        ventana = canvas.create_window((0, 0), window=interior, anchor="nw")
        interior.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(ventana, width=e.width))
        vs.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def rueda(e):
            canvas.yview_scroll(int(-e.delta / 120), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", rueda))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        return interior

    @staticmethod
    def _boton_grande(padre, texto, color, color_activo, comando, **pack):
        b = BotonRedondo(
            padre, texto, comando, bg=color, hover=color_activo, width=100, height=46,
            fuente=("Segoe UI", 11, "bold"), radio=16,
        )
        b.pack(**pack)
        return b

    def _construir_interfaz(self) -> None:
        # Encabezado (con las acciones principales siempre a la vista)
        header = tk.Frame(self.root, bg=MORADO)
        header.pack(fill=tk.X)
        acciones = tk.Frame(header, bg=MORADO)
        acciones.pack(side=tk.RIGHT, padx=16)
        BotonRedondo(
            acciones, "Planificar equipo 24/7", self._abrir_planificador_equipo,
            bg=VERDE, hover=VERDE_OSC, width=220, height=44, fondo=MORADO,
            fuente=("Segoe UI", 11, "bold"), radio=18,
        ).pack(side=tk.RIGHT, padx=(10, 0), pady=10)
        BotonRedondo(
            acciones, "Asignar malla individual", self._abrir_asistente_malla,
            bg=BLANCO, hover=MORADO_CLARO, fg=MORADO, width=230, height=44, fondo=MORADO,
            fuente=("Segoe UI", 11, "bold"), radio=18,
        ).pack(side=tk.RIGHT, pady=10)
        tk.Label(
            header, text="Planificación de Turnos 4x3", bg=MORADO, fg=BLANCO,
            font=("Segoe UI", 16, "bold"),
        ).pack(side=tk.LEFT, padx=20, pady=(12, 12))
        tk.Label(
            header, text="Jefatura Operativa · Seguridad La Cisterna", bg=MORADO,
            fg="#D6C4EA", font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, pady=(16, 8))
        tk.Frame(self.root, bg=VERDE, height=4).pack(fill=tk.X)

        cuerpo = tk.Frame(self.root, bg=FONDO)
        cuerpo.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # ---------- Columna izquierda: personal ----------
        self.panel = tk.PanedWindow(
            cuerpo, orient=tk.HORIZONTAL, bg="#D9CCEA", bd=0, sashwidth=9,
            sashrelief=tk.RAISED, sashcursor="sb_h_double_arrow",
        )
        self.panel.pack(fill=tk.BOTH, expand=True)
        izq = tk.Frame(self.panel, bg=FONDO, width=330)
        izq.pack_propagate(False)
        self.panel.add(izq, minsize=230, stretch="never")

        tarj_lista, c_lista = self._tarjeta(izq, "Personal", extra=self._controles_ancho)
        tarj_lista.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        caja = tk.Frame(c_lista, bg=BLANCO)
        caja.pack(fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(caja, orient=tk.VERTICAL)
        self.lista_personal = tk.Listbox(
            caja, activestyle="none", exportselection=False, bd=0,
            highlightthickness=1, highlightbackground="#DDD3E8",
            selectbackground=MORADO, selectforeground=BLANCO,
            font=("Segoe UI", 10), yscrollcommand=scroll.set,
        )
        scroll.config(command=self.lista_personal.yview)
        self.lista_personal.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.lista_personal.bind("<<ListboxSelect>>", lambda e: self._on_seleccion_personal())
        self._btn(
            c_lista, text="Eliminar seleccionado", style="Rojo.TButton",
            command=self._eliminar_personal,
        ).pack(fill=tk.X, pady=(8, 0))

        tarj_nuevo, c_nuevo = self._tarjeta(izq, "Agregar integrante", VERDE)
        tarj_nuevo.pack(fill=tk.X)

        ttk.Label(c_nuevo, text="Nombre").grid(row=0, column=0, columnspan=2, sticky="w")
        self.entry_nombre = ttk.Entry(c_nuevo)
        self.entry_nombre.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(c_nuevo, text="Cargo / Rol").grid(row=2, column=0, columnspan=2, sticky="w")
        self.combo_rol = ttk.Combobox(c_nuevo, values=ROLES_PERSONAL, state="readonly")
        self.combo_rol.current(0)
        self.combo_rol.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(c_nuevo, text="Turno").grid(row=4, column=0, sticky="w")
        ttk.Label(c_nuevo, text="Jornada").grid(row=4, column=1, sticky="w", padx=(8, 0))
        self.combo_turno_nuevo = ttk.Combobox(
            c_nuevo, values=GRUPOS_TURNO, state="readonly", width=6
        )
        self.combo_turno_nuevo.current(0)
        self.combo_turno_nuevo.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        self.combo_jornada_nueva = ttk.Combobox(
            c_nuevo, values=JORNADAS, state="readonly", width=12
        )
        self.combo_jornada_nueva.current(0)
        self.combo_jornada_nueva.grid(row=5, column=1, sticky="ew", padx=(8, 0), pady=(0, 8))
        ttk.Label(c_nuevo, text="Cuadrante (opcional)").grid(row=6, column=0, columnspan=2, sticky="w")
        self.combo_cuad_nuevo = ttk.Combobox(
            c_nuevo, values=(SIN_CUADRANTE, *CUADRANTES), state="readonly"
        )
        self.combo_cuad_nuevo.current(0)
        self.combo_cuad_nuevo.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(c_nuevo, text="Modalidades (solo patrulleros)").grid(row=8, column=0, columnspan=2, sticky="w")
        marco_mod = tk.Frame(c_nuevo, bg=BLANCO)
        marco_mod.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.vars_mod_nuevo = {}
        self.checks_mod_nuevo = []
        for k, m in enumerate(MODALIDADES):
            v = tk.BooleanVar(value=False)
            self.vars_mod_nuevo[m] = v
            chk = tk.Checkbutton(
                marco_mod, text=m, variable=v, bg=BLANCO, activebackground=BLANCO,
                selectcolor=BLANCO, font=("Segoe UI", 9), anchor="w",
            )
            chk.grid(row=k // 2, column=k % 2, sticky="w")
            self.checks_mod_nuevo.append(chk)
        self.combo_rol.bind("<<ComboboxSelected>>", lambda e: self._actualizar_modalidades_nuevo())
        self._actualizar_modalidades_nuevo()
        self._btn(
            c_nuevo, text="＋ Guardar integrante", style="Verde.TButton",
            command=self._registrar_personal,
        ).grid(row=10, column=0, columnspan=2, sticky="ew")
        c_nuevo.columnconfigure(0, weight=1)
        c_nuevo.columnconfigure(1, weight=1)

        # ---------- Columna derecha: malla ----------
        der_total = tk.Frame(self.panel, bg=FONDO)
        self.panel.add(der_total, minsize=560, stretch="always")

        self.notebook = ttk.Notebook(der_total)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        tab_ind = tk.Frame(self.notebook, bg=FONDO)
        tab_equipo = tk.Frame(self.notebook, bg=FONDO, padx=10, pady=10)
        tab_mod = tk.Frame(self.notebook, bg=FONDO, padx=10, pady=10)
        self.notebook.add(tab_ind, text="  Malla individual  ")
        self.notebook.add(tab_equipo, text="  Malla del equipo  ")
        self.notebook.add(tab_mod, text="  Modalidad de patrulleros  ")
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self._refrescar_vistas())
        der = self._pestana_scroll(tab_ind)
        self._construir_tab_equipo(tab_equipo)
        self._construir_tab_modalidad(tab_mod)

        tarj_malla, c_malla = self._tarjeta(der, "Malla mensual")
        tarj_malla.pack(fill=tk.X)

        fila_top = tk.Frame(c_malla, bg=BLANCO)
        fila_top.pack(fill=tk.X, pady=(0, 10))
        self.lbl_nombre = tk.Label(
            fila_top, text="Seleccione un integrante de la lista", bg=BLANCO,
            fg=MORADO, font=("Segoe UI", 13, "bold"), anchor="w",
        )
        self.lbl_nombre.pack(side=tk.LEFT)

        self.lbl_detalle = tk.Label(
            c_malla, text="", bg=VERDE_CLARO, fg=VERDE_OSC, anchor="w",
            font=("Segoe UI", 10, "bold"), padx=10, pady=6,
        )
        self.lbl_detalle.pack(fill=tk.X, pady=(0, 10))

        # Grilla
        grilla = tk.Frame(c_malla, bg=BLANCO)
        grilla.pack(fill=tk.X)
        tk.Label(grilla, text="", bg=BLANCO).grid(row=0, column=0)
        for j, dia in enumerate(DIAS, start=1):
            tk.Label(
                grilla, text=dia[:3].upper(), bg=MORADO_CLARO, fg=MORADO,
                font=("Segoe UI", 9, "bold"), pady=6,
            ).grid(row=0, column=j, sticky="ew", padx=2, pady=2)
            grilla.columnconfigure(j, weight=1, uniform="dias")
        for i in range(1, 5):
            tk.Label(
                grilla, text=f"Semana {i}", bg=MORADO_CLARO, fg=MORADO,
                font=("Segoe UI", 9, "bold"), padx=8,
            ).grid(row=i, column=0, sticky="nsew", padx=2, pady=2)
            for j, dia in enumerate(DIAS, start=1):
                lbl = tk.Label(
                    grilla, text="", bg="#F1F1F5", fg=TEXTO, cursor="hand2",
                    font=("Segoe UI", 9, "bold"), height=2, width=7,
                    highlightthickness=3, highlightbackground=BLANCO,
                )
                lbl.grid(row=i, column=j, sticky="nsew", padx=2, pady=2)
                self._hacer_arrastrable(lbl, {"tipo": "dia_ind", "clave": (i, dia)})
                self.celdas[(i, dia)] = lbl

        tk.Label(
            c_malla,
            text="Verde = turno diurno   ·   Morado = turno nocturno   ·   Gris = libre   ·   Bajo el código: horas del turno (inicio-fin)",
            bg=BLANCO, fg=GRIS, font=("Segoe UI", 9), anchor="w",
        ).pack(fill=tk.X, pady=(8, 0))

        # Cuadrantes y mapa de la comuna
        tarj_mapa, c_mapa = self._tarjeta(der, "Cuadrantes · Comuna de La Cisterna")
        tarj_mapa.pack(fill=tk.X, pady=(12, 0))
        fila_cuad = tk.Frame(c_mapa, bg=BLANCO)
        fila_cuad.pack(fill=tk.X)
        self.lbl_cuadrante = tk.Label(
            fila_cuad, text="Sin cuadrante asignado", bg=BLANCO, fg=GRIS,
            font=("Segoe UI", 10, "bold"), anchor="w",
        )
        self.lbl_cuadrante.pack(side=tk.LEFT)
        self._btn(
            fila_cuad, text="Asignar", style="Verde.TButton", command=self._asignar_cuadrante_individual,
        ).pack(side=tk.RIGHT)
        self.combo_cuad_ind = ttk.Combobox(
            fila_cuad, values=(SIN_CUADRANTE, *CUADRANTES), state="readonly", width=16
        )
        self.combo_cuad_ind.current(0)
        self.combo_cuad_ind.pack(side=tk.RIGHT, padx=6)
        self.canvas_mapa = tk.Canvas(
            c_mapa, width=620, height=210, bg=BLANCO, highlightthickness=0
        )
        self.canvas_mapa.pack(pady=(4, 0))
        dibujar_mapa(self.canvas_mapa)

        # Barra de edición rápida
        tarj_edit, c_edit = self._tarjeta(der, "Editar un día / novedad", VERDE)
        tarj_edit.pack(fill=tk.X, pady=(12, 0))
        self.lbl_celda = tk.Label(
            c_edit, text="① Haga clic en un día de la grilla", bg=BLANCO,
            fg=GRIS, font=("Segoe UI", 10), anchor="w",
        )
        self.lbl_celda.pack(fill=tk.X, pady=(0, 8))

        botones = tk.Frame(c_edit, bg=BLANCO)
        botones.pack(fill=tk.X)
        tk.Label(
            botones, text="② Elija el nuevo estado (o arrastre un día a otro casillero):", bg=BLANCO,
            fg=GRIS, font=("Segoe UI", 10),
        ).pack(side=tk.LEFT, padx=(0, 10))
        for estado in ESTADOS_CELDA:
            bg, fg = _colores(estado)
            nombre = NOMBRES_ESTADO.get(str(estado).upper(), "")
            texto = f"{estado}" + (f"  {nombre}" if nombre else "")
            BotonRedondo(
                botones, texto, lambda e=estado: self._editar_celda(e), bg=bg,
                hover=_oscurecer(bg, 0.88), fg=fg, width=max(70, 9 * len(texto) + 24),
                height=34, fondo=BLANCO, fuente=("Segoe UI", 9, "bold"), radio=12,
            ).pack(side=tk.LEFT, padx=3)

        # Leyenda normativa
        tk.Label(
            der,
            text="Normativa: Art. 38 Código del Trabajo — mínimo 2 domingos libres en jornada diurna "
                 "y 2 fines de semana (sábado + domingo) libres en jornada nocturna.",
            bg=MORADO_CLARO, fg=MORADO_OSC, justify="left", anchor="w",
            wraplength=760, padx=12, pady=10, font=("Segoe UI", 9),
        ).pack(fill=tk.X, pady=(12, 0))

    # --------------------------------------------------------------- personal
    def _id_seleccionado(self):
        sel = self.lista_personal.curselection()
        if not sel:
            return None, None
        return self.personal_ids[sel[0]], self.personal_etiquetas[sel[0]]

    @staticmethod
    def _nombre_completo(p: dict) -> str:
        return f"{p['nombre']} {p.get('apellido') or ''}".strip()

    def _cargar_lista_personal(self, seleccionar_ultimo: bool = False) -> None:
        self.personal_ids = []
        self.personal_etiquetas = []
        self.lista_personal.delete(0, tk.END)
        for p in self.servicio.listar_personal():
            turno = f"Turno {p['grupo_turno']} · {p['jornada'].capitalize()}" if p["jornada"] else "Sin turno"
            etiqueta = f"{self._nombre_completo(p)} ({p['rol']})"
            self.personal_ids.append(p["id"])
            self.personal_etiquetas.append(etiqueta)
            self.lista_personal.insert(tk.END, f"  {etiqueta}  ·  {turno}")
        if self.personal_etiquetas:
            idx = len(self.personal_etiquetas) - 1 if seleccionar_ultimo else 0
            self.lista_personal.selection_set(idx)
            self.lista_personal.see(idx)
            self._on_seleccion_personal()

    def _on_seleccion_personal(self) -> None:
        self.celda_sel = None
        self.lbl_celda.config(text="① Haga clic en un día de la grilla", fg=GRIS)
        self._mostrar_malla_guardada()

    def _actualizar_modalidades_nuevo(self) -> None:
        """Las modalidades solo se pueden marcar si el cargo es patrullero."""
        es_patrullero = self.combo_rol.get() == ROL_PATRULLERO
        for chk in self.checks_mod_nuevo:
            chk.configure(state=tk.NORMAL if es_patrullero else tk.DISABLED)
        if not es_patrullero:
            for v in self.vars_mod_nuevo.values():
                v.set(False)

    def _registrar_personal(self) -> None:
        try:
            nombre = self.entry_nombre.get()
            turno = self.combo_turno_nuevo.get()
            jornada = self.combo_jornada_nueva.get()
            cuadrante = None if self.combo_cuad_nuevo.current() == 0 else self.combo_cuad_nuevo.get()
            modalidades = [m for m, v in self.vars_mod_nuevo.items() if v.get()]
            self.servicio.crear_integrante(
                nombre, self.combo_rol.get(), turno, jornada, cuadrante, modalidades
            )
            self.entry_nombre.delete(0, tk.END)
            self.combo_cuad_nuevo.current(0)
            for v in self.vars_mod_nuevo.values():
                v.set(False)
            self._cargar_lista_personal(seleccionar_ultimo=True)
            self._refrescar_vistas()
            messagebox.showinfo(
                "Éxito",
                f"{nombre.strip()} registrado: Turno {turno}, jornada {jornada.lower()}.",
            )
        except ValueError as err:
            messagebox.showerror("Error de validación", str(err))

    # ------------------------------------------------------------- malla / grilla
    def _limpiar_grilla(self) -> None:
        self.malla_actual.clear()
        for lbl in self.celdas.values():
            lbl.config(text="", bg="#F1F1F5", highlightbackground=BLANCO)
        self.cuadrante_actual = None
        self._pintar_mapa()

    def _asignar_cuadrante_individual(self) -> None:
        personal_id, _etq = self._id_seleccionado()
        if personal_id is None:
            messagebox.showwarning("Atención", "Seleccione primero un integrante de la lista.")
            return
        cuadrante = None if self.combo_cuad_ind.current() == 0 else self.combo_cuad_ind.get()
        try:
            self.servicio.asignar_cuadrante([personal_id], cuadrante)
        except ValueError as err:
            messagebox.showerror("Error", str(err))
            return
        self._mostrar_malla_guardada()
        self._refrescar_vistas()

    def _pintar_mapa(self) -> None:
        dibujar_mapa(self.canvas_mapa, resaltado=self.cuadrante_actual)
        self.lbl_cuadrante.config(
            text=f"Cuadrante asignado: {self.cuadrante_actual}" if self.cuadrante_actual
            else "Sin cuadrante asignado",
            fg=VERDE_OSC if self.cuadrante_actual else GRIS,
        )

    def _mostrar_malla_guardada(self) -> None:
        self._limpiar_grilla()
        personal_id, etiqueta = self._id_seleccionado()
        if personal_id is None:
            self.lbl_nombre.config(text="Seleccione un integrante de la lista")
            self.lbl_detalle.config(text="")
            return

        self.lbl_nombre.config(text=etiqueta)
        malla = self.repositorio.obtener_malla_personal(personal_id)
        persona = self.repositorio.obtener_persona(personal_id) or {}
        # el cuadrante es propio de la persona, tenga o no malla
        self.cuadrante_actual = persona.get("cuadrante") or None
        self.combo_cuad_ind.set(self.cuadrante_actual or SIN_CUADRANTE)
        self._pintar_mapa()

        if not malla:
            self.lbl_detalle.config(
                text="Sin malla asignada aún — use «Asignar malla individual» o «Planificar equipo 24/7»",
                bg="#FFF3D6", fg="#7A5200",
            )
            return

        info = malla[0]
        jornadas = {f["jornada"] for f in malla}
        horarios = sorted({f["horario"] for f in malla})
        jornada_txt = info["jornada"] if len(jornadas) == 1 else "ROTATIVO DÍA/NOCHE"
        modalidades = self.servicio.obtener_modalidades_persona(personal_id)
        texto = (
            f"Turno {info['grupo_turno']} ({jornada_txt})   ·   "
            f"Horario: {' / '.join(horarios)}   ·   {self.cuadrante_actual or 'Sin cuadrante'}"
        )
        if modalidades:
            texto += "   ·   " + " + ".join(modalidades)
        self.lbl_detalle.config(text=texto, bg=VERDE_CLARO, fg=VERDE_OSC)

        for fila in malla:
            clave = (fila["semana_mes"], fila["dia_semana"])
            self.malla_actual[clave] = (fila["id"], fila["estado"], fila["jornada"])
            lbl = self.celdas.get(clave)
            if lbl:
                txt, bg, fg = _estilo_celda(fila["estado"], fila["jornada"], fila["horario"])
                lbl.config(text=txt, bg=bg, fg=fg)

        if self.celda_sel:
            self._resaltar_celda()

    def _seleccionar_celda(self, semana: int, dia: str) -> None:
        self.celda_sel = (semana, dia)
        self._resaltar_celda()
        self.lbl_celda.config(
            text=f"① Seleccionado: Semana {semana} · {dia}", fg=MORADO,
        )

    def _resaltar_celda(self) -> None:
        for clave, lbl in self.celdas.items():
            lbl.config(highlightbackground=SELECCION if clave == self.celda_sel else BLANCO)

    def _editar_celda(self, nuevo_estado: str) -> None:
        personal_id, _ = self._id_seleccionado()
        if personal_id is None:
            messagebox.showwarning("Atención", "Seleccione un integrante de la lista.")
            return
        if not self.celda_sel:
            messagebox.showwarning("Atención", "Primero haga clic en el día que desea modificar.")
            return

        datos = self.malla_actual.get(self.celda_sel)
        if datos is None:
            messagebox.showwarning("Atención", "Primero debe asignar una malla al integrante.")
            return

        try:
            self.servicio.editar_estado_dia(personal_id, datos[0], nuevo_estado)
            self._mostrar_malla_guardada()
            self._refrescar_vistas()
        except ValueError as err:
            messagebox.showerror("Bloqueo Legal (Art. 38)", str(err))

    # ------------------------------------------------------------------ eliminar
    def _eliminar_personal(self) -> None:
        personal_id, etiqueta = self._id_seleccionado()
        if personal_id is None:
            messagebox.showwarning("Atención", "Seleccione primero un integrante de la lista.")
            return
        if not messagebox.askyesno(
            "Eliminar integrante",
            f"¿Eliminar a {etiqueta}?\n\nSe borrarán también su malla mensual y su modalidad. "
            "Esta acción no se puede deshacer.",
            icon="warning",
        ):
            return
        try:
            self.servicio.eliminar_integrante(personal_id)
        except ValueError as err:
            messagebox.showerror("Error", str(err))
            return
        self.celda_sel = None
        self._cargar_lista_personal()
        if not self.personal_ids:
            self._mostrar_malla_guardada()
        self._refrescar_vistas()

    def _refrescar_vistas(self) -> None:
        """Redibuja las pestañas del equipo y de modalidad con los datos actuales."""
        if not hasattr(self, "interior_equipo"):
            return
        self._dibujar_malla_equipo()
        self._pintar_modalidad()

    # --------------------------------------------------------- arrastrar y soltar
    def _hacer_arrastrable(self, widget, datos, destino=True) -> None:
        """Permite arrastrar el widget; si destino=True también acepta soltar sobre él."""
        widget._arrastre = datos
        if destino:
            widget._destino = datos
        widget.bind("<ButtonPress-1>", self._arrastre_inicio)
        widget.bind("<B1-Motion>", self._arrastre_mover)
        widget.bind("<ButtonRelease-1>", self._arrastre_fin)

    @staticmethod
    def _buscar_destino(widget):
        while widget is not None:
            datos = getattr(widget, "_destino", None)
            if datos is not None:
                return widget, datos
            widget = getattr(widget, "master", None)
        return None, None

    def _arrastre_inicio(self, e) -> None:
        self._arr = {
            "datos": e.widget._arrastre, "origen": e.widget, "x": e.x_root, "y": e.y_root,
            "movido": False, "fantasma": None, "sobre": None,
        }

    def _arrastre_mover(self, e) -> None:
        arr = self._arr
        if not arr:
            return
        if not arr["movido"]:
            if abs(e.x_root - arr["x"]) < 6 and abs(e.y_root - arr["y"]) < 6:
                return
            arr["movido"] = True
            texto = ""
            try:
                texto = str(arr["origen"].cget("text")).replace("\n", " ").replace("≡ ", "")
            except tk.TclError:
                pass
            g = tk.Toplevel(self.root)
            g.overrideredirect(True)
            try:
                g.attributes("-topmost", True)
                g.attributes("-alpha", 0.88)
            except tk.TclError:
                pass
            tk.Label(
                g, text=texto or "·", bg=MORADO_OSC, fg=BLANCO, font=("Segoe UI", 10, "bold"),
                padx=10, pady=6,
            ).pack()
            arr["fantasma"] = g
        arr["fantasma"].geometry(f"+{e.x_root + 16}+{e.y_root + 16}")
        destino, datos = self._buscar_destino(self.root.winfo_containing(e.x_root, e.y_root))
        if destino is not arr["sobre"]:
            self._resaltar_destino(arr["sobre"], False)
            arr["sobre"] = destino
            self._resaltar_destino(destino, True)

    def _resaltar_destino(self, widget, activo: bool) -> None:
        if widget is None:
            return
        datos = getattr(widget, "_destino", None) or {}
        try:
            if datos.get("tipo") == "dia_ind":
                if activo:
                    widget.configure(highlightbackground=VERDE)
                else:
                    self._resaltar_celda()
            elif datos.get("tipo") == "cuadrante":
                datos["marco"].configure(highlightbackground=VERDE if activo else "#DDD3E8")
        except tk.TclError:
            pass

    def _arrastre_fin(self, e) -> None:
        arr, self._arr = self._arr, None
        if not arr:
            return
        if arr["fantasma"] is not None:
            arr["fantasma"].destroy()
        self._resaltar_destino(arr["sobre"], False)
        if not arr["movido"]:  # fue un clic, no un arrastre
            if arr["datos"].get("tipo") == "dia_ind":
                self._seleccionar_celda(*arr["datos"]["clave"])
            return
        _w, destino = self._buscar_destino(self.root.winfo_containing(e.x_root, e.y_root))
        if destino is not None:
            self._soltar(arr["datos"], destino)

    def _soltar(self, origen: dict, destino: dict) -> None:
        tipos = (origen["tipo"], destino["tipo"])
        if tipos == ("dia_ind", "dia_ind"):
            self._mover_dia_individual(origen["clave"], destino["clave"])
        elif tipos == ("dia_eq", "dia_eq"):
            self._mover_dia_equipo(origen, destino)
        elif tipos == ("persona", "cuadrante"):
            self._cambiar_cuadrante(origen["pid"], destino["cuadrante"])

    def _mover_dia_individual(self, desde, hasta) -> None:
        personal_id, _ = self._id_seleccionado()
        a, b = self.malla_actual.get(desde), self.malla_actual.get(hasta)
        if personal_id is None or a is None or b is None:
            messagebox.showwarning("Atención", "Ese integrante aún no tiene malla asignada.")
            return
        try:
            self.servicio.intercambiar_dias(personal_id, a[0], b[0])
        except ValueError as err:
            messagebox.showerror("Movimiento no permitido (Art. 38)", str(err))
            return
        self.celda_sel = hasta
        self._mostrar_malla_guardada()
        self._refrescar_vistas()

    def _mover_dia_equipo(self, origen: dict, destino: dict) -> None:
        if origen["pid"] != destino["pid"]:
            messagebox.showwarning(
                "Atención", "Los días solo se pueden mover dentro de la fila de la misma persona."
            )
            return
        try:
            self.servicio.intercambiar_dias(origen["pid"], origen["id"], destino["id"])
        except ValueError as err:
            messagebox.showerror("Movimiento no permitido (Art. 38)", str(err))
            return
        self._refrescar_vistas()
        if origen["pid"] == self._id_seleccionado()[0]:
            self._mostrar_malla_guardada()

    def _cambiar_cuadrante(self, personal_id: int, cuadrante) -> None:
        try:
            self.servicio.asignar_cuadrante([personal_id], cuadrante)
        except ValueError as err:
            messagebox.showwarning("Atención", str(err))
            return
        self._refrescar_vistas()
        if personal_id == self._id_seleccionado()[0]:
            self._mostrar_malla_guardada()

    # --------------------------------------------------------- pestaña: equipo
    def _construir_tab_equipo(self, tab) -> None:
        barra = tk.Frame(tab, bg=FONDO)
        barra.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            barra, text="Malla mensual de todo el equipo", bg=FONDO, fg=MORADO,
            font=("Segoe UI", 13, "bold"),
        ).pack(side=tk.LEFT)
        self._btn(barra, text="Actualizar", style="Morado.TButton", command=self._refrescar_vistas).pack(
            side=tk.RIGHT
        )
        self._btn(
            barra, text="Asignar turnos A y B…", style="Verde.TButton", command=self._abrir_turnos_ab,
        ).pack(side=tk.RIGHT, padx=(0, 8))
        self._btn(
            barra, text="Repartir cuadrantes", style="Verde.TButton", command=self._repartir_cuadrantes,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        self.marco_cuadrantes = tk.Frame(tab, bg=FONDO)
        self.marco_cuadrantes.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            tab,
            text="Verde = turno diurno  ·  Morado = turno nocturno  ·  · = libre  ·  V = vacaciones  ·  "
                 "HE / HN = horas extras  ·  Arrastre un día a otro casillero de la misma fila para moverlo",
            bg=FONDO, fg=GRIS, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=900,
        ).pack(fill=tk.X, pady=(0, 6))
        marco = tk.Frame(tab, bg=BLANCO, highlightbackground="#DDD3E8", highlightthickness=1)
        marco.pack(fill=tk.BOTH, expand=True)
        self.interior_equipo = self._marco_scroll(marco)

    def _repartir_cuadrantes(self) -> None:
        pendientes = [p for p in self.servicio.listar_personal() if not p.get("cuadrante")]
        solo_sin = True
        if not pendientes:
            if not messagebox.askyesno(
                "Repartir cuadrantes",
                "Todos ya tienen cuadrante.\n¿Volver a repartir a TODO el personal automáticamente?",
            ):
                return
            solo_sin = False
        n = self.servicio.repartir_cuadrantes_auto(solo_sin_cuadrante=solo_sin)
        self._refrescar_vistas()
        self._mostrar_malla_guardada()
        messagebox.showinfo(
            "Cuadrantes repartidos",
            f"Se asignó cuadrante a {n} integrante(s), de forma pareja por cargo.\n"
            "Puede ajustar cualquiera arrastrando su nombre a otro cuadrante.",
        )

    ABREVIATURAS_MODALIDAD = {"Móvil": "Móvil", "Moto": "Moto", "Infantería": "Infant.", "Bicicleta": "Bici"}

    def _dibujar_cuadrantes(self) -> None:
        marco = self.marco_cuadrantes
        for w in marco.winfo_children():
            w.destroy()
        resumen = self.servicio.resumen_cuadrantes()
        tk.Label(
            marco, text="Cuadrantes de cada persona · modalidades (una persona puede usar varias)  ·  arrastre un nombre a un cuadrante para cambiarlo",
            bg=FONDO, fg=MORADO, font=("Segoe UI", 10, "bold"), anchor="w",
        ).grid(row=0, column=0, columnspan=len(CUADRANTES), sticky="w", pady=(0, 4))
        for i, nombre in enumerate(CUADRANTES):
            datos = resumen["cuadrantes"][nombre]
            tarjeta = tk.Frame(
                marco, bg=BLANCO, highlightbackground="#DDD3E8", highlightthickness=2, padx=8, pady=6,
            )
            tarjeta.grid(row=1, column=i, sticky="nsew", padx=3)
            marco.columnconfigure(i, weight=1, uniform="cuad")
            fila_titulo = tk.Frame(tarjeta, bg=BLANCO)
            fila_titulo.pack(fill=tk.X)
            tk.Label(
                fila_titulo, text=nombre.replace("Cuadrante ", "Cuadr. "), bg=BLANCO, fg=MORADO,
                font=("Segoe UI", 9, "bold"),
            ).pack(side=tk.LEFT)
            tk.Label(
                fila_titulo, text=str(datos["total"]), bg=VERDE if datos["total"] else "#E9E9EF",
                fg=BLANCO if datos["total"] else GRIS, font=("Segoe UI", 10, "bold"), width=3,
            ).pack(side=tk.RIGHT)
            chips = tk.Frame(tarjeta, bg=BLANCO)
            chips.pack(fill=tk.X, pady=(4, 0))
            for k, (modalidad, n) in enumerate(datos["por_modalidad"].items()):
                tk.Label(
                    chips, text=f"{self.ABREVIATURAS_MODALIDAD.get(modalidad, modalidad)} {n}",
                    bg=MORADO_CLARO if n else BLANCO, fg=MORADO if n else "#B5B5C3",
                    font=("Segoe UI", 8, "bold"), padx=3,
                ).grid(row=k // 2, column=k % 2, sticky="ew", padx=1, pady=1)
            chips.columnconfigure(0, weight=1)
            chips.columnconfigure(1, weight=1)
            extra = []
            if datos["patrulleros_sin_modalidad"]:
                extra.append(f"Patrull. sin modalidad {datos['patrulleros_sin_modalidad']}")
            for rol, n in datos["por_rol"].items():
                extra.append(f"{rol.replace('_', ' ').capitalize()} {n}")
            tk.Label(
                tarjeta, text="\n".join(extra) if extra else " ", bg=BLANCO, fg=GRIS,
                font=("Segoe UI", 8), anchor="w", justify="left",
            ).pack(fill=tk.X, pady=(3, 0))
            # toda la tarjeta acepta que se suelte un nombre encima
            destino = {"tipo": "cuadrante", "cuadrante": nombre, "marco": tarjeta}
            tarjeta._destino = destino
            for hijo in self._descendientes(tarjeta):
                hijo._destino = destino
        sin = resumen["sin_cuadrante"]
        marco_sin = tk.Frame(marco, bg=BLANCO, highlightbackground="#DDD3E8", highlightthickness=2, padx=8, pady=4)
        marco_sin.grid(row=2, column=0, columnspan=len(CUADRANTES), sticky="ew", padx=3, pady=(4, 0))
        tk.Label(
            marco_sin,
            text=f"Sin cuadrante ({len(sin)}): " + (", ".join(sin[:8]) + ("…" if len(sin) > 8 else "") if sin else "ninguno")
            + "   ·   suelte aquí un nombre para quitarle el cuadrante",
            bg=BLANCO, fg=GRIS, font=("Segoe UI", 8), anchor="w",
        ).pack(fill=tk.X)
        destino = {"tipo": "cuadrante", "cuadrante": None, "marco": marco_sin}
        marco_sin._destino = destino
        for hijo in self._descendientes(marco_sin):
            hijo._destino = destino

    @classmethod
    def _descendientes(cls, widget):
        for hijo in widget.winfo_children():
            yield hijo
            yield from cls._descendientes(hijo)

    def _dibujar_malla_equipo(self) -> None:
        self._dibujar_cuadrantes()
        interior = self.interior_equipo
        for w in interior.winfo_children():
            w.destroy()
        datos = self.servicio.obtener_mallas_equipo()
        if not datos:
            tk.Label(
                interior, text="Aún no hay personal registrado.", bg=BLANCO, fg=GRIS,
                font=("Segoe UI", 11), padx=20, pady=20,
            ).grid(row=0, column=0)
            return

        orden_rol = {rol: i for i, rol in enumerate(ROLES_PERSONAL)}
        orden_turno = {g: i for i, g in enumerate(GRUPOS_TURNO)}

        def grupo_de(d):
            return d["persona"]["grupo_turno"] or (d["malla"][0]["grupo_turno"] if d["malla"] else None)

        datos.sort(key=lambda d: (
            orden_turno.get(grupo_de(d), 99), orden_rol.get(d["persona"]["rol"], 99),
            d["persona"]["nombre"].lower(),
        ))
        cols_fijas = ("Nombre", "Cargo", "Turno", "Horario", "Cuadrante", "Modalidad")
        anchos = (18, 15, 15, 14, 8, 20)
        for c, (titulo, ancho) in enumerate(zip(cols_fijas, anchos)):
            tk.Label(
                interior, text=titulo, bg=MORADO_CLARO, fg=MORADO, width=ancho, anchor="w",
                font=("Segoe UI", 9, "bold"), padx=4,
            ).grid(row=0, column=c, rowspan=2, sticky="nsew", padx=1, pady=1)
        base = len(cols_fijas)
        for sem in range(4):
            tk.Label(
                interior, text=f"Semana {sem + 1}", bg=MORADO_CLARO, fg=MORADO,
                font=("Segoe UI", 8, "bold"),
            ).grid(row=0, column=base + sem * 7, columnspan=7, sticky="ew", padx=1, pady=1)
            for d in range(7):
                tk.Label(
                    interior, text="LMMJVSD"[d], bg=BLANCO, fg=GRIS,
                    font=("Segoe UI", 8, "bold"), width=3,
                ).grid(row=1, column=base + sem * 7 + d)

        presencia = {}
        fila = 2
        grupo_previo = "—"
        for d in datos:
            persona, malla = d["persona"], d["malla"]
            grupo = grupo_de(d)
            if grupo != grupo_previo:
                grupo_previo = grupo
                cantidad = sum(1 for x in datos if grupo_de(x) == grupo)
                tk.Label(
                    interior,
                    text=f"  TURNO {grupo} · {cantidad} integrante(s) trabajan juntos" if grupo
                    else f"  SIN TURNO ASIGNADO · {cantidad} integrante(s)",
                    bg=(MORADO if grupo == "A" else VERDE if grupo == "B" else "#6B6B7B"),
                    fg=BLANCO, anchor="w", font=("Segoe UI", 9, "bold"), pady=3,
                ).grid(row=fila, column=0, columnspan=base + 28, sticky="ew", padx=1, pady=(6, 2))
                fila += 1
            celdas = {(f["semana_mes"], f["dia_semana"]): f for f in malla}
            if malla:
                jornadas = {f["jornada"] for f in malla}
                horarios = sorted({f["horario"] for f in malla})
                turno = f"{malla[0]['grupo_turno']} · " + (
                    malla[0]["jornada"].capitalize() if len(jornadas) == 1 else "Rotativo"
                )
                horario = horarios[0] if len(horarios) == 1 else " / ".join(_horas_cortas(h) for h in horarios)
            else:
                turno = (
                    f"{persona['grupo_turno']} · {persona['jornada'].capitalize()}"
                    if persona["jornada"] else "Sin turno"
                )
                horario = "Sin malla"
            cuadrante = (persona.get("cuadrante") or "—").replace("Cuadrante ", "C")
            textos = (
                "≡ " + self._nombre_completo(persona),
                persona["rol"].replace("_", " ").capitalize(),
                turno, horario, cuadrante, " + ".join(d["modalidades"]) or "—",
            )
            for c, (txt, ancho) in enumerate(zip(textos, anchos)):
                lbl = tk.Label(
                    interior, text=txt, bg=BLANCO, fg=TEXTO if malla else GRIS, width=ancho,
                    anchor="w", font=("Segoe UI", 9, "bold" if c == 0 else "normal"), padx=4,
                )
                lbl.grid(row=fila, column=c, sticky="w", padx=1, pady=1)
                if c == 0:
                    lbl.configure(cursor="hand2")
                    self._hacer_arrastrable(lbl, {"tipo": "persona", "pid": persona["id"]}, destino=False)
            for k in range(28):
                sem, dia = k // 7 + 1, DIAS[k % 7]
                f = celdas.get((sem, dia))
                if f is None:
                    txt, bg, fg = "", "#F6F6FA", GRIS
                else:
                    est = f["estado"]
                    _t, bg, fg = _estilo_celda(est, f["jornada"])
                    txt = {"L": "·", "VAC": "V", "HEN": "HN"}.get(est, est)
                    if est in ("T", "HE", "HEN"):
                        clave = (persona["rol"], f["jornada"])
                        presencia.setdefault(clave, [0] * 28)[k] += 1
                celda = tk.Label(
                    interior, text=txt, bg=bg, fg=fg, width=3, font=("Segoe UI", 8, "bold"),
                )
                celda.grid(row=fila, column=base + k, padx=1, pady=1)
                if f is not None:
                    celda.configure(cursor="hand2")
                    self._hacer_arrastrable(
                        celda, {"tipo": "dia_eq", "pid": persona["id"], "id": f["id"]}
                    )
            fila += 1

        tk.Label(
            interior, text="Personas de turno por día", bg=BLANCO, fg=MORADO,
            font=("Segoe UI", 9, "bold"), anchor="w",
        ).grid(row=fila, column=0, columnspan=4, sticky="w", pady=(12, 2))
        fila += 1
        for rol in ROLES_PERSONAL:
            for jornada, nombre in (("DIURNO", "día"), ("NOCTURNO", "noche")):
                conteo = presencia.get((rol, jornada))
                if not conteo:
                    continue
                tk.Label(
                    interior, text=f"{rol.replace('_', ' ').capitalize()} · {nombre}",
                    bg=BLANCO, fg=TEXTO, anchor="w", font=("Segoe UI", 9),
                ).grid(row=fila, column=0, columnspan=4, sticky="w")
                for k, v in enumerate(conteo):
                    tk.Label(
                        interior, text=str(v), width=3, font=("Segoe UI", 8, "bold"),
                        bg=VERDE_CLARO if v else ROJO_CLARO, fg=VERDE_OSC if v else ROJO,
                    ).grid(row=fila, column=base + k, padx=1, pady=1)
                fila += 1

    # ---------------------------------------------- diálogo: turnos A y B juntos
    def _abrir_turnos_ab(self) -> None:
        resumen = self.servicio.resumen_turnos()
        t = resumen["turnos"]
        if t["A"]["total"] == 0 or t["B"]["total"] == 0:
            messagebox.showwarning(
                "Atención",
                "Para asignar por turnos hace falta al menos un integrante en el turno A y otro en el "
                "turno B, cada uno con su jornada. Regístrelos en «Agregar integrante».",
            )
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("Asignar turnos A y B")
        dlg.configure(bg=FONDO)
        dlg.geometry("1080x700")
        dlg.transient(self.root)
        dlg.grab_set()
        tk.Label(
            dlg, text="Turno A y turno B: cada turno trabaja junto", bg=MORADO, fg=BLANCO,
            font=("Segoe UI", 12, "bold"), padx=16, pady=10, anchor="w",
        ).pack(fill=tk.X)
        tk.Frame(dlg, bg=VERDE, height=3).pack(fill=tk.X)

        cuerpo = tk.Frame(dlg, bg=BLANCO, padx=16, pady=12)
        cuerpo.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        cuerpo.columnconfigure(0, weight=1)
        cuerpo.rowconfigure(5, weight=1)

        info = "   ·   ".join(
            f"Turno {g}: {t[g]['total']} integrantes ({t[g]['diurnos']} diurnos, {t[g]['nocturnos']} nocturnos)"
            for g in GRUPOS_TURNO
        )
        tk.Label(cuerpo, text=info, bg=BLANCO, fg=MORADO, font=("Segoe UI", 10, "bold"), anchor="w").grid(
            row=0, column=0, sticky="ew"
        )
        tk.Label(
            cuerpo,
            text="Todos los integrantes de un turno trabajan y descansan los mismos días; los horarios "
                 "diurnos se reparten entre los que marque (los nocturnos usan " + HORARIO_NOCTURNO + ").",
            bg=BLANCO, fg=GRIS, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=980,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 6))
        if resumen["sin_turno"]:
            tk.Label(
                cuerpo, text="Sin turno o jornada (no se incluyen): " + ", ".join(resumen["sin_turno"][:10]),
                bg="#FFF3D6", fg="#7A5200", font=("Segoe UI", 9), anchor="w", padx=8, pady=4,
            ).grid(row=2, column=0, sticky="ew", pady=(0, 6))

        ajustes = tk.Frame(cuerpo, bg=BLANCO)
        ajustes.grid(row=3, column=0, sticky="ew")
        tk.Label(ajustes, text="Horarios diurnos a repartir:", bg=BLANCO, fg=TEXTO, font=("Segoe UI", 10)).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        vars_horario = {}
        for h in HORARIOS_DIURNOS:
            v = tk.BooleanVar(value=True)
            vars_horario[h] = v
            tk.Checkbutton(
                ajustes, text=h, variable=v, bg=BLANCO, activebackground=BLANCO,
                font=("Segoe UI", 10), selectcolor=BLANCO,
            ).pack(side=tk.LEFT, padx=4)

        estado = {"opciones": []}
        var_op = tk.IntVar(value=0)
        marco_op = tk.Frame(cuerpo, bg=BLANCO)
        marco_op.grid(row=4, column=0, sticky="ew", pady=(10, 4))
        marco_prev = tk.Frame(cuerpo, bg=BLANCO, highlightbackground="#DDD3E8", highlightthickness=1)
        marco_prev.grid(row=5, column=0, sticky="nsew")
        lbl_pie = tk.Label(
            cuerpo, text="", bg=BLANCO, fg=ROJO, justify="left", anchor="w", wraplength=980,
            font=("Segoe UI", 9, "bold"),
        )
        lbl_pie.grid(row=6, column=0, sticky="ew", pady=(8, 0))

        def dibujar():
            for w in marco_prev.winfo_children():
                w.destroy()
            if not estado["opciones"]:
                return
            op = estado["opciones"][var_op.get()]
            marco_prev.columnconfigure(0, minsize=170)
            for sem in range(4):
                tk.Label(
                    marco_prev, text=f"Semana {sem + 1}", bg=MORADO_CLARO, fg=MORADO,
                    font=("Segoe UI", 8, "bold"),
                ).grid(row=0, column=1 + sem * 7, columnspan=7, sticky="ew", padx=1, pady=(6, 1))
                for d in range(7):
                    tk.Label(
                        marco_prev, text="LMMJVSD"[d], bg=BLANCO, fg=GRIS, font=("Segoe UI", 8, "bold"), width=3,
                    ).grid(row=1, column=1 + sem * 7 + d)
            filas = (("Turno A trabaja", op["seq_a"], MORADO), ("Turno B trabaja", op["seq_b"], VERDE))
            for r, (nombre, seq, color) in enumerate(filas, start=2):
                tk.Label(marco_prev, text=nombre, bg=BLANCO, fg=color, anchor="w", font=("Segoe UI", 9, "bold")).grid(
                    row=r, column=0, sticky="w", padx=8
                )
                for k, libre in enumerate(seq):
                    tk.Label(
                        marco_prev, text="" if libre else "T", width=3, font=("Segoe UI", 8, "bold"),
                        bg="#ECECF2" if libre else color, fg=BLANCO,
                    ).grid(row=r, column=1 + k, padx=1, pady=1)
            tk.Label(
                marco_prev, text="Turnos en servicio ese día", bg=BLANCO, fg=TEXTO, anchor="w", font=("Segoe UI", 9)
            ).grid(row=4, column=0, sticky="w", padx=8, pady=(6, 0))
            for k in range(28):
                n = (not op["seq_a"][k]) + (not op["seq_b"][k])
                tk.Label(
                    marco_prev, text=str(n), width=3, font=("Segoe UI", 8, "bold"),
                    bg=ROJO_CLARO if n == 0 else VERDE_CLARO if n == 1 else "#A6DDB9",
                    fg=ROJO if n == 0 else VERDE_OSC,
                ).grid(row=4, column=1 + k, padx=1, pady=(6, 0))
            if op["avisos"]:
                lbl_pie.config(text="⚠ " + "  ".join(op["avisos"]), fg=ROJO)
            else:
                lbl_pie.config(text="✔ Todos los días del mes quedan cubiertos por al menos un turno.", fg=VERDE_OSC)

        def generar():
            try:
                estado["opciones"] = self.servicio.generar_opciones_turnos_ab()
            except ValueError as err:
                messagebox.showerror("Error", str(err), parent=dlg)
                return
            for w in marco_op.winfo_children():
                w.destroy()
            for i, op in enumerate(estado["opciones"]):
                m = op["metricas"]
                ttk.Radiobutton(
                    marco_op,
                    text=f"{op['nombre_opcion']}   ·   días sin cobertura: {m['huecos']}   ·   "
                         f"días con ambos turnos: {m['ambos_turnos']}",
                    value=i, variable=var_op, style="Radio.TRadiobutton", command=dibujar,
                ).pack(anchor="w", pady=1)
            var_op.set(0)
            dibujar()

        def asignar():
            if not estado["opciones"]:
                messagebox.showinfo("Atención", "Primero genere las opciones.", parent=dlg)
                return
            horarios = [h for h, v in vars_horario.items() if v.get()]
            op = estado["opciones"][var_op.get()]
            if not messagebox.askyesno(
                "Confirmar",
                "Se reemplazará la malla mensual de todos los integrantes con turno y jornada "
                f"(turno A: {t['A']['total']}, turno B: {t['B']['total']}).\n¿Continuar?",
                parent=dlg,
            ):
                return
            try:
                n = self.servicio.asignar_turnos_ab(op, horarios)
            except ValueError as err:
                messagebox.showerror("No se pudo asignar", str(err), parent=dlg)
                return
            dlg.destroy()
            self._mostrar_malla_guardada()
            self._refrescar_vistas()
            messagebox.showinfo("Turnos asignados", f"Se asignó la malla mensual a {n} integrantes.")

        botones = tk.Frame(cuerpo, bg=BLANCO)
        botones.grid(row=7, column=0, sticky="ew", pady=(10, 0))
        self._btn(botones, text="Generar opciones", style="Morado.TButton", command=generar).pack(side=tk.LEFT)
        self._btn(
            botones, text="Asignar turnos A y B", style="Verde.TButton", command=asignar
        ).pack(side=tk.RIGHT)

    # ------------------------------------------------------- pestaña: modalidad
    def _construir_tab_modalidad(self, tab) -> None:
        tk.Label(
            tab, text="Modalidades y cuadrante de los patrulleros", bg=FONDO, fg=MORADO,
            font=("Segoe UI", 13, "bold"), anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            tab,
            text="① Seleccione uno o varios patrulleros (Ctrl o Mayús para varios)   ② Pulse una modalidad para "
                 "agregarla (si todos ya la tienen, se quita). Una persona puede usar varias.",
            bg=FONDO, fg=GRIS, font=("Segoe UI", 10), anchor="w", justify="left", wraplength=820,
        ).pack(fill=tk.X, pady=(2, 8))

        marco = tk.Frame(tab, bg=BLANCO, highlightbackground="#DDD3E8", highlightthickness=1)
        marco.pack(fill=tk.BOTH, expand=True)
        columnas = ("nombre", "turno", "jornada", "cuadrante", "modalidad")
        self.tabla_mod = ttk.Treeview(marco, columns=columnas, show="headings", selectmode="extended")
        for col, titulo, ancho in (
            ("nombre", "Patrullero", 200), ("turno", "Turno", 60),
            ("jornada", "Jornada", 90), ("cuadrante", "Cuadrante", 100), ("modalidad", "Modalidades", 220),
        ):
            self.tabla_mod.heading(col, text=titulo)
            self.tabla_mod.column(col, width=ancho, anchor="w")
        sb = ttk.Scrollbar(marco, orient=tk.VERTICAL, command=self.tabla_mod.yview)
        self.tabla_mod.configure(yscrollcommand=sb.set)
        self.tabla_mod.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        botones = tk.Frame(tab, bg=FONDO)
        botones.pack(fill=tk.X, pady=(10, 0))
        colores = {
            "Móvil": (MORADO, MORADO_OSC), "Moto": (VERDE, VERDE_OSC),
            "Infantería": ("#B8731A", "#8F5810"), "Bicicleta": ("#2B6F8F", "#1F5169"),
        }
        for modalidad in MODALIDADES:
            bg, activo = colores.get(modalidad, (MORADO, MORADO_OSC))
            self._boton_grande(
                botones, modalidad.upper(), bg, activo,
                lambda m=modalidad: self._alternar_modalidad(m),
                side=tk.LEFT, fill=tk.X, expand=True, padx=3,
            )
        extra = tk.Frame(tab, bg=FONDO)
        extra.pack(fill=tk.X, pady=(8, 0))
        self._btn(
            extra, text="Repartir automáticamente (sin modalidad)", style="Verde.TButton",
            command=self._repartir_modalidades,
        ).pack(side=tk.LEFT)
        self._btn(
            extra, text="Quitar todas a la selección", style="Gris.TButton",
            command=self._quitar_modalidades_seleccion,
        ).pack(side=tk.LEFT, padx=(8, 0))
        self._btn(
            extra, text="Asignar cuadrante", style="Morado.TButton",
            command=self._asignar_cuadrante_seleccion,
        ).pack(side=tk.RIGHT)
        self.combo_cuad_mod = ttk.Combobox(
            extra, values=(SIN_CUADRANTE, *CUADRANTES), state="readonly", width=16
        )
        self.combo_cuad_mod.current(1)
        self.combo_cuad_mod.pack(side=tk.RIGHT, padx=6)
        self.lbl_resumen_mod = tk.Label(
            tab, text="", bg=FONDO, fg=VERDE_OSC, font=("Segoe UI", 10, "bold"), anchor="w",
        )
        self.lbl_resumen_mod.pack(fill=tk.X, pady=(8, 0))

    def _pintar_modalidad(self) -> None:
        if not hasattr(self, "tabla_mod"):
            return
        seleccion = set(self.tabla_mod.selection())
        for item in self.tabla_mod.get_children():
            self.tabla_mod.delete(item)
        modalidades = self.servicio.obtener_modalidades()
        conteo = {m: 0 for m in MODALIDADES}
        sin_asignar = 0
        for p in self.servicio.listar_personal():
            if p["rol"] != ROL_PATRULLERO:
                continue
            mods = modalidades.get(p["id"], [])
            for m in mods:
                conteo[m] += 1
            if not mods:
                sin_asignar += 1
            self.tabla_mod.insert(
                "", tk.END, iid=str(p["id"]),
                values=(
                    self._nombre_completo(p),
                    p["grupo_turno"] or "—",
                    p["jornada"].capitalize() if p["jornada"] else "—",
                    p.get("cuadrante") or "—",
                    " + ".join(mods) or "Sin asignar",
                ),
            )
        for iid in seleccion:
            if self.tabla_mod.exists(iid):
                self.tabla_mod.selection_add(iid)
        self.lbl_resumen_mod.config(
            text="  ·  ".join(f"{m}: {n}" for m, n in conteo.items()) + f"  ·  Sin modalidad: {sin_asignar}"
        )

    def _ids_seleccion_mod(self):
        ids = [int(i) for i in self.tabla_mod.selection()]
        if not ids:
            messagebox.showwarning("Atención", "Seleccione al menos un patrullero de la tabla.")
        return ids

    def _tras_cambio_modalidad(self) -> None:
        self._refrescar_vistas()
        self._mostrar_malla_guardada()

    def _alternar_modalidad(self, modalidad: str) -> None:
        ids = self._ids_seleccion_mod()
        if not ids:
            return
        actuales = self.servicio.obtener_modalidades()
        try:
            if all(modalidad in actuales.get(pid, []) for pid in ids):
                self.servicio.quitar_modalidad(ids, modalidad)
            else:
                self.servicio.agregar_modalidad(ids, modalidad)
        except ValueError as err:
            messagebox.showerror("Error", str(err))
            return
        self._tras_cambio_modalidad()

    def _quitar_modalidades_seleccion(self) -> None:
        ids = self._ids_seleccion_mod()
        if not ids:
            return
        try:
            self.servicio.asignar_modalidades(ids, [])
        except ValueError as err:
            messagebox.showerror("Error", str(err))
            return
        self._tras_cambio_modalidad()

    def _repartir_modalidades(self) -> None:
        ids = [int(i) for i in self.tabla_mod.selection()] or None
        n = self.servicio.repartir_modalidades_auto(ids)
        self._tras_cambio_modalidad()
        messagebox.showinfo(
            "Modalidades repartidas",
            f"Se asignó una modalidad a {n} patrullero(s) que no tenían, de forma pareja.\n"
            "Quienes ya tenían modalidades no se modificaron; puede agregar más con los botones.",
        )

    def _asignar_cuadrante_seleccion(self) -> None:
        ids = self._ids_seleccion_mod()
        if not ids:
            return
        cuadrante = None if self.combo_cuad_mod.current() == 0 else self.combo_cuad_mod.get()
        try:
            self.servicio.asignar_cuadrante(ids, cuadrante)
        except ValueError as err:
            messagebox.showerror("Error", str(err))
            return
        self._tras_cambio_modalidad()

    # ------------------------------------------------------ asistente individual
    def _abrir_asistente_malla(self) -> None:
        personal_id, etiqueta = self._id_seleccionado()
        if personal_id is None:
            messagebox.showwarning("Atención", "Seleccione primero un integrante de la lista.")
            return

        self.opciones_actuales = []
        dlg = tk.Toplevel(self.root)
        dlg.title("Asignar malla individual")
        dlg.configure(bg=FONDO)
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(
            dlg, text=f"Malla para: {etiqueta}", bg=MORADO, fg=BLANCO,
            font=("Segoe UI", 11, "bold"), padx=16, pady=10, anchor="w",
        ).pack(fill=tk.X)
        tk.Frame(dlg, bg=VERDE, height=3).pack(fill=tk.X)

        cuerpo = tk.Frame(dlg, bg=BLANCO, padx=18, pady=14)
        cuerpo.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)

        tk.Label(
            cuerpo, text="Paso 1 · Defina el turno", bg=BLANCO, fg=MORADO,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        def fila(r, texto, widget):
            ttk.Label(cuerpo, text=texto).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 12))
            widget.grid(row=r, column=1, sticky="ew", pady=3)

        perfil = next((p for p in self.servicio.listar_personal() if p["id"] == personal_id), {})
        combo_grupo = ttk.Combobox(cuerpo, values=GRUPOS_TURNO, state="readonly", width=26)
        combo_grupo.current(GRUPOS_TURNO.index(perfil["grupo_turno"]) if perfil.get("grupo_turno") in GRUPOS_TURNO else 0)
        fila(1, "Turno (A / B)", combo_grupo)

        combo_jornada = ttk.Combobox(
            cuerpo, values=JORNADAS, state="readonly", width=26
        )
        combo_jornada.current(JORNADAS.index(perfil["jornada"]) if perfil.get("jornada") in JORNADAS else 0)
        fila(2, "Jornada", combo_jornada)

        combo_horario = ttk.Combobox(cuerpo, values=HORARIOS_DIURNOS, state="readonly", width=26)
        fila(3, "Horario", combo_horario)

        # el cuadrante y las modalidades son propios de la persona (no dependen de la malla)
        combo_cuadrante = ttk.Combobox(
            cuerpo, values=(SIN_CUADRANTE, *CUADRANTES), state="readonly", width=26
        )
        combo_cuadrante.set(perfil.get("cuadrante") or SIN_CUADRANTE)
        fila(4, "Cuadrante de la persona", combo_cuadrante)

        vars_mod = {}  # las modalidades solo aplican a patrulleros
        if perfil.get("rol") == ROL_PATRULLERO:
            marco_mod = tk.Frame(cuerpo, bg=BLANCO)
            actuales = self.servicio.obtener_modalidades_persona(personal_id)
            for k, m in enumerate(MODALIDADES):
                vars_mod[m] = tk.BooleanVar(value=m in actuales)
                tk.Checkbutton(
                    marco_mod, text=m, variable=vars_mod[m], bg=BLANCO, activebackground=BLANCO,
                    selectcolor=BLANCO, font=("Segoe UI", 9), anchor="w",
                ).grid(row=k // 2, column=k % 2, sticky="w", padx=(0, 10))
            fila(5, "Modalidades (puede usar varias)", marco_mod)

        def actualizar_horarios(_e=None):
            if combo_jornada.get() == "DIURNO":
                combo_horario["values"] = HORARIOS_DIURNOS
            else:
                combo_horario["values"] = (HORARIO_NOCTURNO,)
            combo_horario.current(0)

        combo_jornada.bind("<<ComboboxSelected>>", actualizar_horarios)
        actualizar_horarios()

        marco_opciones = tk.Frame(cuerpo, bg=BLANCO)
        var_opcion = tk.IntVar(value=0)
        btn_asignar = self._btn(cuerpo, text="Asignar esta malla", style="Verde.TButton")

        def generar():
            try:
                self.opciones_actuales = self.servicio.generar_opciones_malla_mensual(
                    grupo_turno=combo_grupo.get(),
                    jornada=combo_jornada.get(),
                    horario=combo_horario.get(),
                )
            except ValueError as err:
                messagebox.showerror("Error", str(err), parent=dlg)
                return
            for w in marco_opciones.winfo_children():
                w.destroy()
            tk.Label(
                marco_opciones, text="Paso 3 · Elija una de las opciones",
                bg=BLANCO, fg=MORADO, font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w", pady=(0, 4))
            for idx, op in enumerate(self.opciones_actuales):
                ttk.Radiobutton(
                    marco_opciones, text=op["nombre_opcion"], value=idx,
                    variable=var_opcion, style="Radio.TRadiobutton",
                ).pack(anchor="w", pady=2)
            var_opcion.set(0)
            marco_opciones.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(10, 0))
            btn_asignar.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        tk.Label(
            cuerpo, text="Paso 2 · Genere las opciones", bg=BLANCO, fg=MORADO,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(12, 6))
        self._btn(
            cuerpo, text="Generar opciones", style="Morado.TButton", command=generar
        ).grid(row=7, column=0, columnspan=2, sticky="ew")

        def asignar():
            if not self.opciones_actuales:
                return
            idx = var_opcion.get()
            try:
                self.servicio.asignar_cuadrante(
                    [personal_id], None if combo_cuadrante.current() == 0 else combo_cuadrante.get()
                )
                if vars_mod:
                    self.servicio.asignar_modalidades(
                        [personal_id], [m for m, v in vars_mod.items() if v.get()]
                    )
                # reemplaza la malla previa del integrante (transacción única)
                self.servicio.asignar_opcion_a_personal(personal_id, self.opciones_actuales[idx])
                self.servicio.actualizar_perfil_turno(
                    personal_id, combo_grupo.get(), combo_jornada.get()
                )
            except ValueError as err:
                messagebox.showerror("Error", str(err), parent=dlg)
                return
            dlg.destroy()
            self._mostrar_malla_guardada()
            self._refrescar_vistas()
            messagebox.showinfo("Asignado", "Malla mensual asignada y guardada correctamente.")

        btn_asignar.config(command=asignar)
        cuerpo.columnconfigure(1, weight=1)

    # ------------------------------------------------- planificador de equipo 24/7
    def _abrir_planificador_equipo(self) -> None:
        personal = [
            (p["id"], self._nombre_completo(p), p["rol"], p["jornada"])
            for p in self.servicio.listar_personal()
        ]
        if len(personal) < 2:
            messagebox.showwarning("Atención", "Registre al menos 2 integrantes para planificar un equipo.")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("Planificar equipo 24/7")
        dlg.configure(bg=FONDO)
        dlg.geometry("1120x720")
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(
            dlg, text="Planificación mensual del equipo · cobertura 24/7", bg=MORADO, fg=BLANCO,
            font=("Segoe UI", 12, "bold"), padx=16, pady=10, anchor="w",
        ).pack(fill=tk.X)
        tk.Frame(dlg, bg=VERDE, height=3).pack(fill=tk.X)

        nb = ttk.Notebook(dlg)
        nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        tab1 = tk.Frame(nb, bg=BLANCO, padx=16, pady=14)
        tab2 = tk.Frame(nb, bg=BLANCO, padx=16, pady=14)
        nb.add(tab1, text="  1 · Equipo y dotación  ")
        nb.add(tab2, text="  2 · Opciones y vista previa  ")

        estado = {"opciones": []}
        req_vars = {}  # rol -> (IntVar día, IntVar noche)

        # ---------- Pestaña 1 ----------
        tab1.columnconfigure(0, weight=3)
        tab1.columnconfigure(1, weight=2)
        tab1.columnconfigure(2, weight=3)
        tab1.rowconfigure(1, weight=1)

        for col, titulo in enumerate(("¿Quiénes participan?", "Parámetros", "Dotación mínima por turno")):
            tk.Label(
                tab1, text=titulo, bg=BLANCO, fg=MORADO, font=("Segoe UI", 10, "bold"), anchor="w",
            ).grid(row=0, column=col, sticky="w", pady=(0, 6))

        # Personas
        marco_l = tk.Frame(tab1, bg=BLANCO)
        marco_l.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        sc = ttk.Scrollbar(marco_l, orient=tk.VERTICAL)
        lista = tk.Listbox(
            marco_l, selectmode=tk.MULTIPLE, exportselection=False, activestyle="none",
            bd=0, highlightthickness=1, highlightbackground="#DDD3E8",
            selectbackground=MORADO, selectforeground=BLANCO,
            font=("Segoe UI", 10), yscrollcommand=sc.set,
        )
        sc.config(command=lista.yview)
        for _pid, nombre, rol, jornada in personal:
            lista.insert(tk.END, f"  {nombre}  ({rol})  ·  {jornada.capitalize() if jornada else 'sin jornada'}")
        lista.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)

        botones_l = tk.Frame(tab1, bg=BLANCO)
        botones_l.grid(row=2, column=0, sticky="ew", pady=(8, 0), padx=(0, 16))
        marco_dot = tk.Frame(tab1, bg=BLANCO)
        marco_dot.grid(row=1, column=2, sticky="nw")

        # Parámetros
        marco_p = tk.Frame(tab1, bg=BLANCO)
        marco_p.grid(row=1, column=1, sticky="nw", padx=(0, 16))

        def fila_p(r, texto, widget):
            ttk.Label(marco_p, text=texto).grid(row=2 * r, column=0, sticky="w")
            widget.grid(row=2 * r + 1, column=0, sticky="ew", pady=(0, 8))

        tk.Label(
            marco_p, text="El cuadrante de cada persona no cambia\n(se asigna aparte, por persona).",
            bg=BLANCO, fg=GRIS, justify="left", font=("Segoe UI", 9),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        combo_mod = ttk.Combobox(
            marco_p,
            values=("Mantener las actuales", *(f"Agregar {m}" for m in MODALIDADES),
                    "Repartir a quienes no tienen"),
            state="readonly", width=26,
        )
        combo_mod.current(0)
        fila_p(1, "Modalidades (solo patrulleros)", combo_mod)
        combo_hor = ttk.Combobox(marco_p, values=HORARIOS_DIURNOS, state="readonly", width=26)
        combo_hor.current(0)
        fila_p(2, "Horario diurno", combo_hor)
        ttk.Label(marco_p, text=f"Horario nocturno: {HORARIO_NOCTURNO}", foreground=GRIS).grid(
            row=6, column=0, sticky="w"
        )

        # Dotación (se reconstruye según los roles seleccionados)
        def pintar_dotacion(_e=None):
            for w in marco_dot.winfo_children():
                w.destroy()
            conteo = {}
            for i in lista.curselection():
                conteo[personal[i][2]] = conteo.get(personal[i][2], 0) + 1
            if not conteo:
                tk.Label(
                    marco_dot, text="Seleccione personas para definir\nla dotación de cada rol.",
                    bg=BLANCO, fg=GRIS, justify="left", font=("Segoe UI", 10),
                ).grid(row=0, column=0, sticky="w")
                return
            for c, t in enumerate(("Rol", "Día", "Noche", "Equipo")):
                tk.Label(
                    marco_dot, text=t, bg=BLANCO, fg=GRIS, font=("Segoe UI", 9, "bold"), anchor="w",
                ).grid(row=0, column=c, sticky="w", padx=(0, 10))
            for r, (rol, n) in enumerate(sorted(conteo.items()), start=1):
                vd, vn = req_vars.setdefault(rol, (tk.IntVar(value=1), tk.IntVar(value=1)))
                ttk.Label(marco_dot, text=rol).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=3)
                lbl = tk.Label(marco_dot, bg=BLANCO, anchor="w", font=("Segoe UI", 9, "bold"))

                def actualizar(_e=None, v1=vd, v2=vn, etiqueta=lbl, cantidad=n):
                    try:
                        minimo = minimo_personas(v1.get(), v2.get())
                    except tk.TclError:
                        return
                    etiqueta.config(
                        text=f"{cantidad} pers. · mín. teórico {minimo}",
                        fg=VERDE_OSC if cantidad >= minimo else ROJO,
                    )

                for col, var in ((1, vd), (2, vn)):
                    sp = ttk.Spinbox(marco_dot, from_=0, to=20, width=4, textvariable=var, command=actualizar)
                    sp.bind("<KeyRelease>", actualizar)
                    sp.grid(row=r, column=col, padx=(0, 10), pady=3)
                lbl.grid(row=r, column=3, sticky="w")
                actualizar()
            tk.Label(
                marco_dot,
                text="Personas que deben estar de turno\nen cada día y cada jornada, por rol.",
                bg=BLANCO, fg=GRIS, justify="left", font=("Segoe UI", 9),
            ).grid(row=len(conteo) + 1, column=0, columnspan=4, sticky="w", pady=(10, 0))

        lista.bind("<<ListboxSelect>>", pintar_dotacion)
        self._btn(
            botones_l, text="Seleccionar todos", style="Morado.TButton",
            command=lambda: (lista.select_set(0, tk.END), pintar_dotacion()),
        ).pack(side=tk.LEFT)
        self._btn(
            botones_l, text="Quitar selección", style="Morado.TButton",
            command=lambda: (lista.select_clear(0, tk.END), pintar_dotacion()),
        ).pack(side=tk.LEFT, padx=(8, 0))
        pintar_dotacion()

        # ---------- Pestaña 2 ----------
        tab2.rowconfigure(2, weight=1)
        tab2.columnconfigure(0, weight=1)
        marco_op = tk.Frame(tab2, bg=BLANCO)
        marco_op.grid(row=0, column=0, sticky="ew")
        tk.Label(
            tab2,
            text="D = turno diurno (verde)   ·   N = turno nocturno (morado)   ·   · = libre   ·   "
                 "Filas inferiores: personas de turno por día (rojo = bajo el mínimo)",
            bg=BLANCO, fg=GRIS, font=("Segoe UI", 9), anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 4))
        marco_prev = tk.Frame(tab2, bg=BLANCO, highlightbackground="#DDD3E8", highlightthickness=1)
        marco_prev.grid(row=2, column=0, sticky="nsew")
        interior = self._marco_scroll(marco_prev)

        pie = tk.Frame(tab2, bg=BLANCO)
        pie.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        lbl_pie = tk.Label(pie, text="", bg=BLANCO, fg=ROJO, justify="left", anchor="w",
                           wraplength=820, font=("Segoe UI", 9, "bold"))
        lbl_pie.pack(side=tk.LEFT, fill=tk.X, expand=True)
        var_op = tk.IntVar(value=0)

        def dibujar():
            for w in interior.winfo_children():
                w.destroy()
            if not estado["opciones"]:
                return
            op = estado["opciones"][var_op.get()]
            tk.Label(interior, text="", bg=BLANCO, width=30).grid(row=0, column=0, rowspan=2)
            for sem in range(4):
                tk.Label(
                    interior, text=f"Semana {sem + 1}", bg=MORADO_CLARO, fg=MORADO,
                    font=("Segoe UI", 8, "bold"),
                ).grid(row=0, column=1 + sem * 7, columnspan=7, sticky="ew", padx=1)
                for d in range(7):
                    tk.Label(
                        interior, text="LMMJVSD"[d], bg=BLANCO, fg=GRIS,
                        font=("Segoe UI", 8, "bold"), width=3,
                    ).grid(row=1, column=1 + sem * 7 + d)
            fila = 2
            for pid, nombre, rol in op["personas"]:
                tk.Label(
                    interior, text=f"{nombre} ({rol})", bg=BLANCO, anchor="w", font=("Segoe UI", 9),
                ).grid(row=fila, column=0, sticky="w", padx=(0, 8))
                for k, (est, jor) in enumerate(op["asignaciones"][pid]["grilla"]):
                    if est == "T":
                        txt = "D" if jor == DIURNO else "N"
                        bg = VERDE if jor == DIURNO else MORADO
                        fg = BLANCO
                    else:
                        txt, bg, fg = "·", "#ECECF2", GRIS
                    tk.Label(
                        interior, text=txt, bg=bg, fg=fg, width=3, font=("Segoe UI", 8, "bold"),
                    ).grid(row=fila, column=1 + k, padx=1, pady=1)
                fila += 1
            tk.Label(
                interior, text="Cobertura (personas de turno)", bg=BLANCO, fg=MORADO,
                font=("Segoe UI", 9, "bold"), anchor="w",
            ).grid(row=fila, column=0, sticky="w", pady=(10, 2))
            fila += 1
            for rol, (rd, rn) in op["req"].items():
                for t, (nom, req) in enumerate((("día", rd), ("noche", rn))):
                    if req <= 0:
                        continue
                    tk.Label(
                        interior, text=f"{rol} · {nom} (mín. {req})", bg=BLANCO,
                        anchor="w", font=("Segoe UI", 9),
                    ).grid(row=fila, column=0, sticky="w")
                    for k in range(28):
                        v = op["conteo"][rol][t][k]
                        ok = v >= req
                        tk.Label(
                            interior, text=str(v), width=3, font=("Segoe UI", 8, "bold"),
                            bg=VERDE_CLARO if ok else ROJO_CLARO, fg=VERDE_OSC if ok else ROJO,
                        ).grid(row=fila, column=1 + k, padx=1, pady=1)
                    fila += 1
            m = op["metricas"]
            if op["avisos"]:
                lbl_pie.config(text="⚠ " + "  ".join(op["avisos"]), fg=ROJO)
            else:
                lbl_pie.config(
                    text=f"✔ Cobertura 24/7 completa · fines de semana libres por persona: {m['findes_prom']:.1f}",
                    fg=VERDE_OSC,
                )

        def mostrar_opciones():
            for w in marco_op.winfo_children():
                w.destroy()
            for i, op in enumerate(estado["opciones"]):
                m = op["metricas"]
                ttk.Radiobutton(
                    marco_op,
                    text=f"{op['nombre_opcion']}   ·   cobertura {m['cobertura_pct']:.0f}%   ·   "
                         f"fines de semana libres por persona: {m['findes_prom']:.1f}",
                    value=i, variable=var_op, style="Radio.TRadiobutton", command=dibujar,
                ).pack(anchor="w", pady=2)
            var_op.set(0)
            dibujar()

        def generar():
            seleccion = lista.curselection()
            if len(seleccion) < 2:
                messagebox.showwarning("Atención", "Seleccione al menos 2 integrantes.", parent=dlg)
                return
            personas = [personal[i] for i in seleccion]
            roles = {p[2] for p in personas}
            try:
                requerimientos = {
                    rol: (req_vars[rol][0].get(), req_vars[rol][1].get()) for rol in roles
                }
                estado["opciones"] = self.servicio.generar_opciones_equipo(personas, requerimientos)
            except tk.TclError:
                messagebox.showerror("Error", "La dotación debe ser un número entero.", parent=dlg)
                return
            except ValueError as err:
                messagebox.showerror("Error", str(err), parent=dlg)
                return
            mostrar_opciones()
            nb.select(tab2)

        def asignar_plan():
            if not estado["opciones"]:
                return
            op = estado["opciones"][var_op.get()]
            if op["metricas"]["cobertura_pct"] < 100:
                if not messagebox.askyesno(
                    "Cobertura incompleta",
                    "Esta opción no cubre el 24/7 completo con la dotación indicada.\n"
                    "¿Asignarla de todos modos?",
                    parent=dlg,
                ):
                    return
            elegida = combo_mod.get()
            patrulleros = [p[0] for p in op["personas"] if p[2] == ROL_PATRULLERO]
            modalidades = {}
            if elegida.startswith("Agregar "):
                modalidades = {pid: [elegida[len("Agregar "):]] for pid in patrulleros}
            try:
                self.servicio.asignar_plan_equipo(op, combo_hor.get(), modalidades)
                if elegida.startswith("Repartir"):
                    self.servicio.repartir_modalidades_auto(patrulleros)
            except ValueError as err:
                messagebox.showerror("No se pudo guardar", str(err), parent=dlg)
                return
            dlg.destroy()
            self._mostrar_malla_guardada()
            self._refrescar_vistas()
            messagebox.showinfo(
                "Plan asignado", f"Se asignó la malla mensual a {len(op['personas'])} integrantes."
            )

        self._btn(
            tab1, text="Generar opciones de planificación", style="Morado.TButton", command=generar,
        ).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(16, 0))
        self._btn(
            pie, text="Asignar este plan al equipo", style="Verde.TButton", command=asignar_plan,
        ).pack(side=tk.RIGHT)


if __name__ == "__main__":
    ventana = tk.Tk()
    app = AplicacionTurnosGUI(ventana)
    ventana.mainloop()
