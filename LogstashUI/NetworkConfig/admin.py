from django.contrib import admin
from .models import Device, Credential, Profile

admin.site.register(Device)
admin.site.register(Credential)
admin.site.register(Profile)
