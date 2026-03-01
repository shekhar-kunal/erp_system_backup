from django import forms
from django.core.exceptions import ValidationError
from .models import City


class CountryCityMixin:
    """
    Mixin to handle dependent country/city dropdowns
    Use this in any form that has country and city fields
    """
    
    def setup_country_city_fields(self):
        """Call this in __init__ after super().__init__"""
        
        # Get the country value from data or instance
        country_id = None
        country_field_name = self.get_country_field_name()
        city_field_name = self.get_city_field_name()
        
        if self.data.get(country_field_name):
            country_id = self.data.get(country_field_name)
        elif self.instance and hasattr(self.instance, country_field_name):
            country_instance = getattr(self.instance, country_field_name)
            if country_instance:
                country_id = country_instance.id
        
        # Filter cities based on selected country
        if country_id:
            self.fields[city_field_name].queryset = City.objects.filter(
                country_id=country_id,
                is_active=True
            ).order_by('name')
        else:
            self.fields[city_field_name].queryset = City.objects.none()
        
        # Make city optional if no country selected
        self.fields[city_field_name].required = False
    
    def clean_country_city(self):
        """Call this in clean() to validate country/city relationship"""
        country_field_name = self.get_country_field_name()
        city_field_name = self.get_city_field_name()
        
        country = self.cleaned_data.get(country_field_name)
        city = self.cleaned_data.get(city_field_name)
        
        if country and city and city.country != country:
            raise ValidationError({
                city_field_name: f"Selected city '{city.name}' does not belong to selected country '{country.name}'"
            })
        
        return country, city
    
    def get_country_field_name(self):
        """Override this if your country field has a different name"""
        return 'country'
    
    def get_city_field_name(self):
        """Override this if your city field has a different name"""
        return 'city'