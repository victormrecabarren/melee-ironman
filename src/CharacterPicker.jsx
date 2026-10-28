import React, {useEffect,useRef} from 'react';
import {characterChoices} from './previewRoster.js';

export default function CharacterPicker({side,current,base,manifest,busy,error,onPick,onClose}) {
  const dialog=useRef(null),selected=useRef(null);
  useEffect(()=>{
    const node=dialog.current,previousOverflow=document.documentElement.style.overflow;
    node.showModal();
    document.documentElement.style.overflow='hidden';
    selected.current?.focus({preventScroll:true});
    selected.current?.scrollIntoView({block:'nearest'});
    return()=>{document.documentElement.style.overflow=previousOverflow;node.close();};
  },[]);
  return <dialog ref={dialog} className={`character-picker picker-side-${side}`} aria-labelledby="character-picker-title"
    onCancel={event=>{event.preventDefault();if(!busy)onClose();}}
    onClick={event=>{if(event.target===event.currentTarget&&!busy)onClose();}}>
    <div className="character-picker-panel">
      <header><h2 id="character-picker-title">Player {side+1}</h2><button onClick={onClose} disabled={busy} aria-label="Close character picker">×</button></header>
      <div className="character-picker-options" aria-busy={busy}>
        {characterChoices(side).map(({character,index,stocks})=>{
          const active=current.index===index && current.stocks===stocks;
          const clip=manifest.environment['stock-'+character.slug];
          return <button key={`${index}:${stocks}`} ref={active?selected:undefined} className={stocks===2?'character-choice pair-first':'character-choice'}
            aria-label={`${character.name}, ${stocks} ${stocks===1?'stock':'stocks'}`} aria-pressed={active} disabled={busy}
            onClick={()=>onPick(index,stocks)}>
            {Array.from({length:stocks},(_,i)=><img key={i} src={base+(clip.sourceAtlas || clip.file)} width="32" height="32" alt="" draggable="false" />)}
          </button>;
        })}
      </div>
      {busy && <p role="status">Preparing character…</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  </dialog>;
}
