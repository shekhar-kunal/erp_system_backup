from django import forms
from django.contrib.auth import authenticate


class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'erp-input',
            'placeholder': 'Username',
            'autofocus': True,
            'autocomplete': 'username',
        }),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'erp-input',
            'placeholder': 'Password',
            'autocomplete': 'current-password',
        }),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self._user  = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned  = super().clean()
        username = cleaned.get('username', '').strip()
        password = cleaned.get('password', '')
        if username and password:
            user = authenticate(self.request, username=username, password=password)
            if user is None:
                raise forms.ValidationError(
                    'Invalid username or password.',
                    code='invalid_login',
                )
            if not user.is_active:
                raise forms.ValidationError(
                    'This account has been disabled.',
                    code='inactive',
                )
            self._user = user
        return cleaned

    def get_user(self):
        return self._user
