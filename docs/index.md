---
layout: default
title: Home
description: A visual tool for authoring, simulating, and managing Logstash pipelines
---

{% capture readme_content %}
{% include_relative ../README.md %}
{% endcapture %}

{{ readme_content | markdownify }}
