"""Tests for config/region loading."""

import json
from unittest.mock import patch
from pathlib import Path

from toybaru.const import RegionConfig, _load_regions, _DEFAULTS, DATA_DIR


def test_default_regions():
    regions = _load_regions()
    assert "EU" in regions
    assert "NA" in regions
    assert regions["EU"].brand == "S"
    assert regions["NA"].brand == "S"
    assert "toyota-europe" in regions["EU"].auth_realm
    assert "subarudriverslogin" in regions["NA"].auth_realm


def test_custom_regions_json(tmp_path):
    config = {"EU": {"api_key": "my-custom-key"}}
    (tmp_path / "regions.json").write_text(json.dumps(config))
    with patch("toybaru.const.DATA_DIR", tmp_path):
        regions = _load_regions()
    assert regions["EU"].api_key == "my-custom-key"
    # Other fields stay default
    assert "toyota-europe" in regions["EU"].auth_realm


def test_custom_regions_merge(tmp_path):
    config = {"EU": {"client_id": "custom-client"}}
    (tmp_path / "regions.json").write_text(json.dumps(config))
    with patch("toybaru.const.DATA_DIR", tmp_path):
        regions = _load_regions()
    assert regions["EU"].client_id == "custom-client"
    assert regions["EU"].name == "EU"
    assert regions["EU"].brand == "S"


def test_new_region(tmp_path):
    config = {"JP": {
        "name": "JP", "auth_realm": "https://jp.example.com", "api_base_url": "https://api.jp.example.com",
        "client_id": "jp-client", "redirect_uri": "com.jp.app:/callback", "basic_auth": "abc123",
        "api_key": "jp-key", "brand": "S", "region": "JP",
    }}
    (tmp_path / "regions.json").write_text(json.dumps(config))
    with patch("toybaru.const.DATA_DIR", tmp_path):
        regions = _load_regions()
    assert "JP" in regions
    assert regions["JP"].api_base_url == "https://api.jp.example.com"
    # Defaults still there
    assert "EU" in regions
    assert "NA" in regions
