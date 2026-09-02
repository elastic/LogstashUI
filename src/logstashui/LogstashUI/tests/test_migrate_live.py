#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("LOGSTASHUI_LIVE_DB") != "1",
    reason="set LOGSTASHUI_LIVE_DB=1 (bin/test_databases.sh)",
)


def test_live_placeholder():
    pytest.skip("migrator live tests land in Task 7")
