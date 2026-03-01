from decimal import Decimal
from ..models import Currency

class CurrencyConverter:
    """Utility class for currency conversions"""
    
    def __init__(self):
        self.base_currency = Currency.objects.filter(is_base=True).first()
        self.currencies = {c.code: c for c in Currency.objects.filter(is_active=True)}
    
    def convert(self, amount, from_currency, to_currency):
        """Convert amount from one currency to another"""
        if not from_currency or not to_currency or from_currency == to_currency:
            return amount
        
        # Get currency objects
        from_curr = self.currencies.get(from_currency) if isinstance(from_currency, str) else from_currency
        to_curr = self.currencies.get(to_currency) if isinstance(to_currency, str) else to_currency
        
        if not from_curr or not to_curr:
            return amount
        
        # Convert via base currency
        base_amount = amount / from_curr.exchange_rate
        return base_amount * to_curr.exchange_rate
    
    def format_currency(self, amount, currency_code):
        """Format amount for a specific currency"""
        currency = self.currencies.get(currency_code)
        if not currency:
            return f"{amount:.2f}"
        return currency.format_amount(amount)
    
    def get_all_rates(self):
        """Get all exchange rates relative to base"""
        rates = {}
        for code, currency in self.currencies.items():
            rates[code] = float(currency.exchange_rate)
        return rates


class Money:
    """Money value object with currency"""
    
    def __init__(self, amount, currency):
        self.amount = Decimal(str(amount))
        self.currency = currency if isinstance(currency, Currency) else None
    
    def __add__(self, other):
        if self.currency != other.currency:
            # Convert other to this currency
            converter = CurrencyConverter()
            other_amount = converter.convert(other.amount, other.currency, self.currency)
            return Money(self.amount + other_amount, self.currency)
        return Money(self.amount + other.amount, self.currency)
    
    def __sub__(self, other):
        if self.currency != other.currency:
            converter = CurrencyConverter()
            other_amount = converter.convert(other.amount, other.currency, self.currency)
            return Money(self.amount - other_amount, self.currency)
        return Money(self.amount - other.amount, self.currency)
    
    def __mul__(self, factor):
        return Money(self.amount * Decimal(str(factor)), self.currency)
    
    def __truediv__(self, divisor):
        return Money(self.amount / Decimal(str(divisor)), self.currency)
    
    def __str__(self):
        if self.currency:
            return self.currency.format_amount(self.amount)
        return f"{self.amount:.2f}"
    
    def convert_to(self, target_currency):
        """Convert to another currency"""
        converter = CurrencyConverter()
        new_amount = converter.convert(self.amount, self.currency, target_currency)
        return Money(new_amount, target_currency)