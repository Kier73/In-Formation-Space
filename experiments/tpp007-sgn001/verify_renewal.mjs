/** Independent source-byte receiver for TPP-007 context-renewal receipts.
 * Does not import Python, NumPy, SGN or a trusted model executor.
 * Verifies retrospective witness only. Never authorizes a future day.
 */
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';

const SOURCE_SCHEMA = 'in-formation-space.tpp007.seven-day-residual-continuity.v1';
const SGN_SCHEMA = 'ifs.tpp007-sgn001.chronological-qualification.v1';
const RENEW_SCHEMA = 'ifs.tpp007-sgn001.context-renewal.v1';
const SGN_SHA = '000108a8a6a52346ad6e658ed07695fd917281137040187f56da8e676749eabf';
const HASHES = {
  water_level:'8a31edbda35209261cbba2cc1fa8d7e3955449fda2d928ac31287028bc74f79d',
  predictions:'7bb2a2a473aac47a268991816aa7e23f06a12daaa7dbf7922bb60d514ad413f8'
};
const POLICY = {
  adaptive_threshold_multiplier:2, min_improvement_percent:15,
  samples_per_day:240, method:'lagged-median-residual-on-context-change',
  version:'1.0'
};
const DAYS = Array.from({length:7}, (_,i) => '2026-11-' + (13+i));
function check(x,msg) {if(!x) throw new Error(msg);}
function stable(x) {
  if(x === null || typeof x !== 'object') return JSON.stringify(x);
  if(Array.isArray(x)) return '[' + x.map(stable).join(',') + ']';
  return '{' + Object.keys(x).sort().map(k => JSON.stringify(k) + ':' + stable(x[k])).join(',') + '}';
}
const hash = x => createHash('sha256').update(x).digest('hex');
const id = x => hash(Buffer.from(stable(x), 'utf8'));
function parseMilli(s) {
  check(typeof s === 'string' && /^-?(?:0|[1-9]\d*)(?:\.\d{1,3})?$/.test(s), 'source decimal invalid');
  const neg = s.startsWith('-');
  const [integer, fraction=''] = (neg ? s.slice(1) : s).split('.');
  const result = BigInt(integer)*1000n + BigInt((fraction + '000').slice(0,3));
  return neg ? -result : result;
}
function originalSeries(archive) {
  check(archive?.schema === SOURCE_SCHEMA &&
        archive.acquisition === 'real-public-two-batched-requests' &&
        archive.actual_request_attempts === 2 &&
        archive.assessment?.status === 'complete' &&
        stable(archive.assessment.source_sha256) === stable([HASHES.water_level,HASHES.predictions]),
        'original source schema or digest invalid');
  const src = {};
  for(const d of archive.documents ?? []) {
    const product = d.product;
    check(Object.hasOwn(HASHES,product) && !Object.hasOwn(src,product), 'unrecognized/duplicate source');
    check(d.status === 'received' &&
          d.scope === 'public-provider-read-only-no-instrument-attestation' &&
          d.start_utc_day === '20261113' && d.end_utc_day === '20261119', 'source scope refused');
    const url = new URL(d.source);
    check(url.protocol === 'https:' && url.hostname === 'api.tidesandcurrents.noaa.gov' &&
          url.pathname === '/api/prod/datagetter', 'source URL refused');
    for(const [name,value] of Object.entries({
      station:'9414290', product, datum:'MLLW',units:'metric',
      time_zone:'gmt',format:'json',begin_date:'20261113',end_date:'20261119'})) {
      check(url.searchParams.getAll(name).length === 1 &&
            url.searchParams.get(name) === value, 'source reference refused');
    }
    check(typeof d.raw_body_base64 === 'string' &&
          /^[a-zA-Z0-9+/]+={0,2}$/.test(d.raw_body_base64), 'invalid source base64');
    const body = Buffer.from(d.raw_body_base64, 'base64');
    check(body.toString('base64') === d.raw_body_base64 &&
          body.length === d.raw_bytes &&
          hash(body) === HASHES[product] &&
          d.raw_sha256 === HASHES[product], 'original provider bytes not pinned');
    const json = JSON.parse(body.toString('utf8'));
    if(product === 'water_level')
      check(String(json.metadata?.id) === '9414290', 'unexpected physical station');
    const rows = product === 'water_level' ? json.data : json.predictions;
    check(Array.isArray(rows), 'missing product rows');
    const readings = new Map();
    for(const row of rows) {
      check(typeof row.t === 'string' && !readings.has(row.t), 'duplicate/invalid timestamp');
      if(product === 'water_level')
        check(['p','v'].includes(row.q) && typeof row.f === 'string', 'physical quality refused');
      readings.set(row.t, parseMilli(row.v));
    }
    check(readings.size === 1680, 'incomplete original observation');
    const start = Date.parse('2026-11-13T00:00:00.000Z');
    const values = [];
    for(let i=0;i<1680;i++) {
      const stamp = new Date(start+360000*i).toISOString().slice(0,16).replace('T',' ');
      check(readings.has(stamp), 'missing six-minute timestamp');
      values.push(readings.get(stamp));
    }
    src[product] = values;
  }
  check(Object.keys(src).length === 2, 'missing evidence product');
  return src.water_level.map((x,i) => x-src.predictions[i]);
}
function twiceMedian(xs) {
  check(xs.length > 0, 'empty data median');
  const a = [...xs].sort((x,y) => x < y ? -1 : (x > y ? 1 : 0));
  const m = Math.floor(a.length/2);
  return a.length % 2 ? 2n*a[m] : a[m-1]+a[m];
}
const day = (xs,i) => xs.slice(i*240,(i+1)*240);
const abs = x => x < 0n ? -x : x;
const error = (xs,offset) => xs.reduce((sum,x) => sum+abs(2n*x-offset),0n);
const toNum = x => {
  check(x <= BigInt(Number.MAX_SAFE_INTEGER) && x >= -BigInt(Number.MAX_SAFE_INTEGER),
        'unsafe serialized integer');
  return Number(x);
};
function reconstruct(archive,sgn) {
  const xs = originalSeries(archive);
  check(id(sgn) === SGN_SHA && sgn.schema === SGN_SCHEMA, 'SGN artifact identity refused');
  check(stable(sgn.physical_evidence) === stable(HASHES) &&
        stable(sgn.splits) === stable({
          train:[1,720],validation:[721,1200],final_test:[1201,1680]
        }), 'SGN physical reference differed');
  for(const lane of ['noaa_residual','water_level']) {
    check(sgn.lanes?.[lane]?.effective_admission === 'refused_after_independent_test' &&
          sgn.lanes[lane].held_out_test?.status === 'failed_out_of_sample',
          'not a refused spectral predecessor');
  }
  const calibration = Array.from({length:5}, (_,i) => twiceMedian(day(xs,i)));
  const changes = calibration.slice(1).map((x,i) => abs(x-calibration[i]));
  const threshold = twiceMedian(changes);
  const prior = calibration[4], candidate = twiceMedian(day(xs,5));
  const shift = abs(candidate-prior);
  const triggered = shift>threshold;
  const pretarget = {
    status:'provisional_not_admitted',
    prior_observed_day:DAYS[4],renewal_observed_day:DAYS[5],proposed_target_day:DAYS[6],
    previous_offset_twice_millimetres:toNum(prior),
    candidate_offset_twice_millimetres:toNum(candidate),
    measured_shift_twice_millimetres:toNum(shift),
    calibration_window_utc_days:[DAYS[0],DAYS[4]],
    calibration_adjacent_shifts_twice_millimetres:changes.map(toNum),
    calibrated_threshold_twice_millimetres:toNum(threshold),
    renewal_triggered:triggered,
    available_through_utc:DAYS[5]+'T23:54:00Z',
    not:'no_target_observations_or_future_authority'
  };
  let posttarget;
  if(!triggered) {
    posttarget = {
      status:'renewal_not_triggered',target_day:DAYS[6],
      scope:'no newly qualified physical Ground'
    };
  } else {
    const target=day(xs,6), original=error(target,0n),
          stale=error(target,prior), renewed=error(target,candidate);
    const corroborated = 100n*renewed <=
      BigInt(100-POLICY.min_improvement_percent)*original && renewed<stale;
    posttarget = {
      status:corroborated ? 'historically_corrob_for_target_only' :
        'refused_after_target_observation',
      target_day:DAYS[6],scored_samples:target.length,
      error_units:'sum_of_absolute_half_millimetres',
      uncorrected_error:toNum(original),stale_context_error:toNum(stale),
      renewed_candidate_error:toNum(renewed),
      scope:'retrospective single-day physical observation; no future authorization'
    };
  }
  const payload = {
    schema:RENEW_SCHEMA,
    source:{station:'9414290',datum:'MLLW',units:'metric',
            retrieval:'retrospective',provider_quality:'preliminary',source_sha256:HASHES},
    policy:POLICY,
    predecessor:{kind:'spectral',status:'refused_after_independent_test',
      report_sha256:SGN_SHA,
      not:'independent_receipt_checksum_is_not_source_authentication'},
    pretarget,posttarget,
    authority:{state:'retrospective_witness_only',
      executable_next_unobserved_day:false,
      requires:'receiver-owned-source-admission-and-new-out-of-sample-evidence'}
  };
  return {payload,sha256:id(payload)};
}
export function verify(receipt,archive,sgn) {
  check(receipt && Object.keys(receipt).sort().join(',') === 'payload,sha256',
        'invalid receipt envelope');
  check(receipt.sha256 === id(receipt.payload), 'receipt self-digest rejected');
  const expected = reconstruct(archive,sgn);
  check(stable(expected) === stable(receipt), 'source-reconstructed claims differ');
  return {status:'verified_retrospective_only',receipt_sha256:receipt.sha256,
          pretarget_status:receipt.payload.pretarget.status,
          posttarget_status:receipt.payload.posttarget.status,
          executable_next_unobserved_day:false};
}
if(process.argv[1]?.endsWith('verify_renewal.mjs')) {
  try {
    check(process.argv.length === 5,
          'usage: node verify_renewal.mjs ARCHIVE.json SGN.json RECEIPT.json');
    const [archive,sgn,receipt] = process.argv.slice(2).map(p =>
      JSON.parse(readFileSync(p,'utf8')));
    console.log(JSON.stringify(verify(receipt,archive,sgn)));
  } catch(error) {
    console.error('REFUSED: '+error.message);
    process.exitCode = 1;
  }
}
