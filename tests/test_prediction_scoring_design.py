"""Independent business oracles: exact, near, distant, unknown and unavailable facts."""
import pytest
from app.services.prediction_service import PREDICTION_FIELDS, calculate_prediction_points, prediction_breakdown

PLACEMENTS = [('winner_driver',1,8),('second_driver',2,5),('third_driver',3,5),
              ('fourth_driver',4,5),('fifth_driver',5,5)]


@pytest.mark.parametrize('field,target,exact',PLACEMENTS,ids=[item[0] for item in PLACEMENTS])
@pytest.mark.parametrize('position',range(1,10),ids=lambda position:f'actual-P{position}')
def test_placement_decision_table(field,target,exact,position):
    prediction = dict.fromkeys(PREDICTION_FIELDS)
    prediction[field] = 'NOR'
    answers = {field:'NOR' if position==target else 'VER','_race_positions':{'NOR':position}}
    expected = {0:exact,1:3,2:2,3:1}.get(abs(position-target),0)
    assert calculate_prediction_points(prediction,answers) == expected
    item = next(row for row in prediction_breakdown(prediction,answers) if row['key']==field)
    assert item['points'] == expected
    assert item['status'] == ('exact' if position==target else 'partial' if expected else 'miss')


@pytest.mark.parametrize('field,exact', [('sprint_pole_driver',3),('sprint_winner_driver',3),
    ('pole_driver',3),('fastest_lap_driver',2),('first_retirement_driver',2)])
@pytest.mark.parametrize('predicted,actual,awarded',[
    pytest.param('NOR','NOR',True,id='exact'),pytest.param('NOR','VER',False,id='wrong'),
    pytest.param(None,'NOR',False,id='not-predicted'),pytest.param('NOR',None,False,id='fact-unavailable'),
])
def test_non_placement_field_partitions(field,exact,predicted,actual,awarded):
    prediction = dict.fromkeys(PREDICTION_FIELDS)
    prediction[field] = predicted
    assert calculate_prediction_points(prediction,{field:actual}) == (exact if awarded else 0)


@pytest.mark.parametrize('predicted,actual,expected',[(0,0,2),(1,1,2),(0,1,0),(1,0,0),(0,None,0),(None,0,0)])
def test_safety_car_false_is_an_answer_not_missing_data(predicted,actual,expected):
    prediction = dict.fromkeys(PREDICTION_FIELDS)
    prediction['safety_car'] = predicted
    assert calculate_prediction_points(prediction,{'safety_car':actual}) == expected


def test_missing_classification_driver_cannot_receive_near_position_points():
    prediction = dict.fromkeys(PREDICTION_FIELDS,'UNKNOWN')
    assert calculate_prediction_points(prediction,{'winner_driver':'VER','_race_positions':{'VER':1}}) == 0
