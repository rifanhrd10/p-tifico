import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from urllib.request import Request, urlopen


APP_DIR = (
    os.path.dirname(os.path.abspath(sys.executable))
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
DEFAULT_ENDPOINT = "http://127.0.0.1:5000/BreakerStatus.json"
POLL_SECONDS = 1.0

PALETTE = {
    "background": "#0b1220",
    "panel": "#111b2e",
    "panel_alt": "#162238",
    "border": "#283750",
    "text": "#e7edf7",
    "muted": "#93a4ba",
    "accent": "#37b4ff",
    "green": "#14d84a",
    "red": "#ff2020",
    "gray": "#808080",
}

TABLE_COLUMNS = (
    ("display_name", "Nama Breaker", 220, "w"),
    ("used_in", "Dipakai di", 215, "w"),
    ("device_addr", "RTU / IP", 120, "center"),
    ("bay_name", "Bay", 235, "w"),
    ("info_name", "Point YX", 155, "w"),
    ("asdu", "ASDU", 70, "center"),
    ("ioa", "IOA", 65, "center"),
    ("raw_yx", "Nilai YX", 75, "center"),
    ("reverse", "Reverse", 75, "center"),
    ("condition", "Hasil", 105, "center"),
    ("color_name", "Warna", 85, "center"),
    ("quality", "Kualitas", 145, "center"),
)

MATRIX = [
    {"raw_yx": 0, "reverse": 0, "effective_yx": 0, "condition": "Open/Off", "color_name": "Hijau"},
    {"raw_yx": 1, "reverse": 0, "effective_yx": 1, "condition": "Closed/On", "color_name": "Merah"},
    {"raw_yx": 0, "reverse": 1, "effective_yx": 1, "condition": "Closed/On", "color_name": "Merah"},
    {"raw_yx": 1, "reverse": 1, "effective_yx": 0, "condition": "Open/Off", "color_name": "Hijau"},
]


def _read_json(filename):
    path = os.path.join(APP_DIR, filename)
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _unknown_row(identifier, display_name, binding, used_in, binding_keys):
    ip = str(binding.get("Device_Addr", "")).strip()
    bay = str(binding.get("Bay_Name", "")).strip()
    physical = str(binding.get("Physical_Name", "")).strip()
    info_name = str(binding.get("Info_Name", binding.get("InfoName", ""))).strip()
    reverse_raw = str(binding.get("Reverse", "0") or "0").strip().lower()
    reverse = 1 if reverse_raw in {"-1", "1", "true", "yes", "on"} else 0
    return {
        "id": str(identifier),
        "display_name": str(display_name or bay or identifier),
        "used_in": sorted({str(item) for item in used_in if str(item).strip()}),
        "binding_keys": sorted({str(item) for item in binding_keys}),
        "device_addr": ip,
        "bay_name": bay,
        "physical_name": physical,
        "info_name": info_name,
        "info_index": str(binding.get("Info_Index", "")),
        "asdu": binding.get("ASDU", ""),
        "ioa": binding.get("IOA", ""),
        "set_str": binding.get("SetStr", ""),
        "reset_str": binding.get("ResetStr", ""),
        "source_kind": binding.get("Source_Kind", ""),
        "source": f"IEC-104 {ip} · {bay} · {info_name or physical}",
        "raw_yx": None,
        "reverse": reverse,
        "effective_yx": None,
        "condition": "Unknown",
        "color_name": "Abu-abu",
        "color_hex": PALETTE["gray"],
        "quality": "SCADA NOT CONNECTED",
        "rtu_online": False,
        "expected_rule": "Effective YX = Raw YX XOR Reverse",
    }


def load_fallback_payload():
    """Load address metadata even when the main SCADA process is unavailable."""
    bindings = _read_json("UIRealtimeBindings.json")
    grouped = {}
    for binding_key, item in bindings.get("statuses", {}).items():
        if not isinstance(item, dict) or item.get("Source_Kind") != "rectangle_status_csv":
            continue
        signature = (
            str(item.get("Device_Addr", "")).strip(),
            str(item.get("Bay_Name", "")).strip(),
            str(item.get("Info_Name", item.get("InfoName", ""))).strip(),
            str(item.get("Info_Index", "")).strip(),
            str(item.get("ASDU", "")).strip(),
            str(item.get("IOA", "")).strip(),
            str(item.get("Reverse", "0")).strip(),
        )
        group = grouped.setdefault(signature, {
            "binding": dict(item), "used_in": set(), "binding_keys": [],
        })
        group["used_in"].add(item.get("page", str(binding_key).split(":", 1)[0]))
        group["binding_keys"].append(binding_key)

    breakers = []
    ordered = sorted(grouped.values(), key=lambda group: (
        str(group["binding"].get("Bay_Name", "")),
        str(group["binding"].get("Device_Addr", "")),
        str(group["binding"].get("IOA", "")),
    ))
    for index, group in enumerate(ordered, 1):
        binding = group["binding"]
        breakers.append(_unknown_row(
            f"breaker-{index}",
            binding.get("Bay_Name", binding.get("element", f"Breaker {index}")),
            binding,
            group["used_in"],
            group["binding_keys"],
        ))

    monitor_tv = []
    config = _read_json("MonitorTVConfig.json")
    for monitor_id in ("G1", "G2"):
        rectangles = config.get(monitor_id, {}).get("rectangles", {})
        for rectangle_id, binding in sorted(rectangles.items()):
            if not isinstance(binding, dict) or binding.get("Source_Kind") != "rectangle_status_csv":
                continue
            monitor_tv.append(_unknown_row(
                f"{monitor_id}:{rectangle_id}",
                f"{monitor_id} · {binding.get('label', rectangle_id)}",
                binding,
                [f"Monitor TV {monitor_id}"],
                [f"{monitor_id}:{rectangle_id}"],
            ))

    return {
        "schema": "SCADA-BONT-BREAKER-STATUS-1",
        "generated_at": "-",
        "rule": "Effective YX = Raw YX XOR Reverse",
        "matrix": list(MATRIX),
        "breakers": breakers,
        "monitor_tv": monitor_tv,
    }


def fetch_payload(endpoint):
    request = Request(endpoint, headers={"Cache-Control": "no-cache"})
    with urlopen(request, timeout=1.5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("schema") != "SCADA-BONT-BREAKER-STATUS-1":
        raise ValueError("respons BreakerStatus.json tidak dikenali")
    return payload


class BreakerInspector:
    def __init__(self, root):
        self.root = root
        self.root.title("SCADA BONT · Breaker Inspector")
        self.root.geometry("1540x850")
        self.root.minsize(1080, 640)
        self.root.configure(bg=PALETTE["background"])

        self.endpoint = DEFAULT_ENDPOINT
        self.latest_payload = load_fallback_payload()
        self.payload_queue = queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.refresh_now = threading.Event()
        self.tables = {}
        self.row_lookup = {}

        self.endpoint_var = tk.StringVar(value=self.endpoint)
        self.search_var = tk.StringVar()
        self.connection_var = tk.StringVar(value="Menunggu SCADA lokal…")
        self.summary_var = tk.StringVar(value="-")
        self.detail_var = tk.StringVar(value="Pilih satu breaker untuk melihat alamat sumber lengkap.")

        self._configure_style()
        self._build_ui()
        self._render_payload(self.latest_payload, connected=False, error="SCADA belum terhubung")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        threading.Thread(target=self._poll_worker, name="breaker-inspector-poll", daemon=True).start()
        self.root.after(150, self._drain_payload_queue)

    def _configure_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TNotebook", background=PALETTE["background"], borderwidth=0)
        style.configure(
            "App.TNotebook.Tab", background=PALETTE["panel"], foreground=PALETTE["muted"],
            font=("Segoe UI", 11, "bold"), padding=(18, 10), borderwidth=0,
        )
        style.map(
            "App.TNotebook.Tab",
            background=[("selected", PALETTE["panel_alt"])],
            foreground=[("selected", PALETTE["text"])],
        )
        style.configure(
            "Breaker.Treeview", background=PALETTE["panel"], fieldbackground=PALETTE["panel"],
            foreground=PALETTE["text"], rowheight=30, borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.map(
            "Breaker.Treeview",
            background=[("selected", "#22577a")], foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Breaker.Treeview.Heading", background="#1d2b45", foreground="#dce8f8",
            relief="flat", font=("Segoe UI", 9, "bold"), padding=(5, 8),
        )
        style.map("Breaker.Treeview.Heading", background=[("active", "#263b60")])

    def _build_ui(self):
        header = tk.Frame(self.root, bg=PALETTE["background"], padx=22, pady=16)
        header.pack(fill="x")
        title_block = tk.Frame(header, bg=PALETTE["background"])
        title_block.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_block, text="SCADA BONT", bg=PALETTE["background"], fg=PALETTE["accent"],
            font=("Segoe UI", 12, "bold"), anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_block, text="BREAKER INSPECTOR", bg=PALETTE["background"], fg=PALETTE["text"],
            font=("Segoe UI", 25, "bold"), anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_block,
            text="Nilai YX live, alamat sumber IEC-104, Reverse, hasil kondisi, dan warna yang seharusnya.",
            bg=PALETTE["background"], fg=PALETTE["muted"], font=("Segoe UI", 10), anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        status_block = tk.Frame(header, bg=PALETTE["panel"], padx=14, pady=10,
                                highlightthickness=1, highlightbackground=PALETTE["border"])
        status_block.pack(side="right", padx=(16, 0))
        self.status_dot = tk.Label(status_block, text="●", bg=PALETTE["panel"],
                                   fg=PALETTE["gray"], font=("Segoe UI", 14, "bold"))
        self.status_dot.grid(row=0, column=0, rowspan=2, padx=(0, 8))
        tk.Label(status_block, textvariable=self.connection_var, bg=PALETTE["panel"],
                 fg=PALETTE["text"], font=("Segoe UI", 10, "bold")).grid(row=0, column=1, sticky="w")
        tk.Label(status_block, textvariable=self.summary_var, bg=PALETTE["panel"],
                 fg=PALETTE["muted"], font=("Consolas", 9)).grid(row=1, column=1, sticky="w")

        controls = tk.Frame(self.root, bg=PALETTE["panel"], padx=18, pady=10,
                            highlightthickness=1, highlightbackground=PALETTE["border"])
        controls.pack(fill="x", padx=22, pady=(0, 12))
        tk.Label(controls, text="SCADA API", bg=PALETTE["panel"], fg=PALETTE["muted"],
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        endpoint_entry = tk.Entry(
            controls, textvariable=self.endpoint_var, width=54, bg="#0d1728", fg=PALETTE["text"],
            insertbackground=PALETTE["text"], relief="flat", font=("Consolas", 10),
        )
        endpoint_entry.pack(side="left", padx=(10, 8), ipady=6)
        tk.Button(
            controls, text="Hubungkan", command=self.apply_endpoint, bg="#16638c", fg="white",
            activebackground="#1c7eaf", activeforeground="white", relief="flat",
            font=("Segoe UI", 9, "bold"), padx=15, pady=6, cursor="hand2",
        ).pack(side="left")
        tk.Label(controls, text="Cari", bg=PALETTE["panel"], fg=PALETTE["muted"],
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(28, 8))
        search_entry = tk.Entry(
            controls, textvariable=self.search_var, width=30, bg="#0d1728", fg=PALETTE["text"],
            insertbackground=PALETTE["text"], relief="flat", font=("Segoe UI", 10),
        )
        search_entry.pack(side="left", ipady=6)
        search_entry.bind("<KeyRelease>", lambda _event: self._render_tables())

        notebook = ttk.Notebook(self.root, style="App.TNotebook")
        notebook.pack(fill="both", expand=True, padx=22)
        breaker_tab = tk.Frame(notebook, bg=PALETTE["background"])
        monitor_tab = tk.Frame(notebook, bg=PALETTE["background"])
        matrix_tab = tk.Frame(notebook, bg=PALETTE["background"])
        notebook.add(breaker_tab, text="Breaker SCADA")
        notebook.add(monitor_tab, text="Monitor TV")
        notebook.add(matrix_tab, text="Logika YX × Reverse")
        self.tables["breakers"] = self._build_table(breaker_tab, "breakers")
        self.tables["monitor_tv"] = self._build_table(monitor_tab, "monitor_tv")
        self._build_matrix(matrix_tab)

        detail = tk.Label(
            self.root, textvariable=self.detail_var, justify="left", anchor="nw",
            bg=PALETTE["panel"], fg=PALETTE["text"], font=("Consolas", 9),
            padx=16, pady=10, highlightthickness=1, highlightbackground=PALETTE["border"],
        )
        detail.pack(fill="x", padx=22, pady=(12, 8))
        tk.Label(
            self.root,
            text="Read-only: aplikasi ini tidak membuka koneksi IEC-104 baru. Nilai live dibaca dari SCADA BONT lokal.",
            bg=PALETTE["background"], fg=PALETTE["muted"], font=("Segoe UI", 9),
        ).pack(anchor="w", padx=24, pady=(0, 12))

    def _build_table(self, parent, key):
        container = tk.Frame(parent, bg=PALETTE["background"])
        container.pack(fill="both", expand=True)
        tree = ttk.Treeview(
            container, columns=[column[0] for column in TABLE_COLUMNS], show="headings",
            style="Breaker.Treeview", selectmode="browse",
        )
        for field, heading, width, anchor in TABLE_COLUMNS:
            tree.heading(field, text=heading)
            tree.column(field, width=width, minwidth=55, anchor=anchor, stretch=field in {"display_name", "used_in", "bay_name"})
        vertical = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        tree.tag_configure("closed", background="#3a141b", foreground="#ffc3c3")
        tree.tag_configure("open", background="#12351f", foreground="#c3ffd4")
        tree.tag_configure("unknown", background="#242b37", foreground="#c3cad4")
        tree.bind("<<TreeviewSelect>>", lambda _event, table_key=key: self._show_selected(table_key))
        return tree

    def _build_matrix(self, parent):
        card = tk.Frame(parent, bg=PALETTE["panel"], padx=28, pady=24,
                        highlightthickness=1, highlightbackground=PALETTE["border"])
        card.pack(fill="both", expand=True)
        tk.Label(card, text="Aturan kondisi breaker", bg=PALETTE["panel"], fg=PALETTE["text"],
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(card, text="Effective YX = Nilai YX XOR Reverse", bg=PALETTE["panel"],
                 fg=PALETTE["accent"], font=("Consolas", 14, "bold")).pack(anchor="w", pady=(5, 18))
        columns = ("raw_yx", "reverse", "effective_yx", "condition", "color_name")
        tree = ttk.Treeview(card, columns=columns, show="headings", height=4, style="Breaker.Treeview")
        headings = {
            "raw_yx": "Nilai YX", "reverse": "Reverse", "effective_yx": "YX Efektif",
            "condition": "Hasil", "color_name": "Warna",
        }
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=160, anchor="center", stretch=True)
        tree.tag_configure("closed", background="#3a141b", foreground="#ffc3c3")
        tree.tag_configure("open", background="#12351f", foreground="#c3ffd4")
        for index, item in enumerate(MATRIX):
            tag = "closed" if item["effective_yx"] == 1 else "open"
            tree.insert("", "end", iid=f"matrix-{index}", values=tuple(item[column] for column in columns), tags=(tag,))
        tree.pack(fill="x")
        note = (
            "Nilai YX berasal dari point StatusSetting yang ditunjukkan pada kolom Point YX, ASDU, dan IOA.\n"
            "Jika RTU offline atau point belum pernah diterima, hasil adalah Unknown dan berwarna abu-abu.\n"
            "Reverse diterapkan sesudah nilai YX diterima; nilai cache tidak digunakan saat RTU offline."
        )
        tk.Label(card, text=note, justify="left", bg=PALETTE["panel"], fg=PALETTE["muted"],
                 font=("Segoe UI", 11), pady=20).pack(anchor="w")

    def apply_endpoint(self):
        endpoint = self.endpoint_var.get().strip()
        if endpoint:
            self.endpoint = endpoint
            self.connection_var.set("Menghubungkan…")
            self.status_dot.configure(fg=PALETTE["gray"])
            self.refresh_now.set()

    def _poll_worker(self):
        fallback = self.latest_payload
        while not self.stop_event.is_set():
            started = time.monotonic()
            try:
                payload = fetch_payload(self.endpoint)
                message = (payload, True, "")
            except Exception as exc:
                try:
                    fallback = load_fallback_payload()
                except Exception:
                    pass
                message = (fallback, False, str(exc))
            try:
                while True:
                    self.payload_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.payload_queue.put_nowait(message)
            except queue.Full:
                pass
            delay = max(0.1, POLL_SECONDS - (time.monotonic() - started))
            self.refresh_now.wait(delay)
            self.refresh_now.clear()

    def _drain_payload_queue(self):
        latest = None
        try:
            while True:
                latest = self.payload_queue.get_nowait()
        except queue.Empty:
            pass
        if latest is not None:
            payload, connected, error = latest
            self._render_payload(payload, connected, error)
        if not self.stop_event.is_set():
            self.root.after(150, self._drain_payload_queue)

    def _render_payload(self, payload, connected, error):
        self.latest_payload = payload
        if connected:
            self.connection_var.set("SCADA TERHUBUNG")
            self.status_dot.configure(fg=PALETTE["green"])
            total = len(payload.get("breakers", [])) + len(payload.get("monitor_tv", []))
            good = sum(
                row.get("quality") == "GOOD"
                for section in ("breakers", "monitor_tv")
                for row in payload.get(section, [])
            )
            self.summary_var.set(f"{good}/{total} point GOOD · {payload.get('generated_at', '-')}")
        else:
            self.connection_var.set("SCADA TIDAK TERHUBUNG")
            self.status_dot.configure(fg=PALETTE["red"])
            self.summary_var.set((error or "endpoint tidak tersedia")[:72])
        self._render_tables()

    def _render_tables(self):
        query_text = self.search_var.get().strip().lower()
        self.row_lookup.clear()
        for section, tree in self.tables.items():
            selected = tree.selection()
            selected_id = selected[0] if selected else None
            tree.delete(*tree.get_children())
            for index, row in enumerate(self.latest_payload.get(section, [])):
                searchable = " ".join(str(row.get(field, "")) for field, *_rest in TABLE_COLUMNS).lower()
                if query_text and query_text not in searchable:
                    continue
                item_id = f"{section}:{row.get('id', index)}"
                values = []
                for field, *_rest in TABLE_COLUMNS:
                    value = row.get(field, "")
                    if field == "used_in":
                        value = ", ".join(value or [])
                    elif field in {"raw_yx", "effective_yx"} and value is None:
                        value = "?"
                    values.append(value)
                effective = row.get("effective_yx")
                tag = "unknown" if effective is None else ("closed" if effective == 1 else "open")
                tree.insert("", "end", iid=item_id, values=values, tags=(tag,))
                self.row_lookup[item_id] = row
            if selected_id and tree.exists(selected_id):
                tree.selection_set(selected_id)

    def _show_selected(self, table_key):
        tree = self.tables[table_key]
        selection = tree.selection()
        if not selection:
            return
        row = self.row_lookup.get(selection[0])
        if not row:
            return
        raw = "?" if row.get("raw_yx") is None else row.get("raw_yx")
        effective = "?" if row.get("effective_yx") is None else row.get("effective_yx")
        details = (
            f"BREAKER      : {row.get('display_name', '')}\n"
            f"DIPAKAI DI   : {', '.join(row.get('used_in', []))}\n"
            f"SUMBER       : {row.get('source', '')}\n"
            f"POINT        : Physical={row.get('physical_name', '')} | Info={row.get('info_name', '')} | Index={row.get('info_index', '')}\n"
            f"ALAMAT       : ASDU={row.get('asdu', '')} | IOA={row.get('ioa', '')} | Set/Reset={row.get('set_str', '')}/{row.get('reset_str', '')}\n"
            f"PERHITUNGAN  : YX {raw} XOR Reverse {row.get('reverse', 0)} = {effective}\n"
            f"HASIL        : {row.get('condition', '')} | {row.get('color_name', '')} | Quality={row.get('quality', '')}"
        )
        self.detail_var.set(details)

    def close(self):
        self.stop_event.set()
        self.refresh_now.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    BreakerInspector(root)
    root.mainloop()


if __name__ == "__main__":
    main()
