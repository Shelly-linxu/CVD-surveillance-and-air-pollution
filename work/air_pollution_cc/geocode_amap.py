"""Resumable geocoding of unique addresses; never send identifiers or diagnoses.

Run only after an account key and its quota are confirmed:
  .venv/bin/python3 geocode_amap.py --key-file /local/private/key.json --limit 100
Key file schema: {"amap_web_key":"..."}. Results retain provider coordinates
and precision labels; successful geocoding does not establish 1 km accuracy.
Documentation: https://lbs.amap.com/api/webservice/guide/api/georegeo
"""
import argparse, csv, json, os, time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[2]
PRIVATE=ROOT/'work/air_pollution_cc/private'

def main():
    if __import__('os').environ.get('GEOCODING_AUTHORIZED') != 'YES':
        raise RuntimeError('External address geocoding is disabled. Obtain data-custodian approval before setting GEOCODING_AUTHORIZED=YES.')
    ap=argparse.ArgumentParser()
    ap.add_argument('--key-file',type=Path,required=True)
    ap.add_argument('--limit',type=int,default=100)
    ap.add_argument('--interval',type=float,default=1.0)
    ap.add_argument('--queue',type=Path,default=PRIVATE/'geocoding_queue.csv')
    ap.add_argument('--results',type=Path,default=PRIVATE/'amap_geocoding_results.jsonl')
    args=ap.parse_args()
    if args.limit<1 or args.interval<0.2: ap.error('positive limit and interval >=0.2 required')
    key=json.loads(args.key_file.read_text())['amap_web_key'].strip()
    if not key: raise SystemExit('Empty key')
    output=args.results
    done=set()
    if output.exists():
        for line in output.read_text().splitlines():
            r=json.loads(line)
            if r.get('status')=='1': done.add(r['location_id'])
    processed=0
    # Newly created results file contains address-linked coordinates; restrict mode.
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    os.chmod(output,0o600)
    with os.fdopen(fd,'a',encoding='utf-8') as out, args.queue.open(encoding='utf-8-sig') as src:
        for row in csv.DictReader(src):
            if row['location_id'] in done: continue
            params=urlencode({'key':key,'address':row['address'],'city':'广州市','output':'JSON'})
            try:
                with urlopen('https://restapi.amap.com/v3/geocode/geo?'+params,timeout=30) as response:
                    result=json.load(response)
            except Exception:
                # Do not print exception URLs, which could contain credentials/addresses.
                raise SystemExit('Network request failed; no sensitive URL printed. Re-run to resume.')
            result.update(location_id=row['location_id'],provider='AMap',coordinate_system='GCJ-02',verified_within_1km=0,quality_status='requires_coordinate_conversion_and_accuracy_review',retrieved_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
            out.write(json.dumps(result,ensure_ascii=False)+'\n'); out.flush()
            processed+=1
            if result.get('status')!='1':
                print(json.dumps({'requests_this_run':processed,'stopped':True,'provider_info_code':result.get('infocode')}))
                break
            if processed>=args.limit: break
            time.sleep(args.interval)
    print(json.dumps({'requests_this_run':processed,'previous_successful_addresses':len(done),'results_file':str(output),'note':'No coordinates certified for main analysis yet.'}))

if __name__=='__main__': main()
