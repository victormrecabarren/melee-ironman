import roster from '../tools/melee/roster.json' with { type: 'json' };
export const CHARACTER_ROSTER = roster;
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
