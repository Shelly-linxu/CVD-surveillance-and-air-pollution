"""Stage only local aggregate plotting inputs. Does not create a manuscript."""
from pathlib import Path
import shutil
R=Path(__file__).resolve().parents[1]
D=R/'outputs/air_pollution_cc/manuscript_reviewed_bw/tables';D.mkdir(parents=True,exist_ok=True)
files={'S29_two_group_interactions.csv':('two_group','亚组交互作用.csv'),'S30_subtype_interactions.csv':('five_outcomes','亚组交互作用.csv')}
for dest,(scope,name) in files.items():
 source=R/'outputs/air_pollution_cc'/scope/name
 if not source.exists(): raise FileNotFoundError(f'Find the interaction test output for {scope}: {source}')
 shutil.copy2(source,D/dest)
source=R/'outputs/air_pollution_cc/manuscript/tables'
for name in ['supp_reference_extensions.csv','supp_equal_knots_curves.csv']:
 shutil.copy2(source/name,D/name)
