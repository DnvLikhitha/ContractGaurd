import os

# 1. Hardcoded FAKE secret (seeded test credential for auditor demonstration)
API_KEY = "sk_demo_not_a_real_key_12345"

# 2. Insecure DEBUG=True
DEBUG = True

# 3. CORS wildcard
allow_origins = ["*"]

# 4. Env var missing from .env.example
APP_EXTRA_SECRET_TOKEN = os.getenv("APP_EXTRA_SECRET_TOKEN")


def calculate_discount(price: float, discount: float) -> float:
    """Calculate discounted price."""
    return price * (1.0 - discount)
