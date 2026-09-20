"""Real subprocesses run only the temporary fake CLI; no platform or real keys."""
from argparse import Namespace
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

SPEC = importlib.util.spec_from_file_location('training_submit', Path(__file__).parents[1] / 'scripts/training_submit.py')
m = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)

FAKE = r'''
import hashlib,json,os,sys
from pathlib import Path
import yaml
a=sys.argv[1:]; op=a[1]; root=Path(os.environ['FIXTURE_ROOT'])
def option(name):return a[a.index(name)+1]
def out(value):print('An update is available');print(json.dumps(value))
if '--help' in a:
 print('--conf --task_name --output --status --name --limit --offset --id');sys.exit(0)
with (root/'calls.jsonl').open('a') as f:f.write(json.dumps({'operation':op})+'\n')
db=root/'platform.json'; rows=json.loads(db.read_text()) if db.exists() else []
scenario=os.environ.get('FIXTURE_SCENARIO','success')
if op=='list':
 offset=int(option('--offset'));limit=int(option('--limit'));out(rows[offset:offset+limit]);sys.exit(0)
if op=='get':
 identity=option('--id')
 row=next((r for r in rows if r['JobId']==identity),{'JobId':identity,'JobName':'source','Status':'Running'})
 if scenario=='wrong_get' and rows:row={**row,'JobId':'t-unrelated'}
 out([row]);sys.exit(0)
if op=='submit':
 cfg=Path(option('--conf'));assert cfg.stat().st_mode & 0o777 == 0o600
 assert cfg.parent.stat().st_mode & 0o777 == 0o700
 with (root/'submitted.json').open('w') as f:json.dump({'config_sha':hashlib.sha256(cfg.read_bytes()).hexdigest(),'private_path':str(cfg),'priority':option('--priority')},f)
 if scenario=='reject':
  conf=yaml.safe_load(cfg.read_text());path=conf['Storages'][0]['SubPath']
  print('提交失败: Post "https://example.invalid/?Signature=never-save" Code: AccessDenied dir: '+path+', mode: RDONLY '+os.environ['VOLC_SECRET_ACCESS_KEY'],file=sys.stderr);sys.exit(1)
 if scenario!='uncreated_ambiguous':
  row={'JobId':'t-new-fixture','JobName':option('--task_name'),'Status':'Queue'};rows.append(row);db.write_text(json.dumps(rows))
 if scenario in ('ambiguous','uncreated_ambiguous'):print('response lost');sys.exit(0)
 out({'JobId':'t-new-fixture'});sys.exit(0)
raise SystemExit(3)
'''


class WorkflowTests(unittest.TestCase):
    @contextmanager
    def fixture(self, scenario='success', minimum=True):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); cli=root/'fake-mlp';cli.write_text('#!'+sys.executable+'\n'+FAKE);cli.chmod(0o700)
            code=root/'code';code.mkdir();data=root/'data';data.mkdir();(data/'model').write_text('weights')
            config={'TaskName':'fixture-copy','Entrypoint':'exec bash scripts/run/finetune.sh projects/task exp_name=task edp.card=task model.max_epochs=2',
                    'TaskRoleSpecs':[{'RoleName':'worker','RoleReplicas':2,'ResourceSpec':{'GPUNum':3}}],
                    'Storages':[{'Type':'Vepfs','MountPath':str(code),'SubPath':'group/user','VepfsId':'vepfs-fixture','ReadOnly':True},
                                {'Type':'Nas','MountPath':str(data),'SubPath':'training','NasId':'nas-fixture'}],
                    'Envs':{'API_KEY':'cfgXYZ7','LONG_SECRET':'configuration-secret-fixture'}}
            conf=root/'private.yaml';conf.write_text(yaml.safe_dump(config));conf.chmod(0o600)
            auth=root/'authorization.json';auth.write_text(json.dumps({'actor':'user','authorized':True,'source_id':'t-source','task_name':'fixture-copy','basis':'User asked to create this training task.'}))
            requirements=root/'requirements.json';requirements.write_text(json.dumps({'minimum_mount_scope':minimum,'dependencies':[
                {'role':'code','path':str(code),'access':'read'}, {'role':'data','path':str(data),'access':'read'},
                {'role':'model','path':str(data/'model'),'access':'read'}, {'role':'output','path':str(data/'runs'),'access':'write'},
                {'role':'cache','path':str(root/'cache'),'access':'write','storage':'container_local'}]}))
            args=Namespace(config=conf,authorization=auth,requirements=requirements,output_path=data/'runs'/'new',journal=root/'journal',record=root/'plan.json',
                           source_id='t-source',name='fixture-copy',task='projects/task',region='fixture-region',exp_name=None,card=None,cli=str(cli),priority=4,
                           statuses=m.STATUSES,credential_script=None,recovery=None,recovery_reason=None)
            env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C.UTF-8','FIXTURE_ROOT':str(root),'FIXTURE_SCENARIO':scenario,
                 'VOLC_ACCESS_KEY_ID':'fixture-access-key','VOLC_SECRET_ACCESS_KEY':'fixture-secret-key'}
            with patch.dict(os.environ,env,clear=True):yield root,args,config

    def test_command_smoke_uses_exact_pinned_entrypoint_and_submits_once(self):
        with self.fixture() as (root,args,config):
            args.workload = 'command'
            args.task = None
            args.entrypoint_file = root / 'entrypoint.txt'
            args.entrypoint_file.write_text('timeout 300 bash /workspace/smoke.sh')
            config['Entrypoint'] = args.entrypoint_file.read_text()
            args.config.write_text(yaml.safe_dump(config))
            m.preflight(args)
            plan = m.read(args.record)
            self.assertEqual(plan['workload'], 'command')
            result = m.submit(Namespace(plan=args.record, intent=root/'intent.json'))
            self.assertEqual(result['status'], 'submitted_and_get_verified')
            self.assertEqual(self.calls(root).count('submit'), 1)

    def test_command_rejects_entrypoint_mismatch_and_later_changes(self):
        with self.fixture() as (root,args,config):
            args.workload = 'command'
            args.entrypoint_file = root / 'entrypoint.txt'
            args.entrypoint_file.write_text('timeout 300 bash smoke.sh')
            with self.assertRaises(m.Stop) as caught:
                m.preflight(args)
            self.assertEqual(caught.exception.code, 'command_entrypoint_mismatch')
            config['Entrypoint'] = args.entrypoint_file.read_text()
            args.config.write_text(yaml.safe_dump(config))
            m.preflight(args)
            args.entrypoint_file.write_text('different command')
            with self.assertRaises(m.Stop) as caught:
                m.submit(Namespace(plan=args.record, intent=root/'intent.json'))
            self.assertEqual(caught.exception.code, 'input_changed')
            self.assertEqual(self.calls(root), [])

    def calls(self,root):
        file=root/'calls.jsonl'
        return [json.loads(line)['operation'] for line in file.read_text().splitlines()] if file.exists() else []

    def test_duplicate_search_cannot_omit_terminal_or_transitional_statuses(self):
        with self.fixture() as (root,args,config):
            args.statuses = 'Running,Queue'
            with self.assertRaises(m.Stop) as caught:
                m.preflight(args)
            self.assertEqual(caught.exception.code, 'all_statuses_required')
            self.assertEqual(self.calls(root), [])
            args.statuses = m.STATUSES
            m.preflight(args)
            plan = m.read(args.record)
            plan['statuses'] = 'Running'
            plan['plan_sha256'] = m.digest({k:v for k,v in plan.items() if k != 'plan_sha256'})
            args.record.write_text(json.dumps(plan))
            with self.assertRaises(m.Stop) as caught:
                m.submit(Namespace(plan=args.record,intent=root/'intent.json'))
            self.assertEqual(caught.exception.code, 'all_statuses_required')
            self.assertEqual(self.calls(root), [])

    def test_preflight_is_offline_and_success_submits_unchanged_once(self):
        with self.fixture() as (root,args,config):
            self.assertEqual(m.preflight(args)['status'],'offline_preflight_passed');self.assertEqual(self.calls(root),[])
            intent=root/'intent.json';out=m.submit(Namespace(plan=args.record,intent=intent))
            self.assertEqual(out['status'],'submitted_and_get_verified');self.assertEqual(self.calls(root),['list','submit','get'])
            submitted=m.read(root/'submitted.json');self.assertEqual(submitted['config_sha'],m.pin(args.config)['sha256'])
            self.assertEqual(submitted['priority'],'4');self.assertFalse(Path(submitted['private_path']).exists())
            with self.assertRaises(m.Stop):m.submit(Namespace(plan=args.record,intent=root/'other-intent.json'))
            self.assertEqual(self.calls(root).count('submit'),1)
            text=intent.read_text()+args.record.read_text()
            for secret in ('fixture-access-key','fixture-secret-key','cfgXYZ7','configuration-secret-fixture'):self.assertNotIn(secret,text)
            self.assertEqual(m.read(intent)['authentication']['caller_identity'],'unknown')

    def test_ambiguous_response_is_recovered_readonly_and_existing_task_blocks(self):
        with self.fixture('ambiguous') as (root,args,_):
            m.preflight(args);intent=root/'intent.json';out=m.submit(Namespace(plan=args.record,intent=intent))
            self.assertEqual(out['status'],'submission_needs_readonly_recovery')
            # Cleanup of private source config does not prevent read-only recovery.
            original=args.config.read_bytes();args.config.unlink()
            recovery=root/'recovery.json';result=m.recover(Namespace(intent=intent,record=recovery))
            self.assertEqual(len(result['matches']),1);self.assertEqual(self.calls(root).count('submit'),1)
            args.config.write_bytes(original);args.config.chmod(0o600)
            args.record=root/'plan2.json';args.recovery=recovery;args.recovery_reason='Investigated the response.'
            with self.assertRaises(m.Stop):m.preflight(args)

    def test_failed_request_requires_distinct_proof_and_intent_after_concrete_fix(self):
        with self.fixture('uncreated_ambiguous') as (root,args,_):
            m.preflight(args);intent=root/'intent.json';m.submit(Namespace(plan=args.record,intent=intent));before=m.pin(intent)
            recovery=root/'recovery.json';m.recover(Namespace(intent=intent,record=recovery))
            args.record=root/'plan2.json';args.recovery=recovery;args.recovery_reason='Fixed the local response transport configuration.'
            m.preflight(args);os.environ['FIXTURE_SCENARIO']='success'
            self.assertEqual(m.submit(Namespace(plan=args.record,intent=root/'intent2.json'))['status'],'submitted_and_get_verified')
            self.assertEqual(m.pin(intent),before);self.assertEqual(self.calls(root).count('submit'),2)
            with self.assertRaises(m.Stop):m.submit(Namespace(plan=args.record,intent=root/'intent3.json'))

    def test_minimum_acl_is_actionable_redacted_and_blocks_blind_retry(self):
        with self.fixture('reject') as (root,args,_):
            m.preflight(args);intent=root/'intent.json';out=m.submit(Namespace(plan=args.record,intent=intent))
            self.assertEqual(out['status'],'blocked_minimum_mount_acl')
            text=intent.read_text();self.assertIn('group/user',text);self.assertIn('RDONLY',text);self.assertNotIn('fixture-secret-key',text)
            self.assertIn('AccessDenied',m.read(intent)['diagnostic']['codes'])
            recovery=root/'recovery.json';m.recover(Namespace(intent=intent,record=recovery))
            args.record=root/'plan2.json';args.recovery=recovery;args.recovery_reason='No external access change yet.'
            with self.assertRaisesRegex(m.Stop,'minimum_mount_acl'):m.preflight(args)
            self.assertEqual(self.calls(root).count('submit'),1)

    def test_full_status_pagination_finds_late_exact_match(self):
        with self.fixture() as (root,args,_):
            rows=[{'JobId':f't-other-{i}','JobName':f'nearby-{i}','Status':'Killed'} for i in range(100)]
            rows.append({'JobId':'t-old-exact','JobName':args.name,'Status':'Initialized'})
            (root/'platform.json').write_text(json.dumps(rows));m.preflight(args)
            result=m.submit(Namespace(plan=args.record,intent=root/'intent.json'))
            self.assertEqual(result['error_code'],'exact_name_already_exists');self.assertEqual(self.calls(root),['list','list'])

    def test_source_auth_check_does_not_claim_caller_or_create_permission(self):
        with self.fixture() as (root,args,_):
            args.record=root/'inspection.json';result=m.inspect_source(args)
            self.assertEqual(result['status'],'source_readonly_check_passed');self.assertEqual(self.calls(root),['get'])
            actual=m.read(args.record);self.assertEqual(actual['authentication']['caller_identity'],'unknown')
            self.assertFalse(actual['create_permission_verified'])

    def test_output_collision_config_change_and_active_name_lock_stop_before_create(self):
        for change in ('output','config','lock'):
            with self.subTest(change=change),self.fixture() as (root,args,_):
                m.preflight(args);plan=m.read(args.record)
                if change=='output':args.output_path.mkdir(parents=True)
                if change=='config':args.config.write_text(args.config.read_text()+'# changed\n')
                if change=='lock':
                    with m.claim_lock(plan),self.assertRaises(m.Stop):m.submit(Namespace(plan=args.record,intent=root/'intent.json'))
                else:
                    with self.assertRaises(m.Stop):m.submit(Namespace(plan=args.record,intent=root/'intent.json'))
                self.assertNotIn('submit',self.calls(root))

    def test_unused_mount_readonly_writes_and_wrong_three_fields_fail_offline(self):
        for change in ('unused','readonly','task','card','redacted','string_bool'):
            with self.subTest(change=change),self.fixture() as (root,args,config):
                if change=='unused':config['Storages'].append({'Type':'Nas','MountPath':str(root/'unused')})
                elif change=='readonly':config['Storages'][1]['ReadOnly']=True
                elif change=='task':config['Entrypoint']=config['Entrypoint'].replace('projects/task','projects/old')
                elif change=='card':config['Entrypoint']=config['Entrypoint'].replace('edp.card=task','edp.card=old')
                elif change=='redacted':config['Envs']['API_KEY']='[REDACTED]'
                else:config['Storages'][0]['ReadOnly']='true'
                args.config.write_text(yaml.safe_dump(config))
                with self.assertRaises(m.Stop):m.preflight(args)
                self.assertEqual(self.calls(root),[])

    def test_help_must_match_subcommands_not_top_level_banner(self):
        result=SimpleNamespace(returncode=0,stdout='Top level command help',stderr='')
        with patch.object(m.subprocess,'run',return_value=result):
            with self.assertRaisesRegex(m.Stop,'cli_subcommands_not_supported'):m.supported_cli(sys.executable)

    def test_short_secrets_https_chinese_codes_and_oversized_lines(self):
        config={'Envs':{'API_KEY':'abc123'},'Storages':[{'SubPath':'group/user'}]}
        raw='错误: Post "https://x.invalid/?Signature=secret" Code: InvalidParameter.Foo dir: group/user mode: RDONLY abc123\n'
        raw+='Code: ResourceLimitExceeded '+'x'*900+'\nAuthorization: credential failed\n'
        result=m.diagnostic(SimpleNamespace(returncode=1,stdout='',stderr=raw),{},config)
        value=json.dumps(result);self.assertNotIn('abc123',value);self.assertNotIn('x.invalid',value);self.assertNotIn('x'*100,value)
        self.assertIn('group/user',value);self.assertIn('ResourceLimitExceeded',result['codes']);self.assertIn('[URL]',value)

    def test_literal_auth_is_opt_in_and_never_executes_script(self):
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory)/'startup.sh';marker=Path(directory)/'executed'
            script.write_text('export TOS_AK=fixture-key\nexport TOS_SK=fixture-secret\ntouch '+str(marker)+'\n')
            values,basis=m.credential_values({},script)
            self.assertEqual(values,('fixture-key','fixture-secret'));self.assertEqual(basis['caller_identity'],'unknown');self.assertFalse(marker.exists())
            script.write_text('export TOS_AK=$(bad)\nexport TOS_SK=fixture-secret\n')
            with self.assertRaises(m.Stop):m.credential_values({},script)
            self.assertEqual(m.credential_values({})[1]['source'],'existing_cli_configuration_uninspected')


if __name__ == '__main__': unittest.main()
