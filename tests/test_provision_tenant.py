"""provision_tenant: чистые функции + dry-run (без SSH).

Must set env BEFORE importing api/config (для сверки токена с api).
"""
import os
import time

os.environ.setdefault("CRM_SECRET", "test_secret_for_unit_tests")
os.environ.setdefault("CRM_PASSWORD", "test_crm_pass")
os.environ.setdefault("SALON_ID", "testsalon")
os.environ.setdefault("CRM_TOKEN_FIXED", "fixed_test_crm_token")

import pytest

import api as api_module
import provision_tenant as pt


def test_pick_port_first_free():
    assert pt.pick_port(set()) == 8000
    assert pt.pick_port({8000, 8001}) == 8002


def test_pick_port_exhausted_raises():
    with pytest.raises(RuntimeError):
        pt.pick_port(set(pt.PORT_RANGE))


def test_setup_token_matches_api():
    exp = int(time.time()) + 3600
    from_provisioner = pt.make_setup_token("testsalon", "test_secret_for_unit_tests", exp)
    from_api = api_module._make_setup_token(exp)
    assert from_provisioner == from_api


def test_parse_setting_file():
    text = 'SERVER = "92.246.128.94"\n# PASS = "commented"\nPASS = "s3cret"\n'
    assert pt.parse_setting_file(text, "SERVER") == "92.246.128.94"
    assert pt.parse_setting_file(text, "PASS") == "s3cret"
    assert pt.parse_setting_file(text, "MISSING") == ""


def test_make_env_contains_org_and_secrets():
    class A:
        id = "zima"
        bot_token = "1:AA"
        admin_tg_id = "42"
        type = "coworking"
        name = "Зима"
        address = "Минск, ул. 1"
        phone = "+375291112233"
        tz = "Europe/Minsk"
    env = pt.make_env(A(), crm_secret="sec", crm_pass="pw", crm_token="tok")
    assert "SALON_ID=zima" in env
    assert "ORG_TYPE=coworking" in env
    assert "CRM_SECRET=sec" in env
    assert "CRM_TOKEN_FIXED=tok" in env
    assert "SALON_NAME=Зима" in env


def test_dry_run_no_ssh(capsys):
    rc = pt.main(["--id", "zima", "--name", "Салон Зима", "--bot-token", "1:ABC",
                  "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY-RUN" in out
    assert "SSH-подключение не выполняется" in out
    assert "zima-crm" in out  # юниты в плане


def test_bad_id_rejected():
    with pytest.raises(SystemExit):
        pt.main(["--id", "Bad Id!", "--name", "X", "--bot-token", "1:x"])


def test_cleanup_requires_yes(capsys):
    rc = pt.main(["--cleanup", "--id", "zima"])
    assert rc == 2
    assert "--yes" in capsys.readouterr().out


def test_unit_service_files_contain_tz_and_port():
    crm = pt.crm_service("/opt/x-bot", "x", "Название", 8012, "Europe/Minsk")
    pol = pt.polling_service("/opt/x-bot", "x", "Название", "Europe/Minsk")
    assert "--port 8012" in crm
    assert "Environment=SALON_ID=x" in crm and "Environment=SALON_ID=x" in pol
    assert "Environment=TZ=Europe/Minsk" in crm and "Environment=TZ=Europe/Minsk" in pol
    assert "bot.py" in pol
