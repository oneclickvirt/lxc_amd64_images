#!/usr/bin/env python3
"""Use a validated upstream catalog for listing and building the same image set."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import re
import time
import urllib.request

DISTROS = set('almalinux alpine archlinux centos debian fedora gentoo kali openeuler opensuse openwrt oracle rockylinux ubuntu'.split())
CODENAMES = {'bookworm':'12','trixie':'13','forky':'14','jammy':'22.04','noble':'24.04','resolute':'26.04',
             'kali-rolling':'latest','current':'current','9-Stream':'9','10-Stream':'10'}

def parse_jobs(content, distro):
    import yaml
    class JobLoader(yaml.SafeLoader):
        pass
    JobLoader.add_multi_constructor('!include:', lambda loader, suffix, node: None)
    job = yaml.load(content, Loader=JobLoader)[0]['job']
    axes = {a['axis']['name']:[str(x) for x in a['axis']['values']] for a in job['axes']}
    releases = axes['release']
    # Kali's distrobuilder downloader names its rolling release kali-rolling.
    if distro == 'kali': releases = ['kali-rolling']
    variants = [v for v in axes['variant'] if v in ('default','cloud','openrc','systemd')]
    if distro == 'gentoo': variants = ['cloud','openrc','systemd']
    return {'releases':[{'release':r,'version':'latest' if distro=='kali' else CODENAMES.get(r,r)} for r in releases],
            'architectures':[a for a in axes['architecture'] if a in ('amd64','arm64')], 'variants':variants}


def validate(data):
    if data.get('schema') != 1 or set(data['distros']) != DISTROS:
        raise ValueError('incomplete upstream image catalog')
    if not re.fullmatch('[0-9a-f]{40}', data['source_commit']):
        raise ValueError('invalid upstream catalog commit')
    for config in data['distros'].values():
        if not config['releases'] or not config['variants'] or not config['architectures']:
            raise ValueError('empty upstream image axis')
        for value in config['variants'] + config['architectures'] + [v for r in config['releases'] for v in r.values()]:
            if not re.fullmatch('[A-Za-z0-9_.-]+',value):
                raise ValueError('invalid upstream axis value')
    return data


def refresh_catalog(root, commit, deadline):
    import yaml
    def fetch(distro):
        url=f'https://raw.githubusercontent.com/lxc/lxc-ci/{commit}/jenkins/jobs/image-{distro}.yaml'
        for attempt in range(3):
            if time.monotonic() >= deadline: raise TimeoutError('catalog budget exhausted')
            try:
                with urllib.request.urlopen(url,timeout=min(30,deadline-time.monotonic())) as response:
                    return distro,parse_jobs(response.read().decode(),distro)
            except (OSError,ValueError,yaml.YAMLError):
                if attempt == 2: raise
                time.sleep(min(2**attempt,max(0,deadline-time.monotonic())))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        distros=dict(pool.map(fetch,sorted(DISTROS)))
    data=validate({'schema':1,'source_commit':commit,'distros':distros})
    path=root/'.github/image-catalog.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')


def matrix(data, repo, distro='all', scope='current', kind='container', architecture='all', exact_release='', variant=''):
    if distro != 'all' and distro not in DISTROS: raise ValueError('unknown distribution')
    arches = ['amd64'] if repo=='lxc_amd64_images' else ['arm64'] if repo=='lxc_arm_images' else ['amd64','arm64']
    if architecture != 'all': arches=[a for a in arches if a==architecture]
    rows=[]
    for name,config in sorted(data['distros'].items()):
        if distro != 'all' and distro != name: continue
        if kind == 'vm' and name in ('kali','oracle'): continue
        if variant and variant not in config['variants']: raise ValueError('unknown image variant')
        for release in config['releases']:
            if exact_release and exact_release != release['release']: continue
            if not exact_release and scope != 'full' and release['release'] in ('forky','snapshot','edge'): continue
            for arch in arches:
                if arch in config['architectures']:
                    rows.append({'distro':name,'release':release['release'],'arch':arch,
                                 'runner':'ubuntu-24.04-arm' if arch=='arm64' else 'ubuntu-24.04','kind':kind})
    if not rows or len(rows)>256: raise ValueError('empty or oversized image matrix')
    return {'include':rows}


def automatic_matrix(value, policy):
    """Quarantine confirmed failures in schedules; manual repair stays usable."""
    if policy.get('schema') != 1 or not isinstance(policy.get('entries'), list):
        raise ValueError('invalid automated image quarantine')
    blocked = set()
    for entry in policy['entries']:
        if (set(entry) != {'distro', 'release', 'arch', 'kind', 'reason', 'evidence'}
                or entry['distro'] not in DISTROS or entry['arch'] not in ('amd64', 'arm64')
                or entry['kind'] not in ('container', 'vm')
                or not re.fullmatch('[A-Za-z0-9_.-]+', entry['release'])
                or not entry['reason'] or not re.fullmatch(r'https://github\.com/oneclickvirt/[A-Za-z0-9_.-]+/actions/runs/[0-9]+', entry['evidence'])):
            raise ValueError('invalid quarantined image entry')
        key = tuple(entry[field] for field in ('distro', 'release', 'arch', 'kind'))
        if key in blocked:
            raise ValueError('duplicate quarantined image entry')
        blocked.add(key)
    return {'include': [row for row in value['include']
                        if tuple(row[field] for field in ('distro', 'release', 'arch', 'kind')) not in blocked]}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['selection','matrix'])
    parser.add_argument('--catalog',default='.github/image-catalog.json');parser.add_argument('--distro',default='all')
    parser.add_argument('--scope',choices=['current','full'],default='current');parser.add_argument('--kind',choices=['container','vm'],default='container')
    parser.add_argument('--release',default='');parser.add_argument('--variant',default='')
    parser.add_argument('--arch',choices=['all','amd64','arm64','x86_64','aarch64'],default='all')
    args=parser.parse_args();data=validate(json.loads(Path(args.catalog).read_text()))
    if args.command=='selection':
        config=data['distros'][args.distro]
        print(' '.join(r['release'] for r in config['releases']))
        print(' '.join(r['version'] for r in config['releases']))
        print(' '.join(config['variants']))
    else:
        value=matrix(data,os.environ['GITHUB_REPOSITORY'].split('/')[-1],args.distro,args.scope,args.kind,args.arch,args.release,args.variant)
        if os.environ.get('CI_IMAGE_AUTOMATIC') == 'true':
            original_count = len(value['include'])
            policy = json.loads(Path('.github/image-build-quarantine.json').read_text())
            value = automatic_matrix(value, policy)
            print(f'Automated image policy: {len(value["include"])} selected, {original_count-len(value["include"])} quarantined; previous assets retained')
        encoded=json.dumps(value,separators=(',',':'));print(encoded)
        with open(os.environ['GITHUB_OUTPUT'],'a') as output:
            print('matrix='+encoded,file=output)
            print('count='+str(len(value['include'])),file=output)

if __name__=='__main__': main()
