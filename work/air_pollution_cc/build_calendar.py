"""Pre-specified Chinese holiday calendar; no outcome/exposure results consulted."""
from datetime import date, timedelta
from pathlib import Path
import csv, json

ROOT=Path(__file__).resolve().parents[2]
PRIVATE=ROOT/'work/air_pollution_cc/private'
OUT=ROOT/'outputs/air_pollution_cc'
breaks={
2023:[('01-01','01-02'),('01-21','01-27'),('04-05','04-05'),('04-29','05-03'),('06-22','06-24'),('09-29','10-06'),('12-30','12-31')],
2024:[('01-01','01-01'),('02-10','02-17'),('04-04','04-06'),('05-01','05-05'),('06-08','06-10'),('09-15','09-17'),('10-01','10-07')],
2025:[('01-01','01-01'),('01-28','02-04'),('04-04','04-06'),('05-01','05-05'),('05-31','06-02'),('10-01','10-08')]}
workdays={2023:'01-28 01-29 04-23 05-06 06-25 10-07 10-08',2024:'02-04 02-18 04-07 04-28 05-11 09-14 09-29 10-12',2025:'01-26 02-08 04-27 09-28 10-11'}
statutory={2023:'01-01 01-22 01-23 01-24 04-05 05-01 06-22 09-29 10-01 10-02 10-03',2024:'01-01 02-10 02-11 02-12 04-04 05-01 06-10 09-17 10-01 10-02 10-03',2025:'01-01 01-28 01-29 01-30 01-31 04-04 05-01 05-02 05-31 10-06 10-01 10-02 10-03'}
sources={2023:'https://www.beijing.gov.cn/zhengce/gwywj/202212/t20221209_2873949.html',2024:'https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202310/t20231025_3286455.html',2025:'https://www.forestry.gov.cn/c/www/szxx/594663.jhtml'}
rows=[]
d=date(2023,1,1)
while d<=date(2025,12,31):
    y=d.year; md=d.strftime('%m-%d')
    vacation=int(any(a<=md<=b for a,b in breaks[y]))
    holiday=int(md in statutory[y].split())
    adjusted=int(md in workdays[y].split())
    assert not(vacation and adjusted)
    assert not holiday or vacation
    rows.append(dict(date=d.isoformat(),holiday=holiday,statutory_holiday=holiday,official_break=vacation,adjusted_workday=adjusted,weekday=d.isoweekday(),calendar_source=sources[y]))
    d+=timedelta(days=1)
assert len(rows)==1096
for target in (PRIVATE/'calendar.csv',OUT/'calendar.csv'):
    with target.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
summary={str(y):{'statutory_days':sum(r['holiday'] for r in rows if r['date'].startswith(str(y))),'official_break_days':sum(r['official_break'] for r in rows if r['date'].startswith(str(y))),'adjusted_workdays':sum(r['adjusted_workday'] for r in rows if r['date'].startswith(str(y)))} for y in breaks}
assert [summary[str(y)]['statutory_days'] for y in breaks]==[11,11,13]
assert [summary[str(y)]['adjusted_workdays'] for y in breaks]==[7,8,5]
(OUT/'calendar_metadata.json').write_text(json.dumps({'definition':'holiday=全体公民法定节日当日；official_break=国务院安排的放假调休和连休期间；不将整个放假期间误标为法定节日当日','sources':sources,'law_2025':'https://www.cztn.gov.cn/html/cztn/2024/CNPFLQPA_1221/31874.html','summary':summary},ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False))
