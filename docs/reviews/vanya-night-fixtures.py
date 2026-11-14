"""Run the actual local service with isolated, synthetic V11 acceptance history."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.expectations.egor.make_e9_contract import CV, JOBS, DisputedModel
from prototype.demo import SyntheticPrivacy
from prototype.local_service import LocalService
from prototype.pipeline import run_pipeline
from prototype.web_app import create_server


def seed(service):
    ids = {}
    for scenario in ('success', 'incomplete'):
        run = service.create({'mode': 'synthetic-replay', 'scenario': scenario,
                              'idempotency_key': 'fixture-' + scenario})
        ids[scenario] = run['run_id']
        service.wait(run['run_id'])

    run, _ = service.store.create({'mode': 'synthetic-replay'}, 'fixture-disputed', scenario='disputed')
    ids['disputed'] = run['run_id']
    service.store.start(run['run_id'])
    sources = {}
    report = asyncio.run(run_pipeline(CV, JOBS, DisputedModel(), SyntheticPrivacy(), source_sink=sources.update))
    report.update(mode='synthetic_replay_NOT_model_output', demo_scenario='disputed',
                  privacy={'professional_information_may_be_hidden': True}, openai_network_calls=0)
    service.store.finish(run['run_id'], report, sources)

    run, _ = service.store.create({'mode': 'synthetic-replay'}, 'fixture-interrupted', scenario='incomplete')
    ids['interrupted'] = run['run_id']
    service.store.start(run['run_id'])
    return ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='A new directory for synthetic acceptance state')
    args = parser.parse_args()
    args.directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    service = LocalService(args.directory)
    try:
        ids = seed(service)
    finally:
        service.close()

    service = LocalService(args.directory)
    with create_server(service, '127.0.0.1', 0) as server:
        config = {'origin': f'http://127.0.0.1:{server.server_port}', 'ids': ids}
        (args.directory / 'browser.json').write_text(json.dumps(config), encoding='utf-8')
        print(config['origin'], flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            service.close()


if __name__ == '__main__':
    main()
