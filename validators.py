import re

# ==============================
# BASIC CLEANING
# ==============================

def clean_text(value, max_length=100):
    if not value:
        return None
    
    value = value.strip()

    # Remove emojis / non-standard chars
    value = re.sub(r'[^\w\s\-]', '', value)

    # Limit length
    return value[:max_length]


# ==============================
# NAME VALIDATION
# ==============================

def validate_name(name):
    name = clean_text(name, 80)

    if not name or len(name) < 2:
        raise ValueError("Invalid name")

    return name.title()


# ==============================
# LOCATION VALIDATION
# ==============================

def validate_location(value, field_name="location"):
    value = clean_text(value, 60)

    if not value:
        raise ValueError(f"Invalid {field_name}")

    return value.title()


# ==============================
# PHONE NORMALIZATION (ZAMBIA)
# ==============================

def normalize_phone(phone):
    if not phone:
        raise ValueError("Phone number required")

    phone = re.sub(r'\D', '', phone)  # remove non-digits

    # Handle formats
    if phone.startswith("0"):
        phone = "260" + phone[1:]
    elif phone.startswith("260"):
        pass
    elif phone.startswith("+" ):
        phone = phone[1:]

    # Final format
    if not phone.startswith("260") or len(phone) != 12:
        raise ValueError("Invalid Zambian phone number")

    return "+" + phone