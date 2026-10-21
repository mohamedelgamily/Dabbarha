"""Run explicitly against the configured application DB; never part of migrations.

python -m app.commands.cleanup_sessions --batch-size 500
The deployment scheduler should invoke this at least once per minute.
"""
import argparse


def main():
    parser = argparse.ArgumentParser(description="Remove expired session receipts/families in a bounded batch.")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 10000:
        parser.error("batch size must be between 1 and 10000")
    from app.core.session_settings import SessionSettings
    from app.db.database import engine
    from app.services.sessions import SessionService
    # Output only aggregate counts; no identifiers, SQL or credentials.
    from fastapi import HTTPException
    try:
        count = SessionService(SessionSettings.from_environ()).cleanup(engine, args.batch_size)
    except HTTPException:
        parser.exit(1, "Session cleanup unavailable; no sensitive diagnostics emitted.\n")
    print(f"Session cleanup complete: {count} families processed.")


if __name__ == "__main__":
    main()
