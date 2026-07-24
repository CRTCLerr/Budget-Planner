import sqlite3
import random
from datetime import date
from pathlib import Path

# ------------------------------------------------------------
# CATEGORY DEFINITIONS (EASY TO EDIT)
# ------------------------------------------------------------

SLIDER_CATEGORIES = [
    "Housing",
    "Utilities",
    "Groceries",
    "Transportation",
    "Insurance",
    "Healthcare",
    "Credit Card Payment",
    "Loan Payment",
    "Savings",
    "Personal Care",
    "Education",
    "Shopping",
    "Entertainment",
    "Dining Out",
    "Subscriptions",
    "Gifts",
    "Snacks",
    "Vapes",
    "Other",
]

# EASY-TO-EDIT CLAMP RANGES
CATEGORY_CLAMPS = {
    "Housing": (15, 200),
    "Utilities": (100, 300),
    "Groceries": (150, 200),
    "Transportation": (40, 80),
    "Insurance": (200, 800),
    "Healthcare": (20, 150),
    "Credit Card Payment": (25, 100),
    "Loan Payment": (50, 100),
    "Savings": (10, 50),
    "Personal Care": (10, 80),
    "Education": (20, 80),
    "Shopping": (20, 200),
    "Entertainment": (10, 80),
    "Dining Out": (15, 40),
    "Subscriptions": (5, 30),
    "Gifts": (10, 50),
    "Snacks": (5, 30),
    "Vapes": (18, 36),
    "Other": (5, 50),
}

# ------------------------------------------------------------
# FREQUENCY RULES FOR EXPENSES
# ------------------------------------------------------------

FREQUENCY_RULES = {
    # Insurance: 2 payments in January, 2 in July
    "Insurance": lambda year, month: 2 if month in (1, 7) else 0,

    # Utilities: 4 per month (Water, Electric, Gas, Internet)
    "Utilities": lambda year, month: 4,

    # Credit card: 1 per month
    "Credit Card Payment": lambda year, month: 1,

    # Savings: 2 per month
    "Savings": lambda year, month: 2,

    # Gifts: 1 per month
    "Gifts": lambda year, month: 1,

    # Transportation: 4–8 per month
    "Transportation": lambda year, month: random.randint(4, 8),

    # Loan payment: 1 per month
    "Loan Payment": lambda year, month: 1,
    
    # Vapes: 4-6 per month
    "Vapes": lambda year, month: random.randint(4, 6),
    
    # Groceries: 4 per month (weekly shopping)
    "Groceries": lambda year, month: 4,
    
    # Dining Out: 2-4 per month
    "Dining Out": lambda year, month: random.randint(2, 4),
    
    # Entertainment: 1 per month
    "Entertainment": lambda year, month: 1,
    
    # Personal Care: 2 per month simulating grooming and self-care expenses
    "Personal Care": lambda year, month: 2,
    
    # Subscriptions: 1 per month
    "Subscriptions": lambda year, month: 1,
    
    # Healthcare: 1-2 per month simulating doctor visits, medications, etc.
    "Healthcare": lambda year, month: random.randint(1, 2),
    
    # Education: 1 per month simulating courses, books, or educational materials
    "Education": lambda year, month: 1,
    
    # Shopping: 2-4 per month simulating clothing, electronics, or other discretionary purchases
    "Shopping": lambda year, month: random.randint(2, 4),
    
    # Other: 1-3 per month simulating miscellaneous expenses that don't fit into other categories
    "Other": lambda year, month: random.randint(1, 3),
    
    # Snacks: 4-8 per month simulating regular purchases of snacks and beverages
    "Snacks": lambda year, month: random.randint(4, 8),
}

# Default: 0–4 per month for all other categories
def default_frequency(year, month):
    return random.randint(0, 4)

# ------------------------------------------------------------
# RANDOM HELPERS
# ------------------------------------------------------------

def random_day(year, month):
    return random.randint(1, 28)  # safe for all months

def random_amount(category):
    low, high = CATEGORY_CLAMPS[category]
    return round(random.uniform(low, high), 2)

# ------------------------------------------------------------
# INCOME GENERATION (2 PAYCHECKS PER MONTH)
# ------------------------------------------------------------

HOURLY_WAGE = 32.98
HOURS_PER_WEEK = 40
WEEKS_PER_MONTH = 4  # per your request
TAX_RATE = 0.22
HEALTH_INSURANCE = 325.05
CHILD_SUPPORT = 360.00

# Calculate net paycheck
gross_monthly = HOURLY_WAGE * HOURS_PER_WEEK * WEEKS_PER_MONTH
taxes = gross_monthly * TAX_RATE
net_monthly = gross_monthly - taxes - HEALTH_INSURANCE - CHILD_SUPPORT
NET_PAYCHECK = round(net_monthly / 2, 2)  # two paychecks per month

def generate_income(conn, year, month):
    for day in (1, 15):  # two paychecks per month
        date_str = date(year, month, day).strftime("%Y-%m-%d")
        conn.execute(
            """
            INSERT INTO transactions (date, type, category, vendor, description, amount)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (date_str, "income", "Income", "Employer", "Paycheck", NET_PAYCHECK),
        )

# ------------------------------------------------------------
# SQLITE INSERT FOR EXPENSES
# ------------------------------------------------------------

def insert_expense(conn, date_str, category, amount):
    conn.execute(
        """
        INSERT INTO transactions (date, type, category, vendor, description, amount)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (date_str, "expense", category, category, f"Auto-generated {category}", amount),
    )

# ------------------------------------------------------------
# MAIN GENERATOR
# ------------------------------------------------------------

def generate_data(start_year=2020, end_year=2026):
    db_path = Path("budget_data.db")
    if not db_path.exists():
        raise FileNotFoundError("budget_data.db not found.")

    conn = sqlite3.connect(db_path)

    for year in range(start_year, end_year + 1):
        for month in range(1, 13):

            # 1. Generate income
            generate_income(conn, year, month)

            # 2. Generate expenses
            for category in SLIDER_CATEGORIES:

                # Determine frequency
                if category in FREQUENCY_RULES:
                    count = FREQUENCY_RULES[category](year, month)
                else:
                    count = default_frequency(year, month)

                # Generate transactions
                for _ in range(count):
                    day = random_day(year, month)
                    date_str = date(year, month, day).strftime("%Y-%m-%d")
                    amount = random_amount(category)
                    insert_expense(conn, date_str, category, amount)

    conn.commit()
    conn.close()
    print("Synthetic data generation complete.")

# ------------------------------------------------------------
# RUN SCRIPT
# ------------------------------------------------------------

if __name__ == "__main__":
    generate_data()
