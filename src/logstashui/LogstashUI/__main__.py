#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Delegate ``python -m LogstashUI`` to ``LogstashUI.cli.main``."""

from LogstashUI.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
