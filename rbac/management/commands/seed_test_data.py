"""
Management command: seed_test_data
===================================
Clears all transactional ERP data and re-seeds comprehensive test data.

Preserved (never touched):
  - Superuser accounts
  - ExportConfig records
  - Countries / Regions / Cities
  - Currencies

Seeded (created with get_or_create — safe to re-run):
  - Units (products.Unit) — 10 common units always created

Run:
  python manage.py seed_test_data [--yes]
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

User = get_user_model()

PASSWORD = "Test@12345"

# ---------------------------------------------------------------------------
# Static seed data
# ---------------------------------------------------------------------------

# (name, parent_key_or_None, slug_key)
CATEGORY_SEED = [
    ("Electronics",           None,            "electronics"),
    ("Laptops & Computers",   "electronics",   "laptops"),
    ("Smartphones & Tablets", "electronics",   "smartphones"),
    ("Audio & Video",         "electronics",   "audio-video"),
    ("Computer Accessories",  "electronics",   "accessories"),
    ("Office & Furniture",    None,            "office"),
    ("Office Furniture",      "office",        "furniture"),
    ("Stationery & Supplies", "office",        "stationery"),
    ("Networking",            None,            "networking"),
    ("Storage Solutions",     None,            "storage"),
]

# (name, brands_it_supplies)
BRAND_SEED = [
    "TechBrand", "AudioPro", "StorageCo", "OfficeWorld",
    "PrintTech", "NetGear", "MobileTech", "DataSystems",
]

# (code, name, brand_name, description)
MODEL_NUMBER_SEED = [
    ("TBL-14PRO", "Laptop 14\" Pro Series",        "TechBrand",   "Business laptop line"),
    ("TBL-15DEV", "Laptop 15\" Developer Series",  "TechBrand",   "Developer workstation line"),
    ("MBSP-ENT",  "Enterprise Smartphone",          "MobileTech",  "Enterprise mobile series"),
    ("MBSP-BIZ",  "Business Smartphone",            "MobileTech",  "Business mobile series"),
    ("APH-NC50",  "Noise-Cancel Headset 50",        "AudioPro",    "Flagship noise-cancel series"),
    ("SC-SSD-1T", "SSD 1TB Series",                 "StorageCo",   "Portable SSD line"),
    ("SC-NAS-4B", "NAS 4-Bay Series",               "StorageCo",   "4-Bay NAS line"),
    ("NG-SW24",   "Switch 24-Port Series",          "NetGear",     "Managed switch line"),
    ("NG-UPS15",  "UPS 1500VA Series",              "NetGear",     "UPS power backup line"),
    ("OW-ERGO",   "Ergonomic Chair Series",         "OfficeWorld", "Ergonomic office seating"),
]

# (name, category_key, brand_name, model_code_or_None, price, cost)
PRODUCT_SEED = [
    # Laptops & Computers
    ("Business Laptop 14\"",      "laptops",     "TechBrand",   "TBL-14PRO", Decimal("1199.00"), Decimal("780.00")),
    ("Developer Laptop 15\"",     "laptops",     "TechBrand",   "TBL-15DEV", Decimal("1499.00"), Decimal("980.00")),
    ("Gaming Laptop 17\"",        "laptops",     "TechBrand",   None,        Decimal("1899.00"), Decimal("1200.00")),
    ("Desktop Mini PC",           "laptops",     "TechBrand",   None,        Decimal("449.00"),  Decimal("280.00")),
    ("All-in-One Computer 24\"",  "laptops",     "TechBrand",   None,        Decimal("899.00"),  Decimal("580.00")),
    ("Workstation Tower",         "laptops",     "DataSystems", None,        Decimal("2499.00"), Decimal("1600.00")),
    ("Budget Laptop 13\"",        "laptops",     "TechBrand",   None,        Decimal("649.00"),  Decimal("420.00")),
    ("Ultrabook 13\" Pro",        "laptops",     "TechBrand",   None,        Decimal("1299.00"), Decimal("840.00")),
    # Smartphones & Tablets
    ("Enterprise Smartphone Pro", "smartphones", "MobileTech",  "MBSP-ENT",  Decimal("999.00"),  Decimal("620.00")),
    ("Business Smartphone",       "smartphones", "MobileTech",  "MBSP-BIZ",  Decimal("699.00"),  Decimal("430.00")),
    ("Budget Smartphone",         "smartphones", "MobileTech",  None,        Decimal("299.00"),  Decimal("180.00")),
    ("Business Tablet 10\"",      "smartphones", "MobileTech",  None,        Decimal("549.00"),  Decimal("340.00")),
    ("Professional Tablet 12\"",  "smartphones", "MobileTech",  None,        Decimal("749.00"),  Decimal("460.00")),
    ("Industrial Tablet Rugged",  "smartphones", "DataSystems", None,        Decimal("1299.00"), Decimal("820.00")),
    # Audio & Video
    ("Noise-Cancelling Headset",  "audio-video", "AudioPro",    "APH-NC50",  Decimal("249.00"),  Decimal("130.00")),
    ("Conference Speaker System", "audio-video", "AudioPro",    None,        Decimal("349.00"),  Decimal("180.00")),
    ("Wireless Earbuds Pro",      "audio-video", "AudioPro",    None,        Decimal("149.00"),  Decimal("75.00")),
    ("USB Desktop Microphone",    "audio-video", "AudioPro",    None,        Decimal("89.00"),   Decimal("42.00")),
    ("Video Conference Camera 4K","audio-video", "AudioPro",    None,        Decimal("299.00"),  Decimal("155.00")),
    ("Portable Bluetooth Speaker","audio-video", "AudioPro",    None,        Decimal("119.00"),  Decimal("58.00")),
    # Computer Accessories
    ("Wireless Mouse Ergonomic",  "accessories", "TechBrand",   None,        Decimal("49.99"),   Decimal("22.00")),
    ("Mechanical Keyboard",       "accessories", "TechBrand",   None,        Decimal("89.99"),   Decimal("45.00")),
    ("USB-C Hub 7-Port",          "accessories", "TechBrand",   None,        Decimal("49.99"),   Decimal("22.00")),
    ("27\" 4K Monitor",           "accessories", "TechBrand",   None,        Decimal("599.00"),  Decimal("380.00")),
    ("24\" Full HD Monitor",      "accessories", "TechBrand",   None,        Decimal("299.00"),  Decimal("190.00")),
    ("Webcam HD 1080p",           "accessories", "TechBrand",   None,        Decimal("89.99"),   Decimal("45.00")),
    ("Docking Station Pro",       "accessories", "TechBrand",   None,        Decimal("199.00"),  Decimal("105.00")),
    ("HDMI Cable 2m (3-Pack)",    "accessories", "TechBrand",   None,        Decimal("29.99"),   Decimal("10.00")),
    ("Mouse Pad XL",              "accessories", "TechBrand",   None,        Decimal("39.99"),   Decimal("15.00")),
    ("USB-A Hub 4-Port",          "accessories", "TechBrand",   None,        Decimal("24.99"),   Decimal("8.00")),
    # Office Furniture
    ("Office Chair Ergonomic",    "furniture",   "OfficeWorld", "OW-ERGO",   Decimal("399.00"),  Decimal("210.00")),
    ("Standing Desk Electric",    "furniture",   "OfficeWorld", None,        Decimal("649.00"),  Decimal("380.00")),
    ("Height-Adjustable Desk",    "furniture",   "OfficeWorld", None,        Decimal("449.00"),  Decimal("260.00")),
    ("Filing Cabinet 4-Drawer",   "furniture",   "OfficeWorld", None,        Decimal("329.00"),  Decimal("180.00")),
    ("Bookshelf Office Grade",    "furniture",   "OfficeWorld", None,        Decimal("199.00"),  Decimal("95.00")),
    # Stationery & Supplies
    ("Printer Laser Mono",        "stationery",  "PrintTech",   None,        Decimal("199.00"),  Decimal("110.00")),
    ("Inkjet Photo Printer",      "stationery",  "PrintTech",   None,        Decimal("149.00"),  Decimal("78.00")),
    ("Label Printer",             "stationery",  "PrintTech",   None,        Decimal("199.00"),  Decimal("95.00")),
    ("Barcode Scanner Wireless",  "stationery",  "NetGear",     None,        Decimal("129.00"),  Decimal("60.00")),
    # Networking
    ("Network Switch 24-Port",    "networking",  "NetGear",     "NG-SW24",   Decimal("189.00"),  Decimal("95.00")),
    ("Network Switch 48-Port",    "networking",  "NetGear",     None,        Decimal("349.00"),  Decimal("190.00")),
    ("Wireless Access Point Pro", "networking",  "NetGear",     None,        Decimal("179.00"),  Decimal("90.00")),
    ("UPS Battery 1500VA",        "networking",  "NetGear",     "NG-UPS15",  Decimal("159.00"),  Decimal("85.00")),
    ("UPS Battery 3000VA",        "networking",  "NetGear",     None,        Decimal("299.00"),  Decimal("160.00")),
    ("Server Rack 12U",           "networking",  "NetGear",     None,        Decimal("499.00"),  Decimal("260.00")),
    ("Projector Full HD",         "stationery",  "PrintTech",   None,        Decimal("799.00"),  Decimal("450.00")),
    # Storage Solutions
    ("NAS Server 4-Bay",          "storage",     "StorageCo",   "SC-NAS-4B", Decimal("499.00"),  Decimal("280.00")),
    ("External SSD 1TB",          "storage",     "StorageCo",   "SC-SSD-1T", Decimal("119.00"),  Decimal("70.00")),
    ("External SSD 2TB",          "storage",     "StorageCo",   None,        Decimal("199.00"),  Decimal("115.00")),
    ("External HDD 4TB",          "storage",     "StorageCo",   None,        Decimal("129.00"),  Decimal("65.00")),
    ("NAS Server 8-Bay",          "storage",     "StorageCo",   None,        Decimal("899.00"),  Decimal("520.00")),
    # ---- More Laptops & Computers (indices 51-60) ----
    ("Chromebook 11\" Education",   "laptops",     "TechBrand",   None,        Decimal("349.00"),  Decimal("210.00")),
    ("Server Tower Rack-Mount",     "laptops",     "DataSystems", None,        Decimal("3999.00"), Decimal("2400.00")),
    ("Thin Client Terminal",        "laptops",     "DataSystems", None,        Decimal("249.00"),  Decimal("140.00")),
    ("Convertible Laptop 2-in-1",   "laptops",     "TechBrand",   None,        Decimal("999.00"),  Decimal("640.00")),
    ("NUC Mini PC Pro",             "laptops",     "DataSystems", None,        Decimal("599.00"),  Decimal("370.00")),
    ("Rugged Laptop Military",      "laptops",     "DataSystems", None,        Decimal("2299.00"), Decimal("1450.00")),
    ("Desktop Business PC",         "laptops",     "TechBrand",   None,        Decimal("749.00"),  Decimal("480.00")),
    ("Raspberry Pi 5 Dev Kit",      "laptops",     "DataSystems", None,        Decimal("129.00"),  Decimal("65.00")),
    ("Fanless Industrial PC",       "laptops",     "DataSystems", None,        Decimal("1499.00"), Decimal("950.00")),
    ("Laptop Docking Station Elite","laptops",     "TechBrand",   None,        Decimal("349.00"),  Decimal("195.00")),
    # ---- More Smartphones & Tablets (indices 61-66) ----
    ("Smartphone Entry Level",      "smartphones", "MobileTech",  None,        Decimal("199.00"),  Decimal("110.00")),
    ("Tablet 8\" Compact",          "smartphones", "MobileTech",  None,        Decimal("349.00"),  Decimal("200.00")),
    ("Rugged Smartphone IP68",      "smartphones", "DataSystems", None,        Decimal("899.00"),  Decimal("560.00")),
    ("POS Terminal Tablet",         "smartphones", "DataSystems", None,        Decimal("699.00"),  Decimal("430.00")),
    ("Drawing Tablet 15\"",         "smartphones", "MobileTech",  None,        Decimal("449.00"),  Decimal("270.00")),
    ("E-Reader Business 7\"",       "smartphones", "MobileTech",  None,        Decimal("249.00"),  Decimal("140.00")),
    # ---- More Audio & Video (indices 67-72) ----
    ("Smart TV 43\" 4K",            "audio-video", "AudioPro",    None,        Decimal("699.00"),  Decimal("420.00")),
    ("Wired Headphones Studio",     "audio-video", "AudioPro",    None,        Decimal("129.00"),  Decimal("62.00")),
    ("Soundbar 2.1 System",         "audio-video", "AudioPro",    None,        Decimal("299.00"),  Decimal("155.00")),
    ("Video Capture Card USB",      "audio-video", "AudioPro",    None,        Decimal("179.00"),  Decimal("88.00")),
    ("Ring Light 18\" LED",         "audio-video", "AudioPro",    None,        Decimal("89.00"),   Decimal("38.00")),
    ("HDMI Splitter 4-Port",        "audio-video", "AudioPro",    None,        Decimal("59.00"),   Decimal("24.00")),
    # ---- More Computer Accessories (indices 73-82) ----
    ("Laptop Stand Aluminium",      "accessories", "TechBrand",   None,        Decimal("59.99"),   Decimal("25.00")),
    ("USB-C to HDMI Adapter",       "accessories", "TechBrand",   None,        Decimal("29.99"),   Decimal("10.00")),
    ("Screen Cleaner Kit",          "accessories", "TechBrand",   None,        Decimal("19.99"),   Decimal("6.00")),
    ("Cable Management Kit",        "accessories", "TechBrand",   None,        Decimal("34.99"),   Decimal("12.00")),
    ("Wireless Ergonomic Keyboard", "accessories", "TechBrand",   None,        Decimal("99.99"),   Decimal("52.00")),
    ("Trackball Mouse Pro",         "accessories", "TechBrand",   None,        Decimal("79.99"),   Decimal("38.00")),
    ("GPU Card Professional 8GB",   "accessories", "DataSystems", None,        Decimal("799.00"),  Decimal("510.00")),
    ("Portable Battery Bank 20Ah",  "accessories", "TechBrand",   None,        Decimal("69.99"),   Decimal("32.00")),
    ("Anti-Glare Screen Filter 24", "accessories", "TechBrand",   None,        Decimal("39.99"),   Decimal("16.00")),
    ("Drawing Tablet Pen Pro",      "accessories", "TechBrand",   None,        Decimal("129.00"),  Decimal("65.00")),
    # ---- More Office Furniture (indices 83-86) ----
    ("Reception Desk Executive",    "furniture",   "OfficeWorld", None,        Decimal("1299.00"), Decimal("720.00")),
    ("Conference Table 8-Person",   "furniture",   "OfficeWorld", None,        Decimal("899.00"),  Decimal("500.00")),
    ("Monitor Arm Dual",            "furniture",   "OfficeWorld", None,        Decimal("149.00"),  Decimal("72.00")),
    ("Storage Cabinet Lockable",    "furniture",   "OfficeWorld", None,        Decimal("279.00"),  Decimal("145.00")),
    # ---- More Stationery & Supplies (indices 87-92) ----
    ("Toner Cartridge Black",       "stationery",  "PrintTech",   None,        Decimal("89.00"),   Decimal("40.00")),
    ("Paper A4 Box 5 Reams",        "stationery",  "OfficeWorld", None,        Decimal("39.99"),   Decimal("18.00")),
    ("Whiteboard Markers Set 12",   "stationery",  "OfficeWorld", None,        Decimal("24.99"),   Decimal("9.00")),
    ("Desk Organizer Premium",      "stationery",  "OfficeWorld", None,        Decimal("49.99"),   Decimal("20.00")),
    ("Document Scanner A4",         "stationery",  "PrintTech",   None,        Decimal("499.00"),  Decimal("290.00")),
    ("Thermal Receipt Printer",     "stationery",  "PrintTech",   None,        Decimal("249.00"),  Decimal("130.00")),
    # ---- More Networking (indices 93-98) ----
    ("Business VPN Router",         "networking",  "NetGear",     None,        Decimal("299.00"),  Decimal("158.00")),
    ("Firewall Appliance 1Gbps",    "networking",  "NetGear",     None,        Decimal("799.00"),  Decimal("460.00")),
    ("PoE Switch 8-Port",           "networking",  "NetGear",     None,        Decimal("149.00"),  Decimal("78.00")),
    ("Network Cable Cat6 305m",     "networking",  "NetGear",     None,        Decimal("89.00"),   Decimal("38.00")),
    ("IP Camera 4MP PTZ",           "networking",  "NetGear",     None,        Decimal("299.00"),  Decimal("158.00")),
    ("VoIP IP Phone",               "networking",  "NetGear",     None,        Decimal("129.00"),  Decimal("62.00")),
    # ---- More Storage Solutions (indices 99-104) ----
    ("USB Flash Drive 64GB 10-Pack","storage",     "StorageCo",   None,        Decimal("79.99"),   Decimal("35.00")),
    ("Memory Card 128GB UHS-II",    "storage",     "StorageCo",   None,        Decimal("49.99"),   Decimal("22.00")),
    ("RAID Controller PCIe",        "storage",     "StorageCo",   None,        Decimal("299.00"),  Decimal("165.00")),
    ("NAS Server 2-Bay",            "storage",     "StorageCo",   None,        Decimal("249.00"),  Decimal("140.00")),
    ("External DVD Writer USB",     "storage",     "StorageCo",   None,        Decimal("59.99"),   Decimal("25.00")),
    ("Portable SSD 512GB",          "storage",     "StorageCo",   "SC-SSD-1T", Decimal("89.00"),   Decimal("48.00")),
]

# (display_name, email, ctype, address, credit_limit, credit_days, payment_type)
CUSTOMER_SEED = [
    ("Alice Johnson",        "alice@example.com",       "individual", "12 Oak Street",        Decimal("5000"),  30, "credit"),
    ("Bob Smith Ltd",        "bob@bsmith.com",           "business",   "456 Commerce Ave",     Decimal("20000"), 30, "credit"),
    ("Carol Davis",          "carol@cdavis.com",         "individual", "789 Pine Road",        Decimal("3000"),  15, "credit"),
    ("Delta Corp",           "info@deltacorp.com",       "business",   "1 Corporate Plaza",    Decimal("50000"), 45, "credit"),
    ("Echo Enterprises",     "contact@echo.com",         "business",   "20 Business Park",     Decimal("30000"), 30, "credit"),
    ("Frank Industries Ltd", "frank@industries.com",     "business",   "88 Factory Street",    Decimal("40000"), 45, "credit"),
    ("Grace Solutions",      "info@gracesolutions.com",  "business",   "33 Innovation Drive",  Decimal("25000"), 30, "credit"),
    ("Henry Trading",        "henry@trading.com",        "individual", "5 Market Lane",        Decimal("8000"),  15, "credit"),
    ("Iris Technologies",    "iris@iristech.com",        "business",   "200 Tech Boulevard",   Decimal("60000"), 60, "credit"),
    ("Jack & Co",            "jack@jackco.com",          "business",   "77 South Road",        Decimal("15000"), 30, "credit"),
    ("Karen Mitchell",       "karen@mitchell.com",       "individual", "14 Elm Grove",         Decimal("4000"),  15, "credit"),
    ("Leo Business Solns",   "leo@leobiz.com",           "business",   "55 Commerce Centre",   Decimal("35000"), 45, "credit"),
    ("Maria Office Supplies","maria@mariaoffice.com",    "business",   "99 Trade Street",      Decimal("20000"), 30, "credit"),
    ("Nathan Electronics",   "nathan@nathanelec.com",    "business",   "150 Electronics Row",  Decimal("45000"), 45, "credit"),
    ("Olivia Consulting",    "olivia@olivia.com",        "business",   "22 Consulting Park",   Decimal("12000"), 30, "credit"),
]

# (name, code, email, address, payment_terms, category_hint)
VENDOR_SEED = [
    ("Tech Distributors Inc", "TDI", "tdi@vendor.com",     "10 Tech Drive",      "net30", "electronics"),
    ("Office Supplies Co",    "OSC", "osc@vendor.com",     "25 Supply Lane",     "net45", "office"),
    ("Global Electronics",    "GEL", "gel@vendor.com",     "50 Electronics Blvd","net30", "electronics+networking"),
    ("Furniture Depot",       "FRD", "frd@vendor.com",     "33 Factory Road",    "net60", "furniture"),
    ("Network Solutions Ltd", "NSL", "nsl@vendor.com",     "18 Network Park",    "net30", "networking"),
    ("StoragePro Ltd",        "SPL", "spl@vendor.com",     "77 Storage Ave",     "net30", "storage"),
    ("Mobile Direct",         "MBD", "mbd@vendor.com",     "44 Mobile Street",   "net45", "mobile"),
    ("Computing Solutions",   "CSL", "csl@vendor.com",     "12 Silicon Way",     "net30", "laptops"),
]

# (name, code, short_name, unit_type)
UNIT_SEED = [
    ("Each",     "EA",  "ea",   "standard"),
    ("Box",      "BOX", "box",  "packaging"),
    ("Pack",     "PCK", "pck",  "packaging"),
    ("Set",      "SET", "set",  "packaging"),
    ("Pair",     "PR",  "pr",   "packaging"),
    ("Ream",     "RM",  "rm",   "packaging"),
    ("Roll",     "RL",  "rl",   "packaging"),
    ("Kilogram", "KG",  "kg",   "weight"),
    ("Meter",    "M",   "m",    "length"),
    ("License",  "LIC", "lic",  "standard"),
]


class Command(BaseCommand):
    help = "Clear transactional data and seed comprehensive test data for the ERP."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes", action="store_true",
            help="Skip the confirmation prompt.",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            confirm = input(
                "\nWARNING: This will DELETE all transactional data and re-seed test data.\n"
                "Preserved: superuser accounts, ExportConfig, Countries, Currencies, Units.\n"
                "Type 'yes' to continue: "
            )
            if confirm.strip().lower() != "yes":
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        with transaction.atomic():
            self.stdout.write(self.style.HTTP_INFO("\n[1/5] Clearing data..."))
            self._clear_data()

            self.stdout.write(self.style.HTTP_INFO("\n[2/5] Seeding RBAC..."))
            warehouses = self._seed_rbac()

            self.stdout.write(self.style.HTTP_INFO("\n[3/5] Seeding products & pricing..."))
            products, price_lists = self._seed_products()

            self.stdout.write(self.style.HTTP_INFO("\n[4/5] Seeding customers, vendors & accounting setup..."))
            country, city = self._get_or_create_country_city()
            tax_rate = self._seed_tax_rates()
            customers = self._seed_customers(country, city)
            vendors = self._seed_vendors(country, city)
            self._seed_chart_of_accounts()
            self._seed_fiscal_year()

            self.stdout.write(self.style.HTTP_INFO("\n[5/5] Seeding transactions..."))
            self._seed_stock(products, warehouses)
            self._seed_purchase_orders(vendors, products, warehouses)
            self._seed_sales_orders(customers, products, warehouses[0], tax_rate)

        self.stdout.write(self.style.SUCCESS("\n=== Seed completed successfully! ==="))
        self._print_summary()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _safe_delete(self, model, **kwargs):
        try:
            cnt, _ = model.objects.filter(**kwargs).delete()
            if cnt:
                self.stdout.write(f"  Deleted {cnt:>4}  {model.__name__}")
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  Skipped {model.__name__}: {exc}"))

    def _get_or_create_country_city(self):
        from core.models import Country, Region, City
        country = Country.objects.filter(is_active=True).first()
        if not country:
            country, _ = Country.objects.get_or_create(
                code="TST", defaults=dict(name="Test Country", iso_code="TC", is_active=True),
            )
        city = City.objects.filter(country=country).first()
        if not city:
            region = Region.objects.filter(country=country).first()
            if not region:
                region, _ = Region.objects.get_or_create(
                    name="Test Region", country=country, defaults=dict(is_active=True),
                )
            city, _ = City.objects.get_or_create(
                name="Test City", country=country, defaults=dict(region=region, is_active=True),
            )
        return country, city

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def _clear_data(self):
        from rbac.models import AuditLog, UserProfile
        from products.models import (
            ProductVariant, ProductPriceHistory, ProductPrice,
            Product, ModelNumber, PriceList, Brand, ProductCategory,
        )
        from inventory.models import StockMovement, StockBatch, Stock, WarehouseSection, Warehouse
        from sales.models import SalesOrderLine, SalesOrder, Customer, TaxRate
        from purchasing.models import (
            PurchaseReceiptLine, PurchaseReceipt, PurchaseOrderLine, PurchaseOrder, Vendor,
        )
        from accounting.models import (
            JournalLine, JournalEntry, Payment, Bill, Invoice, Account,
            FiscalPeriod, FiscalYear,
        )

        # Transactions first (deepest dependencies)
        self._safe_delete(AuditLog)
        self._safe_delete(JournalLine)
        self._safe_delete(JournalEntry)
        self._safe_delete(Payment)
        self._safe_delete(Bill)
        self._safe_delete(Invoice)
        self._safe_delete(SalesOrderLine)
        self._safe_delete(SalesOrder)
        self._safe_delete(PurchaseReceiptLine)
        self._safe_delete(PurchaseReceipt)
        self._safe_delete(PurchaseOrderLine)
        self._safe_delete(PurchaseOrder)
        self._safe_delete(StockMovement)
        self._safe_delete(StockBatch)
        self._safe_delete(Stock)
        self._safe_delete(WarehouseSection)
        self._safe_delete(Warehouse)
        # Products (clear prices first, then products, then catalogs)
        self._safe_delete(ProductVariant)
        self._safe_delete(ProductPriceHistory)
        self._safe_delete(ProductPrice)
        self._safe_delete(Product)
        self._safe_delete(PriceList)
        self._safe_delete(ModelNumber)
        self._safe_delete(Brand)
        self._safe_delete(ProductCategory)
        # Other reference data
        self._safe_delete(TaxRate)
        self._safe_delete(Customer)
        self._safe_delete(Vendor)
        # Accounting structure
        self._safe_delete(FiscalPeriod)
        self._safe_delete(FiscalYear)
        # Accounts: null out AccountingSettings FK references + self-referential parent
        try:
            from accounting.models import AccountingSettings
            AccountingSettings.objects.all().update(
                default_cash_account=None, default_ar_account=None,
                default_ap_account=None, default_inventory_account=None,
                default_sales_account=None, default_purchase_account=None,
                default_tax_account=None, default_cogs_account=None,
                default_shipping_account=None, default_discount_account=None,
            )
        except Exception:
            pass
        Account.objects.all().update(parent=None)
        self._safe_delete(Account)
        # Users
        self._safe_delete(UserProfile)
        self._safe_delete(User, is_system_admin=False)

    # ------------------------------------------------------------------
    # RBAC
    # ------------------------------------------------------------------

    def _seed_rbac(self):
        from rbac.models import (
            Branch, Department, Role, ModulePermission, UserProfile, MODULE_CHOICES,
        )
        from inventory.models import Warehouse

        all_modules = [mk for mk, _ in MODULE_CHOICES]
        ACCT  = ["accounting.invoice","accounting.bill","accounting.payment","accounting.journalentry"]
        SALES = ["sales.customer","sales.salesorder"]
        PURCH = ["purchasing.purchaseorder","purchasing.vendor","purchasing.purchasereceipt"]
        INV   = ["inventory.stock","inventory.stockbatch","inventory.stockmovement",
                 "inventory.warehouse","inventory.warehousesection"]
        PROD  = ["products.product","products.unit","products.brand",
                 "products.productcategory","products.pricelist",
                 "products.productattribute","products.productattributevalue",
                 "products.productvariant","products.productpricehistory"]

        def _full(**extra):
            return dict(can_view=True, can_create=True, can_edit=True,
                        can_delete=True, can_approve=True, can_export=True, can_print=True, **extra)
        def _view_only():
            return dict(can_view=True, can_create=False, can_edit=False,
                        can_delete=False, can_approve=False, can_export=True, can_print=False)

        role_defs = [
            {"code": "administrator",     "name": "Administrator",      "priority": 1, "is_system_role": True,
             "perms": {mk: _full() for mk in all_modules}},
            {"code": "finance_manager",   "name": "Finance Manager",    "priority": 2,
             "perms": {**{mk: _view_only() for mk in all_modules}, **{mk: _full() for mk in ACCT}}},
            {"code": "sales_manager",     "name": "Sales Manager",      "priority": 3,
             "perms": {**{mk: _view_only() for mk in all_modules}, **{mk: _full() for mk in SALES}}},
            {"code": "purchasing_officer","name": "Purchasing Officer",  "priority": 4,
             "perms": {**{mk: _view_only() for mk in all_modules}, **{mk: _full() for mk in PURCH}}},
            {"code": "warehouse_staff",   "name": "Warehouse Staff",    "priority": 5,
             "perms": {
                 **{mk: _view_only() for mk in PROD},
                 "inventory.stock":         dict(can_view=True, can_create=False, can_edit=True,  can_delete=False, can_approve=False, can_export=True, can_print=False),
                 "inventory.stockbatch":    dict(can_view=True, can_create=False, can_edit=True,  can_delete=False, can_approve=False, can_export=True, can_print=False),
                 "inventory.stockmovement": dict(can_view=True, can_create=True,  can_edit=False, can_delete=False, can_approve=False, can_export=True, can_print=False),
                 "inventory.warehouse":     _view_only(),
                 "inventory.warehousesection": _view_only(),
             }},
        ]

        roles = {}
        for rd in role_defs:
            role, _ = Role.objects.get_or_create(
                code=rd["code"],
                defaults=dict(name=rd["name"], priority=rd["priority"],
                              is_system_role=rd.get("is_system_role", False), is_active=True),
            )
            roles[rd["code"]] = role
            for mk, perm_kw in rd["perms"].items():
                ModulePermission.objects.update_or_create(role=role, module=mk, defaults=perm_kw)
        self.stdout.write(f"  Created {len(roles)} roles with module permissions")

        # Branches
        hq,    _ = Branch.objects.get_or_create(code="HQ",  defaults=dict(name="HQ Main Branch", address="100 Main Street", is_main=True, is_active=True))
        north, _ = Branch.objects.get_or_create(code="NB",  defaults=dict(name="North Branch",   address="50 North Avenue", is_main=False, is_active=True))
        south, _ = Branch.objects.get_or_create(code="SB",  defaults=dict(name="South Branch",   address="75 South Road",   is_main=False, is_active=True))

        # Departments
        fin_dept, _ = Department.objects.get_or_create(code="FIN", defaults=dict(name="Finance",           is_active=True))
        ops_dept, _ = Department.objects.get_or_create(code="OPS", defaults=dict(name="Operations",        is_active=True))
        sal_dept, _ = Department.objects.get_or_create(code="SAL", defaults=dict(name="Sales & Marketing", is_active=True))
        pur_dept, _ = Department.objects.get_or_create(code="PUR", defaults=dict(name="Purchasing",        is_active=True))
        it_dept,  _ = Department.objects.get_or_create(code="IT",  defaults=dict(name="IT & Systems",      is_active=True))

        # Warehouses
        wh_main  = Warehouse.objects.create(name="Main Warehouse",  code="WH-MAIN",  warehouse_type="main",        is_active=True, address="100 Warehouse Rd")
        wh_north = Warehouse.objects.create(name="North Warehouse", code="WH-NORTH", warehouse_type="branch",      is_active=True, address="50 North Industrial")
        wh_cold  = Warehouse.objects.create(name="Cold Storage",    code="WH-COLD",  warehouse_type="cold_storage",is_active=True, address="15 Cold Chain Ave")
        warehouses = [wh_main, wh_north, wh_cold]
        self.stdout.write(f"  Created {len(warehouses)} warehouses")

        hq.warehouses.set([wh_main, wh_cold])
        north.warehouses.set([wh_north])

        # Warehouse sections
        from inventory.models import WarehouseSection
        sections = [
            dict(warehouse=wh_main,  zone="A", aisle="1", rack="1", bin="01", max_capacity=Decimal("500"), description="Electronics Main"),
            dict(warehouse=wh_main,  zone="A", aisle="1", rack="2", bin="01", max_capacity=Decimal("500"), description="Electronics Accessories"),
            dict(warehouse=wh_main,  zone="A", aisle="2", rack="1", bin="01", max_capacity=Decimal("300"), description="Mobile & Tablets"),
            dict(warehouse=wh_main,  zone="B", aisle="1", rack="1", bin="01", max_capacity=Decimal("200"), description="Office Furniture"),
            dict(warehouse=wh_main,  zone="B", aisle="2", rack="1", bin="01", max_capacity=Decimal("400"), description="Networking Equipment"),
            dict(warehouse=wh_main,  zone="C", aisle="1", rack="1", bin="01", max_capacity=Decimal("400"), description="Storage Solutions"),
            dict(warehouse=wh_north, zone="A", aisle="1", rack="1", bin="01", max_capacity=Decimal("600"), description="General Stock"),
            dict(warehouse=wh_cold,  zone="A", aisle="1", rack="1", bin="01", max_capacity=Decimal("200"), description="Temperature-Sensitive"),
        ]
        for s in sections:
            WarehouseSection.objects.create(**s)
        self.stdout.write(f"  Created {len(sections)} warehouse sections")

        # Test users
        user_defs = [
            dict(username="admin_erp",        first_name="Adam",   last_name="Wright",   email="admin_erp@test.erp",
                 role="administrator",     dept=fin_dept,  branch=hq,    approval_level=3, warehouses=[],                    employee_id="EMP-001"),
            dict(username="finance_mgr",      first_name="Fiona",  last_name="Chen",     email="finance_mgr@test.erp",
                 role="finance_manager",   dept=fin_dept,  branch=hq,    approval_level=3, warehouses=[],                    employee_id="EMP-002"),
            dict(username="sales_mgr",        first_name="Sam",    last_name="Torres",   email="sales_mgr@test.erp",
                 role="sales_manager",     dept=sal_dept,  branch=hq,    approval_level=2, warehouses=[],                    employee_id="EMP-003"),
            dict(username="purchase_officer", first_name="Paul",   last_name="King",     email="purchase_officer@test.erp",
                 role="purchasing_officer",dept=pur_dept,  branch=north, approval_level=2, warehouses=[wh_north],            employee_id="EMP-004"),
            dict(username="warehouse_staff",  first_name="Wendy",  last_name="Park",     email="warehouse_staff@test.erp",
                 role="warehouse_staff",   dept=ops_dept,  branch=north, approval_level=1, warehouses=[wh_main, wh_north],   employee_id="EMP-005"),
            dict(username="sales_rep",        first_name="Rachel", last_name="Morgan",   email="sales_rep@test.erp",
                 role="sales_manager",     dept=sal_dept,  branch=south, approval_level=1, warehouses=[],                    employee_id="EMP-006"),
        ]

        from rbac.models import UserProfile
        for ud in user_defs:
            user = User.objects.create_user(
                username=ud["username"], email=ud["email"], password=PASSWORD,
                first_name=ud["first_name"], last_name=ud["last_name"],
            )
            profile = UserProfile.objects.create(
                user=user, role=roles[ud["role"]], department=ud["dept"],
                branch=ud["branch"], approval_level=ud["approval_level"],
                employee_id=ud["employee_id"],
            )
            if ud["warehouses"]:
                profile.warehouses.set(ud["warehouses"])
        self.stdout.write(f"  Created {len(user_defs)} test users")
        return warehouses

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def _seed_products(self):
        from products.models import (
            Brand, ProductCategory, ModelNumber, Product, PriceList, ProductPrice,
        )
        from products.models import Unit

        # Seed units first so every product gets a base_unit
        unit_map = {}
        for uname, ucode, ushort, utype in UNIT_SEED:
            u, _ = Unit.objects.get_or_create(
                code=ucode,
                defaults=dict(name=uname, short_name=ushort, unit_type=utype, is_active=True),
            )
            unit_map[ucode] = u
        self.stdout.write(f"  Created {len(unit_map)} units")
        each_unit = unit_map["EA"]
        pack_unit = unit_map["PCK"]
        box_unit  = unit_map["BOX"]
        roll_unit = unit_map["RL"]

        # Unit hints by product name keywords
        def _pick_unit(name):
            n = name.lower()
            if "10-pack" in n or "pack" in n:
                return pack_unit
            if "box" in n or "5 reams" in n:
                return box_unit
            if "305m" in n or "roll" in n:
                return roll_unit
            return each_unit

        # Categories (hierarchical MPTT) — use create() with explicit slug
        # to avoid MPTT/unique-slug race conditions inside the transaction
        from django.utils.text import slugify as _slugify
        cat_map = {}
        for name, parent_key, slug_key in CATEGORY_SEED:
            parent = cat_map.get(parent_key) if parent_key else None
            slug_val = _slugify(name)
            cat = ProductCategory.objects.filter(slug=slug_val).first()
            if not cat:
                cat = ProductCategory.objects.create(
                    name=name, parent=parent, slug=slug_val,
                )
            cat_map[slug_key] = cat
        self.stdout.write(f"  Created {len(cat_map)} categories")

        # Brands
        brand_map = {}
        for brand_name in BRAND_SEED:
            brand, _ = Brand.objects.get_or_create(name=brand_name)
            brand_map[brand_name] = brand
        self.stdout.write(f"  Created {len(brand_map)} brands")

        # Model numbers
        model_map = {}
        for code, name, brand_name, desc in MODEL_NUMBER_SEED:
            mn, _ = ModelNumber.objects.get_or_create(
                code=code,
                defaults=dict(name=name, brand=brand_map[brand_name],
                              description=desc, is_active=True),
            )
            model_map[code] = mn
        self.stdout.write(f"  Created {len(model_map)} model numbers")

        # Price lists
        retail, _ = PriceList.objects.get_or_create(
            code="RETAIL",
            defaults=dict(name="Retail", priority=1, is_default=True,
                          discount_method="none", applicable_to_retail=True, is_active=True),
        )
        wholesale, _ = PriceList.objects.get_or_create(
            code="WHOLE",
            defaults=dict(name="Wholesale", priority=2, is_default=False,
                          discount_method="percentage", default_discount_percentage=Decimal("10.00"),
                          applicable_to_wholesale=True, is_active=True),
        )
        distributor, _ = PriceList.objects.get_or_create(
            code="DIST",
            defaults=dict(name="Distributor", priority=3, is_default=False,
                          discount_method="percentage", default_discount_percentage=Decimal("20.00"),
                          applicable_to_distributor=True, is_active=True),
        )
        price_lists = [retail, wholesale, distributor]
        self.stdout.write(f"  Created {len(price_lists)} price lists")

        # Products
        products = []
        for name, cat_key, brand_name, model_code, price, cost in PRODUCT_SEED:
            product = Product.objects.create(
                name=name,
                category=cat_map[cat_key],
                brand=brand_map[brand_name],
                model_number=model_map.get(model_code) if model_code else None,
                price=price,
                cost=cost,
                base_unit=_pick_unit(name),
                active=True,
                default_price_list=retail,
            )
            products.append(product)
            # Wholesale and distributor prices
            ProductPrice.objects.create(
                product=product, price_list=wholesale,
                price=(price * Decimal("0.90")).quantize(Decimal("0.01")),
                min_quantity=Decimal("5"),
            )
            ProductPrice.objects.create(
                product=product, price_list=distributor,
                price=(price * Decimal("0.80")).quantize(Decimal("0.01")),
                min_quantity=Decimal("20"),
            )

        self.stdout.write(f"  Created {len(products)} products with prices")
        return products, price_lists

    # ------------------------------------------------------------------
    # Reference data
    # ------------------------------------------------------------------

    def _seed_tax_rates(self):
        from sales.models import TaxRate
        rates = [
            ("Standard VAT 20%", Decimal("20.00"), "vat"),
            ("Reduced VAT 5%",   Decimal("5.00"),  "vat"),
            ("Zero Rate 0%",     Decimal("0.00"),  "vat"),
        ]
        created = []
        for name, rate, tax_type in rates:
            tr, _ = TaxRate.objects.get_or_create(
                name=name, defaults=dict(rate=rate, tax_type=tax_type, is_active=True),
            )
            created.append(tr)
        self.stdout.write(f"  Created {len(created)} tax rates")
        return created[0]

    def _seed_customers(self, country, city):
        from sales.models import Customer
        customers = []
        for i, (display_name, email, ctype, address, credit_limit, credit_days, pay_type) in enumerate(CUSTOMER_SEED):
            is_biz = (ctype == "business")
            cust = Customer.objects.create(
                customer_type=ctype,
                first_name="" if is_biz else display_name.split()[0],
                last_name="" if is_biz else " ".join(display_name.split()[1:]),
                full_name=display_name,
                company_name=display_name if is_biz else "",
                email=email,
                phone=f"+1-555-{2000 + i:04d}",
                billing_address_line1=address,
                billing_country=country,
                billing_city=city,
                billing_postal_code=f"1000{i}",
                payment_type=pay_type,
                credit_limit=credit_limit,
                credit_days=credit_days,
                is_active=True,
                is_vip=(i < 3),
            )
            customers.append(cust)
        self.stdout.write(f"  Created {len(customers)} customers")
        return customers

    def _seed_vendors(self, country, city):
        from purchasing.models import Vendor
        vendors = []
        for i, (name, code, email, address, payment_terms, _) in enumerate(VENDOR_SEED):
            v = Vendor.objects.create(
                name=name, code=code, email=email,
                address_line1=address,
                country=country, city=city,
                postal_code=f"2000{i}",
                payment_terms=payment_terms,
                credit_limit=Decimal("100000"),
                is_active=True,
                is_preferred=(i < 4),
            )
            vendors.append(v)
        self.stdout.write(f"  Created {len(vendors)} vendors")
        return vendors

    def _seed_chart_of_accounts(self):
        from accounting.models import Account
        created = 0
        for code, name, acc_type, is_system, currency in Account.STANDARD_ACCOUNTS:
            Account.objects.get_or_create(
                code=code,
                defaults=dict(name=name, type=acc_type, is_system=is_system,
                              is_active=True, currency=currency),
            )
            created += 1
        self.stdout.write(f"  Created {created} chart of accounts entries")

    def _seed_fiscal_year(self):
        from accounting.models import FiscalYear, FiscalPeriod
        import calendar

        fy, _ = FiscalYear.objects.get_or_create(
            name="FY 2026",
            defaults=dict(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), is_closed=False),
        )
        periods_created = 0
        for month in range(1, 13):
            last_day = calendar.monthrange(2026, month)[1]
            FiscalPeriod.objects.get_or_create(
                fiscal_year=fy,
                period_number=month,
                defaults=dict(
                    period_type="monthly",
                    start_date=date(2026, month, 1),
                    end_date=date(2026, month, last_day),
                    is_closed=(month < date.today().month),
                ),
            )
            periods_created += 1
        self.stdout.write(f"  Created fiscal year FY 2026 with {periods_created} periods")

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

    def _seed_stock(self, products, warehouses):
        from inventory.models import Stock, StockMovement

        wh_main, wh_north, wh_cold = warehouses
        today = date.today()

        n = len(products)
        # Stock quantities per warehouse
        # (product_index_range, warehouse, qty, reorder_level, max_level)
        stock_defs = [
            # Main warehouse — original products
            (range(0,  8),   wh_main,  Decimal("30"), Decimal("5"),  Decimal("100")),  # Laptops
            (range(8,  14),  wh_main,  Decimal("25"), Decimal("5"),  Decimal("80")),   # Mobile
            (range(14, 20),  wh_main,  Decimal("40"), Decimal("10"), Decimal("120")),  # Audio
            (range(20, 30),  wh_main,  Decimal("50"), Decimal("10"), Decimal("150")),  # Accessories
            (range(30, 35),  wh_main,  Decimal("15"), Decimal("3"),  Decimal("40")),   # Furniture
            (range(35, 46),  wh_main,  Decimal("35"), Decimal("5"),  Decimal("100")),  # Stationery+Networking
            (range(46, 51),  wh_main,  Decimal("20"), Decimal("4"),  Decimal("60")),   # Storage
            # Main warehouse — new products
            (range(51, 61),  wh_main,  Decimal("20"), Decimal("3"),  Decimal("60")),   # More laptops
            (range(61, 67),  wh_main,  Decimal("30"), Decimal("5"),  Decimal("80")),   # More mobile
            (range(67, 73),  wh_main,  Decimal("35"), Decimal("8"),  Decimal("100")),  # More audio
            (range(73, 83),  wh_main,  Decimal("45"), Decimal("10"), Decimal("130")),  # More accessories
            (range(83, 87),  wh_main,  Decimal("10"), Decimal("2"),  Decimal("30")),   # More furniture
            (range(87, 93),  wh_main,  Decimal("40"), Decimal("8"),  Decimal("100")),  # More stationery
            (range(93, 99),  wh_main,  Decimal("25"), Decimal("5"),  Decimal("70")),   # More networking
            (range(99, n),   wh_main,  Decimal("30"), Decimal("6"),  Decimal("80")),   # More storage
            # North warehouse — all products, smaller quantities
            (range(0,  14),  wh_north, Decimal("10"), Decimal("2"),  Decimal("30")),
            (range(14, 30),  wh_north, Decimal("15"), Decimal("3"),  Decimal("50")),
            (range(30, 51),  wh_north, Decimal("8"),  Decimal("2"),  Decimal("25")),
            (range(51, n),   wh_north, Decimal("8"),  Decimal("2"),  Decimal("25")),
        ]

        stock_count = 0
        for prod_range, warehouse, qty, reorder, max_lvl in stock_defs:
            for i in prod_range:
                if i >= len(products):
                    continue
                stock, created = Stock.objects.get_or_create(
                    product=products[i], warehouse=warehouse,
                    defaults=dict(quantity=qty, reorder_level=reorder, max_level=max_lvl),
                )
                if created:
                    stock_count += 1
                    # Stock-in movement
                    StockMovement.objects.create(
                        product=products[i], warehouse=warehouse,
                        movement_type="IN", source="initial",
                        quantity=qty, previous_balance=Decimal("0"), new_balance=qty,
                        reference="INITIAL-STOCK",
                        notes="Initial stock seeding",
                    )

        self.stdout.write(f"  Created {stock_count} stock records with movements")

    # ------------------------------------------------------------------
    # Purchase Orders
    # ------------------------------------------------------------------

    def _seed_purchase_orders(self, vendors, products, warehouses):
        from purchasing.models import PurchaseOrder, PurchaseOrderLine, PurchaseReceipt, PurchaseReceiptLine
        from accounting.models import Bill, Payment, Account
        from inventory.models import Stock

        wh_main, wh_north, _ = warehouses
        today = date.today()
        tdi, osc, gel, frd, nsl, spl, mbd, csl = vendors

        # Helper: create PO with lines
        def make_po(vendor, wh, status, expected_delta, product_list, qty, notes=""):
            po = PurchaseOrder.objects.create(
                vendor=vendor, warehouse=wh, status=status,
                expected_date=today + timedelta(days=expected_delta),
                payment_terms=vendor.payment_terms, notes=notes,
            )
            for product, unit_price in product_list:
                PurchaseOrderLine.objects.create(
                    order=po, product=product,
                    quantity=qty, price=unit_price,
                    received_quantity=Decimal("0"),
                )
            po.calculate_totals()
            PurchaseOrder.objects.filter(pk=po.pk).update(
                subtotal=po.subtotal, total_amount=po.total_amount
            )
            return po

        # Helper: receive PO (create receipt + update stock)
        def receive_po(po, wh, received_by=None):
            from django.contrib.auth import get_user_model
            User = get_user_model()
            staff = User.objects.filter(is_active=True, is_system_admin=False).first()
            receipt = PurchaseReceipt.objects.create(
                purchase_order=po, warehouse=wh,
                received_by=staff, received_date=po.expected_date or today,
                status="completed", delivery_note_number=f"DN-{po.pk:04d}",
            )
            for line in po.lines.all():
                PurchaseReceiptLine.objects.create(
                    receipt=receipt, order_line=line, product=line.product,
                    quantity_received=line.quantity, quantity_accepted=line.quantity,
                    quantity_rejected=Decimal("0"), quality_status="accepted",
                    warehouse=wh,
                )
                # Update stock
                stock = Stock.objects.filter(product=line.product, warehouse=wh).first()
                if stock:
                    stock.quantity += line.quantity
                    stock.save(update_fields=["quantity"])
            return receipt

        # Helper: create bill for a PO
        def make_bill(po, vendor, status="received"):
            bill = Bill.objects.create(
                purchase_order=po, vendor=vendor,
                bill_date=today - timedelta(days=5),
                due_date=today + timedelta(days=30),
                total_amount=po.total_amount,
                net_amount=po.total_amount,
                status=status,
            )
            return bill

        # Helper: pay a bill
        def pay_bill(bill, amount=None, partial=False):
            amt = amount or bill.total_amount
            p = Payment.objects.create(
                payment_type="vendor", payment_method="bank_transfer",
                bill=bill, amount=amt,
                status="completed",
                payment_date=today - timedelta(days=2),
                reference=f"PAY-BILL-{bill.pk:04d}",
            )
            new_status = "partial" if partial else "paid"
            Bill.objects.filter(pk=bill.pk).update(status=new_status)
            return p

        # PO 1 — Tech Distributors: Accessories (Draft)
        po1 = make_po(tdi, wh_main, "draft", 14,
                      [(products[20], products[20].cost),   # Wireless Mouse
                       (products[21], products[21].cost),   # Keyboard
                       (products[22], products[22].cost),   # USB-C Hub
                       (products[27], products[27].cost),   # HDMI Cables
                       (products[28], products[28].cost)],  # Mouse Pad
                      Decimal("50"))

        # PO 2 — Computing Solutions: Laptops (Confirmed)
        po2 = make_po(csl, wh_main, "confirmed", 10,
                      [(products[0], products[0].cost),   # Business Laptop 14"
                       (products[1], products[1].cost),   # Developer Laptop 15"
                       (products[6], products[6].cost),   # Budget Laptop
                       (products[7], products[7].cost)],  # Ultrabook
                      Decimal("15"))

        # PO 3 — Global Electronics: Audio & Monitors (Done + receipt + bill + paid)
        po3 = make_po(gel, wh_main, "done", -7,
                      [(products[14], products[14].cost),  # Headset
                       (products[15], products[15].cost),  # Conference Speaker
                       (products[16], products[16].cost),  # Earbuds
                       (products[24], products[24].cost),  # 24" Monitor
                       (products[23], products[23].cost)], # 27" Monitor
                      Decimal("20"))
        receive_po(po3, wh_main)
        bill3 = make_bill(po3, gel, "paid")
        pay_bill(bill3)

        # PO 4 — Office Supplies Co: Furniture (Done + receipt + bill + partially paid)
        po4 = make_po(osc, wh_main, "done", -10,
                      [(products[30], products[30].cost),  # Ergo Chair
                       (products[31], products[31].cost),  # Standing Desk
                       (products[32], products[32].cost),  # Height-Adjustable Desk
                       (products[33], products[33].cost)], # Filing Cabinet
                      Decimal("10"))
        receive_po(po4, wh_main)
        bill4 = make_bill(po4, osc, "partial")
        pay_bill(bill4, po4.total_amount * Decimal("0.5"), partial=True)

        # PO 5 — Network Solutions: Networking gear (Partial)
        po5 = PurchaseOrder.objects.create(
            vendor=nsl, warehouse=wh_main, status="partial",
            expected_date=today - timedelta(days=3),
            payment_terms=nsl.payment_terms,
        )
        for product in [products[39], products[40], products[41], products[42]]:
            PurchaseOrderLine.objects.create(
                order=po5, product=product,
                quantity=Decimal("15"), price=product.cost,
                received_quantity=Decimal("8"),
            )
        po5.calculate_totals()
        PurchaseOrder.objects.filter(pk=po5.pk).update(subtotal=po5.subtotal, total_amount=po5.total_amount)

        # PO 6 — StoragePro: Storage products (Done + receipt + bill)
        po6 = make_po(spl, wh_main, "done", -5,
                      [(products[46], products[46].cost),  # NAS 4-Bay
                       (products[47], products[47].cost),  # External SSD 1TB
                       (products[48], products[48].cost),  # External SSD 2TB
                       (products[49], products[49].cost)], # External HDD 4TB
                      Decimal("25"))
        receive_po(po6, wh_main)
        bill6 = make_bill(po6, spl, "received")

        # PO 7 — Mobile Direct: Smartphones & Tablets (Approved)
        po7 = make_po(mbd, wh_north, "approved", 7,
                      [(products[8],  products[8].cost),   # Enterprise Smartphone
                       (products[9],  products[9].cost),   # Business Smartphone
                       (products[11], products[11].cost),  # Business Tablet
                       (products[12], products[12].cost)], # Professional Tablet
                      Decimal("12"))

        # PO 8 — Furniture Depot: More furniture (Done + receipt + bill + paid)
        po8 = make_po(frd, wh_north, "done", -15,
                      [(products[30], products[30].cost),  # Ergo Chair
                       (products[34], products[34].cost),  # Bookshelf
                       (products[33], products[33].cost)], # Filing Cabinet
                      Decimal("8"))
        receive_po(po8, wh_north)
        bill8 = make_bill(po8, frd, "paid")
        pay_bill(bill8)

        # PO 9 — Tech Distributors: Monitors & Docking (Draft)
        po9 = make_po(tdi, wh_main, "draft", 21,
                      [(products[23], products[23].cost),  # 27" 4K Monitor
                       (products[24], products[24].cost),  # 24" FHD Monitor
                       (products[25], products[25].cost),  # Webcam
                       (products[26], products[26].cost)], # Docking Station
                      Decimal("20"))

        # PO 10 — Computing Solutions: Workstations (Cancelled)
        po10 = make_po(csl, wh_main, "cancelled", -20,
                       [(products[5], products[5].cost),   # Workstation Tower
                        (products[4], products[4].cost),   # All-in-One
                        (products[2], products[2].cost)],  # Gaming Laptop
                       Decimal("5"))

        # PO 11 — Tech Distributors: New accessories + audio (Confirmed)
        if len(products) > 73:
            po11 = make_po(tdi, wh_main, "confirmed", 12,
                           [(products[73], products[73].cost),  # Laptop Stand
                            (products[74], products[74].cost),  # USB-C Adapter
                            (products[77], products[77].cost),  # Wireless Keyboard
                            (products[67], products[67].cost),  # Smart TV
                            (products[70], products[70].cost)], # Ring Light
                           Decimal("30"))

        # PO 12 — Mobile Direct: New smartphones & tablets (Done + receipt + bill)
        if len(products) > 64:
            po12 = make_po(mbd, wh_main, "done", -8,
                           [(products[61], products[61].cost),  # Smartphone Entry
                            (products[62], products[62].cost),  # Tablet 8" Compact
                            (products[63], products[63].cost),  # Rugged Smartphone
                            (products[65], products[65].cost)], # Drawing Tablet
                           Decimal("18"))
            receive_po(po12, wh_main)
            bill12 = make_bill(po12, mbd, "received")

        # PO 13 — Network Solutions: New networking gear (Approved)
        if len(products) > 97:
            po13 = make_po(nsl, wh_main, "approved", 9,
                           [(products[93], products[93].cost),  # VPN Router
                            (products[94], products[94].cost),  # Firewall
                            (products[95], products[95].cost),  # PoE Switch 8-Port
                            (products[97], products[97].cost),  # IP Camera
                            (products[98], products[98].cost)], # VoIP Phone
                           Decimal("10"))

        # PO 14 — StoragePro: New storage products (Done + receipt + bill + paid)
        if len(products) > 103:
            po14 = make_po(spl, wh_north, "done", -12,
                           [(products[99],  products[99].cost),   # USB Flash 10-Pack
                            (products[101], products[101].cost),  # RAID Controller
                            (products[102], products[102].cost),  # NAS 2-Bay
                            (products[104], products[104].cost)], # Portable SSD 512
                           Decimal("10"))  # qty=10 keeps stock under max_level=25
            receive_po(po14, wh_north)
            bill14 = make_bill(po14, spl, "paid")
            pay_bill(bill14)

        # PO 15 — Computing Solutions: New laptops (Draft)
        if len(products) > 59:
            po15 = make_po(csl, wh_main, "draft", 18,
                           [(products[51], products[51].cost),  # Chromebook
                            (products[53], products[53].cost),  # Convertible Laptop
                            (products[57], products[57].cost),  # Desktop Business PC
                            (products[55], products[55].cost)], # Rugged Laptop
                           Decimal("10"))

        self.stdout.write("  Created 15 purchase orders (receipts, bills, payments included)")

    # ------------------------------------------------------------------
    # Sales Orders
    # ------------------------------------------------------------------

    def _seed_sales_orders(self, customers, products, warehouse, tax_rate):
        from sales.models import SalesOrder, SalesOrderLine
        from accounting.models import Invoice, Payment

        today = date.today()

        # Helper: create SO with lines
        def make_so(customer, status, product_list, tax=tax_rate, disc_days=7):
            so = SalesOrder.objects.create(
                customer=customer, warehouse=warehouse, status=status,
                expected_delivery_date=today + timedelta(days=disc_days),
                tax_rate=tax,
            )
            subtotal = Decimal("0")
            for product, qty, disc_pct in product_list:
                SalesOrderLine.objects.create(
                    order=so, product=product, quantity=qty,
                    price=product.price, discount_percent=disc_pct,
                )
                line_total = product.price * qty * (1 - disc_pct / 100)
                subtotal += line_total
            tax_amt = subtotal * (tax_rate.rate / Decimal("100"))
            SalesOrder.objects.filter(pk=so.pk).update(subtotal=subtotal, tax_amount=tax_amt)
            so.refresh_from_db()
            return so, subtotal, tax_amt

        # Helper: create invoice for SO
        def make_invoice(so, subtotal, tax_amt, status="sent", paid_amt=None, days_ago=3):
            total = subtotal + tax_amt
            inv = Invoice.objects.create(
                sales_order=so, customer=so.customer,
                invoice_date=today - timedelta(days=days_ago),
                due_date=today + timedelta(days=27),
                total_amount=total, net_amount=total,
                tax_amount=tax_amt,
                amount_paid=paid_amt or Decimal("0"),
                status=status,
            )
            return inv, total

        # Helper: pay an invoice
        def pay_invoice(inv, amount, partial=False):
            p = Payment.objects.create(
                payment_type="customer", payment_method="bank_transfer",
                invoice=inv, amount=amount,
                status="completed",
                payment_date=today - timedelta(days=1),
                reference=f"PAY-INV-{inv.pk:04d}",
            )
            new_status = "partial" if partial else "paid"
            Invoice.objects.filter(pk=inv.pk).update(status=new_status, amount_paid=amount)
            return p

        # SO 1 — Alice Johnson: Accessories, Draft
        make_so(customers[0], "draft", [
            (products[20], 2, Decimal("0")),   # Mouse
            (products[21], 1, Decimal("0")),   # Keyboard
            (products[22], 2, Decimal("0")),   # USB-C Hub
        ])

        # SO 2 — Bob Smith Ltd: Laptops, Confirmed
        make_so(customers[1], "confirmed", [
            (products[0], 3, Decimal("5")),    # Business Laptop 14" — 5% disc
            (products[1], 2, Decimal("5")),    # Developer Laptop 15"
            (products[6], 5, Decimal("0")),    # Budget Laptop
        ])

        # SO 3 — Delta Corp: Networking, Confirmed
        make_so(customers[3], "confirmed", [
            (products[39], 10, Decimal("10")), # Network Switch 24-Port
            (products[40], 5,  Decimal("10")), # Network Switch 48-Port
            (products[41], 8,  Decimal("5")),  # WAP
            (products[43], 6,  Decimal("0")),  # UPS 1500VA
        ])

        # SO 4 — Carol Davis: Accessories, Completed → Invoice (draft)
        so4, sub4, tax4 = make_so(customers[2], "completed", [
            (products[24], 1, Decimal("0")),   # 24" Monitor
            (products[25], 1, Decimal("0")),   # Webcam
        ])
        make_invoice(so4, sub4, tax4, status="draft")

        # SO 5 — Echo Enterprises: Mixed electronics, Completed → Invoice (sent)
        so5, sub5, tax5 = make_so(customers[4], "completed", [
            (products[8],  5, Decimal("8")),   # Enterprise Smartphone
            (products[11], 3, Decimal("5")),   # Business Tablet
            (products[14], 4, Decimal("0")),   # Headset
            (products[19], 6, Decimal("0")),   # Bluetooth Speaker
        ])
        make_invoice(so5, sub5, tax5, status="sent")

        # SO 6 — Frank Industries: Audio gear, Completed → Invoice (paid)
        so6, sub6, tax6 = make_so(customers[5], "completed", [
            (products[14], 10, Decimal("12")), # Headset — bulk discount
            (products[15], 5,  Decimal("10")), # Conference Speaker
            (products[16], 8,  Decimal("5")),  # Earbuds
        ])
        inv6, total6 = make_invoice(so6, sub6, tax6, status="paid", paid_amt=total6 if False else None)
        pay_invoice(inv6, total6)

        # SO 7 — Grace Solutions: Laptops + Monitors, Completed → Invoice (sent)
        so7, sub7, tax7 = make_so(customers[6], "completed", [
            (products[0], 4, Decimal("7")),    # Business Laptop
            (products[7], 2, Decimal("7")),    # Ultrabook
            (products[23], 4, Decimal("0")),   # 27" 4K Monitor
        ])
        make_invoice(so7, sub7, tax7, status="sent", days_ago=5)

        # SO 8 — Iris Technologies: Networking + Storage, Invoiced → Paid in full
        so8, sub8, tax8 = make_so(customers[8], "invoiced", [
            (products[39], 20, Decimal("15")), # Network Switch 24-Port — big order
            (products[44], 5,  Decimal("10")), # UPS 3000VA
            (products[45], 3,  Decimal("5")),  # Server Rack
            (products[46], 10, Decimal("10")), # NAS 4-Bay
        ])
        inv8, total8 = make_invoice(so8, sub8, tax8, status="paid", paid_amt=total8 if False else None, days_ago=8)
        pay_invoice(inv8, total8)

        # SO 9 — Jack & Co: Audio + Accessories, Invoiced → Partial payment
        so9, sub9, tax9 = make_so(customers[9], "invoiced", [
            (products[15], 3, Decimal("0")),   # Conference Speaker
            (products[17], 5, Decimal("0")),   # USB Microphone
            (products[26], 2, Decimal("0")),   # Docking Station
        ])
        inv9, total9 = make_invoice(so9, sub9, tax9, status="partial", days_ago=10)
        pay_invoice(inv9, total9 * Decimal("0.5"), partial=True)

        # SO 10 — Henry Trading: Furniture, Confirmed
        make_so(customers[7], "confirmed", [
            (products[30], 2, Decimal("0")),   # Ergo Chair
            (products[31], 1, Decimal("0")),   # Standing Desk
        ])

        # SO 11 — Nathan Electronics: Mobile devices, Confirmed
        make_so(customers[13], "confirmed", [
            (products[8],  6, Decimal("10")),  # Enterprise Smartphone
            (products[9],  8, Decimal("10")),  # Business Smartphone
            (products[12], 4, Decimal("5")),   # Professional Tablet
        ])

        # SO 12 — Maria Office: Office supplies + Printers, Completed → Invoice (overdue)
        so12, sub12, tax12 = make_so(customers[12], "completed", [
            (products[35], 3, Decimal("0")),   # Laser Printer
            (products[37], 5, Decimal("0")),   # Label Printer
            (products[38], 4, Decimal("0")),   # Barcode Scanner
        ])
        inv12, _ = make_invoice(so12, sub12, tax12, status="overdue", days_ago=40)
        Invoice.objects.filter(pk=inv12.pk).update(
            due_date=today - timedelta(days=10)
        )

        # SO 13 — Karen Mitchell: Accessories, Cancelled
        make_so(customers[10], "cancelled", [
            (products[22], 1, Decimal("0")),   # USB-C Hub
            (products[29], 2, Decimal("0")),   # USB-A Hub
        ])

        # SO 14 — Leo Business: Laptops, Draft
        make_so(customers[11], "draft", [
            (products[1], 2, Decimal("0")),    # Developer Laptop
            (products[5], 1, Decimal("0")),    # Workstation Tower
        ])

        # SO 15 — Olivia Consulting: Accessories + Audio, Invoiced → Paid in full
        so15, sub15, tax15 = make_so(customers[14], "invoiced", [
            (products[20], 5, Decimal("0")),   # Wireless Mouse
            (products[21], 5, Decimal("0")),   # Keyboard
            (products[16], 5, Decimal("0")),   # Wireless Earbuds
            (products[18], 3, Decimal("0")),   # Conference Camera
        ])
        inv15, total15 = make_invoice(so15, sub15, tax15, status="paid", paid_amt=total15 if False else None, days_ago=6)
        pay_invoice(inv15, total15)

        # SO 16 — Delta Corp: New networking gear, Confirmed
        if len(products) > 98:
            make_so(customers[3], "confirmed", [
                (products[93], 5,  Decimal("10")),  # VPN Router
                (products[94], 2,  Decimal("10")),  # Firewall
                (products[95], 8,  Decimal("5")),   # PoE Switch 8-Port
                (products[97], 10, Decimal("5")),   # IP Camera
                (products[98], 6,  Decimal("0")),   # VoIP Phone
            ])

        # SO 17 — Nathan Electronics: New mobiles, Confirmed
        if len(products) > 65:
            make_so(customers[13], "confirmed", [
                (products[61], 15, Decimal("5")),   # Smartphone Entry Level
                (products[62], 8,  Decimal("5")),   # Tablet 8" Compact
                (products[63], 4,  Decimal("0")),   # Rugged Smartphone
                (products[65], 6,  Decimal("5")),   # Drawing Tablet
            ])

        # SO 18 — Echo Enterprises: New audio/video, Completed → Invoice (sent)
        if len(products) > 72:
            so18, sub18, tax18 = make_so(customers[4], "completed", [
                (products[67], 3, Decimal("8")),   # Smart TV 43"
                (products[68], 8, Decimal("5")),   # Wired Headphones
                (products[69], 4, Decimal("0")),   # Soundbar
                (products[71], 6, Decimal("0")),   # Ring Light
            ])
            make_invoice(so18, sub18, tax18, status="sent", days_ago=4)

        # SO 19 — Iris Technologies: New storage, Invoiced → Paid
        if len(products) > 104:
            so19, sub19, tax19 = make_so(customers[8], "invoiced", [
                (products[99],  20, Decimal("10")), # USB Flash 10-Pack
                (products[100], 10, Decimal("5")),  # Memory Card 128GB
                (products[102], 5,  Decimal("5")),  # NAS 2-Bay
                (products[104], 15, Decimal("8")),  # Portable SSD 512GB
            ])
            inv19, total19 = make_invoice(so19, sub19, tax19, status="paid", days_ago=7)
            pay_invoice(inv19, total19)

        # SO 20 — Grace Solutions: New accessories, Completed → Invoice (draft)
        if len(products) > 82:
            so20, sub20, tax20 = make_so(customers[6], "completed", [
                (products[73], 5, Decimal("0")),   # Laptop Stand
                (products[75], 10, Decimal("0")),  # Screen Cleaner Kit
                (products[77], 6, Decimal("5")),   # Wireless Ergonomic Keyboard
                (products[78], 4, Decimal("0")),   # Trackball Mouse Pro
                (products[80], 3, Decimal("0")),   # Portable Battery Bank
            ])
            make_invoice(so20, sub20, tax20, status="draft")

        self.stdout.write("  Created 20 sales orders (invoices and payments included)")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _print_summary(self):
        self.stdout.write(f"\nTest users (password: {PASSWORD}):")
        for u in ["admin_erp", "finance_mgr", "sales_mgr", "purchase_officer", "warehouse_staff", "sales_rep"]:
            self.stdout.write(f"  {u}")
        self.stdout.write("\nData created:")
        try:
            from products.models import Product, ProductCategory, Brand, ModelNumber, PriceList, Unit
            from products.models import ProductPrice
            from inventory.models import Stock, Warehouse, WarehouseSection, StockMovement
            from sales.models import Customer, SalesOrder
            from purchasing.models import Vendor, PurchaseOrder, PurchaseReceipt
            from accounting.models import Invoice, Bill, Payment, Account, FiscalYear
            self.stdout.write(f"  Units:           {Unit.objects.count()}")
            self.stdout.write(f"  Products:        {Product.objects.count()}")
            self.stdout.write(f"  Categories:      {ProductCategory.objects.count()}")
            self.stdout.write(f"  Brands:          {Brand.objects.count()}")
            self.stdout.write(f"  Model Numbers:   {ModelNumber.objects.count()}")
            self.stdout.write(f"  Price Lists:     {PriceList.objects.count()}")
            self.stdout.write(f"  Product Prices:  {ProductPrice.objects.count()}")
            self.stdout.write(f"  Warehouses:      {Warehouse.objects.count()}")
            self.stdout.write(f"  WH Sections:     {WarehouseSection.objects.count()}")
            self.stdout.write(f"  Stock Records:   {Stock.objects.count()}")
            self.stdout.write(f"  Stock Movements: {StockMovement.objects.count()}")
            self.stdout.write(f"  Customers:       {Customer.objects.count()}")
            self.stdout.write(f"  Vendors:         {Vendor.objects.count()}")
            self.stdout.write(f"  Purchase Orders: {PurchaseOrder.objects.count()}")
            self.stdout.write(f"  PO Receipts:     {PurchaseReceipt.objects.count()}")
            self.stdout.write(f"  Bills:           {Bill.objects.count()}")
            self.stdout.write(f"  Sales Orders:    {SalesOrder.objects.count()}")
            self.stdout.write(f"  Invoices:        {Invoice.objects.count()}")
            self.stdout.write(f"  Payments:        {Payment.objects.count()}")
            self.stdout.write(f"  Chart Accounts:  {Account.objects.count()}")
            self.stdout.write(f"  Fiscal Year:     {FiscalYear.objects.count()} year(s)")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  (summary error: {e})"))
