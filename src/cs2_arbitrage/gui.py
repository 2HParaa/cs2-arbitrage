import io
import queue
import threading
import tkinter as tk

import customtkinter as ctk
from PIL import Image

from cs2_arbitrage.catalog import CatalogError, ItemCatalog, fetch_icon

ICON_DISPLAY_SIZE = 64
ICON_HEADER_SIZE = 128
ICON_POLL_INTERVAL_MS = 50

# Charte graphique "Obsidian Gold" : fond ardoise très sombre, accent ambre
# (rappelle l'or/les objets rares plutôt qu'un thème "gamer" saturé), une
# seule teinte d'accent réutilisée partout pour rester cohérent plutôt que
# de multiplier les couleurs. "danger" reste dispo pour d'éventuels futurs
# messages d'erreur inline.
PALETTE = {
    "bg": "#12131a",
    "surface": "#1b1d29",
    "surface_alt": "#242736",
    "surface_hover": "#2c2f42",
    "border": "#333650",
    "text": "#eceef5",
    "text_muted": "#9497ac",
    "accent": "#f2a93b",
    "accent_hover": "#d9922a",
    "accent_text": "#1a1207",
    "danger": "#f2545b",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# (nom interne PriceSource.name, libellé affiché), toutes cochées par défaut.
PLATFORMS = [
    ("steam", "Steam"),
    ("skinport", "Skinport"),
    ("csmoney", "CS.Money"),
    ("waxpeer", "Waxpeer"),
    ("csdeals", "CS.Deals"),
]


class ItemBrowserApp:
    """Navigation Type -> Arme -> Skin -> Variante avec cases à cocher.
    Une seule fenêtre dont le contenu (body_frame) est reconstruit à chaque
    navigation, plutôt qu'un empilement de Frame par niveau."""

    def __init__(self, root: ctk.CTk, catalog: ItemCatalog):
        self.root = root
        self.catalog = catalog
        self.path: list[str] = []
        self.selected_items: set[str] = set()
        # market_hash_name -> PIL.Image brute (pas encore mise à la taille
        # d'affichage) : permet de reconstruire un CTkImage à la taille
        # voulue (liste vs en-tête agrandi) sans redemander l'image.
        self.icon_cache: dict[str, Image.Image] = {}
        self.placeholder_image = Image.new("RGBA", (8, 8), PALETTE["surface_alt"])
        self.render_generation = 0
        self.current_skin_hash_name = None
        self.result_items: list[str] = []
        self.result_platforms: list[str] = []

        self.root.title("CS2 Arbitrage — Choisir des items")
        self.root.geometry("720x700")
        self.root.minsize(600, 560)
        self.root.configure(fg_color=PALETTE["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        top_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        top_frame.pack(fill="x", padx=12, pady=(12, 4))
        self.back_button = ctk.CTkButton(
            top_frame,
            text="◀ Retour",
            width=90,
            state="disabled",
            fg_color=PALETTE["surface"],
            hover_color=PALETTE["surface_hover"],
            text_color=PALETTE["text"],
            command=self._go_back,
        )
        self.back_button.pack(side="left")
        self.breadcrumb_label = ctk.CTkLabel(
            top_frame,
            text="Type d'item",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=PALETTE["text"],
        )
        self.breadcrumb_label.pack(side="left", padx=12)

        self.body_frame = ctk.CTkScrollableFrame(
            self.root, fg_color=PALETTE["bg"], scrollbar_button_color=PALETTE["surface_hover"]
        )
        self.body_frame.pack(fill="both", expand=True, padx=12, pady=4)

        self._build_bottom_panel()
        self._render()

    # -- Construction du panneau bas -------------------------------------

    def _build_bottom_panel(self) -> None:
        frame = ctk.CTkFrame(self.root, fg_color=PALETTE["surface"], corner_radius=10)
        frame.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(
            frame,
            text="Items sélectionnés",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=PALETTE["text_muted"],
        ).pack(anchor="w", padx=12, pady=(10, 2))

        self.selected_frame = ctk.CTkScrollableFrame(
            frame,
            height=110,
            fg_color=PALETTE["surface_alt"],
            scrollbar_button_color=PALETTE["surface_hover"],
        )
        self.selected_frame.pack(fill="x", padx=12, pady=(0, 8))

        platforms_frame = ctk.CTkFrame(frame, fg_color="transparent")
        platforms_frame.pack(fill="x", padx=12, pady=(0, 4))
        ctk.CTkLabel(
            platforms_frame,
            text="Plateformes à sonder :",
            text_color=PALETTE["text_muted"],
        ).pack(side="left")
        self.platform_vars: dict[str, tk.BooleanVar] = {}
        for name, label in PLATFORMS:
            variable = tk.BooleanVar(value=True)
            self.platform_vars[name] = variable
            ctk.CTkCheckBox(
                platforms_frame,
                text=label,
                variable=variable,
                fg_color=PALETTE["accent"],
                hover_color=PALETTE["accent_hover"],
                checkmark_color=PALETTE["accent_text"],
                text_color=PALETTE["text"],
                command=self._update_selected_panel,
            ).pack(side="left", padx=6)

        self.launch_button = ctk.CTkButton(
            frame,
            text="Lancer la comparaison (0 items)",
            height=40,
            corner_radius=10,
            state="disabled",
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            text_color=PALETTE["accent_text"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._launch,
        )
        self.launch_button.pack(fill="x", padx=12, pady=(4, 12))

        self._update_selected_panel()

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
        self.breadcrumb_label.configure(text=" > ".join(self.path) or "Type d'item")
        self.back_button.configure(state="normal" if self.path else "disabled")

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
            ctk.CTkLabel(
                self.body_frame, text=str(error), text_color=PALETTE["danger"], wraplength=600
            ).pack(pady=8)
            ctk.CTkButton(
                self.body_frame,
                text="Réessayer",
                fg_color=PALETTE["surface"],
                hover_color=PALETTE["surface_hover"],
                command=self._render,
            ).pack(pady=8)

    # -- Rendu par niveau ----------------------------------------------

    def _render_choice_list(self, names: list[str], on_choose) -> None:
        if not names:
            self._render_empty()
            return
        for name in names:
            ctk.CTkButton(
                self.body_frame,
                text=name,
                anchor="w",
                height=36,
                corner_radius=8,
                fg_color=PALETTE["surface"],
                hover_color=PALETTE["surface_hover"],
                text_color=PALETTE["text"],
                command=lambda n=name: on_choose(n),
            ).pack(fill="x", pady=3)

    def _render_empty(self) -> None:
        ctk.CTkLabel(
            self.body_frame, text="Aucun résultat.", text_color=PALETTE["text_muted"]
        ).pack(pady=8)

    def _render_skin_list(self) -> None:
        item_type, weapon = self.path
        skins = self.catalog.fetch_skins(item_type, weapon)
        if not skins:
            self._render_empty()
            return

        generation = self.render_generation
        hash_names = []
        icon_labels = []
        for entry in skins:
            row = ctk.CTkFrame(self.body_frame, fg_color="transparent")
            row.pack(fill="x", pady=3)
            icon_label = ctk.CTkLabel(
                row, text="", image=self._ctk_image(self.placeholder_image, ICON_DISPLAY_SIZE)
            )
            icon_label.pack(side="left", padx=(0, 8))
            ctk.CTkButton(
                row,
                text=entry.label,
                anchor="w",
                height=ICON_DISPLAY_SIZE,
                corner_radius=8,
                fg_color=PALETTE["surface"],
                hover_color=PALETTE["surface_hover"],
                text_color=PALETTE["text"],
                command=lambda e=entry: self._enter_skin(e),
            ).pack(side="left", fill="x", expand=True)
            hash_names.append(entry.representative_hash_name)
            icon_labels.append(icon_label)

        self._load_icons_async(hash_names, icon_labels, generation)

    def _render_variant_list(self) -> None:
        item_type, weapon, skin = self.path
        variants = self.catalog.fetch_variants(item_type, weapon, skin)

        image = self.icon_cache.get(self.current_skin_hash_name, self.placeholder_image)
        header = ctk.CTkLabel(
            self.body_frame, text="", image=self._ctk_image(image, ICON_HEADER_SIZE)
        )
        header.pack(pady=8)

        if not variants:
            self._render_empty()
            return

        for hash_name in variants:
            variable = tk.BooleanVar(value=hash_name in self.selected_items)
            ctk.CTkCheckBox(
                self.body_frame,
                text=hash_name,
                variable=variable,
                fg_color=PALETTE["accent"],
                hover_color=PALETTE["accent_hover"],
                checkmark_color=PALETTE["accent_text"],
                text_color=PALETTE["text"],
                command=lambda h=hash_name, v=variable: self._toggle_item(h, v),
            ).pack(fill="x", pady=2)

    # -- Chargement des images en arrière-plan --------------------------

    def _ctk_image(self, image: Image.Image, size: int) -> ctk.CTkImage:
        return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))

    def _load_icons_async(
        self, hash_names: list[str], labels: list[ctk.CTkLabel], generation: int
    ) -> None:
        # Le thread ne touche à aucun widget Tk (pas thread-safe) : il ne
        # fait que résoudre/télécharger les octets (via catalog.fetch_icon,
        # qui essaie Waxpeer sans throttle avant Steam, cache disque inclus)
        # et les déposer dans la queue ; la création des CTkImage et
        # l'affichage se font côté thread principal via _poll_icon_queue.
        work_queue: queue.Queue = queue.Queue()

        def worker():
            for index, hash_name in enumerate(hash_names):
                image = None
                if hash_name not in self.icon_cache:
                    try:
                        image_bytes = fetch_icon(hash_name)
                        image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
                    except CatalogError:
                        image = None
                work_queue.put((index, hash_name, image))
            work_queue.put(None)

        threading.Thread(target=worker, daemon=True).start()
        self._poll_icon_queue(work_queue, labels, generation)

    def _poll_icon_queue(
        self, work_queue: "queue.Queue", labels: list[ctk.CTkLabel], generation: int
    ) -> None:
        if generation != self.render_generation:
            return  # l'utilisateur a navigué ailleurs, ces résultats ne servent plus

        try:
            while True:
                item = work_queue.get_nowait()
                if item is None:
                    return
                index, hash_name, image = item
                if image is not None:
                    self.icon_cache[hash_name] = image
                cached = self.icon_cache.get(hash_name)
                if cached is not None and index < len(labels):
                    labels[index].configure(image=self._ctk_image(cached, ICON_DISPLAY_SIZE))
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

    def _remove_item(self, hash_name: str) -> None:
        self.selected_items.discard(hash_name)
        self._update_selected_panel()
        self._render()

    def _update_selected_panel(self) -> None:
        for widget in self.selected_frame.winfo_children():
            widget.destroy()

        for hash_name in sorted(self.selected_items):
            row = ctk.CTkFrame(self.selected_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=hash_name, text_color=PALETTE["text"], anchor="w").pack(
                side="left", fill="x", expand=True
            )
            ctk.CTkButton(
                row,
                text="✕",
                width=24,
                height=24,
                corner_radius=6,
                fg_color="transparent",
                hover_color=PALETTE["danger"],
                text_color=PALETTE["text_muted"],
                command=lambda h=hash_name: self._remove_item(h),
            ).pack(side="right")

        count = len(self.selected_items)
        platform_count = sum(1 for v in self.platform_vars.values() if v.get())
        self.launch_button.configure(
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
    root = ctk.CTk()
    app = ItemBrowserApp(root, ItemCatalog())
    root.mainloop()
    return app.result_items, app.result_platforms
