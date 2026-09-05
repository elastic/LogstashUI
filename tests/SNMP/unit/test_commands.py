#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Tests for the sync_snmp_official_data management command and the
sync_official_profiles / sync_official_device_templates snmp_crud helpers
it delegates to.

Test categories:
  - sync_official_profiles()       individual function behaviour
  - sync_official_device_templates() individual function behaviour
  - call_command('sync_snmp_official_data') end-to-end command behaviour
  - --cleanup path (delete / orphan stale official records)
"""

import json
import os

import pytest
from django.core.management import call_command
from io import StringIO

from SNMP.snmp_crud import sync_official_profiles, sync_official_device_templates
from SNMP.models import Profile, DeviceTemplate


# ---------------------------------------------------------------------------
# Shared data
# ---------------------------------------------------------------------------

MINIMAL_PROFILE = {
    "official_key": "test_profile_key",
    "description": "A test profile",
    "vendor": "Generic",
    "product": "",
}

MINIMAL_TEMPLATE = {
    "official_key": "test_template_key",
    "name": "Test Template",
    "description": "A test template",
    "vendor": "Generic",
    "model": "",
    "product": "",
    "matching_rules": [],
    "profiles": [],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(directory, filename, data):
    with open(os.path.join(directory, filename), "w", encoding="utf-8") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def profile_dir(tmp_path, settings):
    """
    Create the official_profiles directory and point settings.BASE_DIR to
    the temp root.  Tests that only exercise sync_official_profiles() use this.
    """
    dirpath = tmp_path / "SNMP" / "data" / "official_profiles"
    dirpath.mkdir(parents=True)
    settings.BASE_DIR = str(tmp_path)
    return str(dirpath)


@pytest.fixture
def template_dir(tmp_path, settings):
    """
    Create BOTH data directories and point settings.BASE_DIR to the temp root.
    Tests that exercise sync_official_device_templates() use this.
    """
    (tmp_path / "SNMP" / "data" / "official_profiles").mkdir(parents=True)
    dirpath = tmp_path / "SNMP" / "data" / "official_device_templates"
    dirpath.mkdir(parents=True)
    settings.BASE_DIR = str(tmp_path)
    return str(dirpath)


@pytest.fixture
def both_dirs(tmp_path, settings):
    """
    Creates both directories and returns (profile_dir_str, template_dir_str).
    Used by command-level tests that exercise the full pipeline.
    """
    p = tmp_path / "SNMP" / "data" / "official_profiles"
    t = tmp_path / "SNMP" / "data" / "official_device_templates"
    p.mkdir(parents=True)
    t.mkdir(parents=True)
    settings.BASE_DIR = str(tmp_path)
    return str(p), str(t)


# ---------------------------------------------------------------------------
# sync_official_profiles — new record creation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_profiles_creates_new_profile(profile_dir):
    _write_json(profile_dir, "test_profile.json", MINIMAL_PROFILE)
    sync_official_profiles()
    assert Profile.objects.filter(official_key="test_profile_key").exists()


@pytest.mark.django_db
def test_sync_profiles_stores_name_with_json_extension(profile_dir):
    _write_json(profile_dir, "test_profile.json", MINIMAL_PROFILE)
    sync_official_profiles()
    profile = Profile.objects.get(official_key="test_profile_key")
    assert profile.name == "test_profile.json"


@pytest.mark.django_db
def test_sync_profiles_sets_placeholder_flag(profile_dir):
    _write_json(profile_dir, "test_profile.json", MINIMAL_PROFILE)
    sync_official_profiles()
    profile = Profile.objects.get(official_key="test_profile_key")
    assert profile.profile_data == {"is_official_placeholder": True}


@pytest.mark.django_db
def test_sync_profiles_stores_vendor_and_product(profile_dir):
    data = {**MINIMAL_PROFILE, "vendor": "Cisco", "product": "Catalyst"}
    _write_json(profile_dir, "test_profile.json", data)
    sync_official_profiles()
    profile = Profile.objects.get(official_key="test_profile_key")
    assert profile.vendor == "Cisco"
    assert profile.product == "Catalyst"


# ---------------------------------------------------------------------------
# sync_official_profiles — update existing record
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_profiles_updates_existing_record(profile_dir):
    _write_json(profile_dir, "test_profile.json", MINIMAL_PROFILE)
    sync_official_profiles()

    updated = {**MINIMAL_PROFILE, "description": "Updated description", "vendor": "Cisco"}
    _write_json(profile_dir, "test_profile.json", updated)
    sync_official_profiles()

    profile = Profile.objects.get(official_key="test_profile_key")
    assert profile.description == "Updated description"
    assert profile.vendor == "Cisco"
    assert Profile.objects.filter(official_key="test_profile_key").count() == 1


@pytest.mark.django_db
def test_sync_profiles_idempotent(profile_dir):
    _write_json(profile_dir, "test_profile.json", MINIMAL_PROFILE)
    sync_official_profiles()
    sync_official_profiles()
    assert Profile.objects.filter(official_key="test_profile_key").count() == 1


# ---------------------------------------------------------------------------
# sync_official_profiles — fix #1: is_orphaned cleared on restoration
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_profiles_clears_is_orphaned_on_restoration(profile_dir):
    """
    Regression test for fix #1.
    A profile previously marked is_orphaned=True must have the flag removed
    the next time its backing JSON is present during sync.
    """
    _write_json(profile_dir, "test_profile.json", MINIMAL_PROFILE)
    sync_official_profiles()

    # Simulate cleanup having orphaned the profile
    profile = Profile.objects.get(official_key="test_profile_key")
    profile.profile_data = {"is_official_placeholder": True, "is_orphaned": True}
    profile.save()
    assert profile.profile_data.get("is_orphaned") is True

    # Re-sync with the JSON still present
    sync_official_profiles()
    profile.refresh_from_db()

    assert "is_orphaned" not in profile.profile_data
    assert profile.profile_data == {"is_official_placeholder": True}


@pytest.mark.django_db
def test_sync_profiles_clears_arbitrary_stale_flags(profile_dir):
    """profile_data is always reset to a clean placeholder on sync."""
    _write_json(profile_dir, "test_profile.json", MINIMAL_PROFILE)
    sync_official_profiles()

    profile = Profile.objects.get(official_key="test_profile_key")
    profile.profile_data = {"is_official_placeholder": True, "custom_flag": "leftover"}
    profile.save()

    sync_official_profiles()
    profile.refresh_from_db()
    assert profile.profile_data == {"is_official_placeholder": True}


# ---------------------------------------------------------------------------
# sync_official_profiles — fix #6: missing vendor defaults to 'Any'
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_profiles_missing_vendor_defaults_to_any(profile_dir):
    """
    Regression test for fix #6.
    A JSON file that omits the vendor key must still produce a DB record
    (vendor='Any') rather than being silently skipped by a full_clean() failure.
    """
    no_vendor = {k: v for k, v in MINIMAL_PROFILE.items() if k != "vendor"}
    _write_json(profile_dir, "no_vendor.json", no_vendor)
    sync_official_profiles()

    profile = Profile.objects.get(official_key="test_profile_key")
    assert profile.vendor == "Any"


# ---------------------------------------------------------------------------
# sync_official_profiles — skip / guard cases
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_profiles_skips_file_without_official_key(profile_dir):
    no_key = {k: v for k, v in MINIMAL_PROFILE.items() if k != "official_key"}
    _write_json(profile_dir, "no_key.json", no_key)
    sync_official_profiles()
    assert Profile.objects.count() == 0


@pytest.mark.django_db
def test_sync_profiles_ignores_non_json_files(profile_dir):
    with open(os.path.join(profile_dir, "readme.txt"), "w") as f:
        f.write("not a profile")
    sync_official_profiles()
    assert Profile.objects.count() == 0


@pytest.mark.django_db
def test_sync_profiles_handles_empty_directory(profile_dir):
    sync_official_profiles()
    assert Profile.objects.count() == 0


@pytest.mark.django_db
def test_sync_profiles_handles_malformed_json_gracefully(profile_dir):
    with open(os.path.join(profile_dir, "bad.json"), "w") as f:
        f.write("{ not valid json }")
    sync_official_profiles()
    assert Profile.objects.count() == 0


@pytest.mark.django_db
def test_sync_profiles_handles_multiple_files(profile_dir):
    for i in range(5):
        _write_json(profile_dir, f"profile_{i}.json", {
            **MINIMAL_PROFILE,
            "official_key": f"key_{i}",
        })
    sync_official_profiles()
    assert Profile.objects.filter(official_key__startswith="key_").count() == 5


# ---------------------------------------------------------------------------
# sync_official_profiles — legacy backfill path
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_profiles_backfills_official_key_for_legacy_record(profile_dir):
    """
    A pre-existing DB record that lacks official_key should have it backfilled
    when a JSON file with the matching name is found.
    """
    legacy = Profile.objects.create(
        name="legacy_profile.json",
        official_key=None,
        vendor="Generic",
        profile_data={"is_official_placeholder": True},
    )
    _write_json(profile_dir, "legacy_profile.json", {
        **MINIMAL_PROFILE,
        "official_key": "legacy_key",
    })
    sync_official_profiles()

    legacy.refresh_from_db()
    assert legacy.official_key == "legacy_key"
    assert Profile.objects.filter(official_key="legacy_key").count() == 1


# ---------------------------------------------------------------------------
# sync_official_device_templates — new record creation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_templates_creates_new_template(template_dir):
    _write_json(template_dir, "test_template.json", MINIMAL_TEMPLATE)
    sync_official_device_templates()
    assert DeviceTemplate.objects.filter(official_key="test_template_key").exists()


@pytest.mark.django_db
def test_sync_templates_is_marked_official(template_dir):
    _write_json(template_dir, "test_template.json", MINIMAL_TEMPLATE)
    sync_official_device_templates()
    template = DeviceTemplate.objects.get(official_key="test_template_key")
    assert template.official is True


@pytest.mark.django_db
def test_sync_templates_uses_name_field_not_filename(template_dir):
    """The 'name' key in JSON is used as the DB name, not the filename stem."""
    data = {**MINIMAL_TEMPLATE, "name": "My Custom Name"}
    _write_json(template_dir, "file_name_irrelevant.json", data)
    sync_official_device_templates()
    assert DeviceTemplate.objects.filter(name="My Custom Name").exists()


@pytest.mark.django_db
def test_sync_templates_stores_vendor_model_product(template_dir):
    data = {**MINIMAL_TEMPLATE, "vendor": "Dell", "model": "PowerEdge", "product": "iDRAC"}
    _write_json(template_dir, "test_template.json", data)
    sync_official_device_templates()
    template = DeviceTemplate.objects.get(official_key="test_template_key")
    assert template.vendor == "Dell"
    assert template.model == "PowerEdge"
    assert template.product == "iDRAC"


# ---------------------------------------------------------------------------
# sync_official_device_templates — update existing record
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_templates_updates_existing_record(template_dir):
    _write_json(template_dir, "test_template.json", MINIMAL_TEMPLATE)
    sync_official_device_templates()

    updated = {**MINIMAL_TEMPLATE, "description": "Updated", "vendor": "Cisco"}
    _write_json(template_dir, "test_template.json", updated)
    sync_official_device_templates()

    template = DeviceTemplate.objects.get(official_key="test_template_key")
    assert template.description == "Updated"
    assert template.vendor == "Cisco"
    assert DeviceTemplate.objects.filter(official_key="test_template_key").count() == 1


@pytest.mark.django_db
def test_sync_templates_idempotent(template_dir):
    _write_json(template_dir, "test_template.json", MINIMAL_TEMPLATE)
    sync_official_device_templates()
    sync_official_device_templates()
    assert DeviceTemplate.objects.filter(official_key="test_template_key").count() == 1


# ---------------------------------------------------------------------------
# sync_official_device_templates — profile linking (three lookup paths)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_templates_links_profiles_via_official_key(tmp_path, settings):
    """Primary path: profile resolved by its official_key value."""
    (tmp_path / "SNMP" / "data" / "official_profiles").mkdir(parents=True)
    tdir = tmp_path / "SNMP" / "data" / "official_device_templates"
    tdir.mkdir(parents=True)
    settings.BASE_DIR = str(tmp_path)

    profile = Profile.objects.create(
        official_key="linked_profile_key",
        name="linked_profile.json",
        vendor="Generic",
        profile_data={"is_official_placeholder": True},
    )
    data = {**MINIMAL_TEMPLATE, "profiles": ["linked_profile_key"]}
    _write_json(str(tdir), "test_template.json", data)
    sync_official_device_templates()

    template = DeviceTemplate.objects.get(official_key="test_template_key")
    assert profile in template.profiles.all()


@pytest.mark.django_db
def test_sync_templates_links_profiles_via_json_name_fallback(tmp_path, settings):
    """
    Fallback path: profile referenced without .json extension is found by
    appending .json to the lookup name (un-migrated official profile).
    """
    (tmp_path / "SNMP" / "data" / "official_profiles").mkdir(parents=True)
    tdir = tmp_path / "SNMP" / "data" / "official_device_templates"
    tdir.mkdir(parents=True)
    settings.BASE_DIR = str(tmp_path)

    profile = Profile.objects.create(
        official_key=None,
        name="linked_profile.json",
        vendor="Generic",
        profile_data={"is_official_placeholder": True},
    )
    data = {**MINIMAL_TEMPLATE, "profiles": ["linked_profile"]}
    _write_json(str(tdir), "test_template.json", data)
    sync_official_device_templates()

    template = DeviceTemplate.objects.get(official_key="test_template_key")
    assert profile in template.profiles.all()


@pytest.mark.django_db
def test_sync_templates_links_profiles_via_bare_name_fallback(tmp_path, settings):
    """
    Fallback path: user-created custom profile matched by exact bare name.
    """
    (tmp_path / "SNMP" / "data" / "official_profiles").mkdir(parents=True)
    tdir = tmp_path / "SNMP" / "data" / "official_device_templates"
    tdir.mkdir(parents=True)
    settings.BASE_DIR = str(tmp_path)

    profile = Profile.objects.create(
        official_key=None,
        name="custom_profile",
        vendor="Generic",
        profile_data={"get": {}, "walk": {}, "table": {}},
    )
    data = {**MINIMAL_TEMPLATE, "profiles": ["custom_profile"]}
    _write_json(str(tdir), "test_template.json", data)
    sync_official_device_templates()

    template = DeviceTemplate.objects.get(official_key="test_template_key")
    assert profile in template.profiles.all()


@pytest.mark.django_db
def test_sync_templates_links_multiple_profiles(tmp_path, settings):
    (tmp_path / "SNMP" / "data" / "official_profiles").mkdir(parents=True)
    tdir = tmp_path / "SNMP" / "data" / "official_device_templates"
    tdir.mkdir(parents=True)
    settings.BASE_DIR = str(tmp_path)

    profiles = []
    for i in range(3):
        p = Profile.objects.create(
            official_key=f"profile_key_{i}",
            name=f"profile_{i}.json",
            vendor="Generic",
            profile_data={"is_official_placeholder": True},
        )
        profiles.append(p)

    data = {**MINIMAL_TEMPLATE, "profiles": [f"profile_key_{i}" for i in range(3)]}
    _write_json(str(tdir), "test_template.json", data)
    sync_official_device_templates()

    template = DeviceTemplate.objects.get(official_key="test_template_key")
    assert template.profiles.count() == 3


# ---------------------------------------------------------------------------
# sync_official_device_templates — profile linking edge cases
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_templates_missing_profile_skipped_gracefully(template_dir):
    """
    A profile name listed in the JSON that doesn't exist in the DB should be
    silently skipped.  The template itself must still be created.
    """
    data = {**MINIMAL_TEMPLATE, "profiles": ["nonexistent_profile"]}
    _write_json(template_dir, "test_template.json", data)
    sync_official_device_templates()

    template = DeviceTemplate.objects.get(official_key="test_template_key")
    assert template.profiles.count() == 0


@pytest.mark.django_db
def test_sync_templates_empty_profiles_list_does_not_clear_existing(tmp_path, settings):
    """
    profiles: [] in JSON is treated as a no-op — existing M2M rows must not
    be cleared.  This is the current documented behaviour of the if-guard.
    """
    (tmp_path / "SNMP" / "data" / "official_profiles").mkdir(parents=True)
    tdir = tmp_path / "SNMP" / "data" / "official_device_templates"
    tdir.mkdir(parents=True)
    settings.BASE_DIR = str(tmp_path)

    profile = Profile.objects.create(
        official_key="kept_profile",
        name="kept_profile.json",
        vendor="Generic",
        profile_data={"is_official_placeholder": True},
    )
    template = DeviceTemplate.objects.create(
        official_key="test_template_key",
        name="Test Template",
        vendor="Generic",
        official=True,
    )
    template.profiles.add(profile)
    assert template.profiles.count() == 1

    _write_json(str(tdir), "test_template.json", {**MINIMAL_TEMPLATE, "profiles": []})
    sync_official_device_templates()

    template.refresh_from_db()
    assert template.profiles.count() == 1


# ---------------------------------------------------------------------------
# sync_official_device_templates — fix #6 and skip/guard cases
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sync_templates_missing_vendor_defaults_to_any(template_dir):
    """Regression test for fix #6 on the template sync path."""
    no_vendor = {k: v for k, v in MINIMAL_TEMPLATE.items() if k != "vendor"}
    _write_json(template_dir, "no_vendor.json", no_vendor)
    sync_official_device_templates()

    template = DeviceTemplate.objects.get(official_key="test_template_key")
    assert template.vendor == "Any"


@pytest.mark.django_db
def test_sync_templates_skips_file_without_official_key(template_dir):
    no_key = {k: v for k, v in MINIMAL_TEMPLATE.items() if k != "official_key"}
    _write_json(template_dir, "no_key.json", no_key)
    sync_official_device_templates()
    assert DeviceTemplate.objects.count() == 0


@pytest.mark.django_db
def test_sync_templates_handles_malformed_json_gracefully(template_dir):
    with open(os.path.join(template_dir, "bad.json"), "w") as f:
        f.write("{ not valid json }")
    sync_official_device_templates()
    assert DeviceTemplate.objects.count() == 0


@pytest.mark.django_db
def test_sync_templates_handles_empty_directory(template_dir):
    sync_official_device_templates()
    assert DeviceTemplate.objects.count() == 0


# ---------------------------------------------------------------------------
# Management command — call_command end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_command_syncs_profiles_and_templates(both_dirs):
    profile_dir, template_dir = both_dirs
    _write_json(profile_dir, "p.json", {**MINIMAL_PROFILE, "official_key": "cmd_profile_key"})
    _write_json(template_dir, "t.json", {**MINIMAL_TEMPLATE, "official_key": "cmd_template_key"})

    call_command("sync_snmp_official_data", stdout=StringIO())

    assert Profile.objects.filter(official_key="cmd_profile_key").exists()
    assert DeviceTemplate.objects.filter(official_key="cmd_template_key").exists()


@pytest.mark.django_db
def test_command_output_mentions_profiles_and_templates(both_dirs):
    profile_dir, _ = both_dirs
    _write_json(profile_dir, "p.json", {**MINIMAL_PROFILE, "official_key": "out_key"})

    out = StringIO()
    call_command("sync_snmp_official_data", stdout=out)
    output = out.getvalue().lower()

    assert "profile" in output
    assert "template" in output


@pytest.mark.django_db
def test_command_does_not_raise_on_malformed_json(both_dirs):
    """A corrupt JSON file must not abort startup."""
    profile_dir, _ = both_dirs
    with open(os.path.join(profile_dir, "bad.json"), "w") as f:
        f.write("{ not valid json }")

    out = StringIO()
    call_command("sync_snmp_official_data", stdout=out)


# ---------------------------------------------------------------------------
# Management command — --cleanup: stale-by-official_key records
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_command_without_cleanup_leaves_stale_records(both_dirs):
    """Without --cleanup, stale official records must persist in the DB."""
    _, _ = both_dirs
    Profile.objects.create(
        official_key="stale_key",
        name="stale.json",
        vendor="Any",
        profile_data={"is_official_placeholder": True},
    )

    call_command("sync_snmp_official_data", stdout=StringIO())
    assert Profile.objects.filter(official_key="stale_key").exists()


@pytest.mark.django_db
def test_command_cleanup_deletes_unused_stale_profile(both_dirs):
    """Stale official profile with no DeviceTemplate referencing it is deleted."""
    _, _ = both_dirs
    Profile.objects.create(
        official_key="stale_key",
        name="stale.json",
        vendor="Any",
        profile_data={"is_official_placeholder": True},
    )

    call_command("sync_snmp_official_data", cleanup=True, stdout=StringIO())
    assert not Profile.objects.filter(official_key="stale_key").exists()


@pytest.mark.django_db
def test_command_cleanup_orphans_in_use_stale_profile(both_dirs):
    """
    Stale official profile referenced by a DeviceTemplate must be marked
    is_orphaned=True instead of deleted.
    """
    _, _ = both_dirs
    stale_profile = Profile.objects.create(
        official_key="stale_in_use_key",
        name="stale_in_use.json",
        vendor="Any",
        profile_data={"is_official_placeholder": True},
    )
    using_template = DeviceTemplate.objects.create(
        name="Uses Stale Profile",
        vendor="Generic",
        official=False,
    )
    using_template.profiles.add(stale_profile)

    call_command("sync_snmp_official_data", cleanup=True, stdout=StringIO())

    stale_profile.refresh_from_db()
    assert Profile.objects.filter(official_key="stale_in_use_key").exists()
    assert stale_profile.profile_data.get("is_orphaned") is True


@pytest.mark.django_db
def test_command_cleanup_deletes_unused_stale_template(both_dirs):
    """Stale official template with no devices assigned is deleted."""
    _, _ = both_dirs
    DeviceTemplate.objects.create(
        official_key="stale_template_key",
        name="Stale Template",
        vendor="Any",
        official=True,
    )

    call_command("sync_snmp_official_data", cleanup=True, stdout=StringIO())
    assert not DeviceTemplate.objects.filter(official_key="stale_template_key").exists()


@pytest.mark.django_db
def test_command_cleanup_does_not_delete_in_use_stale_template(both_dirs):
    """
    Stale official template with devices still assigned must be kept.
    The command should log a warning but not delete it.
    """
    from SNMP.models import Credential, Network, Device
    from PipelineManager.models import Connection

    _, _ = both_dirs
    stale_template = DeviceTemplate.objects.create(
        official_key="stale_in_use_template",
        name="Stale In Use",
        vendor="Any",
        official=True,
    )

    conn = Connection.objects.create(
        name="Test Conn",
        connection_type="CENTRALIZED",
        host="https://localhost:9200",
        username="elastic",
        password="changeme",
    )
    cred = Credential.objects.create(name="cred", version="2c", community="public")
    net = Network.objects.create(
        name="net",
        network_range="10.0.0.0/24",
        connection=conn,
        discovery_credential=cred,
        interval=30,
    )
    Device.objects.create(
        name="test_device",
        ip_address="10.0.0.1",
        port=161,
        retries=2,
        timeout=1000,
        credential=cred,
        network=net,
        device_template=stale_template,
    )

    call_command("sync_snmp_official_data", cleanup=True, stdout=StringIO())
    assert DeviceTemplate.objects.filter(official_key="stale_in_use_template").exists()


# ---------------------------------------------------------------------------
# Management command — --cleanup: legacy (stale-by-flag) records
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_command_cleanup_deletes_legacy_stale_profile(both_dirs):
    """
    Old-style official profiles (no official_key, has is_official_placeholder)
    that were not backfilled during sync are treated as stale and deleted.
    """
    _, _ = both_dirs
    legacy = Profile.objects.create(
        official_key=None,
        name="legacy_no_key.json",
        vendor="Any",
        profile_data={"is_official_placeholder": True},
    )

    call_command("sync_snmp_official_data", cleanup=True, stdout=StringIO())
    assert not Profile.objects.filter(pk=legacy.pk).exists()


@pytest.mark.django_db
def test_command_cleanup_deletes_legacy_stale_template(both_dirs):
    """
    Official templates with no official_key after sync ran are stale and
    must be deleted when not in use.
    """
    _, _ = both_dirs
    legacy = DeviceTemplate.objects.create(
        official_key=None,
        name="Legacy Template",
        vendor="Any",
        official=True,
    )

    call_command("sync_snmp_official_data", cleanup=True, stdout=StringIO())
    assert not DeviceTemplate.objects.filter(pk=legacy.pk).exists()


# ---------------------------------------------------------------------------
# Management command — --cleanup: output counts
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_command_cleanup_output_reports_deleted_counts(both_dirs):
    _, _ = both_dirs
    Profile.objects.create(
        official_key="deleted_profile",
        name="deleted.json",
        vendor="Any",
        profile_data={"is_official_placeholder": True},
    )

    out = StringIO()
    call_command("sync_snmp_official_data", cleanup=True, stdout=out)
    output = out.getvalue().lower()

    assert "deleted" in output or "profile" in output
