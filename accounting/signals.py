from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from .models import Invoice, Bill, Payment, JournalEntry, AccountingSettings
from decimal import Decimal

@receiver(post_save, sender=Invoice)
def invoice_post_save(sender, instance, created, **kwargs):
    """Auto-create journal entry when invoice is confirmed/sent"""
    if instance.status in ['sent', 'paid'] and not instance.journal_entries.exists():
        settings = AccountingSettings.get_settings()
        if settings.enable_auto_posting:
            try:
                instance.post_to_accounting()
            except Exception:
                pass  # Non-critical — entry can be created manually


@receiver(post_save, sender=Bill)
def bill_post_save(sender, instance, created, **kwargs):
    """Auto-create journal entry when bill is received"""
    if instance.status in ['received', 'paid'] and not instance.journal_entries.exists():
        settings = AccountingSettings.get_settings()
        if settings.enable_auto_posting:
            try:
                instance.post_to_accounting()
            except Exception:
                pass


@receiver(post_save, sender=Payment)
def payment_post_save(sender, instance, created, **kwargs):
    """Auto-create journal entry when payment is completed"""
    if instance.status == 'completed' and not instance.journal_entries.exists():
        settings = AccountingSettings.get_settings()
        if settings.enable_auto_posting:
            try:
                instance.post_to_accounting()
            except Exception:
                pass


@receiver(pre_save, sender=JournalEntry)
def journal_entry_pre_save(sender, instance, **kwargs):
    """Validate journal entry before save"""
    if instance.pk:  # Existing entry
        old = JournalEntry.objects.get(pk=instance.pk)
        if old.is_posted and (old.approval_status != instance.approval_status):
            raise ValidationError("Cannot modify posted journal entry")