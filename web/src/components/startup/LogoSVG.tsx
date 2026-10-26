/** Original Scriptorium mark: offset pages and the negative space of an S. */
export const LOGO_PATH = 'M7 9C14 7 21 10 25 14V32C20 29 15 28 10 30V16C15 15 19 16 22 18V15C18 12 12 11 7 13ZM28 18C33 14 39 14 44 16V40C38 38 31 40 26 43V37C31 34 36 33 41 35V20C36 18 32 20 28 23Z';
export function LogoSVG({className,size=40}:{className?:string;size?:number}){
 return <svg className={className} viewBox="0 0 50 50" width={size} height={size} aria-hidden="true"><path d={LOGO_PATH} fill="currentColor"/></svg>;
}
