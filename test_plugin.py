import importlib.util
import pathlib

PLUGIN_PATH = pathlib.Path(__file__).with_name('plugin.py')
spec = importlib.util.spec_from_file_location('discord_thread_title_plugin', PLUGIN_PATH)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


def test_sender_allowed_for_xtra_and_mics():
    assert plugin.sender_allowed('[Xtra] 3全自動模式') is True
    assert plugin.sender_allowed('[Mics] 可以') is True
    assert plugin.sender_allowed('[Other] 不要亂改') is False


def test_propose_auto_title_uses_newer_topic_keywords():
    title = plugin.propose_auto_title(
        current_title='Hermes 上下文與主題改名',
        user_message='[Xtra] 3全自動模式',
        assistant_response='可以做全自動模式，偵測主題漂移後自動改名。',
    )
    assert title is not None
    assert '全自動' in title or '主題改名' in title


def test_propose_auto_title_ignores_small_talk():
    title = plugin.propose_auto_title(
        current_title='Hermes 上下文與主題改名',
        user_message='[Xtra] 牛阿歐力棒棒棒',
        assistant_response='謝啦 Xtra 😎',
    )
    assert title is None


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


def test_failed_patch_does_not_mark_duplicate(monkeypatch):
    source = {'platform': 'discord', 'thread_id': '123', 'chat_name': 'Guild / 舊標題'}
    monkeypatch.setattr(plugin, 'source_for_session', lambda session_id: source)
    monkeypatch.setattr(plugin, 'discord_patch_thread', lambda thread_id, new_name: {'ok': False, 'error': 'boom'})
    plugin.LAST_MESSAGE_SIG_BY_SESSION.clear()
    plugin.LAST_AUTO_TITLE_BY_SESSION.clear()

    plugin.maybe_auto_rename('s1', '[Xtra] 3全自動模式', '可以做全自動模式，偵測主題漂移後自動改名。')
    assert plugin.LAST_AUTO_RENAME_STATUS == 'error'
    assert 's1' not in plugin.LAST_MESSAGE_SIG_BY_SESSION
    assert 's1' not in plugin.LAST_AUTO_TITLE_BY_SESSION
