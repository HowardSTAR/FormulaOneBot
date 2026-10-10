"""A portable profile card rendered from curated server data only."""
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def render(person):
    fonts = Path(__file__).resolve().parents[1] / 'assets' / 'fonts'
    def font(size, bold=False):
        return ImageFont.truetype(str(fonts / ('Jost-Bold.ttf' if bold else 'Jost-Regular.ttf')), size)

    style = person['profile_style']
    palette = {'carbon': ((25, 30, 40), (10, 13, 20)), 'grid': ((30, 44, 64), (12, 18, 28)),
               'scarlet': ((85, 28, 37), (19, 16, 26)), 'aurora': ((24, 91, 83), (22, 28, 56)),
               'champion': ((89, 66, 30), (22, 24, 32))}
    start, end = palette.get(style['background'], palette['carbon'])
    image = Image.new('RGB', (1200, 630))
    draw = ImageDraw.Draw(image)
    for y in range(630):
        t = y / 629
        draw.line((0, y, 1200, y), fill=tuple(round(a*(1-t)+b*t) for a,b in zip(start,end)))
    if style['background'] == 'grid':
        for x in range(0,1200,48): draw.line((x,0,x,630), fill='#304053')
        for y in range(0,630,48): draw.line((0,y,1200,y), fill='#304053')
    # Racing stripes stay behind the content on the right.
    draw.polygon(((970,0),(1030,0),(720,630),(660,630)), fill='#26323b')
    draw.polygon(((1050,0),(1070,0),(760,630),(740,630)), fill='#34434b')
    draw.rounded_rectangle((24,24,1176,606),radius=26,outline='#71818e',width=1)
    draw.text((58,43),'TURBO',font=font(27,True),fill='#ff6259')
    draw.text((150,43),'TEARS',font=font(27,True),fill='#f4f4f5')
    draw.text((1140,51),f"ПРОФИЛЬ УЧАСТНИКА / {person['season']}",anchor='ra',font=font(17),fill='#c0ccd7')

    def text(value, xy, size, color='#f4f4f5', width=500, bold=False):
        value = str(value)
        face = font(size,bold)
        while value and draw.textlength(value,font=face) > width:
            value = value[:-2].rstrip() + '…' if len(value) > 2 else ''
        draw.text(xy,value,font=face,fill=color)

    nick = {'white':'#f4f4f5','red':'#ff8a7d','blue':'#9bc4ff','gold':'#f5ce73','mint':'#8ce5c7'}.get(style['color'],'#f4f4f5')
    frame = {'classic':'#6d7c8d','red':'#ff786e','silver':'#dde5f0','gold':'#f5ce73','neon':'#8ce5c7'}.get(style['frame'],'#6d7c8d')
    draw.ellipse((58,118,172,232),fill='#121923',outline=frame,width=5)
    draw.text((115,175),person['subtitle'][:2].upper(),anchor='mm',font=font(36,True),fill='#f4f4f5')
    text(person['subtitle'],(198,128),42,nick,520,True)
    if person['supporter']:
        draw.polygon(((202,202),(209,195),(216,202),(209,209)),fill='#f5ce73')
    text(person['tier_name'],(228 if person['supporter'] else 200,188),20,'#d1dbe5',462)

    draw.rounded_rectangle((780,112,1140,276),radius=18,fill='#131e29',outline='#53636c')
    text('ЛУЧШИЙ ПРОГНОЗ СЕЗОНА',(804,130),16,'#b5c2ce',310)
    if person['best_points'] is not None:
        text(person['best_points'],(802,153),60,'#ffffff',125,True)
        text('/ ' + str(person['best_max'] if person['best_max'] is not None else '—'),(900,181),26,'#b5c2ce',160)
        text(person['best_event'],(804,236),18,'#d2dce7',310)
    else:
        text('Всё впереди',(804,180),32,'#ffffff',310,True)

    for x, value, label in [(58,person['total_points'],'БАЛЛОВ ЗА СЕЗОН'),(298,person['scored_rounds'],'ПРОГНОЗОВ РАССЧИТАНО'),(538,person['records_count'],'ТРАСС С РЕКОРДАМИ')]:
        draw.rounded_rectangle((x,286,x+218,390),radius=14,fill='#182330',outline='#344352')
        text(value,(x+18,295),38,'#ffffff',182,True)
        text(label,(x+18,353),12,'#becad6',186)
    text('РЕКОРДЫ НА ТРАССАХ',(58,420),15,'#b5c2ce',650)
    if person['records']:
        for index, record in enumerate(person['records']):
            x = 58 + index * 390
            text(record['name'],(x,452),24,'#e8edf2',240,True)
            text(record['time'],(x,489),27,'#8ce5c7',240,True)
    else:
        text('Следующий заезд — начало новой истории',(58,456),23,'#d2dce7',690)
    draw.line((58,550,1140,550),fill='#50606b')
    text('МОЯ СКОРОСТЬ. МОИ ПРОГНОЗЫ.',(58,568),16,'#b5c2ce',620)
    draw.text((1140,564),'ОТКРЫТЬ ПРОФИЛЬ  →',anchor='ra',font=font(21,True),fill='#ff9084')
    output = io.BytesIO()
    image.save(output,format='JPEG',quality=93,optimize=True)
    return output.getvalue()
