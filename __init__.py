import importlib.util
from pathlib import Path

_plugin_path = Path(__file__).with_name('plugin.py')
_spec = importlib.util.spec_from_file_location('discord_thread_title_plugin_runtime', _plugin_path)
_module = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_module)
register = _module.register
