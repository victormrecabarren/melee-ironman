import roster from '../tools/melee/roster.json' with { type: 'json' };
export const CHARACTER_ROSTER = roster;
export function characterChoices(side) {
  const ordered=side===0?roster:[...roster].reverse();
  return ordered.flatMap((character,index)=>[2,1].map(stocks=>({character,index,stocks})));
}
export function selectCharacter(lineup,side,index,stocks) {
  if(![0,1].includes(side) || !Number.isInteger(index) || index<0 || index>=roster.length || ![1,2].includes(stocks))
    throw new Error('Invalid character selection');
  // A completed match resumes by replacing its exhausted side; never silently
  // restore stocks to the opponent as a side effect of a selection.
  if(lineup.players[1-side].index>=roster.length)throw new Error('Select the defeated side first');
  return withPlayedCharacters({...lineup,champion:null,
    players:lineup.players.map((player,i)=>i===side?{index,stocks}:{...player})});
}
export const initialLineup = () => withPlayedCharacters({ players:[{index:0,stocks:2},{index:0,stocks:2}], champion:null, stockHistory:[], played:[[],[]] });
export function lineupCharacter(lineup, side) {
  const index=lineup.players[side].index;
  return roster[side===0?index:roster.length-1-index];
}
export function lineupFighters(lineup) {
  return lineup.players.map((_,side)=>{
    const character=lineupCharacter(lineup,side);
    return character ? character.slug+(side===1?'-left':'') : null;
  });
}
export function takeStock(lineup,winner) {
  if (lineup.champion!==null || ![0,1].includes(winner)) throw new Error('Invalid stock result');
  const players=lineup.players.map(player=>({...player})), loser=1-winner;
  players[loser].stocks--;
  if (!players[loser].stocks) {
    players[loser].index++;
    if (players[loser].index<roster.length) players[loser].stocks=2;
  }
  const recorded=withPlayedCharacters(lineup);
  return {...recorded,players,champion:players[loser].index===roster.length?winner:null,
    stockHistory:[...(recorded.stockHistory || []),{side:winner,character:lineupCharacter(lineup,winner).slug,victim:lineupCharacter(lineup,loser).slug}]};
}

// Manual selections record who appeared, but never invent kills for skipped
// characters. Immutable history travels with each lineup's undo snapshot.
export function withPlayedCharacters(lineup) {
  const played=[0,1].map(side=>{
    const previous=lineup.played?.[side] || [];
    const slug=lineupCharacter(lineup,side)?.slug;
    return slug && !previous.includes(slug)?[...previous,slug]:previous;
  });
  return {...lineup,played};
}
export function playerStockStats(lineup,side) {
  return (lineup.played?.[side] || []).map(slug=>({
    character:roster.find(c=>c.slug===slug),
    victims:(lineup.stockHistory || []).filter(e=>e.side===side && e.character===slug).map(e=>roster.find(c=>c.slug===e.victim)),
  }));
}
