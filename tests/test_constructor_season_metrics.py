from app.f1_data import _constructor_season_metrics


def test_team_metrics_count_car_results_instead_of_assuming_two_cars_per_event():
    result = _constructor_season_metrics([
        {'position': '1', 'positionText': '1', 'points': 25, 'grid': '2'},
        {'position': '20', 'positionText': 'R', 'points': 0, 'grid': '0'},
        {'position': '2', 'positionText': '2', 'points': 18, 'grid': '1'},
    ])
    assert result['grand_prix_entries'] == 3
    assert result['grand_prix_points_finishes'] == 2
    assert result['grand_prix_unclassified'] == 1
    assert result['highest_race_finish'] == {'position': 1, 'count': 1}
    assert result['highest_grid'] == {'position': 1, 'count': 1}


def test_unknown_classification_is_not_reported_as_zero_retirements():
    result = _constructor_season_metrics([{'position': '5', 'points': 0, 'grid': '0'}])
    assert result['grand_prix_unclassified'] is None
    assert result['grand_prix_points_finishes'] == 0
    assert result['highest_grid'] == {'position': '-', 'count': 0}


def test_empty_season_has_no_invented_records():
    result = _constructor_season_metrics([])
    assert result['grand_prix_entries'] == 0
    assert result['grand_prix_points_finishes'] == 0
    assert result['highest_race_finish'] == {'position': '-', 'count': 0}


def test_record_occurrences_and_disqualifications_keep_the_source_meaning():
    result = _constructor_season_metrics([
        {'position': '2', 'positionText': '2', 'points': 18, 'grid': '6'},
        {'position': '2', 'positionText': '2', 'points': 18, 'grid': '6'},
        {'position': '20', 'positionText': 'D', 'points': 0, 'grid': '7'},
    ])
    assert result['highest_race_finish']['count'] == 2
    assert result['highest_grid']['count'] == 2
    assert result['grand_prix_unclassified'] == 1


def test_unclassified_positions_are_not_presented_as_finish_records():
    result = _constructor_season_metrics([{'position': '1', 'positionText': 'D', 'points': 0, 'grid': '1'}])
    assert result['highest_race_finish'] == {'position': '-', 'count': 0}
