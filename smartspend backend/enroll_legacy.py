"""Local operator credential enrollment. Never exposed through HTTP."""
import argparse
import getpass
from sqlalchemy.exc import IntegrityError
from database import engine, Base, SessionLocal
import models
import auth
from migrations import migrate

def main():
    parser = argparse.ArgumentParser(description="Enroll an externally verified legacy ledger owner. Stop the server first.")
    parser.add_argument("user_id", type=int)
    parser.add_argument("username")
    parser.add_argument("--verified-owner", action="store_true", required=True,
                        help="Operator attests ownership was established outside the app; IDs/names alone are insufficient")
    args = parser.parse_args()
    # Validate without accepting a password on the command line or in logs.
    password = getpass.getpass("New password (12–128 characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords do not match")
    login = auth.Login(username=args.username, password=password)
    if engine.dialect.name == "postgresql":
        from postgres_storage import verify_postgres
        verify_postgres(engine, Base.metadata)
    else:
        migrate(engine, Base.metadata)
    with SessionLocal() as db:
        if not db.get(models.User, args.user_id):
            raise SystemExit("User does not exist")
        if db.get(auth.Credential, args.user_id):
            raise SystemExit("Already enrolled; no credential overwritten")
        db.add(auth.Credential(user_id=args.user_id, username=login.username.lower(), password_hash=auth.password_hash(login.password)))
        try:
            db.commit()
        except IntegrityError:
            raise SystemExit("Username unavailable; no records changed")
    print("Credentials enrolled. Financial records retained.")

if __name__ == "__main__":
    main()
