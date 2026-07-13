#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.db import models
from Common.encryption import encrypt_credential, decrypt_credential


class AISettings(models.Model):
    """
    Connection settings for the external AI authoring agent (Elastic Agent Builder).
    Singleton: always row pk=1.
    """
    agent_url = models.CharField(
        max_length=512, blank=True,
        help_text="Base Kibana URL of the Agent Builder deployment "
                  "(e.g. https://my-deployment.kb.region.cloud.es.io)")
    agent_id = models.CharField(
        max_length=255, default="snmp-profile-author",
        help_text="Agent Builder agent id used to author SNMP profiles")
    api_key = models.CharField(
        max_length=1024, blank=True,
        help_text="Encrypted Elasticsearch/Kibana API key (base64 'encoded' form)")
    verify_tls = models.BooleanField(default=True)
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI Settings"
        verbose_name_plural = "AI Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        if self.api_key and not self.api_key.startswith("enc::"):
            self.api_key = "enc::" + encrypt_credential(self.api_key)
        super().save(*args, **kwargs)

    def get_api_key(self):
        if self.api_key and self.api_key.startswith("enc::"):
            return decrypt_credential(self.api_key[5:])
        return self.api_key or ""

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class DraftDefinition(models.Model):
    """
    An AI-authored SNMP profile awaiting human approval before it becomes a
    real Profile + DeviceTemplate. This is the approval gate for the
    discovery -> author -> approve -> deploy loop.
    """
    STATUS = [("pending", "Pending approval"), ("approved", "Approved"), ("rejected", "Rejected")]

    device = models.ForeignKey("SNMP.Device", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="ai_drafts")
    target_ip = models.CharField(max_length=255, blank=True)
    sys_descr = models.TextField(blank=True)
    vendor = models.CharField(max_length=255, blank=True)
    proposed_name = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=STATUS, default="pending")

    profile_json = models.JSONField(default=dict, help_text="Authored {get, walk, table} blob")
    normalizers = models.JSONField(default=list, help_text="Authored normalizer ops (multiply/ratio/...)")
    unverified = models.JSONField(default=list, help_text="OIDs the agent could not verify")
    walk_summary = models.TextField(blank=True, help_text="OIDs found on the live snmpwalk")
    agent_notes = models.TextField(blank=True, help_text="Agent explanation / provenance")

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.CharField(max_length=255, blank=True)
    created_profile = models.ForeignKey("SNMP.Profile", on_delete=models.SET_NULL, null=True, blank=True)
    created_template = models.ForeignKey("SNMP.DeviceTemplate", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.proposed_name} ({self.status})"
