"""Run the suite in a dedicated database; never against the application database."""

import os
import sys

sys.path.insert(0, "/app")
os.environ["TEST_DATABASE_URL"] = (
    os.environ["DATABASE_URL"].rsplit("/", 1)[0] + "/workagent_test"
)
import pytest

raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider", "/app/tests"]))
