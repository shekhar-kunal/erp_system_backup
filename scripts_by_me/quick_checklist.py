# quick_checklist.py
def quick_validation():
    """Quick manual validation checklist"""
    
    checklist = [
        "✅ All model names are singular (Product, not Products)",
        "✅ All ForeignKey fields end with '_id' in database",
        "✅ All DateTimeField fields end with '_at'",
        "✅ All DateField fields end with '_on'",
        "✅ All BooleanField fields start with 'is_' or 'has_'",
        "✅ No field names conflict with Python keywords",
        "✅ All CharField have max_length specified",
        "✅ All DecimalField have max_digits and decimal_places",
        "✅ FileField/ImageField have upload_to specified",
        "✅ All models have __str__ method",
        "✅ All models have Meta class with proper ordering",
        "✅ ForeignKey have on_delete specified",
        "✅ ManyToManyField have related_name specified"
    ]
    
    print("=" * 80)
    print("📋 QUICK VALIDATION CHECKLIST")
    print("=" * 80)
    
    for i, item in enumerate(checklist, 1):
        print(f"{i}. {item}")
    
    print("\nRun these commands to test:")
    print("  python manage.py check")
    print("  python manage.py makemigrations --dry-run")
    print("  python manage.py sqlmigrate products 0001")