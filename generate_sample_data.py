import csv
import random
from datetime import datetime, timedelta

frame_brands = ["Ray-Ban", "Oakley", "Prada", "Warby Parker", "Oakley", "Tom Ford", "Coach", "Michael Kors", "Burberry", "Versace"]
frame_styles = ["Aviator", "Wayfarer", "Round", "Cat-eye", "Rectangle", "Oval", "Square", "Shield", "Sport"]
lens_types = ["Single Vision", "Progressive", "Bifocal", "Polychromatic"]
materials = ["Acetate", "Titanium", "Metal", "Memory Metal", "TR-90", "Combination"]
prescriptions = ["-3.00", "-2.50", "-2.00", "-1.50", "-1.00", "-0.50", "0.00", "+0.50", "+1.00", "+1.50", "+2.00", "+2.50", "+3.00"]

def random_date(start, end):
    delta = end - start
    random_days = random.randint(0, delta.days)
    return (start + timedelta(days=random_days)).strftime("%Y-%m-%d")

start_date = datetime(2024, 1, 1)
end_date = datetime(2025, 12, 31)

rows = []
for i in range(500):
    brand = random.choice(frame_brands)
    style = random.choice(frame_styles)
    material = random.choice(materials)
    lens = random.choice(lens_types)
    rx = random.choice(prescriptions)
    qty = random.randint(1, 3)
    price = round(random.uniform(99, 450), 2)
    age = random.randint(18, 85)
    zip_code = random.choice(["10001", "90210", "60601", "33101", "02101", "98101", "75201", "85001"])
    
    rows.append({
        "sale_date": random_date(start_date, end_date),
        "frame_brand": brand,
        "frame_style": style,
        "material": material,
        "lens_type": lens,
        "prescription": rx,
        "quantity": qty,
        "unit_price": price,
        "total": round(price * qty, 2),
        "customer_age": age,
        "customer_zip": zip_code,
        "optician": random.choice(["Dr. Smith", "Dr. Johnson", "Dr. Williams", "Dr. Brown", "Dr. Davis"])
    })

with open("data-in/sample_optical_sales.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

print(f"Generated {len(rows)} rows in data-in/sample_optical_sales.csv")
