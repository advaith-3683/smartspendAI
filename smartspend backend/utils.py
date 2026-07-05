def normalize_category(name: str) -> str:
    """Trim whitespace and title-case so 'shopping', 'Shopping ', 'SHOPPING'
    all resolve to the same category: 'Shopping'."""
    return name.strip().title()
