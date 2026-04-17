#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.urls import path
from . import views

urlpatterns = [
    path("", views.documentation_home, name="DocumentationHome"),
    path("<path:doc_path>/", views.render_documentation, name="RenderDocumentation"),
]
