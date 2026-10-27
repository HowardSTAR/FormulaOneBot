from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import f1_data


def test_long_biography_keeps_paragraphs_and_more_than_the_summary():
    first = 'Первый этап карьеры. ' * 35
    second = 'Следующий этап карьеры. ' * 35
    result = f1_data._format_wiki_biography(first + '\n\n' + second)
    assert len(result) > 900
    assert '\n\n' in result
    assert result.endswith('Следующий этап карьеры.')


def test_long_biography_removes_notices_and_bounds_the_extract():
    result = f1_data._format_wiki_biography('Эта статья о пилоте. История карьеры.\n\n' + 'Подробности выступлений. ' * 80, max_chars=240)
    assert 'Эта статья' not in result
    assert result.startswith('История карьеры.')
    assert len(result) <= 240
    assert result.endswith(('.', '…'))
    assert f1_data._format_wiki_biography('') == ''


def image_info(license_name='CC BY-SA 4.0'):
    return {'thumburl': 'https://upload.wikimedia.org/photo.jpg',
            'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Photo.jpg',
            'thumbwidth': 1200, 'thumbheight': 800,
            'extmetadata': {'Artist': {'value': '<a href="/user">Photographer</a>'},
                            'LicenseShortName': {'value': license_name},
                            'LicenseUrl': {'value': '//creativecommons.org/licenses/by-sa/4.0/'},
                            'ImageDescription': {'value': '<p>Car on track.</p>'}}}


def test_image_credit_is_plain_text_with_the_real_license_and_source():
    image = f1_data._wiki_image_info(image_info())
    assert image['author'] == 'Photographer'
    assert image['caption'] == 'Car on track.'
    assert image['license_url'].startswith('https://')
    assert image['width'] == 1200


@pytest.mark.parametrize('license_name', ['Fair use', '', 'All rights reserved'])
def test_image_without_a_reusable_license_is_optional(license_name):
    assert f1_data._wiki_image_info(image_info(license_name)) is None


@pytest.mark.asyncio
async def test_batch_images_skips_missing_and_non_reusable_candidates():
    response = MagicMock(status=200)
    response.json = AsyncMock(return_value={'query': {'pages': [
        {'title': 'File:First.jpg', 'imageinfo': [image_info('Fair use')]},
        {'title': 'File:Second.jpg', 'imageinfo': [image_info()]},
    ]}})
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    session = MagicMock()
    session.get.return_value = context
    image = await f1_data._fetch_biography_image(session, ['Logo.svg', 'First.jpg', 'Файл:Second.jpg'])
    assert image['author'] == 'Photographer'
    assert session.get.call_count == 1
    assert 'Logo.svg' not in session.get.call_args.kwargs['params']['titles']
    assert 'File:Second.jpg' in session.get.call_args.kwargs['params']['titles']


@pytest.mark.asyncio
async def test_missing_photo_does_not_remove_biography():
    with patch.object(f1_data, '_fetch_wiki_profile', AsyncMock(return_value={
        'bio': 'Summary', 'biography': 'First paragraph.\n\nSecond paragraph.',
        'source_url': 'https://ru.wikipedia.org/wiki/Пилот', 'image_titles': [],
    })):
        result = await f1_data._fetch_entrant_biography(MagicMock(), 'https://en.wikipedia.org/wiki/Driver')
    assert result['text'] == 'First paragraph.\n\nSecond paragraph.'
    assert result['image'] is None
    assert 'ru.wikipedia.org' in result['source_url']


@pytest.mark.asyncio
async def test_failed_translation_keeps_english_text_and_its_source():
    english = {'extract': 'English biography.', 'langlinks': [{'lang': 'ru', 'title': 'Пилот'}]}
    with patch.object(f1_data, '_fetch_wiki_page_profile', AsyncMock(side_effect=[english, {}])):
        profile = await f1_data._fetch_wiki_profile(MagicMock(), 'https://en.wikipedia.org/wiki/Driver')
    assert profile['biography'] == 'English biography.'
    assert profile['source_url'] == 'https://en.wikipedia.org/wiki/Driver'
