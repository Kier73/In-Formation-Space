function screen(){
 const max=(...xs)=>xs.reduce((a,b)=>a>b?a:b);
 function floorRoot(x,k){let lo=0n,hi=1n;while(hi**k<=x)hi*=2n;while(hi-lo>1n){let m=(hi+lo)/2n;if(m**k<=x)lo=m;else hi=m}return lo}
 function ceilRoot(x,k){let t=floorRoot(x,k);return t**k===x?t:t+1n}
 function square(n){return max(2n*n*n-1n,(5n*n*n-6n*n+1n)/2n)}
 function shape(a,b,c){let v=a*b*c,min=a<b?a:b;min=min<c?min:c;let basic=max(a*b+c-1n,a*c+b-1n,b*c+a-1n),restricted=square(min),cyclic=ceilRoot(square(v),3n),lb=max(basic,restricted,cyclic),target=floorRoot(v**3n-1n,4n);return {shape:[Number(a),Number(b),Number(c)],volume:Number(v),target:Number(target),slice:Number(basic),restriction:Number(restricted),cyclic:Number(cyclic),lower:Number(lb),admissible:lb<=target}}
 let rows=[];for(let n=2n;n<=128n;n++){let v=n**9n-1n,t=floorRoot(v,4n),lb=square(n);if(t**4n>v||(t+1n)**4n<=v)throw Error("root");rows.push({n:Number(n),target:Number(t),alderStrassen:Number(2n*n*n-1n),blaser:Number((5n*n*n-6n*n+1n)/2n),lower:Number(lb),notExcluded:lb<=t})}
 let counts={total:0,oldPruned:0,newPruned:0},eligible=[],newly=[];
 for(let a=1n;a<=48n;a++)for(let b=a;b<=48n;b++)for(let c=b;c<=48n;c++){if(a*b*c===1n)continue;let z=shape(a,b,c);counts.total++;if(z.slice>z.target)counts.oldPruned++;if(!z.admissible){counts.newPruned++;if(z.slice<=z.target)newly.push(z)}else eligible.push(z)}
 eligible.sort((a,b)=>a.volume-b.volume||a.target-b.target);
 newly.sort((a,b)=>a.volume-b.volume);
 return {square:rows,firstSquareNotExcluded:rows.find(x=>x.notExcluded),counts,firstEligible:eligible.slice(0,20),examplesNewlyPruned:newly.slice(0,10),scope:"exact rank; necessary screening only; not border rank or existence"};
}
console.log(JSON.stringify(screen(),null,2));
