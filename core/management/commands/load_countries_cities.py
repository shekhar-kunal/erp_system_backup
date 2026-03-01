from django.core.management.base import BaseCommand
from core.models import Country, Region, City


class Command(BaseCommand):
    help = 'Load initial countries, regions, and cities data (USA, UK, Ukraine, India, China, Germany)'

    def handle(self, *args, **kwargs):
        self.stdout.write("=" * 50)
        self.stdout.write("Loading countries, regions, and cities...")
        self.stdout.write("=" * 50)
        
        # Countries data (selected countries only)
        countries_data = [
            {
                'name': 'United States', 
                'code': 'USA', 
                'iso_code': 'US', 
                'phone_code': '+1', 
                'currency': 'USD', 
                'currency_symbol': '$'
            },
            {
                'name': 'United Kingdom', 
                'code': 'GBR', 
                'iso_code': 'GB', 
                'phone_code': '+44', 
                'currency': 'GBP', 
                'currency_symbol': '£'
            },
            {
                'name': 'Ukraine', 
                'code': 'UKR', 
                'iso_code': 'UA', 
                'phone_code': '+380', 
                'currency': 'UAH', 
                'currency_symbol': '₴'
            },
            {
                'name': 'India', 
                'code': 'IND', 
                'iso_code': 'IN', 
                'phone_code': '+91', 
                'currency': 'INR', 
                'currency_symbol': '₹'
            },
            {
                'name': 'China', 
                'code': 'CHN', 
                'iso_code': 'CN', 
                'phone_code': '+86', 
                'currency': 'CNY', 
                'currency_symbol': '¥'
            },
            {
                'name': 'Germany', 
                'code': 'DEU', 
                'iso_code': 'DE', 
                'phone_code': '+49', 
                'currency': 'EUR', 
                'currency_symbol': '€'
            },
        ]
        
        # Create countries
        created_count = 0
        for country_data in countries_data:
            country, created = Country.objects.get_or_create(
                code=country_data['code'],
                defaults=country_data
            )
            if created:
                created_count += 1
                self.stdout.write(f"  ✅ Created: {country.name} ({country.code})")
            else:
                self.stdout.write(f"  ℹ️ Already exists: {country.name}")
        
        self.stdout.write(self.style.SUCCESS(f"✅ Successfully loaded {created_count} countries"))
        
        # Create regions/states for each country
        regions_data = {
            'USA': [
                {'name': 'California', 'code': 'CA'},
                {'name': 'Texas', 'code': 'TX'},
                {'name': 'New York', 'code': 'NY'},
                {'name': 'Florida', 'code': 'FL'},
                {'name': 'Illinois', 'code': 'IL'},
                {'name': 'Pennsylvania', 'code': 'PA'},
                {'name': 'Ohio', 'code': 'OH'},
                {'name': 'Georgia', 'code': 'GA'},
                {'name': 'Michigan', 'code': 'MI'},
                {'name': 'Washington', 'code': 'WA'},
            ],
            'GBR': [
                {'name': 'England', 'code': 'ENG'},
                {'name': 'Scotland', 'code': 'SCT'},
                {'name': 'Wales', 'code': 'WLS'},
                {'name': 'Northern Ireland', 'code': 'NIR'},
            ],
            'UKR': [
                {'name': 'Kyiv Oblast', 'code': 'KV'},
                {'name': 'Lviv Oblast', 'code': 'LV'},
                {'name': 'Odesa Oblast', 'code': 'OD'},
                {'name': 'Kharkiv Oblast', 'code': 'KH'},
                {'name': 'Dnipropetrovsk Oblast', 'code': 'DP'},
                {'name': 'Donetsk Oblast', 'code': 'DT'},
                {'name': 'Zaporizhzhia Oblast', 'code': 'ZP'},
            ],
            'IND': [
                {'name': 'Maharashtra', 'code': 'MH'},
                {'name': 'Delhi', 'code': 'DL'},
                {'name': 'Karnataka', 'code': 'KA'},
                {'name': 'Tamil Nadu', 'code': 'TN'},
                {'name': 'Gujarat', 'code': 'GJ'},
                {'name': 'Uttar Pradesh', 'code': 'UP'},
                {'name': 'West Bengal', 'code': 'WB'},
                {'name': 'Rajasthan', 'code': 'RJ'},
                {'name': 'Madhya Pradesh', 'code': 'MP'},
                {'name': 'Punjab', 'code': 'PB'},
            ],
            'CHN': [
                {'name': 'Beijing', 'code': 'BJ'},
                {'name': 'Shanghai', 'code': 'SH'},
                {'name': 'Guangdong', 'code': 'GD'},
                {'name': 'Sichuan', 'code': 'SC'},
                {'name': 'Zhejiang', 'code': 'ZJ'},
                {'name': 'Jiangsu', 'code': 'JS'},
                {'name': 'Hunan', 'code': 'HN'},
                {'name': 'Fujian', 'code': 'FJ'},
                {'name': 'Shandong', 'code': 'SD'},
                {'name': 'Hubei', 'code': 'HB'},
            ],
            'DEU': [
                {'name': 'Bavaria', 'code': 'BY'},
                {'name': 'North Rhine-Westphalia', 'code': 'NW'},
                {'name': 'Baden-Württemberg', 'code': 'BW'},
                {'name': 'Lower Saxony', 'code': 'NI'},
                {'name': 'Hesse', 'code': 'HE'},
                {'name': 'Saxony', 'code': 'SN'},
                {'name': 'Rhineland-Palatinate', 'code': 'RP'},
                {'name': 'Berlin', 'code': 'BE'},
                {'name': 'Hamburg', 'code': 'HH'},
                {'name': 'Schleswig-Holstein', 'code': 'SH'},
            ],
        }
        
        region_count = 0
        self.stdout.write("\n" + "-" * 40)
        self.stdout.write("Creating regions...")
        self.stdout.write("-" * 40)
        
        for country_code, regions in regions_data.items():
            try:
                country = Country.objects.get(code=country_code)
                for region_data in regions:
                    region, created = Region.objects.get_or_create(
                        name=region_data['name'],
                        country=country,
                        defaults={'code': region_data['code'], 'is_active': True}
                    )
                    if created:
                        region_count += 1
                        self.stdout.write(f"  ✅ Created region: {region.name}, {country.name}")
            except Country.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"  ⚠️ Country {country_code} not found"))
        
        self.stdout.write(self.style.SUCCESS(f"✅ Successfully loaded {region_count} regions"))
        
        # Create major cities for each country
        cities_data = {
            'USA': {
                'California': ['Los Angeles', 'San Francisco', 'San Diego', 'Sacramento', 'San Jose'],
                'New York': ['New York City', 'Buffalo', 'Rochester', 'Albany'],
                'Texas': ['Houston', 'Dallas', 'Austin', 'San Antonio', 'Fort Worth'],
                'Florida': ['Miami', 'Orlando', 'Tampa', 'Jacksonville'],
                'Illinois': ['Chicago', 'Springfield', 'Naperville'],
                'Washington': ['Seattle', 'Spokane', 'Tacoma'],
            },
            'GBR': {
                'England': ['London', 'Manchester', 'Birmingham', 'Liverpool', 'Leeds', 'Bristol'],
                'Scotland': ['Edinburgh', 'Glasgow', 'Aberdeen'],
                'Wales': ['Cardiff', 'Swansea'],
                'Northern Ireland': ['Belfast', 'Derry'],
            },
            'UKR': {
                'Kyiv Oblast': ['Kyiv', 'Brovary', 'Boryspil'],
                'Lviv Oblast': ['Lviv', 'Drohobych', 'Chervonohrad'],
                'Odesa Oblast': ['Odesa', 'Illichivsk', 'Yuzhne'],
                'Kharkiv Oblast': ['Kharkiv', 'Chuhuiv', 'Izium'],
                'Dnipropetrovsk Oblast': ['Dnipro', 'Kryvyi Rih', 'Kamianske'],
            },
            'IND': {
                'Maharashtra': ['Mumbai', 'Pune', 'Nagpur', 'Nashik'],
                'Delhi': ['New Delhi', 'Delhi'],
                'Karnataka': ['Bangalore', 'Mysore', 'Mangalore'],
                'Tamil Nadu': ['Chennai', 'Coimbatore', 'Madurai'],
                'Gujarat': ['Ahmedabad', 'Surat', 'Vadodara'],
                'Uttar Pradesh': ['Lucknow', 'Kanpur', 'Agra', 'Varanasi'],
                'West Bengal': ['Kolkata', 'Howrah', 'Durgapur'],
            },
            'CHN': {
                'Beijing': ['Beijing'],
                'Shanghai': ['Shanghai'],
                'Guangdong': ['Guangzhou', 'Shenzhen', 'Dongguan', 'Foshan'],
                'Sichuan': ['Chengdu', 'Mianyang'],
                'Zhejiang': ['Hangzhou', 'Ningbo', 'Wenzhou'],
                'Jiangsu': ['Nanjing', 'Suzhou', 'Wuxi'],
            },
            'DEU': {
                'Bavaria': ['Munich', 'Nuremberg', 'Augsburg', 'Regensburg'],
                'North Rhine-Westphalia': ['Cologne', 'Düsseldorf', 'Dortmund', 'Essen'],
                'Baden-Württemberg': ['Stuttgart', 'Karlsruhe', 'Mannheim'],
                'Lower Saxony': ['Hanover', 'Braunschweig', 'Osnabrück'],
                'Hesse': ['Frankfurt', 'Wiesbaden', 'Kassel'],
                'Berlin': ['Berlin'],
                'Hamburg': ['Hamburg'],
            },
        }
        
        city_count = 0
        self.stdout.write("\n" + "-" * 40)
        self.stdout.write("Creating cities...")
        self.stdout.write("-" * 40)
        
        for country_code, regions in cities_data.items():
            try:
                country = Country.objects.get(code=country_code)
                for region_name, cities in regions.items():
                    try:
                        region = Region.objects.get(name=region_name, country=country)
                        for city_name in cities:
                            city, created = City.objects.get_or_create(
                                name=city_name,
                                country=country,
                                region=region,
                                defaults={
                                    'is_active': True,
                                    'state': region_name
                                }
                            )
                            if created:
                                city_count += 1
                                self.stdout.write(f"  ✅ Created city: {city_name}, {region_name}, {country.name}")
                    except Region.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f"  ⚠️ Region {region_name} not found in {country.name}"))
                        
                        # Create city without region if region doesn't exist
                        for city_name in cities:
                            city, created = City.objects.get_or_create(
                                name=city_name,
                                country=country,
                                region=None,
                                defaults={
                                    'is_active': True,
                                    'state': region_name
                                }
                            )
                            if created:
                                city_count += 1
                                self.stdout.write(f"  ✅ Created city: {city_name}, {region_name}, {country.name} (no region)")
            except Country.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"  ⚠️ Country {country_code} not found"))
        
        self.stdout.write(self.style.SUCCESS(f"✅ Successfully loaded {city_count} cities"))
        
        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("✅ MASTER DATA LOADING COMPLETE!"))
        self.stdout.write("=" * 50)
        
        # Show statistics
        total_countries = Country.objects.filter(code__in=[c['code'] for c in countries_data]).count()
        total_regions = Region.objects.filter(country__code__in=[c['code'] for c in countries_data]).count()
        total_cities = City.objects.filter(country__code__in=[c['code'] for c in countries_data]).count()
        
        self.stdout.write(f"\n📊 Statistics:")
        self.stdout.write(f"  Countries: {total_countries}")
        self.stdout.write(f"  Regions: {total_regions}")
        self.stdout.write(f"  Cities: {total_cities}")
        self.stdout.write("=" * 50)