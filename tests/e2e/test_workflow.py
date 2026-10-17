import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e
expect.set_options(timeout=20000)


def english(page, app_url):
    page.goto(app_url)
    page.get_by_role('combobox', name='UI Language').click()
    page.get_by_role('option', name='English', exact=True).click()
    expect(page.get_by_role('heading', name='Supported Subtitles', exact=True)).to_be_visible()


def upload(page, name='sample.srt', text='Hello'):
    page.get_by_test_id('stFileUploader').first.locator('input[type=file]').set_input_files({
        'name': name, 'mimeType': 'text/plain',
        'buffer': f'1\n00:00:01,000 --> 00:00:02,000\n{text}\n\n'.encode(),
    })
    expect(page.get_by_role('combobox', name='Input encoding')).to_be_visible()


def test_language_switch_and_upload(page, app_url):
    english(page, app_url)
    expect(page.get_by_role('heading', name='Subtitle Translator Studio')).to_be_visible()
    page.get_by_test_id('stFileUploader').first.locator('input[type=file]').set_input_files({
        'name': 'sample.srt', 'mimeType': 'text/plain',
        'buffer': b'1\n00:00:01,000 --> 00:00:02,000\nHello\n\n',
    })
    expect(page.get_by_text('Source language', exact=True)).to_be_visible()
    page.get_by_role('combobox', name='UI Language').click()
    page.get_by_role('option', name='日本語', exact=True).click()
    expect(page.get_by_role('heading', name='字幕翻訳スタジオ')).to_be_visible()


def test_translate_failure_retry_download(page, app_url, fake_api, tmp_path):
    english(page, app_url)
    page.get_by_role('button', name='Test Connection', exact=True).click()
    expect(page.get_by_text('Model (from API)', exact=True)).to_be_visible()
    page.get_by_role('button', name='Test translation (may incur cost)').click()
    expect(page.get_by_text('Hello, how are you? translated', exact=True)).to_be_visible()
    fake_api['fail'].add('RetryMe')
    upload(page, 'retry.srt', 'RetryMe')
    page.get_by_role('button', name='Start Translation', exact=True).click()
    expect(page.get_by_text('Failed items can be retried', exact=True)).to_be_visible(timeout=20000)
    fake_api['fail'].clear()
    page.get_by_role('button', name='Resume / retry failed items', exact=True).click()
    expect(page.get_by_text('Translation completed', exact=True)).to_be_visible(timeout=20000)
    expect(page.get_by_role('button', name='Apply edits and update download')).to_be_visible()
    page.get_by_text('Edit one subtitle', exact=True).click()
    page.get_by_role('textbox', name='Translation text').fill('Manually corrected subtitle')
    page.get_by_role('button', name='Apply single edit', exact=True).click()
    expect(page.get_by_text('Edits applied.', exact=True)).to_be_visible()
    with page.expect_download() as received:
        page.get_by_role('button', name='Download retry.zh.srt').click()
    path = tmp_path / 'result.srt'
    received.value.save_as(path)
    assert 'Manually corrected subtitle' in path.read_text(encoding='utf-8-sig')
    assert '00:00:01,000 --> 00:00:02,000' in path.read_text(encoding='utf-8-sig')


def test_clear_key_does_not_refill_from_environment(page, app_url):
    english(page, app_url)
    page.get_by_role('button', name='Save key', exact=True).click()
    expect(page.get_by_text('API key saved in encrypted storage.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Clear key', exact=True).click()
    expect(page.get_by_role('textbox', name='API key', exact=True)).to_have_value('')
    expect(page.get_by_role('checkbox', name='Remember API key (encrypted)')).not_to_be_checked()
    expect(page.get_by_role('button', name='Test Connection', exact=True)).to_be_disabled()


def test_cancel_and_resume_preserves_finished_line(page, app_url, fake_api):
    english(page, app_url)
    fake_api['entered'].clear()
    fake_api['release'].clear()
    fake_api['block'].add('BlockLine')
    try:
        upload(page, 'cancel.srt', 'BlockLine\n\n2\n00:00:03,000 --> 00:00:04,000\nNextLine')
        page.get_by_role('button', name='Start Translation', exact=True).click()
        expect(page.get_by_role('button', name='Cancel translation', exact=True)).to_be_visible()
        assert fake_api['entered'].wait(timeout=10)
        page.get_by_role('button', name='Cancel translation', exact=True).click()
        expect(page.get_by_text('Cancelling after current request...', exact=True)).to_be_visible()
        fake_api['release'].set()
        expect(page.get_by_text('Cancelled; completed results saved', exact=True)).to_be_visible()
        previous_calls = fake_api['calls'].count('BlockLine')
        page.get_by_role('button', name='Resume / retry failed items', exact=True).click()
        expect(page.get_by_text('Translation completed', exact=True)).to_be_visible()
        assert fake_api['calls'].count('BlockLine') == previous_calls
        assert 'NextLine' in fake_api['calls']
    finally:
        fake_api['release'].set()
        fake_api['block'].clear()
