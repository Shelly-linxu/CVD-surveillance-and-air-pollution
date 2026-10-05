"""Public ERA5 regional lattice; no case coordinates or clinical data transmitted."""
from pathlib import Path
import csv,json,hashlib,subprocess,time,gzip
from datetime import date,timedelta
from urllib.parse import urlencode
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/air_pollution_cc'
DEST=ROOT/'work/air_pollution_cc/weather_era5'
START='2022-12-04';END='2025-12-31'
DOC='https://open-meteo.com/en/docs/historical-weather-api'

def main():
    DEST.mkdir(parents=True,exist_ok=True)
    points=[(22.25+i*.25,112.5+j*.25) for i in range(10) for j in range(10)]
    dates=[];d=date.fromisoformat(START)
    while d<=date.fromisoformat(END):dates.append(d.isoformat());d+=timedelta(days=1)
    datasets=[]; provenance=[]
    for first in range(0,len(points),10):
        group=points[first:first+10]; target=DEST/f'era5_batch_{first//10:02d}.json'
        query=urlencode(dict(latitude=','.join(str(x[0]) for x in group),longitude=','.join(str(x[1]) for x in group),start_date=START,end_date=END,daily='temperature_2m_mean,relative_humidity_2m_mean',models='era5',timezone='Asia/Shanghai',elevation=','.join(['nan']*len(group)),cell_selection='nearest'))
        url='https://archive-api.open-meteo.com/v1/archive?'+query
        downloaded_now=not target.exists()
        if downloaded_now:
            partial=target.with_suffix('.partial.json')
            subprocess.run(['curl','-fsSL','--connect-timeout','30','--max-time','120','--retry','2','--retry-delay','30',url,'-o',str(partial)],check=True)
            data=json.loads(partial.read_text())
            if not isinstance(data,list) or len(data)!=len(group): raise ValueError('Unexpected weather batch schema')
            partial.replace(target)
        data=json.loads(target.read_text())
        for requested,obj in zip(group,data):
            assert obj['utc_offset_seconds']==28800 and obj['timezone']=='Asia/Shanghai'
            assert obj['daily_units']['temperature_2m_mean']=='°C' and obj['daily_units']['relative_humidity_2m_mean']=='%'
            assert obj['daily']['time']==dates
            ts=obj['daily']['temperature_2m_mean']; rs=obj['daily']['relative_humidity_2m_mean']
            assert len(ts)==len(rs)==len(dates)
            for t,r in zip(ts,rs):
                if t is not None: assert -90<t<60
                if r is not None: assert 0<=r<=100
            datasets.append((requested,obj))
        provenance.append(dict(batch_file=str(target),url=url,sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
        (OUT/'weather_download_status.json').write_text(json.dumps(dict(requested_points_processed=len(datasets),total_requested_points=len(points),dates_per_point=len(dates),model='ERA5',timezone='Asia/Shanghai'),indent=2))
        print('Weather points processed:',len(datasets),flush=True)
        if downloaded_now: time.sleep(30)
    grids={}
    for requested,obj in datasets:
        key=(obj['latitude'],obj['longitude'])
        if key in grids:
            assert grids[key]['daily']==obj['daily']
        grids[key]=obj
    with gzip.open(DEST/'weather_grid_daily.csv.gz','wt',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['weather_grid_id','latitude','longitude','date','temp','rh']);w.writeheader()
        for (lat,lon),obj in sorted(grids.items()):
            for d,t,r in zip(dates,obj['daily']['temperature_2m_mean'],obj['daily']['relative_humidity_2m_mean']):w.writerow(dict(weather_grid_id=f'ERA5_{lat:.2f}_{lon:.2f}',latitude=lat,longitude=lon,date=d,temp='' if t is None else t,rh='' if r is None else r))
    meta=dict(model='ERA5',source_provider='Open-Meteo',source_documentation=DOC,spatial_resolution_degrees=.25,timezone='Asia/Shanghai',utc_offset_seconds=28800,start=START,end=END,dates_per_grid=len(dates),requested_points=len(points),unique_returned_grids=len(grids),elevation_adjustment='disabled: elevation=nan',cell_selection='nearest',scope='regional lattice, not yet matched to case residences',null_temperature_values=sum(t is None for o in grids.values() for t in o['daily']['temperature_2m_mean']),null_humidity_values=sum(t is None for o in grids.values() for t in o['daily']['relative_humidity_2m_mean']),provenance=provenance)
    (OUT/'weather_era5_metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in meta.items() if k!='provenance'},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
