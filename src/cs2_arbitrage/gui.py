import io
import queue
import threading
import tkinter as tk
import webbrowser
from decimal import ROUND_HALF_UP, Decimal

import customtkinter as ctk
import requests
from PIL import Image

from cs2_arbitrage.catalog import CatalogError, ItemCatalog, fetch_icon, rarity_color
from cs2_arbitrage.compare import Opportunity, profit_percent
from cs2_arbitrage.exchange_rate import ExchangeRateError, fetch_usd_to_eur_rate
from cs2_arbitrage.fonts import ITEM_NAME_FONT_FAMILY, register_fonts
from cs2_arbitrage.platform_links import build_item_url
from cs2_arbitrage.scanner import SCAN_CATEGORY_LABELS
from cs2_arbitrage.sources.skinport import SkinportError, fetch_recent_sales_volume

STEAM_WALLET_WARNING = "Steam Wallet uniquement, non retirable en cash"
CENT = Decimal("0.01")

ICON_DISPLAY_SIZE = 96
ICON_HEADER_SIZE = 192
REPORT_ICON_SIZE = 64
ICON_POLL_INTERVAL_MS = 50
# Attend une pause dans la frappe avant de lancer la recherche (évite un
# appel à ItemCatalog.search — donc un balayage du catalogue entier — à
# chaque touche pressée).
SEARCH_DEBOUNCE_MS = 250
# Volontairement plus bas que catalog.SEARCH_RESULT_LIMIT (40) : ici c'est
# une liste de suggestions façon autocomplétion, pas un résultat de
# recherche exhaustif — chaque suggestion charge sa propre icône, pas
# question d'en déclencher des dizaines d'un coup à chaque frappe.
SEARCH_SUGGESTIONS_LIMIT = 8
# Nombre max de trades affichés dans le rapport (un par item, cf.
# ReportApp._best_trade_per_item) : un scan de catalogue entier peut
# trouver bien plus d'opportunités que ça, au prix d'une fenêtre très
# lente à s'ouvrir (constaté en réel) pour un intérêt limité au-delà des
# toutes meilleures affaires.
TOP_TRADES_COUNT = 10
# Curseur de liquidité dans le rapport (ReportApp) : nombre minimum de
# ventes RÉELLEMENT CONCLUES sur Skinport (endpoint /v1/sales/history) sur
# les 7 DERNIERS JOURS — fenêtre fixe, pas ajustable, moins bruitée que
# 24h — pour qu'un item soit gardé dans le top 10, peu importe la
# plateforme réelle du trade. Repéré le 2026-08-04 : une grosse part des
# trades les plus rentables ont CS.Deals comme plateforme de vente, qui
# n'expose aucun vrai indicateur de ventes exploitable en masse — Skinport
# sert donc de proxy de liquidité cross-plateforme. Ajustable en direct
# (curseur) plutôt qu'une constante figée : toutes les données sont déjà
# en mémoire au moment d'afficher le rapport, pas besoin de relancer la
# comparaison pour changer le seuil.
LIQUIDITY_SLIDER_MIN = 0
LIQUIDITY_SLIDER_MAX = 50
LIQUIDITY_SLIDER_DEFAULT = 14

# Scan "tout le catalogue entre $X et $Y" : limité à Skinport/Waxpeer/
# CS.Deals (cf. scanner.py), Skinport servant de référence pour les deux
# seuils. Plages des molettes pensées pour de la chasse aux bonnes
# affaires, pas pour cibler des items chers. Le plancher par défaut
# (0.50) écarte déjà le bruit des items à 1-2 centimes, où un écart "à
# 100%" n'est souvent que le pas minimum de cotation entre deux
# plateformes plutôt qu'une vraie opportunité.
SCAN_PRICE_FLOOR_MIN = 0
SCAN_PRICE_FLOOR_MAX = 20
SCAN_PRICE_FLOOR_DEFAULT = Decimal("0.5")
SCAN_PRICE_CEIL_MIN = 1
SCAN_PRICE_CEIL_MAX = 100
SCAN_PRICE_CEIL_DEFAULT = 10

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
# Optimisation mineure : évite les appels Windows API de détection DPI à
# chaque tick de la boucle de surveillance interne de customtkinter,
# inutile ici (fenêtres à taille fixe). Ne suffit PAS à éliminer le bruit
# ci-dessous (vérifié en lisant scaling_tracker.py : la boucle elle-même
# n'est pas conditionnée par ce flag, seul le calcul DPI l'est).
ctk.deactivate_automatic_dpi_awareness()
register_fonts()


def _item_font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    # Police dédiée pour tous les noms d'items (skins/variantes), cf.
    # fonts.py pour le choix de Noto Sans comme alternative à Motiva Sans.
    # Le reste de l'interface (boutons, libellés génériques) garde la
    # police par défaut de customtkinter, volontairement pas touchée.
    return ctk.CTkFont(family=ITEM_NAME_FONT_FAMILY, size=size, weight=weight)


def _item_text_color(hash_name: str) -> str:
    # Couleurs de rareté CS2 classiques (cf. catalog.rarity_color, sourcé
    # depuis Waxpeer) ; repli sur la couleur de texte neutre du thème pour
    # les ~0.5% d'items sans couleur connue plutôt que de ne rien afficher.
    return rarity_color(hash_name) or PALETTE["text"]


def _install_benign_tcl_error_filter(root: ctk.CTk) -> None:
    """La boucle de surveillance DPI de customtkinter se reprogramme en
    continu via after() ; à la destruction d'une fenêtre, un appel reste en
    attente et Tcl râle une fois ("invalid command name ...") sur le tick
    suivant. Repéré le 2026-08-03 en enchaînant navigateur -> rapport (deux
    fenêtres CTk successives). Inoffensif (aucun impact sur le
    fonctionnement, confirmé en testant l'enchaînement complet) mais
    bruyant en console.

    Deux couches de filtrage, pas une seule :
    - report_callback_exception attrape les vraies exceptions Python levées
      DANS un callback Tk (ex: un bug dans la boucle de chargement des
      icônes) — utile à garder visible, donc pas désactivé globalement.
    - Le bruit qui nous intéresse ici n'est PAS une exception Python : Tcl
      ne trouve même plus la commande à appeler (widget détruit) et le
      signale via son propre mécanisme d'erreur "en arrière-plan" (bgerror),
      qui ne passe jamais par le pont Python — d'où la redéfinition de
      bgerror ci-dessous, seule couche qui l'intercepte réellement (vérifié
      : report_callback_exception seul ne suffisait pas)."""

    def _filtered(exc, val, tb):
        if issubclass(exc, tk.TclError) and "invalid command name" in str(val):
            return
        import traceback

        traceback.print_exception(exc, val, tb)

    root.report_callback_exception = _filtered
    root.tk.eval(
        """
        proc bgerror {msg} {
            if {[string match {invalid command name*} $msg]} {
                return
            }
            puts stderr $msg
        }
        """
    )


def _ctk_image(image: Image.Image, size: int) -> ctk.CTkImage:
    return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))


def _fetch_display_rate() -> Decimal | None:
    # None si le taux n'a pas pu être récupéré (réseau indisponible...) :
    # l'affichage retombe alors sur USD plutôt que d'afficher un montant
    # faux sous une étiquette EUR.
    try:
        return fetch_usd_to_eur_rate()
    except ExchangeRateError:
        return None


def _fetch_sales_volume_7d() -> dict[str, int]:
    # dict vide si l'historique de ventes Skinport est indisponible
    # (réseau, 429...) : le filtre de liquidité traite alors tout comme
    # "volume inconnu" et n'exclut rien, plutôt que de faire planter tout
    # le rapport pour un signal secondaire.
    try:
        return fetch_recent_sales_volume()
    except (requests.RequestException, SkinportError):
        return {}


def _to_display_currency(amount: Decimal, rate: Decimal | None) -> tuple[Decimal, str]:
    """Convertit un montant USD (l'unité de tout le pipeline, cf.
    main.py) en EUR pour l'AFFICHAGE seulement, si un taux est
    disponible."""
    if rate is None:
        return amount, "USD"
    return (amount * rate).quantize(CENT, rounding=ROUND_HALF_UP), "EUR"


# (nom interne PriceSource.name, libellé affiché), toutes cochées par défaut.
PLATFORMS = [
    ("steam", "Steam"),
    ("skinport", "Skinport"),
    ("csmoney", "CS.Money"),
    ("waxpeer", "Waxpeer"),
    ("csdeals", "CS.Deals"),
    ("whitemarket", "White.market"),
    ("marketcsgo", "market.csgo.com"),
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
        self.eur_rate = _fetch_display_rate()
        # market_hash_name -> PIL.Image brute (pas encore mise à la taille
        # d'affichage) : permet de reconstruire un CTkImage à la taille
        # voulue (liste vs en-tête agrandi) sans redemander l'image.
        self.icon_cache: dict[str, Image.Image] = {}
        self.placeholder_image = Image.new("RGBA", (8, 8), PALETTE["surface_alt"])
        self.render_generation = 0
        self.current_skin_hash_name = None
        self.search_active = False
        self.search_query = ""
        self.search_after_id: str | None = None
        self.result_items: list[str] = []
        self.result_platforms: list[str] = []
        self.result_scan_min_price: Decimal | None = None
        self.result_scan_max_price: Decimal | None = None
        self.result_scan_categories: set[str] | None = None

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

        self.search_entry = ctk.CTkEntry(
            self.root,
            placeholder_text="Rechercher un skin (ex: AK-47 Redline)",
            fg_color=PALETTE["surface"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text"],
        )
        self.search_entry.pack(fill="x", padx=12, pady=(0, 4))
        self.search_entry.bind("<KeyRelease>", self._on_search_key)

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
            text=(
                "Ou scanner tout le catalogue (Skinport/Waxpeer/CS.Deals/White.market/"
                "market.csgo.com) entre deux prix :"
            ),
            text_color=PALETTE["text_muted"],
        ).pack(anchor="w", padx=12)

        self._build_category_section(parent)

        self.scan_min_slider, self.scan_min_price_label = self._build_scan_slider_row(
            parent,
            "Minimum",
            SCAN_PRICE_FLOOR_MIN,
            SCAN_PRICE_FLOOR_MAX,
            SCAN_PRICE_FLOOR_DEFAULT,
            # Pas de 0.50 $ (40 crans sur 0-20) : assez fin pour écarter
            # spécifiquement le bruit des tout petits prix (1-2 centimes)
            # sans pour autant viser une précision au centime inutile ici.
            number_of_steps=(SCAN_PRICE_FLOOR_MAX - SCAN_PRICE_FLOOR_MIN) * 2,
        )
        self.scan_max_slider, self.scan_max_price_label = self._build_scan_slider_row(
            parent,
            "Maximum",
            SCAN_PRICE_CEIL_MIN,
            SCAN_PRICE_CEIL_MAX,
            SCAN_PRICE_CEIL_DEFAULT,
            number_of_steps=SCAN_PRICE_CEIL_MAX - SCAN_PRICE_CEIL_MIN,
        )

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
        ).pack(fill="x", padx=12, pady=(4, 12))

    def _build_category_section(self, parent: ctk.CTkFrame) -> None:
        # Filtre par catégorie (cf. scanner.py SCAN_CATEGORY_LABELS),
        # ajouté suite à des opportunités jugées peu fiables sur des
        # stickers à liquidité fine — permet de les exclure du scan plutôt
        # que de les découvrir après coup dans les résultats. Grille à 4
        # colonnes dans un cadre à hauteur fixe (comme "Items sélectionnés"
        # plus haut) pour ne pas allonger indéfiniment la fenêtre avec 17
        # catégories.
        ctk.CTkLabel(
            parent,
            text="Catégories incluses dans le scan :",
            text_color=PALETTE["text_muted"],
        ).pack(anchor="w", padx=12, pady=(8, 2))

        categories_frame = ctk.CTkScrollableFrame(
            parent,
            height=90,
            fg_color=PALETTE["surface_alt"],
            scrollbar_button_color=PALETTE["surface_hover"],
        )
        categories_frame.pack(fill="x", padx=12, pady=(0, 8))

        self.category_vars: dict[str, tk.BooleanVar] = {}
        columns = 4
        for index, (slug, label) in enumerate(SCAN_CATEGORY_LABELS.items()):
            variable = tk.BooleanVar(value=True)
            self.category_vars[slug] = variable
            ctk.CTkCheckBox(
                categories_frame,
                text=label,
                variable=variable,
                fg_color=PALETTE["accent"],
                hover_color=PALETTE["accent_hover"],
                checkmark_color=PALETTE["accent_text"],
                text_color=PALETTE["text"],
            ).grid(row=index // columns, column=index % columns, sticky="w", padx=6, pady=3)

    def _build_scan_slider_row(
        self,
        parent: ctk.CTkFrame,
        label_text: str,
        from_: float,
        to: float,
        default: Decimal,
        number_of_steps: int,
    ) -> tuple[ctk.CTkSlider, ctk.CTkLabel]:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 4))

        ctk.CTkLabel(row, text=label_text, width=60, text_color=PALETTE["text_muted"]).pack(
            side="left"
        )
        price_label = ctk.CTkLabel(
            row,
            text=self._format_scan_price(float(default)),
            width=90,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PALETTE["accent"],
        )
        price_label.pack(side="right")

        slider = ctk.CTkSlider(
            row,
            from_=from_,
            to=to,
            number_of_steps=number_of_steps,
            fg_color=PALETTE["surface_alt"],
            progress_color=PALETTE["accent"],
            button_color=PALETTE["accent"],
            button_hover_color=PALETTE["accent_hover"],
            command=lambda value, label=price_label: label.configure(
                text=self._format_scan_price(value)
            ),
        )
        slider.set(float(default))
        slider.pack(side="left", fill="x", expand=True, padx=(8, 10))
        return slider, price_label

    def _format_scan_price(self, usd_value: float) -> str:
        # La molette manipule des dollars en interne (c'est ce qui est
        # comparé au catalogue Skinport, en USD) : seul l'affichage est
        # converti en EUR, cf. _to_display_currency.
        amount, currency = _to_display_currency(Decimal(str(usd_value)), self.eur_rate)
        return f"{amount:.2f} {currency}"

    # -- Navigation ---------------------------------------------------

    def _enter(self, name: str) -> None:
        self.path.append(name)
        self._render()

    def _enter_skin(self, entry) -> None:
        self.current_skin_hash_name = entry.representative_hash_name
        self.path.append(entry.label)
        self._render()

    def _go_back(self) -> None:
        if self.search_active:
            self._clear_search()
            return
        self.path.pop()
        self._render()

    def _update_breadcrumb(self) -> None:
        if self.search_active:
            text = f'Résultats pour "{self.search_query}"'
        else:
            text = " > ".join(self.path) or "Type d'item"
        self.breadcrumb_label.configure(text=text)
        self.back_button.configure(
            state="normal" if (self.path or self.search_active) else "disabled"
        )

    # -- Recherche en langage naturel ------------------------------------

    def _on_search_key(self, event=None) -> None:
        if self.search_after_id is not None:
            self.root.after_cancel(self.search_after_id)
            self.search_after_id = None

        query = self.search_entry.get().strip()
        if not query:
            if self.search_active:
                self.search_active = False
                self._render()
            return
        self.search_after_id = self.root.after(SEARCH_DEBOUNCE_MS, self._run_search, query)

    def _run_search(self, query: str) -> None:
        self.search_after_id = None
        # La frappe a continué pendant le délai d'attente : cette requête
        # est déjà obsolète, une plus récente a été (ou va être) planifiée.
        if self.search_entry.get().strip() != query:
            return
        self.search_active = True
        self.search_query = query
        self._render()

    def _clear_search(self) -> None:
        self.search_active = False
        self.search_entry.delete(0, "end")
        self._render()

    def _render(self) -> None:
        self.render_generation += 1
        for widget in self.body_frame.winfo_children():
            widget.destroy()
        self._update_breadcrumb()

        try:
            if self.search_active:
                self._render_search_results()
                return
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
                row, text="", image=_ctk_image(self.placeholder_image, ICON_DISPLAY_SIZE)
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
                text_color=_item_text_color(entry.representative_hash_name),
                font=_item_font(),
                command=lambda e=entry: self._enter_skin(e),
            ).pack(side="left", fill="x", expand=True)
            hash_names.append(entry.representative_hash_name)
            icon_labels.append(icon_label)

        self._load_icons_async(hash_names, icon_labels, generation)

    def _render_variant_list(self) -> None:
        item_type, weapon, skin = self.path
        variants = self.catalog.fetch_variants(item_type, weapon, skin)

        image = self.icon_cache.get(self.current_skin_hash_name, self.placeholder_image)
        header = ctk.CTkLabel(self.body_frame, text="", image=_ctk_image(image, ICON_HEADER_SIZE))
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
                text_color=_item_text_color(hash_name),
                font=_item_font(),
                command=lambda h=hash_name, v=variable: self._toggle_item(h, v),
            ).pack(fill="x", pady=2)

    def _render_search_results(self) -> None:
        # Suggestions façon autocomplétion : icône + nom complet + case à
        # cocher, directement au niveau Variante (pas de nouvelle étape de
        # navigation) puisque market_hash_name est déjà l'item final.
        hash_names = self.catalog.search(self.search_query, limit=SEARCH_SUGGESTIONS_LIMIT)
        if not hash_names:
            self._render_empty()
            return

        generation = self.render_generation
        icon_labels = []
        for hash_name in hash_names:
            row = ctk.CTkFrame(self.body_frame, fg_color="transparent")
            row.pack(fill="x", pady=3)
            icon_label = ctk.CTkLabel(
                row, text="", image=_ctk_image(self.placeholder_image, ICON_DISPLAY_SIZE)
            )
            icon_label.pack(side="left", padx=(0, 8))
            variable = tk.BooleanVar(value=hash_name in self.selected_items)
            ctk.CTkCheckBox(
                row,
                text=hash_name,
                variable=variable,
                fg_color=PALETTE["accent"],
                hover_color=PALETTE["accent_hover"],
                checkmark_color=PALETTE["accent_text"],
                text_color=_item_text_color(hash_name),
                font=_item_font(),
                command=lambda h=hash_name, v=variable: self._toggle_item(h, v),
            ).pack(side="left", fill="x", expand=True)
            icon_labels.append(icon_label)

        self._load_icons_async(hash_names, icon_labels, generation)

    # -- Chargement des images en arrière-plan --------------------------

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
                    labels[index].configure(image=_ctk_image(cached, ICON_DISPLAY_SIZE))
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
            ctk.CTkLabel(
                row,
                text=hash_name,
                text_color=_item_text_color(hash_name),
                font=_item_font(),
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
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
        min_price = Decimal(str(round(self.scan_min_slider.get(), 2)))
        max_price = Decimal(str(round(self.scan_max_slider.get(), 2)))
        # Les deux molettes sont indépendantes : si l'utilisateur met le
        # minimum au-dessus du maximum, on les remet dans le bon ordre
        # plutôt que d'exiger qu'il les ajuste lui-même dans le bon sens.
        self.result_scan_min_price, self.result_scan_max_price = sorted([min_price, max_price])
        self.result_scan_categories = {
            slug for slug, var in self.category_vars.items() if var.get()
        }
        self.root.destroy()

    def _on_close(self) -> None:
        if self.search_after_id is not None:
            self.root.after_cancel(self.search_after_id)
        self.result_items = []
        self.result_platforms = []
        self.result_scan_min_price = None
        self.result_scan_max_price = None
        self.result_scan_categories = None
        self.root.destroy()


def run_item_browser() -> tuple[list[str], list[str], Decimal | None, Decimal | None, set | None]:
    root = ctk.CTk()
    _install_benign_tcl_error_filter(root)
    app = ItemBrowserApp(root, ItemCatalog())
    root.mainloop()
    return (
        app.result_items,
        app.result_platforms,
        app.result_scan_min_price,
        app.result_scan_max_price,
        app.result_scan_categories,
    )


class ReportApp:
    """Fenêtre de résultats : une carte par trade, un seul (le meilleur)
    par item, triées par profit relatif (%) décroissant — plus parlant que
    le montant absolu pour repérer les affaires intéressantes sur des
    items de prix très différents (cf. compare.profit_percent). Limité aux
    TOP_TRADES_COUNT meilleurs trades : un scan de catalogue entier peut
    trouver bien plus d'opportunités que ça n'a de sens d'afficher d'un
    coup (lenteur d'ouverture constatée en réel avec des centaines de
    lignes), et l'utilisateur ne s'intéresse de toute façon qu'aux
    meilleures affaires, pas à la liste exhaustive."""

    def __init__(self, root: ctk.CTk, opportunities: list[Opportunity]):
        self.root = root
        self.opportunities = opportunities
        self.eur_rate = _fetch_display_rate()
        self.sales_volume_7d = _fetch_sales_volume_7d()
        self.liquidity_threshold = LIQUIDITY_SLIDER_DEFAULT
        self.icon_cache: dict[str, Image.Image] = {}
        self.placeholder_image = Image.new("RGBA", (8, 8), PALETTE["surface_alt"])
        self.render_generation = 0
        self.root.title("CS2 Arbitrage — Résultats")
        self.root.geometry("720x700")
        self.root.minsize(600, 560)
        self.root.configure(fg_color=PALETTE["bg"])

        self.header_label = ctk.CTkLabel(
            self.root,
            text="",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=PALETTE["text"],
            wraplength=680,
        )
        self.header_label.pack(fill="x", padx=12, pady=(12, 4))

        self._build_liquidity_slider()

        self.body = ctk.CTkScrollableFrame(self.root, fg_color=PALETTE["bg"])
        self.body.pack(fill="both", expand=True, padx=12, pady=4)

        self._render_trades()

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

    def _build_liquidity_slider(self) -> None:
        # Réglable en direct plutôt qu'une constante figée : opportunities
        # et sales_volume_7d sont déjà en mémoire, pas besoin de relancer
        # la comparaison/le scan pour changer le seuil (cf.
        # LIQUIDITY_SLIDER_DEFAULT). Désactivé à 0 (aucun item exclu).
        panel = ctk.CTkFrame(self.root, fg_color=PALETTE["surface"], corner_radius=10)
        panel.pack(fill="x", padx=12, pady=(0, 4))

        label_row = ctk.CTkFrame(panel, fg_color="transparent")
        label_row.pack(fill="x", padx=12, pady=(8, 0))
        ctk.CTkLabel(
            label_row,
            text="Liquidité minimum (ventes Skinport / 7 jours) :",
            text_color=PALETTE["text_muted"],
        ).pack(side="left")
        self.liquidity_value_label = ctk.CTkLabel(
            label_row,
            text=self._format_liquidity_threshold(LIQUIDITY_SLIDER_DEFAULT),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PALETTE["accent"],
        )
        self.liquidity_value_label.pack(side="right")

        self.liquidity_slider = ctk.CTkSlider(
            panel,
            from_=LIQUIDITY_SLIDER_MIN,
            to=LIQUIDITY_SLIDER_MAX,
            number_of_steps=LIQUIDITY_SLIDER_MAX - LIQUIDITY_SLIDER_MIN,
            fg_color=PALETTE["surface_alt"],
            progress_color=PALETTE["accent"],
            button_color=PALETTE["accent"],
            button_hover_color=PALETTE["accent_hover"],
            command=self._on_liquidity_slider_change,
        )
        self.liquidity_slider.set(LIQUIDITY_SLIDER_DEFAULT)
        self.liquidity_slider.pack(fill="x", padx=12, pady=(4, 10))

    def _format_liquidity_threshold(self, value: float) -> str:
        threshold = round(value)
        return "désactivé" if threshold == 0 else f"≥ {threshold} ventes/7j"

    def _on_liquidity_slider_change(self, value: float) -> None:
        self.liquidity_threshold = round(value)
        self.liquidity_value_label.configure(text=self._format_liquidity_threshold(value))
        self._render_trades()

    def _render_trades(self) -> None:
        self.render_generation += 1
        generation = self.render_generation
        for widget in self.body.winfo_children():
            widget.destroy()

        compared_items_count = len({o.item_name for o in self.opportunities})
        best_trades = self._best_trade_per_item(self.opportunities)
        top_trades = best_trades[:TOP_TRADES_COUNT]

        header_text = (
            f"{compared_items_count} item(s) comparé(s) — top {len(top_trades)} "
            f"trade(s) le(s) plus rentable(s)"
            if top_trades
            else "Aucune opportunité rentable (ou seuil de liquidité trop élevé) pour cette sélection."
        )
        self.header_label.configure(text=header_text)

        icon_labels = []
        for opportunity in top_trades:
            icon_label = self._render_item_card(self.body, opportunity)
            icon_labels.append((opportunity.item_name, icon_label))
        self._load_icons_async(icon_labels, generation)

    def _best_trade_per_item(self, opportunities: list[Opportunity]) -> list[Opportunity]:
        """Le meilleur trade rentable (profit relatif décroissant) pour
        chaque item, un seul par item — les items sans trade rentable ne
        sont pas représentés du tout, contrairement à l'ancien
        comportement qui les affichait quand même avec "Aucune opportunité
        rentable". Écarte aussi les items sous le seuil de liquidité
        courant (self.liquidity_threshold, cf. _build_liquidity_slider) :
        un spread de prix ne veut rien dire si personne n'achète ce skin
        en ce moment, peu importe la plateforme réelle du trade. Filtre
        désactivé (rien exclu) si sales_volume_7d est vide, càd si
        l'historique de ventes Skinport n'a pas pu être récupéré : un
        signal secondaire indisponible ne doit pas vider tout le rapport."""
        liquidity_known = bool(self.sales_volume_7d)
        best_by_item: dict[str, Opportunity] = {}
        for opportunity in opportunities:
            if opportunity.profit <= 0:
                continue
            if (
                liquidity_known
                and self.sales_volume_7d.get(opportunity.item_name, 0) < self.liquidity_threshold
            ):
                continue
            current_best = best_by_item.get(opportunity.item_name)
            if current_best is None or profit_percent(opportunity) > profit_percent(current_best):
                best_by_item[opportunity.item_name] = opportunity
        return sorted(best_by_item.values(), key=profit_percent, reverse=True)

    def _render_item_card(self, parent: ctk.CTkFrame, opportunity: Opportunity) -> ctk.CTkLabel:
        card = ctk.CTkFrame(parent, fg_color=PALETTE["surface"], corner_radius=10)
        card.pack(fill="x", pady=6)

        header_row = ctk.CTkFrame(card, fg_color="transparent")
        header_row.pack(fill="x", padx=12, pady=(10, 4))
        icon_label = ctk.CTkLabel(
            header_row, text="", image=_ctk_image(self.placeholder_image, REPORT_ICON_SIZE)
        )
        icon_label.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            header_row,
            text=opportunity.item_name,
            font=_item_font(size=13, weight="bold"),
            text_color=_item_text_color(opportunity.item_name),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        self._render_opportunity_row(card, opportunity)
        ctk.CTkFrame(card, fg_color="transparent", height=6).pack()
        return icon_label

    def _render_opportunity_row(self, parent: ctk.CTkFrame, opportunity: Opportunity) -> None:
        row = ctk.CTkFrame(parent, fg_color=PALETTE["surface_alt"], corner_radius=8)
        row.pack(fill="x", padx=12, pady=3)

        # Conversion pour l'affichage seulement (utilisateur français) : le
        # pipeline entier reste en USD, cf. _to_display_currency. Le profit
        # affiché est dérivé des montants déjà convertis (pas reconverti
        # séparément) pour rester cohérent au centime près avec ce qui est
        # montré juste au-dessus.
        buy_amount, currency = _to_display_currency(opportunity.buy_price, self.eur_rate)
        sell_gross_amount, _ = _to_display_currency(opportunity.sell_gross_price, self.eur_rate)
        sell_net_amount, _ = _to_display_currency(opportunity.sell_net_price, self.eur_rate)
        profit_amount = sell_net_amount - buy_amount

        # profit_frame packé AVANT text_frame : c'est un widget à taille
        # fixe (side="right"), il doit réserver sa place dans la cavité en
        # premier. Repéré le 2026-08-03 (bug utilisateur, disparition du
        # bloc profit sur un scan avec beaucoup de résultats) : dans
        # l'ordre inverse, text_frame (fill="x", expand=True) packé en
        # premier réclame toute la largeur disponible de la ligne à cet
        # instant-là, ne laissant plus de place pour profit_frame packé
        # ensuite — idiome Tk classique, l'ordre de pack() (pas le side)
        # détermine qui réserve son espace en premier.
        profit_frame = ctk.CTkFrame(row, fg_color="transparent")
        profit_frame.pack(side="right", padx=12)
        ctk.CTkLabel(
            profit_frame,
            text=f"+{profit_amount} {currency}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PALETTE["profit"],
        ).pack()
        ctk.CTkLabel(
            profit_frame,
            text=f"+{profit_percent(opportunity):.1f}%",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["profit"],
        ).pack()

        text_frame = ctk.CTkFrame(row, fg_color="transparent")
        text_frame.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        self._render_platform_line(
            text_frame,
            text=f"Acheter sur {opportunity.buy_source} ({buy_amount} {currency})",
            source=opportunity.buy_source,
            item_name=opportunity.item_name,
            text_color=PALETTE["text"],
            font=ctk.CTkFont(),
        )
        self._render_platform_line(
            text_frame,
            text=f"→ Lister sur {opportunity.sell_source} à {sell_gross_amount} {currency}",
            source=opportunity.sell_source,
            item_name=opportunity.item_name,
            text_color=PALETTE["text"],
            font=ctk.CTkFont(),
        )
        ctk.CTkLabel(
            text_frame,
            text=f"   (net {sell_net_amount} {currency} après frais)",
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

    def _render_platform_line(
        self,
        parent: ctk.CTkFrame,
        text: str,
        source: str,
        item_name: str,
        text_color: str,
        font: ctk.CTkFont,
    ) -> None:
        # Bouton "↗" qui ouvre la page de l'item sur la plateforme
        # (platform_links.build_item_url) dans le navigateur par défaut —
        # accélère l'exécution MANUELLE du trade, jamais un ordre placé
        # depuis le code (décision utilisateur du 2026-08-04). Absent si
        # aucun lien n'a pu être construit (item introuvable dans le
        # catalogue de la plateforme, réseau indisponible...) plutôt que
        # d'afficher un bouton mort.
        line = ctk.CTkFrame(parent, fg_color="transparent")
        line.pack(fill="x")
        ctk.CTkLabel(line, text=text, text_color=text_color, font=font, anchor="w").pack(
            side="left", fill="x", expand=True
        )
        url = build_item_url(source, item_name)
        if url:
            ctk.CTkButton(
                line,
                text="↗",
                width=22,
                height=18,
                corner_radius=4,
                fg_color="transparent",
                hover_color=PALETTE["surface_hover"],
                text_color=PALETTE["accent"],
                font=ctk.CTkFont(size=11),
                command=lambda: webbrowser.open(url),
            ).pack(side="right", padx=(4, 0))

    # -- Chargement des icônes en arrière-plan ---------------------------

    def _load_icons_async(
        self, icon_labels: list[tuple[str, ctk.CTkLabel]], generation: int
    ) -> None:
        # Même principe que ItemBrowserApp._load_icons_async : le thread ne
        # touche aucun widget (pas thread-safe), il résout juste les octets
        # (fetch_icon, Waxpeer sans throttle puis repli Steam, cache disque
        # inclus) et les dépose dans la queue ; la création des CTkImage et
        # l'affichage se font côté thread principal via _poll_icon_queue.
        # generation (cf. render_generation) invalide les résultats d'un
        # chargement précédent si le curseur de liquidité a été rebougé
        # entre-temps (_render_trades peut être appelé plusieurs fois).
        work_queue: queue.Queue = queue.Queue()

        def worker():
            for index, (hash_name, _label) in enumerate(icon_labels):
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
        self._poll_icon_queue(work_queue, icon_labels, generation)

    def _poll_icon_queue(
        self,
        work_queue: "queue.Queue",
        icon_labels: list[tuple[str, ctk.CTkLabel]],
        generation: int,
    ) -> None:
        if not self.root.winfo_exists():
            return  # la fenêtre a été fermée pendant le chargement
        if generation != self.render_generation:
            return  # le curseur de liquidité a rebougé, ces résultats ne servent plus

        try:
            while True:
                item = work_queue.get_nowait()
                if item is None:
                    return
                index, hash_name, image = item
                if image is not None:
                    self.icon_cache[hash_name] = image
                cached = self.icon_cache.get(hash_name)
                if cached is not None:
                    icon_labels[index][1].configure(image=_ctk_image(cached, REPORT_ICON_SIZE))
        except queue.Empty:
            pass

        self.root.after(
            ICON_POLL_INTERVAL_MS, self._poll_icon_queue, work_queue, icon_labels, generation
        )


def show_report(opportunities: list[Opportunity]) -> None:
    root = ctk.CTk()
    _install_benign_tcl_error_filter(root)
    ReportApp(root, opportunities)
    root.mainloop()
