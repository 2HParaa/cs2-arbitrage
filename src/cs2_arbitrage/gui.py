import queue
import threading
import tkinter as tk
from tkinter import messagebox

from cs2_arbitrage.catalog import CatalogError, ItemCatalog, fetch_icon

ICON_DISPLAY_SIZE = 64
ICON_POLL_INTERVAL_MS = 50

# (nom interne PriceSource.name, libellé affiché), toutes cochées par défaut.
PLATFORMS = [
    ("steam", "Steam"),
    ("skinport", "Skinport"),
    ("csmoney", "CS.Money"),
]


class ItemBrowserApp:
    """Navigation Type -> Arme -> Skin -> Variante avec cases à cocher.
    Une seule fenêtre dont le contenu (body_frame) est reconstruit à chaque
    navigation, plutôt qu'un empilement de Frame par niveau."""

    def __init__(self, root: tk.Tk, catalog: ItemCatalog):
        self.root = root
        self.catalog = catalog
        self.path: list[str] = []
        self.selected_items: set[str] = set()
        self.icon_cache: dict[str, tk.PhotoImage] = {}
        self.placeholder = self._make_placeholder()
        self.render_generation = 0
        self.current_skin_hash_name = None
        self.result_items: list[str] = []
        self.result_platforms: list[str] = []

        self.root.title("CS2 Arbitrage — Choisir des items")
        self.root.geometry("640x600")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        top_frame = tk.Frame(self.root)
        top_frame.pack(fill="x", padx=8, pady=8)
        self.back_button = tk.Button(
            top_frame, text="◀ Retour", command=self._go_back, state="disabled"
        )
        self.back_button.pack(side="left")
        self.breadcrumb_label = tk.Label(top_frame, text="Type d'item", font=("", 10, "bold"))
        self.breadcrumb_label.pack(side="left", padx=8)

        self.body_frame = self._build_scrollable_body(self.root)
        self._build_bottom_panel()

        self._render()

    # -- Construction de la fenêtre ---------------------------------

    def _make_placeholder(self) -> tk.PhotoImage:
        image = tk.PhotoImage(width=ICON_DISPLAY_SIZE, height=ICON_DISPLAY_SIZE)
        image.put("gray75", to=(0, 0, ICON_DISPLAY_SIZE, ICON_DISPLAY_SIZE))
        return image

    def _build_scrollable_body(self, parent: tk.Widget) -> tk.Frame:
        container = tk.Frame(parent)
        container.pack(fill="both", expand=True, padx=8)

        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return inner

    def _build_bottom_panel(self) -> None:
        frame = tk.Frame(self.root)
        frame.pack(fill="x", padx=8, pady=8)

        tk.Label(frame, text="Items sélectionnés :").pack(anchor="w")
        self.selected_listbox = tk.Listbox(frame, height=5)
        self.selected_listbox.pack(fill="x")
        tk.Button(frame, text="Retirer la sélection", command=self._remove_selected).pack(
            anchor="e", pady=2
        )

        platforms_frame = tk.Frame(frame)
        platforms_frame.pack(fill="x", pady=(4, 0))
        tk.Label(platforms_frame, text="Plateformes à sonder :").pack(side="left")
        self.platform_vars: dict[str, tk.BooleanVar] = {}
        for name, label in PLATFORMS:
            variable = tk.BooleanVar(value=True)
            self.platform_vars[name] = variable
            tk.Checkbutton(
                platforms_frame, text=label, variable=variable, command=self._update_selected_panel
            ).pack(side="left", padx=4)

        self.launch_button = tk.Button(
            frame,
            text="Lancer la comparaison (0 items)",
            state="disabled",
            command=self._launch,
        )
        self.launch_button.pack(fill="x", pady=4)

    # -- Navigation ---------------------------------------------------

    def _enter(self, name: str) -> None:
        self.path.append(name)
        self._render()

    def _enter_skin(self, entry) -> None:
        self.current_skin_hash_name = entry.representative_hash_name
        self.path.append(entry.label)
        self._render()

    def _go_back(self) -> None:
        self.path.pop()
        self._render()

    def _update_breadcrumb(self) -> None:
        self.breadcrumb_label.config(text=" > ".join(self.path) or "Type d'item")
        self.back_button.config(state="normal" if self.path else "disabled")

    def _render(self) -> None:
        self.render_generation += 1
        for widget in self.body_frame.winfo_children():
            widget.destroy()
        self._update_breadcrumb()

        try:
            level = len(self.path)
            if level == 0:
                self._render_choice_list(self.catalog.fetch_types(), self._enter)
            elif level == 1:
                self._render_choice_list(self.catalog.fetch_weapons(self.path[0]), self._enter)
            elif level == 2:
                self._render_skin_list()
            else:
                self._render_variant_list()
        except CatalogError as error:
            messagebox.showerror("Erreur", str(error))
            tk.Button(self.body_frame, text="Réessayer", command=self._render).pack(pady=8)

    # -- Rendu par niveau ----------------------------------------------

    def _render_choice_list(self, names: list[str], on_choose) -> None:
        if not names:
            tk.Label(self.body_frame, text="Aucun résultat.").pack(pady=8)
            return
        for name in names:
            tk.Button(
                self.body_frame, text=name, anchor="w", command=lambda n=name: on_choose(n)
            ).pack(fill="x", padx=4, pady=2)

    def _render_skin_list(self) -> None:
        item_type, weapon = self.path
        skins = self.catalog.fetch_skins(item_type, weapon)
        if not skins:
            tk.Label(self.body_frame, text="Aucun résultat.").pack(pady=8)
            return

        generation = self.render_generation
        hash_names = []
        icon_labels = []
        for entry in skins:
            row = tk.Frame(self.body_frame)
            row.pack(fill="x", padx=4, pady=2)
            icon_label = tk.Label(row, image=self.placeholder)
            icon_label.pack(side="left", padx=(0, 8))
            tk.Button(
                row, text=entry.label, anchor="w", command=lambda e=entry: self._enter_skin(e)
            ).pack(side="left", fill="x", expand=True)
            hash_names.append(entry.representative_hash_name)
            icon_labels.append(icon_label)

        self._load_icons_async(hash_names, icon_labels, generation)

    def _render_variant_list(self) -> None:
        item_type, weapon, skin = self.path
        variants = self.catalog.fetch_variants(item_type, weapon, skin)

        photo = self.icon_cache.get(self.current_skin_hash_name, self.placeholder)
        header = tk.Label(self.body_frame, image=photo)
        header.image = photo
        header.pack(pady=8)

        if not variants:
            tk.Label(self.body_frame, text="Aucun résultat.").pack(pady=8)
            return

        for hash_name in variants:
            variable = tk.BooleanVar(value=hash_name in self.selected_items)
            tk.Checkbutton(
                self.body_frame,
                text=hash_name,
                variable=variable,
                anchor="w",
                command=lambda h=hash_name, v=variable: self._toggle_item(h, v),
            ).pack(fill="x", padx=4, pady=1)

    # -- Chargement des images en arrière-plan --------------------------

    def _load_icons_async(
        self, hash_names: list[str], labels: list[tk.Label], generation: int
    ) -> None:
        # Le thread ne touche à aucun widget Tk (pas thread-safe) : il ne
        # fait que résoudre/télécharger les octets (via catalog.fetch_icon,
        # cache disque inclus) et les déposer dans la queue ; la création
        # des PhotoImage et l'affichage se font côté thread principal via
        # _poll_icon_queue.
        work_queue: queue.Queue = queue.Queue()

        def worker():
            for index, hash_name in enumerate(hash_names):
                image_bytes = None
                if hash_name not in self.icon_cache:
                    try:
                        image_bytes = fetch_icon(hash_name)
                    except CatalogError:
                        image_bytes = None
                work_queue.put((index, hash_name, image_bytes))
            work_queue.put(None)

        threading.Thread(target=worker, daemon=True).start()
        self._poll_icon_queue(work_queue, labels, generation)

    def _poll_icon_queue(
        self, work_queue: "queue.Queue", labels: list[tk.Label], generation: int
    ) -> None:
        if generation != self.render_generation:
            return  # l'utilisateur a navigué ailleurs, ces résultats ne servent plus

        try:
            while True:
                item = work_queue.get_nowait()
                if item is None:
                    return
                index, hash_name, image_bytes = item
                if image_bytes is not None:
                    self.icon_cache[hash_name] = tk.PhotoImage(data=image_bytes)
                photo = self.icon_cache.get(hash_name)
                if photo is not None and index < len(labels):
                    labels[index].config(image=photo)
                    labels[index].image = photo
        except queue.Empty:
            pass

        self.root.after(
            ICON_POLL_INTERVAL_MS, self._poll_icon_queue, work_queue, labels, generation
        )

    # -- Sélection ------------------------------------------------------

    def _toggle_item(self, hash_name: str, variable: tk.BooleanVar) -> None:
        if variable.get():
            self.selected_items.add(hash_name)
        else:
            self.selected_items.discard(hash_name)
        self._update_selected_panel()

    def _remove_selected(self) -> None:
        selection = self.selected_listbox.curselection()
        if not selection:
            return
        hash_name = self.selected_listbox.get(selection[0])
        self.selected_items.discard(hash_name)
        self._update_selected_panel()
        self._render()

    def _update_selected_panel(self) -> None:
        self.selected_listbox.delete(0, tk.END)
        for hash_name in sorted(self.selected_items):
            self.selected_listbox.insert(tk.END, hash_name)
        count = len(self.selected_items)
        platform_count = sum(1 for v in self.platform_vars.values() if v.get())
        self.launch_button.config(
            text=f"Lancer la comparaison ({count} items)",
            state="normal" if count and platform_count else "disabled",
        )

    def _launch(self) -> None:
        self.result_items = sorted(self.selected_items)
        self.result_platforms = [name for name, var in self.platform_vars.items() if var.get()]
        self.root.destroy()

    def _on_close(self) -> None:
        self.result_items = []
        self.result_platforms = []
        self.root.destroy()


def run_item_browser() -> tuple[list[str], list[str]]:
    root = tk.Tk()
    app = ItemBrowserApp(root, ItemCatalog())
    root.mainloop()
    return app.result_items, app.result_platforms
