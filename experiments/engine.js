/* Paper-only economy. No wallets, RPC calls, signatures, or real token data. */
(function(root){
 'use strict';
 const names=['Clover','Fig','Juniper','Miso','Olive','Pip','Sage','Taro','Willow','Zest'];
 class Economy {
  constructor(seed=42){
   this.seed=seed>>>0; this.tick=0; this.volume=0; this.trades=0; this.events=[]; this.history=[];
   this.outsideCash=20;
   this.pools=['BLOOM','MOSS','DEW'].map(name=>({name,eth:10,tokens:10000,previous:.001,outside:0}));
   this.flies=names.map((name,id)=>({id,name,cash:1,tokens:[0,0,0],goods:[id%2?2:5,id%2?5:2],role:id%2?'Silk spinner':'Nectar grower',earned:0,spent:0,trades:0,activity:'Ready to forage',x:14+(id%5)*18,y:32+Math.floor(id/5)*36,trail:[1]}));
  }
  random(){this.seed=(Math.imul(this.seed,1664525)+1013904223)>>>0;return this.seed/4294967296;}
  prices(){return this.pools.map(p=>p.eth/p.tokens);}
  worth(f){return f.cash+f.tokens.reduce((s,n,i)=>s+n*this.prices()[i],0);}
  exposure(f){return this.worth(f)-f.cash;}
  log(type,text,from=null,to=null,value=0){this.events.unshift({tick:this.tick,type,text,from,to,value});this.events.length=Math.min(100,this.events.length);}
  ask(f){const kind=f.id%2;return Math.max(.001,.012/(1+f.goods[kind]/4));}
  buy(f,i,spend){
   const p=this.pools[i];
   if(!Number.isFinite(spend)||spend<=0||spend>f.cash) return false;
   const units=p.tokens*spend*.997/(p.eth+spend*.997);
   const newPrice=(p.eth+spend)/(p.tokens-units);
   const exposure=f.tokens.reduce((s,n,j)=>s+(j===i?(n+units)*newPrice:n*this.prices()[j]),0);
   if(exposure>(f.cash-spend+exposure)*.5+1e-12)return false;
   f.cash-=spend;f.tokens[i]+=units;p.eth+=spend;p.tokens-=units;
   this.log('token',`${f.name} bought paper ${p.name}`,f.id,null,spend);return true;
  }
  sell(f,i,units){
   const p=this.pools[i];
   if(!Number.isFinite(units)||units<=0||units>f.tokens[i]+1e-12)return false;
   units=Math.min(units,f.tokens[i]);
   const proceeds=p.eth*units*.997/(p.tokens+units*.997);
   p.tokens+=units;p.eth-=proceeds;f.tokens[i]-=units;f.cash+=proceeds;
   this.log('token',`${f.name} sold paper ${p.name}`,f.id,null,proceeds);return true;
  }
  trade(buyer,seller){
   const kind=seller.id%2, price=this.ask(seller);
   if(buyer===seller||buyer.id%2===kind||seller.goods[kind]<1||buyer.cash<price||buyer.goods[kind]>=3)return false;
   // A fly buys an input only if its expected two-unit output exceeds the cost.
   if(this.ask(buyer)*2<=price*1.15)return false;
   buyer.cash-=price;seller.cash+=price;buyer.goods[kind]++;seller.goods[kind]--;
   buyer.spent+=price;seller.earned+=price;buyer.trades++;seller.trades++;this.volume+=price;this.trades++;
   buyer.activity=`Bought ${kind?'silk':'nectar'} from ${seller.name}`;seller.activity=`Sold ${kind?'silk':'nectar'} to ${buyer.name}`;
   this.log('trade',`${buyer.name} → ${seller.name} · ${kind?'silk':'nectar'}`,buyer.id,seller.id,price);return true;
  }
  rebalance(f){
   // Sell toward 48%, leaving room for rounding and AMM price impact.
   for(let i=0;i<3;i++){
    const excess=this.exposure(f)-this.worth(f)*.48;
    if(excess>1e-10&&f.tokens[i]>0)this.sell(f,i,Math.min(f.tokens[i],excess/this.prices()[i]*1.02));
   }
  }
  step(){
   this.tick++;
   // A bounded external paper trader moves AMM prices; its ETH is accounted for.
   for(const p of this.pools){
    p.previous=p.eth/p.tokens;
    if(this.random()>.46&&this.outsideCash>.02){
     const spend=Math.min(this.outsideCash,.015+this.random()*.08),units=p.tokens*spend*.997/(p.eth+spend*.997);
     p.eth+=spend;p.tokens-=units;p.outside+=units;this.outsideCash-=spend;
    }else if(p.outside>0){
     const units=p.outside*(.05+this.random()*.3),cash=p.eth*units*.997/(p.tokens+units*.997);
     p.tokens+=units;p.eth-=cash;p.outside-=units;this.outsideCash+=cash;
    }
   }
   const order=[...this.flies];
   for(let i=order.length-1;i>0;i--){const j=Math.floor(this.random()*(i+1));[order[i],order[j]]=[order[j],order[i]];}
   for(const f of order){
    const own=f.id%2,input=1-own;
    f.goods=f.goods.map(n=>n*.96);
    f.activity='Foraging';
    if(f.goods[input]>=1&&f.goods[own]<12){f.goods[input]-=1;f.goods[own]+=2+(f.id%3)*.15;f.activity=own?'Spinning silk':'Growing nectar';}
    else f.goods[own]+=.15; // Slow gathering means no fly becomes permanently stuck.
    const sellers=order.filter(s=>s.id%2===input&&s.goods[input]>=1).sort((a,b)=>this.ask(a)-this.ask(b));
    if(f.goods[input]<2) for(const seller of sellers){if(this.trade(f,seller))break;}
    this.rebalance(f);
    const i=(this.tick+f.id)%3,p=this.pools[i],momentum=p.eth/p.tokens/p.previous-1;
    if(momentum<-.001&&f.tokens[i]>0)this.sell(f,i,f.tokens[i]*.2);
    else if(momentum>.0005){
     const room=this.worth(f)*.45-this.exposure(f);
     if(room>.001)this.buy(f,i,Math.min(room*.7,this.worth(f)*.07));
    }
    // Readable spatial markers; positions do not determine economic outcomes.
    f.x=14+(f.id%5)*18+Math.sin(this.tick*.2+f.id)*3;
    f.y=32+Math.floor(f.id/5)*36+Math.cos(this.tick*.15+f.id)*7;
   }
   this.flies.forEach(f=>this.rebalance(f));
   this.flies.forEach(f=>{f.trail.push(this.worth(f));if(f.trail.length>80)f.trail.shift();});
   this.history.push({tick:this.tick,wealth:this.flies.reduce((s,f)=>s+this.worth(f),0),trades:this.trades});
   if(this.history.length>200)this.history.shift();
   return this;
  }
  audit(){
   const total=this.flies.reduce((s,f)=>s+f.cash,0)+this.pools.reduce((s,p)=>s+p.eth,0)+this.outsideCash;
   return {ethConserved:Math.abs(total-60)<1e-8,total,capRespected:this.flies.every(f=>this.exposure(f)<=this.worth(f)*.5+1e-8),balancesValid:this.flies.every(f=>Number.isFinite(f.cash)&&f.cash>=0&&f.tokens.every(n=>Number.isFinite(n)&&n>=0)&&f.goods.every(n=>Number.isFinite(n)&&n>=0)),tokensConserved:this.pools.every((p,i)=>Math.abs(p.tokens+p.outside+this.flies.reduce((s,f)=>s+f.tokens[i],0)-10000)<1e-6)};
  }
 }
 if(typeof module!=='undefined'&&module.exports)module.exports={Economy};else root.Economy=Economy;
})(typeof globalThis!=='undefined'?globalThis:this);
