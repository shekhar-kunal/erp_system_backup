"""
management command: seed_data
Populates a fresh database with realistic medium-sized demo data.

Usage:
    python manage.py seed_data
"""

import random
from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rand_price(lo, hi):
    return Decimal(str(round(random.uniform(lo, hi), 2)))


def rand_date(days_ago_min, days_ago_max):
    offset = random.randint(days_ago_min, days_ago_max)
    return date.today() - timedelta(days=offset)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Seed the database with realistic demo data"

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Starting data seed…"))
        with transaction.atomic():
            self._seed_core()
            self._seed_config()
            self._seed_products()
            self._seed_inventory()
            self._seed_purchasing()
            self._seed_sales()
            self._seed_accounting()
        self.stdout.write(self.style.SUCCESS("✓ Seed complete."))

    # -----------------------------------------------------------------------
    # 1. Core — Countries / Regions / Cities
    # -----------------------------------------------------------------------

    def _seed_core(self):
        from core.models import Country, Region, City
        self.stdout.write("  → Core: countries, regions, cities")

        # Countries
        countries_data = [
            dict(name="United States", code="USA", iso_code="US",
                 phone_code="+1", currency="USD", currency_symbol="$",
                 default_timezone="America/New_York", position=1),
            dict(name="United Kingdom", code="GBR", iso_code="GB",
                 phone_code="+44", currency="GBP", currency_symbol="£",
                 default_timezone="Europe/London", position=2),
            dict(name="United Arab Emirates", code="ARE", iso_code="AE",
                 phone_code="+971", currency="AED", currency_symbol="د.إ",
                 default_timezone="Asia/Dubai", position=3),
            dict(name="Germany", code="DEU", iso_code="DE",
                 phone_code="+49", currency="EUR", currency_symbol="€",
                 default_timezone="Europe/Berlin", position=4),
            dict(name="India", code="IND", iso_code="IN",
                 phone_code="+91", currency="INR", currency_symbol="₹",
                 default_timezone="Asia/Kolkata", position=5),
        ]

        countries = {}
        for d in countries_data:
            obj, _ = Country.objects.update_or_create(
                iso_code=d["iso_code"],
                defaults={k: v for k, v in d.items() if k != "iso_code"},
            )
            countries[d["iso_code"]] = obj

        # Regions
        regions_raw = {
            "US": [
                ("California", "CA"), ("Texas", "TX"), ("New York", "NY"),
                ("Florida", "FL"), ("Illinois", "IL"),
            ],
            "GB": [
                ("England", "ENG"), ("Scotland", "SCO"), ("Wales", "WAL"),
            ],
            "AE": [
                ("Dubai", "DXB"), ("Abu Dhabi", "AUH"), ("Sharjah", "SHJ"),
            ],
            "DE": [
                ("Bavaria", "BY"), ("Berlin", "BE"), ("Hamburg", "HH"),
            ],
            "IN": [
                ("Maharashtra", "MH"), ("Karnataka", "KA"), ("Delhi", "DL"),
            ],
        }

        regions = {}
        for iso, raw_list in regions_raw.items():
            country = countries[iso]
            for name, code in raw_list:
                obj, _ = Region.objects.update_or_create(
                    name=name, country=country,
                    defaults={"code": code},
                )
                regions[(iso, name)] = obj

        # Cities
        cities_raw = {
            "US": [
                ("Los Angeles", "California", "CA", "90001"),
                ("San Francisco", "California", "CA", "94102"),
                ("Houston", "Texas", "TX", "77001"),
                ("Dallas", "Texas", "TX", "75201"),
                ("New York City", "New York", "NY", "10001"),
                ("Miami", "Florida", "FL", "33101"),
                ("Chicago", "Illinois", "IL", "60601"),
            ],
            "GB": [
                ("London", "England", "ENG", "EC1A"),
                ("Manchester", "England", "ENG", "M1"),
                ("Birmingham", "England", "ENG", "B1"),
                ("Edinburgh", "Scotland", "SCO", "EH1"),
                ("Cardiff", "Wales", "WAL", "CF10"),
            ],
            "AE": [
                ("Dubai", "Dubai", "DXB", "00000"),
                ("Abu Dhabi", "Abu Dhabi", "AUH", "00000"),
                ("Sharjah", "Sharjah", "SHJ", "00000"),
            ],
            "DE": [
                ("Munich", "Bavaria", "BY", "80331"),
                ("Berlin", "Berlin", "BE", "10115"),
                ("Hamburg", "Hamburg", "HH", "20095"),
            ],
            "IN": [
                ("Mumbai", "Maharashtra", "MH", "400001"),
                ("Pune", "Maharashtra", "MH", "411001"),
                ("Bangalore", "Karnataka", "KA", "560001"),
                ("New Delhi", "Delhi", "DL", "110001"),
            ],
        }

        self.cities = {}
        for iso, city_list in cities_raw.items():
            country = countries[iso]
            for city_name, region_name, region_code, postal in city_list:
                region = regions.get((iso, region_name))
                obj, _ = City.objects.update_or_create(
                    name=city_name, country=country, region=region,
                    defaults={"postal_code": postal},
                )
                self.cities[(iso, city_name)] = obj

        self.countries = countries
        self.regions = regions

    # -----------------------------------------------------------------------
    # 2. Config settings — Currency, PricingConfig
    # -----------------------------------------------------------------------

    def _seed_config(self):
        from config_settings.models import Currency, PricingConfig
        self.stdout.write("  → Config settings")

        currencies = [
            ("USD", "US Dollar", "$", 1.0),
            ("EUR", "Euro", "€", 0.92),
            ("GBP", "British Pound", "£", 0.79),
            ("AED", "UAE Dirham", "د.إ", 3.67),
            ("INR", "Indian Rupee", "₹", 83.5),
        ]
        for code, name, symbol, rate in currencies:
            Currency.objects.update_or_create(
                code=code,
                defaults={"name": name, "symbol": symbol,
                          "exchange_rate": Decimal(str(rate)), "is_active": True},
            )

        PricingConfig.objects.get_or_create(pk=1)

    # -----------------------------------------------------------------------
    # 3. Products — Units, Brands, Categories, Products, PriceLists
    # -----------------------------------------------------------------------

    def _seed_products(self):
        from products.models import (
            Unit, Brand, ProductCategory, Product, PriceList, ProductPrice,
        )
        self.stdout.write("  → Products")

        # --- Units ---
        units_data = [
            ("Piece", "pc", "PC", "standard"),
            ("Kilogram", "kg", "KG", "weight"),
            ("Gram", "g", "G", "weight"),
            ("Litre", "L", "L", "volume"),
            ("Millilitre", "mL", "ML", "volume"),
            ("Metre", "m", "M", "length"),
            ("Centimetre", "cm", "CM", "length"),
            ("Box", "box", "BOX", "packaging"),
            ("Carton", "ctn", "CTN", "packaging"),
            ("Dozen", "doz", "DOZ", "standard"),
            ("Pair", "pr", "PR", "standard"),
            ("Set", "set", "SET", "standard"),
        ]
        units = {}
        for name, short, code, utype in units_data:
            obj, _ = Unit.objects.update_or_create(
                code=code,
                defaults={"name": name, "short_name": short, "unit_type": utype, "is_active": True},
            )
            units[code] = obj

        # --- Brands ---
        brands_data = [
            ("TechCore", "techcore", "https://techcore.example.com", "Leading electronics brand"),
            ("FreshFoods", "freshfoods", "", "Premium organic food supplier"),
            ("ActiveWear", "activewear", "https://activewear.example.com", "Sports and fitness apparel"),
            ("HomeStyle", "homestyle", "", "Modern home furnishing solutions"),
            ("AutoParts Pro", "autopartspro", "https://autopartspro.example.com", "Automotive components"),
            ("GreenLeaf", "greenleaf", "", "Eco-friendly product range"),
        ]
        brands = {}
        for name, slug, website, desc in brands_data:
            obj, _ = Brand.objects.update_or_create(
                slug=slug,
                defaults={"name": name, "website": website,
                          "description": desc, "is_active": True},
            )
            brands[slug] = obj

        # --- Categories (MPTT) ---
        cat_tree = [
            ("Electronics", None),
            ("Smartphones", "Electronics"),
            ("Laptops", "Electronics"),
            ("Accessories", "Electronics"),
            ("Food & Beverages", None),
            ("Dairy", "Food & Beverages"),
            ("Snacks", "Food & Beverages"),
            ("Clothing", None),
            ("Men's Wear", "Clothing"),
            ("Women's Wear", "Clothing"),
            ("Home & Living", None),
            ("Kitchen", "Home & Living"),
            ("Automotive", None),
        ]
        categories = {}
        for cat_name, parent_name in cat_tree:
            parent = categories.get(parent_name)
            slug = slugify(cat_name)
            obj, _ = ProductCategory.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": cat_name,
                    "parent": parent,
                    "active": True,
                    "code": slug[:10].upper().replace("-", ""),
                },
            )
            categories[cat_name] = obj

        # --- Price Lists ---
        pl_retail, _ = PriceList.objects.update_or_create(
            code="RETAIL",
            defaults={
                "name": "Retail",
                "priority": 10,
                "discount_method": "none",
                "is_active": True,
                "is_default": True,
                "applicable_to_retail": True,
            },
        )
        pl_wholesale, _ = PriceList.objects.update_or_create(
            code="WHOLESALE",
            defaults={
                "name": "Wholesale",
                "priority": 20,
                "discount_method": "percentage",
                "default_discount_percentage": Decimal("10.00"),
                "is_active": True,
                "applicable_to_wholesale": True,
            },
        )
        pl_distributor, _ = PriceList.objects.update_or_create(
            code="DISTRIBUTOR",
            defaults={
                "name": "Distributor",
                "priority": 30,
                "discount_method": "percentage",
                "default_discount_percentage": Decimal("20.00"),
                "is_active": True,
                "applicable_to_distributor": True,
            },
        )

        # --- Products ---
        products_raw = [
            # (name, brand_slug, cat_name, unit_code, price, cost)
            ("iPhone 15 Pro", "techcore", "Smartphones", "PC", 999.99, 620.00),
            ("Samsung Galaxy S24", "techcore", "Smartphones", "PC", 849.99, 510.00),
            ("Google Pixel 9", "techcore", "Smartphones", "PC", 799.99, 480.00),
            ("MacBook Air M3", "techcore", "Laptops", "PC", 1299.99, 810.00),
            ("Dell XPS 15", "techcore", "Laptops", "PC", 1099.99, 680.00),
            ("Lenovo ThinkPad X1", "techcore", "Laptops", "PC", 1199.99, 750.00),
            ("USB-C Hub 7-in-1", "techcore", "Accessories", "PC", 49.99, 18.00),
            ("Wireless Charger 15W", "techcore", "Accessories", "PC", 29.99, 10.00),
            ("Bluetooth Keyboard", "techcore", "Accessories", "PC", 79.99, 32.00),
            ("Ergonomic Mouse", "techcore", "Accessories", "PC", 59.99, 22.00),
            ("Organic Whole Milk 1L", "freshfoods", "Dairy", "L", 1.49, 0.80),
            ("Greek Yoghurt 500g", "freshfoods", "Dairy", "G", 2.99, 1.40),
            ("Cheddar Cheese 400g", "freshfoods", "Dairy", "G", 4.49, 2.20),
            ("Granola Bars (Box 12)", "freshfoods", "Snacks", "BOX", 5.99, 2.80),
            ("Protein Chips 150g", "freshfoods", "Snacks", "G", 3.49, 1.50),
            ("Almonds 500g", "freshfoods", "Snacks", "G", 7.99, 4.20),
            ("Trail Mix 400g", "freshfoods", "Snacks", "G", 5.49, 2.60),
            ("Men's Running Shorts", "activewear", "Men's Wear", "PC", 34.99, 14.00),
            ("Men's Polo Shirt", "activewear", "Men's Wear", "PC", 44.99, 18.00),
            ("Men's Chino Pants", "activewear", "Men's Wear", "PC", 59.99, 24.00),
            ("Women's Yoga Leggings", "activewear", "Women's Wear", "PC", 49.99, 20.00),
            ("Women's Sports Bra", "activewear", "Women's Wear", "PC", 29.99, 12.00),
            ("Women's Running Jacket", "activewear", "Women's Wear", "PC", 79.99, 38.00),
            ("Non-stick Frying Pan 28cm", "homestyle", "Kitchen", "PC", 39.99, 16.00),
            ("Chef's Knife Set", "homestyle", "Kitchen", "SET", 89.99, 42.00),
            ("Bamboo Cutting Board", "homestyle", "Kitchen", "PC", 24.99, 9.00),
            ("Stainless Steel Kettle", "homestyle", "Kitchen", "PC", 44.99, 20.00),
            ("Ceramic Coffee Mug Set (4)", "homestyle", "Kitchen", "SET", 32.99, 12.00),
            ("Sofa 3-Seater", "homestyle", "Home & Living", "PC", 699.99, 350.00),
            ("Coffee Table", "homestyle", "Home & Living", "PC", 199.99, 90.00),
            ("Car Engine Oil 5W-30 5L", "autopartspro", "Automotive", "L", 39.99, 22.00),
            ("Air Filter Universal", "autopartspro", "Automotive", "PC", 24.99, 9.00),
            ("Spark Plugs (Set of 4)", "autopartspro", "Automotive", "SET", 19.99, 8.00),
            ("Brake Pads Front Set", "autopartspro", "Automotive", "SET", 59.99, 28.00),
            ("Windshield Washer Fluid 1L", "autopartspro", "Automotive", "L", 4.99, 1.80),
            ("Eco Laundry Detergent 2kg", "greenleaf", "Home & Living", "KG", 12.99, 5.50),
            ("Bamboo Toothbrush Pack 4", "greenleaf", "Home & Living", "PC", 9.99, 3.20),
            ("Organic Cotton Tote Bag", "greenleaf", "Accessories", "PC", 14.99, 5.00),
            ("Reusable Water Bottle 750mL", "greenleaf", "Accessories", "PC", 19.99, 7.50),
            ("Solar Power Bank 20000mAh", "greenleaf", "Accessories", "PC", 49.99, 22.00),
        ]

        self.products = []
        for name, brand_slug, cat_name, unit_code, price, cost in products_raw:
            brand = brands[brand_slug]
            category = categories[cat_name]
            unit = units[unit_code]
            slug = slugify(name)[:95]

            p, _ = Product.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "brand": brand,
                    "category": category,
                    "base_unit": unit,
                    "price": Decimal(str(price)),
                    "cost": Decimal(str(cost)),
                    "base_price": Decimal(str(price)),
                    "active": True,
                    "product_type": "simple",
                },
            )
            self.products.append(p)

            # Price list prices
            for pl, mult in [(pl_retail, Decimal("1.00")),
                             (pl_wholesale, Decimal("0.90")),
                             (pl_distributor, Decimal("0.80"))]:
                ProductPrice.objects.update_or_create(
                    product=p, price_list=pl,
                    defaults={"price": (p.price * mult).quantize(Decimal("0.01"))},
                )

        self.units = units
        self.stdout.write(f"    {len(self.products)} products created")

    # -----------------------------------------------------------------------
    # 4. Inventory — Warehouses, Sections, Stock
    # -----------------------------------------------------------------------

    def _seed_inventory(self):
        from inventory.models import Warehouse, WarehouseSection, Stock, InventorySettings
        self.stdout.write("  → Inventory")

        InventorySettings.objects.get_or_create(pk=1)

        wh_main, _ = Warehouse.objects.update_or_create(
            code="WH-MAIN",
            defaults={
                "name": "Main Warehouse",
                "address": "100 Industrial Blvd, Los Angeles, CA 90001",
                "is_active": True,
                "is_default": True,
            },
        )
        wh_secondary, _ = Warehouse.objects.update_or_create(
            code="WH-SEC",
            defaults={
                "name": "Secondary Warehouse",
                "address": "500 Commerce St, Houston, TX 77001",
                "is_active": True,
                "is_default": False,
            },
        )

        sections_main = []
        for name, code in [("Aisle A", "A"), ("Aisle B", "B"),
                            ("Cold Storage", "CS"), ("Bulk Storage", "BLK")]:
            s, _ = WarehouseSection.objects.update_or_create(
                warehouse=wh_main, code=code,
                defaults={"name": name, "is_active": True},
            )
            sections_main.append(s)

        sections_sec = []
        for name, code in [("Zone 1", "Z1"), ("Zone 2", "Z2")]:
            s, _ = WarehouseSection.objects.update_or_create(
                warehouse=wh_secondary, code=code,
                defaults={"name": name, "is_active": True},
            )
            sections_sec.append(s)

        # Seed stock for each product in main warehouse
        unit = self.units["PC"]
        for product in self.products:
            qty = random.randint(10, 200)
            Stock.objects.update_or_create(
                product=product,
                warehouse=wh_main,
                section=sections_main[0],
                defaults={
                    "quantity": qty,
                    "unit": product.base_unit,
                    "unit_quantity": 1,
                    "min_quantity": 5,
                    "reorder_point": 10,
                },
            )

        self.warehouse = wh_main
        self.warehouse_secondary = wh_secondary

    # -----------------------------------------------------------------------
    # 5. Purchasing — Vendors + Purchase Orders
    # -----------------------------------------------------------------------

    def _seed_purchasing(self):
        from purchasing.models import Vendor, PurchaseOrder, PurchaseOrderLine, PurchasingSettings
        self.stdout.write("  → Purchasing")

        PurchasingSettings.objects.get_or_create(pk=1)

        # Vendors need Country+City from core
        us = self.countries["US"]
        gb = self.countries["GB"]
        ae = self.countries["AE"]
        de = self.countries["DE"]

        la = self.cities[("US", "Los Angeles")]
        lon = self.cities[("GB", "London")]
        dubai = self.cities[("AE", "Dubai")]
        munich = self.cities[("DE", "Munich")]
        houston = self.cities[("US", "Houston")]

        vendors_data = [
            ("Alpha Electronics Ltd", "VND-001", "sarah.jones@alphaelec.com",
             "+1-310-555-0101", "200 Tech Drive", us, self.regions.get(("US","California")), la, "90010"),
            ("Global Organics Co", "VND-002", "procurement@globalorganics.com",
             "+44-20-7946-0958", "15 Organic Lane", gb, self.regions.get(("GB","England")), lon, "EC2A 1QW"),
            ("Gulf Trade FZCO", "VND-003", "orders@gulftrade.ae",
             "+971-4-555-0200", "Unit 7, Dubai Logistics Park", ae, self.regions.get(("AE","Dubai")), dubai, "00000"),
            ("TechSupply GmbH", "VND-004", "supply@techsupply.de",
             "+49-89-555-0300", "Industriestrasse 45", de, self.regions.get(("DE","Bavaria")), munich, "80339"),
            ("StateSide Parts LLC", "VND-005", "info@statesideparts.com",
             "+1-713-555-0404", "800 Commerce Ave", us, self.regions.get(("US","Texas")), houston, "77002"),
        ]

        vendors = []
        for name, code, email, phone, addr, country, region, city, postal in vendors_data:
            v, _ = Vendor.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "address_line1": addr,
                    "country": country,
                    "region": region,
                    "city": city,
                    "postal_code": postal,
                    "is_active": True,
                    "payment_terms": "net30",
                    "credit_limit": Decimal("50000.00"),
                },
            )
            vendors.append(v)

        # Purchase orders — mix of statuses
        statuses = ["done", "done", "done", "partial", "confirmed", "draft"]
        for i, vendor in enumerate(vendors):
            for j in range(2):
                status = statuses[(i + j) % len(statuses)]
                po = PurchaseOrder.objects.create(
                    vendor=vendor,
                    warehouse=self.warehouse,
                    status=status,
                    payment_terms="net30",
                )
                # Add 3-5 lines
                sample = random.sample(self.products, k=random.randint(3, 5))
                for prod in sample:
                    qty = Decimal(str(random.randint(5, 50)))
                    price = prod.cost * Decimal("1.05")  # slight markup from cost
                    received = qty if status == "done" else (qty / 2 if status == "partial" else Decimal("0"))
                    PurchaseOrderLine.objects.create(
                        order=po,
                        product=prod,
                        unit=prod.base_unit,
                        quantity=qty,
                        price=price.quantize(Decimal("0.01")),
                        received_quantity=received,
                    )
                po.calculate_totals()
                PurchaseOrder.objects.filter(pk=po.pk).update(
                    subtotal=po.subtotal,
                    total_amount=po.total_amount,
                )

        self.stdout.write(f"    {len(vendors)} vendors, {PurchaseOrder.objects.count()} purchase orders")

    # -----------------------------------------------------------------------
    # 6. Sales — Customers + Sales Orders + Lines
    # -----------------------------------------------------------------------

    def _seed_sales(self):
        from sales.models import Customer, SalesOrder, SalesOrderLine, SalesSettings
        self.stdout.write("  → Sales")

        SalesSettings.objects.get_or_create(pk=1)

        us = self.countries["US"]
        gb = self.countries["GB"]
        ae = self.countries["AE"]

        nyc = self.cities[("US", "New York City")]
        sf = self.cities[("US", "San Francisco")]
        chi = self.cities[("US", "Chicago")]
        lon = self.cities[("GB", "London")]
        man = self.cities[("GB", "Manchester")]
        dubai = self.cities[("AE", "Dubai")]
        miami = self.cities[("US", "Miami")]

        ny_region = self.regions.get(("US", "New York"))
        ca_region = self.regions.get(("US", "California"))
        il_region = self.regions.get(("US", "Illinois"))
        fl_region = self.regions.get(("US", "Florida"))
        eng_region = self.regions.get(("GB", "England"))
        dxb_region = self.regions.get(("AE", "Dubai"))

        customers_data = [
            # (type, first, last, company, email, phone, addr, country, region, city, postal, tier, credit_limit, credit_days)
            ("individual", "James", "Wilson", "", "james.wilson@email.com",
             "+1-212-555-0101", "45 Park Avenue", us, ny_region, nyc, "10022",
             "retail", 0, 0),
            ("individual", "Emily", "Chen", "", "emily.chen@email.com",
             "+1-415-555-0202", "12 Market Street", us, ca_region, sf, "94105",
             "retail", 0, 0),
            ("business", "Robert", "Johnson", "Johnson Trading Co", "rjohnson@johnsontrading.com",
             "+1-312-555-0303", "100 Michigan Ave", us, il_region, chi, "60601",
             "wholesale", 25000, 30),
            ("business", "Sarah", "Ahmed", "Gulf Retail LLC", "s.ahmed@gulfretail.ae",
             "+971-4-555-0404", "Sheikh Zayed Road, Tower B", ae, dxb_region, dubai, "00000",
             "distributor", 50000, 45),
            ("individual", "Michael", "Brown", "", "m.brown@email.com",
             "+44-20-7946-0505", "25 Oxford Street", gb, eng_region, lon, "W1C 2JL",
             "retail", 0, 0),
            ("business", "Linda", "Taylor", "Taylor Imports Ltd", "ltaylor@taylorimports.co.uk",
             "+44-161-555-0606", "33 King Street", gb, eng_region, man, "M2 4LQ",
             "wholesale", 30000, 30),
            ("individual", "David", "Martinez", "", "d.martinez@email.com",
             "+1-305-555-0707", "888 Brickell Ave", us, fl_region, miami, "33131",
             "retail", 0, 0),
            ("business", "Priya", "Sharma", "Sharma Distributors", "priya@sharmagroup.com",
             "+971-4-555-0808", "DAFZA Warehouse 22", ae, dxb_region, dubai, "00000",
             "distributor", 75000, 60),
            ("individual", "Thomas", "Clark", "", "t.clark@email.com",
             "+1-212-555-0909", "220 East 42nd St", us, ny_region, nyc, "10017",
             "retail", 0, 0),
            ("business", "Anna", "Mueller", "Mueller GmbH Partners", "anna@muellerpartners.com",
             "+44-20-7946-1010", "12 Canary Wharf", gb, eng_region, lon, "E14 5AB",
             "wholesale", 20000, 30),
        ]

        customers = []
        for i, row in enumerate(customers_data, 1):
            (ctype, first, last, company, email, phone, addr,
             country, region, city, postal, tier, credit_limit, credit_days) = row

            full_name = f"{first} {last}".strip() if ctype == "individual" else company
            code = f"CUST-{i:04d}"

            c, _ = Customer.objects.update_or_create(
                email=email,
                defaults={
                    "customer_type": ctype,
                    "first_name": first,
                    "last_name": last,
                    "full_name": full_name,
                    "company_name": company,
                    "phone": phone,
                    "billing_address_line1": addr,
                    "billing_country": country,
                    "billing_region": region,
                    "billing_city": city,
                    "billing_postal_code": postal,
                    "same_as_billing": True,
                    "customer_code": code,
                    "pricing_tier": tier,
                    "payment_type": "credit" if credit_limit > 0 else "pay_now",
                    "credit_limit": Decimal(str(credit_limit)),
                    "credit_days": credit_days,
                    "is_active": True,
                },
            )
            customers.append(c)

        # Sales Orders
        so_statuses = [
            "confirmed", "confirmed", "shipped", "shipped",
            "delivered", "delivered", "invoiced", "cancelled", "draft", "draft",
        ]
        for i, customer in enumerate(customers):
            for j in range(random.randint(2, 4)):
                status = so_statuses[(i * 3 + j) % len(so_statuses)]
                order_date = rand_date(5, 180)
                so = SalesOrder.objects.create(
                    customer=customer,
                    warehouse=self.warehouse,
                    status=status,
                    order_date=order_date,
                    expected_delivery=order_date + timedelta(days=random.randint(3, 14)),
                    currency=customer.default_currency,
                )
                # 2-5 lines
                sample = random.sample(self.products, k=random.randint(2, 5))
                for prod in sample:
                    qty = Decimal(str(random.randint(1, 20)))
                    SalesOrderLine.objects.create(
                        order=so,
                        product=prod,
                        quantity=qty,
                        unit_price=prod.price,
                        discount_percent=Decimal("0.00"),
                    )
                so.calculate_totals()
                SalesOrder.objects.filter(pk=so.pk).update(
                    subtotal=so.subtotal,
                    total_amount=so.total_amount,
                )

        self.stdout.write(
            f"    {len(customers)} customers, {SalesOrder.objects.count()} sales orders"
        )

    # -----------------------------------------------------------------------
    # 7. Accounting — Chart of Accounts, Settings, FiscalYear + Periods
    # -----------------------------------------------------------------------

    def _seed_accounting(self):
        from accounting.models import Account, AccountingSettings, FiscalYear, FiscalPeriod
        self.stdout.write("  → Accounting")

        # Chart of Accounts (from STANDARD_ACCOUNTS list on the model)
        for code, name, acc_type, is_active, currency in Account.STANDARD_ACCOUNTS:
            Account.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "type": acc_type,
                    "is_active": is_active,
                    "is_system": True,
                    "currency": currency,
                    "normal_balance": Account.NORMAL_BALANCE[acc_type],
                },
            )

        # AccountingSettings singleton
        ar_acc = Account.objects.filter(code="1100").first()
        ap_acc = Account.objects.filter(code="2000").first()
        sales_acc = Account.objects.filter(code="4000").first()
        cash_acc = Account.objects.filter(code="1000").first()
        purchase_acc = Account.objects.filter(code="5400").first()

        AccountingSettings.objects.update_or_create(
            pk=1,
            defaults={
                "default_ar_account": ar_acc,
                "default_ap_account": ap_acc,
                "default_sales_account": sales_acc,
                "default_cash_account": cash_acc,
                "default_purchase_account": purchase_acc,
                "enable_auto_posting": True,
                "require_approval": False,
                "fiscal_year_start_month": 1,
            },
        )

        # Fiscal Year (current calendar year)
        today = date.today()
        fy_start = date(today.year, 1, 1)
        fy_end = date(today.year, 12, 31)
        fy, _ = FiscalYear.objects.update_or_create(
            start_date=fy_start,
            end_date=fy_end,
            defaults={"name": f"FY {today.year}", "is_closed": False},
        )

        # 12 monthly periods
        import calendar as cal
        for month in range(1, 13):
            last_day = cal.monthrange(today.year, month)[1]
            p_start = date(today.year, month, 1)
            p_end = date(today.year, month, last_day)
            is_closed = p_end < today.replace(day=1)  # past months are closed
            FiscalPeriod.objects.update_or_create(
                fiscal_year=fy,
                period_number=month,
                defaults={
                    "period_type": "monthly",
                    "start_date": p_start,
                    "end_date": p_end,
                    "is_closed": is_closed,
                },
            )

        self.stdout.write(
            f"    {Account.objects.count()} accounts, "
            f"FY {today.year} with 12 periods"
        )
