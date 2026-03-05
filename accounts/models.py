from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone


class CustomUserManager(BaseUserManager):

    def create_user(self, username, email='', password=None, **extra_fields):
        if not username:
            raise ValueError('Username is required')
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_system_admin', False)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email='', password=None, **extra_fields):
        extra_fields['is_system_admin'] = True
        extra_fields['is_active'] = True
        return self.create_user(username, email, password, **extra_fields)


class CustomUser(AbstractBaseUser):
    username        = models.CharField(max_length=150, unique=True)
    email           = models.EmailField(blank=True)
    first_name      = models.CharField(max_length=150, blank=True)
    last_name       = models.CharField(max_length=150, blank=True)
    is_active       = models.BooleanField(default=True)
    is_system_admin = models.BooleanField(
        default=False,
        help_text='Full system access — bypasses all RBAC checks.',
    )
    date_joined = models.DateTimeField(default=timezone.now)

    objects = CustomUserManager()

    USERNAME_FIELD  = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name        = 'User'
        verbose_name_plural = 'Users'
        ordering            = ['username']

    def __str__(self):
        return self.username

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.username

    def get_short_name(self):
        return self.first_name or self.username

    # --- Django internal compatibility properties ---

    @property
    def is_staff(self):
        """Maps to is_system_admin so Django admin machinery still works."""
        return self.is_system_admin

    @property
    def is_superuser(self):
        """Maps to is_system_admin; existing code reading .is_superuser keeps working."""
        return self.is_system_admin

    # --- Permission API (RBAC handles real checks via PermissionService) ---

    def has_perm(self, perm, obj=None):
        return self.is_system_admin

    def has_module_perms(self, app_label):
        # Return True for all active users so the admin index can build.
        # ERPAdminMixin gates access at the per-model level via PermissionService.
        return self.is_active
