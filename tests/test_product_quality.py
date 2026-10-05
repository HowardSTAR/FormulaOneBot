"""Quality decisions: completeness, finite metrics, cutoff and deduplication."""
import json
import pytest
from app.services.product_analytics import forecast_quality


def row(*,version='v1',round_number=1,cutoff=100,metrics=None,pending=False):
    return {'season':2026,'round':round_number,'session':'race','start_at':200,
            'payload':json.dumps({'cutoff':cutoff,'model':{'version':version}}),
            'actual':None if pending else json.dumps({'metrics':metrics or {'matched':20,'total':20,'mae':2,'winner_brier':0.1}})}


def test_latest_snapshot_wins_and_model_versions_are_separate():
    result = forecast_quality([row(),row(metrics={'matched':20,'total':20,'mae':0,'winner_brier':0}),row(version='v2',pending=True)])
    assert result == [
        {'version':'v1','session':'race','sessions':1,'pending':0,'excluded':0,'mae':2,'winner_brier':0.1},
        {'version':'v2','session':'race','sessions':0,'pending':1,'excluded':0,'mae':None,'winner_brier':None},
    ]


@pytest.mark.parametrize('metrics',[
    pytest.param({'matched':19,'total':20,'mae':0,'winner_brier':0},id='incomplete'),
    pytest.param({'matched':0,'total':0,'mae':0,'winner_brier':0},id='empty'),
    pytest.param({'matched':20,'total':20,'mae':float('nan'),'winner_brier':0},id='nan'),
    pytest.param({'matched':20,'total':20,'mae':0,'winner_brier':float('inf')},id='infinite'),
    pytest.param({'matched':20,'total':20,'mae':None,'winner_brier':0},id='missing-metric'),
])
def test_invalid_quality_is_excluded_and_never_becomes_perfect_zero(metrics):
    result = forecast_quality([row(metrics=metrics)])[0]
    assert (result['sessions'],result['excluded'],result['pending']) == (0,1,0)
    assert result['mae'] is None and result['winner_brier'] is None


@pytest.mark.parametrize('cutoff,eligible',[
    pytest.param(-1,False,id='negative'),pytest.param(0,False,id='zero'),
    pytest.param(1,True,id='first-positive'),pytest.param(199.999,True,id='before-start'),
    pytest.param(200,False,id='at-start'),pytest.param(200.001,False,id='after-start'),
])
def test_forecast_cutoff_boundary(cutoff,eligible):
    result = forecast_quality([row(cutoff=cutoff)])
    assert len(result) == int(eligible)
    if eligible:
        assert result[0]['sessions'] == 1


def test_quality_averages_distinct_rounds_and_keeps_real_zero():
    result = forecast_quality([row(),row(round_number=2,metrics={'matched':20,'total':20,'mae':0,'winner_brier':0})])[0]
    assert result['sessions'] == 2
    assert result['mae'] == 1 and result['winner_brier'] == pytest.approx(0.05)
