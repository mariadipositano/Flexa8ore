"""
orario_widget.py — Widget desktop "calcolo orario di uscita"
=============================================================
Replica la logica del foglio di calcolo:

    ore_mattina   = uscita_pranzo - entrata
    ore_rimanenti = MONTE_ORE - ore_mattina
    uscita_finale = rientro_pranzo + ore_rimanenti

Con l'opzione "pausa minima 30 minuti" attiva, se la pausa reale dura
meno di 30 minuti il rientro viene considerato come uscita_pranzo + 30 min
(la pausa viene cioè "allungata" fino al minimo contrattuale).

Usa SOLO la libreria standard (tkinter): nessun pip install necessario.
Testato con Python 3.10+ su Windows 10/11.
"""

import tkinter as tk
from tkinter import font as tkfont
import random
import math

# ============================================================
#  IMPOSTAZIONI MODIFICABILI
# ============================================================
MONTE_ORE_MINUTI = 8 * 60      # ore lavorative nette al giorno (8h = 480 min)
PAUSA_MINIMA_MINUTI = 30       # durata minima della pausa pranzo
PAUSA_MINIMA_ATTIVA = True     # stato iniziale della manopola sinistra

LARGHEZZA, ALTEZZA = 560, 170  # dimensioni del widget (px)
RAGGIO_MANOPOLA = 26           # raggio delle due "manopoline" laterali

# Palette ispirata alla tavolozza di Kandinsky (Several Circles, 1926)
SFONDO = "#0e0f12"
PALETTE = [
    "#2a63b8", "#e3b72a", "#c73a2a", "#1d8b7a", "#6b3f9e",
    "#e07b2a", "#d9d2c5", "#3aa65c", "#8ab6e8", "#b23a6b",
]
COLORE_TESTO = "#f4f1ea"
COLORE_ETICHETTA = "#b9b4a8"
COLORE_OUTPUT = "#ffd45c"
COLORE_ERRORE = "#ff6b5a"
COLORE_LED_ON = "#3aa65c"
COLORE_LED_OFF = "#444"


# ============================================================
#  FUNZIONI DI CALCOLO (indipendenti dall'interfaccia)
# ============================================================
def parse_orario(testo: str):
    """
    Converte 'HH:MM', 'HH.MM', 'HHMM' o 'HH' in minuti dalla mezzanotte.
    Restituisce None se il testo non è un orario valido.
    """
    t = testo.strip().replace(".", ":").replace(",", ":")
    if not t:
        return None
    if ":" in t:
        parti = t.split(":")
        if len(parti) != 2 or not all(p.isdigit() for p in parti):
            return None
        h, m = int(parti[0]), int(parti[1])
    elif t.isdigit():
        if len(t) <= 2:          # "9" o "09" -> 09:00
            h, m = int(t), 0
        elif len(t) in (3, 4):   # "907" -> 09:07, "1203" -> 12:03
            h, m = int(t[:-2]), int(t[-2:])
        else:
            return None
    else:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def formatta_orario(minuti: int) -> str:
    """Converte minuti dalla mezzanotte in 'HH:MM' (gestisce il passaggio oltre le 24)."""
    minuti %= 24 * 60
    return f"{minuti // 60:02d}:{minuti % 60:02d}"


def calcola_uscita(entrata: int, uscita_pranzo: int, rientro: int,
                   monte_ore: int = MONTE_ORE_MINUTI,
                   pausa_minima: int | None = PAUSA_MINIMA_MINUTI):
    """
    Restituisce (uscita_finale, info) in minuti, oppure (None, messaggio_errore).
    `pausa_minima` = None disattiva il vincolo dei 30 minuti.
    """
    if uscita_pranzo < entrata:
        return None, "Uscita pranzo prima dell'entrata"
    if rientro < uscita_pranzo:
        return None, "Rientro prima dell'uscita pranzo"

    ore_mattina = uscita_pranzo - entrata              # es. 12:03 - 09:07 = 2h56
    rientro_effettivo = rientro
    if pausa_minima is not None:
        # Se la pausa reale è più corta del minimo, la "allunghiamo"
        rientro_effettivo = max(rientro, uscita_pranzo + pausa_minima)

    ore_rimanenti = monte_ore - ore_mattina            # es. 8h - 2h56 = 5h04
    uscita_finale = rientro_effettivo + ore_rimanenti  # es. 12:33 + 5h04 = 17:37
    info = {
        "mattina": ore_mattina,
        "pausa": rientro_effettivo - uscita_pranzo,
        "pomeriggio": ore_rimanenti,
    }
    return uscita_finale, info


# ============================================================
#  INTERFACCIA
# ============================================================
class OrarioWidget(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Orario di uscita")
        self.overrideredirect(True)            # niente barra del titolo (frameless)
        self.attributes("-topmost", True)      # resta sopra le altre finestre
        self.resizable(False, False)
        self.configure(bg=SFONDO)

        # Posizione iniziale: angolo in basso a destra, con un margine
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{LARGHEZZA}x{ALTEZZA}+{sw - LARGHEZZA - 40}+{sh - ALTEZZA - 90}")

        self.pausa_minima_attiva = PAUSA_MINIMA_ATTIVA
        self._drag_dx = self._drag_dy = 0

        # Font (Segoe UI è presente su tutti i Windows; fallback automatico altrove)
        self.f_label = tkfont.Font(family="Segoe UI", size=8)
        self.f_input = tkfont.Font(family="Segoe UI", size=15)
        self.f_output = tkfont.Font(family="Segoe UI Semibold", size=24)
        self.f_info = tkfont.Font(family="Segoe UI", size=8)

        # Canvas = sfondo pittorico + contenitore di tutti i controlli
        self.canvas = tk.Canvas(self, width=LARGHEZZA, height=ALTEZZA,
                                bg=SFONDO, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self._disegna_sfondo()
        self._disegna_manopole()
        self._crea_campi()

        # Trascinamento dal corpo del widget
        self.canvas.bind("<ButtonPress-1>", self._inizio_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        # Chiusura rapida con Esc
        self.bind("<Escape>", lambda e: self.destroy())

        self._aggiorna_led()

    # ---------- disegno dello sfondo stile "cerchi" ----------
    def _disegna_sfondo(self):
        """Disegna cerchi sovrapposti di dimensioni e colori diversi su fondo scuro."""
        rnd = random.Random(1926)  # seme fisso -> stessa composizione a ogni avvio
        cerchi = []
        # Un cerchio grande dominante, decentrato
        cerchi.append((LARGHEZZA * 0.32, ALTEZZA * 0.45, 95, PALETTE[0]))
        for _ in range(22):
            x = rnd.uniform(-20, LARGHEZZA + 20)
            y = rnd.uniform(-20, ALTEZZA + 20)
            r = rnd.choice([6, 9, 12, 16, 22, 30, 42, 58])
            cerchi.append((x, y, r, rnd.choice(PALETTE)))
        # I più grandi sotto, i piccoli sopra
        for x, y, r, col in sorted(cerchi, key=lambda c: -c[2]):
            # stipple simula la semitrasparenza dei cerchi sovrapposti
            stip = "gray50" if r > 20 else ""
            self.canvas.create_oval(x - r, y - r, x + r, y + r,
                                    fill=col, outline="", stipple=stip)
            # alone chiaro sottile (effetto "aureola")
            if r >= 22:
                self.canvas.create_oval(x - r - 3, y - r - 3, x + r + 3, y + r + 3,
                                        outline=col, width=1, stipple="gray25")
        # Pannello centrale semitrasparente per la leggibilità dei campi
        self.canvas.create_rectangle(70, 22, LARGHEZZA - 70, ALTEZZA - 22,
                                     fill="#000000", outline="", stipple="gray75")

    # ---------- le due manopole laterali ----------
    def _disegna_manopole(self):
        r = RAGGIO_MANOPOLA
        cy = ALTEZZA // 2
        self.manopola_sx = self._manopola(32, cy, r, "pausa")
        self.manopola_dx = self._manopola(LARGHEZZA - 32, cy, r, "chiudi")

        # Etichette sotto le manopole
        self.canvas.create_text(32, cy + r + 12, text="PAUSA 30'", fill=COLORE_ETICHETTA,
                                font=self.f_label)
        self.canvas.create_text(LARGHEZZA - 32, cy + r + 12, text="CHIUDI", fill=COLORE_ETICHETTA,
                                font=self.f_label)

        # Click sulle manopole
        self.canvas.tag_bind("pausa", "<Button-1>", self._toggle_pausa)
        self.canvas.tag_bind("chiudi", "<Button-1>", lambda e: self.destroy())
        for tag in ("pausa", "chiudi"):
            self.canvas.tag_bind(tag, "<Enter>", lambda e: self.canvas.config(cursor="hand2"))
            self.canvas.tag_bind(tag, "<Leave>", lambda e: self.canvas.config(cursor=""))

    def _manopola(self, cx, cy, r, tag):
        """Disegna una manopola 'fisica' (ombra, corpo, bordo chiaro, tacca, led)."""
        c = self.canvas
        c.create_oval(cx - r + 2, cy - r + 4, cx + r + 2, cy + r + 4, fill="#000", outline="",
                      stipple="gray50", tags=tag)                                   # ombra
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#2a2b30", outline="#55565c",
                      width=2, tags=tag)                                            # corpo
        c.create_oval(cx - r + 6, cy - r + 6, cx + r - 6, cy + r - 6, fill="#1c1d21",
                      outline="#3a3b40", tags=tag)                                  # incavo
        # tacca di riferimento (come su una manopola vera)
        ang = math.radians(-60)
        c.create_line(cx + (r - 10) * math.cos(ang), cy + (r - 10) * math.sin(ang),
                      cx + (r - 4) * math.cos(ang), cy + (r - 4) * math.sin(ang),
                      fill="#d9d2c5", width=3, capstyle="round", tags=tag)
        # led centrale (per la manopola pausa cambia colore)
        led = c.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill=COLORE_LED_OFF, outline="",
                            tags=tag)
        return led

    def _aggiorna_led(self):
        self.canvas.itemconfig(self.manopola_sx,
                               fill=COLORE_LED_ON if self.pausa_minima_attiva else COLORE_LED_OFF)
        self.canvas.itemconfig(self.manopola_dx, fill=COLORE_ERRORE)

    def _toggle_pausa(self, _event=None):
        """Manopola sinistra: attiva/disattiva il vincolo della pausa minima."""
        self.pausa_minima_attiva = not self.pausa_minima_attiva
        self._aggiorna_led()
        self._calcola()
        return "break"  # evita che il click avvii anche il trascinamento

    # ---------- campi di input/output ----------
    def _crea_campi(self):
        etichette = ["ENTRATA", "USCITA PRANZO", "RIENTRO"]
        self.entries = []
        self.vars = []
        x0, passo = 110, 100   # posizione del primo campo e distanza tra i campi
        y_label, y_entry = 42, 72

        # Validazione: solo cifre, ':' o '.', massimo 5 caratteri
        vcmd = (self.register(lambda s: len(s) <= 5 and all(ch.isdigit() or ch in ":." for ch in s)), "%P")

        for i, testo in enumerate(etichette):
            x = x0 + i * passo
            self.canvas.create_text(x, y_label, text=testo, fill=COLORE_ETICHETTA, font=self.f_label)
            var = tk.StringVar()
            var.trace_add("write", lambda *a: self._calcola())
            e = tk.Entry(self, textvariable=var, width=5, justify="center",
                         font=self.f_input, bg="#1a1b1f", fg=COLORE_TESTO,
                         insertbackground=COLORE_TESTO, relief="flat", bd=0,
                         highlightthickness=1, highlightbackground="#3a3b40",
                         highlightcolor=PALETTE[1], validate="key", validatecommand=vcmd)
            self.canvas.create_window(x, y_entry, window=e, width=78, height=36)
            # Invio o Tab passano al campo successivo
            e.bind("<Return>", lambda ev, idx=i: self._focus_prossimo(idx))
            self.entries.append(e)
            self.vars.append(var)

        # Campo output (solo lettura), separato da una sottile linea
        x_out = x0 + 3 * passo + 25
        self.canvas.create_line(x_out - 60, 40, x_out - 60, 100, fill="#3a3b40")
        self.canvas.create_text(x_out, y_label, text="USCITA", fill=COLORE_ETICHETTA, font=self.f_label)
        self.out_var = tk.StringVar(value="--:--")
        out = tk.Entry(self, textvariable=self.out_var, width=6, justify="center",
                       font=self.f_output, bg="#1a1b1f", fg=COLORE_OUTPUT,
                       relief="flat", bd=0, highlightthickness=0,
                       state="readonly", readonlybackground="#1a1b1f", cursor="arrow")
        self.canvas.create_window(x_out, y_entry + 2, window=out, width=108, height=44)

        # Riga informativa in basso (ore mattina / pausa / pomeriggio o errore)
        self.info_id = self.canvas.create_text(LARGHEZZA // 2, ALTEZZA - 38, text="",
                                               fill=COLORE_ETICHETTA, font=self.f_info)
        self.entries[0].focus_set()

    def _focus_prossimo(self, idx):
        if idx + 1 < len(self.entries):
            self.entries[idx + 1].focus_set()
            self.entries[idx + 1].selection_range(0, "end")

    # ---------- calcolo ----------
    def _calcola(self, *_):
        valori = [parse_orario(v.get()) for v in self.vars]
        if any(v is None for v in valori):
            # Dati incompleti o non validi: nessun errore, solo placeholder
            self.out_var.set("--:--")
            self.canvas.itemconfig(self.info_id, text="", fill=COLORE_ETICHETTA)
            return

        pausa = PAUSA_MINIMA_MINUTI if self.pausa_minima_attiva else None
        uscita, info = calcola_uscita(*valori, MONTE_ORE_MINUTI, pausa)
        if uscita is None:
            self.out_var.set("--:--")
            self.canvas.itemconfig(self.info_id, text=info, fill=COLORE_ERRORE)
            return

        self.out_var.set(formatta_orario(uscita))
        pausa_reale = valori[2] - valori[1]
        nota = ""
        if pausa is not None and pausa_reale < pausa:
            nota = f"  (pausa reale {pausa_reale}' → conteggiata {pausa}')"
        testo = (f"mattina {formatta_orario(info['mattina'])}  ·  pausa {info['pausa']}'"
                 f"  ·  pomeriggio {formatta_orario(info['pomeriggio'])}  ·  "
                 f"totale {MONTE_ORE_MINUTI // 60}h{nota}")
        self.canvas.itemconfig(self.info_id, text=testo, fill=COLORE_ETICHETTA)

    # ---------- trascinamento della finestra ----------
    def _inizio_drag(self, event):
        self._drag_dx = event.x_root - self.winfo_x()
        self._drag_dy = event.y_root - self.winfo_y()
        self.focus_set()  # toglie il focus dai campi quando si clicca sullo sfondo

    def _drag(self, event):
        self.geometry(f"+{event.x_root - self._drag_dx}+{event.y_root - self._drag_dy}")


if __name__ == "__main__":
    OrarioWidget().mainloop()
