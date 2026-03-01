"""
Management command: seed_test_data
===================================
Clears all transactional ERP data and re-seeds realistic test data.

Preserved (never touched):
  - Superuser accounts
  - ExportConfig records
  - Countries / Regions / Cities
  - Currencies
  - Units (products.Unit)

Run:
  python manage.py seed_test_data [--yes]
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

User = get_user_model()

# ---------------------------------------------------------------------------
# Static seed data
# ---------------------------------------------------------------------------

PRODUCT_SEED = [
    ("Laptop Pro 15",             "Electronics", "TechBrand",  Decimal("1299.00"), Decimal("900.00")),
    ("Wireless Mouse",            "Electronics", "TechBrand",  Decimal("29.99"),   Decimal("12.00")),
    ("Mechanical Keyboard",       "Electronics", "TechBrand",  Decimal("79.99"),   Decimal("40.00")),
    ("USB-C Hub 7-Port",          "Electronics", "TechBrand",  Decimal("49.99"),   Decimal("22.00")),
    ('27" 4K Monitor',            "Electronics", "TechBrand",  Decimal("599.00"),  Decimal("380.00")),
    ("Webcam HD 1080p",           "Electronics", "TechBrand",  Decimal("89.99"),   Decimal("45.00")),
    ("Noise-Cancelling Headset",  "Electronics", "AudioPro",   Decimal("249.00"),  Decimal("130.00")),
    ("External SSD 1TB",          "Electronics", "StorageCo",  Decimal("119.00"),  Decimal("70.00")),
    ("Office Chair Ergonomic",    "Furniture",   "OfficeWorld", Decimal("399.00"), Decimal("210.00")),
    ("Standing Desk Electric",    "Furniture",   "OfficeWorld", Decimal("649.00"), Decimal("380.00")),
    ("Printer Laser Mono",        "Office",      "PrintTech",  Decimal("199.00"),  Decimal("110.00")),
    ("Network Switch 24-Port",    "Networking",  "NetGear",    Decimal("189.00"),  Decimal("95.00")),
    ("UPS Battery 1500VA",        "Networking",  "NetGear",    Decimal("159.00"),  Decimal("85.00")),
    ("Smartphone Enterprise",     "Electronics", "TechBrand",  Decimal("899.00"),  Decimal("580.00")),
    ("Tablet 10\" Business",      "Electronics", "TechBrand",  Decimal("549.00"),  Decimal("330.00")),
    ("Projector Full HD",         "Office",      "PrintTech",  Decimal("799.00"),  Decimal("450.00")),
    ("Conference Speaker",        "Office",      "AudioPro",   Decimal("149.00"),  Decimal("70.00")),
    ("Label Printer",             "Office",      "PrintTech",  Decimal("199.00"),  Decimal("95.00")),
    ("Barcode Scanner Wireless",  "Office",      "NetGear",    Decimal("129.00"),  Decimal("60.00")),
    ("Server Rack 12U",           "Networking",  "NetGear",    Decimal("499.00"),  Decimal("260.00")),
]

CUSTOMER_SEED = [
    ("Alice Johnson",    "alice@example.com",    "individual", "123 Oak Street"),
    ("Bob Smith Ltd",    "bob@bsmith.com",       "business",   "456 Commerce Ave"),
    ("Carol Davis",      "carol@example.com",    "individual", "789 Pine Road"),
    ("Delta Corp",       "info@deltacorp.com",   "business",   "1 Corporate Plaza"),
    ("Echo Enterprises", "contact@echo.com",     "business",   "20 Business Park"),
]

VENDOR_SEED = [
    ("Tech Distributors Inc", "TDI", "tech.dist@vendor.com",     "10 Tech Drive"),
    ("Office Supplies Co",    "OSC", "office@supplies.com",      "25 Supply Lane"),
    ("Global Electronics",    "GEL", "global@electronics.com",  "50 Electronics Blvd"),
    ("Furniture Depot",       "FRD", "depot@furniture.com",      "33 Factory Road"),
]

PASSWORD = "Test@12345"


class Command(BaseCommand):
    help = "Clear transactional data and seed realistic test data for the ERP."

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
            self.stdout.write(self.style.HTTP_INFO("\n[1/3] Clearing transactional data..."))
            self._clear_data()

            self.stdout.write(self.style.HTTP_INFO("\n[2/3] Seeding RBAC (branches, departments, roles, users)..."))
            warehouses = self._seed_rbac()

            self.stdout.write(self.style.HTTP_INFO("\n[3/3] Seeding operational data..."))
            self._seed_operational(warehouses)

        self.stdout.write(self.style.SUCCESS("\n=== Seed completed successfully! ==="))
        self.stdout.write(f"\nTest users (password: {PASSWORD}):")
        for u in ["admin_erp", "finance_mgr", "sales_mgr", "purchase_officer", "warehouse_staff"]:
            self.stdout.write(f"  {u}")

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
        """Return (country, city) using first existing records or creating test ones."""
        from core.models import Country, Region, City

        country = Country.objects.filter(is_active=True).first()
        if not country:
            country, _ = Country.objects.get_or_create(
                code="TST",
                defaults=dict(name="Test Country", iso_code="TC", is_active=True),
            )

        city = City.objects.filter(country=country).first()
        if not city:
            region = Region.objects.filter(country=country).first()
            if not region:
                region, _ = Region.objects.get_or_create(
                    name="Test Region", country=country,
                    defaults=dict(is_active=True),
                )
            city, _ = City.objects.get_or_create(
                name="Test City", country=country,
                defaults=dict(region=region, is_active=True),
            )
        return country, city

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def _clear_data(self):
        from rbac.models import AuditLog, UserProfile
        from products.models import (
            ProductVariant, ProductPriceHistory, ProductPrice,
            Product, PriceList, Brand, ProductCategory,
        )
        from inventory.models import StockMovement, StockBatch, Stock, WarehouseSection, Warehouse
        from sales.models import SalesOrderLine, SalesOrder, Customer, TaxRate
        from purchasing.models import (
            PurchaseReceiptLine, PurchaseReceipt, PurchaseOrderLine, PurchaseOrder, Vendor,
        )
        from accounting.models import JournalLine, JournalEntry, Payment, Bill, Invoice

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
        self._safe_delete(ProductVariant)
        self._safe_delete(ProductPriceHistory)
        self._safe_delete(ProductPrice)
        self._safe_delete(Product)
        self._safe_delete(PriceList)
        self._safe_delete(Brand)
        self._safe_delete(ProductCategory)
        self._safe_delete(TaxRate)
        self._safe_delete(Customer)
        self._safe_delete(Vendor)
        self._safe_delete(UserProfile)
        # Delete non-superuser users
        self._safe_delete(User, is_superuser=False)

    # ------------------------------------------------------------------
    # RBAC seed
    # ------------------------------------------------------------------

    def _seed_rbac(self):
        """Returns a list of created Warehouse objects (seeded here so users can be assigned)."""
        from rbac.models import (
            Branch, Department, Role, ModulePermission, UserProfile, MODULE_CHOICES,
        )
        from inventory.models import Warehouse

        all_modules = [mk for mk, _ in MODULE_CHOICES]

        # Accounting modules
        ACCT = ["accounting.invoice", "accounting.bill", "accounting.payment", "accounting.journalentry"]
        # Sales modules
        SALES = ["sales.customer", "sales.salesorder"]
        # Purchasing modules
        PURCH = ["purchasing.purchaseorder", "purchasing.vendor", "purchasing.purchasereceipt"]
        # Inventory modules
        INV = ["inventory.stock", "inventory.stockbatch", "inventory.stockmovement",
               "inventory.warehouse", "inventory.warehousesection"]
        # Product modules
        PROD = ["products.product", "products.unit", "products.brand",
                "products.productcategory", "products.pricelist",
                "products.productattribute", "products.productattributevalue",
                "products.productvariant", "products.productpricehistory"]

        def _full(**extra):
            return dict(can_view=True, can_create=True, can_edit=True,
                        can_delete=True, can_approve=True, can_export=True, can_print=True, **extra)

        def _view_only():
            return dict(can_view=True, can_create=False, can_edit=False,
                        can_delete=False, can_approve=False, can_export=True, can_print=False)

        role_defs = [
            {
                "code": "administrator", "name": "Administrator",
                "priority": 1, "is_system_role": True,
                "perms": {mk: _full() for mk in all_modules},
            },
            {
                "code": "finance_manager", "name": "Finance Manager",
                "priority": 2,
                "perms": {
                    **{mk: _view_only() for mk in all_modules},
                    **{mk: _full() for mk in ACCT},
                },
            },
            {
                "code": "sales_manager", "name": "Sales Manager",
                "priority": 3,
                "perms": {
                    **{mk: _view_only() for mk in all_modules},
                    **{mk: _full() for mk in SALES},
                },
            },
            {
                "code": "purchasing_officer", "name": "Purchasing Officer",
                "priority": 4,
                "perms": {
                    **{mk: _view_only() for mk in all_modules},
                    **{mk: _full() for mk in PURCH},
                },
            },
            {
                "code": "warehouse_staff", "name": "Warehouse Staff",
                "priority": 5,
                "perms": {
                    **{mk: _view_only() for mk in PROD},
                    "inventory.stock": dict(can_view=True, can_create=False, can_edit=True,
                                           can_delete=False, can_approve=False, can_export=True, can_print=False),
                    "inventory.stockbatch": dict(can_view=True, can_create=False, can_edit=True,
                                                 can_delete=False, can_approve=False, can_export=True, can_print=False),
                    "inventory.stockmovement": dict(can_view=True, can_create=True, can_edit=False,
                                                    can_delete=False, can_approve=False, can_export=True, can_print=False),
                    "inventory.warehouse": _view_only(),
                    "inventory.warehousesection": _view_only(),
                },
            },
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
                ModulePermission.objects.update_or_create(
                    role=role, module=mk, defaults=perm_kw,
                )
        self.stdout.write(f"  Created {len(roles)} roles with module permissions")

        # --- Branches ---
        hq, _ = Branch.objects.get_or_create(
            code="HQ",
            defaults=dict(name="HQ Main Branch", address="100 Main Street",
                          is_main=True, is_active=True),
        )
        north, _ = Branch.objects.get_or_create(
            code="NB",
            defaults=dict(name="North Branch", address="50 North Avenue",
                          is_main=False, is_active=True),
        )

        # --- Departments ---
        fin_dept, _ = Department.objects.get_or_create(
            code="FIN", defaults=dict(name="Finance", is_active=True),
        )
        ops_dept, _ = Department.objects.get_or_create(
            code="OPS", defaults=dict(name="Operations", is_active=True),
        )
        sal_dept, _ = Department.objects.get_or_create(
            code="SAL", defaults=dict(name="Sales & Marketing", is_active=True),
        )

        # --- Warehouses (created here so profiles can reference them) ---
        wh_main = Warehouse.objects.create(
            name="Main Warehouse", code="WH-MAIN",
            warehouse_type="main", is_active=True,
        )
        wh_north = Warehouse.objects.create(
            name="North Warehouse", code="WH-NORTH",
            warehouse_type="branch", is_active=True,
        )
        wh_cold = Warehouse.objects.create(
            name="Cold Storage", code="WH-COLD",
            warehouse_type="cold_storage", is_active=True,
        )
        warehouses = [wh_main, wh_north, wh_cold]
        self.stdout.write(f"  Created {len(warehouses)} warehouses")

        # Assign warehouses to branches
        hq.warehouses.set([wh_main, wh_cold])
        north.warehouses.set([wh_north])

        # --- Test Users ---
        user_defs = [
            dict(username="admin_erp",        first_name="Adam",  last_name="Wright",
                 email="admin_erp@test.erp",   role="administrator",     dept=fin_dept,
                 branch=hq,    approval_level=3, warehouses=[],           employee_id="EMP-001"),
            dict(username="finance_mgr",      first_name="Fiona", last_name="Chen",
                 email="finance_mgr@test.erp", role="finance_manager",   dept=fin_dept,
                 branch=hq,    approval_level=3, warehouses=[],           employee_id="EMP-002"),
            dict(username="sales_mgr",        first_name="Sam",   last_name="Torres",
                 email="sales_mgr@test.erp",   role="sales_manager",     dept=sal_dept,
                 branch=hq,    approval_level=2, warehouses=[],           employee_id="EMP-003"),
            dict(username="purchase_officer", first_name="Paul",  last_name="King",
                 email="purchase_officer@test.erp", role="purchasing_officer", dept=ops_dept,
                 branch=north, approval_level=2, warehouses=[wh_north],   employee_id="EMP-004"),
            dict(username="warehouse_staff",  first_name="Wendy", last_name="Park",
                 email="warehouse_staff@test.erp", role="warehouse_staff", dept=ops_dept,
                 branch=north, approval_level=1, warehouses=[wh_main, wh_north], employee_id="EMP-005"),
        ]

        for ud in user_defs:
            user = User.objects.create_user(
                username=ud["username"],
                email=ud["email"],
                password=PASSWORD,
                first_name=ud["first_name"],
                last_name=ud["last_name"],
                is_staff=True,
            )
            profile = UserProfile.objects.create(
                user=user,
                role=roles[ud["role"]],
                department=ud["dept"],
                branch=ud["branch"],
                approval_level=ud["approval_level"],
                employee_id=ud["employee_id"],
            )
            if ud["warehouses"]:
                profile.warehouses.set(ud["warehouses"])

        self.stdout.write(f"  Created {len(user_defs)} test users")
        return warehouses

    # ------------------------------------------------------------------
    # Operational seed
    # ------------------------------------------------------------------

    def _seed_operational(self, warehouses):
        wh_main, wh_north, wh_cold = warehouses

        country, city = self._get_or_create_country_city()

        products = self._seed_products()
        tax_rate = self._seed_tax_rates()
        customers = self._seed_customers(country, city)
        vendors = self._seed_vendors(country, city)
        self._seed_purchase_orders(vendors, products, wh_main)
        self._seed_sales_orders(customers, products, wh_main, tax_rate)

    def _seed_products(self):
        from products.models import Brand, ProductCategory, Product
        from products.models import Unit  # noqa (already preserved)

        # Get a unit for products (use first available or skip)
        unit = Unit.objects.filter(is_active=True).first()

        # Categories (flat)
        cat_map = {}
        for cat_name in ("Electronics", "Furniture", "Office", "Networking"):
            cat, _ = ProductCategory.objects.get_or_create(name=cat_name)
            cat_map[cat_name] = cat

        # Brands
        brand_map = {}
        for brand_name in ("TechBrand", "AudioPro", "StorageCo", "OfficeWorld",
                           "PrintTech", "NetGear"):
            brand, _ = Brand.objects.get_or_create(name=brand_name)
            brand_map[brand_name] = brand

        products = []
        for name, cat_name, brand_name, price, cost in PRODUCT_SEED:
            product = Product.objects.create(
                name=name,
                category=cat_map[cat_name],
                brand=brand_map[brand_name],
                price=price,
                cost=cost,
                base_unit=unit,
                active=True,
            )
            products.append(product)

        self.stdout.write(f"  Created {len(products)} products")
        return products

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
                name=name,
                defaults=dict(rate=rate, tax_type=tax_type, is_active=True),
            )
            created.append(tr)
        self.stdout.write(f"  Created {len(created)} tax rates")
        return created[0]  # return standard VAT for use in orders

    def _seed_customers(self, country, city):
        from sales.models import Customer

        customers = []
        for i, (display_name, email, ctype, address) in enumerate(CUSTOMER_SEED):
            is_biz = (ctype == "business")
            cust = Customer.objects.create(
                customer_type=ctype,
                first_name="" if is_biz else display_name.split()[0],
                last_name="" if is_biz else " ".join(display_name.split()[1:]),
                full_name=display_name,
                company_name=display_name if is_biz else "",
                email=email,
                phone=f"+1-555-{1000 + i:04d}",
                billing_address_line1=address,
                billing_country=country,
                billing_city=city,
                billing_postal_code=f"1000{i}",
                payment_type="credit",
                credit_limit=Decimal("10000.00"),
            )
            customers.append(cust)

        self.stdout.write(f"  Created {len(customers)} customers")
        return customers

    def _seed_vendors(self, country, city):
        from purchasing.models import Vendor

        vendors = []
        for name, code, email, address in VENDOR_SEED:
            v = Vendor.objects.create(
                name=name,
                code=code,
                email=email,
                address_line1=address,
                country=country,
                city=city,
                postal_code="10001",
                payment_terms="net30",
                is_active=True,
            )
            vendors.append(v)

        self.stdout.write(f"  Created {len(vendors)} vendors")
        return vendors

    def _seed_purchase_orders(self, vendors, products, warehouse):
        from purchasing.models import PurchaseOrder, PurchaseOrderLine
        from accounting.models import Bill
        from inventory.models import Stock

        today = date.today()

        # PO 1 – Draft (no lines received)
        po1 = PurchaseOrder.objects.create(
            vendor=vendors[0],
            warehouse=warehouse,
            status="draft",
            expected_date=today + timedelta(days=14),
            payment_terms="net30",
        )
        for product in products[:4]:
            PurchaseOrderLine.objects.create(
                order=po1, product=product,
                quantity=Decimal("10"), price=product.cost,
                received_quantity=Decimal("0"),
            )

        # PO 2 – Confirmed
        po2 = PurchaseOrder.objects.create(
            vendor=vendors[1],
            warehouse=warehouse,
            status="confirmed",
            expected_date=today + timedelta(days=7),
            payment_terms="net30",
        )
        for product in products[4:8]:
            PurchaseOrderLine.objects.create(
                order=po2, product=product,
                quantity=Decimal("5"), price=product.cost,
                received_quantity=Decimal("0"),
            )

        # PO 3 – Done (fully received); also seed stock + bill
        po3 = PurchaseOrder.objects.create(
            vendor=vendors[2],
            warehouse=warehouse,
            status="done",
            expected_date=today - timedelta(days=7),
            payment_terms="net30",
        )
        stock_qty = Decimal("20")
        for product in products[8:14]:
            PurchaseOrderLine.objects.create(
                order=po3, product=product,
                quantity=stock_qty, price=product.cost,
                received_quantity=stock_qty,
            )
            # Seed stock directly
            Stock.objects.get_or_create(
                product=product, warehouse=warehouse,
                defaults=dict(quantity=stock_qty, unit_quantity=1),
            )

        # Also seed stock for the remaining products (so SOs can be fulfilled)
        for product in products[14:]:
            Stock.objects.get_or_create(
                product=product, warehouse=warehouse,
                defaults=dict(quantity=stock_qty, unit_quantity=1),
            )

        # Bill for the done PO
        po3.calculate_totals()
        PurchaseOrder.objects.filter(pk=po3.pk).update(
            subtotal=po3.subtotal, total_amount=po3.total_amount
        )
        Bill.objects.create(
            purchase_order=po3,
            vendor=vendors[2],
            bill_date=today - timedelta(days=5),
            due_date=today + timedelta(days=25),
            total_amount=po3.total_amount,
            net_amount=po3.total_amount,
            status="received",
        )

        self.stdout.write("  Created 3 purchase orders + 1 bill")

    def _seed_sales_orders(self, customers, products, warehouse, tax_rate):
        from sales.models import SalesOrder, SalesOrderLine
        from accounting.models import Invoice

        today = date.today()

        so_defs = [
            # (customer_idx, status, product_slice, qty)
            (0, "draft",     slice(0, 3),  2),
            (1, "confirmed", slice(3, 6),  3),
            (2, "confirmed", slice(6, 9),  1),
            (3, "completed", slice(9, 12), 5),
            (4, "cancelled", slice(0, 2),  2),
        ]

        for cust_idx, status, prod_slice, qty in so_defs:
            so = SalesOrder.objects.create(
                customer=customers[cust_idx],
                warehouse=warehouse,
                status=status,
                expected_delivery_date=today + timedelta(days=7),
                tax_rate=tax_rate,
            )
            subtotal = Decimal("0")
            for product in products[prod_slice]:
                SalesOrderLine.objects.create(
                    order=so, product=product,
                    quantity=qty, price=product.price,
                )
                subtotal += product.price * qty

            # Update real DB fields (total_amount is a @property — not a DB column)
            tax_amt = subtotal * (tax_rate.rate / Decimal("100"))
            SalesOrder.objects.filter(pk=so.pk).update(
                subtotal=subtotal,
                tax_amount=tax_amt,
            )

            # Create invoice for completed order
            if status == "completed":
                invoice_total = subtotal + tax_amt
                Invoice.objects.create(
                    sales_order=so,
                    customer=so.customer,
                    invoice_date=today - timedelta(days=3),
                    due_date=today + timedelta(days=27),
                    total_amount=invoice_total,
                    net_amount=invoice_total,
                    status="sent",
                )

        self.stdout.write("  Created 5 sales orders + 1 invoice")
