from models import db, Product

def seed_products():
    if not Product.query.first():  # Only seed if table is empty
        products = [
            Product(sku="SKU-1", name="MetaEarn Intern", price=250, income_per_day=50, period_days=8, image="intern.png"),
            Product(sku="SKU-2", name="MetaEarn 1", price=900, income_per_day=100, period_days=25, image="metearn1.png"),
            Product(sku="SKU-3", name="MetaEarn 2", price=2200, income_per_day=200, period_days=30, image="metearn2.png"),
            Product(sku="SKU-4", name="MetaEarn 3", price=3500, income_per_day=301, period_days=40, image="metearn3.png"),
            Product(sku="SKU-5", name="MetaEarn 4", price=5500, income_per_day=450, period_days=45, image="metearn4.png"),
            Product(sku="SKU-6", name="MetaEarn 5", price=12000, income_per_day=1020, period_days=60, image="metearn5.png"),
            Product(sku="SKU-7", name="MetaEarn 6", price=21000, income_per_day=1890, period_days=90, image="metearn6.png"),
            Product(sku="SKU-8", name="MetaEarn 7", price=35000, income_per_day=3150, period_days=100, image="metearn7.png"),
            Product(sku="SKU-9", name="MetaEarn 8", price=49000, income_per_day=4410, period_days=120, image="metearn8.png"),
            Product(sku="SKU-10", name="MetaEarn 9", price=68000, income_per_day=6120, period_days=150, image="metearn9.png"),
            Product(sku="SKU-11", name="MetaEarn 10", price=None, income_per_day=None, period_days=None, image="metearn10.png"),
        ]
        db.session.add_all(products)
        db.session.commit()
        print("✅ Products seeded successfully!")
    else:
        print("⚠️ Products already exist, skipping seeding.")
