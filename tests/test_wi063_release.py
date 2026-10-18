import argparse
import importlib.util
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location('deploy_wi063_test', Path(__file__).parents[1] / 'scripts/deploy_cloud_run.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


@pytest.mark.parametrize('failure', [None, 'second-job', 'remote-update', 'promote', 'smoke'])
def test_image_only_release_preserves_configuration_and_rolls_back(monkeypatch, failure):
    args = argparse.Namespace(region='region',target='wi063-s02',dry_run=False,secret_mode='secret-manager')
    calls, builds, restores = [], [], []
    monkeypatch.setattr(deploy, '_service_traffic', lambda **kw: [
        {'revisionName':'stable-before','percent':100}, {'revisionName':'tag-before','tag':deploy.DEFAULT_WI046_REMOTE_TAG}])
    monkeypatch.setattr(deploy, '_build_release_image', lambda *a, **k: builds.append(1) or 'repo@sha256:fixed')
    monkeypatch.setattr(deploy, '_run_capture', lambda cmd, **kw:
        subprocess.CompletedProcess(cmd,0,stdout='exact job export',stderr=''))
    monkeypatch.setattr(deploy, '_rollback_job_definitions', lambda **kw: restores.append(kw) or True)
    monkeypatch.setattr(deploy, '_tagged_service_url', lambda **kw: 'https://tag.example.test')
    monkeypatch.setattr(deploy, '_smoke_wi046_remote', lambda **kw: failure != 'smoke')
    monkeypatch.setattr(deploy, '_smoke_wi046_tagged_urls', lambda **kw: True)
    def execute(cmd, **kw):
        calls.append(cmd)
        if failure == 'second-job' and cmd[:4] == ['gcloud','run','jobs','update'] and 'overseas' in cmd[4]: return 1
        if failure == 'remote-update' and cmd[:4] == ['gcloud','run','services','update']: return 1
        if failure == 'promote' and '--to-latest' in cmd: return 1
        return 0
    monkeypatch.setattr(deploy,'_run',execute)
    result = deploy._deploy_wi063_s02(args,env={'KIS_AUTH_BASE_URL':'https://auth.test','KIS_RESOURCE_SERVER_URL':'https://resource.test/mcp'},project='project')
    assert result == (0 if failure is None else 1)
    assert builds == [1]
    assert len([c for c in calls if c[:4] == ['gcloud','run','jobs','update']]) == 2
    assert not any('execute' in c or 'scheduler' in c or '--args' in c or '--command' in c or '--env-vars-file' in c or '--update-env-vars' in c for c in calls)
    if failure:
        assert len(restores) == 1
        assert len(restores[0]['job_names']) == 2
        assert calls[-1][calls[-1].index('--to-revisions')+1] == 'stable-before=100'
        assert calls[-1][calls[-1].index('--update-tags')+1] == f'{deploy.DEFAULT_WI046_REMOTE_TAG}=tag-before'
    else:
        assert not restores
        assert all('repo@sha256:fixed' in c for c in calls if '--image' in c)
        assert any('--to-latest' in c and '--update-tags' in c for c in calls)


def test_preflight_stops_before_build_without_rollback_routes(monkeypatch):
    args = argparse.Namespace(region='region', target='wi063-s02', dry_run=False)
    monkeypatch.setattr(deploy,'_service_traffic',lambda **kw: [])
    monkeypatch.setattr(deploy,'_build_release_image',lambda *a,**kw: pytest.fail('must not build'))
    assert deploy._deploy_wi063_s02(args,env={'KIS_AUTH_BASE_URL':'x','KIS_RESOURCE_SERVER_URL':'y'},project='p') == 1
