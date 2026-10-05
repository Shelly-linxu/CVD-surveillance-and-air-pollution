from pathlib import Path
import json,datetime
import pandas as pd
import numpy as np
import netCDF4
R=Path(__file__).resolve().parents[2];Q=R/'work/air_pollution_cc/private/two_group';O=R/'outputs/air_pollution_cc/two_group'
x=pd.read_csv(Q/'matched_exposure_rows.csv.gz');loc=pd.read_csv(Q/'exposure_location_assignments.csv').set_index('location_id');inv={(a['pollutant'],a['date']):a for a in map(json.loads,(R/'outputs/air_pollution_cc/chap_crop_inventory.jsonl').read_text().splitlines())}
rng=np.random.default_rng(20261003);rows=x.iloc[rng.choice(len(x),size=30,replace=False)];errs=[];n=0
for _,row in rows.iterrows():
 for pol in ['PM25','PM10','O3']:
  lag=int(rng.integers(0,8));d=(datetime.date.fromisoformat(row.date)-datetime.timedelta(days=lag)).isoformat();src=inv[pol,d];l=loc.loc[row.location_id]
  with netCDF4.Dataset(src['path']) as ds:
   yi=np.argmin(abs(ds['lat'][:]-l.latitude));xi=np.argmin(abs(ds['lon'][:]-l.longitude));v=ds[src['variable']][yi,xi];v=float(v) if not np.ma.is_masked(v) else np.nan
  expected=row[f'{pol}_l{lag}'];n+=1
  if not ((np.isnan(v) and np.isnan(expected)) or np.isclose(v,expected,atol=.0001,rtol=0)):errs.append({'pollutant':pol,'lag':lag})
assert not errs,errs
(O/'暴露独立抽样核验.json').write_text(json.dumps({'scalar_checks':n,'mismatches':len(errs),'seed':20261003,'checks':'独立读取netCDF单个标量，对比30个候选日期×3污染物随机滞后；不输出个体信息'},ensure_ascii=False,indent=2))
print({'scalar_checks':n,'mismatches':len(errs)})
