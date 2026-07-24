"""Text utilities for DMD rendering.

The bitmap fonts used by zeClock only support printable ASCII (32-126).
This module provides transliteration to replace accented and special
characters with their closest ASCII equivalents so that city names like
"Échirolles" render correctly as "Echirolles" on the display.
"""

# Transliteration table: accented/special chars → ASCII equivalents
_TRANSLITERATE_MAP = str.maketrans(
    {
        "à": "a",
        "á": "a",
        "â": "a",
        "ã": "a",
        "ä": "a",
        "å": "a",
        "ç": "c",
        "è": "e",
        "é": "e",
        "ê": "e",
        "ë": "e",
        "ì": "i",
        "í": "i",
        "î": "i",
        "ï": "i",
        "ð": "d",
        "ñ": "n",
        "ò": "o",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ö": "o",
        "ù": "u",
        "ú": "u",
        "û": "u",
        "ü": "u",
        "ý": "y",
        "ÿ": "y",
        "ß": "ss",
        "À": "A",
        "Á": "A",
        "Â": "A",
        "Ã": "A",
        "Ä": "A",
        "Å": "A",
        "Ç": "C",
        "È": "E",
        "É": "E",
        "Ê": "E",
        "Ë": "E",
        "Ì": "I",
        "Í": "I",
        "Î": "I",
        "Ï": "I",
        "Ð": "D",
        "Ñ": "N",
        "Ò": "O",
        "Ó": "O",
        "Ô": "O",
        "Õ": "O",
        "Ö": "O",
        "Ù": "U",
        "Ú": "U",
        "Û": "U",
        "Ü": "U",
        "Ý": "Y",
        "æ": "ae",
        "Æ": "AE",
        "œ": "oe",
        "Œ": "OE",
    }
)


def transliterate(text: str) -> str:
    """Replace accented and special characters with ASCII equivalents.

    Characters not in the translation table and not printable ASCII
    are stripped. This ensures text is renderable by the bitmap font
    system which only supports ASCII 32-126.

    Examples:
        >>> transliterate("Échirolles")
        'Echirolles'
        >>> transliterate("Château-d'Œx")
        "Chateau-d'OEx"
    """
    result = text.translate(_TRANSLITERATE_MAP)
    # Strip any remaining non-ASCII characters, but preserve newlines
    return "".join(ch for ch in result if ch == "\n" or 32 <= ord(ch) <= 126)
