import pandas as pd
import os
from datetime import datetime
from db import get_members  # FIXED

def export_members_excel():
    data = get_members()

    df = pd.DataFrame(data, columns=[
        "Member Code",
        "Name",
        "Province",
        "Constituency",
        "Phone"
    ])

    # Unique filename
    filename = f"members_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = os.path.join("exports", filename)

    os.makedirs("exports", exist_ok=True)

    df.to_excel(filepath, index=False)

    return filepath