#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""User roles and singleton site settings."""

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    """Per-user role attached to Django ``User``.

    Every ``User`` has exactly one profile (``related_name='profile'``).
    Role is ``admin`` or ``readonly`` and is what ``require_admin_role``
    and admin API tokens consult. New users default to ``admin`` via
    ``create_user_profile``; first-run bootstrap also forces admin.
    """

    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('readonly', 'Readonly'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='admin')
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"
    
    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a ``UserProfile`` with role ``admin`` when a ``User`` is inserted.

    Args:
        instance: The saved ``User``.
        created: True only on insert; updates are ignored.
    """
    if created:
        UserProfile.objects.create(user=instance, role='admin')

class Settings(models.Model):
    """Singleton site settings row (always ``pk=1``).

    Created on first ``get_settings()`` call. Field meaning lives on
    ``help_text``; extra rows are not valid configuration.
    """

    experimental_mode = models.BooleanField(default=False)
    agent_ui_url = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text=(
            "Base URL agents use to reach LogstashUI (backend channel). "
            "Prefills --logstash-ui-url in generated enroll commands. "
            "May differ from the browser reverse-proxy URL."
        ),
    )
    logstash_artifact_base_url = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text=(
            "Upstream source for Logstash release tarballs. Blank uses "
            "https://artifacts.elastic.co/downloads/logstash. Point this at an "
            "internal mirror to keep tarball fetches inside your network."
        ),
    )

    class Meta:
        db_table = 'settings'
        verbose_name = 'Settings'
        verbose_name_plural = 'Settings'
    
    def __str__(self):
        return f"Experimental Mode: {self.experimental_mode}"
    
    @classmethod
    def get_settings(cls):
        """Return the singleton settings row, creating ``pk=1`` if needed.

        Returns:
            The ``Settings`` instance with primary key 1.
        """
        settings, created = cls.objects.get_or_create(pk=1)
        return settings
