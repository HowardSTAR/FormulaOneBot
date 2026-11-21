"""Aggregate decision metrics; never return identities or prediction choices."""
import json
import math
import time


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


async def report(conn, since, until=None):
    until = time.time() if until is None else until
    async def rows(sql, params=()):
        return [dict(r) for r in await (await conn.execute(sql,params)).fetchall()]
    # Visits have five-minute resolution. Compare disjoint windows of the same length.
    start_bucket, end_bucket = int(since) // 300, int(until) // 300
    previous_bucket = 2 * start_bucket - end_bucket
    traffic = await rows('''WITH browser_periods AS (
        SELECT bucket>=? AS current, visitor_id, COUNT(DISTINCT bucket/288) AS days
        FROM site_visits WHERE bucket>=? AND bucket<? GROUP BY current, visitor_id)
        SELECT current, COUNT(*) AS browsers, SUM(days>1) AS returning_browsers
        FROM browser_periods GROUP BY current''', (start_bucket, previous_bucket, end_bucket))
    periods = {row['current']: {'browsers': row['browsers'], 'returning': row['returning_browsers']} for row in traffic}
    first_visit = (await rows('SELECT MIN(bucket) AS first FROM site_visits'))[0]['first']
    comparison = {
        'start': start_bucket * 300,
        'end': end_bucket * 300,
        'previous_start': previous_bucket * 300,
        'first_visit': first_visit * 300 if first_visit is not None else None,
        'current': periods.get(1, {'browsers': 0, 'returning': 0}),
        'previous': periods.get(0, {'browsers': 0, 'returning': 0})
            if first_visit is not None and first_visit <= previous_bucket else None,
    }
    visits = await rows('''SELECT platform,path,COUNT(*) visits,COUNT(DISTINCT visitor_id) browsers,
        COUNT(DISTINCT CASE WHEN user_id IS NULL THEN visitor_id END) anonymous_browsers
        FROM site_visits WHERE bucket>=? GROUP BY platform,path ORDER BY visits DESC LIMIT 60''',(int(since)//300,))
    audience = (await rows('''SELECT COUNT(DISTINCT CASE WHEN user_id IS NULL THEN visitor_id END) anonymous_browsers,
        COUNT(DISTINCT user_id) accounts FROM site_visits WHERE bucket>=?''',(int(since)//300,)))[0]
    # The row's creation time is the first confirmed save. Updates can also come
    # from an edit or recalculation. The database stores saves in whole seconds.
    funnel = (await rows('''WITH opens AS (
        SELECT user_id,season,round,MIN(created) AS opened
        FROM product_events WHERE created>=? AND created<? AND user_id IS NOT NULL
          AND event='prediction_view' GROUP BY user_id,season,round
    ), stages AS (
        SELECT o.user_id,o.season,o.round,MIN(e.created) AS started
        FROM opens o LEFT JOIN product_events e ON e.user_id=o.user_id AND e.season=o.season
          AND e.round=o.round AND e.event='prediction_start' AND e.created>=? AND e.created>=o.opened AND e.created<?
        GROUP BY o.user_id,o.season,o.round
    )
        SELECT COUNT(*) opened, COUNT(s.started) started,
          COUNT(CASE WHEN unixepoch(p.created_at)>=CAST(s.started AS INTEGER)
            AND unixepoch(p.created_at)<? THEN 1 END) saved
        FROM stages s LEFT JOIN race_predictions p USING(user_id,season,round)''',
        (since, until, since, until, until)))[0]
    prediction_first = (await rows("""SELECT MIN(created) AS first FROM product_events
        WHERE event='prediction_view'"""))[0]['first']
    first_saves = (await rows('''SELECT COUNT(*) AS count FROM race_predictions
        WHERE unixepoch(created_at)>=? AND unixepoch(created_at)<?''', (int(since), until)))[0]['count']
    retention = await rows('''WITH rounds AS (
        SELECT season,round,LEAD(round) OVER(PARTITION BY season ORDER BY round) next_round FROM prediction_round_results)
        SELECT r.season,r.round,r.next_round,COUNT(*) participants,SUM(n.user_id IS NOT NULL) returned
        FROM rounds r JOIN race_predictions p ON p.season=r.season AND p.round=r.round
        LEFT JOIN race_predictions n ON n.user_id=p.user_id AND n.season=r.season AND n.round=r.next_round
        WHERE r.next_round IS NOT NULL
        GROUP BY r.season,r.round,r.next_round ORDER BY r.season DESC,r.round DESC LIMIT 30''')
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
    sharing = await rows('''SELECT s.kind,e.event,COUNT(*) events,COUNT(DISTINCT e.visitor) browsers
        FROM engagement_events e JOIN engagement_shares s ON s.token=e.token
        WHERE e.created>=? GROUP BY s.kind,e.event''', (since,))
    referrals = (await rows('''SELECT COUNT(*) arrived,COUNT(activated) activated,COALESCE(SUM(returned),0) returned
        FROM engagement_referrals WHERE created>=?''', (since,)))[0]
    screens = await rows('''SELECT path,COUNT(*) views,COUNT(DISTINCT visitor_id) browsers FROM ui_events
        WHERE created>=? AND event='screen_view' GROUP BY path ORDER BY views DESC,path''', (since,))
    actions = await rows('''SELECT path,action,destination,COUNT(*) clicks,COUNT(DISTINCT visitor_id) browsers FROM ui_events
        WHERE created>=? AND event='click' GROUP BY path,action,destination ORDER BY clicks DESC LIMIT 30''', (since,))
    interaction_first = (await rows('SELECT MIN(created) first_event FROM ui_events'))[0]['first_event']
    from app.services.posthog_bridge import status
    posthog = await status(conn)
    from app.services.notification_clicks import report as notification_report
    notification_buttons = await notification_report(conn, since)
    return {'audience':audience,'visits':visits,'funnel':funnel,'retention':retention,'errors':errors,'delivery':delivery,'quality':forecast_quality(source),'first_event':first,'reach':reach,'sharing':sharing,'referrals':referrals,
        'period': {'start': since, 'end': until}, 'traffic': comparison, 'prediction_first': prediction_first, 'first_saves': first_saves,
        'screens':screens,'actions':actions,'interaction_first':interaction_first,'posthog':posthog,
        'notification_buttons':notification_buttons}
