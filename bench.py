#!/usr/bin/env python3
"""Integrated AI Model Lab benchmark runner (Python standard library only).
No dependency on earlier downloaded benchmark kits. Never modifies Android project.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from collections import Counter
import core

STOP = threading.Event()
CHILD = None

def announce(s): print(s, flush=True)

def signal_handler(sig, frame):
    STOP.set()
    global CHILD
    if CHILD is not None and CHILD.poll() is None:
        try: os.killpg(CHILD.pid, signal.SIGTERM)
        except ProcessLookupError: pass

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def request(url, payload, timeout):
    raw=json.dumps(payload,ensure_ascii=False).encode('utf-8')
    with urllib.request.urlopen(urllib.request.Request(url,data=raw,headers={'Content-Type':'application/json'}),timeout=timeout) as r:
        return json.load(r)


def source_digest(root):
    """Sorted source fingerprint, intentionally ignores build, .git and secrets."""
    root=Path(root)
    if not root.is_dir(): raise FileNotFoundError(f'Android-проект отсутствует: {root}')
    h=hashlib.sha256()
    count=0
    for path in sorted(root.rglob('*')):
        if not path.is_file() or set(path.relative_to(root).parts) & {'build','.gradle','.git','.idea','.cxx'}:continue
        if path.suffix.lower() not in ('.java','.kt','.xml','.gradle','.kts'): continue
        rel=path.relative_to(root).as_posix()
        h.update(rel.encode('utf-8'));h.update(b'\0')
        h.update(hashlib.sha256(path.read_bytes()).digest());h.update(b'\0')
        count+=1
    return {'sha256':h.hexdigest(),'files':count}


def cpu_stat():
    try:
        v=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:]))
        return sum(v),v[3]+v[4]
    except (OSError,ValueError,IndexError): return None


def collect(samples,path,interval,gpu_index=None):
    old=cpu_stat()
    with path.open('w',encoding='utf-8',newline='') as out:
        cols=['seconds','gpu_percent','vram_mib','vram_total_mib','power_w','temp_c','ram_gib','swap_gib','cpu_percent']
        writer=csv.DictWriter(out,fieldnames=cols);writer.writeheader()
        started=time.monotonic()
        while True:
            gpu=core.gpu_metrics(gpu_index);mem=core.ram_metrics();now=cpu_stat()
            cpu=round(100*((now[0]-old[0])-(now[1]-old[1]))/(now[0]-old[0]),2) if now and old and now[0]>old[0] else None
            old=now
            item=dict(seconds=round(time.monotonic()-started,3),gpu_percent=gpu.get('gpu'),
                      vram_mib=gpu.get('vram'),vram_total_mib=gpu.get('vram_total'),
                      power_w=gpu.get('power'),temp_c=gpu.get('temp'),
                      ram_gib=round(mem.get('ram',0),3) if mem else None,
                      swap_gib=round(mem.get('swap',0),3) if mem else None,cpu_percent=cpu)
            samples.append(item);writer.writerow(item);out.flush()
            if STOP.wait(interval): break


def hardware_stats(samples):
    result={'samples':len(samples)}
    for k in ['gpu_percent','vram_mib','vram_total_mib','power_w','temp_c','ram_gib','swap_gib','cpu_percent']:
        x=[a[k] for a in samples if a.get(k) is not None]
        result[k]={'max':round(max(x),3),'avg':round(sum(x)/len(x),3)} if x else None
    power=0.0
    for a,b in zip(samples,samples[1:]):
        if a.get('power_w') is not None and b.get('power_w') is not None:
            power+=(a['power_w']+b['power_w'])*.5*(b['seconds']-a['seconds'])/3600
    result['gpu_energy_wh_estimate']=round(power,3)
    return result


def pi_events(path):
    stats={'messages':0,'peak_context_estimate':0,'tool_calls':{},'tool_errors':0,'usage':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0},'stop_reasons':{},'answer':'','status':'no_answer'}
    tool_counts=Counter();stop_counts=Counter();last=None
    with path.open(encoding='utf-8') as infile:
      for line in infile:
        try: item=json.loads(line)
        except ValueError: continue
        t=item.get('type')
        if t=='tool_execution_end':
            tool_counts[item.get('toolName','unknown')]+=1
            stats['tool_errors']+=bool(item.get('isError'))
        if t=='message_end':
            msg=item.get('message') or {}
            if msg.get('role')!='assistant':continue
            stats['messages']+=1
            last=msg
            use=msg.get('usage') or {}
            for k in stats['usage']:
                stats['usage'][k]+=use.get(k,0) or 0
            ctx=sum(use.get(k,0) or 0 for k in ('input','cacheRead','cacheWrite'))
            stats['peak_context_estimate']=max(stats['peak_context_estimate'],ctx)
            stop_counts[msg.get('stopReason','unknown')]+=1
    stats['tool_calls']=dict(tool_counts);stats['stop_reasons']=dict(stop_counts)
    if last:
        stats['answer']='\n'.join(str(b.get('text','')) for b in (last.get('content') or []) if b.get('type')=='text').strip()
        r=last.get('stopReason')
        stats['status']='completed' if r in ('stop','end_turn') and stats['answer'] else ('truncated' if r=='length' else ('no_final_answer' if r in ('toolUse','tool_use') else str(r)))
    return stats


def create_report_dir(kind,model):
    core.prepare()
    prefix=re.sub(r'[^A-Za-z0-9_-]','-',model)
    stamp=dt.datetime.now().strftime('%d-%m-%Y_%H-%M-%S')
    for i in range(101):
        d=core.REPORTS/(f'{prefix}_{kind}_{stamp}' + (f'_{i}' if i else ''))
        try: d.mkdir(mode=0o700);return d
        except FileExistsError:continue
    raise RuntimeError('Не удалось создать уникальную папку отчёта')


def generate_context(target):
    # Not exact token count. Ground truth facts placed near 5/50/95% by characters.
    refs=('ROUTE_SAFFRON_38','VALIDATE_COBALT_62','localConfiguration.uri.toString()')
    fillers=['Android fragment controller Kotlin java project dependency lifecycle player data source '+str(i)+'\n' for i in range(1000)]
    length=max(4000,int(target*4))
    def pad(size):
        lines=[];current=0;i=0
        while current<size:
            line=fillers[i%len(fillers)];lines.append(line);current+=len(line);i+=1
        return ''.join(lines)[:size]
    # Markers near 5%, 50%, and 95% of synthetic data by character position.
    spans=[int(length*.05),int(length*.45),int(length*.45),int(length*.05)]
    content=(pad(spans[0])+'\nroute_key='+refs[0]+'\n'+
             pad(spans[1])+'\nvalidation_key='+refs[1]+'\n'+
             pad(spans[2])+'\nrequested_fix='+refs[2]+'\n'+pad(spans[3]))
    prefix='Найди три связанных контрольных факта в тексте и ответь тремя строками: route_key=..., validation_key=..., requested_fix=... .\n'
    return prefix+content+'\nКОНЕЦ ДАННЫХ. Ответ строго тремя строками.'


def run_api(kind,model,args,d):
    pre=core.json_api(f'http://127.0.0.1:{args.port}/props') or {}
    if pre.get('model_alias') and pre['model_alias']!=model:
        raise RuntimeError(f'На порту {args.port} загружен другой alias')
    cases=[]
    if kind=='speed':
        prompt='Напиши ровно двадцать практических рекомендаций по архитектуре Android приложений на Kotlin, каждую отдельным пунктом.'
        cases=[('speed',prompt,'')]
    elif kind=='qa':
        cases=[('math1','Вычисли (73*19)-48. Ответь только одним целым числом.','1339'),
               ('math2','Вычисли 17*(24-9)+36/3. Ответь только одним целым числом.','267'),
               ('math3','Вычисли сумму квадратов 12 и 13. Ответь только одним целым числом.','313')]
    elif kind=='context':
        prompt=generate_context(int(args.target_tokens))
        cases=[('context',prompt,'route_key=ROUTE_SAFFRON_38\nvalidation_key=VALIDATE_COBALT_62\nrequested_fix=localConfiguration.uri.toString()')]
    else: raise ValueError(kind)
    data=[];t0=time.monotonic()
    for name,prompt,expected in cases:
        if STOP.is_set():break
        announce('API task '+name)
        payload={'model':model,'messages':[{'role':'user','content':prompt}],
                 'temperature':0,'max_tokens':int(args.output_tokens) if kind=='speed' else 160,'stream':False}
        start=time.monotonic()
        result=request(f'http://127.0.0.1:{args.port}/v1/chat/completions',payload,args.timeout)
        elapsed=round(time.monotonic()-start,3)
        reply=((result.get('choices') or [{}])[0].get('message') or {}).get('content') or ''
        usage=result.get('usage') or {}
        expected_ok=(str(reply).strip()==expected) if expected else None
        entry={'name':name,'elapsed_s':elapsed,'answer':reply,'passed':expected_ok,
               'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
               'input_tokens':usage.get('prompt_tokens'),'output_tokens':usage.get('completion_tokens'),
               'timings':result.get('timings'),
               'tokens_per_wall_s':round(usage.get('completion_tokens',0)/elapsed,2) if elapsed and isinstance(usage.get('completion_tokens'),int) else None}
        data.append(entry)
        announce(f'{name}: {elapsed} c, output={entry["output_tokens"]}, passed={expected_ok}')
    status='completed' if len(data)==len(cases) else 'cancelled'
    score=sum(x['passed'] for x in data) if kind=='qa' else None
    (d/'answers.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {'status':status,'cases':data,'score':score,'max_score':len(cases) if kind=='qa' else None,
            'elapsed_s':round(time.monotonic()-t0,2),'prompt_sha256':data[0]['prompt_sha256'] if len(data)==1 else None,
            'note':'Context length is approximate, inspect API usage prompt_tokens' if kind=='context' else ''}


def run_android(kind,model,args,d):
    if args.port != 8080:
        raise RuntimeError('Android Pi local-lab использует порт 8080. Для другого порта нужен отдельный Pi provider.')
    state=core.preflight_android()
    if state['alias']!=model: raise RuntimeError('Серверная модель отличается от выбранной')
    project=Path(args.project).expanduser().resolve()
    if not project.is_dir(): raise FileNotFoundError(project)
    prompt_file=core.ROOT/'benchmarks'/'prompts'/('LP-P1-STB-ui.md' if kind=='p1' else 'LP-P2-STB-player.md')
    ext=core.ROOT/'benchmarks'/'extensions'/'tool-guard.js'
    if not shutil.which('pi'): raise RuntimeError('Не найден Pi в PATH')
    prompt_sha=hashlib.sha256(prompt_file.read_bytes()).hexdigest()
    announce('Проверяю SHA256 исходников (только чтение)...')
    fingerprint=source_digest(project)
    env=os.environ.copy()
    env['AI_LAB_TOOL_BUDGET']=str(args.budget)
    command=['pi','--mode','json','--provider','local-lab','--model',model,'--thinking','off',
             '--no-session','--no-context-files','--no-extensions','--no-mcp','--no-skills',
             '--no-prompt-templates','--no-approve','--tools','read,grep,find,ls',
             '--extension',str(ext),
             '--append-system-prompt',
             'Все ответы только по-русски. Итоговый ответ обязателен. Не делай непроверенных утверждений. Инструменты только на чтение.',
             '@'+str(prompt_file)]
    stdout=d/'pi-events.jsonl';stderr=d/'pi-stderr.log'
    global CHILD
    announce(f'Pi: project={project}, budget={args.budget}, timeout={args.timeout}; fingerprint={fingerprint["sha256"]}')
    ended_by_timeout=False
    try:
        with stdout.open('w',encoding='utf-8') as out, stderr.open('w',encoding='utf-8') as err:
            CHILD=subprocess.Popen(command,cwd=project,env=env,stdout=out,stderr=err,
                                   stdin=subprocess.DEVNULL,start_new_session=True)
            try: CHILD.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                ended_by_timeout=True
                STOP.set()
                try: os.killpg(CHILD.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try: CHILD.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(CHILD.pid,signal.SIGKILL);CHILD.wait()
        parsed=pi_events(stdout)
        if ended_by_timeout: parsed['status']='timeout'
        elif STOP.is_set(): parsed['status']='cancelled'
        answer=parsed.pop('answer')
        (d/'final_answer.md').write_text(answer+'\n',encoding='utf-8')
        exitcode=CHILD.returncode
        result={'status':parsed['status'],'pi':parsed,'exit_code':exitcode,'prompt_sha256':prompt_sha,
                'project':str(project),'fingerprint':fingerprint,'timeout':int(args.timeout),
                'tool_budget':int(args.budget),'context_window':state['ctx']}
        return result
    finally: CHILD=None


def main():
    p=argparse.ArgumentParser(description='AI Model Lab, integrated benchmark engine')
    p.add_argument('--kind',required=True,choices=('speed','qa','context','p1','p2'))
    p.add_argument('--model',required=True)
    p.add_argument('--port',type=int,default=8080)
    p.add_argument('--gpu',default='',help='Индекс NVIDIA GPU или UUID для записи телеметрии')
    p.add_argument('--project',default=core.settings().get('android_project',''))
    p.add_argument('--timeout',type=int,default=1800)
    p.add_argument('--budget',type=int,default=24)
    p.add_argument('--output-tokens',type=int,default=256)
    p.add_argument('--target-tokens',type=int,default=8192)
    args=p.parse_args()
    if not (1024<=args.port<=65535 and 10<=args.timeout<=7200 and 1<=args.budget<=200 and 32<=args.output_tokens<=2048):
        p.error('Недопустимые бюджет, тайм-аут или длина ответа')
    core.prepare()
    d=create_report_dir(args.kind,args.model)
    samples=[];thread=threading.Thread(target=collect,args=(samples,d/'telemetry.csv',2,args.gpu),daemon=True)
    thread.start();started=time.monotonic()
    metadata={'schema_version':3,'started_at':dt.datetime.now().astimezone().isoformat(),
              'model':args.model,'kind':args.kind,'arguments':vars(args)}
    announce('REPORT_DIR='+str(d))
    try:
        if args.kind in ('p1','p2'):result=run_android(args.kind,args.model,args,d)
        else:result=run_api(args.kind,args.model,args,d)
    except Exception as exc:
        result={'status':'error','error':str(exc)}
        announce('ОШИБКА: '+str(exc))
    finally:
        STOP.set();thread.join(timeout=5)
    metadata.update({'result':result,'elapsed_s':round(time.monotonic()-started,3),
                     'hardware':hardware_stats(samples),'finished_at':dt.datetime.now().astimezone().isoformat()})
    core.atomic_json(d/'summary.json',metadata)
    with (d/'overview.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['model','kind','status','seconds','vram_max_mib','gpu_energy_wh_estimate','prompt_sha256'])
        w.writerow([args.model,args.kind,result['status'],metadata['elapsed_s'],
                    (metadata['hardware'].get('vram_mib') or {}).get('max'),
                    metadata['hardware']['gpu_energy_wh_estimate'],result.get('prompt_sha256')])
    summary=(f"# AI Model Lab Benchmark\n\nМодель: **{args.model}**  \n"
             f"Тип: **{args.kind}**  \nСтатус: **{result['status']}**  \n"
             f"Время: **{metadata['elapsed_s']} с**  \n"
             f"Пик VRAM: **{(metadata['hardware'].get('vram_mib') or {}).get('max')} MiB**  \n"
             f"Энергия GPU (оценка): **{metadata['hardware']['gpu_energy_wh_estimate']} Вт·ч**  \n"
             f"SHA256 промпта: `{result.get('prompt_sha256')}`  \n"
             f"\nКритерий завершения не равен качеству анализа. Полные данные — summary.json.\n")
    (d/'summary.md').write_text(summary,encoding='utf-8')
    announce('RESULT='+result['status'])
    announce('SUMMARY='+str(d/'summary.json'))
    return 0 if result['status']=='completed' else 1

if __name__=='__main__':sys.exit(main())
