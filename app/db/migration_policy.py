"""Keep archival tables until a separately approved data-retirement migration."""

LEGACY_RETAINED_TABLES = frozenset({"conversations", "conversation_messages"})


def include_object(obj, name: str, type_: str, reflected: bool, compare_to) -> bool:
    """Do not autogenerate drops just because retired ORM models are absent.

    This only filters reflected, metadata-absent archival tables. It does not
    change applied revision history, execute DDL, or hide other schema changes.
    An explicit future retirement migration remains a separate approval.
    """
    return not (
        type_ == "table"
        and reflected
        and compare_to is None
        and name in LEGACY_RETAINED_TABLES
    )
