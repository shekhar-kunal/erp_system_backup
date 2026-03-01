from django import forms
from .models import FORMAT_CHOICES, DATE_FORMAT_CHOICES


# Formats the user can choose between on the options page
_SELECTABLE_FORMATS = [
    (k, v) for k, v in FORMAT_CHOICES
    if k not in ('none', 'google_sheets', 'zip')
]


class ExportOptionsForm(forms.Form):
    """
    Shown on the intermediate Export Options page before the file download.
    The 'enabled_formats' constructor argument limits which formats are shown
    (derived from ExportConfig.enabled_formats for this module).
    """

    format = forms.ChoiceField(
        label='Export Format',
        choices=[],  # Populated in __init__
        widget=forms.RadioSelect(attrs={'class': 'export-format-radio'}),
    )
    include_headers = forms.BooleanField(
        label='Include column headers',
        required=False,
        initial=True,
    )
    include_footer = forms.BooleanField(
        label='Include summary footer',
        required=False,
        initial=False,
    )
    compress_zip = forms.BooleanField(
        label='Compress as ZIP archive',
        required=False,
        initial=False,
    )
    date_format = forms.ChoiceField(
        label='Date Format',
        choices=DATE_FORMAT_CHOICES,
        initial='%Y-%m-%d',
    )
    save_as_preference = forms.BooleanField(
        label='Remember my choices for this module',
        required=False,
        initial=False,
        help_text='Your selections will be pre-filled next time you export from this module.',
    )

    def __init__(self, *args, enabled_formats=None, initial_format=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Build format choices from enabled_formats config
        if enabled_formats:
            format_map = dict(FORMAT_CHOICES)
            choices = [
                (k, format_map.get(k, k.upper()))
                for k in enabled_formats
                if k not in ('none', 'google_sheets', 'zip')
            ]
        else:
            choices = _SELECTABLE_FORMATS

        self.fields['format'].choices = choices

        # Pre-select the format passed in
        if initial_format and not self.is_bound:
            self.initial['format'] = initial_format
