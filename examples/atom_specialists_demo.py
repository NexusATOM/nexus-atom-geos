"""Prepare a synthetic ATOM workflow with two scripted specialist reviewers."""

import argparse
import sys
from pathlib import Path

import yaml

from nexus_atom_geos.config import GEOSConfig
from nexus_atom_geos.demo import prepare_demo


def prepare(destination: Path):
    config = prepare_demo(destination)
    root = config.workspace.parent
    runtime = root / "scripted_runtime.py"
    runtime.write_text("""import json,sys
request=json.load(sys.stdin)
e=request['evidence']
if request['task']['capability']=='geos.review_specialist':
    source=e['contexts'][0]['evidence'][0]
    proposal={'summary':'Scripted '+e['profile']['name']+' review',
              'findings':[{'summary':'Source supplied for review; no scientific certification',
                           'evidence_ids':[source['id']]}],
              'unknowns':['Synthetic response; live reasoning quality unmeasured']}
else:
    assert len(e['specialist_assessments'])==2
    source=e['files'][0]
    proposal={'summary':'Synthetic arithmetic optimization','changes':[{
        'repository':source['repository'],'path':source['path'],
        'before_sha256':source['before_sha256'],
        'content':'def compute():\\n    return float(99999 * 100000 // 2)\\n',
        'rationale':'Arithmetic identity, checked by executed gates'}]}
print(json.dumps({'proposal':proposal,'rationale':'Scripted local protocol demonstration'}))
""")
    data = config.model_dump(mode="json")
    data.update(
        proposal=None,
        runtime_argv=[sys.executable, str(runtime)],
        targets=[["MAPL", "kernel.py"]],
        objective_tags=["conservation"],
        specialists=[
            {
                "name": "conservation",
                "repositories": ["MAPL"],
                "objective_tags": ["conservation"],
                "instructions": "Review conservation assumptions and missing evidence.",
            },
            {
                "name": "reproducibility",
                "repositories": ["MAPL"],
                "instructions": "Review reproducibility and source provenance.",
            },
        ],
    )
    validated = GEOSConfig.model_validate(data)
    path = root / "specialists.yaml"
    path.write_text(yaml.safe_dump(validated.model_dump(mode="json")))
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    print(prepare(parser.parse_args().destination))
