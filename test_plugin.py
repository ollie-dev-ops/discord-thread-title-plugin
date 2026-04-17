import importlib.util
import json
import pathlib

PLUGIN_PATH = pathlib.Path(__file__).with_name('plugin.py')
spec = importlib.util.spec_from_file_location('discord_thread_title_plugin', PLUGIN_PATH)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


def test_build_topic_guard_context_includes_tool_and_first_turn_directive(monkeypatch):
    monkeypatch.setattr(
        plugin,
        'source_for_session',
        lambda session_id: {
            'platform': 'discord',
            'thread_id': '1494707116454314115',
            'chat_name': 'Guild / Hermes 上下文與主題改名',
        },
    )
    ctx = plugin.build_topic_guard_context('s1', is_first_turn=True)
    assert ctx is not None
    assert 'Hermes 上下文與主題改名' not in ctx
    assert plugin.CHANGE_TOOL_NAME in ctx
    assert str(plugin.TITLE_SOFT_LIMIT) in ctx
    assert 'On the first turn' in ctx
    assert 'Do not ask for confirmation first' in ctx


def test_build_topic_guard_context_none_after_first_turn(monkeypatch):
    monkeypatch.setattr(
        plugin,
        'source_for_session',
        lambda session_id: {
            'platform': 'discord',
            'thread_id': '1494707116454314115',
            'chat_name': 'Guild / Hermes 上下文與主題改名',
        },
    )
    assert plugin.build_topic_guard_context('s1', is_first_turn=False) is None


def test_build_topic_guard_context_none_for_non_discord(monkeypatch):
    monkeypatch.setattr(plugin, 'source_for_session', lambda session_id: {'platform': 'telegram'})
    assert plugin.build_topic_guard_context('s1') is None


def test_build_topic_guard_context_none_without_thread(monkeypatch):
    monkeypatch.setattr(plugin, 'source_for_session', lambda session_id: {'platform': 'discord', 'chat_name': 'Guild / Title'})
    assert plugin.build_topic_guard_context('s1') is None


def test_loads_only_discord_bot_token_from_env_file(tmp_path, monkeypatch):
    fake_home = tmp_path / 'fake-home'
    hermes_dir = fake_home / '.hermes'
    hermes_dir.mkdir(parents=True)
    (hermes_dir / '.env').write_text(
        'OTHER_SECRET=should_not_load\nDISCORD_BOT_TOKEN=test-token-123\nDISCORD_TOKEN=legacy-should-not-load\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(plugin.Path, 'home', staticmethod(lambda: fake_home))
    monkeypatch.delenv('DISCORD_BOT_TOKEN', raising=False)
    monkeypatch.delenv('DISCORD_TOKEN', raising=False)
    monkeypatch.delenv('OTHER_SECRET', raising=False)

    token = plugin.load_discord_bot_token_from_env_file()
    assert token == 'test-token-123'
    assert plugin.discord_token() == 'test-token-123'
    assert 'OTHER_SECRET' not in plugin.os.environ
    assert 'DISCORD_TOKEN' not in plugin.os.environ


def test_get_thread_title_reads_current_session(monkeypatch):
    monkeypatch.setattr(
        plugin,
        'source_for_session',
        lambda session_id: {
            'platform': 'discord',
            'thread_id': '123',
            'chat_name': 'Guild / 新主題',
        },
    )
    result = json.loads(plugin.get_thread_title({}, session_id='s1'))
    assert result == {'success': True, 'thread_id': '123', 'title': '新主題'}


def test_change_thread_title_validates_required_fields():
    result = json.loads(plugin.change_thread_title({'thread_id': '', 'title': ''}))
    assert result['success'] is False


def test_change_thread_title_uses_session_thread_id_and_accepts_longer_titles(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        plugin,
        'source_for_session',
        lambda session_id: {
            'platform': 'discord',
            'thread_id': '123',
            'chat_name': 'Guild / 舊標題',
        },
    )

    def fake_patch(thread_id, title):
        captured['thread_id'] = thread_id
        captured['title'] = title
        return {'ok': True, 'name': title}

    monkeypatch.setattr(plugin, 'discord_patch_thread', fake_patch)
    long_title = '這是一個超過四十字元的標題這是一個超過四十字元的標題這是一個超過四十字元的標題'
    result = json.loads(plugin.change_thread_title({'thread_id': '123', 'title': long_title}, session_id='s1'))
    assert result['success'] is True
    assert captured['thread_id'] == '123'
    assert captured['title'] == long_title


def test_change_thread_title_rejects_when_no_active_thread_session(monkeypatch):
    monkeypatch.setattr(plugin, 'source_for_session', lambda session_id: None)
    result = json.loads(plugin.change_thread_title({'thread_id': '123', 'title': '新標題'}, session_id='s1'))
    assert result['success'] is False
    assert 'active Discord thread' in result['error']


def test_change_thread_title_rejects_mismatched_thread_id(monkeypatch):
    monkeypatch.setattr(
        plugin,
        'source_for_session',
        lambda session_id: {
            'platform': 'discord',
            'thread_id': '123',
            'chat_name': 'Guild / 舊標題',
        },
    )
    result = json.loads(plugin.change_thread_title({'thread_id': '999', 'title': '新標題'}, session_id='s1'))
    assert result['success'] is False
    assert 'mismatch' in result['error']


def test_register_adds_pre_llm_hook_and_two_tools():
    calls = {'hooks': [], 'tools': []}

    class DummyCtx:
        def register_hook(self, name, callback):
            calls['hooks'].append(name)

        def register_tool(self, **kwargs):
            calls['tools'].append(kwargs['name'])

    plugin.register(DummyCtx())
    assert 'on_session_start' in calls['hooks']
    assert 'pre_llm_call' in calls['hooks']
    assert plugin.GET_TOOL_NAME in calls['tools']
    assert plugin.CHANGE_TOOL_NAME in calls['tools']
