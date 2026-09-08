"""Localized labels for generated front/back-matter sections.

The engine generates a handful of headings ("Contents", "About the Author", ...)
that are not part of the manuscript, and the boilerplate of the generated
glossary. They must follow the book's ``language`` field — a Spanish book with
an English "Contents" page, or a Spanish glossary whose every entry says "also
called", is the engine leaking into the book. Unknown languages fall back to
English.
"""

from __future__ import annotations

_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "glossary": "Glossary",
        "glossary_intro": (
            "Every term this book teaches, with the definition it commits to.\n"
            "The chapter number is where the term is introduced."
        ),
        "chapter_abbrev": "ch.",
        "also_called": "also called",
        "contents": "Contents",
        "about_author": "About the Author",
        "copyright": "Copyright",
        "cover": "Cover",
        "title": "Title",
    },
    "es": {
        "glossary": "Glosario",
        "glossary_intro": (
            "Cada término que enseña este libro, con la definición a la que se compromete.\n"
            "El número es el capítulo donde se introduce."
        ),
        "chapter_abbrev": "cap.",
        "also_called": "también llamado",
        "contents": "Índice",
        "about_author": "Sobre el autor",
        "copyright": "Copyright",
        "cover": "Cubierta",
        "title": "Portada",
    },
    "fr": {
        "glossary": "Glossaire",
        "glossary_intro": (
            "Chaque terme enseigné par ce livre, avec la définition qu'il retient.\n"
            "Le numéro est celui du chapitre où le terme est introduit."
        ),
        "chapter_abbrev": "chap.",
        "also_called": "aussi appelé",
        "contents": "Table des matières",
        "about_author": "À propos de l'auteur",
        "copyright": "Copyright",
        "cover": "Couverture",
        "title": "Titre",
    },
    "de": {
        "glossary": "Glossar",
        "glossary_intro": (
            "Jeder Begriff, den dieses Buch lehrt, mit der Definition, auf die es sich festlegt.\n"
            "Die Zahl ist das Kapitel, in dem der Begriff eingeführt wird."
        ),
        "chapter_abbrev": "Kap.",
        "also_called": "auch genannt",
        "contents": "Inhalt",
        "about_author": "Über den Autor",
        "copyright": "Impressum",
        "cover": "Umschlag",
        "title": "Titel",
    },
    "it": {
        "glossary": "Glossario",
        "glossary_intro": (
            "Ogni termine che questo libro insegna, con la definizione a cui si attiene.\n"
            "Il numero è il capitolo in cui il termine viene introdotto."
        ),
        "chapter_abbrev": "cap.",
        "also_called": "detto anche",
        "contents": "Indice",
        "about_author": "L'autore",
        "copyright": "Copyright",
        "cover": "Copertina",
        "title": "Titolo",
    },
    "pt": {
        "glossary": "Glossário",
        "glossary_intro": (
            "Cada termo que este livro ensina, com a definição a que se compromete.\n"
            "O número é o capítulo onde o termo é introduzido."
        ),
        "chapter_abbrev": "cap.",
        "also_called": "também chamado",
        "contents": "Índice",
        "about_author": "Sobre o autor",
        "copyright": "Copyright",
        "cover": "Capa",
        "title": "Título",
    },
    "ca": {
        "glossary": "Glossari",
        "glossary_intro": (
            "Cada terme que ensenya aquest llibre, amb la definició a què es compromet.\n"
            "El número és el capítol on s'introdueix el terme."
        ),
        "chapter_abbrev": "cap.",
        "also_called": "també anomenat",
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
