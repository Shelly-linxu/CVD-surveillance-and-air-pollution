// Offline conversion only. No network; no addresses enter this helper.
const fs=require('node:fs');const gcoord=require('gcoord');
const rows=JSON.parse(fs.readFileSync(0,'utf8'));
for(const row of rows){const gcj=[row.gcj02_longitude,row.gcj02_latitude];const wgs=gcoord.transform(gcj,gcoord.GCJ02,gcoord.WGS84);const back=gcoord.transform(wgs,gcoord.WGS84,gcoord.GCJ02);if(Math.max(...back.map((v,i)=>Math.abs(v-gcj[i])))>1e-6)throw Error('Coordinate conversion validation failed');row.longitude=wgs[0];row.latitude=wgs[1];}
process.stdout.write(JSON.stringify(rows));
