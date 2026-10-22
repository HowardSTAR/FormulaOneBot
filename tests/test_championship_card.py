"""Poster semantics: title eligibility, refreshed data and truthful arrows."""
from dataclasses import replace
from io import BytesIO

from PIL import Image
import pytest

from app.utils.championship_card import build_card_models, render_championship_card, rival_labels, HEIGHT
from scripts.championship_preview_data import preview_context


@pytest.fixture(scope='module')
def contexts():
    return preview_context(), preview_context(next_round=True)


def test_cards_exist_only_for_available_mathematical_opportunities():
    for context in [{'status':'unavailable'}, {'status':'ok', 'drivers':[], 'constructors':[]}]:
        assert build_card_models(context) == []


def test_both_competitions_use_current_points_and_relevant_opponents(contexts):
    drivers, teams = build_card_models(contexts[0])
    assert drivers.leader.code == 'ANT' and drivers.leader.points == 350
    assert [r.entrant.code for r in drivers.rivals] == ['RUS', 'NOR']
    assert [(r.maximum, r.blocks_from) for r in drivers.rivals] == [(8,10), (10,12)]
    assert teams.leader.code == 'mercedes' and teams.leader.points == 665
    assert teams.gain == 43 and teams.race == (1,2)


def test_next_round_recalculates_limits_and_reorders_opponents(contexts):
    old, new = [build_card_models(c) for c in contexts]
    assert new[0].leader.points == 375 and new[0].round == 23
    assert new[1].leader.points == 708
    assert [r.entrant.code for r in new[0].rivals] == ['NOR', 'RUS']
    assert [r.entrant.code for r in new[1].rivals] == ['ferrari', 'mclaren']
    # Winning the next race is sufficient regardless of rival points.
    assert all(r.maximum is None and r.blocks_from is None for r in new[0].rivals)
    assert old[0].rivals[0].maximum == 8  # Previous model was not mutated.


def test_equal_point_exception_is_not_marked_as_a_red_failure(contexts):
    import copy
    context = copy.deepcopy(contexts[0])
    context['drivers'][0]['scenarios'][0]['rivals'][0]['tie_points'] = 10
    rival = build_card_models(context)[0].rivals[0]
    assert rival.maximum == 8 and rival.tie_points == 10
    assert rival.blocks_from == 12


@pytest.mark.parametrize('style', ['aura', 'podium'])
def test_local_renderer_works_without_art_and_does_not_mutate_input(contexts, style):
    model = build_card_models(contexts[0])[0]
    png = render_championship_card(model, style=style, artwork_loader=lambda *args: None)
    with Image.open(BytesIO(png)) as image:
        assert image.size == (1080,HEIGHT) and image.format == 'PNG'
    assert model.leader.points == 350
    changed = render_championship_card(replace(model, leader=replace(model.leader, points=375)),
                                       style=style, artwork_loader=lambda *args: None)
    assert png != changed


@pytest.fixture(scope='module', params=[4, 5, 8])
def crowded_models(request):
    return request.param, build_card_models(preview_context(participants=request.param))


@pytest.mark.parametrize('kind', ['drivers', 'constructors'])
def test_crowded_cards_keep_every_identity_artwork_and_condition(crowded_models, kind, monkeypatch):
    import app.utils.championship_card as renderer
    count, models = crowded_models
    model = next(m for m in models if m.kind == kind)
    assert len(model.rivals)+1 == count
    text_seen, artwork_seen = [], []
    original = renderer._text

    def record_text(*args, **kwargs):
        text_seen.append(str(args[2]))
        return original(*args, **kwargs)

    def record_artwork(card, entrant, category):
        artwork_seen.append((entrant.code, category))
        return None

    monkeypatch.setattr(renderer, '_text', record_text)
    png = renderer.render_championship_card(model, artwork_loader=record_artwork)
    with Image.open(BytesIO(png)) as image:
        assert image.size == (1080, 2316 if count == 8 else 1660)
    # Each rival is retained exactly once, with a photograph/logo and both
    # mathematical bounds. This catches truncation to the original top three.
    for rival in model.rivals:
        assert text_seen.count(rival.entrant.name.upper()) == 1
        assert (rival.entrant.code, 'pilots' if kind == 'drivers' else 'teams') in artwork_seen
        green, red = rival_labels(model, rival)
        assert green[0] in text_seen and red[0] in text_seen
    assert text_seen.count('ДЛЯ ТИТУЛА') == count-1
    assert text_seen.count('ОТЛОЖИТ ТИТУЛ') == count-1


def test_finish_labels_match_the_actual_points_boundary(contexts):
    from app.services.championship import RACE
    model = build_card_models(contexts[0])[0]
    for cap in range(25):
        rival = replace(model.rivals[0], maximum=cap, blocks_from=next(p for p in sorted(RACE) if p > cap))
        green, red = rival_labels(model, rival)
        safe_place = int(green[0].split('-')[0])
        blocking_place = int(red[0].split('-')[0])
        # Every labelled finish obeys the corresponding point bound, including
        # the first non-scoring place, rather than rounding a bound upward.
        for place in range(1, 23):
            score = RACE[place-1] if place <= len(RACE) else 0
            assert (place >= safe_place) == (score <= cap)
            assert (place <= blocking_place) == (score >= rival.blocks_from)


def test_team_and_sprint_totals_are_not_presented_as_race_positions(contexts):
    driver, team = build_card_models(contexts[0])
    for model in [team, replace(driver, sprint=(1,))]:
        green, red = rival_labels(model, model.rivals[0])
        assert green[0] == 'НЕ БОЛЬШЕ'
        assert 'ОЧКОВ' in red[0]
        assert 'ВЫШЕ' not in red[0] and 'НИЖЕ' not in green[0]


def test_unrestricted_rival_has_no_fabricated_red_condition(contexts):
    model = build_card_models(contexts[1])[0]
    assert rival_labels(model, model.rivals[0]) == (('ЛЮБОЙ РЕЗУЛЬТАТ',''), ('НЕ ПОМЕШАЕТ',''))
