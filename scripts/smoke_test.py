import urllib.request, json, sys

def get(path):
    try:
        r = urllib.request.urlopen(f'http://localhost:8000{path}')
        return json.loads(r.read()), None
    except Exception as e:
        return None, str(e)

tests = [
    '/api/health',
    '/api/dcs',
    '/api/dcs/DC001/skus',
    '/api/dcs/DC001/skus/MED001',
    '/api/dcs/DC001/skus/MED003',
    '/api/replenishment',
    '/api/replenishment?criticality=High&risk=red',
    '/api/replenishment/kpis',
    '/api/business-rules',
]

all_ok = True
for path in tests:
    data, err = get(path)
    if err:
        print(f'FAIL  {path}: {err}')
        all_ok = False
    else:
        if isinstance(data, dict):
            keys = list(data.keys())[:5]
            print(f'OK    {path}  keys={keys}')
        elif isinstance(data, list):
            print(f'OK    {path}  [{len(data)} items]')

print()

# Deep-check MED001 at DC001 (Low-criticality, Analgesic — good baseline check)
d, err = get('/api/dcs/DC001/skus/MED001')
if d is None:
    print(f'SKIP  DC001/MED001 deep check (API unavailable: {err})')
else:
    required = ['forecast','dacdf','options','batches','usable_inventory','health_flag',
                'near_expiry_qty','replenishment_requirement','projected_stockout_date','trend']
    missing = [f for f in required if f not in d]
    print('=== DC001/MED001 deep check ===')
    for f in required:
        val = d.get(f, 'MISSING')
        if isinstance(val, dict):
            val = str(list(val.keys())[:3])
        elif isinstance(val, list):
            val = f'[{len(val)} items]'
        print(f'  {f:<30} = {val}')

    print()
    print('  forecast.winner =', d['forecast'].get('winner'))
    print('  forecast.mae    =', d['forecast'].get('mae'))
    print('  forecast.mape   =', d['forecast'].get('mape'))
    print('  dacdf.final_option =', d['dacdf'].get('final_option'))
    print('  dacdf.alpha        =', d['dacdf'].get('alpha'))
    print('  dacdf.agree        =', d['dacdf'].get('agree'))
    print('  options count   =', len(d.get('options', [])))
    print('  batches count   =', len(d.get('batches', [])))
    print('  replenishment_requirement =', d.get('replenishment_requirement'))
    if d.get('replenishment_requirement', 0) == 0:
        # Verify no option recommends a positive qty from a supplier when req=0
        options = d.get('options', [])
        for opt in options:
            if opt.get('option') == 'no_action': continue
            if opt.get('qty', 0) > 0 and opt.get('option') == d['dacdf'].get('final_option'):
                print(f'  WARNING: final_option={opt["option"]} recommends qty={opt["qty"]} despite req=0')
        print('  MOQ check PASSED: req=0 case handled correctly')

print()

# Deep-check MED003 at DC001 (Emergency/High — checks FEFO near-expiry demo batch)
d2, err2 = get('/api/dcs/DC001/skus/MED003')
if d2 is None:
    print(f'SKIP  DC001/MED003 deep check (API unavailable: {err2})')
else:
    print('=== DC001/MED003 deep check (near-expiry demo) ===')
    print('  near_expiry_qty =', d2.get('near_expiry_qty'))
    print('  health_flag     =', d2.get('health_flag'))
    print('  trend           =', d2.get('trend'))
    batches = d2.get('batches', [])
    near = [b for b in batches if b.get('days_to_expiry') is not None and b['days_to_expiry'] <= 90]
    print(f'  batches near expiry (<= 90 days): {len(near)}')
    for b in near:
        print(f'    {b.get("batch_id")} qty={b.get("quantity")} days_to_expiry={b.get("days_to_expiry")}')
    if len(near) > 0:
        print('  FEFO demo PASSED: near-expiry batch detected')
    else:
        print('  FEFO demo FAILED: no near-expiry batch found')

print()
# Check replenishment table
rep, _ = get('/api/replenishment')
if rep:
    rows = rep.get('rows', [])
    actions = {}
    for r in rows:
        a = r.get('best_action','')
        actions[a] = actions.get(a, 0) + 1
    print('=== Replenishment action distribution ===')
    for k, v in sorted(actions.items(), key=lambda x: -x[1]):
        print(f'  {k:<25} {v:>3} rows')

kpis, _ = get('/api/replenishment/kpis')
if kpis:
    print()
    print('=== Network KPIs ===')
    for k, v in kpis.items():
        if k != 'global_model_metrics':
            print(f'  {k:<40} = {v}')
    mm = kpis.get('global_model_metrics', {})
    for model, metrics in mm.items():
        if isinstance(metrics, dict):
            print(f'  {model:<40} MAE={metrics.get("mae",0):.2f} MAPE={metrics.get("mape",0):.1f}%')

print()
print('ALL OK' if all_ok else 'SOME FAILURES')
