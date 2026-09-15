"""Aggregate decision metrics; never return identities or prediction choices."""
import json
import math


def forecast_quality(rows):
    groups, seen = {}, set()
    for row in rows:  # newest first, one forecast per session/version/event
        try:
            payload = json.loads(row['payload'])
            version = payload['model']['version']
            key = (row['season'], row['round'], row['session'], version)
            if key in seen or not 0 < payload['cutoff'] < row['start_at']:
                continue
            seen.add(key)
            group = groups.setdefault((version,row['session']), {'version':version,'session':row['session'],'sessions':0,'pending':0,'excluded':0,'mae':[],'winner_brier':[]})
            if not row['actual']:
                group['pending'] += 1
                continue
            metrics = json.loads(row['actual'])['metrics']
            if not metrics['total'] or metrics['matched'] != metrics['total'] or any(not isinstance(metrics.get(k),(float,int)) or not math.isfinite(metrics[k]) for k in ('mae','winner_brier')):
                group['excluded'] += 1
                continue
            group['sessions'] += 1
            for metric in ('mae','winner_brier'):
                group[metric].append(metrics[metric])
        except (ValueError,KeyError,TypeError):
            continue
    return [{**g, **{k:sum(g[k])/len(g[k]) if g[k] else None for k in ('mae','winner_brier')}} for g in groups.values()]


async def report(conn, since):
    async def rows(sql, params=()):
        return [dict(r) for r in await (await conn.execute(sql,params)).fetchall()]
    visits = await rows('''SELECT platform,path,COUNT(*) visits,COUNT(DISTINCT visitor_id) browsers,
        COUNT(DISTINCT CASE WHEN user_id IS NULL THEN visitor_id END) anonymous_browsers
        FROM site_visits WHERE bucket>=? GROUP BY platform,path ORDER BY visits DESC LIMIT 60''',(int(since)//300,))
    audience = (await rows('''SELECT COUNT(DISTINCT CASE WHEN user_id IS NULL THEN visitor_id END) anonymous_browsers,
        COUNT(DISTINCT user_id) accounts FROM site_visits WHERE bucket>=?''',(int(since)//300,)))[0]
    funnel = (await rows('''WITH stages AS (
        SELECT user_id,season,round,MIN(CASE WHEN event='prediction_view' THEN created END) opened,
          MIN(CASE WHEN event='prediction_start' THEN created END) started
        FROM product_events WHERE created>=? AND user_id IS NOT NULL
          AND event IN ('prediction_view','prediction_start') GROUP BY user_id,season,round)
        SELECT COUNT(*) opened,COALESCE(SUM(s.started>=s.opened),0) started,
          COALESCE(SUM(s.started>=s.opened AND CAST(strftime('%s',p.updated_at) AS INTEGER)+1>=s.started),0) saved
        FROM stages s LEFT JOIN race_predictions p USING(user_id,season,round) WHERE s.opened IS NOT NULL''',(since,)))[0]
    retention = await rows('''WITH rounds AS (
        SELECT season,round,LEAD(round) OVER(PARTITION BY season ORDER BY round) next_round FROM prediction_round_results)
        SELECT r.season,r.round,r.next_round,COUNT(*) participants,SUM(n.user_id IS NOT NULL) returned
        FROM rounds r JOIN race_predictions p ON p.season=r.season AND p.round=r.round
        LEFT JOIN race_predictions n ON n.user_id=p.user_id AND n.season=r.season AND n.round=r.next_round
        WHERE r.next_round IS NOT NULL AND CAST(strftime('%s',p.updated_at) AS INTEGER)>=?
        GROUP BY r.season,r.round,r.next_round ORDER BY r.season DESC,r.round DESC LIMIT 30''',(since,))
    errors = await rows("SELECT path,platform,error_code,COUNT(*) occurrences FROM product_events WHERE event='error' AND created>=? GROUP BY path,platform,error_code ORDER BY occurrences DESC LIMIT 30",(since,))
    delivery = await rows("SELECT COALESCE(p.channel,'telegram') channel,d.status,COUNT(*) recipients FROM telegram_deliveries d LEFT JOIN delivery_payloads p USING(event_key) WHERE d.updated>=? GROUP BY channel,d.status",(since,))
    source = await rows("SELECT season,round,session,created_at,start_at,payload,actual FROM prediction_analytics WHERE status='ready' AND created_at>=? ORDER BY created_at DESC,id DESC",(since,))
    first = (await rows('SELECT MIN(created) first_event FROM product_events'))[0]['first_event']
    reach = (await rows('''SELECT
        COALESCE(SUM(telegram_id IS NOT NULL AND (COALESCE(reminder_sessions,31)&31)>0),0) telegram_reminders,
        COALESCE(SUM(EXISTS(SELECT 1 FROM web_notification_members m WHERE m.user_id=u.id)
          AND EXISTS(SELECT 1 FROM web_push_subscriptions s WHERE s.user_id=u.id)
          AND (COALESCE(reminder_sessions,31)&31)>0),0) push_reminders,
        COALESCE(SUM(telegram_id IS NOT NULL AND notifications_enabled=0),0) silent_telegram
        FROM users u WHERE archived_at IS NULL'''))[0]
    return {'audience':audience,'visits':visits,'funnel':funnel,'retention':retention,'errors':errors,'delivery':delivery,'quality':forecast_quality(source),'first_event':first,'reach':reach}
