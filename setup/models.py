from django.db import models

class SetupStatus(models.Model):
    """Track installation status"""
    STEP_CHOICES = [
        (1, 'Welcome'),
        (2, 'Company'),
        (3, 'Admin User'),
        (4, 'Modules'),
        (5, 'Configuration'),
        (6, 'Review'),
        (7, 'Install'),
        (8, 'Complete'),
    ]
    
    current_step = models.IntegerField(choices=STEP_CHOICES, default=1)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Store all setup data as JSON
    setup_data = models.JSONField(default=dict, blank=True)
    
    # References after completion
    company_id = models.IntegerField(null=True, blank=True)
    admin_user_id = models.IntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Setup Status"
        verbose_name_plural = "Setup Status"
    
    def __str__(self):
        return f"Setup - Step {self.current_step} ({'Complete' if self.completed else 'In Progress'})"
    
    @classmethod
    def get_status(cls):
        """Get or create setup status"""
        status, created = cls.objects.get_or_create(pk=1)
        return status
    
    @classmethod
    def is_complete(cls):
        """Check if setup is complete"""
        try:
            return cls.objects.get(pk=1).completed
        except cls.DoesNotExist:
            return False
    
    def save_step_data(self, step, data):
        """Save data for a specific step"""
        self.setup_data[step] = data
        self.save()
    
    def get_step_data(self, step):
        """Get data for a specific step"""
        return self.setup_data.get(step, {})


class InstallationLog(models.Model):
    """Log installation steps for debugging"""
    LEVEL_CHOICES = [
        ('info', 'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]
    
    step = models.CharField(max_length=50)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='info')
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"[{self.level}] {self.step}: {self.message[:50]}"