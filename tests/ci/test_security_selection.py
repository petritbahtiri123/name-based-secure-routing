from scripts.ci.check import command_groups

def test_core_selects_only_offline_campaign_contract_tests():
    commands = command_groups("python-core")
    core = next(c for c in commands if c.name == "python-core")
    assert core.argv.count("tests/security/test_adversarial_campaign.py") == 1
    assert "scripts/security/adversarial_campaign.py" not in core.argv
    assert all("--output" not in c.argv for c in commands)
