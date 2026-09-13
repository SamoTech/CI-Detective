def test_ci_detective_e2e_failure_probe():
    """Intentional failure used only to validate PR diagnosis publishing."""
    raise TypeError("classify() missing 1 required positional argument: 'config'")
