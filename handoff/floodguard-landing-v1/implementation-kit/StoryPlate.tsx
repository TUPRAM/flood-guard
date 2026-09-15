/* Integration example, not the finished landing page. Keep the real app's imports/CSS conventions. */
/* eslint-disable @next/next/no-img-element -- responsive preoptimized art supports static export. */
import { useId, type CSSProperties } from 'react';
import { cropImageStyle, polylinePath, routeSegments, type Crop, type Point } from './story-math.mjs';

type Label = { id: string; text: string; at: Point };
type Props = {
  src: string;
  srcSet?: string;
  sizes?: string;
  crop: Crop;
  route: Point[];
  affected: { startIndex: number; endIndex: number };
  showRoute?: boolean;
  routeAffected?: boolean;
  selectionPath?: string | null;
  labels?: Label[];
  description: string;
  caption?: string;
  eager?: boolean;
};

export function StoryPlate({src,srcSet,sizes,crop,route,affected,showRoute=true,routeAffected=false,selectionPath,labels=[],description,caption='Illustrative scenario · Not current conditions',eager=false}:Props) {
  const id = useId();
  const segments = routeSegments(route, affected.startIndex, affected.endIndex);
  const style:CSSProperties = {position:'relative',overflow:'hidden',aspectRatio:`${crop[2]} / ${crop[3]}`};
  return (
    <figure className="fg-plate" aria-describedby={`${id}-description`}>
      <div className="fg-plate__frame" style={style}>
        <img src={src} srcSet={srcSet} sizes={sizes} width={1536} height={1024}
          alt="" loading={eager?'eager':'lazy'} decoding="async" fetchPriority={eager?'high':undefined}
          style={{position:'absolute',maxWidth:'none',...cropImageStyle(crop)}} />
        <svg className="fg-plate__overlay" viewBox={crop.join(' ')} aria-hidden="true" focusable="false"
          style={{position:'absolute',inset:0,width:'100%',height:'100%',pointerEvents:'none'}}>
          {selectionPath && <path d={selectionPath} fill="none" stroke="var(--fg-brand)" strokeWidth="1.5" strokeDasharray="5 5" vectorEffect="non-scaling-stroke" />}
          {showRoute && <>
            <path d={polylinePath(route)} fill="none" stroke="#fffdf7" strokeWidth="7" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            <path d={polylinePath(route)} fill="none" stroke="var(--fg-route)" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
            {routeAffected && <path d={polylinePath(segments.affected)} fill="none" stroke="var(--fg-review)" strokeWidth="4" strokeDasharray="9 6" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />}
          </>}
        </svg>
        {labels.map(label=><span key={label.id} className="fg-plate__label" style={{position:'absolute',left:`${(label.at[0]-crop[0])/crop[2]*100}%`,top:`${(label.at[1]-crop[1])/crop[3]*100}%`}}>{label.text}</span>)}
      </div>
      <figcaption>{caption}</figcaption>
      <p id={`${id}-description`} className="fg-sr-only">{description}</p>
    </figure>
  );
}
