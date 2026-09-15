import json
from app.services.product_analytics import forecast_quality


def test_quality_uses_latest_snapshot_per_version_and_complete_matches():
    def row(version='v1',value=2,actual=True):
        return {'season':2026,'round':1,'session':'race','start_at':200,
                'payload':json.dumps({'cutoff':100,'model':{'version':version}}),
                'actual':json.dumps({'metrics':{'matched':20,'total':20,'mae':value,'winner_brier':0.1}}) if actual else None}
    result=forecast_quality([row(),row(value=0),row('v2',actual=False)])
    assert result[0]['sessions']==1 and result[0]['mae']==2
    assert result[1]['sessions']==0 and result[1]['pending']==1 and result[1]['mae'] is None
    incomplete=row()
    incomplete['actual']=json.dumps({'metrics':{'matched':19,'total':20,'mae':0,'winner_brier':0}})
    assert forecast_quality([incomplete])[0]['excluded']==1
    late=row();late['start_at']=90
    assert forecast_quality([late])==[]
