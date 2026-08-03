import io
import queue
import threading
import tkinter as tk
from collections import defaultdict
from decimal import Decimal

import customtkinter as ctk
from PIL import Image

from cs2_arbitrage.catalog import CatalogError, ItemCatalog, fetch_icon
from cs2_arbitrage.compare import Opportunity, profit_percent

STEAM_WALLET_WARNING = "Steam Wallet uniquement, non retirable en cash"

ICON_DISPLAY_SIZE = 96
ICON_HEADER_SIZE = 192
ICON_POLL_INTERVAL_MS = 50
MAX_DISPLAYED_ITEMS = 150

# Scan "tout le catalogue sous $X" : limité à Skinport/Waxpeer/CS.Deals
# (cf. scanner.py), Skinport servant de référence pour le seuil. Plage de
# la molette pensée pour de la chasse aux bonnes affaires, pas pour cibler
# des items chers.
SCAN_MIN_PRICE = 1
SCAN_MAX_PRICE = 100
SCAN_DEFAULT_PRICE = 10

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
    "profit": "#4ade80",
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
        self.result_scan_max_price: Decimal | None = None

        self.root.title("CS2 Arbitrage — Choisir des items")
        self.root.geometry("720x800")
        self.root.minsize(600, 720)
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

        self._build_scan_section(frame)

        self._update_selected_panel()

    def _build_scan_section(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkFrame(parent, fg_color=PALETTE["border"], height=1).pack(
            fill="x", padx=12, pady=(0, 10)
        )
        ctk.CTkLabel(
            parent,
            text="Ou scanner tout le catalogue (Skinport/Waxpeer/CS.Deals) sous un prix :",
            text_color=PALETTE["text_muted"],
        ).pack(anchor="w", padx=12)

        slider_row = ctk.CTkFrame(parent, fg_color="transparent")
        slider_row.pack(fill="x", padx=12, pady=(4, 8))

        self.scan_price_label = ctk.CTkLabel(
            slider_row,
            text=f"{SCAN_DEFAULT_PRICE:.2f} USD",
            width=90,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PALETTE["accent"],
        )
        self.scan_price_label.pack(side="right")

        self.scan_slider = ctk.CTkSlider(
            slider_row,
            from_=SCAN_MIN_PRICE,
            to=SCAN_MAX_PRICE,
            number_of_steps=SCAN_MAX_PRICE - SCAN_MIN_PRICE,
            fg_color=PALETTE["surface_alt"],
            progress_color=PALETTE["accent"],
            button_color=PALETTE["accent"],
            button_hover_color=PALETTE["accent_hover"],
            command=self._on_scan_slider_change,
        )
        self.scan_slider.set(SCAN_DEFAULT_PRICE)
        self.scan_slider.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(
            parent,
            text="Scanner le catalogue",
            height=40,
            corner_radius=10,
            fg_color=PALETTE["surface_hover"],
            hover_color=PALETTE["accent_hover"],
            text_color=PALETTE["text"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._launch_scan,
        ).pack(fill="x", padx=12, pady=(0, 12))

    def _on_scan_slider_change(self, value: float) -> None:
        self.scan_price_label.configure(text=f"{value:.2f} USD")

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

    def _launch_scan(self) -> None:
        self.result_scan_max_price = Decimal(str(round(self.scan_slider.get(), 2)))
        self.root.destroy()

    def _on_close(self) -> None:
        self.result_items = []
        self.result_platforms = []
        self.result_scan_max_price = None
        self.root.destroy()


def run_item_browser() -> tuple[list[str], list[str], Decimal | None]:
    root = ctk.CTk()
    app = ItemBrowserApp(root, ItemCatalog())
    root.mainloop()
    return app.result_items, app.result_platforms, app.result_scan_max_price


class ReportApp:
    """Fenêtre de résultats : une carte par item, triée par meilleure
    opportunité relative (%) décroissante — plus parlant que le montant
    absolu pour repérer les affaires intéressantes sur des items de prix
    très différents (cf. compare.profit_percent) — les items sans
    opportunité rentable relégués en bas. Affichage plafonné à
    MAX_DISPLAYED_ITEMS items (utile pour le scan de catalogue entier, qui
    peut trouver bien plus d'opportunités qu'une sélection manuelle)."""

    def __init__(self, root: ctk.CTk, opportunities: list[Opportunity]):
        self.root = root
        self.root.title("CS2 Arbitrage — Résultats")
        self.root.geometry("720x700")
        self.root.minsize(600, 560)
        self.root.configure(fg_color=PALETTE["bg"])

        by_item = defaultdict(list)
        for opportunity in opportunities:
            by_item[opportunity.item_name].append(opportunity)

        sorted_items = self._sorted_by_best_profit_percent(by_item)
        displayed_items = sorted_items[:MAX_DISPLAYED_ITEMS]
        hidden_count = len(sorted_items) - len(displayed_items)

        profitable_count = sum(1 for o in opportunities if o.profit > 0)
        header_text = (
            f"{len(by_item)} item(s) comparé(s) — {profitable_count} opportunité(s) rentable(s)"
            if by_item
            else "Aucune donnée de prix exploitable pour cette sélection."
        )
        if hidden_count > 0:
            header_text += f" — {len(displayed_items)} affiché(s), triés par rentabilité"
        header = ctk.CTkLabel(
            self.root,
            text=header_text,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=PALETTE["text"],
            wraplength=680,
        )
        header.pack(fill="x", padx=12, pady=(12, 4))

        body = ctk.CTkScrollableFrame(self.root, fg_color=PALETTE["bg"])
        body.pack(fill="both", expand=True, padx=12, pady=4)

        for item_name, item_opportunities in displayed_items:
            self._render_item_card(body, item_name, item_opportunities)

        ctk.CTkButton(
            self.root,
            text="Fermer",
            height=40,
            corner_radius=10,
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            text_color=PALETTE["accent_text"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.root.destroy,
        ).pack(fill="x", padx=12, pady=12)

    def _sorted_by_best_profit_percent(self, by_item: dict) -> list[tuple[str, list[Opportunity]]]:
        def best_profit_percent(pair):
            _, item_opportunities = pair
            return max((profit_percent(o) for o in item_opportunities), default=0)

        return sorted(by_item.items(), key=best_profit_percent, reverse=True)

    def _render_item_card(
        self, parent: ctk.CTkFrame, item_name: str, item_opportunities: list[Opportunity]
    ) -> None:
        card = ctk.CTkFrame(parent, fg_color=PALETTE["surface"], corner_radius=10)
        card.pack(fill="x", pady=6)

        ctk.CTkLabel(
            card,
            text=item_name,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PALETTE["text"],
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 4))

        profitable = sorted(
            (o for o in item_opportunities if o.profit > 0),
            key=profit_percent,
            reverse=True,
        )
        if not profitable:
            ctk.CTkLabel(
                card,
                text="Aucune opportunité rentable.",
                text_color=PALETTE["text_muted"],
                anchor="w",
            ).pack(fill="x", padx=12, pady=(0, 10))
            return

        for opportunity in profitable:
            self._render_opportunity_row(card, opportunity)
        ctk.CTkFrame(card, fg_color="transparent", height=6).pack()

    def _render_opportunity_row(self, parent: ctk.CTkFrame, opportunity: Opportunity) -> None:
        row = ctk.CTkFrame(parent, fg_color=PALETTE["surface_alt"], corner_radius=8)
        row.pack(fill="x", padx=12, pady=3)

        text_frame = ctk.CTkFrame(row, fg_color="transparent")
        text_frame.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        ctk.CTkLabel(
            text_frame,
            text=(
                f"Acheter sur {opportunity.buy_source} "
                f"({opportunity.buy_price} {opportunity.currency})"
            ),
            text_color=PALETTE["text"],
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            text_frame,
            text=(
                f"→ Lister sur {opportunity.sell_source} à "
                f"{opportunity.sell_gross_price} {opportunity.currency}"
            ),
            text_color=PALETTE["text"],
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            text_frame,
            text=(f"   (net {opportunity.sell_net_price} {opportunity.currency} après frais)"),
            text_color=PALETTE["text_muted"],
            anchor="w",
            font=ctk.CTkFont(size=11),
        ).pack(fill="x")
        if not opportunity.cash_realizable:
            ctk.CTkLabel(
                text_frame,
                text=STEAM_WALLET_WARNING,
                text_color=PALETTE["danger"],
                font=ctk.CTkFont(size=11),
                anchor="w",
            ).pack(fill="x")

        profit_frame = ctk.CTkFrame(row, fg_color="transparent")
        profit_frame.pack(side="right", padx=12)
        ctk.CTkLabel(
            profit_frame,
            text=f"+{opportunity.profit} {opportunity.currency}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PALETTE["profit"],
        ).pack()
        ctk.CTkLabel(
            profit_frame,
            text=f"+{profit_percent(opportunity):.1f}%",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["profit"],
        ).pack()


def show_report(opportunities: list[Opportunity]) -> None:
    root = ctk.CTk()
    ReportApp(root, opportunities)
    root.mainloop()
