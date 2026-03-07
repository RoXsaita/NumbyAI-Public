"""Seed mock data for LinkedIn carousel screenshots."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, datetime, timezone
from uuid import uuid4
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, User, Transaction, Budget, CategorizationPreference, TEST_USER_EMAIL

DATABASE_URL = "sqlite:///./finance_recon.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)

def utc_now():
    return datetime.now(timezone.utc)

def seed():
    session = Session()

    # --- User ---
    user = session.query(User).filter_by(email=TEST_USER_EMAIL).first()
    if not user:
        user = User(
            id=str(uuid4()),
            email=TEST_USER_EMAIL,
            name="Alex Chen",
            created_at=utc_now(),
        )
        session.add(user)
        session.flush()

    uid = user.id

    # --- Clear existing data ---
    session.query(Transaction).filter_by(user_id=uid).delete()
    session.query(Budget).filter_by(user_id=uid).delete()
    session.query(CategorizationPreference).filter_by(user_id=uid).delete()
    session.flush()

    # --- Transactions (Feb 2026) ---
    transactions = [
        # Income
        dict(date=date(2026, 2, 1),  description="DIRECT DEPOSIT - ACME CORP PAYROLL",    merchant="Acme Corp",      amount=Decimal("3850.00"),  category="Income",             category_source="rule",  bank_name="Chase"),
        dict(date=date(2026, 2, 15), description="DIRECT DEPOSIT - ACME CORP PAYROLL",    merchant="Acme Corp",      amount=Decimal("3850.00"),  category="Income",             category_source="rule",  bank_name="Chase"),
        dict(date=date(2026, 2, 10), description="VENMO CASHOUT",                         merchant="Venmo",          amount=Decimal("120.00"),   category="Income",             category_source="ai",    bank_name="Chase"),

        # Housing & Utilities
        dict(date=date(2026, 2, 1),  description="ZELLE PMT - LANDLORD RENT FEB",         merchant="Landlord",       amount=Decimal("-1850.00"), category="Housing & Utilities",category_source="rule",  bank_name="Chase"),
        dict(date=date(2026, 2, 5),  description="PG&E ELECTRIC BILL",                    merchant="PG&E",           amount=Decimal("-94.50"),   category="Housing & Utilities",category_source="ai",    bank_name="Chase"),
        dict(date=date(2026, 2, 7),  description="COMCAST XFINITY INTERNET",              merchant="Comcast",        amount=Decimal("-79.99"),   category="Housing & Utilities",category_source="rule",  bank_name="Chase"),

        # Food & Groceries
        dict(date=date(2026, 2, 3),  description="WHOLE FOODS MARKET #1286",              merchant="Whole Foods",    amount=Decimal("-87.43"),   category="Food & Groceries",   category_source="ai",    bank_name="Chase"),
        dict(date=date(2026, 2, 9),  description="TRADER JOE'S #421",                     merchant="Trader Joe's",   amount=Decimal("-63.12"),   category="Food & Groceries",   category_source="ai",    bank_name="Chase"),
        dict(date=date(2026, 2, 18), description="SAFEWAY STORE 0387",                    merchant="Safeway",        amount=Decimal("-54.78"),   category="Food & Groceries",   category_source="rule",  bank_name="Chase"),

        # Dining
        dict(date=date(2026, 2, 4),  description="DOORDASH*CHIPOTLE ORDER",               merchant="DoorDash",       amount=Decimal("-28.50"),   category="Food & Groceries",   category_source="ai",    bank_name="Chase"),
        dict(date=date(2026, 2, 13), description="SWEETGREEN SF MISSION",                 merchant="Sweetgreen",     amount=Decimal("-18.75"),   category="Food & Groceries",   category_source="ai",    bank_name="Chase"),
        dict(date=date(2026, 2, 20), description="RESTAURANT 365 DINNER",                 merchant="Restaurant 365", amount=Decimal("-94.20"),   category="Food & Groceries",   category_source="ai",    bank_name="Chase"),

        # Transportation
        dict(date=date(2026, 2, 2),  description="LYFT *RIDE FEB02",                      merchant="Lyft",           amount=Decimal("-14.50"),   category="Transportation",     category_source="rule",  bank_name="Chase"),
        dict(date=date(2026, 2, 11), description="UBER *TRIP HELP.UBER.COM",              merchant="Uber",           amount=Decimal("-22.30"),   category="Transportation",     category_source="rule",  bank_name="Chase"),
        dict(date=date(2026, 2, 16), description="CLIPPER CARD TRANSIT RELOAD",           merchant="BART/Clipper",   amount=Decimal("-50.00"),   category="Transportation",     category_source="ai",    bank_name="Chase"),

        # Subscriptions / Entertainment
        dict(date=date(2026, 2, 1),  description="NETFLIX.COM",                           merchant="Netflix",        amount=Decimal("-15.99"),   category="Entertainment",      category_source="rule",  bank_name="Chase"),
        dict(date=date(2026, 2, 1),  description="SPOTIFY USA",                           merchant="Spotify",        amount=Decimal("-11.99"),   category="Entertainment",      category_source="rule",  bank_name="Chase"),
        dict(date=date(2026, 2, 3),  description="APPLE.COM/BILL",                        merchant="Apple",          amount=Decimal("-9.99"),    category="Entertainment",      category_source="ai",    bank_name="Chase"),
        dict(date=date(2026, 2, 8),  description="CHATGPT SUBSCRIPTION",                  merchant="OpenAI",         amount=Decimal("-20.00"),   category="Entertainment",      category_source="rule",  bank_name="Chase"),

        # Shopping
        dict(date=date(2026, 2, 12), description="AMAZON.COM*4K9J2 AMZN.COM/BILL",       merchant="Amazon",         amount=Decimal("-67.89"),   category="Shopping",           category_source="ai",    bank_name="Chase"),
        dict(date=date(2026, 2, 22), description="TARGET 00000832",                       merchant="Target",         amount=Decimal("-43.55"),   category="Shopping",           category_source="ai",    bank_name="Chase"),

        # Healthcare
        dict(date=date(2026, 2, 14), description="CVS PHARMACY #7143",                   merchant="CVS",            amount=Decimal("-32.10"),   category="Healthcare",         category_source="ai",    bank_name="Chase"),

        # --- MANUAL_REVIEW items ---
        dict(date=date(2026, 2, 17), description="CASH APP*TRANSFER TO MIKE",             merchant="Cash App",       amount=Decimal("-250.00"),  category="MANUAL_REVIEW",      category_source="ai",    bank_name="Chase"),
        dict(date=date(2026, 2, 19), description="AMZN MKTP US*7F2K4 RETURN",            merchant="Amazon",         amount=Decimal("43.00"),    category="MANUAL_REVIEW",      category_source="ai",    bank_name="Chase"),
        dict(date=date(2026, 2, 24), description="CHECKCARD 0224 GLOBALTECH LLC",         merchant="GlobalTech LLC", amount=Decimal("-189.00"),  category="MANUAL_REVIEW",      category_source="ai",    bank_name="Chase"),
    ]

    for t in transactions:
        tx = Transaction(
            id=str(uuid4()),
            user_id=uid,
            currency="USD",
            created_at=utc_now(),
            updated_at=utc_now(),
            **t,
        )
        session.add(tx)

    # --- Budgets (monthly defaults, Feb 2026) ---
    budgets = [
        ("Food & Groceries",    500.00),
        ("Housing & Utilities", 2000.00),
        ("Transportation",      150.00),
        ("Entertainment",       100.00),
        ("Shopping",            200.00),
        ("Healthcare",          100.00),
        ("Investments",         500.00),
    ]
    for category, amount in budgets:
        b = Budget(
            id=str(uuid4()),
            user_id=uid,
            category=category,
            month_year="2026-02",
            amount=Decimal(str(amount)),
            currency="USD",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(b)

    # --- Categorization preferences (saved rules) ---
    rules = [
        dict(name="Rent payments via Zelle", rule={"type": "description_contains", "pattern": "RENT", "category": "Housing & Utilities"}, priority=10),
        dict(name="Netflix subscription",    rule={"type": "description_contains", "pattern": "NETFLIX", "category": "Entertainment"},      priority=10),
        dict(name="Spotify subscription",    rule={"type": "description_contains", "pattern": "SPOTIFY", "category": "Entertainment"},      priority=10),
        dict(name="Lyft rides",              rule={"type": "description_contains", "pattern": "LYFT",    "category": "Transportation"},     priority=10),
        dict(name="Uber rides",              rule={"type": "description_contains", "pattern": "UBER",    "category": "Transportation"},     priority=10),
        dict(name="Acme Corp payroll",       rule={"type": "description_contains", "pattern": "ACME CORP", "category": "Income"},           priority=20),
        dict(name="Safeway grocery runs",    rule={"type": "description_contains", "pattern": "SAFEWAY", "category": "Food & Groceries"},  priority=10),
        dict(name="Comcast internet bill",   rule={"type": "description_contains", "pattern": "COMCAST", "category": "Housing & Utilities"}, priority=10),
        dict(name="ChatGPT subscription",    rule={"type": "description_contains", "pattern": "CHATGPT", "category": "Entertainment"},     priority=10),
    ]
    for r in rules:
        pref = CategorizationPreference(
            id=str(uuid4()),
            user_id=uid,
            bank_name=None,
            preference_type="categorization",
            enabled=True,
            created_at=utc_now(),
            updated_at=utc_now(),
            **r,
        )
        session.add(pref)

    session.commit()
    session.close()
    print(f"Seeded: {len(transactions)} transactions, {len(budgets)} budgets, {len(rules)} rules")

if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(__file__), ".."))
    seed()
