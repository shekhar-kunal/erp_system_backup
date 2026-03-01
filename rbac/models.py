from django.conf import settings
from django.db import models
from django.utils import timezone


MODULE_CHOICES = [
    ('products.product', 'Products - Product'),
    ('products.unit', 'Products - Unit'),
    ('products.brand', 'Products - Brand'),
    ('products.productcategory', 'Products - Category'),
    ('products.pricelist', 'Products - Price List'),
    ('products.productattribute', 'Products - Product Attribute'),
    ('products.productattributevalue', 'Products - Attribute Value'),
    ('products.productvariant', 'Products - Product Variant'),
    ('products.productpricehistory', 'Products - Price History'),
    ('inventory.stock', 'Inventory - Stock'),
    ('inventory.stockbatch', 'Inventory - Stock Batch'),
    ('inventory.stockmovement', 'Inventory - Stock Movement'),
    ('inventory.warehouse', 'Inventory - Warehouse'),
    ('inventory.warehousesection', 'Inventory - Warehouse Section'),
    ('purchasing.purchaseorder', 'Purchasing - Purchase Order'),
    ('purchasing.vendor', 'Purchasing - Vendor'),
    ('purchasing.purchasereceipt', 'Purchasing - Purchase Receipt'),
    ('sales.customer', 'Sales - Customer'),
    ('sales.salesorder', 'Sales - Sales Order'),
    ('accounting.invoice', 'Accounting - Invoice'),
    ('accounting.bill', 'Accounting - Bill'),
    ('accounting.payment', 'Accounting - Payment'),
    ('accounting.journalentry', 'Accounting - Journal Entry'),
]

WEEKDAY_CHOICES = [
    (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'),
    (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
]


class Department(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    head = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='headed_departments',
    )
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sub_departments',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.code})'


class Branch(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='managed_branches',
    )
    is_main = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    warehouses = models.ManyToManyField(
        'inventory.Warehouse', blank=True, related_name='branches',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Branch'
        verbose_name_plural = 'Branches'
        ordering = ['-is_main', 'name']

    def __str__(self):
        return self.name


class Role(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_system_role = models.BooleanField(
        default=False,
        help_text='System roles cannot be deleted.',
    )
    is_active = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(
        default=0,
        help_text='Lower number = higher priority. Used when resolving conflicts.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'
        ordering = ['priority', 'name']

    def __str__(self):
        return self.name


class ModulePermission(models.Model):
    """One record per (role, module) pair defining all 7 action permissions."""
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='module_permissions')
    module = models.CharField(max_length=100, choices=MODULE_CHOICES)
    can_view = models.BooleanField(default=False)
    can_create = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_approve = models.BooleanField(default=False)
    can_export = models.BooleanField(default=False)
    can_print = models.BooleanField(default=False)
    allowed_export_formats = models.JSONField(
        default=list,
        help_text='Allowed export formats for this role+module. Empty = all enabled formats.',
    )

    class Meta:
        verbose_name = 'Module Permission'
        verbose_name_plural = 'Module Permissions'
        unique_together = [('role', 'module')]
        ordering = ['module']

    def __str__(self):
        return f'{self.role.name} — {self.get_module_display()}'


class FieldPermission(models.Model):
    """Field-level visibility and edit restriction per role+module."""
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='field_permissions')
    module = models.CharField(max_length=100, choices=MODULE_CHOICES)
    field_name = models.CharField(max_length=100)
    can_view = models.BooleanField(default=True)
    can_edit = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Field Permission'
        verbose_name_plural = 'Field Permissions'
        unique_together = [('role', 'module', 'field_name')]
        ordering = ['module', 'field_name']

    def __str__(self):
        return f'{self.role.name} / {self.module} / {self.field_name}'


class UserProfile(models.Model):
    """Extended user attributes for ERP. Linked 1-to-1 with Django User."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile',
    )
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='members',
    )
    role = models.ForeignKey(
        Role, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='users',
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='users',
    )
    warehouses = models.ManyToManyField(
        'inventory.Warehouse', blank=True, related_name='assigned_users',
        help_text='Warehouses this user can access. Empty = no warehouse restriction.',
    )
    approval_level = models.PositiveIntegerField(
        default=0,
        help_text='0=no approval rights, 1-5=approval authority level.',
    )

    # Working hours
    work_start = models.TimeField(
        null=True, blank=True,
        help_text='Start of allowed work hours (local time). Leave blank for no restriction.',
    )
    work_end = models.TimeField(
        null=True, blank=True,
        help_text='End of allowed work hours (local time). Leave blank for no restriction.',
    )
    work_days = models.JSONField(
        default=list,
        help_text='Allowed weekdays as list of integers (0=Mon … 6=Sun). Empty = all days.',
    )

    # Account lock
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_password_change = models.DateField(null=True, blank=True)

    # Additional info
    employee_id = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f'Profile: {self.user.username}'

    def is_locked(self):
        return bool(self.locked_until and timezone.now() < self.locked_until)

    def is_within_working_hours(self):
        if not self.work_start or not self.work_end:
            return True
        now = timezone.localtime()
        if self.work_days and now.weekday() not in self.work_days:
            return False
        return self.work_start <= now.time() <= self.work_end

    def get_work_days_display(self):
        day_names = dict(WEEKDAY_CHOICES)
        return ', '.join(day_names[d] for d in self.work_days if d in day_names) or 'All days'


class ApprovalRule(models.Model):
    """
    Configurable approval rules per module+action.
    Defines which approval level is required, optionally above a threshold amount.
    """
    module = models.CharField(max_length=100, choices=MODULE_CHOICES)
    action = models.CharField(
        max_length=50,
        help_text='e.g. confirm, approve, post, cancel',
    )
    min_amount = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
        help_text='Rule only applies when the document amount is >= this value. Leave blank to always apply.',
    )
    required_approval_level = models.PositiveIntegerField(
        default=1,
        help_text='Minimum UserProfile.approval_level needed to perform this action.',
    )
    required_role = models.ForeignKey(
        Role, on_delete=models.SET_NULL, null=True, blank=True,
        help_text='If set, user must also have this role (in addition to approval_level).',
    )
    sequence = models.PositiveIntegerField(
        default=1,
        help_text='Step order in multi-level approval (1=first).',
    )
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Approval Rule'
        verbose_name_plural = 'Approval Rules'
        ordering = ['module', 'action', 'sequence']

    def __str__(self):
        amount_str = f' (>= {self.min_amount})' if self.min_amount else ''
        return f'{self.get_module_display()} / {self.action}{amount_str} — level {self.required_approval_level}'


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('export', 'Export'),
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('print', 'Print'),
        ('view', 'View'),
        ('lock', 'Account Locked'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='rbac_audit_logs',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    module = models.CharField(max_length=100, blank=True, db_index=True)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=50, blank=True)
    object_repr = models.CharField(max_length=200, blank=True)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    extra = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['module', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
        ]

    def __str__(self):
        username = self.user.username if self.user else 'Anonymous'
        ts = self.timestamp.strftime('%Y-%m-%d %H:%M') if self.timestamp else '?'
        return f'{username} {self.action} {self.model_name} #{self.object_id} at {ts}'
