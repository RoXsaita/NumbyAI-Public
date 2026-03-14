"""
Seed the database with a full-year 2024 USD demo dataset.
Run from repo root with: make restart-dev
Or from server/ with: python scripts/seed_demo_data.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from decimal import Decimal
from app.database import Base, User, Transaction, CategorizationPreference, Budget, SessionLocal, engine, TEST_USER_EMAIL, TEST_USER_NAME

# ── bootstrap ──────────────────────────────────────────────────────────────────
Base.metadata.create_all(bind=engine)
db = SessionLocal()

# 1. Create test user
user = db.query(User).filter(User.email == TEST_USER_EMAIL).first()
if not user:
    user = User(email=TEST_USER_EMAIL, name=TEST_USER_NAME)
    db.add(user)
    db.commit()
    db.refresh(user)
user_id = str(user.id)
print(f"User: {user_id}")

# 2. Set functional currency to USD
existing = db.query(CategorizationPreference).filter(
    CategorizationPreference.user_id == user_id,
    CategorizationPreference.preference_type == "settings"
).first()
SETTINGS_RULE = {
    "functional_currency": "USD",
    "registered_banks": ["Chase", "Amex"],
    "onboarding_complete": True,
}
if existing:
    existing.rule = SETTINGS_RULE
else:
    db.add(CategorizationPreference(
        user_id=user_id,
        name="user_settings",
        rule=SETTINGS_RULE,
        preference_type="settings",
        priority=0,
    ))
db.commit()
print("Currency set to USD")

# 3. Clear any existing transactions
db.query(Transaction).filter(Transaction.user_id == user_id).delete()
db.commit()

# 4. Seed transactions
TRANSACTIONS = [
    # January
    ("2024-01-01", "Salary – Acme Corp",            5000.00,  "USD", "Income",              "Chase"),
    ("2024-01-02", "Rent – 412 Oak St",             -1500.00,  "USD", "Housing & Utilities", "Chase"),
    ("2024-01-03", "Con Edison Electric",             -180.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-01-04", "NYC Water & Sewer",               -120.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-01-06", "Whole Foods Market",              -142.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-01-10", "Trader Joe's",                    -98.00,  "USD", "Food & Groceries",    "Chase"),
    ("2024-01-13", "Chipotle",                         -22.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-01-15", "Sweetgreen",                       -18.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-01-17", "Pret A Manger",                    -14.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-01-18", "Starbucks",                        -12.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-01-21", "Panera Bread",                     -16.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-01-24", "Duane Reade – Groceries",          -62.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-01-15", "MTA Metro Card",                  -132.00, "USD", "Transportation",      "Chase"),
    ("2024-01-19", "Lyft",                             -28.00, "USD", "Transportation",      "Chase"),
    ("2024-01-23", "Uber",                             -32.00, "USD", "Transportation",      "Chase"),
    ("2024-01-26", "Gas – Shell",                      -48.00, "USD", "Transportation",      "Chase"),
    ("2024-01-29", "Parking",                          -50.00, "USD", "Transportation",      "Chase"),
    ("2024-01-20", "Planet Fitness",                   -25.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-01-28", "Walgreens – Prescriptions",        -75.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-01-21", "Spotify Premium",                  -11.00, "USD", "Entertainment",       "Amex"),
    ("2024-01-14", "Netflix",                          -18.00, "USD", "Entertainment",       "Amex"),
    ("2024-01-16", "Hulu",                             -14.00, "USD", "Entertainment",       "Amex"),
    ("2024-01-27", "Movie Tickets",                   -137.00, "USD", "Entertainment",       "Amex"),
    ("2024-01-25", "Amazon – Household",              -128.00, "USD", "Shopping",            "Amex"),
    ("2024-01-12", "Target",                           -72.00, "USD", "Shopping",            "Amex"),
    ("2024-01-08", "CVS – Household",                  -50.00, "USD", "Shopping",            "Amex"),
    ("2024-01-31", "Transfer to Savings",             -500.00, "USD", "Internal Transfers",  "Chase"),

    # February
    ("2024-02-01", "Salary – Acme Corp",             5000.00,  "USD", "Income",              "Chase"),
    ("2024-02-02", "Rent – 412 Oak St",             -1500.00,  "USD", "Housing & Utilities", "Chase"),
    ("2024-02-04", "Con Edison Electric",             -175.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-02-06", "NYC Water & Sewer",               -125.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-02-08", "Trader Joe's",                     -87.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-02-10", "Whole Foods Market",              -120.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-02-13", "Chipotle",                         -19.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-02-15", "Starbucks",                        -13.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-02-17", "Sweetgreen",                       -16.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-02-20", "Pret A Manger",                    -15.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-02-22", "Duane Reade – Groceries",          -62.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-02-25", "Bagel Shop",                       -12.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-02-15", "MTA Metro Card",                  -132.00, "USD", "Transportation",      "Chase"),
    ("2024-02-19", "Lyft",                             -24.00, "USD", "Transportation",      "Chase"),
    ("2024-02-22", "Uber",                             -29.00, "USD", "Transportation",      "Chase"),
    ("2024-02-26", "Parking",                          -85.00, "USD", "Transportation",      "Chase"),
    ("2024-02-14", "Valentine's Dinner",               -95.00, "USD", "Entertainment",       "Amex"),
    ("2024-02-08", "Spotify Premium",                  -11.00, "USD", "Entertainment",       "Amex"),
    ("2024-02-16", "Netflix",                          -18.00, "USD", "Entertainment",       "Amex"),
    ("2024-02-24", "Concert Tickets",                  -36.00, "USD", "Entertainment",       "Amex"),
    ("2024-02-20", "Planet Fitness",                   -25.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-02-27", "Walgreens – Prescriptions",        -75.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-02-18", "Amazon – Books",                   -45.00, "USD", "Shopping",            "Amex"),
    ("2024-02-23", "Target",                           -78.00, "USD", "Shopping",            "Amex"),
    ("2024-02-10", "CVS",                              -57.00, "USD", "Shopping",            "Amex"),
    ("2024-02-29", "Transfer to Savings",             -500.00, "USD", "Internal Transfers",  "Chase"),

    # March
    ("2024-03-01", "Salary – Acme Corp",             5000.00,  "USD", "Income",              "Chase"),
    ("2024-03-02", "Rent – 412 Oak St",             -1500.00,  "USD", "Housing & Utilities", "Chase"),
    ("2024-03-03", "Con Edison Electric",             -172.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-03-05", "NYC Water & Sewer",               -128.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-03-05", "Whole Foods Market",              -155.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-03-09", "Trader Joe's",                     -92.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-03-12", "Chipotle",                         -21.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-03-14", "Sweetgreen",                       -17.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-03-16", "Starbucks",                        -14.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-03-19", "Pret A Manger",                    -12.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-03-22", "Farmer's Market",                  -55.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-03-25", "Duane Reade",                      -64.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-03-28", "Bagel Shop",                       -11.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-03-14", "MTA Metro Card",                  -132.00, "USD", "Transportation",      "Chase"),
    ("2024-03-11", "Lyft",                             -27.00, "USD", "Transportation",      "Chase"),
    ("2024-03-18", "Uber",                             -35.00, "USD", "Transportation",      "Chase"),
    ("2024-03-21", "Gas – Shell",                      -52.00, "USD", "Transportation",      "Chase"),
    ("2024-03-26", "Parking",                          -42.00, "USD", "Transportation",      "Chase"),
    ("2024-03-29", "Lyft Airport",                     -22.00, "USD", "Transportation",      "Chase"),
    ("2024-03-18", "Netflix",                          -18.00, "USD", "Entertainment",       "Amex"),
    ("2024-03-10", "Spotify Premium",                  -11.00, "USD", "Entertainment",       "Amex"),
    ("2024-03-23", "Movie Tickets",                   -171.00, "USD", "Entertainment",       "Amex"),
    ("2024-03-16", "Broadway Lottery",                  0.00,  "USD", "Entertainment",       "Amex"),
    ("2024-03-25", "Planet Fitness",                   -25.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-03-07", "Walgreens – Prescriptions",        -75.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-03-20", "Target – Spring Refresh",         -165.00, "USD", "Shopping",            "Amex"),
    ("2024-03-13", "Amazon",                           -68.00, "USD", "Shopping",            "Amex"),
    ("2024-03-27", "H&M",                              -57.00, "USD", "Shopping",            "Amex"),
    ("2024-03-30", "CVS",                              -42.00, "USD", "Shopping",            "Amex"),
    ("2024-03-31", "Transfer to Savings",             -500.00, "USD", "Internal Transfers",  "Chase"),

    # April
    ("2024-04-01", "Salary – Acme Corp",             5000.00,  "USD", "Income",              "Chase"),
    ("2024-04-02", "Rent – 412 Oak St",             -1500.00,  "USD", "Housing & Utilities", "Chase"),
    ("2024-04-03", "Con Edison Electric",             -168.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-04-04", "NYC Water & Sewer",               -132.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-04-06", "Whole Foods Market",              -148.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-04-09", "Trader Joe's",                     -88.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-04-11", "Sweetgreen",                       -18.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-04-14", "Starbucks",                        -13.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-04-17", "Chipotle",                         -22.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-04-20", "Farmer's Market",                  -62.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-04-23", "Duane Reade",                      -54.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-04-27", "Bagel Shop",                       -13.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-04-28", "Pret A Manger",                    -16.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-04-10", "MTA Metro Card",                  -132.00, "USD", "Transportation",      "Chase"),
    ("2024-04-12", "Uber",                             -45.00, "USD", "Transportation",      "Chase"),
    ("2024-04-18", "Lyft",                             -38.00, "USD", "Transportation",      "Chase"),
    ("2024-04-22", "Gas – Shell",                      -58.00, "USD", "Transportation",      "Chase"),
    ("2024-04-26", "Parking",                          -47.00, "USD", "Transportation",      "Chase"),
    ("2024-04-15", "Concert Tickets",                 -140.00, "USD", "Entertainment",       "Amex"),
    ("2024-04-08", "Netflix",                          -18.00, "USD", "Entertainment",       "Amex"),
    ("2024-04-11", "Spotify Premium",                  -11.00, "USD", "Entertainment",       "Amex"),
    ("2024-04-20", "Museum – MoMA",                    -27.00, "USD", "Entertainment",       "Amex"),
    ("2024-04-28", "Comedy Club",                      -24.00, "USD", "Entertainment",       "Amex"),
    ("2024-04-25", "Planet Fitness",                   -25.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-04-16", "Walgreens – Prescriptions",        -75.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-04-18", "Amazon – Spring Wardrobe",        -220.00, "USD", "Shopping",            "Amex"),
    ("2024-04-07", "Target",                           -68.00, "USD", "Shopping",            "Amex"),
    ("2024-04-24", "Zara",                             -52.00, "USD", "Shopping",            "Amex"),
    ("2024-04-30", "Transfer to Savings",             -500.00, "USD", "Internal Transfers",  "Chase"),

    # May
    ("2024-05-01", "Salary – Acme Corp",             5000.00,  "USD", "Income",              "Chase"),
    ("2024-05-02", "Rent – 412 Oak St",             -1500.00,  "USD", "Housing & Utilities", "Chase"),
    ("2024-05-03", "Con Edison Electric",             -165.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-05-04", "NYC Water & Sewer",               -135.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-05-07", "Whole Foods Market",              -162.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-05-10", "Trader Joe's",                     -94.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-05-12", "Memorial Day BBQ – Costco",       -148.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-05-15", "Sweetgreen",                       -18.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-05-17", "Starbucks",                        -14.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-05-20", "Chipotle",                         -21.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-05-23", "Farmer's Market",                  -68.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-05-27", "Bagel Shop",                       -14.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-05-29", "Pret A Manger",                    -15.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-05-15", "MTA Metro Card",                  -132.00, "USD", "Transportation",      "Chase"),
    ("2024-05-08", "Uber",                             -32.00, "USD", "Transportation",      "Chase"),
    ("2024-05-16", "Lyft",                             -28.00, "USD", "Transportation",      "Chase"),
    ("2024-05-22", "Gas – Shell",                      -55.00, "USD", "Transportation",      "Chase"),
    ("2024-05-27", "Parking",                          -33.00, "USD", "Transportation",      "Chase"),
    ("2024-05-20", "Hulu + Disney Bundle",             -26.00, "USD", "Entertainment",       "Amex"),
    ("2024-05-08", "Netflix",                          -18.00, "USD", "Entertainment",       "Amex"),
    ("2024-05-11", "Spotify Premium",                  -11.00, "USD", "Entertainment",       "Amex"),
    ("2024-05-18", "Rooftop Bar",                      -85.00, "USD", "Entertainment",       "Amex"),
    ("2024-05-25", "Live Music",                       -65.00, "USD", "Entertainment",       "Amex"),
    ("2024-05-29", "Mini Golf + Drinks",               -75.00, "USD", "Entertainment",       "Amex"),
    ("2024-05-22", "Planet Fitness",                   -25.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-05-14", "Walgreens – Prescriptions",        -75.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-05-11", "Amazon – Home Refresh",            -95.00, "USD", "Shopping",            "Amex"),
    ("2024-05-19", "Target",                           -72.00, "USD", "Shopping",            "Amex"),
    ("2024-05-26", "TJ Maxx",                          -68.00, "USD", "Shopping",            "Amex"),
    ("2024-05-28", "Home Depot",                       -25.00, "USD", "Shopping",            "Amex"),
    ("2024-05-31", "Transfer to Savings",             -500.00, "USD", "Internal Transfers",  "Chase"),

    # June — raise kicks in
    ("2024-06-01", "Salary – Acme Corp",             5200.00,  "USD", "Income",              "Chase"),
    ("2024-06-02", "Rent – 412 Oak St",             -1500.00,  "USD", "Housing & Utilities", "Chase"),
    ("2024-06-04", "Con Edison Electric",             -175.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-06-05", "NYC Water & Sewer",               -125.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-06-08", "Whole Foods Market",              -178.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-06-11", "Trader Joe's",                    -104.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-06-14", "Sweetgreen",                       -20.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-06-16", "Starbucks",                        -15.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-06-18", "Farmer's Market",                  -72.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-06-21", "Chipotle",                         -23.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-06-24", "Bagel Shop",                       -14.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-06-27", "Duane Reade",                      -58.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-06-29", "Pret A Manger",                    -16.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-06-12", "MTA Metro Card",                  -132.00, "USD", "Transportation",      "Chase"),
    ("2024-06-15", "Uber – Airport",                   -68.00, "USD", "Transportation",      "Chase"),
    ("2024-06-19", "Lyft",                             -42.00, "USD", "Transportation",      "Chase"),
    ("2024-06-23", "Gas – Shell",                      -60.00, "USD", "Transportation",      "Chase"),
    ("2024-06-26", "NJ Transit",                       -22.00, "USD", "Transportation",      "Chase"),
    ("2024-06-28", "Parking",                          -26.00, "USD", "Transportation",      "Chase"),
    ("2024-06-18", "Broadway Show",                   -180.00, "USD", "Entertainment",       "Amex"),
    ("2024-06-08", "Netflix",                          -18.00, "USD", "Entertainment",       "Amex"),
    ("2024-06-11", "Spotify Premium",                  -11.00, "USD", "Entertainment",       "Amex"),
    ("2024-06-14", "Hulu",                             -15.00, "USD", "Entertainment",       "Amex"),
    ("2024-06-21", "Rooftop Bar",                      -62.00, "USD", "Entertainment",       "Amex"),
    ("2024-06-27", "Summer Concert",                   -44.00, "USD", "Entertainment",       "Amex"),
    ("2024-06-10", "Biab Workshop",                    -66.00, "USD", "Entertainment",       "Amex"),
    ("2024-06-22", "Planet Fitness",                   -25.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-06-06", "Walgreens – Prescriptions",        -75.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-06-20", "REI – Outdoor Gear",              -195.00, "USD", "Shopping",            "Amex"),
    ("2024-06-09", "Amazon",                           -68.00, "USD", "Shopping",            "Amex"),
    ("2024-06-25", "Target",                           -47.00, "USD", "Shopping",            "Amex"),
    ("2024-06-30", "Transfer to Savings",             -500.00, "USD", "Internal Transfers",  "Chase"),

    # July — summer peak
    ("2024-07-01", "Salary – Acme Corp",             5200.00,  "USD", "Income",              "Chase"),
    ("2024-07-02", "Rent – 412 Oak St",             -1550.00,  "USD", "Housing & Utilities", "Chase"),
    ("2024-07-03", "Con Edison Electric – A/C",       -195.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-07-04", "NYC Water & Sewer",               -105.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-07-07", "Whole Foods Market",              -185.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-07-09", "Trader Joe's",                    -110.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-07-11", "Farmer's Market",                  -62.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-07-13", "Sweetgreen",                       -22.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-07-15", "Starbucks",                        -16.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-07-18", "Chipotle",                         -24.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-07-21", "Duane Reade",                      -65.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-07-24", "Bagel Shop",                       -15.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-07-27", "BBQ Supplies – Costco",            -88.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-07-28", "Pret A Manger",                    -17.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-07-10", "MTA Metro Card",                  -132.00, "USD", "Transportation",      "Chase"),
    ("2024-07-13", "Amtrak – Weekend Trip",           -210.00, "USD", "Transportation",      "Chase"),
    ("2024-07-17", "Uber",                             -38.00, "USD", "Transportation",      "Chase"),
    ("2024-07-22", "Lyft",                             -44.00, "USD", "Transportation",      "Chase"),
    ("2024-07-25", "Gas – Shell",                      -55.00, "USD", "Transportation",      "Chase"),
    ("2024-07-29", "Parking",                          -28.00, "USD", "Transportation",      "Chase"),
    ("2024-07-30", "E-ZPass Toll",                     -32.00, "USD", "Transportation",      "Chase"),
    ("2024-07-31", "Bike Share",                       -41.00, "USD", "Transportation",      "Chase"),
    ("2024-07-19", "Rooftop Bar",                      -95.00, "USD", "Entertainment",       "Amex"),
    ("2024-07-22", "Summer Concert",                   -75.00, "USD", "Entertainment",       "Amex"),
    ("2024-07-08", "Netflix",                          -18.00, "USD", "Entertainment",       "Amex"),
    ("2024-07-11", "Spotify Premium",                  -11.00, "USD", "Entertainment",       "Amex"),
    ("2024-07-14", "Hulu",                             -15.00, "USD", "Entertainment",       "Amex"),
    ("2024-07-26", "Museum Day",                       -45.00, "USD", "Entertainment",       "Amex"),
    ("2024-07-28", "Beach Day Rental",                 -55.00, "USD", "Entertainment",       "Amex"),
    ("2024-07-20", "Yacht Party",                      -36.00, "USD", "Entertainment",       "Amex"),
    ("2024-07-25", "Planet Fitness",                   -25.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-07-08", "Walgreens",                        -75.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-07-16", "Amazon – Summer",                 -155.00, "USD", "Shopping",            "Amex"),
    ("2024-07-23", "Target",                            -75.00, "USD", "Shopping",            "Amex"),
    ("2024-07-12", "Zara – Summer Sale",               -50.00, "USD", "Shopping",            "Amex"),
    ("2024-07-31", "Transfer to Savings",             -500.00, "USD", "Internal Transfers",  "Chase"),

    # August — back to school
    ("2024-08-01", "Salary – Acme Corp",             5200.00,  "USD", "Income",              "Chase"),
    ("2024-08-02", "Rent – 412 Oak St",             -1550.00,  "USD", "Housing & Utilities", "Chase"),
    ("2024-08-03", "Con Edison Electric – A/C",       -190.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-08-04", "NYC Water & Sewer",               -110.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-08-05", "Whole Foods Market",              -172.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-08-08", "Trader Joe's",                    -108.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-08-10", "Farmer's Market",                  -58.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-08-13", "Sweetgreen",                       -21.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-08-16", "Starbucks",                        -15.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-08-19", "Chipotle",                         -23.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-08-22", "Duane Reade",                      -62.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-08-25", "Bagel Shop",                       -14.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-08-28", "Pret A Manger",                    -16.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-08-30", "Grill Night – Costco",             -75.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-08-12", "MTA Metro Card",                  -132.00, "USD", "Transportation",      "Chase"),
    ("2024-08-09", "Uber",                             -36.00, "USD", "Transportation",      "Chase"),
    ("2024-08-14", "Lyft",                             -32.00, "USD", "Transportation",      "Chase"),
    ("2024-08-20", "Gas – Shell",                      -58.00, "USD", "Transportation",      "Chase"),
    ("2024-08-24", "Parking",                          -45.00, "USD", "Transportation",      "Chase"),
    ("2024-08-28", "E-ZPass Toll",                     -37.00, "USD", "Transportation",      "Chase"),
    ("2024-08-22", "Museum Memberships",               -85.00, "USD", "Entertainment",       "Amex"),
    ("2024-08-08", "Netflix",                          -18.00, "USD", "Entertainment",       "Amex"),
    ("2024-08-11", "Spotify Premium",                  -11.00, "USD", "Entertainment",       "Amex"),
    ("2024-08-17", "Hulu",                             -15.00, "USD", "Entertainment",       "Amex"),
    ("2024-08-24", "Live Music",                       -80.00, "USD", "Entertainment",       "Amex"),
    ("2024-08-29", "Comedy Club",                      -81.00, "USD", "Entertainment",       "Amex"),
    ("2024-08-25", "Planet Fitness",                   -25.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-08-07", "Walgreens",                        -75.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-08-12", "Amazon – Back-to-School",         -290.00, "USD", "Shopping",            "Amex"),
    ("2024-08-15", "Target – Home Office",            -155.00, "USD", "Shopping",            "Amex"),
    ("2024-08-06", "Best Buy – Monitor",               -35.00, "USD", "Shopping",            "Amex"),
    ("2024-08-31", "Transfer to Savings",             -500.00, "USD", "Internal Transfers",  "Chase"),

    # September
    ("2024-09-01", "Salary – Acme Corp",             5200.00,  "USD", "Income",              "Chase"),
    ("2024-09-02", "Rent – 412 Oak St",             -1550.00,  "USD", "Housing & Utilities", "Chase"),
    ("2024-09-04", "Con Edison Electric",             -178.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-09-05", "NYC Water & Sewer",               -122.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-09-07", "Whole Foods Market",              -148.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-09-10", "Trader Joe's",                     -96.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-09-12", "Chipotle",                         -23.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-09-15", "Sweetgreen",                       -19.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-09-18", "Farmer's Market",                  -55.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-09-21", "Starbucks",                        -14.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-09-24", "Duane Reade",                      -58.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-09-27", "Bagel Shop",                       -13.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-09-29", "Pret A Manger",                    -15.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-09-10", "MTA Metro Card",                  -132.00, "USD", "Transportation",      "Chase"),
    ("2024-09-13", "Uber",                             -34.00, "USD", "Transportation",      "Chase"),
    ("2024-09-17", "Lyft",                             -29.00, "USD", "Transportation",      "Chase"),
    ("2024-09-23", "Gas – Shell",                      -50.00, "USD", "Transportation",      "Chase"),
    ("2024-09-26", "Parking",                          -50.00, "USD", "Transportation",      "Chase"),
    ("2024-09-20", "Apple Fitness+",                   -80.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-09-07", "Walgreens",                        -75.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-09-08", "Spotify Premium",                  -11.00, "USD", "Entertainment",       "Amex"),
    ("2024-09-11", "Netflix",                          -18.00, "USD", "Entertainment",       "Amex"),
    ("2024-09-15", "Hulu",                             -15.00, "USD", "Entertainment",       "Amex"),
    ("2024-09-21", "Jazz Club",                        -56.00, "USD", "Entertainment",       "Amex"),
    ("2024-09-22", "Fall Market – Shopping",          -188.00, "USD", "Shopping",            "Amex"),
    ("2024-09-14", "Amazon",                           -82.00, "USD", "Shopping",            "Amex"),
    ("2024-09-28", "Target",                           -55.00, "USD", "Shopping",            "Amex"),
    ("2024-09-30", "TJ Maxx",                          -25.00, "USD", "Shopping",            "Amex"),
    ("2024-09-30", "Transfer to Savings",             -500.00, "USD", "Internal Transfers",  "Chase"),

    # October
    ("2024-10-01", "Salary – Acme Corp",             5200.00,  "USD", "Income",              "Chase"),
    ("2024-10-02", "Rent – 412 Oak St",             -1550.00,  "USD", "Housing & Utilities", "Chase"),
    ("2024-10-03", "Con Edison Electric",             -172.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-10-04", "NYC Water & Sewer",               -128.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-10-05", "Whole Foods Market",              -162.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-10-08", "Trader Joe's",                     -98.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-10-11", "Sweetgreen",                       -20.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-10-14", "Starbucks – Pumpkin Spice Season", -16.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-10-17", "Chipotle",                         -22.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-10-20", "Farmer's Market",                  -62.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-10-23", "Duane Reade",                      -60.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-10-26", "Bagel Shop",                       -13.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-10-28", "Pret A Manger",                    -16.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-10-30", "Pre-Halloween Groceries",          -56.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-10-10", "MTA Metro Card",                  -132.00, "USD", "Transportation",      "Chase"),
    ("2024-10-13", "Uber",                             -33.00, "USD", "Transportation",      "Chase"),
    ("2024-10-16", "Lyft",                             -35.00, "USD", "Transportation",      "Chase"),
    ("2024-10-22", "Gas – Shell",                      -52.00, "USD", "Transportation",      "Chase"),
    ("2024-10-25", "Parking",                          -44.00, "USD", "Transportation",      "Chase"),
    ("2024-10-28", "NJ Transit – Day Trip",            -54.00, "USD", "Transportation",      "Chase"),
    ("2024-10-20", "Spotify Premium",                  -11.00, "USD", "Entertainment",       "Amex"),
    ("2024-10-08", "Netflix",                          -18.00, "USD", "Entertainment",       "Amex"),
    ("2024-10-11", "Hulu",                             -15.00, "USD", "Entertainment",       "Amex"),
    ("2024-10-19", "Halloween – Party Supplies",       -85.00, "USD", "Entertainment",       "Amex"),
    ("2024-10-26", "Haunted House",                    -68.00, "USD", "Entertainment",       "Amex"),
    ("2024-10-28", "Comedy Club",                      -23.00, "USD", "Entertainment",       "Amex"),
    ("2024-10-24", "Planet Fitness",                   -25.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-10-08", "Walgreens",                        -75.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-10-15", "Halloween – Amazon Costumes",     -145.00, "USD", "Shopping",            "Amex"),
    ("2024-10-07", "Target",                           -72.00, "USD", "Shopping",            "Amex"),
    ("2024-10-18", "Amazon – Household",               -73.00, "USD", "Shopping",            "Amex"),
    ("2024-10-31", "Transfer to Savings",             -500.00, "USD", "Internal Transfers",  "Chase"),

    # November — Thanksgiving + Black Friday
    ("2024-11-01", "Salary – Acme Corp",             5200.00,  "USD", "Income",              "Chase"),
    ("2024-11-02", "Rent – 412 Oak St",             -1550.00,  "USD", "Housing & Utilities", "Chase"),
    ("2024-11-04", "Con Edison Electric",             -185.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-11-05", "NYC Water & Sewer",               -115.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-11-08", "Whole Foods Market",              -198.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-11-11", "Trader Joe's",                    -105.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-11-14", "Sweetgreen",                       -20.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-11-17", "Starbucks – Holiday Cups",         -16.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-11-19", "Chipotle",                         -24.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-11-21", "Thanksgiving Groceries – Costco", -225.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-11-23", "Farmer's Market",                  -52.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-11-26", "Bagel Shop",                       -14.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-11-28", "Duane Reade",                      -60.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-11-30", "Pret A Manger",                    -16.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-11-12", "MTA Metro Card",                  -132.00, "USD", "Transportation",      "Chase"),
    ("2024-11-06", "Uber",                             -36.00, "USD", "Transportation",      "Chase"),
    ("2024-11-15", "Lyft",                             -31.00, "USD", "Transportation",      "Chase"),
    ("2024-11-20", "Gas – Shell",                      -55.00, "USD", "Transportation",      "Chase"),
    ("2024-11-26", "Parking – Airport",                -56.00, "USD", "Transportation",      "Chase"),
    ("2024-11-25", "Airbnb – Thanksgiving Weekend",  -280.00, "USD", "Entertainment",       "Amex"),
    ("2024-11-08", "Netflix",                          -18.00, "USD", "Entertainment",       "Amex"),
    ("2024-11-11", "Spotify Premium",                  -11.00, "USD", "Entertainment",       "Amex"),
    ("2024-11-15", "Hulu",                             -15.00, "USD", "Entertainment",       "Amex"),
    ("2024-11-22", "Live Music",                       -62.00, "USD", "Entertainment",       "Amex"),
    ("2024-11-24", "Planet Fitness",                   -25.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-11-07", "Walgreens",                        -75.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-11-29", "Black Friday – Amazon",           -320.00, "USD", "Shopping",            "Amex"),
    ("2024-11-16", "Target – Pre-Holiday",             -95.00, "USD", "Shopping",            "Amex"),
    ("2024-11-09", "Zara – Fall Collection",           -65.00, "USD", "Shopping",            "Amex"),
    ("2024-11-22", "Amazon – Early Gifts",             -40.00, "USD", "Shopping",            "Amex"),
    ("2024-11-30", "Transfer to Savings",             -500.00, "USD", "Internal Transfers",  "Chase"),

    # December — bonus month + holiday spending
    ("2024-12-01", "Salary – Acme Corp",             5200.00,  "USD", "Income",              "Chase"),
    ("2024-12-15", "Year-End Bonus",                   500.00,  "USD", "Income",              "Chase"),
    ("2024-12-02", "Rent – 412 Oak St",             -1550.00,  "USD", "Housing & Utilities", "Chase"),
    ("2024-12-04", "Con Edison Electric",             -192.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-12-06", "NYC Water & Sewer",               -108.00, "USD", "Housing & Utilities", "Chase"),
    ("2024-12-05", "Whole Foods Market",              -220.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-12-07", "Holiday Party Catering",          -185.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-12-10", "Trader Joe's",                    -115.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-12-12", "Starbucks – Holiday",              -18.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-12-14", "Sweetgreen",                       -20.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-12-17", "Chipotle",                         -24.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-12-19", "Duane Reade",                      -65.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-12-22", "Christmas Dinner – Whole Foods",  -180.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-12-24", "Bagel Shop",                       -16.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-12-27", "Pret A Manger",                    -17.00, "USD", "Food & Groceries",    "Chase"),
    ("2024-12-10", "MTA Metro Card",                  -132.00, "USD", "Transportation",      "Chase"),
    ("2024-12-08", "Uber",                             -44.00, "USD", "Transportation",      "Chase"),
    ("2024-12-13", "Lyft – Holiday Party",             -38.00, "USD", "Transportation",      "Chase"),
    ("2024-12-18", "Gas – Shell",                      -56.00, "USD", "Transportation",      "Chase"),
    ("2024-12-23", "Parking – Airport",                -50.00, "USD", "Transportation",      "Chase"),
    ("2024-12-12", "Nutcracker Ballet",               -120.00, "USD", "Entertainment",       "Amex"),
    ("2024-12-20", "NYE Dinner Reservation",          -200.00, "USD", "Entertainment",       "Amex"),
    ("2024-12-26", "Airbnb – NYE Getaway",            -100.00, "USD", "Entertainment",       "Amex"),
    ("2024-12-08", "Netflix",                          -18.00, "USD", "Entertainment",       "Amex"),
    ("2024-12-11", "Spotify Premium",                  -11.00, "USD", "Entertainment",       "Amex"),
    ("2024-12-15", "Hulu – Holiday Bundle",            -15.00, "USD", "Entertainment",       "Amex"),
    ("2024-12-22", "Holiday Lights Tour",              -76.00, "USD", "Entertainment",       "Amex"),
    ("2024-12-25", "Planet Fitness",                   -25.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-12-06", "Walgreens",                        -75.00, "USD", "Health & Fitness",    "Chase"),
    ("2024-12-14", "Holiday Gifts – Amazon",          -380.00, "USD", "Shopping",            "Amex"),
    ("2024-12-17", "Holiday Gifts – Apple Store",     -250.00, "USD", "Shopping",            "Amex"),
    ("2024-12-09", "Macy's – Holiday",                 -95.00, "USD", "Shopping",            "Amex"),
    ("2024-12-19", "Amazon – Stocking Stuffers",       -55.00, "USD", "Shopping",            "Amex"),
    ("2024-12-31", "Transfer to Savings",             -500.00, "USD", "Internal Transfers",  "Chase"),
]

count = 0
for row in TRANSACTIONS:
    d_str, desc, amount, currency, category, bank = row
    y, m, day = map(int, d_str.split("-"))
    tx = Transaction(
        user_id=user_id,
        date=date(y, m, day),
        description=desc,
        amount=Decimal(str(amount)),
        currency=currency,
        category=category,
        bank_name=bank,
        category_source="manual",
    )
    db.add(tx)
    count += 1

db.commit()
print(f"Inserted {count} transactions")

# 5. Seed budgets (monthly defaults)
db.query(Budget).filter(Budget.user_id == user_id).delete()
db.commit()

BUDGETS = [
    # category, month_year, amount  (amount = positive target spend for expense cats, positive for income)
    ("Income",              None,      5200.00),
    ("Housing & Utilities", None,      1850.00),
    ("Food & Groceries",    None,       620.00),
    ("Transportation",      None,       300.00),
    ("Entertainment",       None,       250.00),
    ("Health & Fitness",    None,       100.00),
    ("Shopping",            None,       350.00),
    ("Internal Transfers",  None,       500.00),
    # December higher budgets
    ("Food & Groceries",    "2024-12",  700.00),
    ("Entertainment",       "2024-12",  350.00),
    ("Shopping",            "2024-12",  700.00),
    # November
    ("Food & Groceries",    "2024-11",  620.00),
    ("Shopping",            "2024-11",  500.00),
    # Summer
    ("Entertainment",       "2024-07",  300.00),
    ("Entertainment",       "2024-06",  300.00),
    ("Transportation",      "2024-07",  300.00),
]

for cat, month_year, amount in BUDGETS:
    db.add(Budget(
        user_id=user_id,
        category=cat,
        month_year=month_year,
        amount=Decimal(str(amount)),
        currency="USD",
    ))

db.commit()
print(f"Inserted {len(BUDGETS)} budget entries")
print("\n✓ Seed complete — full year 2024 USD data ready")
db.close()
