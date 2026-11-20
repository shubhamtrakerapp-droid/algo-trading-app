import sqlite3


def pytest_sessionfinish(session, exitstatus):
    """Safe session finish hook. Never delete historical production data."""
    pass

