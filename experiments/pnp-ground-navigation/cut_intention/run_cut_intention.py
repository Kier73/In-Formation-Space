"""CIG-001 matched, reproducible local cost ledger and tiny exact oracles."""
from __future__ import annotations

import json
import platform
from statistics import median
from time import perf_counter_ns

from cut_intention import compile_ground, make_source, min_balanced_hub_norm_sq_numerator
from verify_cut_intention import verify
from test_cut_intention import brute, literal_rank


def measured(source,intention,cut,repetitions=11):
    # Each trial pays for a fresh compiler invocation plus original-CNF replay.
    samples=[]; final=None
    for _ in range(repetitions):
        cert,ledger=compile_ground(source,intention,cut)
        start=perf_counter_ns()
        assert verify(source,cert)
        verifier_ns=perf_counter_ns()-start
        samples.append({'construct_ns':ledger['construct_ns'],
                        'verify_ns':verifier_ns,
                        'total_ns':ledger['construct_ns']+verifier_ns})
        final=cert
    result={'certificate_bytes':ledger['symbolic_certificate_bytes'],
            'construct_ms_median':round(median(x['construct_ns'] for x in samples)/1e6,4),
            'verify_ms_median':round(median(x['verify_ns'] for x in samples)/1e6,4),
            'joint_ms_median':round(median(x['total_ns'] for x in samples)/1e6,4),
            'verified':True,'trials':repetitions}
    if intention=='CUT_RANK':
        result.update({'rank_log2':final['result']['log2_rank'],
                       'row_bits':final['result']['flattening_row_bits'],
                       'col_bits':final['result']['flattening_col_bits'],
                       'full_matrix_entries_log2':final['result']['matrix_entry_log2'],
                       'hub_norm_sq_numerator':final['geometry']['hub_norm_sq_numerator']})
    elif intention=='#SAT':
        result.update({'model_count_log2':final['result']['free_label_bits']})
    else:
        result.update({'status':final['result']['status']})
    return result


def main():
    rows=[]
    for k,l in [(3,1),(4,1),(6,1),(12,1),(24,2)]:
        source=make_source(k,l)
        cut=list(range(k//2))
        entries={intent:measured(source,intent,cut if intent=='CUT_RANK' else None)
                 for intent in ('SAT','#SAT','CUT_RANK')}
        legacy={}
        if source['n']<=12:
            # Deliberately naive oracles: charges exponential work, no hidden structural advice.
            reps=5; data=[]
            for _ in range(reps):
                start=perf_counter_ns(); models=brute(source)
                data.append(perf_counter_ns()-start)
            assert models==1<<(l*k*(k-1)//2)
            legacy['bruteforce_count_ms_median']=round(median(data)/1e6,4)
            data=[]
            for _ in range(reps):
                start=perf_counter_ns(); rank=literal_rank(source,set(cut))
                data.append(perf_counter_ns()-start)
            assert rank==1<<(l*len(cut)*(k-len(cut)))
            legacy['explicit_matrix_rank_ms_median']=round(median(data)/1e6,4)
        rows.append({'k':k,'label_bits':l,'source_variables':source['n'],
                     'source_clauses':len(source['clauses']),
                     'cut':cut,'cut_edges':len(cut)*(k-len(cut)),
                     'min_balanced_hub_four_norm_sq':min_balanced_hub_norm_sq_numerator(k),
                     'grounds':entries,'tiny_exhaustive_oracles':legacy or None})
    output={'schema':'ifs.cut-intention-campaign.v1',
            'environment':{'python':platform.python_version(),
                           'implementation':platform.python_implementation(),
                           'platform':platform.platform()},
            'ledger':'11 local trials per Ground; each charges fresh source compilation and separate original-CNF verification; no shared cache or external host',
            'matrix_note':'Matrix entries are described by log2 size, never materialized except independent tiny-oracle cases.',
            'cases':rows}
    print(json.dumps(output,indent=2))


if __name__=='__main__':main()
