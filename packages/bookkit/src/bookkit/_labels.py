"""Localized labels for generated front/back-matter sections.

The engine generates a handful of headings ("Contents", "About the Author", ...)
that are not part of the manuscript. They must follow the book's ``language``
field — a Spanish book with an English "Contents" page is the engine leaking
into the book. Unknown languages fall back to English.
"""

from __future__ import annotations

_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "contents": "Contents",
        "about_author": "About the Author",
        "copyright": "Copyright",
        "cover": "Cover",
        "title": "Title",
    },
    "es": {
        "contents": "Índice",
        "about_author": "Sobre el autor",
        "copyright": "Copyright",
        "cover": "Cubierta",
        "title": "Portada",
    },
    "fr": {
        "contents": "Table des matières",
        "about_author": "À propos de l'auteur",
        "copyright": "Copyright",
        "cover": "Couverture",
        "title": "Titre",
    },
    "de": {
        "contents": "Inhalt",
        "about_author": "Über den Autor",
        "copyright": "Impressum",
        "cover": "Umschlag",
        "title": "Titel",
    },
    "it": {
        "contents": "Indice",
        "about_author": "L'autore",
        "copyright": "Copyright",
        "cover": "Copertina",
        "title": "Titolo",
    },
    "pt": {
        "contents": "Índice",
        "about_author": "Sobre o autor",
        "copyright": "Copyright",
        "cover": "Capa",
        "title": "Título",
    },
    "ca": {
        "contents": "Índex",
        "about_author": "Sobre l'autor",
        "copyright": "Copyright",
        "cover": "Coberta",
        "title": "Títol",
    },
}


def labels_for(language: str) -> dict[str, str]:
    """Labels for a language code ("es", "es-ES", ...), falling back to English."""
    primary = (language or "en").split("-")[0].split("_")[0].lower()
    return _LABELS.get(primary, _LABELS["en"])
