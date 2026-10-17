import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_language_switch_and_upload(page, app_url):
    page.goto(app_url)
    page.get_by_role('combobox', name='UI Language').click()
    page.get_by_role('option', name='English', exact=True).click()
    expect(page.get_by_role('heading', name='Subtitle Translator Studio')).to_be_visible()
    page.get_by_test_id('stFileUploader').first.locator('input[type=file]').set_input_files({
        'name': 'sample.srt', 'mimeType': 'text/plain',
        'buffer': b'1\n00:00:01,000 --> 00:00:02,000\nHello\n\n',
    })
    expect(page.get_by_text('Source language', exact=True)).to_be_visible()
    page.get_by_role('combobox', name='UI Language').click()
    page.get_by_role('option', name='日本語', exact=True).click()
    expect(page.get_by_role('heading', name='字幕翻訳スタジオ')).to_be_visible()
