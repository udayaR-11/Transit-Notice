"""Map TN_SOURCES keys to adapters. To add a real source: write an adapter, register it here."""
from config import config
from scraper.adapters.demo import DemoAdapter


def build_adapter(key):
    if key == "demo":
        return DemoAdapter(base_url=config.DEMO_BASE_URL)
    raise KeyError(f"unknown source '{key}'. Register it in scraper/registry.py")


def enabled_adapters():
    return [build_adapter(k) for k in config.SOURCES]
