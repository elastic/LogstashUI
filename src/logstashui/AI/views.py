#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import json
import re
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from PipelineManager.models import Connection
from Common.decorators import require_admin_role
from SNMP.models import Device, Profile, DeviceTemplate
from .models import AISettings, DraftDefinition
from . import snmp_discovery, agent_client

logger = logging.getLogger(__name__)


def IntegrationFactory(request):
    connections = Connection.objects.filter(
        connection_type=Connection.ConnectionType.CENTRALIZED,
        cloud_id__isnull=False
    ).exclude(cloud_id='').values('id', 'name')

    return render(request, 'integration_factory.html', {
        'connections': connections
    })


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_") or "device"


def IntegrationFactory(request):
    return render(request, "integration_factory.html")


def _oid_count(pj):
    n = len(pj.get("get", {})) + len(pj.get("walk", {}))
    for t in (pj.get("table", {}) or {}).values():
        n += len((t or {}).get("columns", {}))
    return n


def _ip_already_monitored(ip_address, exclude_device_id=None):
    """True if another device with this IP already has a template (i.e. is being monitored)."""
    qs = Device.objects.filter(ip_address=ip_address, device_template__isnull=False)
    if exclude_device_id:
        qs = qs.exclude(pk=exclude_device_id)
    return qs.exists()


def AIOnboarding(request):
    """Approval-queue UI: candidate devices (no template) + drafts to review."""
    # Candidates = devices with no template AND whose IP isn't already monitored by another
    # device (check B — don't offer to onboard a device that's effectively already covered).
    monitored_ips = set(Device.objects.filter(device_template__isnull=False)
                        .values_list("ip_address", flat=True))
    candidates = (Device.objects.filter(device_template__isnull=True)
                  .exclude(ip_address__in=monitored_ips)
                  .select_related("credential", "network"))
    drafts = list(DraftDefinition.objects.all()[:50])
    for d in drafts:
        d.oid_count = _oid_count(d.profile_json or {})
        d.profile_pretty = json.dumps(d.profile_json or {}, indent=2)
    settings_obj = AISettings.load()
    return render(request, "ai_onboarding.html", {
        "candidates": candidates,
        "drafts": drafts,
        "ai_settings": settings_obj,
        "ai_ready": bool(settings_obj.enabled and settings_obj.agent_url and settings_obj.api_key),
    })


@require_admin_role
@require_http_methods(["POST"])
def SaveAISettings(request):
    s = AISettings.load()
    s.agent_url = request.POST.get("agent_url", "").strip()
    s.agent_id = request.POST.get("agent_id", "snmp-profile-author").strip() or "snmp-profile-author"
    key = request.POST.get("api_key", "").strip()
    if key:                       # only overwrite if a new key was entered
        s.api_key = key
    s.verify_tls = request.POST.get("verify_tls", "true") == "true"
    s.enabled = request.POST.get("enabled", "false") == "true"
    s.save()
    return JsonResponse({"success": True, "message": "AI settings saved"})


@require_admin_role
@require_http_methods(["POST"])
def GenerateDraft(request):
    """Walk a device live, ask the agent to author a profile, store as pending draft."""
    try:
        device_id = json.loads(request.body).get("device_id")
        device = Device.objects.select_related("credential", "network").get(pk=device_id)
        cred = device.credential or (device.network.credential if device.network else None)
        if not cred:
            return JsonResponse({"success": False, "error": "Device has no SNMP credential"}, status=400)

        # Check B: don't onboard an IP that's already monitored by another device.
        if _ip_already_monitored(device.ip_address, exclude_device_id=device.id):
            return JsonResponse({"success": False, "error":
                f"IP {device.ip_address} is already monitored by another device — onboarding skipped "
                f"to avoid a duplicate/overlapping definition."}, status=400)

        settings_obj = AISettings.load()
        if not (settings_obj.enabled and settings_obj.agent_url and settings_obj.api_key):
            return JsonResponse({"success": False, "error": "AI agent not configured (see AI Settings)"}, status=400)

        # 1) live discovery walk -> verified OIDs
        community = cred.get_community() if cred.version in ("1", "2c") else "public"
        sys_descr, populated, summary = snmp_discovery.discover_device(
            device.ip_address, device.port or 161, community, cred.version)

        vendor = sys_descr.split()[0] if sys_descr else ""
        proposed = f"{_slug(vendor)}_{_slug(device.name)}_ai"

        # 2) author via the agent, grounded on the walk
        result = agent_client.generate_profile(
            settings_obj, sys_descr=sys_descr, walk_summary=summary,
            vendor=vendor, proposed_name=proposed)

        draft = DraftDefinition.objects.create(
            device=device, target_ip=device.ip_address, sys_descr=sys_descr, vendor=result["vendor"],
            proposed_name=result["name"], status="pending", profile_json=result["profile_json"],
            normalizers=result.get("normalizers", []),
            unverified=result["unverified"], walk_summary=summary, agent_notes=result["agent_notes"])
        return JsonResponse({"success": True, "draft_id": draft.id,
                             "unverified_count": len(result["unverified"])})
    except Device.DoesNotExist:
        return JsonResponse({"success": False, "error": "Device not found"}, status=404)
    except Exception as e:
        logger.exception("GenerateDraft failed")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
@require_http_methods(["POST"])
def ApproveDraft(request):
    """Turn an approved draft into a real Profile + DeviceTemplate and attach it."""
    try:
        draft = DraftDefinition.objects.get(pk=json.loads(request.body).get("draft_id"))
        if draft.status != "pending":
            return JsonResponse({"success": False, "error": f"Draft already {draft.status}"}, status=400)
        if Profile.objects.filter(name=draft.proposed_name).exists():
            return JsonResponse({"success": False, "error": "A profile with that name already exists"}, status=400)
        # Check B (at approval): refuse if the device's IP became monitored since the draft was created.
        if draft.device and _ip_already_monitored(draft.device.ip_address, exclude_device_id=draft.device.id):
            return JsonResponse({"success": False, "error":
                f"IP {draft.device.ip_address} is now monitored by another device — not attaching a "
                f"duplicate. Reject this draft or remove the other device first."}, status=400)

        profile = Profile.objects.create(
            name=draft.proposed_name, description=f"[AI-authored] {draft.vendor}".strip(),
            vendor=draft.vendor or "", product="", profile_data=draft.profile_json,
            normalizers=draft.normalizers or [])

        tpl_name = f"{draft.proposed_name}_template"
        template = DeviceTemplate.objects.create(
            name=tpl_name, vendor=draft.vendor or "Any", official=False,
            matching_rules=[draft.vendor] if draft.vendor else [])
        template.profiles.add(profile)

        if draft.device:
            draft.device.device_template = template
            draft.device.save()

        draft.status = "approved"
        draft.reviewed_at = timezone.now()
        draft.reviewed_by = getattr(request.user, "username", "")
        draft.created_profile = profile
        draft.created_template = template
        draft.save()
        return JsonResponse({"success": True, "message": "Approved - profile + template created and attached. "
                                                         "Deploy from the SNMP page to start polling."})
    except DraftDefinition.DoesNotExist:
        return JsonResponse({"success": False, "error": "Draft not found"}, status=404)
    except Exception as e:
        logger.exception("ApproveDraft failed")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
@require_http_methods(["POST"])
def RejectDraft(request):
    try:
        draft = DraftDefinition.objects.get(pk=json.loads(request.body).get("draft_id"))
        draft.status = "rejected"
        draft.reviewed_at = timezone.now()
        draft.reviewed_by = getattr(request.user, "username", "")
        draft.save()
        return JsonResponse({"success": True, "message": "Draft rejected"})
    except DraftDefinition.DoesNotExist:
        return JsonResponse({"success": False, "error": "Draft not found"}, status=404)
