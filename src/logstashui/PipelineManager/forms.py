#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Django forms for PipelineManager connections."""

import json
import re

from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from urllib.parse import urlparse, urlunparse
from PipelineManager.models import Connection, _split_url_port


def split_host_port(host, port):
    """Move a port written into an Elasticsearch URL into the ``port`` field.

    Connections are dialled as ``f"{host}:{port}"``, so a port left in
    ``host`` would be doubled.

    Args:
        host: Elasticsearch URL as entered.
        port: Port field value, or None.

    Returns:
        tuple: ``(host_without_port, port)``.

    Raises:
        ValidationError: ``host`` carries a different port than ``port``.

    Examples:
        >>> split_host_port('https://es.lab:9200', None)
        ('https://es.lab', 9200)
        >>> split_host_port('https://es.lab', 9200)
        ('https://es.lab', 9200)
    """
    parsed = urlparse(host if '://' in host else f'//{host}')
    try:
        host_port = parsed.port
    except ValueError:
        return host, port
    if host_port is None:
        return host, port
    if port and int(port) != host_port:
        raise ValidationError(
            f"Host includes port {host_port} but Port is {port}. Put the port only in Port.")
    netloc = parsed.netloc.rsplit(':', 1)[0]
    return urlunparse(parsed._replace(netloc=netloc)).removeprefix('//'), host_port


def normalize_es_host(url, port=None):
    """Return one Elasticsearch node as ``scheme://host:port[/path]``.

    Mirrors the connection modal's live normalization: a port typed into the
    URL moves into ``port``, and a missing port defaults to 443 for https or
    80 for http. The port is always explicit because the Logstash
    elasticsearch output defaults to 9200 while the Python client uses the
    scheme default.

    Args:
        url: Node URL as entered; must start with ``http://`` or ``https://``.
        port: Port field value (int, numeric string, empty, or None).

    Returns:
        Normalized URL string.

    Raises:
        ValidationError: Missing scheme or hostname, a non-numeric or
            out-of-range port, or conflicting ports in URL and Port.

    Examples:
        >>> normalize_es_host('https://es1.lab:9200')
        'https://es1.lab:9200'
        >>> normalize_es_host('https://es1.lab', '9243')
        'https://es1.lab:9243'
        >>> normalize_es_host('http://es1.lab/')
        'http://es1.lab:80'
    """
    url = (url or '').strip().rstrip('/')
    if not re.match(r'^https?://', url, re.IGNORECASE):
        raise ValidationError(f"'{url}' must start with http:// or https://")

    port_text = str(port).strip() if port is not None else ''
    if port_text:
        if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
            raise ValidationError(f"Port '{port_text}' for {url} must be a number from 1 to 65535.")
        port = int(port_text)
    else:
        port = None

    url, port = split_host_port(url, port)
    parsed = urlparse(url)
    if not parsed.hostname:
        raise ValidationError(f"'{url}' has no hostname.")
    scheme = parsed.scheme.lower()
    if port is None:
        port = 443 if scheme == 'https' else 80
    return urlunparse((scheme, f"{parsed.netloc}:{port}", parsed.path.rstrip('/'), '', '', ''))


class ConnectionForm(ModelForm):
    """Create or update a ``Connection`` for Agent or Centralized types.

    Field requirements change with ``connection_type`` and, for CENTRALIZED,
    with the ``connection_mode`` / ``auth_type`` radios in the POST body.
    """
    # Connection type radio buttons
    connection_type = forms.ChoiceField(
        choices=Connection.ConnectionType.choices,
        widget=forms.RadioSelect(attrs={
            'class': 'flex flex-col space-y-2',
        }),
        initial=Connection.ConnectionType.CENTRALIZED,
    )

    # Agent Fields
    ssh_key = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'textarea textarea-bordered w-full',
            'rows': 5,
            'placeholder': 'Paste your private key (PEM format) here',
        }),
        required=False,
        help_text='Private key for key-based authentication',
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
            # Agent fields
            'host', 'port', 'username', 'password', 'ssh_key',
            # Centralized fields
            'cloud_id', 'cloud_url', 'api_key', 'kibana_url',
            'allow_self_signed_certs',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'e.g., Production Cluster',
            }),
            'host': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'https://elasticsearch.example.com',
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
            'kibana_url': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'https://kibana.example.com:5601',
            }),
            'allow_self_signed_certs': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary',
            }),
        }
        help_texts = {
            'password': 'Leave empty to keep current password',
            'cloud_url': 'Full URL to your Elasticsearch cluster',
            'ssh_key': 'Paste your private key in PEM format',
            'username': 'Elasticsearch username (usually "elastic")',
            'port': 'Elasticsearch API port (usually 9200)',
            'allow_self_signed_certs': 'Skip TLS certificate verification (required for self-signed or private CA certs)',
        }

    def __init__(self, *args, **kwargs):
        """Bind the form and relax password/API-key requiredness on edit.

        Existing rows do not need credentials re-entered. DaisyUI classes
        and empty ``label_suffix`` are applied to every field except
        ``connection_type``.
        """
        super().__init__(*args, **kwargs)
        # Snapshot original encrypted credentials BEFORE Django's _post_clean()
        # clears them from self.instance during is_valid().  save() uses these
        # snapshots to restore credentials when the caller didn't re-submit them
        # (i.e. a partial PUT that doesn't include api_key or password).
        if self.instance and self.instance.pk:
            self._original_api_key = self.instance.api_key
            self._original_password = self.instance.password
        else:
            self._original_api_key = None
            self._original_password = None

        # Set initial values for the form
        if self.instance and self.instance.pk:
            # For existing instances, don't require password/API key to be re-entered
            self.fields['password'].required = False
            self.fields['api_key'].required = False
        else:
            # The model default is True (so migrated rows keep working), but a
            # brand-new connection should start strict: unchecked in the UI.
            self.initial['allow_self_signed_certs'] = False

        # Add DaisyUI classes to all fields
        for field_name, field in self.fields.items():
            if field_name not in ('connection_type', 'allow_self_signed_certs'):  # Skip separately handled fields
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
        """Cross-field validation for Agent vs Centralized modes.

        AGENT requires host or Cloud URL. CENTRALIZED zeros the hidden
        opposing fields (cloud vs URL, basic vs API key) so a stale value
        from a previously selected radio cannot silently win.

        Returns:
            The cleaned data dict.

        Raises:
            ValidationError: Required field for the selected mode is missing.
        """
        cleaned_data = super().clean()
        connection_type = cleaned_data.get('connection_type')

        if connection_type == Connection.ConnectionType.AGENT:
            # For Agent connections, require either host or cloud_url
            if not cleaned_data.get('host') and not cleaned_data.get('cloud_url'):
                raise forms.ValidationError("Either Host or Cloud URL is required for Agent connections.")
            cleaned_data['kibana_url'] = None
        else:  # CENTRALIZED
            # Read the radio-button selections from raw POST data so we can zero
            # out whichever fields the user hid before submitting. Hidden inputs
            # are still included in the POST payload, so without this a stale
            # cloud_id (or stale auth credential) silently wins even after the
            # user has switched modes.
            connection_mode = self.data.get('connection_mode', 'cloud')
            auth_type = self.data.get('auth_type', 'basic')

            # --- Connection mode ---
            if connection_mode == 'cloud':
                # URL-mode fields should be ignored
                cleaned_data['host'] = ''
                cleaned_data['port'] = None
                if not cleaned_data.get('cloud_id'):
                    raise forms.ValidationError("Cloud ID is required when using Cloud ID mode.")
                cleaned_data['es_hosts'] = []
            else:  # 'url'
                # Cloud ID field should be ignored
                cleaned_data['cloud_id'] = ''
                hosts = []
                for url, port in self._submitted_hosts(cleaned_data):
                    if not str(url or '').strip():
                        continue
                    node = normalize_es_host(url, port)
                    if node not in hosts:
                        hosts.append(node)
                if not hosts:
                    raise forms.ValidationError(
                        "At least one Elasticsearch node URL is required when using Elastic Node URL mode.")
                if len({urlparse(h).scheme for h in hosts}) > 1:
                    raise forms.ValidationError(
                        "All Elasticsearch node URLs must use the same scheme (all http:// or all https://).")
                cleaned_data['es_hosts'] = hosts
                cleaned_data['host'], cleaned_data['port'] = _split_url_port(hosts[0])

            kibana_url = (cleaned_data.get('kibana_url') or '').strip()
            if kibana_url:
                from Common.elastic_utils import normalize_kibana_url
                if '://' in kibana_url and not re.match(r'^https?://', kibana_url, re.IGNORECASE):
                    raise forms.ValidationError("Kibana URL must start with http:// or https://")
                cleaned_data['kibana_url'] = normalize_kibana_url(kibana_url)
            else:
                cleaned_data['kibana_url'] = None

            # --- Auth type ---
            if auth_type == 'basic':
                # API key field should be ignored
                cleaned_data['api_key'] = ''
            else:  # 'apiKey'
                # Username / password fields should be ignored
                cleaned_data['username'] = ''
                cleaned_data['password'] = ''

        return cleaned_data

    def _submitted_hosts(self, cleaned_data):
        """Return the submitted Elasticsearch nodes as ``(url, port)`` pairs.

        Sources, first match wins: the modal's parallel ``es_host_url`` /
        ``es_host_port`` rows, an ``es_hosts`` list (JSON array, repeated form
        key, or comma-separated string), then the legacy single
        ``host`` + ``port``.

        Args:
            cleaned_data: The form's cleaned data, for the legacy fields.

        Returns:
            List of ``(url, port)`` tuples in submitted order.

        Raises:
            ValidationError: ``es_hosts`` is not a list of strings.

        Examples:
            >>> # POST es_host_url=https://es1&es_host_port=9200&es_host_url=https://es2&es_host_port=
            >>> # -> [('https://es1', '9200'), ('https://es2', '')]
        """
        data = self.data
        getlist = getattr(data, 'getlist', None)
        if 'es_host_url' in data:
            urls = getlist('es_host_url') if getlist else data.get('es_host_url')
            ports = (getlist('es_host_port') if getlist else data.get('es_host_port')) or []
            if isinstance(urls, str):
                urls = [urls]
            if isinstance(ports, (str, int)):
                ports = [ports]
            return [(u, ports[i] if i < len(ports) else '') for i, u in enumerate(urls)]

        if 'es_hosts' in data:
            raw = getlist('es_hosts') if getlist else data.get('es_hosts')
            if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], str):
                raw = raw[0]
            if isinstance(raw, str):
                text = raw.strip()
                if text.startswith('['):
                    try:
                        raw = json.loads(text)
                    except ValueError:
                        raise ValidationError("es_hosts must be a JSON array of URLs.")
                else:
                    raw = [part for part in text.split(',')]
            if raw is None:
                raw = []
            if not isinstance(raw, list) or not all(isinstance(h, str) for h in raw):
                raise ValidationError("es_hosts must be a list of URL strings.")
            return [(h, None) for h in raw]

        host = cleaned_data.get('host')
        return [(host, cleaned_data.get('port'))] if host else []

    def save(self, commit=True):
        """Persist the connection, keeping existing credentials when left blank.

        Args:
            commit: If True, save the instance immediately.

        Returns:
            The unsaved or saved ``Connection`` instance.
        """
        instance = super().save(commit=False)
        if 'es_hosts' in self.cleaned_data:
            instance.es_hosts = self.cleaned_data['es_hosts']
        
        # Only update password if a new one was provided.
        # Use the snapshot from __init__ because Django's _post_clean() already
        # cleared self.instance.password during is_valid().
        if 'password' in self.cleaned_data and not self.cleaned_data['password']:
            if self._original_password:
                instance.password = self._original_password
        
        # Only update API key if a new one was provided.
        # Same reason: use the __init__-time snapshot.
        if 'api_key' in self.cleaned_data and not self.cleaned_data['api_key']:
            if self._original_api_key:
                instance.api_key = self._original_api_key
        
        if commit:
            instance.save()
        
        return instance