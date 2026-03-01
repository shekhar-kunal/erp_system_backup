"""
populate_sample_data.py
-----------------------
Creates realistic sample data across all ERP modules for testing.

Usage:
    python manage.py populate_sample_data            # create sample data
    python manage.py populate_sample_data --clear    # wipe & recreate
"""

from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

User = get_user_model()


class Command(BaseCommand):
    help = 'Populate the ERP system with realistic sample data for testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing sample data before creating new data',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['clear']:
            self._clear_data()

        self.stdout.write(self.style.MIGRATE_HEADING('\nCreating ERP sample data...\n'))

        admin = self._ensure_admin()

        self.stdout.write('  [1/9] Geography (countries, regions, cities)...')
        usa, uk, uae = self._create_geography()

        self.stdout.write('  [2/9] Units of measure...')
        units = self._create_units()

        self.stdout.write('  [3/9] Product categories...')
        cats = self._create_categories()

        self.stdout.write('  [4/9] Products...')
        products = self._create_products(cats, units)

        self.stdout.write('  [5/9] Warehouses & sections...')
        warehouses = self._create_warehouses()

        self.stdout.write('  [6/9] Stock entries...')
        self._create_stock(products, warehouses, units)

        self.stdout.write('  [7/9] Vendors...')
        vendors = self._create_vendors(usa, uk, uae, admin)

        self.stdout.write('  [8/9] Customers...')
        customers = self._create_customers(usa, uk, uae)

        self.stdout.write('  [9/9] Purchase & sales orders...')
        self._create_purchase_orders(vendors, products, warehouses, admin)
        self._create_sales_orders(customers, products, warehouses)

        self._print_summary(products, vendors, customers, warehouses)

    # ------------------------------------------------------------------
    # Admin user
    # ------------------------------------------------------------------

    def _ensure_admin(self):
        user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@erp-demo.com',
                'first_name': 'Admin',
                'last_name': 'User',
                'is_staff': True,
                'is_superuser': True,
            },
        )
        if created:
            user.set_password('admin123')
            user.save()
        return user

    # ------------------------------------------------------------------
    # Geography
    # ------------------------------------------------------------------

    def _create_geography(self):
        from core.models import Country, Region, City

        usa, _ = Country.objects.get_or_create(
            iso_code='US',
            defaults=dict(name='United States', code='USA', phone_code='+1',
                          currency='USD', currency_symbol='$', is_active=True),
        )
        uk, _ = Country.objects.get_or_create(
            iso_code='GB',
            defaults=dict(name='United Kingdom', code='GBR', phone_code='+44',
                          currency='GBP', currency_symbol='£', is_active=True),
        )
        uae, _ = Country.objects.get_or_create(
            iso_code='AE',
            defaults=dict(name='United Arab Emirates', code='ARE', phone_code='+971',
                          currency='AED', currency_symbol='د.إ', is_active=True),
        )

        # Regions – Region.save() calls full_clean(), so use get_or_create safely
        ca, _ = Region.objects.get_or_create(name='California', country=usa,
                                              defaults=dict(code='CA', is_active=True))
        ny, _ = Region.objects.get_or_create(name='New York', country=usa,
                                              defaults=dict(code='NY', is_active=True))
        eng, _ = Region.objects.get_or_create(name='England', country=uk,
                                               defaults=dict(code='ENG', is_active=True))
        dxb_region, _ = Region.objects.get_or_create(name='Dubai', country=uae,
                                                      defaults=dict(code='DXB', is_active=True))

        # Cities
        City.objects.get_or_create(
            name='Los Angeles', country=usa,
            defaults=dict(region=ca, state='California'),
        )
        City.objects.get_or_create(
            name='New York City', country=usa,
            defaults=dict(region=ny, state='New York'),
        )
        City.objects.get_or_create(
            name='London', country=uk,
            defaults=dict(region=eng, state='England'),
        )
        City.objects.get_or_create(
            name='Dubai', country=uae,
            defaults=dict(region=dxb_region, state='Dubai'),
        )

        return usa, uk, uae

    # ------------------------------------------------------------------
    # Units
    # ------------------------------------------------------------------

    def _create_units(self):
        from products.models import Unit

        def u(code, name, short, utype='standard'):
            obj, _ = Unit.objects.get_or_create(
                code=code,
                defaults=dict(name=name, short_name=short, unit_type=utype, is_active=True),
            )
            return obj

        return {
            'pcs': u('PCS', 'Pieces', 'pcs'),
            'kg':  u('KG',  'Kilogram', 'kg',  'weight'),
            'ltr': u('LTR', 'Litre', 'ltr',    'volume'),
            'box': u('BOX', 'Box', 'box',       'packaging'),
            'ctn': u('CTN', 'Carton', 'ctn',    'packaging'),
            'mtr': u('MTR', 'Metre', 'm',       'length'),
        }

    # ------------------------------------------------------------------
    # Product Categories (MPTT)
    # ------------------------------------------------------------------

    def _create_categories(self):
        from products.models import ProductCategory

        def cat(name, parent=None):
            slug = name.lower().replace(' ', '-').replace('&', 'and').replace('/', '-')
            obj, _ = ProductCategory.objects.get_or_create(
                name=name,
                defaults=dict(slug=slug, parent=parent, active=True, position=0),
            )
            return obj

        electronics  = cat('Electronics')
        computers    = cat('Computers & Laptops', electronics)
        phones       = cat('Mobile Phones', electronics)
        accessories  = cat('Accessories', electronics)

        food         = cat('Food & Beverages')
        dairy        = cat('Dairy Products', food)
        bakery       = cat('Bakery', food)
        beverages    = cat('Beverages', food)

        office       = cat('Office Supplies')
        furniture    = cat('Office Furniture', office)

        clothing     = cat('Clothing & Apparel')

        # Rebuild MPTT tree to fix lft/rght/level values
        ProductCategory.objects.rebuild()

        return {
            'electronics': electronics, 'computers': computers,
            'phones': phones, 'accessories': accessories,
            'food': food, 'dairy': dairy, 'bakery': bakery, 'beverages': beverages,
            'office': office, 'furniture': furniture,
            'clothing': clothing,
        }

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def _create_products(self, cats, units):
        from products.models import Product

        specs = [
            # (name,                           category,        unit,  price,   cost,   type)
            ('Laptop Pro 15"',                 'computers',     'pcs', 1299.99,  900.00, 'ST'),
            ('Gaming Laptop X500',             'computers',     'pcs', 1599.99, 1100.00, 'ST'),
            ('iPhone 14 Pro',                  'phones',        'pcs',  999.99,  650.00, 'ST'),
            ('Samsung Galaxy S23',             'phones',        'pcs',  849.99,  560.00, 'ST'),
            ('Wireless Mouse',                 'accessories',   'pcs',   29.99,   14.00, 'ST'),
            ('USB-C Cable 2m',                 'accessories',   'pcs',   14.99,    5.50, 'ST'),
            ('Bluetooth Headphones',           'accessories',   'pcs',   89.99,   45.00, 'ST'),
            ('Fresh Whole Milk 1L',            'dairy',         'ltr',    2.99,    1.80, 'ST'),
            ('Greek Yogurt 500g',              'dairy',         'pcs',    3.49,    2.00, 'ST'),
            ('Whole Wheat Bread Loaf',         'bakery',        'pcs',    3.99,    2.20, 'ST'),
            ('Premium Ground Coffee 500g',     'beverages',     'pcs',   18.99,   10.00, 'ST'),
            ('A4 Copy Paper (500 sheets)',     'office',        'box',    8.99,    5.50, 'ST'),
            ('Ergonomic Office Chair',         'furniture',     'pcs',  349.99,  200.00, 'ST'),
            ('Executive Desk',                 'furniture',     'pcs',  699.99,  400.00, 'ST'),
            ('Classic White T-Shirt',          'clothing',      'pcs',   19.99,    7.50, 'ST'),
        ]

        products = {}
        for name, cat_key, unit_key, price, cost, ptype in specs:
            obj, _ = Product.objects.get_or_create(
                name=name,
                defaults=dict(
                    category=cats[cat_key],
                    base_unit=units[unit_key],
                    price=Decimal(str(price)),
                    cost=Decimal(str(cost)),
                    product_type=ptype,
                    active=True,
                ),
            )
            products[name] = obj

        return products

    # ------------------------------------------------------------------
    # Warehouses & Sections
    # ------------------------------------------------------------------

    def _create_warehouses(self):
        from inventory.models import Warehouse, WarehouseSection

        main, _ = Warehouse.objects.get_or_create(
            code='WH-001',
            defaults=dict(
                name='Main Warehouse',
                warehouse_type='main',
                temperature_zone='ambient',
                address='100 Industrial Park, Los Angeles, CA',
                capacity=Decimal('50000'),
                is_active=True,
            ),
        )
        cold, _ = Warehouse.objects.get_or_create(
            code='WH-002',
            defaults=dict(
                name='Cold Storage Facility',
                warehouse_type='cold_storage',
                temperature_zone='cold',
                address='200 Cold Chain Ave, Los Angeles, CA',
                capacity=Decimal('10000'),
                is_active=True,
            ),
        )

        # Sections for main warehouse
        section_defs = [
            ('A', '1', '1', '01'), ('A', '1', '1', '02'),
            ('A', '1', '2', '01'), ('B', '2', '1', '01'),
            ('B', '2', '1', '02'), ('C', '3', '1', '01'),
        ]
        main_sections = {}
        for zone, aisle, rack, bin_ in section_defs:
            sec, _ = WarehouseSection.objects.get_or_create(
                warehouse=main, zone=zone, aisle=aisle, rack=rack, bin=bin_,
                defaults=dict(is_active=True),
            )
            key = f'{zone}{aisle}{rack}{bin_}'
            main_sections[key] = sec

        # Sections for cold storage
        cold_sec, _ = WarehouseSection.objects.get_or_create(
            warehouse=cold, zone='C', aisle='1', rack='1', bin='01',
            defaults=dict(is_active=True),
        )

        return {'main': main, 'cold': cold,
                'main_sections': main_sections, 'cold_section': cold_sec}

    # ------------------------------------------------------------------
    # Stock
    # ------------------------------------------------------------------

    def _create_stock(self, products, warehouses, units):
        from inventory.models import Stock

        main = warehouses['main']
        cold = warehouses['cold']

        stock_data = [
            # (product_name,              wh,   qty,    reorder, section_key)
            ('Laptop Pro 15"',            main, 45,     10,      'A1101'),
            ('Gaming Laptop X500',        main, 30,     8,       'A1101'),
            ('iPhone 14 Pro',             main, 80,     20,      'A1102'),
            ('Samsung Galaxy S23',        main, 65,     15,      'A1102'),
            ('Wireless Mouse',            main, 200,    50,      'A1201'),
            ('USB-C Cable 2m',            main, 350,    80,      'A1201'),
            ('Bluetooth Headphones',      main, 55,     15,      'B2101'),
            ('Fresh Whole Milk 1L',       cold, 500,   100,      None),
            ('Greek Yogurt 500g',         cold, 300,    60,      None),
            ('Whole Wheat Bread Loaf',    main, 120,    30,      'B2102'),
            ('Premium Ground Coffee 500g', main, 90,   20,      'B2102'),
            ('A4 Copy Paper (500 sheets)', main, 400,  80,      'C3101'),
            ('Ergonomic Office Chair',    main, 25,     5,       'C3101'),
            ('Executive Desk',            main, 12,     3,       'C3101'),
            ('Classic White T-Shirt',     main, 180,   40,      'B2101'),
        ]

        main_sections = warehouses['main_sections']

        for name, wh, qty, reorder, sec_key in stock_data:
            product = products.get(name)
            if not product:
                continue

            section = main_sections.get(sec_key) if sec_key and wh == main else None

            Stock.objects.update_or_create(
                product=product,
                warehouse=wh,
                section=section,
                defaults=dict(
                    quantity=Decimal(str(qty)),
                    reorder_level=Decimal(str(reorder)),
                    unit=product.base_unit,
                ),
            )

    # ------------------------------------------------------------------
    # Vendors
    # ------------------------------------------------------------------

    def _create_vendors(self, usa, uk, uae, admin_user):
        from core.models import City
        from purchasing.models import Vendor

        la     = City.objects.filter(name='Los Angeles').first()
        nyc    = City.objects.filter(name='New York City').first()
        london = City.objects.filter(name='London').first()
        dubai  = City.objects.filter(name='Dubai').first()

        data = [
            dict(
                code='VEN-001', name='TechSupply Co.',
                contact_person='Michael Chen', email='sales@techsupply.com',
                phone='+1-310-555-0100', address_line1='500 Silicon Blvd',
                country=usa, city=la, postal_code='90001',
                payment_terms='net30', currency='USD',
                quality_rating=Decimal('4.5'), is_preferred=True,
            ),
            dict(
                code='VEN-002', name='Global Foods Ltd',
                contact_person='Emma Williams', email='orders@globalfoods.co.uk',
                phone='+44-20-5555-0200', address_line1='12 Aldgate High St',
                country=uk, city=london, postal_code='EC3N 1AL',
                payment_terms='net15', currency='GBP',
                quality_rating=Decimal('4.2'), is_preferred=False,
            ),
            dict(
                code='VEN-003', name='Office Essentials FZCO',
                contact_person='Ahmed Al Rashid', email='info@officeessentials.ae',
                phone='+971-4-555-0300', address_line1='Unit 7, Jebel Ali Free Zone',
                country=uae, city=dubai, postal_code='00000',
                payment_terms='net30', currency='USD',
                quality_rating=Decimal('3.8'), is_preferred=False,
            ),
            dict(
                code='VEN-004', name='Fashion Forward Inc.',
                contact_person='Sarah Johnson', email='wholesale@fashionforward.com',
                phone='+1-212-555-0400', address_line1='88 Garment District Ave',
                country=usa, city=nyc, postal_code='10018',
                payment_terms='net60', currency='USD',
                quality_rating=Decimal('4.0'), is_preferred=False,
            ),
        ]

        vendors = {}
        for d in data:
            obj, _ = Vendor.objects.get_or_create(
                code=d.pop('code'),
                defaults=dict(is_active=True, created_by=admin_user, **d),
            )
            vendors[obj.code] = obj

        return vendors

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------

    def _create_customers(self, usa, uk, uae):
        from core.models import City
        from sales.models import Customer

        la = City.objects.filter(name='Los Angeles').first()
        nyc = City.objects.filter(name='New York City').first()
        london = City.objects.filter(name='London').first()
        dubai = City.objects.filter(name='Dubai').first()

        data = [
            # Business customers
            dict(
                email='procurement@acmecorp.com',
                customer_type=Customer.CustomerType.BUSINESS,
                company_name='Acme Corporation', full_name='Acme Corporation',
                phone='+1-310-555-1001',
                billing_address_line1='1234 Corporate Blvd',
                billing_postal_code='90001',
                billing_country=usa, billing_city=la,
                pricing_tier='wholesale', credit_limit=Decimal('50000'),
                payment_type=Customer.PaymentType.CREDIT, credit_days=30,
            ),
            dict(
                email='orders@betatech.co.uk',
                customer_type=Customer.CustomerType.BUSINESS,
                company_name='Beta Tech Solutions Ltd', full_name='Beta Tech Solutions Ltd',
                phone='+44-20-5555-2002',
                billing_address_line1='45 Tech Park Road',
                billing_postal_code='EC1A 1BB',
                billing_country=uk, billing_city=london,
                pricing_tier='wholesale', credit_limit=Decimal('30000'),
                payment_type=Customer.PaymentType.CREDIT, credit_days=45,
            ),
            dict(
                email='info@deltatrade.ae',
                customer_type=Customer.CustomerType.BUSINESS,
                company_name='Delta Trading LLC', full_name='Delta Trading LLC',
                phone='+971-4-555-3003',
                billing_address_line1='Office 12, Dubai Business Bay',
                billing_postal_code='00000',
                billing_country=uae, billing_city=dubai,
                pricing_tier='distributor', credit_limit=Decimal('100000'),
                payment_type=Customer.PaymentType.CREDIT, credit_days=60,
            ),
            # Individual customers
            dict(
                email='alice.smith@example.com',
                customer_type=Customer.CustomerType.INDIVIDUAL,
                first_name='Alice', last_name='Smith',
                full_name='Alice Smith', phone='+1-212-555-4004',
                billing_address_line1='78 Park Avenue',
                billing_postal_code='10016',
                billing_country=usa, billing_city=nyc,
                pricing_tier='retail', payment_type=Customer.PaymentType.PAY_NOW,
            ),
            dict(
                email='bob.johnson@example.co.uk',
                customer_type=Customer.CustomerType.INDIVIDUAL,
                first_name='Bob', last_name='Johnson',
                full_name='Bob Johnson', phone='+44-20-5555-5005',
                billing_address_line1='22 Baker Street',
                billing_postal_code='W1U 3BW',
                billing_country=uk, billing_city=london,
                pricing_tier='retail', payment_type=Customer.PaymentType.PAY_NOW,
            ),
            dict(
                email='carol.white@example.com',
                customer_type=Customer.CustomerType.INDIVIDUAL,
                first_name='Carol', last_name='White',
                full_name='Carol White', phone='+1-310-555-6006',
                billing_address_line1='500 Sunset Strip',
                billing_postal_code='90028',
                billing_country=usa, billing_city=la,
                pricing_tier='retail', payment_type=Customer.PaymentType.PAY_NOW,
            ),
        ]

        customers = {}
        for d in data:
            email = d.get('email')
            try:
                obj, _ = Customer.objects.get_or_create(
                    email=email,
                    defaults=dict(is_active=True, **d),
                )
                customers[email] = obj
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'    Skipped customer {email}: {e}'))

        return customers

    # ------------------------------------------------------------------
    # Purchase Orders
    # ------------------------------------------------------------------

    def _create_purchase_orders(self, vendors, products, warehouses, admin_user):
        from purchasing.models import PurchaseOrder, PurchaseOrderLine

        main = warehouses['main']
        cold = warehouses['cold']
        today = date.today()

        po_specs = [
            # (po_number,        vendor_code, wh,   status,      expected_delta, lines)
            ('PO-SAMPLE-0001', 'VEN-001', main, 'confirmed',  7,  [
                ('Laptop Pro 15"',        10, Decimal('900.00')),
                ('Gaming Laptop X500',     5, Decimal('1100.00')),
                ('iPhone 14 Pro',         20, Decimal('650.00')),
            ]),
            ('PO-SAMPLE-0002', 'VEN-002', cold, 'done',      -5,  [
                ('Fresh Whole Milk 1L',  500, Decimal('1.80')),
                ('Greek Yogurt 500g',    300, Decimal('2.00')),
                ('Whole Wheat Bread Loaf', 200, Decimal('2.20')),
            ]),
            ('PO-SAMPLE-0003', 'VEN-003', main, 'draft',     14,  [
                ('A4 Copy Paper (500 sheets)',  100, Decimal('5.50')),
                ('Ergonomic Office Chair',       10, Decimal('200.00')),
            ]),
            ('PO-SAMPLE-0004', 'VEN-004', main, 'partial',   10,  [
                ('Classic White T-Shirt',  200, Decimal('7.50')),
                ('Wireless Mouse',         100, Decimal('14.00')),
            ]),
        ]

        for po_number, vendor_code, wh, status, exp_delta, lines in po_specs:
            po, created = PurchaseOrder.objects.get_or_create(
                po_number=po_number,
                defaults=dict(
                    vendor=vendors[vendor_code],
                    warehouse=wh,
                    status=status,
                    expected_date=today + timedelta(days=exp_delta),
                    created_by=admin_user,
                    currency='USD',
                    payment_terms='net30',
                ),
            )

            if created:
                for product_name, qty, price in lines:
                    product = products.get(product_name)
                    if not product:
                        continue
                    line = PurchaseOrderLine(
                        order=po,
                        product=product,
                        quantity=Decimal(str(qty)),
                        price=price,
                        net_price=price,
                    )
                    line.save()

                # Recalculate PO totals
                try:
                    po.calculate_totals()
                    po.save(update_fields=['subtotal', 'total_amount', 'tax_amount'])
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Sales Orders
    # ------------------------------------------------------------------

    def _create_sales_orders(self, customers, products, warehouses):
        from sales.models import SalesOrder, SalesOrderLine

        main = warehouses['main']
        today = date.today()

        emails = list(customers.keys())
        if len(emails) < 4:
            return

        acme   = customers.get('procurement@acmecorp.com')
        alice  = customers.get('alice.smith@example.com')
        beta   = customers.get('orders@betatech.co.uk')
        delta  = customers.get('info@deltatrade.ae')
        bob    = customers.get('bob.johnson@example.co.uk')

        so_specs = [
            ('SO-SAMPLE-0001', acme,  main, 'confirmed', 5, [
                ('Laptop Pro 15"',         3, Decimal('1299.99')),
                ('Ergonomic Office Chair', 5, Decimal('349.99')),
                ('Wireless Mouse',         3, Decimal('29.99')),
            ]),
            ('SO-SAMPLE-0002', alice, main, 'completed', -2, [
                ('Premium Ground Coffee 500g', 2, Decimal('18.99')),
                ('Whole Wheat Bread Loaf',     3, Decimal('3.99')),
                ('Classic White T-Shirt',      2, Decimal('19.99')),
            ]),
            ('SO-SAMPLE-0003', beta,  main, 'draft',     7, [
                ('iPhone 14 Pro',          5, Decimal('999.99')),
                ('USB-C Cable 2m',        10, Decimal('14.99')),
                ('Bluetooth Headphones',   3, Decimal('89.99')),
            ]),
            ('SO-SAMPLE-0004', delta, main, 'partial',   3, [
                ('A4 Copy Paper (500 sheets)', 50, Decimal('8.99')),
                ('Wireless Mouse',             20, Decimal('29.99')),
                ('Ergonomic Office Chair',      3, Decimal('349.99')),
            ]),
            ('SO-SAMPLE-0005', bob,   main, 'confirmed', 4, [
                ('Samsung Galaxy S23',     1, Decimal('849.99')),
                ('USB-C Cable 2m',         2, Decimal('14.99')),
            ]),
        ]

        for order_number, customer, wh, status, exp_delta, lines in so_specs:
            if not customer:
                continue

            so, created = SalesOrder.objects.get_or_create(
                order_number=order_number,
                defaults=dict(
                    customer=customer,
                    warehouse=wh,
                    status=status,
                    expected_delivery_date=today + timedelta(days=exp_delta),
                ),
            )

            if created:
                for product_name, qty, price in lines:
                    product = products.get(product_name)
                    if not product:
                        continue
                    delivered = qty if status == 'completed' else (qty // 2 if status == 'partial' else 0)
                    SalesOrderLine.objects.create(
                        order=so,
                        product=product,
                        quantity=qty,
                        price=price,
                        delivered_quantity=delivered,
                    )

    # ------------------------------------------------------------------
    # Clear sample data
    # ------------------------------------------------------------------

    def _clear_data(self):
        self.stdout.write(self.style.WARNING('  Clearing existing sample data...'))
        from purchasing.models import PurchaseOrder, PurchaseOrderLine
        from sales.models import SalesOrder, SalesOrderLine
        from accounting.models import Invoice, Bill, Payment
        from inventory.models import Stock, Warehouse, WarehouseSection

        PurchaseOrderLine.objects.filter(order__po_number__startswith='PO-SAMPLE-').delete()
        PurchaseOrder.objects.filter(po_number__startswith='PO-SAMPLE-').delete()
        SalesOrderLine.objects.filter(order__order_number__startswith='SO-SAMPLE-').delete()
        SalesOrder.objects.filter(order_number__startswith='SO-SAMPLE-').delete()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _print_summary(self, products, vendors, customers, warehouses):
        from inventory.models import Stock

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('-' * 50))
        self.stdout.write(self.style.SUCCESS('  OK  Sample data created successfully!'))
        self.stdout.write(self.style.SUCCESS('-' * 50))
        self.stdout.write(f'  Products   : {len(products)} products across 10 categories')
        self.stdout.write(f'  Vendors    : {len(vendors)} vendors')
        self.stdout.write(f'  Customers  : {len(customers)} customers (3 business, 3 individual)')
        self.stdout.write(f'  Warehouses : 2 (Main + Cold Storage)')
        self.stdout.write(f'  Stock      : {Stock.objects.count()} stock entries')
        self.stdout.write(self.style.SUCCESS('-' * 50))
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('  Admin login:'))
        self.stdout.write('    URL      : http://127.0.0.1:8000/admin/')
        self.stdout.write('    Username : admin')
        self.stdout.write('    Password : admin123')
        self.stdout.write('')
