import sys
from monika.infrastructure.infra.audit_settings_keys import audit_keys, flatten_dict


def test_flatten_dict_nested():
    data = {
        "a": 1,
        "b": {
            "c": 2,
            "d": {
                "e": 3,
            },
        },
    }
    flat = flatten_dict(data)
    assert flat == {
        "a": 1,
        "b.c": 2,
        "b.d.e": 3,
    }


def test_audit_settings_keys_importable_without_scripts_in_syspath(monkeypatch):
    # Ensure importing without 'scripts' directory in sys.path succeeds
    filtered_path = [p for p in sys.path if not p.endswith("scripts")]
    monkeypatch.setattr(sys, "path", filtered_path)

    import monika.infrastructure.infra.audit_settings_keys as mod

    assert hasattr(mod, "flatten_dict")
    assert hasattr(mod, "audit_keys")
    assert callable(mod.flatten_dict)
    assert callable(mod.audit_keys)
