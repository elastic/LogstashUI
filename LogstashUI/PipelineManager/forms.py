from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from Core.models import Connection


class ConnectionForm(ModelForm):
    """
    Form for creating and updating Connection instances.
    Handles both SSH and Centralized connection types with dynamic field requirements.
    """
    # Connection type radio buttons
    connection_type = forms.ChoiceField(
        choices=Connection.ConnectionType.choices,
        widget=forms.RadioSelect(attrs={
            'class': 'flex flex-col space-y-2',
        }),
        initial=Connection.ConnectionType.CENTRALIZED,
    )

    # SSH Fields
    ssh_key = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'textarea textarea-bordered w-full',
            'rows': 5,
            'placeholder': 'Paste your SSH private key (PEM format) here',
        }),
        required=False,
        help_text='SSH private key for key-based authentication',
        label_suffix='',
    )

    # Centralized Management Fields
    cloud_id = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'input input-bordered w-full',
            'placeholder': 'deployment-name:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX',
        }),
        required=False,
        help_text='Elastic Cloud ID (e.g., deployment-name:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX)',
        label_suffix='',
    )

    api_key = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'input input-bordered w-full',
            'autocomplete': 'new-password',
        }),
        required=False,
        help_text='API key for authentication (leave empty to keep current)',
        label_suffix='',
    )

    class Meta:
        model = Connection
        fields = [
            'name', 'connection_type',
            # SSH fields
            'host', 'port', 'username', 'password', 'ssh_key',
            # Centralized fields
            'cloud_id', 'cloud_url', 'api_key',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'e.g., Production Cluster',
            }),
            'host': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'elasticsearch.example.com',
                'required': False,
            }),
            'port': forms.NumberInput(attrs={
                'class': 'input input-bordered w-24',
                'required': False,
            }),
            'username': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'elastic',
                'required': False,
            }),
            'password': forms.PasswordInput(attrs={
                'class': 'input input-bordered w-full',
                'autocomplete': 'new-password',
                'placeholder': '••••••••',
                'required': False,
            }),
            'cloud_url': forms.URLInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'https://my-deployment.es.us-central1.gcp.cloud.es.io:9243',
                'required': False,
            }),
        }
        help_texts = {
            'password': 'Leave empty to keep current password',
            'cloud_url': 'Full URL to your Elasticsearch cluster',
            'ssh_key': 'Paste your SSH private key in PEM format',
            'username': 'Elasticsearch username (usually "elastic")',
            'port': 'Elasticsearch API port (usually 9200)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial values for the form
        if self.instance and self.instance.pk:
            # For existing instances, don't require password/API key to be re-entered
            self.fields['password'].required = False
            self.fields['api_key'].required = False

        # Add DaisyUI classes to all fields
        for field_name, field in self.fields.items():
            if field_name != 'connection_type':  # Skip connection_type as it's handled separately
                if 'class' in field.widget.attrs:
                    if 'input' not in field.widget.attrs['class'] and 'textarea' not in field.widget.attrs['class']:
                        if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.PasswordInput, forms.URLInput)):
                            field.widget.attrs['class'] += ' input input-bordered w-full'
                        elif isinstance(field.widget, forms.Textarea):
                            field.widget.attrs['class'] += ' textarea textarea-bordered w-full'
                else:
                    if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.PasswordInput, forms.URLInput)):
                        field.widget.attrs['class'] = 'input input-bordered w-full'
                    elif isinstance(field.widget, forms.Textarea):
                        field.widget.attrs['class'] = 'textarea textarea-bordered w-full'
                
                # Add placeholder if not already set
                if 'placeholder' not in field.widget.attrs:
                    field.widget.attrs['placeholder'] = field.label or ''
                
                # Remove default colons from labels
                field.label_suffix = ''

    def clean(self):
        cleaned_data = super().clean()
        connection_type = cleaned_data.get('connection_type')
        
        if connection_type == Connection.ConnectionType.SSH:
            # For SSH connections, require either host or cloud_url
            if not cleaned_data.get('host') and not cleaned_data.get('cloud_url'):
                raise forms.ValidationError("Either Host or Cloud URL is required for SSH connections.")
        else:  # CENTRALIZED
            # For Centralized connections, require either cloud_id or cloud_url
            if not cleaned_data.get('cloud_id') and not cleaned_data.get('host'):
                raise forms.ValidationError("Either Cloud ID or host is required for centralized connections.")
        
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Only update password if a new one was provided
        if 'password' in self.cleaned_data and not self.cleaned_data['password']:
            # If password field is empty, keep the existing password
            if self.instance and self.instance.pk:
                instance.password = self.instance.password
        
        # Only update API key if a new one was provided
        if 'api_key' in self.cleaned_data and not self.cleaned_data['api_key']:
            # If API key field is empty, keep the existing API key
            if self.instance and self.instance.pk:
                instance.api_key = self.instance.api_key
        
        if commit:
            instance.save()
        
        return instance