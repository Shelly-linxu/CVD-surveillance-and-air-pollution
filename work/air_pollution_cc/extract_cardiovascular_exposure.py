"""Extract actual CHAP lag histories, preserve pending eligibility and address tiers."""
import csv,gzip,json,os,math
from pathlib import Path
from datetime import date,timedelta
from collections import Counter
import numpy as np
import netCDF4
import argparse
ROOT=Path(__file__).resolve().parents[2];P=ROOT/'work/air_pollution_cc/private';Q=P/'cardiovascular';O=ROOT/'outputs/air_pollution_cc/cardiovascular';W=ROOT/'work/air_pollution_cc'
def read(p):
    op=gzip.open if p.suffix=='.gz' else open
    with op(p,'rt',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def distance(x,y,x2,y2):
    dx=np.radians(x2-x);dy=np.radians(y2-y);a=np.sin(dy/2)**2+np.cos(np.radians(y))*np.cos(np.radians(y2))*np.sin(dx/2)**2
    return 6371*2*np.arcsin(np.sqrt(np.clip(a,0,1)))
def main():
    global Q,O
    parser=argparse.ArgumentParser();parser.add_argument('--all-events',action='store_true');args=parser.parse_args()
    if args.all_events:
        Q=P/'two_group';O=ROOT/'outputs/air_pollution_cc/two_group'
    dest=Q/'matched_exposure_rows.csv.gz'
    if dest.exists():raise RuntimeError('Existing extraction preserved')
    ad=read(Q/'event_adjudication.csv');eids={r['event_id'] for r in ad};lids=sorted({r['location_id'] for r in ad})
    wanted_locations=set(lids)
    loc={r['location_id']:r for r in read(P/'location_quality.csv') if r['location_id'] in wanted_locations}
    inventory=[json.loads(s) for s in (ROOT/'outputs/air_pollution_cc/chap_crop_inventory.jsonl').read_text().splitlines()];sources={(r['pollutant'],r['date']):r for r in inventory}
    polys=['PM25','PM10','O3'];points={};cells={};axes={}
    for poll in polys:
        src=sources[poll,'2023-01-01']
        with netCDF4.Dataset(src['path']) as ds:
            lat=np.asarray(ds['lat'][:]);lon=np.asarray(ds['lon'][:]);axes[poll]=(lat,lon)
        pairs=[]
        for lid in lids:
            r=loc[lid];x,y=float(r['longitude']),float(r['latitude'])
            ok=lon.min()<=x<=lon.max() and lat.min()<=y<=lat.max()
            pair=(int(np.argmin(abs(lat-y))),int(np.argmin(abs(lon-x)))) if ok else None
            pairs.append(pair)
        unique=sorted({p for p in pairs if p is not None});index={p:i for i,p in enumerate(unique)}
        points[poll]={lid:index[p] if p is not None else -1 for lid,p in zip(lids,pairs)};cells[poll]=unique
    # Nearest ERA5 grid assignment uses fixed grid coordinates and spherical distance.
    weather=read(W/'weather_era5/weather_grid_daily.csv.gz');wg={r['weather_grid_id']:(float(r['longitude']),float(r['latitude'])) for r in weather};gids=sorted(wg);wx=np.array([wg[g][0] for g in gids]);wy=np.array([wg[g][1] for g in gids]);weather_loc={}
    for lid in lids:
        r=loc[lid];dist=distance(float(r['longitude']),float(r['latitude']),wx,wy);i=int(np.argmin(dist));weather_loc[lid]=(gids[i],float(dist[i]))
    dates=[(date(2022,12,4)+timedelta(days=i)).isoformat() for i in range(1124)];di={d:i for i,d in enumerate(dates)};values={}
    for poll in polys:
        xy=cells[poll];ys=np.array([p[0] for p in xy]);xs=np.array([p[1] for p in xy]);v=np.full((len(dates),len(xy)),np.nan,dtype=np.float32)
        for i,d in enumerate(dates):
            src=sources[poll,d]
            with netCDF4.Dataset(src['path']) as ds:
                lat,lon=axes[poll]
                if not np.allclose(ds['lat'][:],lat,atol=1e-6,rtol=0) or not np.allclose(ds['lon'][:],lon,atol=1e-6,rtol=0):raise ValueError('Daily grid changed')
                arr=np.ma.asarray(ds[src['variable']][:]).filled(np.nan);v[i,:]=arr[ys,xs]
            if i%300==0:print(poll,'daily files',i+1,'/',len(dates),flush=True)
        values[poll]=v
    locfields=['location_id','longitude','latitude','crs','analysis_tier','weather_grid_id','weather_distance_km']+[p+'_in_crop' for p in polys]
    with (Q/'exposure_location_assignments.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=locfields);w.writeheader()
        for lid in lids:w.writerow({**{k:loc[lid][k] for k in ['location_id','longitude','latitude','crs','analysis_tier']},'weather_grid_id':weather_loc[lid][0],'weather_distance_km':weather_loc[lid][1],**{p+'_in_crop':int(points[p][lid]>=0) for p in polys}})
    fields=['event_id','date','location_id','weather_grid_id']+[p+'_l'+str(l) for p in polys for l in range(8)]
    rows=0;cases=set();miss=Counter();temp=dest.with_suffix('.tmp.gz')
    with gzip.open(P/'candidate_matches.csv.gz','rt',encoding='utf-8') as f,gzip.open(temp,'wt',encoding='utf-8',newline='') as out:
        w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
        for r in csv.DictReader(f):
            if r['event_id'] not in eids:continue
            lid=r['location_id'];i=di[r['date']];record={k:r[k] for k in ['event_id','date','location_id']};record['weather_grid_id']=weather_loc[lid][0]
            for poll in polys:
                ci=points[poll][lid]
                for lag in range(8):
                    val=float(values[poll][i-lag,ci]) if ci>=0 and i>=lag else math.nan
                    record[poll+'_l'+str(lag)]=round(val,4) if math.isfinite(val) else ''
                    if not math.isfinite(val):miss[poll+'_l'+str(lag)]+=1
            w.writerow(record);rows+=1;cases.add(r['event_id'])
    assert cases==eids;os.chmod(temp,0o600);temp.replace(dest);os.chmod(Q/'exposure_location_assignments.csv',0o600)
    meta={'candidate_events':len(eids),'locations':len(lids),'matched_rows':rows,'missing_exposure_values':dict(miss),'out_of_crop_locations':{p:sum(i<0 for i in points[p].values()) for p in polys},'no_exposure_imputation':True,'address_quality_unchanged':True,'units':'ug/m3','pollution_lags':'0..7','weather':'nearest fixed ERA5 grid, spherical distance','extraction_scope':'all candidate cardiovascular and cerebrovascular events' if args.all_events else 'cardiovascular candidates only','location_tier_counts':dict(Counter(loc[l]['analysis_tier'] for l in lids)),'models_fitted':0}
    (O/'个体暴露匹配核验.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2));print(json.dumps(meta,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
