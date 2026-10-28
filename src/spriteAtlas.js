export function clipFiles(clip) {
  return clip.pages ? clip.pages.map(page=>page.file) : [clip.file];
}
export function spriteFrame(clip,index,layout) {
  if(clip.pages) {
    const [page,x,y,width,height,dx,dy]=clip.rects[index];
    return {file:clip.pages[page].file,x,y,width,height,dx,dy};
  }
  return {file:clip.file,x:index%layout.columns*layout.width,y:Math.floor(index/layout.columns)*layout.height,
    width:layout.width,height:layout.height,dx:0,dy:0};
}
