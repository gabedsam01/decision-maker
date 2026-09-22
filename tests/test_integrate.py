from pathlib import Path

from decisors.integrate import install_pi_assets, install_pi_extension


def test_installs_self_contained_pi_adapter(tmp_path: Path) -> None:
    target = tmp_path / "pi" / "index.js"
    installed = install_pi_extension(target)
    text = installed.read_text(encoding="utf-8")
    assert installed == target
    assert 'registerCommand("decision"' in text
    assert 'name: "decision_evaluate"' in text
    assert 'spawn("decisors", ["bridge"]' in text
    assert "Enable cloud decisions for this session?" in text
    assert 'pi.on("session_shutdown"' in text
    assert 'from "typebox"' not in text
    assert "ui.custom" in text
    assert "setWorkingMessage" in text
    assert "DecisionPanel" in text
    assert '"decision_command"' in text
    assert '"decision_where"' in text
    assert "@mariozechner/pi-tui" not in text


def test_installs_skill_and_prompt(tmp_path: Path) -> None:
    assets = install_pi_assets(tmp_path)
    assert "decision_where" in assets["skill"].read_text(encoding="utf-8")
    assert "decision_command" in assets["prompt"].read_text(encoding="utf-8")
    assert assets["skill"].parent.name == "decisores-decisoes"
