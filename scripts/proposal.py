"""Pickup reallocation analysis: 13 underutilized store pickups -> 2027 lifecycle replacements."""
import json, sys
sys.path.insert(0, '.')
from load import fuel
from odo import clean_odo
d = json.load(open('data.json')); A = {a['id']: a for a in d['assets']}
C = ['maint', 'fuel_card', 'onsite', 'propane', 'dep', 'reg', 'tax']
RATE, NEW, MONTHS = 995.46, 55000, 10
F = fuel()

# store-to-door pickup ranking (stores 001-121)
by = {}
for a in d['assets']:
    if a.get('pk') == 1 and a['c'] == 'LD Vehicle' and a['s'].isdigit() and 1 <= int(a['s']) <= 121:
        g = by.setdefault(a['s'], [0, 0]); g[0] += sum(sum(a[c]) for c in C); g[1] += sum(a['mi'])
cpm_order = sorted([s for s in by if by[s][1] > 0], key=lambda s: -by[s][0] / by[s][1])
mi_order = sorted([s for s in by if by[s][1] > 0], key=lambda s: by[s][1])
donor_stores = [s for s in cpm_order[:15] if s in mi_order[:15]]
# combined rank = CPM rank + miles rank (lowest = worst); #12 Laredo and #13 Brazoria added 11/11/26
combo = sorted(cpm_order, key=lambda s: (cpm_order.index(s) + mi_order.index(s), cpm_order.index(s)))
donor_stores += ['41', '3']
# explicit placements from Fleet: donor truck -> (receiving location, truck replaced)
FIXED_PAIR = {'601009': ('764', '599002'), '601026': ('761', '600014')}

ODO_CONFIRMED = {'600008': 30795, '600005': 39155, '598008': 147504, '601030': 5330, '601039': 23499, '601036': 15094, '601025': 19828, '601037': 9231, '601008': 16519, '601048': 17395, '600001': 16476, '601031': 20177, '599007': 202236, '599003': 148529, '596007': 137636, '599030': 119212, '600006': 148990, '596002': 137888, '599025': 137002, '597002': 132429, '599019': 195427, '599004': 167755, '600013': 189155, '601009': 24665, '601026': 16154, '599002': 173967, '600014': 140650}   # GPS / Fleet readings 11/11/26 (override fuel-card odometers)
def odo(unit, a):
    if unit in ODO_CONFIRMED: return dict(odo=float(ODO_CONFIRMED[unit]), odo_dt='2026-11-11', odo_est=False, odo_conf=True)
    o, dt = (None, None) if unit == '600005' else clean_odo(F, int(unit))   # Odessa card shows several vehicles' odometers
    if o: return dict(odo=o, odo_dt=dt, odo_est=False)
    y, m = int(a['o'][:4]), int(a['o'][5:7]); yrs = ((2026 - y) * 12 + (10 - m)) / 12
    return dict(odo=round(sum(a['mi']) / MONTHS * 12 * yrs), odo_dt='', odo_est=True)

donors = []
for s in donor_stores:
    u = [a for a in d['assets'] if a['s'] == s and a.get('pk') == 1 and a['c'] == 'LD Vehicle' and a['r']][0]
    y, m = int(u['o'][:4]), int(u['o'][5:7]); el = (2026 - y) * 12 + (10 - m) + 1
    ann = lambda keys: sum(sum(u[k]) for k in keys) / MONTHS * 12
    donors.append(dict(store=s, name=d['stores'][s]['name'], dist=d['stores'][s]['district'], unit=u['id'], orig=u['o'], cost=u['cost'],
        mi=sum(u['mi']), annmi=sum(u['mi']) / MONTHS * 12, cpm=by[s][0] / by[s][1], rank=combo.index(s) + 1, cpmrank=cpm_order.index(s) + 1, mirank=mi_order.index(s) + 1,
        ex=ann(['maint', 'dep', 'reg', 'tax']), fuel=ann(['fuel_card']), dep=ann(['dep']), maint=ann(['maint']), regtax=ann(['reg', 'tax']),
        nbv=max(0, u['cost'] - u['cost'] / 60 * el), **odo(u['id'], u)))

# receiving stores, ordered by current annual miles (new store last)
REC = [('450', '599007'), ('52', '599003'), ('63', '598008'), ('8', '596007'), ('450', '599004'), ('67', '600006'),
       ('18', '596002'), ('53', '599025'), ('70', '597002'), ('450', '599019'), ('766', '600013')]   # 599019 replaces Okmulgee 594179; 599004 replaces Liberty Hill 599030 (11/11/26)
recs = []
for s, ru in REC:
    r = A.get(ru) if ru else None
    o = (float(ODO_CONFIRMED[ru]) if ru in ODO_CONFIRMED else clean_odo(F, int(ru))[0]) if ru else None
    recs.append(dict(store=s, name=d['stores'].get(s, {}).get('name', 'Canyon Lake'), fixed=(ru == '600013'), repl=ru, repl_o=r['o'] if r else '',
                     repl_annmi=sum(r['mi']) / MONTHS * 12 if r else None, repl_odo=o, why='Fleet Lifecycle' if ru else 'Fleet Addition - New Store'))
# rank by annual miles; 600013 (Region 6) placed last per Fleet (Canyon Lake removed 11/11/26)
recs = sorted([r for r in recs if r['repl'] and not r['fixed']], key=lambda r: -r['repl_annmi']) + [r for r in recs if r['fixed']] + [r for r in recs if not r['repl']]
# lowest-mileage trucks go to the highest-usage receiving stores
def rec_for(s, ru):
    r = A.get(ru)
    return dict(store=s, name=d['stores'].get(s, {}).get('name', s), fixed=True, repl=ru, repl_o=r['o'] if r else '',
                repl_annmi=sum(r['mi']) / MONTHS * 12 if r else None, repl_odo=float(ODO_CONFIRMED.get(ru)) if ru in ODO_CONFIRMED else None, why='Fleet Lifecycle')
free = [dn for dn in donors if dn['unit'] not in FIXED_PAIR]
for dn in donors:
    if dn['unit'] in FIXED_PAIR: dn['to'] = rec_for(*FIXED_PAIR[dn['unit']])
for dn, rc in zip(sorted(free, key=lambda x: x['odo']), recs):
    dn['to'] = rc
unfilled = recs[len(free):]
json.dump(dict(rate=RATE, new_truck=NEW, rates=d['rates'], donors=donors, unfilled=unfilled, built='2026-11-11'), open('proposal.json', 'w'))
for dn in sorted(donors, key=lambda x: x['odo']):
    print(dn['store'], dn['name'], dn['unit'], int(dn['odo']), 'est' if dn['odo_est'] else '', '->', dn['to']['store'], dn['to']['name'], dn['to']['repl'], dn['to']['repl_odo'], round(dn['to']['repl_annmi'] or 0))
print(len(donors), 'billing', RATE * 12 * len(donors), 'ex', round(sum(x['ex'] for x in donors)))
