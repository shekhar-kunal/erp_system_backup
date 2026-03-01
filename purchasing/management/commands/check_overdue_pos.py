from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from purchasing.models import PurchaseOrder
# Comment out if utils.py doesn't exist yet
# from purchasing.utils import send_overdue_notification


class Command(BaseCommand):
    help = 'Check for overdue purchase orders and send notifications'
    
    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=1, 
                          help='Notify for orders overdue by this many days')
    
    def handle(self, *args, **options):
        today = timezone.now().date()
        days = options['days']
        
        overdue_pos = PurchaseOrder.objects.filter(
            status__in=['confirmed', 'partial'],
            expected_date__lte=today - timedelta(days=days)
        )
        
        for po in overdue_pos:
            # send_overdue_notification(po)  # Uncomment when utils.py is created
            self.stdout.write(
                self.style.SUCCESS(f'Order {po.po_number} is overdue by {days} days')
            )