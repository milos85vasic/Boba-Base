import pathlib
import sys
import yaml

def get_on(data):
    """Extract the 'on' mapping from YAML data, handling 'on' parsed as boolean True."""
    if "on" in data:
        return data["on"]
    if True in data:  # 'on' parsed as boolean True
        return data[True]
    raise KeyError("'on' key not found")

def test_ci_workflows_exist():
    """Assert each expected workflow file exists in .github/workflows/"""
    root = pathlib.Path(__file__).resolve().parents[2]
    workflows_dir = root / ".github" / "workflows"
    
    expected = {
        "syntax.yml",
        "unit.yml", 
        "integration.yml",
        "nightly.yml",
        "security.yml",
    }
    
    missing = []
    for name in expected:
        if not (workflows_dir / name).exists():
            missing.append(name)
    
    assert missing == [], f"Missing workflow files: {missing}"
    
    # Check each has an 'on' key
    for name in expected:
        path = workflows_dir / name
        with open(path) as f:
            data = yaml.safe_load(f)
        try:
            on = get_on(data)
        except KeyError:
            raise AssertionError(f"{name} missing 'on' key")
        
        # syntax, unit, integration must have push + pull_request triggers
        if name in {"syntax.yml", "unit.yml", "integration.yml"}:
            # Accept dict with push/pull_request keys, or list containing those strings
            if isinstance(on, dict):
                assert "push" in on, f"{name} missing push trigger"
                assert "pull_request" in on, f"{name} missing pull_request trigger"
            elif isinstance(on, list):
                assert "push" in on, f"{name} missing push in list"
                assert "pull_request" in on, f"{name} missing pull_request in list"
            else:
                raise AssertionError(f"{name} 'on' is neither dict nor list: {type(on)}")
        
        # nightly and security may have different triggers (schedule, workflow_dispatch)
        # but we still require they have an 'on' key (already checked)
    
    # Additional check: no workflow_dispatch‑only workflows (they must also have push/PR)
    # except nightly/security which may be schedule‑only
    for name in {"syntax.yml", "unit.yml", "integration.yml"}:
        path = workflows_dir / name
        with open(path) as f:
            data = yaml.safe_load(f)
        on = get_on(data)
        if isinstance(on, dict):
            # If workflow_dispatch is the only key, that's manual‑only → reject
            keys = set(on.keys())
            if keys == {"workflow_dispatch"}:
                raise AssertionError(f"{name} is workflow_dispatch‑only (needs push/PR)")
        elif isinstance(on, list):
            if "workflow_dispatch" in on and len(on) == 1:
                raise AssertionError(f"{name} is workflow_dispatch‑only (needs push/PR)")