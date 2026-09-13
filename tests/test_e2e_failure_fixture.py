def test_intentional_ci_failure():
    """Temporary E2E fixture: forces CI failure to exercise CI Detective."""
    raise TypeError("classify() missing 1 required positional argument: 'config'")
